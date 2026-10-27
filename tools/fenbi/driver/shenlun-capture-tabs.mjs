#!/usr/bin/env node
// 申论多标签页只读补采（批次驱动 + 单浏览器 N 个 Page）。
//
// 为什么要有这个文件：现有链路 shenlun-batch.mjs 逐卷 spawn shenlun-capture-panes.mjs，
// 每卷都要 launchPersistentContext 一次、再走一遍列表页，约 3 分钟/卷。真正的瓶颈是
// 「每卷新开会话」，不是等待本身。本驱动只调用一次 openSession(config, capture)，
// 在同一个 persistent context 里开 N 个 Page 作为标签页池，每卷在独立 Page 上跑完与
// shenlun-capture-panes.mjs 完全相同的采集流程。
//
// 复用 / 复制边界（改代码时必须知道哪边是权威）：
//   * 浏览器与请求守卫（openSession / capture 模式）、配置加载、列表 API 归一化、
//     显式行号绑定、标题哈希核对、材料 pane 合并、文档解析与校验，全部 import 现有
//     src/*.mjs 的纯函数，不复制实现；
//   * shenlun-capture-panes.mjs 里与单个 page 绑定的部分（列表定位、分页、行点击、
//     身份核对、材料页签逐格快照、document/meta/receipt 组装）原样复制进本文件的
//     capturePaper()。复制是为了让逐卷输出的文件名与 JSON 字段逐项同构；这些 DOM
//     常量或选择器如果站点改版，两个文件必须同步修改。
//
// 只读：openSession(capture) 会 abort 一切非 GET/HEAD/OPTIONS 请求；不 init 练习、
// 不交卷、不购买。任何一个 Page 看到 401/403/429/503 就置全局 halted，正在等待的
// sleep 由 AbortSignal 打断，正在跑的 Playwright 调用由 Promise.race 抢断，调度器
// 不再派新卷，整个批次以退出码 3 结束，不重试。
//
// 身份证据不放松：仍然要求「同一页列表 API 的有序 id 数组」+「显式行号」
// （apiIds[rowIndex] === sourceId）+「列表 API 名称哈希」+「详情页 DOM 全标题哈希」+
// 「标题长度」。任一项观察不到或对不上都 FAIL CLOSED，不会退化成按年份猜行。
//
// 用法：
//   DISPLAY=:77 node tools/fenbi/driver/shenlun-capture-tabs.mjs \
//     --candidates work/fenbi/shenlun-candidates.json \
//     --out-root /home/fjd/tmp/shenlun-capture-tabs-20261027 \
//     [--tabs 4] [--concurrency 4] [--areas 天津,甘肃] [--limit 5] \
//     [--gap-ms 2500] [--stagger-ms 1000] [--scan-gap-ms 30000] [--dry-run]
//
// 输出：
//   <out-root>/<id>/document.json|dom.html|meta.json|receipt.json
//     —— 逐卷结构与 shenlun-capture-panes.mjs 完全一致，worker/land-shenlun.mjs 不用改；
//   <out-root>/batch-tabs-<timestamp>.json
//     —— 批次回执，字段结构照 shenlun-batch.mjs 的 receipt。
//
// 并发口径：
//   --tabs        在同一个 context 里打开的 Page 数（默认 4，允许 1..6）；
//   --concurrency 同时在飞的卷数（默认 4，允许 1..--tabs）。多开的 Page 保持空闲，
//                 作为固定标签页池；不会额外开浏览器会话。
//   注意：src/schedule.mjs 的 MAX_CONCURRENCY=3 是通用流水线调度器的上限，和本驱动的
//   --tabs 不是同一层概念；这里按操作者显式参数执行。超过 3 个标签页属于未验证的
//   风控区间，先用 3 卷小样本做等价性验证（步骤见交付说明）。
//
//   inventory 缺失时，本驱动会在打开采集会话之前串行 spawn shenlun-inventory-scan.mjs
//   （每个地区一次短暂的独立浏览器会话）。所有扫描结束后才 openSession，二者绝不重叠，
//   因此全程仍然只有一个 persistent profile 在同一时刻被一个进程持有。
//
// 退出码：0 处理完（含跳过/单卷失败）；3 风控中止；2 参数错误；1 其他错误。

import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
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

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../../..');
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(REPO, 'work/fenbi'));
const ENTRY = 'https://www.fenbi.com/spa/tiku/guide/shenlunList/shenlun/1000';
const MAX_QUESTIONS = 30;
const DEFAULT_TABS = 4;
const MAX_TABS = 6;
const DEFAULT_CONCURRENCY = 4;

function fail(code, message, extra = {}) {
  const error = new Error(message);
  error.code = code;
  Object.assign(error, extra);
  return error;
}

const { values } = parseArgs({
  allowPositionals: false,
  options: {
    candidates: { type: 'string' }, 'out-root': { type: 'string' },
    'inventory-dir': { type: 'string' }, areas: { type: 'string' },
    limit: { type: 'string' }, 'gap-ms': { type: 'string' }, 'scan-gap-ms': { type: 'string' },
    tabs: { type: 'string' }, concurrency: { type: 'string' }, 'stagger-ms': { type: 'string' },
    'work-dir': { type: 'string' }, 'dry-run': { type: 'boolean' }, help: { type: 'boolean' },
  },
});

if (values.help) {
  console.log('usage: shenlun-capture-tabs.mjs --candidates FILE --out-root DIR [--tabs 4] [--concurrency 4] [--areas A,B] [--limit 5] [--gap-ms 2500] [--stagger-ms 1000] [--scan-gap-ms 30000] [--dry-run]');
  process.exit(0);
}
for (const required of ['candidates', 'out-root']) {
  if (!values[required]) { console.error(`missing-argument:--${required}`); process.exit(2); }
}

// 参数越界直接拒绝，而不是静默夹到边界：操作者必须知道实际会开几个标签页。
function intInRange(label, raw, fallback, min, max) {
  if (raw === undefined) return fallback;
  const number = Number(raw);
  if (!Number.isInteger(number) || number < min || number > max) {
    console.error(`invalid-argument:--${label} (integer ${min}..${max})`);
    process.exit(2);
  }
  return number;
}

const CANDIDATES = path.resolve(values.candidates);
const OUT_ROOT = path.resolve(values['out-root']);
const WORK_DIR = values['work-dir'] ? path.resolve(values['work-dir']) : WORK;
// 卷内页签点击节奏：与 shenlun-capture-panes.mjs 的 GAP 完全一致（下限 2500ms）。
const GAP = intInRange('gap-ms', values['gap-ms'], 2500, 2500, 60000);
// 列表扫描是独立浏览器会话，节奏单独给，默认沿用 shenlun-batch.mjs 的 30s。
const SCAN_GAP = intInRange('scan-gap-ms', values['scan-gap-ms'], 30000, 2500, 600000);
const TABS = intInRange('tabs', values.tabs, DEFAULT_TABS, 1, MAX_TABS);
const CONCURRENCY = intInRange('concurrency', values.concurrency, Math.min(DEFAULT_CONCURRENCY, TABS), 1, TABS);
// 各标签页首次列表导航的错峰间隔。同一账号同时打同一个列表接口是最像脚本的模式，
// 错峰不改变单卷内部的任何等待，只是把 4 个首屏请求摊开。
const STAGGER_MS = intInRange('stagger-ms', values['stagger-ms'], 1000, 0, 30000);
const LIMIT = intInRange('limit', values.limit, 5, 1, 100000);
const DRY = Boolean(values['dry-run']);
const inventoryDir = path.resolve(values['inventory-dir'] || path.join(WORK_DIR, 'shenlun-inventory'));

// 采集产物只能落在仓库外；work-dir 是持久化 profile/清单目录，也不能混入采集正文。
for (const [label, root] of [['repo', REPO], ['work-dir', WORK_DIR]]) {
  if (OUT_ROOT === root || OUT_ROOT.startsWith(root + path.sep)) {
    console.error(`refusing-out-root-inside-${label}`);
    process.exit(2);
  }
}

const run = (command, args, extraEnv = {}) => new Promise((resolve, reject) => {
  const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, ...extraEnv } });
  let stdout = '', stderr = '';
  child.stdout.on('data', (chunk) => { stdout += chunk; });
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  child.on('error', reject);
  child.on('close', (code) => resolve({ code, stdout, stderr }));
});

const validTitleHash = (value) => /^[0-9a-f]{12,64}$/u.test(String(value).toLowerCase());

// ---------------------------------------------------------------------------
// 全局风控闸门。所有 Page 共享同一个 halted 标志：第一个 401/403/429/503 就把
// 整个批次钉死，之后的每次等待/调度都从这里拿到同一个 RISK_SIGNAL。
// ---------------------------------------------------------------------------
const shared = {
  halted: false,
  reason: null,
  risk: { unauthorized: 0, rateLimited: 0 },
};
const haltController = new AbortController();
let rejectHalt;
const haltRace = new Promise((_, reject) => { rejectHalt = reject; });
// 没有任务在 race 时这个 promise 也会 reject；先挂一个 handler，避免 unhandled rejection。
haltRace.catch(() => {});

function riskError(status) {
  return fail('RISK_SIGNAL', `risk status observed (${status ?? 'unknown'}); stopping without retry`, {
    risk: { ...shared.risk },
  });
}

function haltForRisk(job, status) {
  if (shared.halted) return;
  shared.halted = true;
  shared.reason = { status, area: job.area, id: job.sourceId };
  haltController.abort();
  rejectHalt(riskError(status));
}

function checkHalt() {
  if (shared.halted) throw riskError(shared.reason?.status);
}

async function pauseUnlessHalted(ms) {
  if (shared.halted) return;
  try {
    await sleep(ms, undefined, { signal: haltController.signal });
  } catch (error) {
    if (shared.halted) return;
    throw error;
  }
}

// ---------------------------------------------------------------------------
// 单卷采集：从 shenlun-capture-panes.mjs 复制并按 page 参数化。
//
// 复制时只改了四类东西：
//   1. CLI 常量（AREA/YEAR/VARIANT/SOURCE_ID/OUT）改为 job 字段；
//   2. 每个 page.on('response') 监听器在卷结束后用 page.off 摘掉，避免复用 Page 时
//      把上一卷的风险计数/列表 API 带进下一卷；
//   3. sleep 改为可被 AbortSignal 打断的 pause，goto/waitForLoadState/content 用
//      Promise.race 抢断，保证任一卷看到风控后其它卷立即收手；
//   4. 四个输出文件在全部校验通过后才落盘（document.json 最后写），避免中途失败
//      留下「有 document.json 但没有完整回执」的目录，被下一次 --out-root 去重误跳过。
// DOM 选择器、等待时长、点击顺序一律未改。
// ---------------------------------------------------------------------------
async function capturePaper({ page, job, session, gap }) {
  const AREA = job.area;
  const YEAR = job.year;
  const VARIANT = job.variant;
  const SOURCE_ID = job.sourceId;
  const OUT = job.out;

  const receipt = {
    at: new Date().toISOString(), sourceId: SOURCE_ID, area: AREA, year: YEAR, variant: VARIANT,
    status: 'running', navigations: 1, clicks: 0, guarded: null, risk: { unauthorized: 0, rateLimited: 0 },
    titleCheck: null, structure: null, questions: [], panes: null, blocks: [], errors: [],
  };

  // 同页真实列表 API 的有序 id 数组。只留内存：名称仅用于计算标题哈希，绝不写盘。
  // 观察不到就 FAIL CLOSED，绝不按行号硬猜。
  const listApiResponses = [];
  let listApiSeq = 0;

  // 卷内等待：中止时抛 RISK_SIGNAL，而不是继续等到超时。
  const pause = async (ms) => {
    checkHalt();
    try {
      await sleep(ms, undefined, { signal: haltController.signal });
    } catch (error) {
      if (shared.halted) throw riskError(shared.reason?.status);
      throw error;
    }
    checkHalt();
  };
  const abortable = (promise) => {
    // 这些 promise 在调用 abortable 之前就已经创建；先挂一个 handler，
    // 避免 checkHalt() 同步抛出时把原 promise 的 rejection 留成 unhandled。
    promise?.catch?.(() => {});
    checkHalt();
    return Promise.race([promise, haltRace]);
  };
  // 所有 DOM 读取都走这里：page.evaluate 可能因页面忙碌而卡住，风控到达时由 race 抢断。
  const evaluate = (pageFunction, arg) => abortable(page.evaluate(pageFunction, arg));

  const onRisk = (response) => {
    const status = response.status();
    let riskStatus = null;
    if (status === 401 || status === 403) {
      receipt.risk.unauthorized += 1; shared.risk.unauthorized += 1; riskStatus = status;
    }
    if (status === 429 || status === 503) {
      receipt.risk.rateLimited += 1; shared.risk.rateLimited += 1; riskStatus = status;
    }
    if (riskStatus !== null) haltForRisk(job, riskStatus);
  };

  const onListApi = (response) => {
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
  };

  let attached = false;
  try {
    page.on('response', onRisk);
    attached = true;
    page.on('response', onListApi);

    const settle = async (ms = 2500) => {
      await pause(ms);
      // 原脚本在 sleep 之后等 networkidle；这里保留同样的节奏，只是可被风控抢断。
      await abortable(page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}));
    };
    const stopOnRisk = () => {
      checkHalt();
      if (receipt.risk.unauthorized || receipt.risk.rateLimited) {
        throw fail('RISK_SIGNAL', 'unauthorized-or-rate-limited response observed; stopping without retry', { risk: receipt.risk });
      }
    };

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
        await pause(250);
      }
      throw fail('LIST_API_UNOBSERVED', `no list API response observed for page ${pageNumber}`);
    };

    // ---- 列表：只读定位目标行 ----
    await abortable(page.goto(ENTRY, { waitUntil: 'domcontentloaded', timeout: 45000 }));
    await settle(3500);
    const regionClicked = await evaluate((region) => {
      const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
      const el = [...document.querySelectorAll('.category1-btn')].find((x) => norm(x.innerText) === region);
      if (!el || el.offsetParent === null) return false;
      el.click(); return true;
    }, AREA);
    if (!regionClicked) throw fail('REGION_NOT_FOUND', 'region button not visible');
    receipt.clicks += 1;
    await settle(3000);
    stopOnRisk();

    const readListRows = () => evaluate(() => {
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
      const ok = await evaluate((target) => {
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
    const pagerVisible = () => evaluate(() => [...document.querySelectorAll('div.paging div.item')]
      .map((el) => Number(String(el.innerText).trim()))
      .filter((value) => Number.isInteger(value) && value > 0));

    // 批次驱动只走「显式行号」这一条路径：候选清单里每卷都带着 inventory 的
    // page/index，而 year+variant 搜索拿不到「同页 API 有序 id」这一重证据。
    // 少一条证据就不是等价采集，所以这里不实现那条退化路径。
    const pageNumber = job.listPage;
    if (!Number.isInteger(pageNumber) || pageNumber < 1) {
      throw fail('LIST_PAGE_INVALID', 'list page must be a positive integer');
    }
    const mark = listApiMark();
    if (pageNumber > 1 && !(await gotoPage(pageNumber))) throw fail('PAGER_FAILED', 'cannot open the requested list page');
    // 观察不到同页列表 API 就停在这里：不点行、不写 source 文档。
    const api = await waitForListApi(pageNumber, pageNumber > 1 ? mark : 0);
    const pager = await pagerVisible();
    const picked = bindRowToApi(await readListRows(), api, {
      index: job.rowIndex, sourceId: SOURCE_ID, page: pageNumber,
      year: YEAR, variant: VARIANT,
    });
    // 点开之前先用同页 API 的名称哈希核对一次固定的标题哈希：
    // 名字对不上就停在这里，连详情页都不进。
    const boundName = api.names[picked.index];
    if (typeof boundName !== 'string' || boundName.length === 0) {
      throw fail('TITLE_API_NAME_UNHASHABLE', 'bound list API item has no name to hash');
    }
    verifyTitleHash({
      observedHash: createHash('sha256').update(boundName, 'utf8').digest('hex'),
      expectedHash: job.titleHash,
    });
    receipt.pagerVisible = pager;
    const target = { page: pageNumber, index: picked.index, member: false, binding: picked.binding };
    const boundApi = api;

    receipt.listPage = target.page;
    receipt.rowBinding = target.binding;
    if (boundApi) {
      receipt.listApi = {
        page: boundApi.page, totalPage: boundApi.totalPage, totalItem: boundApi.totalItem,
        itemCount: boundApi.itemCount, idsSha256: sha256(boundApi.ids.join(',')), sourcePath: boundApi.sourcePath,
      };
    }

    await evaluate((index) => {
      const rows = [...document.querySelectorAll('li.list-item-container')];
      const row = rows[index];
      if (!row) return false;
      (row.querySelector('.list-item-title') || row).click();
      return true;
    }, target.index);
    receipt.clicks += 1;
    await settle(6000);
    stopOnRisk();

    // ---- 身份：DOM 全标题哈希必须命中事先固定的 title-hash ----
    const title = await abortable(page.title());
    const titleHashFull = createHash('sha256').update(title, 'utf8').digest('hex');
    const apiName = boundApi?.names?.[target.index];
    const apiNameHash = typeof apiName === 'string' && apiName.length
      ? createHash('sha256').update(apiName, 'utf8').digest('hex') : null;
    // 行号绑定模式下，列表 API 的该项名称也必须可用于身份核对；缺失即拒绝。
    if (boundApi && apiNameHash === null) throw fail('TITLE_API_NAME_UNHASHABLE', 'bound list API item has no name to hash');
    // 批次路径的 title-len 来自 inventory，永远是「有值才可核对」的硬条件。
    // 缺失时不能用 null 跳过长度检查（那会弱化身份），规划阶段已经拒绝这种卷。
    const expectedTitleLen = Number(job.titleLen);
    const titleVerdict = verifyTitleHash({
      observedHash: titleHashFull, observedLen: title.length,
      expectedHash: job.titleHash, expectedLen: expectedTitleLen, apiNameHash,
    });
    receipt.titleCheck = {
      source: 'dom-title + pinned hash', titleLen: title.length,
      titleHash: titleHashFull.slice(0, 16), titleHashFull,
      expectedTitleHash: job.titleHash, expectedTitleLen,
      verified: titleVerdict.verified, apiNameVerified: titleVerdict.apiNameVerified,
      apiNamePresent: apiNameHash !== null,
    };

    // ---- 页签结构（只返回 kind/count，不返回正文） ----
    const structure = () => evaluate(() => {
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

    const clickTab = (kind, index) => evaluate(({ kind, index }) => {
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

    const snapshotQuestion = () => evaluate(() => {
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

    const snapshotMaterial = () => evaluate(() => {
      const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
      const body = document.querySelector('.material-body');
      if (!body) return null;
      return { textLen: norm(body.innerText).length, html: body.innerHTML, images: body.querySelectorAll('img').length };
    });

    // 整卷视图：没有页签条，每道题一个 app-ti，旁边一个 app-materials，按文档顺序平铺。
    // 只在左右组件数量相等、各自唯一、且纵坐标同序时才算配对成功。
    const paperViewComponents = () => evaluate(() => {
      const apps = [...document.querySelectorAll('app-materials')];
      const tis = [...document.querySelectorAll('app-ti')];
      return {
        materials: apps.map((app) => ({ top: app.getBoundingClientRect().top, bodies: app.querySelectorAll('.material-body').length })),
        questions: tis.map((ti) => ({ top: ti.getBoundingClientRect().top, contents: ti.querySelectorAll('.ti-content').length })),
      };
    });
    const snapshotQuestionAt = (index) => evaluate((i) => {
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
    const snapshotMaterialAt = (index) => evaluate((i) => {
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
    // 有材料页签条、却没有题目页签条：页面是「单题 + 若干材料页签」。这道题本来就在屏上，
    // 不需要（也没有）题目页签可点，只要逐个点材料页签即可。若按整卷视图处理，
    // 只会截到当前激活的那一个材料页签，其余页签全部漏采（广州 2015：声明 8 个材料只存下 1 个）。
    let paneOnlyQuestion = false;
    if (questionCount <= 0 && initial.materialTabs > 0) { questionCount = 1; paneOnlyQuestion = true; }
    if (questionCount <= 0) {
      const components = await paperViewComponents();
      const pairs = pairPaperViewComponents(components);
      paperView = { components, pairs };
      receipt.structure.initial.paperView = { materials: components.materials.length, questions: components.questions.length, binding: 'component-index+vertical-alignment' };
      questionCount = Math.min(pairs.length, MAX_QUESTIONS);
    }
    if (paneOnlyQuestion) {
      // 没有题号页签可点，题数只能按页面实际渲染的 app-ti 组件数记；材料数同理。
      const components = await paperViewComponents();
      receipt.structure.initial.paneOnlyQuestion = {
        questionComponents: components.questions.length,
        materialComponents: components.materials.length,
        materialTabs: initial.materialTabs,
      };
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
        // 材料总数按页面实际渲染的 app-materials 组件数记录（见 materialPaneEvidence）。
        panes.push({ tabIndex: question, tabLabel: null, html: body.html, textLen: body.textLen, images: body.images, htmlSha: sha256(body.html) });
      } else {
        if (!paneOnlyQuestion) {
          const questionClick = await clickTab('question', question);
          if (!questionClick.clicked) throw fail('QUESTION_TAB_NOT_FOUND', `question tab ${question + 1} not clickable`);
          receipt.clicks += 1;
          await settle(gap);
          stopOnRisk();
        }

        state = await snapshotQuestion();
        if (!state.prompt) throw fail('PROMPT_MISSING', `question ${question + 1} has no .ti-content`);
        strip = await structure();
        paneCount = Math.min(strip.materialTabs, 60);
        for (let pane = 0; pane < paneCount; pane += 1) {
          const click = await clickTab('material', pane);
          if (!click.clicked) { receipt.blocks.push({ question: question + 1, pane: pane + 1, reason: 'material-tab-not-clickable' }); continue; }
          receipt.clicks += 1;
          await settle(gap);
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

    // 合并 + 组装。风控可能在最后一题之后才到达，落盘前再确认一次。
    checkHalt();
    const merged = assembleMaterialPanes({
      questions: captured.map((question) => ({ index: question.index, panes: question.panes })),
    });
    receipt.panes = {
      observed: merged.evidence.paneObservations,
      distinct: merged.evidence.distinctPanes,
      declaredMaterialTabs: paperView ? paperView.components.materials.length : merged.evidence.declaredMaterialTabs,
      perQuestion: merged.evidence.perQuestionPanes,
      duplicatesWithinQuestion: merged.evidence.duplicateHashesWithinQuestion.length,
      empty: merged.evidence.emptyPanes,
      labelNumbering: merged.evidence.labelNumbering,
    };

    const domHtml = await abortable(page.content());

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
        // 与 shenlun-capture-panes.mjs 的 questions[] 保持同构：otherSections 只留标题/长度/哈希，
        // 解析正文另开显式字段，且只挑标题明确可辨的区块，避免把导航条当解析。
        analysisSections: others
          .filter((section) => /解析|文章分析|范文分析|参考作答说明|参考答案说明/u.test(section.title))
          .map((section) => ({
            title: section.title, textLen: section.textLen, htmlSha: sha256(section.html), html: section.html,
          })),
      };
    });

    const capture = {
      schemaVersion: 2,
      subject: 'shenlun',
      cloudStorageBlocked: true,
      identity: {
        sourceId: SOURCE_ID,
        paperId: job.paperId ? String(job.paperId) : SOURCE_ID,
        area: AREA, year: YEAR, variant: VARIANT,
        binding: (target.binding?.method === 'explicit-row-index+api-order'
          ? 'inventory sourceId + same-page list API ordered id + explicit row index + list row click + pinned DOM title hash'
          : 'inventory sourceId + list row click + pinned DOM title hash')
          + (job.paperId ? '' : ' (paperId inherited from inventory; detail payload not retained)'),
        titleHash: titleHashFull.slice(0, 16), titleHashFull, titleLen: title.length,
        titleVerified: titleVerdict.verified, apiNameVerified: titleVerdict.apiNameVerified,
      },
      capturedAt: new Date().toISOString(),
      source: {
        entryKind: 'visible UI list row', listPage: target.page,
        detailPath: new URL(page.url()).pathname,
        observedAnchors: captured[0]?.anchorsVisible ?? [],
        questionsCaptured: questions.length,
        layout: paperView ? 'paper-view-per-question-components'
          : paneOnlyQuestion ? 'single-question-material-tab-strips' : 'question-scoped-material-tab-strips',
        componentBinding: paperView ? { method: 'component-index+vertical-alignment', pairs: paperView.pairs } : null,
        materialPaneEvidence: {
          method: paperView
            ? 'one app-materials component per app-ti question component; .material-body snapshot in component order; declared count is the number of material components rendered on the page (no tab labels to read)'
            : paneOnlyQuestion
              ? 'single question already rendered with no question tab strip; per-material tab click -> .material-body snapshot'
              : 'per-question material tab click -> .material-body snapshot',
          observed: merged.evidence.paneObservations,
          distinct: merged.evidence.distinctPanes,
          // 整卷视图没有「材料N」页签，材料数只能取版面实际渲染的 app-materials 组件数：
          // 这是可观测事实（页面确实渲染了 N 个材料块），不是用「已存数量」冒充声明。
          // 写成 null 会让校验器判 material-count-unknown，整卷卷永远入不了库。
          declaredMaterialTabs: paperView ? paperView.components.materials.length : merged.evidence.declaredMaterialTabs,
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

    const meta = {
      schemaVersion: 2, cloudStorageBlocked: true, sourceId: SOURCE_ID, paperId: capture.identity.paperId,
      area: AREA, year: YEAR, variant: VARIANT, titleHash: titleHashFull.slice(0, 16), titleHashFull, titleLen: title.length,
      titleVerified: titleVerdict.verified,
      documentSha: sha256(documentText), sourceSHA: sha256(domHtml), listPage: target.page,
      capturedAt: capture.capturedAt, rightsStatus: 'unverified', paneEvidence: receipt.panes,
    };

    // ---- 下游：PR108 parser + validator ----
    // 先跑纯函数校验，再落盘；风控到达时宁可这一卷整体不出，也不留下半套文件。
    const { doc, diagnostics } = parseShenlunCapture({ capture, meta, domHtml });
    const verdict = await validateDocument(doc);
    checkHalt();
    const downstream = metadataReceipt(doc, verdict);
    receipt.downstream = downstream;
    receipt.guarded = { ...session.guardStats };
    receipt.status = receipt.blocks.length ? 'partial' : 'captured';

    await fs.mkdir(OUT, { recursive: true, mode: 0o700 });
    // document.json 最后写：下一次 --out-root 去重只看它，先写会让半套目录被误判为已采集。
    await fs.writeFile(path.join(OUT, 'dom.html'), domHtml, { mode: 0o600 });
    await fs.writeFile(path.join(OUT, 'meta.json'), JSON.stringify(meta, null, 1) + '\n', { mode: 0o600 });
    await fs.writeFile(path.join(OUT, 'receipt.json'), JSON.stringify({ ...receipt, diagnostics: {
      storedMaterials: diagnostics.storedMaterials, materialTabs: diagnostics.materialTabs,
      analysis: diagnostics.analysis, missingQuestionNumbers: diagnostics.missingQuestionNumbers,
      unresolvedMaterialReferences: diagnostics.unresolvedMaterialReferences.length,
    } }, null, 1) + '\n', { mode: 0o600 });
    await fs.writeFile(path.join(OUT, 'document.json'), documentText, { mode: 0o600 });

    const summary = JSON.stringify({
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
    }, null, 1);

    return { code: 0, receipt, summary };
  } catch (error) {
    receipt.status = 'failed';
    receipt.errors.push({ code: error.code ?? 'ERROR', message: String(error.message).slice(0, 300) });
    try {
      await fs.mkdir(OUT, { recursive: true, mode: 0o700 });
      await fs.writeFile(path.join(OUT, 'receipt.json'), JSON.stringify(receipt, null, 1) + '\n', { mode: 0o600 });
    } catch { /* 保留原始错误 */ }
    const summary = JSON.stringify({
      ok: false, code: error.code ?? null, message: String(error.message).slice(0, 200),
      risk: receipt.risk, clicks: receipt.clicks,
    });
    return { code: error.code === 'RISK_SIGNAL' ? 3 : 2, receipt, summary };
  } finally {
    // 复用 Page 时必须摘掉监听器：否则上一卷的 onRisk 会把响应计进已经结束的 receipt，
    // onListApi 也会把旧列表快照塞进下一卷的候选集。
    if (attached) {
      try { page.off('response', onRisk); } catch { /* Page 已关闭 */ }
      try { page.off('response', onListApi); } catch { /* Page 已关闭 */ }
    }
  }
}

// ---------------------------------------------------------------------------
// 固定 Page 池。每个 worker 绑定一个 Page，按 cursor 领卷；风控后不再领新卷。
// ---------------------------------------------------------------------------
async function runPool({ pages, jobs, session, onResult }) {
  const results = new Array(jobs.length);
  let cursor = 0;
  const workers = pages.slice(0, Math.min(CONCURRENCY, pages.length)).map(async (initialPage, workerIndex) => {
    let page = initialPage;
    // 首屏错峰：只影响各 Page 第一次列表导航的起点，不改变任何单卷内部节奏。
    if (workerIndex > 0) await pauseUnlessHalted(workerIndex * STAGGER_MS);
    while (!shared.halted) {
      if (page.isClosed()) {
        try { page = await session.context.newPage(); } catch { return; }
      }
      const slot = cursor;
      if (slot >= jobs.length) return;
      cursor += 1;
      const job = jobs[slot];
      let result;
      try {
        result = await capturePaper({ page, job, session, gap: GAP });
      } catch (error) {
        // capturePaper 自己会兜住所有错误；这里只是最后一层保险，避免一个 bug 拖垮整批。
        result = {
          code: error.code === 'RISK_SIGNAL' ? 3 : 2,
          receipt: { status: 'failed', errors: [{ code: error.code ?? 'ERROR', message: String(error.message).slice(0, 300) }] },
          summary: JSON.stringify({ ok: false, code: error.code ?? null, message: String(error.message).slice(0, 200) }),
        };
      }
      results[slot] = result;
      // 卷级进度只打印身份与状态，不打印任何 URL / 标题 / Cookie。
      console.log(JSON.stringify({
        event: 'paper', area: job.area, id: job.sourceId, page: workerIndex, code: result.code,
        status: result.receipt?.status ?? null,
        validation: result.receipt?.downstream?.validation?.status ?? null,
      }));
      if (onResult) onResult(job, result);
      if (result.code === 3) return;
    }
  });
  await Promise.all(workers);
  return results;
}

// ---------------------------------------------------------------------------
// 批次规划：完全照 shenlun-batch.mjs 的「分组 → 排序 → 跳过已采集 → 跳过无哈希/
// 会员/清单陈旧」口径。差别只有一处：所有需要的 inventory 扫描必须在打开浏览器
// 之前串行跑完。扫描本身也是一个浏览器进程，绝不能和主会话同时占用同一个 profile。
// ---------------------------------------------------------------------------
const receipt = {
  at: new Date().toISOString(), candidates: CANDIDATES, outRoot: OUT_ROOT, dryRun: DRY,
  gapMs: GAP, limit: LIMIT, tabs: TABS, concurrency: CONCURRENCY, staggerMs: STAGGER_MS,
  areas: [], captured: [], skipped: [], failed: [], aborted: null,
};

let exitCode = 0;
let session = null;
let pagesOpened = 0;

// 批次回执路径在开跑时就固定：每卷结束刷新同一个文件，进程中途被杀也能看到已完成部分。
const outFile = path.join(OUT_ROOT, `batch-tabs-${new Date().toISOString().replace(/[:.]/gu, '-')}.json`);
let receiptWrite = Promise.resolve();
function persistReceipt() {
  // 串行化写入：多个 worker 同时完成时，不允许互相覆盖或产生半截 JSON。
  receiptWrite = receiptWrite.then(async () => {
    await fs.mkdir(OUT_ROOT, { recursive: true, mode: 0o700 });
    await fs.writeFile(outFile, `${JSON.stringify({
      ...receipt,
      pagesOpened,
      risk: { ...shared.risk },
      guarded: session ? { ...session.guardStats } : null,
      updatedAt: new Date().toISOString(),
    }, null, 2)}\n`, { mode: 0o600 });
  }).catch((error) => {
    receipt.errors = [...(receipt.errors ?? []), { code: 'RECEIPT_WRITE_FAILED', message: String(error.message).slice(0, 200) }];
  });
  return receiptWrite;
}

try {
  const candidateList = JSON.parse(await fs.readFile(CANDIDATES, 'utf8'));
  const candidates = (candidateList.candidates ?? candidateList).filter((c) => c.subject === 'shenlun' || !c.subject);
  const areasWanted = values.areas ? new Set(String(values.areas).split(',').map((a) => a.trim()).filter(Boolean)) : null;
  const grouped = new Map();
  for (const candidate of candidates) {
    if (areasWanted && !areasWanted.has(candidate.area)) continue;
    if (!grouped.has(candidate.area)) grouped.set(candidate.area, []);
    grouped.get(candidate.area).push(candidate);
  }
  for (const list of grouped.values()) list.sort((a, b) => (a.year - b.year) || String(a.variant).localeCompare(String(b.variant)));

  const already = new Set();
  try {
    for (const entry of await fs.readdir(OUT_ROOT)) {
      if (await fs.access(path.join(OUT_ROOT, entry, 'document.json')).then(() => true, () => false)) already.add(entry);
    }
  } catch { /* 输出目录还不存在 */ }

  const jobs = [];

  outer:
  for (const [area, list] of grouped) {
    const areaReceipt = { area, candidates: list.length, inventory: null, scanned: false };
    receipt.areas.push(areaReceipt);
    const pending = list.filter((c) => !already.has(String(c.id)));
    if (!pending.length) { areaReceipt.note = 'all-already-captured'; continue; }
    if (jobs.length >= LIMIT) break;

    const inventoryFile = path.join(inventoryDir, `inventory-${area}.json`);
    let inventory;
    try {
      inventory = JSON.parse(await fs.readFile(inventoryFile, 'utf8'));
      if (inventory.status !== 'ok') throw new Error('inventory not ok');
    } catch {
      if (DRY) { areaReceipt.note = 'would-scan'; continue; }
      // 扫描是独立浏览器会话；主会话此时还没开，profile 不会被并发占用。
      const scan = await run(process.execPath, [path.join(HERE, 'shenlun-inventory-scan.mjs'),
        '--area', area, '--out', inventoryFile, '--work-dir', WORK_DIR, '--gap-ms', String(SCAN_GAP)]);
      areaReceipt.scanned = true;
      areaReceipt.scanExit = scan.code;
      areaReceipt.scanSummary = scan.stdout.trim().split('\n').pop();
      if (scan.code === 3) { receipt.aborted = { step: 'scan', area, code: 3 }; exitCode = 3; break outer; }
      if (scan.code !== 0) { receipt.failed.push({ area, step: 'scan', code: scan.code, detail: scan.stderr.trim().slice(-400) }); continue; }
      inventory = JSON.parse(await fs.readFile(inventoryFile, 'utf8'));
    }
    areaReceipt.inventory = { pages: inventory.pagesRead, items: (inventory.items || []).length, truncated: Boolean(inventory.truncated) };
    const byId = new Map((inventory.items || []).map((item) => [String(item.sourceId), item]));

    for (const candidate of pending) {
      if (jobs.length >= LIMIT) break;
      const id = String(candidate.id);
      const hit = byId.get(id);
      // 跳过理由与 shenlun-batch.mjs 保持同字面，方便两套回执直接比对。
      if (!hit || !hit.titleHash) { receipt.skipped.push({ area, id, reason: 'no-title-hash' }); continue; }
      if (hit.lockStatus !== 0) { receipt.skipped.push({ area, id, reason: `lock-status-${hit.lockStatus}` }); continue; }
      if (!Number.isInteger(hit.page) || !Number.isInteger(hit.index)) {
        receipt.skipped.push({ area, id, reason: 'inventory-stale-no-page-index' }); continue;
      }
      // 下面几条是批次驱动自带的形状校验（capture-panes 原本靠 CLI 参数校验完成）。
      // 不合规就不开卷，绝不让路径/哈希异常进入浏览器阶段。
      if (!/^\d{1,15}$/u.test(id)) { receipt.skipped.push({ area, id, reason: 'invalid-id' }); continue; }
      if (!validTitleHash(hit.titleHash)) { receipt.skipped.push({ area, id, reason: 'invalid-title-hash' }); continue; }
      // 长度是身份核对的一部分。没有它就只能跳过，不能默默降级成「只比哈希前缀」。
      if (!Number.isInteger(hit.titleLen)) { receipt.skipped.push({ area, id, reason: 'invalid-title-len' }); continue; }
      if (!Number.isInteger(Number(candidate.year))) { receipt.skipped.push({ area, id, reason: 'invalid-year' }); continue; }
      if (hit.page < 1) { receipt.skipped.push({ area, id, reason: 'invalid-list-page' }); continue; }
      if (hit.index < 0) { receipt.skipped.push({ area, id, reason: 'invalid-row-index' }); continue; }
      const out = path.join(OUT_ROOT, id);
      if (!out.startsWith(OUT_ROOT + path.sep)) { receipt.skipped.push({ area, id, reason: 'invalid-out-path' }); continue; }
      jobs.push({
        area, year: Number(candidate.year), variant: String(candidate.variant || 'unknown').toLowerCase(),
        sourceId: id, titleHash: String(hit.titleHash).toLowerCase(), titleLen: hit.titleLen,
        listPage: hit.page, rowIndex: hit.index, out,
      });
    }
  }

  // 先把「规划结果 + 跳过原因」落进批次回执；即使第一张卷就出意外，也能看到计划了什么。
  persistReceipt();

  if (DRY) {
    for (const job of jobs) {
      receipt.captured.push({
        area: job.area, id: job.sourceId, dryRun: true,
        args: ['--area', job.area, '--year', String(job.year), '--variant', job.variant,
          '--source-id', job.sourceId, '--title-hash', job.titleHash, '--title-len', String(job.titleLen),
          '--list-page', String(job.listPage), '--row-index', String(job.rowIndex),
          '--out', job.out, '--work-dir', WORK_DIR],
      });
    }
  } else if (exitCode === 0 && jobs.length) {
    const base = await loadConfig(path.join(WORK_DIR, 'config.json'));
    const config = {
      ...base, workDir: WORK_DIR, profileDir: path.join(WORK_DIR, 'profiles', base.profileName),
      entryUrl: ENTRY, timeoutMs: 45000,
    };
    // 整个批次只开这一次浏览器 / 这一个 persistent profile。
    session = await openSession(config, { mode: 'capture', headless: false });

    // 开 TABS 个 Page（第一个是 openSession 自带的）。多开的空闲 Page 不参与导航，
    // 只作为固定标签页池；实际在飞数量由 runPool 的 CONCURRENCY 控制。
    const pages = [session.page];
    for (let index = 1; index < TABS; index += 1) pages.push(await session.context.newPage());
    pagesOpened = pages.length;

    await runPool({
      pages, jobs, session,
      onResult: (job, result) => {
        if (result.code === 0) {
          receipt.captured.push({ area: job.area, id: job.sourceId, out: job.out });
        } else {
          receipt.failed.push({ area: job.area, id: job.sourceId, code: result.code, summary: result.summary });
        }
        // 风控一出现就先写进回执，不必等到整个批次收尾（收尾可能因关闭浏览器而延后）。
        if (result.code === 3) {
          exitCode = 3;
          if (!receipt.aborted) {
            receipt.aborted = {
              step: 'capture',
              area: job.area,
              id: job.sourceId,
              code: 3,
              status: shared.reason?.status ?? null,
            };
          }
        }
        persistReceipt();
      },
    });

    if (shared.halted) {
      receipt.aborted = {
        step: 'capture',
        area: shared.reason?.area ?? null,
        id: shared.reason?.id ?? null,
        code: 3,
        status: shared.reason?.status ?? null,
      };
      exitCode = 3;
    }
  }
} catch (error) {
  receipt.errors = [{ code: error.code ?? 'ERROR', message: String(error.message).slice(0, 300) }];
  console.error(JSON.stringify({ ok: false, code: error.code ?? null, message: String(error.message).slice(0, 300) }));
  exitCode = error.code === 'RISK_SIGNAL' ? 3 : 1;
} finally {
  // 失败也走 finally 关会话：异常退出不能把 profile 锁和浏览器留在原地。
  if (session) await session.close().catch(() => {});
}

// 等最后一次增量写入落定，再写带 finishedAt 的终版。
await receiptWrite;
await fs.mkdir(OUT_ROOT, { recursive: true, mode: 0o700 });
await fs.writeFile(outFile, `${JSON.stringify({
  ...receipt,
  pagesOpened,
  risk: { ...shared.risk },
  guarded: session ? { ...session.guardStats } : null,
  finishedAt: new Date().toISOString(),
}, null, 2)}\n`, { mode: 0o600 });

console.log(JSON.stringify({
  captured: receipt.captured.length, skipped: receipt.skipped.length, failed: receipt.failed.length,
  aborted: receipt.aborted, tabs: TABS, concurrency: CONCURRENCY, pagesOpened,
  receipt: outFile,
}));
process.exitCode = exitCode;
