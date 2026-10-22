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
import { parseShenlunView, buildShenlunDocument } from '../src/dom-shenlun.mjs';
import { createDocument, absorbPayload, collectAssetUrls } from '../src/model.mjs';
import { validateDocument } from '../src/validate.mjs';
import { parseAnalysisDom, mergeAnalysisDom, mergeSolutionJson, isBlank } from './analysis-merge.mjs';
import { pickRow, collectPaperIds, bindingStatus } from './identity.mjs';
import { variantOf } from './queue.mjs';

export const ENTRY = 'https://www.fenbi.com/spa/tiku/guide/realTest/xingce/xingce';
export const ENTRY_SHENLUN = 'https://www.fenbi.com/spa/tiku/guide/shenlunList/shenlun/1000';
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
  const rows = () => page.locator('div.paper-item', { hasText: new RegExp(item.titleRe) });
  // 只认标题精确对上的那一行（见 identity.pickRow）；含本标题的更长标题（如网友回忆版）不算。
  const resolve = async () => {
    const texts = await rows().allInnerTexts().catch(() => []);
    const pick = pickRow(texts, item.identity?.title || '', item.siblingTitles || []);
    if (typeof pick === 'number') return rows().nth(pick);
    if (pick.error === 'AMBIGUOUS_ROW') throw fail('AMBIGUOUS_ROW');
    return null;
  };
  let row = slot.region === item.label ? await resolve() : null;
  if (row) return { row, catalogPages: 0 };
  await gate();
  await page.goto(ENTRY, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.locator('span.categories-item').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  await gate();
  await page.locator('span.categories-item', { hasText: item.label }).first().click();
  slot.region = item.label;
  await rows().first().waitFor({ state: 'visible', timeout: 6000 }).catch(() => {});
  let catalogPages = 1;
  row = await resolve();
  for (let p = 0; p < 6 && !row; p++) {
    const next = page.locator('footer.question-list-pager .houpage').first();
    if (!await next.count()) break;
    const disabled = await next.evaluate(e => !e.offsetParent || /disabled/i.test((e.className || '').toString())).catch(() => true);
    if (disabled) break;
    await gate();
    await next.click({ timeout: 10000 }).catch(() => {});
    await rows().first().waitFor({ state: 'visible', timeout: 3000 }).catch(() => {});
    catalogPages++;
    row = await resolve();
  }
  if (!row) { slot.region = null; throw fail('ROW_NOT_FOUND'); }
  return { row, catalogPages };
}

// 打开练习（在互斥锁内执行）：返回渲染出题目的页面。新卷可能在本页打开，也可能新开一页。
async function openExercise(slot, item, env, rec) {
  const { ctx, gate, policy } = env;
  if (item.kind === 'resume') {
    await gate();
    rec.clickedAt = Date.now();
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
    rec.clickedAt = Date.now();
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
  if (item.subject === 'shenlun') return runShenlunPaper(slot, item, env);
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
  // 打开练习之后，本卷页面上加载的 JSON 里出现的 paperId，用来核对身份（按页面归属，不会混进其他标签页的卷）。
  const idsByPage = new Map();
  const onCtxResp = async r => {
    try {
      if (!rec.clickedAt || !/json/i.test(r.headers()['content-type'] || '')) return;
      const pg = r.frame()?.page();
      if (!pg) return;
      const ids = collectPaperIds(JSON.parse((await r.body()).toString('utf8')));
      if (ids.size) { const set = idsByPage.get(pg) || new Set(); for (const x of ids) set.add(x); idsByPage.set(pg, set); }
    } catch {}
  };
  // 观察到的 paperId 与 sourceId 不一致：这不是目录里那份卷，不交卷（交卷后才发现则不落地），并隔离该 sourceId。
  const checkBinding = async stage => {
    const ids = idsByPage.get(qpage) || new Set();
    rec.binding = bindingStatus(ids, item.sourceId);
    rec.paperIds = [...ids].slice(0, 5);
    if (rec.binding === 'mismatch' || rec.binding === 'mixed') {
      await env.ledger.quarantine?.(item, { stage, binding: rec.binding, paperIds: rec.paperIds });
      throw fail('PAPER_ID_MISMATCH');
    }
  };
  env.ctx.on('response', onCtxResp);
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

    await checkBinding('before-submit');
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
    await checkBinding('after-submit');
    doc.evidence = Array.isArray(doc.evidence) ? doc.evidence : [];
    if (rec.binding === 'verified') doc.evidence.push({ type: 'source-paper-identity', paperId: item.sourceId,
      observedAt: new Date().toISOString(), via: 'paperId in exercise/analysis JSON on the opened page' });
    doc.evidence.push({ type: 'answer-explanation-source', source: 'fenbi-analysis-dom+observed-json', page: 'analysis-after-blank-submit',
      keyedBy: 'data-question-key/globalId', observedAt: new Date().toISOString(), dom, json: solution ? json : null });

    const prev = new Map((doc.assets || []).map(a => [a.url, a]));
    doc.assets = collectAssetUrls(doc).map(u => prev.get(u) || { url: u, status: 'pending' });
    const assets = await downloadAssets(qpage, doc, path.join(outDir, 'assets'));
    rec.assets = assets.filter(a => a.status === 'downloaded').length;
    // 图片走浏览器上下文的 API 客户端，不经过页面响应事件；遇到 401/403/429/503 时 downloadAssets 已立即停下，
    // 这里按 t2-asset-pass 的口径计入风控：401 视同登录失效（硬停），403、429/503 计入一小时阈值。
    for (const a of assets) {
      if (a.httpStatus === 401) env.risk.loginLost++;
      else if (a.httpStatus === 403) env.risk.http403++;
      else if (a.httpStatus === 429 || a.httpStatus === 503) env.risk.http429++;
    }

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
    try { env.ctx.off('response', onCtxResp); } catch {}
    if (qpage) { try { qpage.off('response', onResp); } catch {} }
    if (qpage && qpage !== slot.page) await qpage.close().catch(() => {});
    rec.elapsedMs = Date.now() - t0;
  }
  return rec;
}

// ---------- 申论：只读详情页 ----------
// 不建练习、不答题、不交卷、不购买、不解锁；只在目录里点真实行进入详情，读取页面现成的
// 给定材料、题面、参考答案与「考点/来源」。页面一次只渲染一题，靠 .questions-anchors 切题。

async function shenlunAnchors(page) {
  return page.evaluate(() => [...new Set(
    [...document.querySelectorAll('.questions-anchors *')]
      .map(element => (element.innerText || '').replace(/\s+/g, ' ').trim())
      .filter(text => /^\d+题$/u.test(text))
      .map(text => Number(text.replace('题', '')))
  )].sort((a, b) => a - b));
}

// 页面上已经渲染出来的「做题单元」：每个含 .ti-content 的 .resizable-container 是一题
// （材料栏 + 题面 + 参考答案/解析）。整卷式页面一次就给出全部题目，切换式每切一次多一个。
async function shenlunUnits(page) {
  return page.evaluate(() => [...document.querySelectorAll('.resizable-container')]
    .filter(element => element.querySelector('.ti-content'))
    .map((element, index) => {
      const clone = element.cloneNode(true);
      const images = [...element.querySelectorAll('img')], copies = [...clone.querySelectorAll('img')];
      images.forEach((image, at) => {
        const url = image.currentSrc || image.getAttribute('src') || image.getAttribute('data-src');
        if (url && copies[at]) copies[at].setAttribute('src', url);
      });
      const keyed = element.querySelector('[data-question-key]');
      return { key: (keyed && keyed.getAttribute('data-question-key')) || `dom-index-${index + 1}`, html: clone.outerHTML };
    }));
}

async function switchShenlunQuestion(page, number) {
  const clicked = await page.evaluate(target => {
    const norm = text => String(text || '').replace(/\s+/g, ' ').trim();
    const element = [...document.querySelectorAll('.questions-anchors *')].find(item => norm(item.innerText) === `${target}题`);
    if (!element) return false;
    element.click();
    return true;
  }, number);
  if (!clicked) return false;
  await sleep(2500);
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  return true;
}

async function openShenlunDetail(slot, item, env, rec) {
  const { gate } = env, page = slot.page;
  await gate();
  await page.goto(ENTRY_SHENLUN, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await sleep(2500);
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  const picked = await page.evaluate(name => {
    const norm = text => String(text || '').replace(/\s+/g, ' ').trim();
    const element = [...document.querySelectorAll('.category1-btn')].find(item => norm(item.innerText) === name);
    if (!element || element.offsetParent === null) return false;
    element.click();
    return true;
  }, item.region || item.label);
  if (!picked) throw fail('CATEGORY_NOT_FOUND');
  await sleep(2500);
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

  const rows = page.locator('li.list-item-container');
  const turnPage = async target => {
    const turned = await page.evaluate(number => {
      const element = [...document.querySelectorAll('div.paging div.item')].find(item => String(item.innerText).trim() === String(number));
      if (!element || element.offsetParent === null) return false;
      element.click();
      return true;
    }, target);
    if (!turned) return false;
    await sleep(2500);
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    return true;
  };
  // 行的派生特征：只读年份与卷型标记，不读标题原文。
  const rowTraits = () => page.evaluate(() => [...document.querySelectorAll('li.list-item-container')].map(element => {
    const text = (element.innerText || '').replace(/\s+/g, ' ').trim();
    const years = [...new Set([...text.matchAll(/\b(19|20)\d{2}\b/g)].map(match => Number(match[0])))].filter(year => year >= 2000 && year <= 2026);
    // 上海把卷型写在括号里（「（B、定向选调卷）」「（B、集中选调卷）」），不带「卷/类」二字，一并认。
    return { years, a: /A卷|A类|（A[、,]/u.test(text), b: /B卷|B类|（B[、,]/u.test(text), c: /C卷|C类|（C[、,]/u.test(text),
      xingzheng: /行政执法/u.test(text), township: /乡镇/u.test(text), county: /县级|县乡|旗县/u.test(text),
      fushengji: /副省级/u.test(text), dishiji: /地市级/u.test(text),
      member: /会员|VIP|付费|购买|开通|试看|解锁/u.test(text) };
  }));
  // 卷型必须真的核对：早先只认 A/B/C，行政执法卷于是在同年里点到相邻的 B 卷（PAPER_ID_MISMATCH）。
  const matches = (traits, year, variant) => traits.years.includes(Number(year))
    && (variant === 'a' ? traits.a
      : variant === 'b' ? traits.b
      : variant === 'c' ? traits.c
      : variant === 'xingzheng' ? traits.xingzheng
      : variant === 'township' ? traits.township
      : variant === 'county' ? traits.county
      : variant === 'fushengji' ? traits.fushengji
      : variant === 'dishiji' ? traits.dishiji
      : true);

  let index = null, catalogPages = 0;
  // 卷型区分不了同年多卷时（申论目录不给标题：unknown；或整年都是「联考」卷：liankao/tongkao），
  // 候选记下的「第几页第几行」既没法核对、也容易错位（上海 2018 就整体挪了一行）。
  // 这种卷改用「同地区同年候选顺序 ↔ 目录行顺序」配对定位。
  const generic = new Set(['unknown', 'liankao', 'tongkao']);
  const sequential = generic.has(item.identity.variant) && Number.isInteger(item.yearRank);
  if (Number.isInteger(item.page) && Number.isInteger(item.rowIndex) && !sequential) {
    // 目录采集时记下了「第几页第几行」。直接定位，点前核对年份/卷型，对不上就不点。
    for (let p = 1; p <= item.page; p++) if (p > 1 && !(await turnPage(p))) break;
    catalogPages = item.page;
    const traits = (await rowTraits())[item.rowIndex];
    if (traits && matches(traits, item.year, item.identity.variant)) index = item.rowIndex;
    else rec.catalogDrift = 'page-row-drifted';
  }
  if (index === null) {
    // 目录会更新：候选记下的「第几页第几行」可能整体错位。退回按年份（+卷型）重新扫描全部分页。
    let seen = 0;
    for (let p = 1; p <= 8 && index === null; p++) {
      if (!(await turnPage(p))) break;
      catalogPages = p;
      const traits = await rowTraits();
      if (!traits.length) break;
      const hits = traits.map((traitsOne, i) => matches(traitsOne, item.year, item.identity.variant) ? i : -1).filter(i => i >= 0);
      if (sequential) {
        for (const hit of hits) {
          if (seen === item.yearRank) { index = hit; break; }
          seen++;
        }
      } else {
        if (hits.length > 1) throw fail('AMBIGUOUS_ROW');
        if (hits.length) index = hits[0];
      }
    }
  }
  if (index === null) throw fail('ROW_NOT_FOUND');
  if ((await rowTraits())[index]?.member) throw fail('MEMBER_ROW');
  rec.catalogPages = catalogPages;
  await gate();
  rec.clickedAt = Date.now();
  const target = rows.nth(index);
  // 有的年份标题元素不存在，退化到点整行。
  await target.locator('.list-item-title').first().click({ timeout: 15000 })
    .catch(async () => { await target.click({ timeout: 15000 }); });
  for (let waited = 0; waited < 30000; waited += 1000) {
    if (await page.locator('.ti-content').count().catch(() => 0) > 0) {
      await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
      return page;
    }
    await sleep(1000);
  }
  throw fail('DETAIL_NOT_REACHED');
}

async function runShenlunPaper(slot, item, env) {
  const t0 = Date.now();
  const rec = { key: item.key, sid: item.sourceId, kind: 'new', subject: 'shenlun',
    status: 'pending', answers: 0, explanations: 0, assets: 0 };
  const outDir = path.join(env.papersDir, item.key);
  let qpage = null, captured = false;
  // 详情页地址带 paperId（…/ti/view/paper/…?paperId=7736778&…），用它核对"打开的确实是指定那卷"。
  // 监听要在导航之前挂上：详情页是在 openShenlunDetail 里就完成的，返回后再挂会漏掉这次导航。
  const paperIds = new Set();
  const collectId = url => {
    try {
      const id = new URL(url).searchParams.get('paperId');
      if (id && /^\d+$/u.test(String(id))) paperIds.add(String(id));
    } catch { /* 非法 URL 交给绑定核对处理 */ }
  };
  const onRequest = request => collectId(request.url());
  slot.page.on('request', onRequest);
  try {
    await fs.mkdir(outDir, { recursive: true, mode: 0o700 });
    qpage = await env.openLock(() => openShenlunDetail(slot, item, env, rec));
    if (qpage !== slot.page) qpage.on('request', onRequest);
    rec.pageUrl = qpage.url();
    collectId(rec.pageUrl);

    // 申论详情页有两种形态：切换式（一次只渲染一题，靠 .questions-anchors 点「N题」换页）与
    // 整卷式（整卷题目一次全部渲染、没有锚点，每题各占一个 .resizable-container，福建/广东多为此类）。
    // 统一按「做题单元」采集：题号在切换式取点中的锚点号，在整卷式按渲染顺序。
    const numbers = await shenlunAnchors(qpage);
    const units = new Map();
    const absorb = async number => {
      const materialHtml = (await snapshotHtml(qpage, '.resizable-container')).html;
      for (const unit of await shenlunUnits(qpage)) {
        if (!units.has(unit.key)) units.set(unit.key, { ...unit, materialHtml, number: number ?? units.size + 1 });
      }
    };
    await absorb();
    for (const number of numbers) {
      if (units.size >= numbers.length) break;
      if (!(await switchShenlunQuestion(qpage, number))) { rec.switchFailed = number; break; }
      await absorb(number);
    }
    if (!units.size) throw fail('NO_QUESTIONS');
    const views = [...units.values()].map(unit =>
      parseShenlunView(unit.html, { questionKey: unit.key, number: unit.number, materialHtml: unit.materialHtml }));
    rec.questionsRendered = views.length;

    const doc = buildShenlunDocument(views, item.identity, { url: qpage.url(), capturedAt: new Date().toISOString() });
    rec.pageTitle = (await qpage.title().catch(() => '')).trim();
    rec.titleMatches = (item.titleFrag || []).every(fragment => rec.pageTitle.includes(fragment));
    // 申论目录不返回标题原文，卷名以详情页标题为准；标题缺失时退到「地区+年份」并不冒充原卷名。
    if (!doc.identity.title) doc.identity.title = rec.pageTitle || `${item.area}${item.year}年申论`;
    rec.titleSource = rec.pageTitle ? 'detail-page-title' : 'area-and-year-fallback';
    // 申论目录项没有卷型。详情页标题能识别出具体卷型时用它，免得落地文件名全是「申论-unknown」；
    // 识别不出的仍留 unknown，由落地层用 sourceId 区分。
    if (!doc.identity.variant || doc.identity.variant === 'unknown') {
      const inferred = rec.pageTitle ? variantOf(rec.pageTitle) : null;
      if (inferred && inferred !== 'tongkao') doc.identity.variant = inferred;
    }
    rec.binding = bindingStatus(paperIds, item.sourceId);
    rec.paperIds = [...paperIds].slice(0, 5);
    if (rec.binding === 'mismatch' || rec.binding === 'mixed') {
      await env.ledger.quarantine?.(item, { stage: 'shenlun-detail', binding: rec.binding, paperIds: rec.paperIds });
      throw fail('PAPER_ID_MISMATCH');
    }
    // 校验器要求 source-paper-identity 才能认定身份；申论靠详情页请求里的 paperId 建立这条证据。
    if (rec.binding === 'verified') doc.evidence.push({ type: 'source-paper-identity', paperId: item.sourceId,
      observedAt: new Date().toISOString(), via: 'paperId query parameter on the opened detail page' });

    await writeAtomic(path.join(outDir, 'run-summary.json'), JSON.stringify({ key: item.key, sourceId: item.sourceId,
      subject: 'shenlun', at: new Date().toISOString(), pageUrl: rec.pageUrl, catalogPages: rec.catalogPages,
      binding: rec.binding, by: 'worker' }, null, 2) + '\n');
    await writeAtomic(path.join(outDir, 'dom-raw.json'), JSON.stringify({ source: qpage.url(),
      views: views.map(view => ({ number: view.number, sections: view.sections, absent: view.absent })) }));
    await writeAtomic(path.join(outDir, 'document.json'), JSON.stringify(doc));
    await env.ledger.markCapture(item, 'ok', { questions: doc.questions.length, catalogPages: rec.catalogPages ?? null });
    captured = true;
    rec.questions = doc.questions.length;
    rec.expected = doc.expected?.questions ?? null;

    const assets = await downloadAssets(qpage, doc, path.join(outDir, 'assets'));
    rec.assets = assets.filter(asset => asset.status === 'downloaded').length;
    for (const asset of assets) {
      if (asset.httpStatus === 401) env.risk.loginLost++;
      else if (asset.httpStatus === 403) env.risk.http403++;
      else if (asset.httpStatus === 429 || asset.httpStatus === 503) env.risk.http429++;
    }

    const verdict = await validateDocument(doc, { assetRoot: path.join(outDir, 'assets') });
    await writeAtomic(path.join(outDir, 'document.json'), JSON.stringify(doc));
    await writeAtomic(path.join(outDir, 'validation.json'), JSON.stringify(verdict, null, 2) + '\n');
    rec.answers = doc.questions.filter(question => String(question.answerHtml || '').replace(/<[^>]*>/g, '').trim()).length;
    rec.explanations = doc.questions.filter(question => String(question.explanationHtml || '').replace(/<[^>]*>/g, '').trim()).length;
    rec.verdict = verdict.status;
    rec.issues = [...new Set((verdict.issues || []).filter(issue => !issue.advisory).map(issue => issue.code))].slice(0, 8);
    rec.advisory = [...new Set((verdict.issues || []).filter(issue => issue.advisory).map(issue => issue.code))].slice(0, 8);
    rec.status = verdict.status === 'complete' ? 'complete' : 'submitted_partial';
    await env.ledger.markSubmit(item, rec.status, { answers: rec.answers, assets: rec.assets });
  } catch (e) {
    rec.status = e.code || 'error';
    rec.error = (e.code || e.name || 'ERR') + ' :: ' + String(e.message || e).slice(0, 160);
    if (!captured) await env.ledger.markCapture(item, 'failed', { error: rec.error.slice(0, 120) }).catch(() => {});
  } finally {
    try { slot.page.off('request', onRequest); } catch {}
    if (qpage && qpage !== slot.page) { try { qpage.off('request', onRequest); } catch {} await qpage.close().catch(() => {}); }
    rec.elapsedMs = Date.now() - t0;
  }
  return rec;
}

