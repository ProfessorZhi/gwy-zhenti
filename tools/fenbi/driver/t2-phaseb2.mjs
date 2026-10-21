// T2 Phase B2：重点区下一批（2016–2026、未缓存、免费目录行）。
// 逐个调用 capture-new-generic（每卷最多 1 次 init），串行、有界、可续跑。
// 只写本地缓存与台账；不打印题文/URL。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { setTimeout as sleep } from 'node:timers/promises';
import { yearAllowed } from './year-policy.mjs';

const pexec = promisify(execFile);
const B = process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const WORK = B + '/work/fenbi';
const RUN = WORK + '/t2-20261019';
const CAP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'capture-new-generic.mjs');
const STOP = WORK + '/STOP';
const LEDGER = RUN + '/phaseb2-ledger.json';
const CAND = process.env.CANDIDATES_FILE || WORK + '/p0-discover-20261019/candidates.json';

const END = Date.parse(process.env.PHASEB2_END || new Date(Date.now() + 90 * 60000).toISOString());
const MAX = Number(process.env.PHASEB2_MAX || 40);

const META = {
  国考: { label: '国考', area: '国考', paperDir: '国考', pre: 'gk' },
  浙江: { label: '浙江', area: '浙江', paperDir: '省考/浙江', pre: 'zj' },
  江苏: { label: '江苏', area: '江苏', paperDir: '省考/江苏', pre: 'js' },
  上海: { label: '上海', area: '上海', paperDir: '省考/上海', pre: 'sh' },
  北京: { label: '北京', area: '北京', paperDir: '省考/北京', pre: 'bj' },
  天津: { label: '天津', area: '天津', paperDir: '省考/天津', pre: 'tj' },
  广东: { label: '广东', area: '广东', paperDir: '省考/广东', pre: 'gd' },
  广州: { label: '广州', area: '广州', paperDir: '省考/广州', pre: 'gz' },
  深圳: { label: '深圳', area: '深圳', paperDir: '省考/深圳', pre: 'sz' },
  福建: { label: '福建', area: '福建', paperDir: '省考/福建', pre: 'fj' },
};
const PRE = { 国考: 'gk', 北京: 'bj', 天津: 'tj', 上海: 'sh', 重庆: 'cq', 河北: 'he', 山西: 'sx',
  内蒙古: 'nm', 辽宁: 'ln', 吉林: 'jl', 黑龙江: 'hl', 江苏: 'js', 浙江: 'zj', 安徽: 'ah', 福建: 'fj',
  江西: 'jx', 山东: 'sd', 河南: 'ha', 湖北: 'hb', 湖南: 'hn', 广东: 'gd', 广西: 'gx', 海南: 'hi',
  四川: 'sc', 贵州: 'gz', 云南: 'yn', 西藏: 'xz', 陕西: 'sn', 甘肃: 'gs', 青海: 'qh', 宁夏: 'nx',
  新疆: 'xj', 深圳: 'sz', 广州: 'gz' };
const metaOf = (area, region) => META[area] || {
  label: region || area, area, paperDir: `省考/${area}`, pre: PRE[area] || 'xx' };
const variantOf = t => {
  if (/副省级/.test(t)) return 'fushengji';
  if (/地市级/.test(t)) return 'dishiji';
  if (/行政执法/.test(t)) return 'xingzheng';
  if (/A类|A卷/.test(t)) return 'a';
  if (/B类|B卷/.test(t)) return 'b';
  if (/C类|C卷/.test(t)) return 'c';
  if (/县级/.test(t)) return 'county';
  if (/乡镇/.test(t)) return 'township';
  const m = t.match(/行测([12])/); if (m) return 'hangce' + m[1];
  return 'tongkao';
};

const led = await (async () => { try { return JSON.parse(await fs.readFile(LEDGER, 'utf8')); } catch { return { schemaVersion: 1, targets: {} }; } })();
const existing = new Set(await fs.readdir(WORK + '/papers'));
const existingSids = new Set([...existing].map(k => (k.match(/(\d+)$/) || [])[1]).filter(Boolean));
const t2led = JSON.parse(await fs.readFile(RUN + '/ledger.json', 'utf8'));
const doneSids = new Set(Object.values(t2led.papers || {}).map(x => String(x.sourceId || '')).filter(Boolean));

const disc = JSON.parse(await fs.readFile(CAND, 'utf8'));
const quarantine = await (async () => { try { return JSON.parse(await fs.readFile(RUN + '/identity-quarantine.json', 'utf8')); } catch { return {}; } })();
const quarantined = new Set(Object.keys(quarantine).filter(k => k !== 'schemaVersion' && k !== 'at'));
const targets = [];
const seenTargets = new Set();
for (const p of (disc.candidates || [])) {
  const meta = metaOf(p.area, p.region);
  if (!yearAllowed(meta.area, p.year)) continue;
  const sid = String(p.id);
  if (quarantined.has(sid)) continue;
  if (seenTargets.has(sid)) continue;
  if (existingSids.has(sid) || doneSids.has(sid)) continue;
  if (led.targets[sid] && led.targets[sid].status === 'ok') continue;
  const variant = variantOf(p.title);
  const key = `${meta.pre}-${p.year}-xingce-${variant}-${sid}`;
  if (existing.has(key)) continue;
  seenTargets.add(sid);
  targets.push({ key, sourceId: sid, label: meta.label, area: meta.area,
    titleRe: p.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
    titleFrag: [String(p.year)],
    identity: { id: sid, title: p.title, subject: 'xingce', year: p.year, area: meta.area, variant },
    paper: `${meta.paperDir}/${p.year}/行测-${variant}.md`, year: p.year });
}
targets.sort((a, b) => (a.year === b.year ? a.area.localeCompare(b.area) : a.year - b.year));
const queue = targets.slice(0, MAX);
console.log(JSON.stringify({ queued: queue.length, candidates: targets.length }));
if (process.env.PHASEB2_DRY_RUN === '1') {
  const by = {};
  for (const t of queue) { const k = `${t.area}/${t.year}/${t.identity.variant}`; by[k] = (by[k] || 0) + 1; }
  console.log(JSON.stringify({ dryRun: true, queued: queue.length, candidates: targets.length, by }));
  process.exit(0);
}

let ok = 0, fail = 0, consec = 0;
// 子进程失败分类：只在本机 0600 回执写脱敏后的类别/首行，不打印题文、URL、cookie、token。
const ERRLOG = RUN + '/capture-errors.json';
const sanitizeErr = s => String(s || '')
  .replace(/https?:\/\/[^\s"'<>)]+/g, '<url>')
  .replace(/(cookie|token|authorization|password|sessionid)(["']?\s*[:=]\s*["']?)[^\s,"';}]+/gi, '$1$2<redacted>')
  .slice(0, 400);
const classifyChildError = (e) => {
  const err = String(e.stderr || '');
  if (/ERR_MODULE_NOT_FOUND/.test(err)) {
    const m = err.match(/Cannot find module '([^']+)'/);
    return { cls: 'module_not_found', detail: m ? m[1].replace(B, '<base>') : null };
  }
  if (/ERR_UNSUPPORTED_DIR_IMPORT|ERR_INVALID_MODULE_SPECIFIER|ERR_UNKNOWN_FILE_EXTENSION/.test(err)) return { cls: 'module_resolution', detail: null };
  if (/ECONNREFUSED|ENOTFOUND|EAI_AGAIN|ECONNRESET|net::ERR_|ERR_INTERNET_DISCONNECTED/.test(err)) return { cls: 'network', detail: null };
  if (e.killed || /ETIMEDOUT|timed? ?out/i.test(err)) return { cls: 'timeout', detail: null };
  if (/SyntaxError|TypeError|ReferenceError|RangeError/.test(err)) return { cls: 'code_error', detail: null };
  return { cls: 'child_exit', detail: null };
};
const appendErrReceipt = async (sid, e, c) => {
  let log = {}; try { log = JSON.parse(await fs.readFile(ERRLOG, 'utf8')); } catch {}
  log[sid] = { at: new Date().toISOString(), exitCode: e.code ?? null, class: c.cls, detail: c.detail,
    stderr: sanitizeErr(e.stderr) };
  const keys = Object.keys(log).sort((a, b) => Date.parse(log[b].at) - Date.parse(log[a].at)).slice(0, 200);
  const bounded = Object.fromEntries(keys.map(k => [k, log[k]]));
  const tmp = ERRLOG + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(bounded, null, 2) + '\n', { mode: 0o600 });
  await fs.rename(tmp, ERRLOG);
};
for (const t of queue) {
  try { await fs.access(STOP); console.log(JSON.stringify({ stop: 'stop_file' })); break; } catch {}
  if (Date.now() >= END) { console.log(JSON.stringify({ stop: 'deadline' })); break; }
  let r = null;
  try {
    const { stdout } = await pexec(process.execPath, [CAP, JSON.stringify(t)], { timeout: 10 * 60 * 1000, maxBuffer: 8 * 1024 * 1024,
      env: { ...process.env, DISPLAY: ':77' } });
    const i = stdout.indexOf('{');
    r = i >= 0 ? JSON.parse(stdout.slice(i)) : null;
  } catch (e) {
    const c = classifyChildError(e);
    try { await appendErrReceipt(t.sourceId, e, c); } catch {}
    r = { ok: false, error: `${e.code ?? e.name ?? 'ERR'}:${c.cls}` };
  }
  const status = r?.ok ? 'ok' : 'failed';
  led.targets[t.sourceId] = { status, key: t.key, area: t.area, year: t.year, at: new Date().toISOString(),
    error: r?.ok ? null : String(r?.error || 'CAPTURE_FAILED').slice(0, 120),
    questions: r?.counts?.questions ?? null, catalogPages: r?.catalogPages ?? null, elapsedMs: r?.elapsedMs ?? null };
  await fs.writeFile(LEDGER + '.tmp', JSON.stringify(led, null, 2) + '\n', { mode: 0o600 });
  await fs.rename(LEDGER + '.tmp', LEDGER);
  if (r?.ok) { ok++; consec = 0; } else { fail++; consec++; }
  console.log(`  ${t.sourceId} ${t.area} ${t.year} ${status} q=${r?.counts?.questions ?? '-'} pg=${r?.catalogPages ?? '-'} ${r?.elapsedMs ?? '-'}ms`);
  if (consec >= 3) { console.log(JSON.stringify({ stop: 'consecutive_failures' })); break; }
  await sleep(2500);
}
console.log(JSON.stringify({ ok, fail, remaining: queue.length - ok - fail }));
