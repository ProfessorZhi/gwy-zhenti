#!/usr/bin/env node
// 申论「全部材料页签」只读补采。
//
// 背景：旧 driver 每题只快照当前激活的 .material-body，导致卷面 7 个材料只存下 1 个
// （浙江 2020 A：materialTabs=7 / storedMaterials=1）。本脚本仍只做只读采集：
//   * 不 init 练习、不交卷、不购买；openSession(capture) 会中止一切非 GET/HEAD/OPTIONS 请求；
//   * 逐题点击材料页签，逐个 pane 快照 .material-body，再按 htmlSha 合并成卷级 materials[]；
//   * 每题实际看到的 pane 保留为 materialsThisQuestion[]（来源证据，不推测）。
//
// 输出写到你指定的 --out 目录（本地私有），绝不写 work/fenbi/papers 或题库目录。
//
// 用法：
//   node tools/fenbi/driver/shenlun-capture-panes.mjs \
//     --area 浙江 --year 2020 --variant a --source-id 102033 \
//     --title-hash 0b3e1c9f86d4 --title-len 19 --list-page 2 \
//     --out /path/to/private/capture
//
// --title-hash 是必填项：身份只能靠事先固定的哈希核对，缺失就不采集。
//
// 同一年有多卷（国考 2026 副省级/地市级/行政执法）时，清单行文本里没有 sourceId，
// 只能按行号显式绑定：--row-index N 必须配 --list-page N，且必须在同一页观察到
// 真实列表 API 的有序 id 数组，行数/页码/分页自洽，并断言 apiIds[rowIndex] === sourceId。
// 观察不到或不一致就 FAIL CLOSED：不点开行、不写 source 文档。
//
// 退出码：0 成功；2 参数/结构错误；3 风控信号（401/403/429/503）中止；1 运行时错误。

import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { setTimeout as sleep } from 'node:timers/promises';

import { loadConfig } from '../src/config.mjs';
import { openSession } from '../src/browser.mjs';
import { assembleMaterialPanes, materialsThisQuestion, sha256 } from '../src/shenlun-panes.mjs';
import { bindRowToApi, normalizeListApiSnapshot, verifyTitleHash } from '../src/shenlun-list.mjs';
import { pairPaperViewComponents } from '../src/shenlun-paper-view.mjs';
import { parseShenlunCapture, metadataReceipt } from '../src/shenlun.mjs';
import { validateDocument } from '../src/validate.mjs';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(REPO, 'work/fenbi'));
const ENTRY = 'https://www.fenbi.com/spa/tiku/guide/shenlunList/shenlun/1000';
const MAX_QUESTIONS = 30;
const MAX_PAGES = 5;
const LOGIN = /会员|VIP|付费|购买|开通|试看|解锁/u;

function fail(code, message, extra = {}) {
  const error = new Error(message);
  error.code = code;
  Object.assign(error, extra);
  return error;
}

const { values } = parseArgs({
  allowPositionals: false,
  options: {
    area: { type: 'string' }, year: { type: 'string' }, variant: { type: 'string' },
    'source-id': { type: 'string' }, 'paper-id': { type: 'string' },
    'title-hash': { type: 'string' }, 'title-len': { type: 'string' },
    'list-page': { type: 'string' }, 'row-index': { type: 'string' }, out: { type: 'string' },
    'gap-ms': { type: 'string' }, 'work-dir': { type: 'string' }, help: { type: 'boolean' },
  },
});

if (values.help) {
  console.log('usage: shenlun-capture-panes.mjs --area 浙江 --year 2020 --variant a --source-id 102033 --title-hash HEX12-64 --out DIR [--row-index N --list-page N] [--title-len N] [--gap-ms 2500]');
  process.exit(0);
}
for (const required of ['area', 'year', 'variant', 'source-id', 'out', 'title-hash']) {
  if (!values[required]) { console.error(`missing-argument:--${required}`); process.exit(2); }
}
// 身份只能靠事先固定的标题哈希核对；缺失或格式不对就直接拒绝，连浏览器都不开。
if (!/^[0-9a-f]{12,64}$/u.test(String(values['title-hash']).toLowerCase())) {
  console.error('invalid-argument:--title-hash'); process.exit(2);
}
const AREA = values.area;
const YEAR = Number(values.year);
const VARIANT = values.variant.toLowerCase();
const SOURCE_ID = String(values['source-id']);
const OUT = path.resolve(values.out);
const GAP = Math.max(2500, Number(values['gap-ms'] || 2500));
const WORK_DIR = values['work-dir'] ? path.resolve(values['work-dir']) : WORK;

// 采集正文只能落在仓库外的私有目录：仓库/生产 work 目录一律拒绝，避免误提交。
for (const [label, root] of [['repo', REPO], ['work-dir', WORK_DIR]]) {
  if (OUT === root || OUT.startsWith(root + path.sep)) {
    console.error(`refusing-output-inside-${label}`);
    process.exit(2);
  }
}

const receipt = {
  at: new Date().toISOString(), sourceId: SOURCE_ID, area: AREA, year: YEAR, variant: VARIANT,
  status: 'running', navigations: 1, clicks: 0, guarded: null, risk: { unauthorized: 0, rateLimited: 0 },
  titleCheck: null, structure: null, questions: [], panes: null, blocks: [], errors: [],
};

let session;
let exitCode = 0;
try {
  const base = await loadConfig(path.join(WORK_DIR, 'config.json'));
  const config = {
    ...base, workDir: WORK_DIR, profileDir: path.join(WORK_DIR, 'profiles', base.profileName),
    entryUrl: ENTRY, timeoutMs: 45000,
  };
  session = await openSession(config, { mode: 'capture', headless: false });
  const { page } = session;
  page.on('response', (response) => {
    const status = response.status();
    if (status === 401 || status === 403) receipt.risk.unauthorized += 1;
    if (status === 429 || status === 503) receipt.risk.rateLimited += 1;
  });

  // 同页真实列表 API 的有序 id 数组。只留内存：名称仅用于计算标题哈希，绝不写盘。
  // 观察不到就 FAIL CLOSED，绝不按行号硬猜。
  const listApiResponses = [];
  let listApiSeq = 0;
  page.on('response', (response) => {
    let url;
    try { url = new URL(response.url()); } catch { return; }
    if (!/(^|\.)fenbi\.com$/u.test(url.hostname)) return;
    if (response.request().method() !== 'GET') return;
    if (!url.pathname.startsWith('/api/') || url.pathname.startsWith('/api/users/')) return;
    const contentType = String(response.headers()['content-type'] || '');
    if (!contentType.includes('json')) return;
    const seq = ++listApiSeq;
    response.json().then((json) => {
      if (!Array.isArray(json?.list ?? json?.body?.list)) return;
      listApiResponses.push({ seq, path: url.pathname, json });
    }).catch(() => { /* 非列表响应或读取失败：不登记 */ });
  });
  const listApiMark = () => listApiSeq;
  const waitForListApi = async (pageNumber, afterSeq) => {
    for (let attempt = 0; attempt < 24; attempt += 1) {
      const candidates = listApiResponses.filter((entry) => entry.seq > afterSeq);
      for (let i = candidates.length - 1; i >= 0; i -= 1) {
        try {
          const api = normalizeListApiSnapshot(candidates[i].json, { path: candidates[i].path });
          if (api.page === pageNumber - 1) return api;
        } catch { /* 不是可用的列表快照，继续找 */ }
      }
      await sleep(250);
    }
    throw fail('LIST_API_UNOBSERVED', `no list API response observed for page ${pageNumber}`);
  };

  const settle = async (ms = 2500) => {
    await sleep(ms);
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  };
  const stopOnRisk = () => {
    if (receipt.risk.unauthorized || receipt.risk.rateLimited) {
      throw fail('RISK_SIGNAL', 'unauthorized-or-rate-limited response observed; stopping without retry', { risk: receipt.risk });
    }
  };

  // ---- 列表：只读定位目标行 ----
  await page.goto(ENTRY, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await settle(3500);
  const regionClicked = await page.evaluate((region) => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    const el = [...document.querySelectorAll('.category1-btn')].find((x) => norm(x.innerText) === region);
    if (!el || el.offsetParent === null) return false;
    el.click(); return true;
  }, AREA);
  if (!regionClicked) throw fail('REGION_NOT_FOUND', 'region button not visible');
  receipt.clicks += 1;
  await settle(3000);
  stopOnRisk();

  const rowIndex = () => page.evaluate(() => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    return [...document.querySelectorAll('li.list-item-container')].map((el, index) => {
      const text = norm(el.innerText);
      const years = [...new Set([...text.matchAll(/\b(19|20)\d{2}\b/gu)].map((match) => Number(match[0])))];
      return {
        index, years,
        a: /A卷|A类/u.test(text), b: /B卷|B类/u.test(text), c: /C卷|C类/u.test(text),
        xingzheng: /行政执法/u.test(text), fushi: /副省级|副省/u.test(text), dishi: /地市级|地市/u.test(text),
        member: /会员|VIP|付费|购买|开通|试看|解锁/u.test(text),
      };
    });
  });
  const gotoPage = async (number) => {
    const ok = await page.evaluate((target) => {
      const el = [...document.querySelectorAll('div.paging div.item')].find((x) => String(x.innerText).trim() === String(target));
      if (!el || el.offsetParent === null) return false;
      el.click(); return true;
    }, number);
    if (!ok) return false;
    receipt.clicks += 1;
    await settle(2500);
    stopOnRisk();
    return true;
  };
  const pagerVisible = () => page.evaluate(() => [...document.querySelectorAll('div.paging div.item')]
    .map((el) => Number(String(el.innerText).trim()))
    .filter((value) => Number.isInteger(value) && value > 0));

  let target = null;
  let boundApi = null;
  const wantedPage = values['list-page'] ? Number(values['list-page']) : null;
  const explicitRow = values['row-index'] !== undefined ? Number(values['row-index']) : null;
  if (explicitRow !== null) {
    // 显式行号必须同时固定页码，否则无法断言「同一页」。
    if (wantedPage === null) throw fail('LIST_PAGE_REQUIRED', '--row-index requires --list-page');
    const pageNumber = wantedPage;
    if (!Number.isInteger(pageNumber) || pageNumber < 1) throw fail('LIST_PAGE_INVALID', '--list-page must be a positive integer');
    const mark = listApiMark();
    if (pageNumber > 1 && !(await gotoPage(pageNumber))) throw fail('PAGER_FAILED', 'cannot open the requested list page');
    // 观察不到同页列表 API 就停在这里：不点行、不写 source 文档。
    const api = await waitForListApi(pageNumber, pageNumber > 1 ? mark : 0);
    const pager = await pagerVisible();
    const picked = bindRowToApi(await rowIndex(), api, {
      index: explicitRow, sourceId: SOURCE_ID, page: pageNumber,
      year: YEAR, variant: VARIANT,
    });
    // 点开之前先用同页 API 的名称哈希核对一次固定的 --title-hash：
    // 名字对不上就停在这里，连详情页都不进。
    const boundName = api.names[picked.index];
    if (typeof boundName !== 'string' || boundName.length === 0) {
      throw fail('TITLE_API_NAME_UNHASHABLE', 'bound list API item has no name to hash');
    }
    verifyTitleHash({
      observedHash: createHash('sha256').update(boundName, 'utf8').digest('hex'),
      expectedHash: values['title-hash'],
    });
    receipt.pagerVisible = pager;
    target = { page: pageNumber, index: picked.index, member: false, binding: picked.binding };
    boundApi = api;
  } else {
    for (let pageNumber = 1; pageNumber <= (wantedPage ?? MAX_PAGES) && !target; pageNumber += 1) {
      if (pageNumber > 1 && !(await gotoPage(pageNumber))) break;
      if (wantedPage && pageNumber !== wantedPage) continue;
      const hits = (await rowIndex()).filter((row) => row.years.includes(YEAR)
        && (VARIANT === 'a' ? row.a : VARIANT === 'b' ? row.b : VARIANT === 'c' ? row.c : true));
      if (hits.length === 1) target = { page: pageNumber, index: hits[0].index, member: hits[0].member, binding: { method: 'year-variant-search', rowIndex: hits[0].index } };
      else if (hits.length > 1) throw fail('ROW_NOT_UNIQUE', `matched ${hits.length} rows`);
    }
    if (!target) throw fail('ROW_NOT_FOUND', 'target list row not found');
    if (target.member) throw fail('MEMBER_ROW', 'target row is member/paywalled; refusing to open');
    if (wantedPage && target.page !== wantedPage) {
      if (!(await gotoPage(target.page))) throw fail('PAGER_FAILED', 'cannot return to target page');
    }
  }
  receipt.listPage = target.page;
  receipt.rowBinding = target.binding;
  if (boundApi) {
    receipt.listApi = {
      page: boundApi.page, totalPage: boundApi.totalPage, totalItem: boundApi.totalItem,
      itemCount: boundApi.itemCount, idsSha256: sha256(boundApi.ids.join(',')), sourcePath: boundApi.sourcePath,
    };
  }

  await page.evaluate((index) => {
    const rows = [...document.querySelectorAll('li.list-item-container')];
    const row = rows[index];
    if (!row) return false;
    (row.querySelector('.list-item-title') || row).click();
    return true;
  }, target.index);
  receipt.clicks += 1;
  await settle(6000);
  stopOnRisk();

  // ---- 身份：DOM 全标题哈希必须命中事先固定的 --title-hash ----
  const title = await page.title();
  const titleHashFull = createHash('sha256').update(title, 'utf8').digest('hex');
  const apiName = boundApi?.names?.[target.index];
  const apiNameHash = typeof apiName === 'string' && apiName.length
    ? createHash('sha256').update(apiName, 'utf8').digest('hex') : null;
  // 行号绑定模式下，列表 API 的该项名称也必须可用于身份核对；缺失即拒绝。
  if (boundApi && apiNameHash === null) throw fail('TITLE_API_NAME_UNHASHABLE', 'bound list API item has no name to hash');
  const expectedTitleLen = values['title-len'] ? Number(values['title-len']) : null;
  const titleVerdict = verifyTitleHash({
    observedHash: titleHashFull, observedLen: title.length,
    expectedHash: values['title-hash'], expectedLen: expectedTitleLen, apiNameHash,
  });
  receipt.titleCheck = {
    source: 'dom-title + pinned hash', titleLen: title.length,
    titleHash: titleHashFull.slice(0, 16), titleHashFull,
    expectedTitleHash: values['title-hash'], expectedTitleLen,
    verified: titleVerdict.verified, apiNameVerified: titleVerdict.apiNameVerified,
    apiNamePresent: apiNameHash !== null,
  };

  // ---- 页签结构（只返回 kind/count，不返回正文） ----
  const structure = () => page.evaluate(() => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    const strips = [...document.querySelectorAll('nav.nav-container')].map((nav) => {
      const tabs = [...nav.querySelectorAll('a.tab')];
      const labels = tabs.map((tab) => norm(tab.innerText));
      const kind = labels.length && labels.every((label) => /^材料\s*\d+$/u.test(label)) ? 'material'
        : labels.length && labels.every((label) => /^\d+题$/u.test(label)) ? 'question' : 'other';
      return { kind, count: tabs.length, labels };
    });
    const anchors = [...new Set([...document.querySelectorAll('.questions-anchors *')]
      .map((el) => norm(el.innerText)).filter((text) => /^\d+题$/u.test(text)))];
    return {
      strips,
      materialTabs: Math.max(0, ...strips.filter((strip) => strip.kind === 'material').map((strip) => strip.count)),
      questionTabs: Math.max(0, ...strips.filter((strip) => strip.kind === 'question').map((strip) => strip.count)),
      anchors,
      materialBodyPresent: Boolean(document.querySelector('.material-body')),
    };
  });

  const clickTab = (kind, index) => page.evaluate(({ kind, index }) => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    for (const nav of document.querySelectorAll('nav.nav-container')) {
      const tabs = [...nav.querySelectorAll('a.tab')];
      if (!tabs.length) continue;
      const labels = tabs.map((tab) => norm(tab.innerText));
      const currentKind = labels.every((label) => /^材料\s*\d+$/u.test(label)) ? 'material'
        : labels.every((label) => /^\d+题$/u.test(label)) ? 'question' : 'other';
      if (currentKind !== kind || index >= tabs.length) continue;
      tabs[index].click();
      return { clicked: true, label: labels[index] };
    }
    return { clicked: false };
  }, { kind, index });

  const snapshotQuestion = () => page.evaluate(() => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    const content = document.querySelector('.ti-content');
    const sections = [...document.querySelectorAll('.result-common-section')].map((section) => {
      const title = norm((section.querySelector('.solution-title') || section).innerText).slice(0, 12);
      return {
        title,
        textLen: norm(section.innerText).length,
        images: section.querySelectorAll('img').length,
        html: section.innerHTML,
        bodyHtml: section.innerHTML,
      };
    });
    const keys = [...document.querySelectorAll('[data-question-key]')].map((el) => el.getAttribute('data-question-key'));
    return {
      prompt: content ? { textLen: norm(content.innerText).length, html: content.innerHTML } : null,
      sections, keys,
    };
  });

  const snapshotMaterial = () => page.evaluate(() => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    const body = document.querySelector('.material-body');
    if (!body) return null;
    return { textLen: norm(body.innerText).length, html: body.innerHTML, images: body.querySelectorAll('img').length };
  });

  // 整卷视图：没有页签条，每道题一个 app-ti，旁边一个 app-materials，按文档顺序平铺。
  // 只在左右组件数量相等、各自唯一、且纵坐标同序时才算配对成功。
  const paperViewComponents = () => page.evaluate(() => {
    const apps = [...document.querySelectorAll('app-materials')];
    const tis = [...document.querySelectorAll('app-ti')];
    return {
      materials: apps.map((app) => ({ top: app.getBoundingClientRect().top, bodies: app.querySelectorAll('.material-body').length })),
      questions: tis.map((ti) => ({ top: ti.getBoundingClientRect().top, contents: ti.querySelectorAll('.ti-content').length })),
    };
  });
  const snapshotQuestionAt = (index) => page.evaluate((i) => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    const container = document.querySelectorAll('app-ti')[i];
    if (!container) return { prompt: null, sections: [], keys: [] };
    const content = container.querySelector('.ti-content');
    const sections = [...container.querySelectorAll('.result-common-section')].map((section) => {
      const title = norm((section.querySelector('.solution-title') || section).innerText).slice(0, 12);
      return { title, textLen: norm(section.innerText).length, images: section.querySelectorAll('img').length, html: section.innerHTML, bodyHtml: section.innerHTML };
    });
    const keys = [...container.querySelectorAll('[data-question-key]')].map((el) => el.getAttribute('data-question-key'));
    return { prompt: content ? { textLen: norm(content.innerText).length, html: content.innerHTML } : null, sections, keys };
  }, index);
  const snapshotMaterialAt = (index) => page.evaluate((i) => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    const app = document.querySelectorAll('app-materials')[i];
    const body = app ? app.querySelector('.material-body') : null;
    if (!body) return null;
    return { textLen: norm(body.innerText).length, html: body.innerHTML, images: body.querySelectorAll('img').length };
  }, index);

  const initial = await structure();
  receipt.structure = { initial: { materialTabs: initial.materialTabs, questionTabs: initial.questionTabs, anchors: initial.anchors.length } };
  if (!initial.materialBodyPresent) throw fail('MATERIAL_PANE_MISSING', 'detail page has no .material-body pane');

  let paperView = null;
  let questionCount = Math.min(initial.questionTabs || initial.anchors.length, MAX_QUESTIONS);
  if (questionCount <= 0) {
    const components = await paperViewComponents();
    const pairs = pairPaperViewComponents(components);
    paperView = { components, pairs };
    receipt.structure.initial.paperView = { materials: components.materials.length, questions: components.questions.length, binding: 'component-index+vertical-alignment' };
    questionCount = Math.min(pairs.length, MAX_QUESTIONS);
  }
  if (questionCount <= 0) throw fail('QUESTION_TABS_MISSING', 'no question tabs/anchors observed');

  const captured = [];
  for (let question = 0; question < questionCount; question += 1) {
    let state;
    let strip = { anchors: [], materialTabs: 0 };
    let paneCount = 0;
    const panes = [];
    if (paperView) {
      state = await snapshotQuestionAt(question);
      if (!state.prompt) throw fail('PROMPT_MISSING', `paper-view component ${question + 1} has no .ti-content`);
      paneCount = 1;
      const body = await snapshotMaterialAt(question);
      if (!body) throw fail('MATERIAL_BODY_MISSING', `paper-view component ${question + 1} has no .material-body`);
      // 整卷视图没有页签文字，序号只能取组件顺序（第 i 个材料就是版面第 i 个组件）；
      // 因为标签缺失，declaredMaterialTabs 仍然是 null，不冒充「卷面声明了几个材料」。
      panes.push({ tabIndex: question, tabLabel: null, html: body.html, textLen: body.textLen, images: body.images, htmlSha: sha256(body.html) });
    } else {
      const questionClick = await clickTab('question', question);
      if (!questionClick.clicked) throw fail('QUESTION_TAB_NOT_FOUND', `question tab ${question + 1} not clickable`);
      receipt.clicks += 1;
      await settle(GAP);
      stopOnRisk();

      state = await snapshotQuestion();
      if (!state.prompt) throw fail('PROMPT_MISSING', `question ${question + 1} has no .ti-content`);
      strip = await structure();
      paneCount = Math.min(strip.materialTabs, 60);
      for (let pane = 0; pane < paneCount; pane += 1) {
        const click = await clickTab('material', pane);
        if (!click.clicked) { receipt.blocks.push({ question: question + 1, pane: pane + 1, reason: 'material-tab-not-clickable' }); continue; }
        receipt.clicks += 1;
        await settle(GAP);
        stopOnRisk();
        const body = await snapshotMaterial();
        if (!body) { receipt.blocks.push({ question: question + 1, pane: pane + 1, reason: 'material-body-missing' }); continue; }
        panes.push({
          tabIndex: pane, tabLabel: click.label, html: body.html, textLen: body.textLen,
          images: body.images, htmlSha: sha256(body.html),
        });
      }
    }
    captured.push({
      index: question + 1, keys: state.keys, anchorsVisible: strip.anchors,
      prompt: state.prompt, sections: state.sections, panes,
    });
    receipt.questions.push({
      index: question + 1, promptLen: state.prompt.textLen, materialTabs: paneCount,
      panesCaptured: panes.length, panes: panes.map((pane) => ({ tabNumber: pane.tabLabel, textLen: pane.textLen, images: pane.images })),
      sectionTitles: state.sections.map((section) => ({ len: section.title.length, textLen: section.textLen, images: section.images })),
    });
  }

  // ---- 合并 + 写盘 ----
  const merged = assembleMaterialPanes({
    questions: captured.map((question) => ({ index: question.index, panes: question.panes })),
  });
  receipt.panes = {
    observed: merged.evidence.paneObservations,
    distinct: merged.evidence.distinctPanes,
    declaredMaterialTabs: merged.evidence.declaredMaterialTabs,
    perQuestion: merged.evidence.perQuestionPanes,
    duplicatesWithinQuestion: merged.evidence.duplicateHashesWithinQuestion.length,
    empty: merged.evidence.emptyPanes,
    labelNumbering: merged.evidence.labelNumbering,
  };

  const domHtml = await page.content();
  await fs.mkdir(OUT, { recursive: true, mode: 0o700 });

  const questions = captured.map((question, position) => {
    const mergedQuestion = merged.questions[position];
    const answers = question.sections.filter((section) => /参考答案|参考作答|范文/u.test(section.title));
    const others = question.sections.filter((section) => !/参考答案|参考作答|范文/u.test(section.title));
    return {
      index: question.index,
      questionKey: question.keys[0] ?? null,
      anchorsVisible: question.anchorsVisible,
      prompt: { textLen: question.prompt.textLen, htmlSha: sha256(question.prompt.html), html: question.prompt.html },
      materialsThisQuestion: materialsThisQuestion(mergedQuestion.materialReferences),
      referenceAnswer: answers.map((section) => ({
        title: section.title, textLen: section.textLen, htmlSha: sha256(section.html), html: section.html, images: section.images,
      })),
      otherSections: others.map((section) => ({
        title: section.title, textLen: section.textLen, nonEmpty: section.textLen > section.title.length + 2, htmlSha: sha256(section.html),
      })),
    };
  });

  const capture = {
    schemaVersion: 2,
    subject: 'shenlun',
    cloudStorageBlocked: true,
    identity: {
      sourceId: SOURCE_ID,
      paperId: values['paper-id'] ? String(values['paper-id']) : SOURCE_ID,
      area: AREA, year: YEAR, variant: VARIANT,
      binding: (target.binding?.method === 'explicit-row-index+api-order'
        ? 'inventory sourceId + same-page list API ordered id + explicit row index + list row click + pinned DOM title hash'
        : 'inventory sourceId + list row click + pinned DOM title hash')
        + (values['paper-id'] ? '' : ' (paperId inherited from inventory; detail payload not retained)'),
      titleHash: titleHashFull.slice(0, 16), titleHashFull, titleLen: title.length,
      titleVerified: titleVerdict.verified, apiNameVerified: titleVerdict.apiNameVerified,
    },
    capturedAt: new Date().toISOString(),
    source: {
      entryKind: 'visible UI list row', listPage: target.page,
      detailPath: new URL(page.url()).pathname,
      observedAnchors: captured[0]?.anchorsVisible ?? [],
      questionsCaptured: questions.length,
      layout: paperView ? 'paper-view-per-question-components' : 'question-scoped-material-tab-strips',
      componentBinding: paperView ? { method: 'component-index+vertical-alignment', pairs: paperView.pairs } : null,
      materialPaneEvidence: {
        method: paperView
          ? 'one app-materials component per app-ti question component; .material-body snapshot in component order'
          : 'per-question material tab click -> .material-body snapshot',
        observed: merged.evidence.paneObservations,
        distinct: merged.evidence.distinctPanes,
        declaredMaterialTabs: merged.evidence.declaredMaterialTabs,
        perQuestion: merged.evidence.perQuestionPanes,
      },
    },
    completeness: {
      questionCountMatchesAnchors: Array.isArray(captured[0]?.anchorsVisible) && captured[0].anchorsVisible.length === questions.length,
      questionCountMatchesComponents: paperView ? paperView.pairs.length === questions.length : null,
    },
    materials: merged.materials.map((material) => ({
      index: material.index, textLen: material.textLen, htmlSha: material.htmlSha, html: material.html, images: material.images,
      tabNumbers: material.tabNumbers,
    })),
    questions,
    assets: [],
    imageCount: merged.materials.reduce((sum, material) => sum + (material.images ?? 0), 0)
      + questions.reduce((sum, question) => sum + question.referenceAnswer.reduce((count, entry) => count + entry.images, 0), 0),
    absent: {
      analysisText: 'not-assessed-here (PR108 parser classifies 解析/解析视频/考点/来源 separately)',
      analysisVideo: 'label-presence-only',
    },
    notes: [
      'material tab strips are question-scoped; union is deduplicated by htmlSha',
      'only panes actually clicked are stored; missing panes are reported as partial, never synthesised',
    ],
    rightsStatus: 'unverified',
  };

  const documentText = JSON.stringify(capture, null, 1) + '\n';
  await fs.writeFile(path.join(OUT, 'document.json'), documentText, { mode: 0o600 });
  await fs.writeFile(path.join(OUT, 'dom.html'), domHtml, { mode: 0o600 });

  const meta = {
    schemaVersion: 2, cloudStorageBlocked: true, sourceId: SOURCE_ID, paperId: capture.identity.paperId,
    area: AREA, year: YEAR, variant: VARIANT, titleHash: titleHashFull.slice(0, 16), titleHashFull, titleLen: title.length,
    titleVerified: titleVerdict.verified,
    documentSha: sha256(documentText), sourceSHA: sha256(domHtml), listPage: target.page,
    capturedAt: capture.capturedAt, rightsStatus: 'unverified', paneEvidence: receipt.panes,
  };
  await fs.writeFile(path.join(OUT, 'meta.json'), JSON.stringify(meta, null, 1) + '\n', { mode: 0o600 });

  // ---- 下游：PR108 parser + validator ----
  const { doc, diagnostics } = parseShenlunCapture({ capture, meta, domHtml });
  const verdict = await validateDocument(doc);
  const downstream = metadataReceipt(doc, verdict);
  receipt.downstream = downstream;
  receipt.guarded = { ...session.guardStats };
  receipt.status = receipt.blocks.length ? 'partial' : 'captured';
  await fs.writeFile(path.join(OUT, 'receipt.json'), JSON.stringify({ ...receipt, diagnostics: {
    storedMaterials: diagnostics.storedMaterials, materialTabs: diagnostics.materialTabs,
    analysis: diagnostics.analysis, missingQuestionNumbers: diagnostics.missingQuestionNumbers,
    unresolvedMaterialReferences: diagnostics.unresolvedMaterialReferences.length,
  } }, null, 1) + '\n', { mode: 0o600 });

  console.log(JSON.stringify({
    ok: true, status: receipt.status, listPage: target.page, titleCheck: receipt.titleCheck,
    clicks: receipt.clicks, structure: receipt.structure, panes: receipt.panes,
    questions: receipt.questions.map((question) => ({ q: question.index, promptLen: question.promptLen, panes: question.panesCaptured })),
    downstream: {
      status: downstream.validation?.status, issueCodes: downstream.validation?.issueCodes,
      materialPanesStored: downstream.materialPanesStored, materialTabsDeclared: downstream.materialTabsDeclared,
      questionCount: downstream.questionCount, answersPresent: downstream.answersPresent,
      explanationsPresent: downstream.explanationsPresent, analysis: downstream.analysis,
    },
    blocks: receipt.blocks, risk: receipt.risk,
  }, null, 1));
} catch (error) {
  receipt.status = 'failed';
  receipt.errors.push({ code: error.code ?? 'ERROR', message: String(error.message).slice(0, 300) });
  try {
    await fs.mkdir(OUT, { recursive: true, mode: 0o700 });
    await fs.writeFile(path.join(OUT, 'receipt.json'), JSON.stringify(receipt, null, 1) + '\n', { mode: 0o600 });
  } catch { /* 保留原始错误 */ }
  console.error(JSON.stringify({ ok: false, code: error.code ?? null, message: error.message, risk: receipt.risk, clicks: receipt.clicks }, null, 1));
  // 失败也要走 finally 关会话。以前这里直接 process.exit()，finally 不会执行，
  // 浏览器和 Profile 锁会留在原地，下一卷只能人工清锁。
  exitCode = error.code === 'RISK_SIGNAL' ? 3 : 2;
} finally {
  if (session) await session.close().catch(() => {});
}
process.exitCode = exitCode;
