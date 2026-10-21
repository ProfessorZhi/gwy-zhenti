// 从只读目录巡检结果构建可复现的下一批任务；严格去重、只留 2016–2026、只留确认免费行。
// 不联网、不打印题文；输出仅计数与队列文件（本地 0600）。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { yearAllowed } from './year-policy.mjs';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const CAT = process.env.DISCOVERY_OUT || WORK + '/catalog-live-20261019';
const RUN = WORK + '/t2-20261019';
const OUT = process.env.CANDIDATES_OUT || WORK + '/candidates-live.json';

const readJson = async (p, d = null) => { try { return JSON.parse(await fs.readFile(p, 'utf8')); } catch { return d; } };
const AREA = { 深圳市考: '深圳', 广州市考: '广州' };

const files = (await fs.readdir(CAT).catch(() => [])).filter(f => /^catalog-.*\.json$/.test(f));
const scans = [];
for (const f of files) {
  const j = await readJson(path.join(CAT, f));
  if (j) scans.push({ f, j });
}
// 同一 sourceId 以最新一次目录观察为准（重扫可修正会员/行绑定标记），跨地区仍统一去重。
scans.sort((a, b) => (Date.parse(a.j.at || 0) - Date.parse(b.j.at || 0)) || a.f.localeCompare(b.f));
const byId = new Map();
const regionStats = new Map();
for (const { j } of scans) {
  for (const [region, rec] of Object.entries(j.regions || {})) {
    const s = regionStats.get(region) || { memberRows: 0, entries: 0 };
    s.memberRows = Math.max(s.memberRows, rec.memberRows || 0);
    s.entries += (rec.entries || []).length;
    s.lastTotal = rec.total ?? s.lastTotal ?? null;
    s.lastRows = rec.rows ?? s.lastRows ?? null;
    s.lastCoverage = rec.coverage ?? s.lastCoverage ?? null;
    regionStats.set(region, s);
  }
  for (const e of j.entries || []) {
    if (!e || e.id == null) continue;
    byId.set(String(e.id), e);
  }
}

// 已缓存判定以 run-summary 的真实 sourceId 为准（目录名尾部数字可能与别卷 sourceId 相同）。
const papers = new Set();
for (const dir of await fs.readdir(WORK + '/papers').catch(() => [])) {
  const rs = await readJson(path.join(WORK, 'papers', dir, 'run-summary.json'));
  const sid = rs?.sourceId ?? (dir.match(/(\d+)$/) || [])[1];
  if (sid) papers.add(String(sid));
}
const ledger = await readJson(RUN + '/ledger.json', { papers: {} });
const t2sids = new Set(Object.values(ledger.papers || {}).map(x => String(x.sourceId || '')).filter(Boolean));
const b2 = await readJson(RUN + '/phaseb2-ledger.json', { targets: {} });
// 只有成功采集过的 target 才算缓存；failed 必须重新入队，否则失败来源永久消失。
const b2sids = new Set(Object.entries(b2.targets || {}).filter(([, v]) => v && v.status === 'ok').map(([id]) => id));
// 身份有争议（同 sourceId 跨地区重复出现）的来源不自动入队，避免按猜测地区落盘。
const quarantine = await readJson(RUN + '/identity-quarantine.json', {});
const quarantined = new Set(Object.keys(quarantine).filter(k => k !== 'schemaVersion' && k !== 'at'));

const excluded = { cached: 0, outOfYear: 0, member: 0, unverified: 0, duplicate: 0, quarantined: 0 };
const candidates = [];
const seen = new Set();
for (const e of byId.values()) {
  const id = String(e.id);
  if (seen.has(id)) { excluded.duplicate++; continue; }
  seen.add(id);
  if (quarantined.has(id)) { excluded.quarantined++; continue; }
  const year = Number(e.year);
  const area = AREA[e.region] || e.region;
  if (!yearAllowed(area, year)) { excluded.outOfYear++; continue; }
  if (papers.has(id) || t2sids.has(id) || b2sids.has(id)) { excluded.cached++; continue; }
  if (e.member === true || e.locked === true) { excluded.member++; continue; }
  const rs = regionStats.get(e.region) || { memberRows: 0 };
  if (e.rowMatched === false && rs.memberRows > 0) { excluded.unverified++; continue; }
  candidates.push({ id, title: e.title, year, area, region: e.region, source: 'catalog-live' });
}

// 排序：年份新→旧，同年前提重点区（理论上已耗尽），再按地区
const FOCUS = new Set(['国考', '浙江', '江苏', '上海', '北京', '天津', '广东', '广州', '深圳', '福建']);
candidates.sort((a, b) => (b.year - a.year) || (Number(FOCUS.has(b.area)) - Number(FOCUS.has(a.area))) || a.area.localeCompare(b.area) || a.id.localeCompare(b.id));

// 同卷不同来源检查：仅统计同 area/year/title 对应多个不同 sourceId 的组数；不据此丢弃，
// 因为同名可能是真实的不同卷型；输出到本地队列文件供核验。
const titleGroups = new Map();
for (const c of candidates) {
  const k = `${c.area}|${c.year}|${String(c.title || '').replace(/\s+/g, ' ').trim()}`;
  const g = titleGroups.get(k) || new Set();
  g.add(c.id); titleGroups.set(k, g);
}
const sameTitleGroups = [...titleGroups.values()].filter(g => g.size > 1).length;

await fs.mkdir(path.dirname(OUT), { recursive: true, mode: 0o700 });
const tmp = OUT + '.tmp';
await fs.writeFile(tmp, JSON.stringify({ at: new Date().toISOString(), schemaVersion: 1, sources: files,
  candidates, excluded, sameTitleGroups, regions: Object.fromEntries([...regionStats].map(([k, v]) => [k, v])) }, null, 2) + '\n', { mode: 0o600 });
await fs.rename(tmp, OUT);
console.log(JSON.stringify({ ok: true, catalogFiles: files.length, entries: byId.size, candidates: candidates.length, sameTitleGroups, excluded }));
