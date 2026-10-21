// T2 采集器：既有缓存卷补答案（交白卷 → 解析页 → DOM+JSON → 图片 → 缓存）。
// 1 账号 / 1 持久 Profile / 单 Owner；最多 3 个 Page；导航共用 ≥2.5s 闸门；每卷停留 30s。
// 只放行“交卷”这一个写操作；其它写请求一律拦截。输出仅元数据。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { setTimeout as sleep } from 'node:timers/promises';

const pexec = promisify(execFile);
const B = process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const WORK = B + '/work/fenbi';
const PAPERS = WORK + '/papers';
const RUN = WORK + '/t2-20261019';
const LEDGER = RUN + '/ledger.json';
const STATE = RUN + '/run-state.json';
const STOP = WORK + '/STOP';
const DONE_KEY = 'sz-2025-xingce-tongkao-5232321';

const MAX_TABS = Number(process.env.T2_TABS || 3);
const NAV_GAP_MS = 2500;
const DWELL_MS = 30000;
const MAX_MS = Number(process.env.T2_MAX_MS || 60 * 60 * 1000);

const sha = b => createHash('sha256').update(b).digest('hex');
const strip = s => String(s || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

// ---------- 预检 ----------
const { stdout: psOut } = await pexec('bash', ['-lc', "ps -eo comm,args --no-headers | grep -iE 'chrome|chromium' | grep -v grep | wc -l"]);
if (Number(psOut.trim() || 0) > 0) { console.log(JSON.stringify({ ok: false, code: 'ACTIVE_BROWSER' })); process.exit(0); }
const memGB = (await fs.readFile('/proc/meminfo', 'utf8')).match(/MemAvailable:\s+(\d+) kB/);
if (Number(memGB[1]) / 1048576 < 2) { console.log(JSON.stringify({ ok: false, code: 'MEMORY_LOW' })); process.exit(0); }

await fs.mkdir(RUN, { recursive: true, mode: 0o700 });

const { loadConfig } = await import(B + '/tools/fenbi/src/config.mjs');
const base = await loadConfig(path.join(WORK, 'config.json'));
const config = { ...base, workDir: WORK, profileDir: path.join(WORK, 'profiles', base.profileName) };
if (!config.profileDir.startsWith(WORK + path.sep)) { console.log(JSON.stringify({ ok: false, code: 'WRONG_PROFILE_DIR' })); process.exit(0); }

const lockPath = path.join(config.profileDir, '.fenbi-framework.lock');
const owner = `${process.pid}:${randomUUID()}`;
let lockFh;
try { lockFh = await fs.open(lockPath, 'wx'); await lockFh.writeFile(owner, 'utf8'); await lockFh.close(); }
catch { console.log(JSON.stringify({ ok: false, code: 'PROFILE_LOCKED' })); process.exit(0); }

const { chromium } = await import(B + '/tools/fenbi/node_modules/playwright-core/index.mjs');
const { sanitizeHtml } = await import(B + '/tools/fenbi/src/privacy.mjs');
const { collectAssetUrls } = await import(B + '/tools/fenbi/src/model.mjs');
const { downloadAssets } = await import(B + '/tools/fenbi/src/browser.mjs');
const { validateDocument } = await import(B + '/tools/fenbi/src/validate.mjs');

// ---------- 队列 ----------
const readJson = async (p, d = null) => { try { return JSON.parse(await fs.readFile(p, 'utf8')); } catch { return d; } };
const ledger = (await readJson(LEDGER, null)) || { schemaVersion: 1, papers: {} };
const queue = [];
for (const key of (await fs.readdir(PAPERS)).sort()) {
  if (key === DONE_KEY) continue;
  const run = await readJson(path.join(PAPERS, key, 'run-summary.json'));
  const doc = await readJson(path.join(PAPERS, key, 'document.json'));
  if (!run?.pageUrl || !doc) continue;
  const done = ledger.papers[key];
  if (done && (done.status === 'complete' || done.status === 'submitted_partial' || done.status === 'out_of_scope' || done.status === 'not_blank')) continue;
  const sid = String(run.sourceId || (key.match(/(\d+)$/) || [])[1] || '');
  queue.push({ key, sid, url: run.pageUrl });
}
if (process.env.T2_LIMIT) queue.length = Math.min(queue.length, Number(process.env.T2_LIMIT));
if (!queue.length) {
  try { if ((await fs.readFile(lockPath, 'utf8')) === owner) await fs.unlink(lockPath); } catch {}
  console.log(JSON.stringify({ ok: true, stopReason: 'empty_queue', metrics: { papers: 0, complete: 0, failed: 0 }, risk: { captcha: 0, loginLost: 0, http403: 0, http429: 0, stops: [] } }));
  process.exit(0);
}

const state = { schemaVersion: 1, kind: 't2-run', startedAt: new Date().toISOString(),
  deadlineAt: new Date(Date.now() + MAX_MS).toISOString(), tabs: MAX_TABS, navGapMs: NAV_GAP_MS,
  dwellMs: DWELL_MS, queued: queue.length, done: 0, failed: 0, skipped: 0,
  risk: { captcha: 0, loginLost: 0, http403: 0, http429: 0, stops: [] }, runs: [] };
const persist = async (file, obj) => {
  const tmp = file + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(obj, null, 2) + '\n', { mode: 0o600 });
  await fs.rename(tmp, file);
};
await persist(STATE, state);

let stopReason = null;
const stop = r => { if (!stopReason) stopReason = r; };
const stopRequested = async () => { try { await fs.access(STOP); return true; } catch { return false; } };

// 共享导航闸门
let lastNav = 0, gateChain = Promise.resolve();
const navGate = () => {
  const p = gateChain.then(async () => {
    const w = NAV_GAP_MS - (Date.now() - lastNav);
    if (w > 0) await sleep(w);
    lastNav = Date.now();
  });
  gateChain = p.catch(() => {});
  return p;
};

const rateHits = [];
let consecutiveFailures = 0;

const ctx = await chromium.launchPersistentContext(config.profileDir, {
  headless: false, executablePath: config.executablePath,
  serviceWorkers: 'block', acceptDownloads: false, viewport: { width: 1440, height: 1000 },
});
ctx.setDefaultTimeout(45000);
await ctx.route('**/*', async route => {
  const req = route.request(); const m = req.method().toUpperCase();
  if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') {
    try { const u = new URL(req.url()); if (u.hostname === 'data-api.fenbi.com') return route.abort('blockedbyclient'); } catch {}
    return route.continue();
  }
  let u; try { u = new URL(req.url()); } catch { return route.abort('blockedbyclient'); }
  const isSubmit = m === 'POST' && u.hostname === 'tiku.fenbi.com' && /\/combine\/exercise\/submit$/.test(u.pathname);
  const isUiConfig = m === 'POST' && u.hostname === 'ke.fenbi.com' && /\/tiku_config\/report_display_cards$/.test(u.pathname);
  const isStudyTime = m === 'POST' && u.hostname === 'tiku.fenbi.com' && /\/activity\/report\/studyTime$/.test(u.pathname);
  if (isSubmit || isUiConfig || isStudyTime) return route.continue();
  return route.abort('blockedbyclient');
});

const closeAll = async () => {
  try { await ctx.close(); } catch {}
  try { if ((await fs.readFile(lockPath, 'utf8')) === owner) await fs.unlink(lockPath); } catch {}
  state.finishedAt = new Date().toISOString();
  state.stopReason = stopReason || 'done';
  state.metrics = {
    papers: state.runs.length,
    complete: state.runs.filter(r => r.status === 'complete' || r.status === 'submitted_partial').length,
    answersComplete: state.runs.filter(r => r.answers > 0 && r.answers === r.questions).length,
    failed: state.runs.filter(r => !(r.status === 'complete' || r.status === 'submitted_partial')).length,
    wallMs: Date.now() - Date.parse(state.startedAt),
    avgSecPerPaper: state.runs.length ? Number(((Date.now() - Date.parse(state.startedAt)) / 1000 / state.runs.length).toFixed(1)) : null,
    risk: state.risk,
  };
  await persist(STATE, state);
  await persist(LEDGER, ledger);
  console.log(JSON.stringify({ ok: true, stopReason: state.stopReason, metrics: state.metrics,
    runs: state.runs.map(r => ({ sid: r.sid, status: r.status, ans: r.answers, exp: r.explanations, a: r.assets, ms: r.elapsedMs, err: r.error || null })) }));
  process.exit(0);
};
process.on('SIGTERM', closeAll);
process.on('SIGINT', closeAll);

// ---------- 单卷 ----------
async function processPaper(page, item, idx) {
  const t0 = Date.now();
  const rec = { key: item.key, sid: item.sid, at: new Date().toISOString(), status: 'pending',
    answers: 0, explanations: 0, assets: 0, json: 0, nav: 0, elapsedMs: 0, error: null };
  const payloadDir = path.join(RUN, 'payloads', item.key);
  await fs.mkdir(payloadDir, { recursive: true, mode: 0o700 });
  const seen = new Set();

  const onResp = async r => {
    try {
      const st = r.status();
      if (st === 403) { state.risk.http403++; rateHits.push(Date.now()); }
      if (st === 429) { state.risk.http429++; rateHits.push(Date.now()); }
      let u; try { u = new URL(r.url()); } catch { return; }
      if (/captcha|verifycode|verification/i.test(u.pathname)) { state.risk.captcha++; stop('captcha'); }
      if (u.hostname === 'login.fenbi.com' && /users\/info$/.test(u.pathname) && (st === 401 || st === 403)) { state.risk.loginLost++; stop('login_lost'); }
      if (!/json/i.test(r.headers()['content-type'] || '')) return;
      rec.json++;
      const body = await r.body();
      const k = sha(body).slice(0, 16);
      if (!seen.has(k)) { seen.add(k); await fs.writeFile(path.join(payloadDir, k + '.json'), body, { mode: 0o600 }); }
    } catch {}
  };

  page.on('response', onResp);
  try {
    await navGate();
    rec.nav++;
    await page.goto(item.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    // 等题目页
    const ready = Date.now() + 30000;
    let qn = 0, readyAt = 0;
    while (Date.now() < ready) {
      qn = await page.evaluate(() => document.querySelectorAll('app-ti[data-question-key]').length).catch(() => 0);
      if (qn > 0) { readyAt = Date.now(); break; }
      await sleep(1200);
    }
    if (qn === 0) { rec.status = 'no_question_page'; rec.error = 'NO_QUESTION_PAGE'; return rec; }
    rec.questions = qn;

    // 空白校验
    const blank = await page.evaluate(() => {
      const inputs = [...document.querySelectorAll('app-ti[data-question-key] input')];
      const body = document.body.innerText || '';
      return { checked: inputs.filter(i => i.checked).length, total: inputs.length,
        aria: document.querySelectorAll('app-ti[data-question-key] [aria-checked="true"]').length,
        hint: (body.match(/(已答|已做)\s*[:：]?\s*(\d+)/) || [])[2] };
    });
    if (blank.checked > 0 || blank.aria > 0 || Number(blank.hint) > 0) {
      rec.status = 'not_blank'; rec.error = 'NOT_BLANK'; return rec;
    }
    if (!(await page.evaluate(() => document.querySelectorAll('app-ti[data-question-key]').length > 0))) {
      rec.status = 'not_blank'; rec.error = 'NO_QUESTIONS'; return rec;
    }

    // 实际页面停留 30 秒：从题目页渲染完成起算
    const wait = readyAt + DWELL_MS - Date.now();
    if (wait > 0) await sleep(wait);
    rec.dwellMs = Date.now() - readyAt;

    // 交卷
    let clicked = await page.evaluate(() => {
      const els = [...document.querySelectorAll('.submit-btn')].filter(e => (e.innerText || '').trim() === '交卷' && e.offsetParent !== null);
      if (!els.length) return false;
      els[0].click(); return true;
    }).catch(() => false);
    if (!clicked) { rec.status = 'submit_button_missing'; rec.error = 'SUBMIT_BUTTON_MISSING'; return rec; }
    await sleep(1800);
    for (let i = 0; i < 2; i++) {
      const btn = page.locator('.modal-action-btn.btn-submit').first();
      if (!(await btn.count().catch(() => 0))) break;
      await btn.click({ timeout: 10000 }).catch(() => {});
      await sleep(2500);
    }

    // 解析页
    let ok = false;
    const dl = Date.now() + 45000;
    while (Date.now() < dl) {
      const st = await page.evaluate(() => {
        const b = document.body.innerText || '';
        return /正确答案/.test(b) && /解析/.test(b);
      }).catch(() => false);
      if (st) { ok = true; break; }
      await sleep(1500);
    }
    if (!ok) { rec.status = 'analysis_not_reached'; rec.error = 'ANALYSIS_NOT_REACHED'; return rec; }
    await sleep(3000);

    // 采集 DOM
    const raw = await page.evaluate(() => [...document.querySelectorAll('app-ti[data-question-key]')].map(el => {
      const c = el.cloneNode(true);
      const im = [...el.querySelectorAll('img')], cp = [...c.querySelectorAll('img')];
      im.forEach((i, k) => { const a = i.currentSrc || i.getAttribute('src') || i.getAttribute('data-src'); if (a && cp[k]) cp[k].setAttribute('src', a); });
      return c.outerHTML;
    }).join('\n'));
    const cleaned = sanitizeHtml(raw);
    // 先落解析页快照并登记“已交卷”，即使后续合并崩溃也不会重复交卷
    await fs.writeFile(path.join(PAPERS, item.key, 'analysis-dom.json'),
      JSON.stringify({ sourceId: item.sid, at: new Date().toISOString(), contentHtml: cleaned.html }), { mode: 0o600 });
    ledger.papers[item.key] = { status: 'submitted_partial', sourceId: item.sid, at: new Date().toISOString(), updatedAt: new Date().toISOString() };
    await persist(LEDGER, ledger);

    // 按 data-question-key 合并
    const docPath = path.join(PAPERS, item.key, 'document.json');
    const doc = JSON.parse(await fs.readFile(docPath, 'utf8'));
    const byKey = new Map();
    for (const b of cleaned.html.split(/<app-ti\b/).slice(1)) {
      const key = (b.match(/data-question-key="([^"]+)"/) || [])[1];
      if (!key) continue;
      const ansSpan = b.match(/<span[^>]*class="[^"]*correct-answer[^"]*"[^>]*>([\s\S]*?)<\/span>/);
      const answer = ansSpan ? strip(ansSpan[1]).replace(/[^A-H]/g, '') : '';
      let expl = null;
      for (const sec of [...b.matchAll(/<section[^>]*result-common-section[^>]*>([\s\S]*?)<\/section>/g)].map(m => m[1])) {
        const tm = sec.match(/<app-solution-title[^>]*>([\s\S]*?)<\/app-solution-title>/);
        const title = tm ? strip(tm[1]) : '';
        const body = tm ? sec.slice(tm.index + tm[0].length) : sec;
        if (/解析视频/.test(title)) continue;
        if (/^解析/.test(title)) expl = body;
      }
      byKey.set(key, { answer, expl });
    }
    for (const q of doc.questions) {
      const s = byKey.get(q.id);
      if (!s || !s.answer || !s.expl || strip(s.expl).length < 20) continue;
      const clean = sanitizeHtml(s.expl);
      q.answerHtml = `<p>${s.answer}</p>`;
      q.explanationHtml = clean.html;
      if (clean.rejected) doc.conflicts.push({ scope: 'privacy', id: q.id, field: 'explanationHtml', rejectedReferences: clean.rejected });
      rec.answers++; rec.explanations++;
    }
    doc.evidence = Array.isArray(doc.evidence) ? doc.evidence : [];
    doc.evidence.push({ type: 'answer-explanation-source', source: 'fenbi-analysis-dom', page: 'analysis-after-blank-submit',
      keyedBy: 'data-question-key', observedAt: new Date().toISOString(), answers: rec.answers, explanations: rec.explanations });

    // 图片
    const urls = collectAssetUrls(doc);
    const prev = new Map((doc.assets || []).map(a => [a.url, a]));
    doc.assets = urls.map(u => prev.get(u) || { url: u, status: 'pending' });
    const assets = await downloadAssets(page, doc, path.join(PAPERS, item.key, 'assets'));
    rec.assets = assets.filter(a => a.status === 'downloaded').length;

    const verdict = await validateDocument(doc, { assetRoot: path.join(PAPERS, item.key, 'assets') });
    rec.verdict = verdict.status;
    rec.issues = [...new Set((verdict.issues || []).map(i => i.code))].slice(0, 8);

    const tmp = docPath + '.tmp';
    await fs.writeFile(tmp, JSON.stringify(doc), { mode: 0o600 });
    await fs.rename(tmp, docPath);
    await fs.writeFile(path.join(PAPERS, item.key, 'validation.json'), JSON.stringify(verdict, null, 2) + '\n', { mode: 0o600 });
    rec.status = verdict.status === 'complete' ? 'complete' : 'submitted_partial';
    rec.submitted = true;
  } catch (e) {
    rec.status = 'error';
    rec.error = (e.code || e.name || 'ERR') + ' :: ' + String(e.message || e).slice(0, 120);
  } finally {
    rec.elapsedMs = Date.now() - t0;
    try { page.off('response', onResp); } catch {}
  }
  return rec;
}

// ---------- 调度 ----------
const results = [];
let cursor = 0;
async function worker(page) {
  while (true) {
    if (stopReason) return;
    if (await stopRequested()) { stop('stop_file'); return; }
    if (Date.now() >= Date.parse(state.deadlineAt)) { stop('deadline'); return; }
    // 1 小时 3 次 403/429
    const hourAgo = Date.now() - 3600_000;
    if (rateHits.filter(t => t > hourAgo).length >= 3) { stop('rate_limited_3_per_hour'); return; }
    if (consecutiveFailures >= 3) { stop('consecutive_failures'); return; }
    const i = cursor++;
    if (i >= queue.length) return;
    const item = queue[i];

    const rec = await processPaper(page, item, i);

    if (rec.status === 'complete' || rec.status === 'submitted_partial') {
      consecutiveFailures = 0;
      ledger.papers[item.key] = { status: rec.status, sourceId: item.sid, at: new Date().toISOString(),
        answers: rec.answers, explanations: rec.explanations, assets: rec.assets };
      state.done++;
    } else if (rec.status === 'not_blank') {
      consecutiveFailures = 0;
      ledger.papers[item.key] = { status: 'not_blank', sourceId: item.sid, at: new Date().toISOString() };
      state.skipped++;
    } else {
      consecutiveFailures++;
      ledger.papers[item.key] = { status: 'failed', sourceId: item.sid, at: new Date().toISOString(), error: rec.error };
      state.failed++;
    }
    state.runs.push({ sid: item.sid, key: item.key, status: rec.status, answers: rec.answers,
      explanations: rec.explanations, assets: rec.assets, questions: rec.questions, json: rec.json,
      dwellMs: rec.dwellMs ?? null, elapsedMs: rec.elapsedMs, error: rec.error });
    await persist(STATE, state);
    await persist(LEDGER, ledger);
    console.log(`  ${item.sid} ${rec.status} ans=${rec.answers} exp=${rec.explanations} img=${rec.assets} ${rec.elapsedMs}ms ${rec.error || ''}`);
  }
}

const pages = [];
for (let i = 0; i < Math.min(MAX_TABS, queue.length); i++) pages.push(await ctx.newPage());
await Promise.all(pages.map(p => worker(p)));
await closeAll();
