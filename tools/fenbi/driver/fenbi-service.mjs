// 单 Owner 连续采集服务：目录巡检 → 建队列 → 采集 → 交白卷/解析 → 回填 → 资产补下载。
// 只写 Owner 本地 work/fenbi；不 push、不 promote、不做集成树操作。
// 单实例（锁文件）、STOP 感知、风控即停、可断点续跑（台账/状态文件）。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { setTimeout as sleep } from 'node:timers/promises';
import { FOCUS_REGIONS, chooseFocusScan, applyFocusSuccess, applyRegionScan } from './focus-schedule.mjs';

const pexec = promisify(execFile);
const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const RUN = WORK + '/t2-20261019';
const STOP = WORK + '/STOP';
const LOG = RUN + '/service.log';
const LOCK = RUN + '/service.lock';
const STATE = RUN + '/service-state.json';
const NODE = process.execPath;
const DRIVER = path.dirname(fileURLToPath(import.meta.url));
const CAND = WORK + '/candidates-live.json';
const CAT = WORK + '/catalog-live-20261019';

// 每轮固定开销（目录巡检、建队列、启动浏览器、轮间等待）按批摊薄：批越小，每卷分摊越多。
const BATCH = Number(process.env.SERVICE_BATCH || 30);
const INTERVAL = Number(process.env.SERVICE_INTERVAL || 10) * 1000;
// 非风控类失败（超时、网络、找不到行等）不写 STOP，退避后继续；风控信号仍立即停。
const BACKOFF = Number(process.env.SERVICE_BACKOFF || 900) * 1000;
const EMPTY_RESCAN = Number(process.env.SERVICE_EMPTY_RESCAN || 1800) * 1000;
const OTHER_REGIONS = ['安徽', '甘肃', '广西', '贵州', '海南', '河北', '河南', '黑龙江', '湖北', '湖南',
  '吉林', '江西', '辽宁', '内蒙古', '宁夏', '青海', '山东', '山西', '陕西', '四川', '西藏', '新疆', '云南', '重庆'];
const CHUNK = Number(process.env.SERVICE_REGION_CHUNK || 3);
// 重点区：低占空比、每次只扫 1 个地区；10 区 × 30min 约 5h 一轮，避免与常规队列抢带宽。
const FOCUS_RESCAN = Number(process.env.SERVICE_FOCUS_RESCAN || 7200) * 1000;
const FOCUS_PAGES = Number(process.env.SERVICE_FOCUS_PAGES || 8);

const log = async (event, extra = {}) => {
  const line = JSON.stringify({ at: new Date().toISOString(), event, ...extra });
  await fs.appendFile(LOG, line + '\n', { mode: 0o600 }).catch(() => {});
  console.log(line);
};
const readJson = async (p, d = null) => { try { return JSON.parse(await fs.readFile(p, 'utf8')); } catch { return d; } };
const writeJson = async (p, obj) => {
  const tmp = p + '.tmp'; await fs.writeFile(tmp, JSON.stringify(obj, null, 2) + '\n', { mode: 0o600 }); await fs.rename(tmp, p);
};
const alive = pid => { try { process.kill(pid, 0); return true; } catch { return false; } };

// ---------- 单实例 ----------
try {
  const old = await fs.readFile(LOCK, 'utf8').catch(() => null);
  const pid = Number((old || '').split(':')[0]);
  if (old && Number.isFinite(pid) && pid !== process.pid && alive(pid)) {
    console.log(JSON.stringify({ ok: false, code: 'ALREADY_RUNNING', pid }));
    process.exit(0);
  }
  await fs.unlink(LOCK).catch(() => {});
  await fs.writeFile(LOCK, `${process.pid}:${new Date().toISOString()}`, { mode: 0o600, flag: 'wx' });
} catch { console.log(JSON.stringify({ ok: false, code: 'LOCK_RACE' })); process.exit(0); }
const release = async () => { try { const v = await fs.readFile(LOCK, 'utf8'); if (v.startsWith(`${process.pid}:`)) await fs.unlink(LOCK); } catch {} };

const state = (await readJson(STATE)) || { schemaVersion: 1, startedAt: new Date().toISOString(),
  rounds: 0, regionIndex: 0, lastDiscoveryAt: null, lastEmptyRescanAt: null, newPapers: 0, stops: [] };
state.regions ||= {};
state.focusIndex ||= 0;
state.focusScans ||= 0;
state.focusFailures ||= 0;

// 用既有目录快照种子化 firstIndexedAt/lastScannedAt：重启不把旧地区误记为“首次索引”，
// 也不会因状态文件缺失而立刻重扫全部地区。
async function seedRegionState() {
  const apply = (at, regions) => {
    if (!at) return;
    for (const r of Object.keys(regions || {})) {
      const rs = (state.regions[r] ||= {});
      if (!rs.firstIndexedAt || Date.parse(at) < Date.parse(rs.firstIndexedAt)) rs.firstIndexedAt = at;
      if (!rs.lastScannedAt || Date.parse(at) > Date.parse(rs.lastScannedAt)) rs.lastScannedAt = at;
    }
  };
  for (const f of (await fs.readdir(CAT).catch(() => [])).filter(f => /^catalog-.*\.json$/.test(f))) {
    const j = await readJson(path.join(CAT, f));
    if (j?.at) apply(j.at, j.regions);
  }
  const old = await readJson(WORK + '/p0-discover-20261019/p0-pages.json');
  if (old?.at) apply(old.at, old.regions);
  if (!state.focusLastScanAt) {
    const lasts = FOCUS_REGIONS.map(r => Date.parse(state.regions[r]?.lastScannedAt || 0)).filter(t => t > 0);
    if (lasts.length) state.focusLastScanAt = new Date(Math.max(...lasts)).toISOString();
  }
}
await seedRegionState();

// 子进程：stdout 末尾 JSON 行解析；退出码 0 或 2 视为正常。
async function step(name, file, args, env, timeoutMs) {
  const before = (await fs.readdir(WORK + '/papers').catch(() => [])).length;
  let out = '', err = '', code = 0;
  try {
    const r = await pexec(NODE, [file, ...args], { timeout: timeoutMs, maxBuffer: 16 * 1024 * 1024,
      env: { ...process.env, DISPLAY: ':77', ...env } });
    out = r.stdout; err = r.stderr;
  } catch (e) { code = e.code ?? -1; out = e.stdout || ''; err = e.stderr || ''; }
  const after = (await fs.readdir(WORK + '/papers').catch(() => [])).length;
  let summary = null;
  for (const line of out.trim().split('\n').reverse()) {
    const i = line.indexOf('{');
    if (i >= 0) { try { summary = JSON.parse(line.slice(i)); break; } catch {} }
  }
  await log('step', { name, code, newPapers: after - before, summary: summary && (summary.metrics || summary.risk || summary.ok !== undefined ? summary : { ok: summary.ok }) });
  return { code, summary, newPapers: after - before, stderr: err.slice(-400) };
}
const stopNow = async (reason, extra = {}) => {
  await fs.writeFile(STOP, JSON.stringify({ at: new Date().toISOString(), by: 'fenbi-service', reason, ...extra }) + '\n', { mode: 0o600 });
  await log('stop', { reason, ...extra });
};
const riskHit = s => s && s.risk && (s.risk.captcha || s.risk.loginLost || s.risk.http403 || s.risk.http429);
const backoff = async (reason, extra = {}) => {
  await log('backoff', { reason, seconds: BACKOFF / 1000, ...extra });
  await writeJson(STATE, state);
  await sleep(BACKOFF);
};

if (process.env.FENBI_SERVICE_DRY_RUN === '1') {
  const f = chooseFocusScan(state, FOCUS_REGIONS, Date.now(), FOCUS_RESCAN);
  console.log(JSON.stringify({ ok: true, dryRun: true, pid: process.pid, regionIndex: state.regionIndex,
    regionsSeeded: Object.keys(state.regions).length, focusDue: f.due, focusRegion: f.region || null,
    focusIndex: state.focusIndex, focusLastScanAt: state.focusLastScanAt || null }));
  await release();
  process.exit(0);
}

await log('service_start', { pid: process.pid, batch: BATCH, regions: OTHER_REGIONS.length,
  focusRegions: FOCUS_REGIONS.length, focusRescanSec: FOCUS_RESCAN / 1000, focusIndex: state.focusIndex,
  regionIndex: state.regionIndex, chunk: CHUNK });
try {
  for (;;) {
    try { await fs.access(STOP); await log('exit', { reason: 'stop_file' }); break; } catch {}
    try {

    // 1) 目录巡检（未巡完的地区，每轮 3 个；巡完后仅按 EMPTY_RESCAN 周期重扫）
    let discovered = false;
    if (state.regionIndex < OTHER_REGIONS.length) {
      const chunk = OTHER_REGIONS.slice(state.regionIndex, state.regionIndex + CHUNK);
      const r = await step('discover', DRIVER + '/p0-discover-regions.mjs', [],
        { REGIONS: chunk.join(','), DISCOVERY_OUT: CAT, MAX_PAGES_PER_REGION: '8' }, 15 * 60e3);
      if (r.code === 0 && !r.summary?.error) {
        state.regionIndex += chunk.length; discovered = true; state.discoveryFailures = 0;
        const at = new Date().toISOString();
        for (const region of chunk) applyRegionScan(state, region, at, r.summary?.regions?.[region] || null);
      } else if (r.code !== 0 || r.summary?.error) {
        state.discoveryFailures = (state.discoveryFailures || 0) + 1;
        await log('discovery_failed', { failures: state.discoveryFailures, code: r.code, error: String(r.summary?.error || '').slice(0, 120) });
        if (state.discoveryFailures >= 3) { state.discoveryFailures = 0; await backoff('discovery_repeated_failure'); continue; }
      }
      if (r.summary?.risk?.captcha || r.summary?.risk?.unauthorized || r.summary?.risk?.rateLimited) {
        await stopNow('discovery_risk', r.summary.risk); break;
      }
      state.lastDiscoveryAt = new Date().toISOString();
    } else {
      const last = Date.parse(state.lastEmptyRescanAt || 0);
      if (Date.now() - last >= EMPTY_RESCAN) {
        const start = state.rescanIndex || 0;
        const chunk = OTHER_REGIONS.slice(start, start + CHUNK);
        const r = await step('rescan', DRIVER + '/p0-discover-regions.mjs', [],
          { REGIONS: chunk.join(','), DISCOVERY_OUT: CAT, MAX_PAGES_PER_REGION: '8' }, 15 * 60e3);
        if (r.code === 0 && !r.summary?.error) {
          const at = new Date().toISOString();
          for (const region of chunk) applyRegionScan(state, region, at, r.summary?.regions?.[region] || null);
        }
        state.rescanIndex = (start + CHUNK) % OTHER_REGIONS.length;
        state.lastEmptyRescanAt = new Date().toISOString();
      }
    }

    // 1b) 重点区低占空比重扫：每 SERVICE_FOCUS_RESCAN 只扫 1 个地区（失败不推进游标）。
    const focus = chooseFocusScan(state, FOCUS_REGIONS, Date.now(), FOCUS_RESCAN);
    let focusScan = null;
    if (focus.due) {
      const r = await step('focus-rescan', DRIVER + '/p0-discover-regions.mjs', [],
        { REGIONS: focus.region, DISCOVERY_OUT: CAT, MAX_PAGES_PER_REGION: String(FOCUS_PAGES) }, 15 * 60e3);
      const rec = r.summary?.regions?.[focus.region] || null;
      if (r.code === 0 && !r.summary?.error) {
        applyFocusSuccess(state, FOCUS_REGIONS, focus.region, new Date().toISOString(), rec);
        focusScan = { region: focus.region, total: rec?.total ?? null, entries: rec?.entries ?? null,
          coverage: rec?.coverage ?? null, next: FOCUS_REGIONS[state.focusIndex] };
        discovered = true;
      } else {
        state.focusFailures = (state.focusFailures || 0) + 1;
        state.focusLastAttemptAt = new Date().toISOString();
        await log('focus_failed', { region: focus.region, failures: state.focusFailures, code: r.code,
          error: String(r.summary?.error || '').slice(0, 120) });
        if (state.focusFailures >= 3) { state.focusFailures = 0; state.focusLastAttemptAt = new Date().toISOString(); await backoff('focus_repeated_failure'); continue; }
      }
      if (r.summary?.risk?.captcha || r.summary?.risk?.unauthorized || r.summary?.risk?.rateLimited) {
        await stopNow('focus_risk', { region: focus.region, ...r.summary.risk }); break;
      }
    }

    // 2) 建队列（严格去重）
    await step('candidates', DRIVER + '/build-candidates-live.mjs', [], { DISCOVERY_OUT: CAT, CANDIDATES_OUT: CAND }, 2 * 60e3);
    const cand = await readJson(CAND, { candidates: [] });

    // 3) 采集（有界）
    let newPapers = 0;
    if ((cand.candidates || []).length) {
      const end = new Date(Date.now() + 20 * 60e3).toISOString();
      const r = await step('capture', DRIVER + '/t2-phaseb2.mjs', [], { CANDIDATES_FILE: CAND, PHASEB2_MAX: String(BATCH), PHASEB2_END: end }, 30 * 60e3);
      newPapers += r.newPapers;
      if (r.summary?.stop === 'consecutive_failures' || (r.summary?.ok === 0 && r.summary?.fail >= 3)) { await backoff('capture_consecutive_failures'); continue; }
      try { await fs.access(STOP); await log('exit', { reason: 'stop_file_after_capture' }); break; } catch {}
    }

    // 4) 提交（有界、只对确认空白）
    const sub = await step('collect', DRIVER + '/t2-collector.mjs', [], { T2_LIMIT: String(BATCH), T2_MAX_MS: String(40 * 60e3) }, 45 * 60e3);
    if (riskHit(sub.summary)) { await stopNow('submit_risk', sub.summary.risk); break; }
    if (sub.summary?.metrics?.stopReason === 'consecutive_failures') { await backoff('submit_consecutive_failures'); continue; }
    try { await fs.access(STOP); await log('exit', { reason: 'stop_file_after_submit' }); break; } catch {}

    // 5) 回填 + 资产
    await step('backfill', DRIVER + '/t2-backfill-json.mjs', [], {}, 10 * 60e3);
    const assets = await step('assets', DRIVER + '/t2-asset-pass.mjs', [], {}, 25 * 60e3);

    state.rounds += 1;
    state.newPapers += newPapers;
    state.lastRoundAt = new Date().toISOString();
    await writeJson(STATE, state);
    await log('round', { round: state.rounds, discovered, candidates: (cand.candidates || []).length,
      newPapers, submitted: sub.summary?.metrics?.papers ?? null, assets: assets.summary?.downloaded ?? null,
      regionIndex: state.regionIndex, focusScan, focusIndex: state.focusIndex,
      focusLastScanAt: state.focusLastScanAt || null });

    if (riskHit(sub.summary) || riskHit(assets.summary)) { await stopNow('asset_or_submit_risk'); break; }
    } catch (e) {
      // 单轮异常不结束服务：记日志、退避后继续下一轮。
      await log('round_error', { error: (e.code || e.name) + ' :: ' + String(e.message || e).slice(0, 200) });
      await backoff('round_error');
      continue;
    }
    await sleep(INTERVAL);
  }
} catch (e) {
  await log('fatal', { error: (e.code || e.name) + ' :: ' + String(e.message || e).slice(0, 200) });
} finally {
  await writeJson(STATE, state);
  await release();
  await log('service_exit', { pid: process.pid, rounds: state.rounds });
}
