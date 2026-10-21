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
//     --title-hash 0b3e1c9f86d4e5a2 --list-page 2 \
//     --out /path/to/private/capture
//
// 同一年有多卷（国考 2026 副省级/地市级/行政执法）时，清单行文本里没有 sourceId，
// 只能按行号显式绑定：--row-index N 配合 --list-page N，行号取自清单页按序枚举、
// 并与同页 API 项的等序编号对应；仍须通过年份/卷型标记与详情页标题哈希复核。
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
import { selectRowByIndex } from '../src/shenlun-list.mjs';
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
  console.log('usage: shenlun-capture-panes.mjs --area 浙江 --year 2020 --variant a --source-id 102033 --out DIR [--row-index N] [--title-hash HEX16] [--list-page N] [--gap-ms 2500]');
  process.exit(0);
}
for (const required of ['area', 'year', 'variant', 'source-id', 'out']) {
  if (!values[required]) { console.error(`missing-argument:--${required}`); process.exit(2); }
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

  let target = null;
  const wantedPage = values['list-page'] ? Number(values['list-page']) : null;
  const explicitRow = values['row-index'] !== undefined ? Number(values['row-index']) : null;
  if (explicitRow !== null) {
    // 同名年份/同一年有多卷（国考 副省级/地市级/行政执法）时，按行号显式绑定：
    // 行号来自清单页按序枚举 + 同页 API 项的等序绑定，仍需通过年份/卷型标记和标题哈希复核。
    const pageNumber = wantedPage ?? 1;
    if (pageNumber > 1 && !(await gotoPage(pageNumber))) throw fail('PAGER_FAILED', 'cannot open the requested list page');
    const picked = selectRowByIndex(await rowIndex(), { index: explicitRow, year: YEAR, variant: VARIANT });
    target = { page: pageNumber, index: picked.index, member: false, binding: picked.binding };
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

  // ---- 身份：DOM 标题对清单哈希 ----
  const title = await page.title();
  const titleHash = createHash('sha256').update(title, 'utf8').digest('hex').slice(0, 16);
  receipt.titleCheck = {
    source: 'dom-title', titleLen: title.length, titleHash,
    expectedTitleHash: values['title-hash'] ?? null, expectedTitleLen: values['title-len'] ? Number(values['title-len']) : null,
  };
  if (values['title-hash'] && values['title-hash'] !== titleHash) throw fail('TITLE_HASH_MISMATCH', 'live title does not match the inventory hash');
  if (values['title-len'] && Number(values['title-len']) !== title.length) throw fail('TITLE_LEN_MISMATCH', 'live title length does not match the inventory');

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

  const initial = await structure();
  receipt.structure = { initial: { materialTabs: initial.materialTabs, questionTabs: initial.questionTabs, anchors: initial.anchors.length } };
  if (!initial.materialBodyPresent) throw fail('MATERIAL_PANE_MISSING', 'detail page has no .material-body pane');
  const questionCount = Math.min(initial.questionTabs || initial.anchors.length, MAX_QUESTIONS);
  if (questionCount <= 0) throw fail('QUESTION_TABS_MISSING', 'no question tabs/anchors observed');

  const captured = [];
  for (let question = 0; question < questionCount; question += 1) {
    const questionClick = await clickTab('question', question);
    if (!questionClick.clicked) throw fail('QUESTION_TAB_NOT_FOUND', `question tab ${question + 1} not clickable`);
    receipt.clicks += 1;
    await settle(GAP);
    stopOnRisk();

    const state = await snapshotQuestion();
    if (!state.prompt) throw fail('PROMPT_MISSING', `question ${question + 1} has no .ti-content`);
    const strip = await structure();
    const paneCount = Math.min(strip.materialTabs, 60);
    const panes = [];
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
      binding: (values['paper-id']
        ? 'inventory sourceId + list row click + DOM title hash'
        : 'inventory sourceId + list row click + DOM title hash (paperId inherited from inventory; detail payload not retained)')
        + (target.binding?.method === 'explicit-row-index' ? ' + explicit row index' : ''),
      titleHash, titleLen: title.length,
    },
    capturedAt: new Date().toISOString(),
    source: {
      entryKind: 'visible UI list row', listPage: target.page,
      detailPath: new URL(page.url()).pathname,
      observedAnchors: captured[0]?.anchorsVisible ?? [],
      questionsCaptured: questions.length,
      materialPaneEvidence: {
        method: 'per-question material tab click -> .material-body snapshot',
        observed: merged.evidence.paneObservations,
        distinct: merged.evidence.distinctPanes,
        declaredMaterialTabs: merged.evidence.declaredMaterialTabs,
        perQuestion: merged.evidence.perQuestionPanes,
      },
    },
    completeness: { questionCountMatchesAnchors: Array.isArray(captured[0]?.anchorsVisible) && captured[0].anchorsVisible.length === questions.length },
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
    area: AREA, year: YEAR, variant: VARIANT, titleHash, titleLen: title.length,
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
  process.exit(error.code === 'RISK_SIGNAL' ? 3 : 2);
} finally {
  if (session) await session.close().catch(() => {});
}
