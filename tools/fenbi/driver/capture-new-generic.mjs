// 首个真实新来源：深圳市考2025 (5232321)。
// 授权范围：为该卷正常创建**一次**免费练习并只读采集；绝不作答/交卷/购买。
// 单一 persistent context、1 page、节流 >=2.5s；init POST 硬上限 1 次。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const COMBO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src');
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const REPO = B;
const ENTRY = 'https://www.fenbi.com/spa/tiku/guide/realTest/xingce/xingce';
const GAP = 2500;
const sha = b => createHash('sha256').update(b).digest('hex');
// Wait for an element instead of a fixed sleep; on timeout fall through exactly as the old fixed wait did.
const settle = (page, selector, timeout) => page.locator(selector).first().waitFor({ state: 'visible', timeout }).catch(() => {});

const T = JSON.parse(process.argv[2] || '{}');
if (!T.key || !T.sourceId || !T.label || !T.titleRe) { console.error('usage: node capture-new-generic.mjs <json>'); process.exit(2); }

const { loadConfig } = await import(COMBO + '/config.mjs');
const { requestPolicy, downloadAssets } = await import(COMBO + '/browser.mjs');
const { sanitizeHtml } = await import(COMBO + '/privacy.mjs');
const { parseFenbiExamDom } = await import(COMBO + '/dom.mjs');
const { createDocument, absorbPayload, collectAssetUrls } = await import(COMBO + '/model.mjs');
const { validateDocument } = await import(COMBO + '/validate.mjs');
const { comparePaper } = await import(COMBO + '/align.mjs');

const base = await loadConfig(path.join(WORK, 'config.json'));
const config = { ...base, workDir: WORK, profileDir: path.join(WORK, 'profiles', base.profileName),
  contentSelector: '.tis-container', domAdapter: 'fenbi-xingce-v1' };
if (!config.profileDir.startsWith(WORK + path.sep)) throw new Error('wrong profileDir');

const outDir = path.join(WORK, 'papers', T.key);
await fs.mkdir(outDir, { recursive: true, mode: 0o700 });
const result = { key: T.key, sourceId: T.sourceId, at: new Date().toISOString(), pages: 1, throttleMs: GAP,
  initCalls: [], navCount: 0, nonGet: [] };

let initBudget = 1;
const { chromium } = await import(B + '/tools/fenbi/node_modules/playwright-core/index.mjs');
await fs.mkdir(config.profileDir, { recursive: true, mode: 0o700 });
const lockPath = path.join(config.profileDir, '.fenbi-framework.lock');
const owner = `${process.pid}:${randomUUID()}`;
let lock;
try { lock = await fs.open(lockPath, 'wx'); await lock.writeFile(owner, 'utf8'); await lock.close(); }
catch { console.error('PROFILE_LOCKED'); process.exit(3); }

let ctx; let last = 0;
const throttle = async () => { const w = GAP - (Date.now() - last); if (w > 0) await sleep(w); last = Date.now(); };
const t0 = Date.now();
try {
  ctx = await chromium.launchPersistentContext(config.profileDir, { headless: false,
    executablePath: config.executablePath, serviceWorkers: 'block', acceptDownloads: false,
    viewport: { width: 1440, height: 1000 } });
  ctx.setDefaultTimeout(config.timeoutMs);
  await ctx.route('**/*', async route => {
    const req = route.request(); let u; try { u = new URL(req.url()); } catch { return route.abort('blockedbyclient'); }
    const m = req.method().toUpperCase();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(m)) {
      result.nonGet.push({ method: m, host: u.hostname, path: u.pathname });
      const isInit = m === 'POST' && u.hostname === 'tiku.fenbi.com' && u.pathname === '/api/xingce/exercises';
      if (isInit && initBudget > 0) { initBudget--; result.initCalls.push({ at: new Date().toISOString(), allowed: true }); return route.continue(); }
      return route.abort('blockedbyclient');
    }
    if (requestPolicy({ url: req.url(), method: m, navigation: req.isNavigationRequest() }, 'capture')) return route.abort('blockedbyclient');
    return route.continue();
  });
  const page = await ctx.newPage();
  const auth = { status: 'unknown' };
  // Same risk counters as t2-collector, so t2-phaseb2 and the service can stop or back off on them.
  result.risk = { captcha: 0, loginLost: 0, http403: 0, http429: 0 };
  ctx.on('response', r => { try {
    const u = new URL(r.url()), st = r.status();
    if (st === 403) result.risk.http403++;
    if (st === 429) result.risk.http429++;
    if (/captcha|verifycode|verification/i.test(u.pathname)) result.risk.captcha++;
    if (u.hostname === 'login.fenbi.com' && u.pathname === '/api/users/info' && r.request().method() === 'GET') {
      auth.status = st === 200 ? 'authenticated' : 'unauthenticated';
      if (st === 401 || st === 403) result.risk.loginLost++;
    }
  } catch {} });

  await throttle(); result.navCount++;
  await page.goto(ENTRY, { waitUntil: 'domcontentloaded', timeout: config.timeoutMs });
  await settle(page, 'span.categories-item', 10000);
  await throttle();
  await page.locator('span.categories-item', { hasText: T.label }).first().click();
  // Wait for this paper's own row, not any paper-item: the list from before the region switch may still be on screen.
  // If the paper is on a later page the wait times out and the pager loop below takes over, as before.
  await page.locator('div.paper-item', { hasText: new RegExp(T.titleRe) }).first()
    .waitFor({ state: 'visible', timeout: 6000 }).catch(() => {});
  await sleep(800);

  // 目录分页：目标卷可能在后续页，仅点击真实分页器 .houpage（与导航同一 2.5s 节流）
  let row = page.locator('div.paper-item', { hasText: new RegExp(T.titleRe) }).first();
  let found = await row.count();
  let catalogPages = 1;
  for (let p = 0; p < 6 && !found; p++) {
    const next = page.locator('footer.question-list-pager .houpage').first();
    if (!await next.count()) break;
    const disabled = await next.evaluate(e => !e.offsetParent || /disabled/i.test((e.className || '').toString())).catch(() => true);
    if (disabled) break;
    await throttle();
    await next.click({ timeout: 10000 }).catch(() => {});
    await sleep(3000);
    catalogPages++;
    row = page.locator('div.paper-item', { hasText: new RegExp(T.titleRe) }).first();
    found = await row.count();
  }
  result.catalogPages = catalogPages;
  if (!found) throw Object.assign(new Error('row not found'), { code: 'ROW_NOT_FOUND' });
  const rowText = (await row.innerText()).replace(/\s+/g, ' ').trim();
  result.uiBefore = rowText;
  result.hadExistingExercise = /未完成|继续练习/.test(rowText);
  if (result.hadExistingExercise) initBudget = 0;

  await throttle();
  const clickedAt = Date.now();
  await row.click();
  result.navCount++;

  // The exercise may open in this tab or a new one; poll every page until questions render (max 20s, was a fixed 13s).
  let qpage = null;
  for (let waited = 0; waited < 20000 && !qpage; waited += 1000) {
    await sleep(1000);
    for (const p of ctx.pages()) { try { if (await p.evaluate(() => document.querySelectorAll('app-ti[data-question-key]').length > 0)) { qpage = p; break; } } catch {} }
  }
  // Questions can render progressively: wait until the count is unchanged for 3s, and at least 6s after the click
  // (max 15s more). This only shortens the old fixed 13s wait; completeness is still checked below against the
  // paper's own expected question count, and validateDocument grades anything short as not complete.
  if (qpage) {
    let prev = -1, stable = 0;
    for (let i = 0; i < 15 && (stable < 3 || Date.now() - clickedAt < 6000); i++) {
      await sleep(1000);
      const n = await qpage.evaluate(() => document.querySelectorAll('app-ti[data-question-key]').length).catch(() => prev);
      stable = n === prev ? stable + 1 : 0; prev = n;
    }
  }
  if (!qpage) throw Object.assign(new Error('no rendered question page'), { code: 'NO_QUESTION_PAGE' });
  result.pageUrl = qpage.url(); result.pageTitle = await qpage.title();
  result.titleMatches = (T.titleFrag || []).every(f => result.pageTitle.includes(f));
  result.auth = auth.status;

  const snapshot = async () => {
    const raw = await qpage.evaluate((sel) => [...document.querySelectorAll(sel)].map(el => {
      const clone = el.cloneNode(true);
      const imgs = [...el.querySelectorAll('img')], copies = [...clone.querySelectorAll('img')];
      imgs.forEach((im, i) => { const a = im.currentSrc || im.getAttribute('src') || im.getAttribute('data-src'); if (a && copies[i]) copies[i].setAttribute('src', a); });
      return clone.outerHTML;
    }).join('\n'), config.contentSelector);
    if (!raw) throw Object.assign(new Error('empty DOM'), { code: 'EMPTY_DOM' });
    const cleaned = sanitizeHtml(raw);
    return { cleaned, parsed: parseFenbiExamDom(cleaned.html, T.identity, { url: result.pageUrl, capturedAt: new Date().toISOString() }) };
  };
  let { cleaned, parsed } = await snapshot();
  // The page states how many questions the paper has; if fewer rendered, give it one more chance before parsing.
  const expectedQ = parsed.expected?.questions;
  if (Number.isInteger(expectedQ) && parsed.questions.length < expectedQ) {
    await sleep(8000);
    ({ cleaned, parsed } = await snapshot());
    result.renderRetry = { expected: expectedQ, got: parsed.questions.length };
  }
  result.waitMs = Date.now() - clickedAt;
  await fs.writeFile(path.join(outDir, 'dom-raw.json'), JSON.stringify({ source: result.pageUrl, contentHtml: cleaned.html }), { mode: 0o600 });

  const document = createDocument(T.identity, { url: result.pageUrl, capturedAt: new Date().toISOString() });
  document.identity.questionIdNamespace = parsed.identity.questionIdNamespace;
  document.source.url = parsed.source.url; document.chapters = parsed.chapters;
  document.evidence.push(...parsed.evidence); document.conflicts.push(...parsed.conflicts);
  for (const k of ['questions', 'materials']) if (parsed.expected[k] !== null) document.expected[k] = parsed.expected[k];
  absorbPayload(document, { questions: parsed.questions, materials: parsed.materials }, { url: result.pageUrl });
  for (const q of parsed.questions) { const x = document.questions.find(y => y.id === q.id); if (x) x.materialIdsObserved = q.materialIdsObserved; }
  document.assets = collectAssetUrls(document).map(u => ({ url: u, status: 'pending' }));
  try { await downloadAssets(qpage, document, path.join(outDir, 'assets')); } catch { document.conflicts.push({ scope: 'capture', field: 'image-download-interrupted' }); }
  const verdict = await validateDocument(document, { assetRoot: path.join(outDir, 'assets') });
  await fs.writeFile(path.join(outDir, 'document.json'), JSON.stringify(document), { mode: 0o600 });
  await fs.writeFile(path.join(outDir, 'validation.json'), JSON.stringify(verdict), { mode: 0o600 });

  let align = null;
  try { align = await comparePaper(document, await fs.readFile(path.join(REPO, T.paper), 'utf8'), { repoRoot: REPO, paperPath: path.join(REPO, T.paper), assetRoot: path.join(outDir, 'assets') }); }
  catch (e) { align = { error: String(e.message || e).slice(0, 160) }; }
  await fs.writeFile(path.join(outDir, 'alignment.json'), JSON.stringify(align, null, 2) + '\n', { mode: 0o600 });

  const a = document.assets || [];
  result.counts = { questions: document.questions.length, materials: document.materials.length,
    chapters: (document.chapters || []).length, imageRefs: a.length,
    imagesDownloaded: a.filter(x => x.status === 'downloaded').length,
    imagesUniqueSha: new Set(a.filter(x => x.sha256).map(x => x.sha256)).size };
  result.verdict = { status: verdict.status, issues: [...new Set((verdict.issues || []).map(i => i.code))].slice(0, 8) };
  result.align = align?.summary ? { sq: align.summary.sourceQuestions, rq: align.summary.repositoryQuestions,
    matched: align.summary.matched } : align;
  result.ok = true;
} catch (e) {
  result.error = (e.code || e.name) + ' :: ' + String(e.message || e).slice(0, 200);
} finally {
  try { if (ctx) await ctx.close(); } catch {}
  try { if ((await fs.readFile(lockPath, 'utf8')) === owner) await fs.unlink(lockPath); } catch {}
}
result.elapsedMs = Date.now() - t0;
result.nonGet = [...new Map(result.nonGet.map(x => [x.method + x.host + x.path, x])).values()];
await fs.writeFile(path.join(outDir, 'run-summary.json'), JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
console.log(JSON.stringify(result, null, 2));
