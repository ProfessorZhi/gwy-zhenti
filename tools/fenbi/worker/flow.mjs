// 单卷浏览器流程：一个标签页把一卷从目录走到落盘。
//   目录找行 → 点开练习（每卷至多 1 次 init）→ 解析题目页 → 停留 → 交白卷（每卷至多 1 次）→ 解析页 DOM + solution JSON
//   → 图片 → 校验 → 写本地缓存（papers/<key>/）
// 同一浏览器里多个标签页共用：导航闸门（相邻导航 ≥2.5s）、"打开练习"互斥锁（init 预算按卷发放、新开的页一定属于本卷）。
import fs from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { requestPolicy, downloadAssets } from '../src/browser.mjs';
import { sanitizeHtml } from '../src/privacy.mjs';
import { parseFenbiExamDom } from '../src/dom.mjs';
import { createDocument, absorbPayload, collectAssetUrls } from '../src/model.mjs';
import { validateDocument } from '../src/validate.mjs';
import { parseAnalysisDom, mergeAnalysisDom, mergeSolutionJson, isBlank } from './analysis-merge.mjs';

export const ENTRY = 'https://www.fenbi.com/spa/tiku/guide/realTest/xingce/xingce';
const QSEL = 'app-ti[data-question-key]';
const fail = (code, message = code) => Object.assign(new Error(message), { code });
const writeAtomic = async (file, text) => { const tmp = file + '.tmp'; await fs.writeFile(tmp, text, { mode: 0o600 }); await fs.rename(tmp, file); };

export function createGate(gapMs) {
  let last = 0, chain = Promise.resolve();
  return () => {
    const p = chain.then(async () => { const w = gapMs - (Date.now() - last); if (w > 0) await sleep(w); last = Date.now(); });
    chain = p.catch(() => {});
    return p;
  };
}

export function createMutex() {
  let chain = Promise.resolve();
  return fn => { const p = chain.then(fn); chain = p.catch(() => {}); return p; };
}

// 写请求白名单：交卷、解析页的两个界面上报；练习 init 只有在本卷"打开练习"窗口内、预算未用完时放行。
// 放行用 fallback：没有别的路由时等同 continue（发往网络）；离线测试可以在它之前注册假站点。
export async function installRoutes(ctx, policy) {
  await ctx.route('**/*', async route => {
    const req = route.request(), m = req.method().toUpperCase();
    let u; try { u = new URL(req.url()); } catch { return route.abort('blockedbyclient'); }
    if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') {
      if (u.hostname === 'data-api.fenbi.com') return route.abort('blockedbyclient');
      if (req.isNavigationRequest() && requestPolicy({ url: req.url(), method: m, navigation: true }, 'capture') === 'blockedNavigation') return route.abort('blockedbyclient');
      return route.fallback();
    }
    const isInit = m === 'POST' && u.hostname === 'tiku.fenbi.com' && u.pathname === '/api/xingce/exercises';
    if (isInit && policy.initBudget > 0) { policy.initBudget--; policy.initCalls++; return route.fallback(); }
    const isSubmit = m === 'POST' && u.hostname === 'tiku.fenbi.com' && /\/combine\/exercise\/submit$/.test(u.pathname);
    const isUiConfig = m === 'POST' && u.hostname === 'ke.fenbi.com' && /\/tiku_config\/report_display_cards$/.test(u.pathname);
    const isStudyTime = m === 'POST' && u.hostname === 'tiku.fenbi.com' && /\/activity\/report\/studyTime$/.test(u.pathname);
    if (isSubmit || isUiConfig || isStudyTime) return route.fallback();
    policy.blockedWrites++;
    return route.abort('blockedbyclient');
  });
}

// 风控计数（整个浏览器共用）：403/429、验证码路径、登录态接口 401/403。
export function watchRisk(ctx, risk) {
  ctx.on('response', r => { try {
    const u = new URL(r.url()), st = r.status();
    if (st === 403) risk.http403++;
    if (st === 429) risk.http429++;
    if (/captcha|verifycode|verification/i.test(u.pathname)) risk.captcha++;
    if (u.hostname === 'login.fenbi.com' && /\/api\/users\/info$/.test(u.pathname) && (st === 401 || st === 403)) risk.loginLost++;
  } catch {} });
}

const countQuestions = p => p.evaluate(sel => document.querySelectorAll(sel).length, QSEL).catch(() => 0);

// 目录：标签页已在该地区的目录上就先在当前页找，找不到再从入口重新进入并逐页往后翻（最多 6 页）。
async function findRow(slot, item, gate) {
  const page = slot.page;
  const locate = () => page.locator('div.paper-item', { hasText: new RegExp(item.titleRe) }).first();
  if (slot.region === item.label && await locate().count()) return { row: locate(), catalogPages: 0 };
  await gate();
  await page.goto(ENTRY, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.locator('span.categories-item').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  await gate();
  await page.locator('span.categories-item', { hasText: item.label }).first().click();
  slot.region = item.label;
  await locate().waitFor({ state: 'visible', timeout: 6000 }).catch(() => {});
  let catalogPages = 1;
  for (let p = 0; p < 6 && !(await locate().count()); p++) {
    const next = page.locator('footer.question-list-pager .houpage').first();
    if (!await next.count()) break;
    const disabled = await next.evaluate(e => !e.offsetParent || /disabled/i.test((e.className || '').toString())).catch(() => true);
    if (disabled) break;
    await gate();
    await next.click({ timeout: 10000 }).catch(() => {});
    await locate().waitFor({ state: 'visible', timeout: 3000 }).catch(() => {});
    catalogPages++;
  }
  if (!(await locate().count())) { slot.region = null; throw fail('ROW_NOT_FOUND'); }
  return { row: locate(), catalogPages };
}

// 打开练习（在互斥锁内执行）：返回渲染出题目的页面。新卷可能在本页打开，也可能新开一页。
async function openExercise(slot, item, env, rec) {
  const { ctx, gate, policy } = env;
  if (item.kind === 'resume') {
    await gate();
    await slot.page.goto(item.pageUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
    slot.region = null;
    for (let waited = 0; waited < 30000; waited += 1000) {
      if (await countQuestions(slot.page) > 0) return slot.page;
      await sleep(1000);
    }
    throw fail('NO_QUESTION_PAGE');
  }
  const { row, catalogPages } = await findRow(slot, item, gate);
  rec.catalogPages = catalogPages;
  const rowText = (await row.innerText()).replace(/\s+/g, ' ').trim();
  rec.hadExistingExercise = /未完成|继续练习/.test(rowText);
  const before = new Set(ctx.pages());
  const initBefore = policy.initCalls;
  policy.initBudget = rec.hadExistingExercise ? 0 : 1;
  try {
    await gate();
    await row.click();
    for (let waited = 0; waited < 20000; waited += 1000) {
      await sleep(1000);
      const candidates = [slot.page, ...ctx.pages().filter(p => !before.has(p))];
      for (const p of candidates) if (await countQuestions(p) > 0) {
        if (p === slot.page) slot.region = null;
        return p;
      }
    }
    throw fail('NO_QUESTION_PAGE');
  } finally {
    policy.initBudget = 0;
    rec.initCalls = policy.initCalls - initBefore;
  }
}

// 题目可能分批渲染：数量连续 3 秒不变且距打开至少 6 秒（最多再等 15 秒）。
async function waitStable(qpage, openedAt) {
  let prev = -1, stable = 0;
  for (let i = 0; i < 15 && (stable < 3 || Date.now() - openedAt < 6000); i++) {
    await sleep(1000);
    const n = await countQuestions(qpage) || prev;
    stable = n === prev ? stable + 1 : 0; prev = n;
  }
  return prev;
}

async function snapshotHtml(qpage, selector) {
  const raw = await qpage.evaluate(sel => [...document.querySelectorAll(sel)].map(el => {
    const clone = el.cloneNode(true);
    const imgs = [...el.querySelectorAll('img')], copies = [...clone.querySelectorAll('img')];
    imgs.forEach((im, i) => { const a = im.currentSrc || im.getAttribute('src') || im.getAttribute('data-src'); if (a && copies[i]) copies[i].setAttribute('src', a); });
    return clone.outerHTML;
  }).join('\n'), selector);
  if (!raw) throw fail('EMPTY_DOM');
  return sanitizeHtml(raw);
}

async function buildDocument(qpage, item, rec, outDir) {
  const parse = async () => {
    const cleaned = await snapshotHtml(qpage, '.tis-container');
    return { cleaned, parsed: parseFenbiExamDom(cleaned.html, item.identity, { url: qpage.url(), capturedAt: new Date().toISOString() }) };
  };
  let { cleaned, parsed } = await parse();
  const expected = parsed.expected?.questions;
  if (Number.isInteger(expected) && parsed.questions.length < expected) {
    await sleep(8000);
    ({ cleaned, parsed } = await parse());
    rec.renderRetry = { expected, got: parsed.questions.length };
  }
  await writeAtomic(path.join(outDir, 'dom-raw.json'), JSON.stringify({ source: qpage.url(), contentHtml: cleaned.html }));
  const doc = createDocument(item.identity, { url: qpage.url(), capturedAt: new Date().toISOString() });
  doc.identity.questionIdNamespace = parsed.identity.questionIdNamespace;
  doc.source.url = parsed.source.url; doc.chapters = parsed.chapters;
  doc.evidence.push(...parsed.evidence); doc.conflicts.push(...parsed.conflicts);
  for (const k of ['questions', 'materials']) if (parsed.expected[k] !== null) doc.expected[k] = parsed.expected[k];
  absorbPayload(doc, { questions: parsed.questions, materials: parsed.materials }, { url: qpage.url() });
  for (const q of parsed.questions) { const x = doc.questions.find(y => y.id === q.id); if (x) x.materialIdsObserved = q.materialIdsObserved; }
  return doc;
}

async function submitBlank(qpage) {
  const clicked = await qpage.evaluate(() => {
    const els = [...document.querySelectorAll('.submit-btn')].filter(e => (e.innerText || '').trim() === '交卷' && e.offsetParent !== null);
    if (!els.length) return false;
    els[0].click(); return true;
  }).catch(() => false);
  if (!clicked) throw fail('SUBMIT_BUTTON_MISSING');
  await sleep(1500);
  for (let i = 0; i < 2; i++) {
    const btn = qpage.locator('.modal-action-btn.btn-submit').first();
    if (!(await btn.count().catch(() => 0))) break;
    await btn.click({ timeout: 10000 }).catch(() => {});
    await sleep(2000);
  }
  for (let waited = 0; waited < 45000; waited += 1500) {
    const ok = await qpage.evaluate(() => { const b = document.body.innerText || ''; return /正确答案/.test(b) && /解析/.test(b); }).catch(() => false);
    if (ok) return;
    await sleep(1500);
  }
  throw fail('ANALYSIS_NOT_REACHED');
}

/**
 * 跑一卷。env: { ctx, gate, openLock, policy, risk, dwellMs, papersDir, ledger }
 * ledger: { markSubmit(item, status, extra), markCapture(item, status, extra) } —— 由主进程持久化。
 * 返回记录 { status, ... }；status 为 complete / submitted_partial / not_blank / 失败码。
 */
export async function runPaper(slot, item, env) {
  const t0 = Date.now();
  const rec = { key: item.key, sid: item.sourceId, kind: item.kind, status: 'pending', answers: 0, explanations: 0, assets: 0 };
  const outDir = path.join(env.papersDir, item.key);
  let qpage = null, solution = null, captured = false;
  const onResp = async r => {
    try {
      if (!/\/combine\/static\/solution/.test(new URL(r.url()).pathname)) return;
      const j = JSON.parse((await r.body()).toString('utf8'));
      if (Array.isArray(j?.solutions)) solution = j;
    } catch {}
  };
  try {
    await fs.mkdir(outDir, { recursive: true, mode: 0o700 });
    const openedAt = Date.now();
    qpage = await env.openLock(() => openExercise(slot, item, env, rec));
    qpage.on('response', onResp);
    rec.pageUrl = qpage.url();
    rec.questionsRendered = await waitStable(qpage, openedAt);
    const readyAt = Date.now();

    let doc;
    if (item.kind === 'new') {
      doc = await buildDocument(qpage, item, rec, outDir);
      rec.pageTitle = await qpage.title().catch(() => '');
      rec.titleMatches = (item.titleFrag || []).every(f => rec.pageTitle.includes(f));
      await writeAtomic(path.join(outDir, 'run-summary.json'), JSON.stringify({ key: item.key, sourceId: item.sourceId,
        at: new Date().toISOString(), pageUrl: rec.pageUrl, initCalls: rec.initCalls, catalogPages: rec.catalogPages,
        hadExistingExercise: rec.hadExistingExercise, renderRetry: rec.renderRetry || null, by: 'worker' }, null, 2) + '\n');
      await writeAtomic(path.join(outDir, 'document.json'), JSON.stringify(doc));
      await env.ledger.markCapture(item, 'ok', { questions: doc.questions.length, catalogPages: rec.catalogPages ?? null });
      captured = true;
    } else {
      doc = JSON.parse(await fs.readFile(path.join(outDir, 'document.json'), 'utf8'));
    }
    rec.questions = doc.questions.length;
    rec.expected = doc.expected?.questions ?? null;

    const blank = await qpage.evaluate(sel => {
      const inputs = [...document.querySelectorAll(sel + ' input')];
      const body = document.body.innerText || '';
      return { checked: inputs.filter(i => i.checked).length, aria: document.querySelectorAll(sel + ' [aria-checked="true"]').length,
        hint: (body.match(/(已答|已做)\s*[:：]?\s*(\d+)/) || [])[2] };
    }, QSEL);
    if (!isBlank(blank)) { rec.status = 'not_blank'; await env.ledger.markSubmit(item, 'not_blank'); return rec; }

    const wait = readyAt + env.dwellMs - Date.now();
    if (wait > 0) await sleep(wait);
    rec.dwellMs = Date.now() - readyAt;

    // 先登记"交卷中"再点交卷：之后无论哪一步中断，这一卷都不会再被交第二次。
    await env.ledger.markSubmit(item, 'submitting');
    await submitBlank(qpage);
    await sleep(2000);
    const analysis = await snapshotHtml(qpage, QSEL);
    await writeAtomic(path.join(outDir, 'analysis-dom.json'), JSON.stringify({ sourceId: item.sourceId, at: new Date().toISOString(), contentHtml: analysis.html }));
    await env.ledger.markSubmit(item, 'submitted_partial');

    const dom = mergeAnalysisDom(doc, parseAnalysisDom(analysis.html), sanitizeHtml);
    for (let waited = 0; !solution && waited < 5000; waited += 500) await sleep(500);
    const json = mergeSolutionJson(doc, solution, sanitizeHtml);
    if (solution) await writeAtomic(path.join(outDir, 'solution.json'), JSON.stringify(solution));
    doc.evidence = Array.isArray(doc.evidence) ? doc.evidence : [];
    doc.evidence.push({ type: 'answer-explanation-source', source: 'fenbi-analysis-dom+observed-json', page: 'analysis-after-blank-submit',
      keyedBy: 'data-question-key/globalId', observedAt: new Date().toISOString(), dom, json: solution ? json : null });

    const prev = new Map((doc.assets || []).map(a => [a.url, a]));
    doc.assets = collectAssetUrls(doc).map(u => prev.get(u) || { url: u, status: 'pending' });
    const assets = await downloadAssets(qpage, doc, path.join(outDir, 'assets'));
    rec.assets = assets.filter(a => a.status === 'downloaded').length;
    // 图片接口 401/403 不经过页面响应事件，按 403 计入风控（与 t2-asset-pass 一致）。
    env.risk.http403 += assets.filter(a => a.status === 'unauthorized').length;

    const verdict = await validateDocument(doc, { assetRoot: path.join(outDir, 'assets') });
    await writeAtomic(path.join(outDir, 'document.json'), JSON.stringify(doc));
    await writeAtomic(path.join(outDir, 'validation.json'), JSON.stringify(verdict, null, 2) + '\n');
    rec.answers = doc.questions.filter(q => String(q.answerHtml || '').replace(/<[^>]*>/g, '').trim()).length;
    rec.explanations = dom.explanations + json.explanations;
    rec.verdict = verdict.status;
    rec.issues = [...new Set((verdict.issues || []).map(i => i.code))].slice(0, 8);
    rec.status = verdict.status === 'complete' ? 'complete' : 'submitted_partial';
    await env.ledger.markSubmit(item, rec.status, { answers: rec.answers, assets: rec.assets });
  } catch (e) {
    rec.status = e.code || 'error';
    rec.error = (e.code || e.name || 'ERR') + ' :: ' + String(e.message || e).slice(0, 160);
    if (item.kind === 'new' && !captured) await env.ledger.markCapture(item, 'failed', { error: rec.error.slice(0, 120) }).catch(() => {});
  } finally {
    if (qpage) { try { qpage.off('response', onResp); } catch {} }
    if (qpage && qpage !== slot.page) await qpage.close().catch(() => {});
    rec.elapsedMs = Date.now() - t0;
  }
  return rec;
}

