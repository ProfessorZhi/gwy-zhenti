#!/usr/bin/env node
// 单卷流水线主进程：一个浏览器、WORKER_TABS 个标签页，每个标签页一卷一卷地把试卷从目录走到落盘；
// 每卷落盘后立即转换并发布进集成工作树；每 COMMIT_EVERY 卷或 COMMIT_MS 提交一次，过完整闸门后推送（可自动合入 main）。
// 本进程一次跑到 WORKER_MAX_PAPERS 卷或 WORKER_MAX_MS 为止，最后一行输出 JSON 回执，由 fenbi-service 过风控。
// 任何风控信号（验证码、登录失效、403/429）都让所有标签页停下、本次运行结束；STOP 文件随时生效。
//
// 环境变量：
//   FENBI_WORK_DIR      运行目录（登录 Profile、缓存、台账）
//   CANDIDATES_FILE     目录候选（默认 $FENBI_WORK_DIR/candidates-live.json）
//   WORKER_TABS=3  WORKER_DWELL_MS=15000  WORKER_MAX_PAPERS=60  WORKER_MAX_MS=3000000  WORKER_NAV_GAP_MS=2500
//   INTEG_REPO          集成工作树（非 main 分支）；不设则只抓不发布
//   RIGHTS_FILE         授权文件（发布必需）
//   COMMIT_EVERY=10  COMMIT_MS=600000  PUSH=1  AUTO_MERGE=1
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';
import { buildQueue, takeNext } from './queue.mjs';
import { createGate, createMutex, installRoutes, watchRisk, runPaper } from './flow.mjs';
import { landPaper, landMany, publish } from './publish.mjs';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const PAPERS = WORK + '/papers';
const RUN = WORK + '/t2-20261019';
const T2_LEDGER = RUN + '/ledger.json';
const CAPTURE_LEDGER = RUN + '/phaseb2-ledger.json';
const STOP = WORK + '/STOP';
const LOG = WORK + '/worker.log';
const MERGE_ALERT = WORK + '/ALERT-merge-gate';
const CAND = process.env.CANDIDATES_FILE || WORK + '/candidates-live.json';

const TABS = Number(process.env.WORKER_TABS || 3);
const DWELL_MS = Number(process.env.WORKER_DWELL_MS || 15000);
const MAX_PAPERS = Number(process.env.WORKER_MAX_PAPERS || 60);
const MAX_MS = Number(process.env.WORKER_MAX_MS || 50 * 60e3);
const NAV_GAP_MS = Math.max(2500, Number(process.env.WORKER_NAV_GAP_MS || 2500));
const INTEG = process.env.INTEG_REPO ? path.resolve(process.env.INTEG_REPO) : null;
const RIGHTS = process.env.RIGHTS_FILE || null;
const COMMIT_EVERY = Number(process.env.COMMIT_EVERY || 10);
const COMMIT_MS = Number(process.env.COMMIT_MS || 10 * 60e3);
const PUSH = process.env.PUSH === '1';
const AUTO_MERGE = process.env.AUTO_MERGE === '1';

const readJson = async (p, d = null) => { try { return JSON.parse(await fs.readFile(p, 'utf8')); } catch { return d; } };
const writeJson = async (p, obj) => { const tmp = p + '.' + process.pid + '.tmp'; await fs.writeFile(tmp, JSON.stringify(obj, null, 2) + '\n', { mode: 0o600 }); await fs.rename(tmp, p); };
const log = async (event, extra = {}) => {
  const line = JSON.stringify({ at: new Date().toISOString(), event, ...extra });
  await fs.appendFile(LOG, line + '\n', { mode: 0o600 }).catch(() => {});
  console.log(line);
};
const exists = p => fs.access(p).then(() => true, () => false);
const final = summary => { console.log(JSON.stringify(summary)); };

await fs.mkdir(RUN, { recursive: true, mode: 0o700 });
if (await exists(STOP)) { final({ ok: 0, fail: 0, remaining: 0, stopReason: 'stop_file' }); process.exit(0); }
if (INTEG && !RIGHTS) { final({ ok: 0, fail: 0, remaining: 0, stopReason: 'rights_file_required', error: 'RIGHTS_FILE' }); process.exit(1); }

// ---------- 队列 ----------
const t2Ledger = (await readJson(T2_LEDGER)) || { schemaVersion: 1, papers: {} };
const captureLedger = (await readJson(CAPTURE_LEDGER)) || { schemaVersion: 1, targets: {} };
const cached = [];
for (const key of (await fs.readdir(PAPERS).catch(() => [])).sort()) {
  const run = await readJson(path.join(PAPERS, key, 'run-summary.json'));
  const sid = String(run?.sourceId || (key.match(/(\d+)$/) || [])[1] || '');
  if (!sid) continue;
  const hasDoc = await exists(path.join(PAPERS, key, 'document.json'));
  cached.push({ key, sourceId: sid, pageUrl: hasDoc ? run?.pageUrl || null : null });
}
const quarantine = (await readJson(RUN + '/identity-quarantine.json')) || {};
const queue = buildQueue({ cached, candidates: (await readJson(CAND, { candidates: [] })).candidates || [], t2Ledger, captureLedger,
  quarantined: new Set(Object.keys(quarantine).filter(k => k !== 'schemaVersion' && k !== 'at')) });
queue.length = Math.min(queue.length, MAX_PAPERS);
// 先补落地已交卷、但上次没能发布的卷（例如图片在风控退避后才补齐），队列为空时也做。
if (INTEG) {
  const submitted = cached.map(c => c.key).filter(k => ['complete', 'submitted_partial'].includes(t2Ledger.papers[k]?.status));
  try {
    const r = await landMany({ papersDir: PAPERS, names: submitted, repo: INTEG, rightsFile: RIGHTS });
    await log('catchup_land', { papers: submitted.length, A: r.A, C: r.C, errors: r.errors, promoted: r.promote?.promoted ?? 0 });
    if (r.promote?.promoted) {
      const p = await publish({ repo: INTEG, rightsFile: RIGHTS, push: PUSH, autoMerge: AUTO_MERGE,
        message: `integrate(fenbi): worker catch-up ${new Date().toISOString().slice(0, 16)}Z` });
      await log('publish', { committed: p.committed, pushedBranch: p.pushedBranch, pushedMain: p.pushedMain, error: p.error || null,
        gate: p.gate ? { ok: p.gate.ok, papers: p.gate.papers, reasons: p.gate.reasons.slice(0, 5) } : null });
    }
  } catch (e) { await log('catchup_error', { error: String(e.stderr || e.message).slice(0, 200) }); }
}
if (!queue.length) { final({ ok: 0, fail: 0, remaining: 0, stopReason: 'empty_queue', risk: { captcha: 0, loginLost: 0, http403: 0, http429: 0 } }); process.exit(0); }

// 两本台账串行写，避免多个标签页同时改文件。
const ledgerLock = createMutex();
const ledger = {
  markSubmit: (item, status, extra = {}) => ledgerLock(async () => {
    t2Ledger.papers[item.key] = { status, sourceId: item.sourceId, at: new Date().toISOString(), by: 'worker', ...extra };
    await writeJson(T2_LEDGER, t2Ledger);
  }),
  markCapture: (item, status, extra = {}) => ledgerLock(async () => {
    captureLedger.targets[item.sourceId] = { status, key: item.key, area: item.area, year: item.year, at: new Date().toISOString(), by: 'worker', ...extra };
    await writeJson(CAPTURE_LEDGER, captureLedger);
  }),
};

// ---------- 浏览器 ----------
const { loadConfig } = await import(B + '/tools/fenbi/src/config.mjs');
const base = await loadConfig(path.join(WORK, 'config.json'));
const profileDir = path.join(WORK, 'profiles', base.profileName);
if (!profileDir.startsWith(WORK + path.sep)) { final({ ok: 0, fail: 0, remaining: queue.length, stopReason: 'wrong_profile_dir' }); process.exit(1); }
const lockPath = path.join(profileDir, '.fenbi-framework.lock');
const owner = `${process.pid}:${randomUUID()}`;
try { const fh = await fs.open(lockPath, 'wx'); await fh.writeFile(owner, 'utf8'); await fh.close(); }
catch { final({ ok: 0, fail: 0, remaining: queue.length, stopReason: 'profile_locked' }); process.exit(0); }

const { chromium } = await import(B + '/tools/fenbi/node_modules/playwright-core/index.mjs');
const risk = { captcha: 0, loginLost: 0, http403: 0, http429: 0 };
const policy = { initBudget: 0, initCalls: 0, blockedWrites: 0 };
const started = Date.now(), total = queue.length;
const results = [];
let stopReason = null, consecutiveFailures = 0;
const stop = r => { if (!stopReason) stopReason = r; };
const pub = { landed: 0, sinceCommit: 0, lastCommitAt: Date.now(), commits: 0, mainPushes: 0, lastGate: null, blocked: {} };
const publishLock = createMutex();

async function land(item) {
  if (!INTEG) return;
  try {
    const { row, promote } = await landPaper({ papersDir: PAPERS, name: item.key, repo: INTEG, rightsFile: RIGHTS });
    if (row.grade === 'A') { pub.landed++; pub.sinceCommit++; }
    for (const [reason, paths] of Object.entries(promote?.blocked || {})) pub.blocked[reason] = (pub.blocked[reason] || 0) + paths.length;
    await log('land', { sid: item.sourceId, grade: row.grade, issues: (row.issues || []).slice(0, 5), promoted: promote?.promoted ?? 0, blocked: promote ? Object.keys(promote.blocked) : [] });
  } catch (e) { await log('land_error', { sid: item.sourceId, error: String(e.code || e.message).slice(0, 160) }); }
}

async function flush(force = false) {
  if (!INTEG || (!force && pub.sinceCommit < COMMIT_EVERY && Date.now() - pub.lastCommitAt < COMMIT_MS)) return;
  pub.sinceCommit = 0; pub.lastCommitAt = Date.now();
  try {
    const r = await publish({ repo: INTEG, rightsFile: RIGHTS, push: PUSH, autoMerge: AUTO_MERGE,
      message: `integrate(fenbi): worker batch ${new Date().toISOString().slice(0, 16)}Z` });
    if (r.committed) pub.commits++;
    if (r.pushedMain) pub.mainPushes++;
    pub.lastGate = r.gate ? { ok: r.gate.ok, papers: r.gate.papers, reasons: r.gate.reasons.slice(0, 5) } : null;
    await log('publish', { committed: r.committed, pushedBranch: r.pushedBranch, pushedMain: r.pushedMain, error: r.error || null, gate: pub.lastGate });
    // 闸门没过：集成分支照常推送，main 不动；写 ALERT-merge-gate 提醒人看原因，下一次通过时自动清掉。
    if (r.gate && !r.gate.ok && r.gate.changedFiles) await fs.writeFile(MERGE_ALERT, JSON.stringify({ at: new Date().toISOString(), gate: pub.lastGate }) + '\n', { mode: 0o600 });
    else if (r.gate?.ok) await fs.unlink(MERGE_ALERT).catch(() => {});
  } catch (e) { await log('publish_error', { error: String(e.stderr || e.message).slice(0, 200) }); }
}

let ctx = null;
const closeAll = async () => {
  try { if (ctx) await ctx.close(); } catch {}
  try { if ((await fs.readFile(lockPath, 'utf8')) === owner) await fs.unlink(lockPath); } catch {}
};
process.on('SIGTERM', () => stop('sigterm'));
process.on('SIGINT', () => stop('sigint'));

try {
  ctx = await chromium.launchPersistentContext(profileDir, { headless: false, executablePath: base.executablePath,
    serviceWorkers: 'block', acceptDownloads: false, viewport: { width: 1440, height: 1000 } });
  ctx.setDefaultTimeout(45000);
  await installRoutes(ctx, policy);
  watchRisk(ctx, risk);
  const env = { ctx, gate: createGate(NAV_GAP_MS), openLock: createMutex(), policy, risk, dwellMs: DWELL_MS, papersDir: PAPERS, ledger };
  await log('worker_start', { queued: total, tabs: TABS, dwellMs: DWELL_MS, integ: Boolean(INTEG), push: PUSH, autoMerge: AUTO_MERGE });

  const tab = async slot => {
    for (;;) {
      if (stopReason) return;
      if (await exists(STOP)) { stop('stop_file'); return; }
      if (Date.now() - started >= MAX_MS) { stop('deadline'); return; }
      const item = takeNext(queue, slot.region);
      if (!item) return;
      const rec = await runPaper(slot, item, env);
      results.push(rec);
      await log('paper', { sid: rec.sid, kind: rec.kind, status: rec.status, q: rec.questions ?? null, expected: rec.expected ?? null,
        ans: rec.answers, img: rec.assets, init: rec.initCalls ?? null, pages: rec.catalogPages ?? null, retry: rec.renderRetry || null,
        ms: rec.elapsedMs, err: rec.error || null });
      if (risk.captcha || risk.loginLost || risk.http403 || risk.http429) { stop('risk'); return; }
      if (rec.status === 'complete' || rec.status === 'submitted_partial' || rec.status === 'not_blank') consecutiveFailures = 0;
      else if (++consecutiveFailures >= 3) { stop('consecutive_failures'); return; }
      // 落地和推送排在独立的串行链上，不占用这个标签页。
      if (rec.status === 'complete' || rec.status === 'submitted_partial') publishLock(async () => { await land(item); await flush(); });
    }
  };
  const slots = [];
  for (let i = 0; i < Math.min(TABS, total); i++) slots.push({ page: await ctx.newPage(), region: null });
  await Promise.all(slots.map((slot, i) => sleep(i * NAV_GAP_MS).then(() => tab(slot))));
} catch (e) {
  stop('fatal');
  await log('fatal', { error: (e.code || e.name) + ' :: ' + String(e.message || e).slice(0, 200) });
  process.exitCode = 1;
} finally {
  await closeAll();
  await publishLock(() => flush(true));
}

const ok = results.filter(r => r.status === 'complete' || r.status === 'submitted_partial').length;
const notBlank = results.filter(r => r.status === 'not_blank').length;
const wallMs = Date.now() - started;
final({ ok, fail: results.length - ok - notBlank, remaining: total - results.length, stopReason: stopReason || 'done', risk,
  metrics: { papers: results.length, complete: results.filter(r => r.status === 'complete').length,
    notBlank, wallMs,
    papersPerHour: results.length ? Number((ok / (wallMs / 3600e3)).toFixed(1)) : 0,
    initCalls: policy.initCalls, blockedWrites: policy.blockedWrites,
    landed: pub.landed, commits: pub.commits, mainPushes: pub.mainPushes, gate: pub.lastGate, promoteBlocked: pub.blocked } });
