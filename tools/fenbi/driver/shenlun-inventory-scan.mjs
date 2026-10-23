#!/usr/bin/env node
// 申论列表只读扫描：按地区页签翻完列表，产出「sourceId → 标题哈希」清单。
//
// 为什么需要：capture-panes 要求事先固定 --title-hash，身份不合就不采集。
// 全国目录快照只存了 id/年份/卷型，没存标题；浙江 36 卷的 inventory 是早期一次
// 现场扫描留下的。本脚本把那次扫描工具化：只读列表、只 GET、不点开任何试卷、
// 不创建练习、不写 papers 目录。
//
// 输出里**不写标题原文**，只写 sha256 前 12 位与长度——足以在采集时核对身份，
// 又不会把站内标题落盘。
//
// 用法：
//   DISPLAY=:77 node tools/fenbi/driver/shenlun-inventory-scan.mjs \
//     --area 天津 --out work/fenbi/t2-20261023/inventory-tianjin.json [--max-pages 20] [--gap-ms 2500]
//
// 退出码：0 成功；2 参数错误；3 风控信号（401/403/429/503）中止；1 运行时错误。

import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { setTimeout as sleep } from 'node:timers/promises';

import { loadConfig } from '../src/config.mjs';
import { openSession } from '../src/browser.mjs';
import { normalizeListApiSnapshot } from '../src/shenlun-list.mjs';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(REPO, 'work/fenbi'));
const ENTRY = 'https://www.fenbi.com/spa/tiku/guide/shenlunList/shenlun/1000';
const RISK_STATUS = new Set([401, 403, 429, 503]);
const hash12 = (text) => createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 12);

function fail(code, message, extra = {}) {
  const error = new Error(message);
  error.code = code;
  Object.assign(error, extra);
  return error;
}

const { values } = parseArgs({
  allowPositionals: false,
  options: {
    area: { type: 'string' }, out: { type: 'string' },
    'max-pages': { type: 'string' }, 'gap-ms': { type: 'string' }, 'work-dir': { type: 'string' },
    help: { type: 'boolean' },
  },
});

if (values.help) {
  console.log('usage: shenlun-inventory-scan.mjs --area 天津 --out FILE [--max-pages 20] [--gap-ms 2500]');
  process.exit(0);
}
for (const required of ['area', 'out']) {
  if (!values[required]) { console.error(`missing-argument:--${required}`); process.exit(2); }
}
const AREA = String(values.area).trim();
const OUT = path.resolve(values.out);
const GAP = Math.max(2500, Number(values['gap-ms'] || 2500));
const MAX_PAGES = Math.max(1, Math.min(60, Number(values['max-pages'] || 20)));
const WORK_DIR = values['work-dir'] ? path.resolve(values['work-dir']) : WORK;

const receipt = {
  schemaVersion: 1, at: new Date().toISOString(), area: AREA, entry: ENTRY,
  status: 'running', pagesRead: 0, totalPage: null, totalItem: null,
  items: [], risk: { unauthorized: 0, rateLimited: 0 }, blockedWrites: 0, errors: [],
};

let session;
let exitCode = 0;
try {
  const base = await loadConfig(path.join(WORK_DIR, 'config.json'));
  const config = { ...base, workDir: WORK_DIR, profileDir: path.join(WORK_DIR, 'profiles', base.profileName), entryUrl: ENTRY, timeoutMs: 45000 };
  session = await openSession(config, { mode: 'capture', headless: false });
  const { page } = session;
  page.on('response', (response) => {
    const status = response.status();
    if (status === 401 || status === 403) receipt.risk.unauthorized += 1;
    if (status === 429 || status === 503) receipt.risk.rateLimited += 1;
  });

  // 列表 API：只留内存。名称仅用于算哈希，绝不写盘。
  const seen = [];
  let seq = 0;
  page.on('response', (response) => {
    let url;
    try { url = new URL(response.url()); } catch { return; }
    if (!/(^|\.)fenbi\.com$/u.test(url.hostname)) return;
    if (response.request().method() !== 'GET') return;
    if (!url.pathname.startsWith('/api/') || url.pathname.startsWith('/api/users/')) return;
    if (!String(response.headers()['content-type'] || '').includes('json')) return;
    const mark = ++seq;
    response.json().then((json) => {
      if (!Array.isArray(json?.list ?? json?.body?.list)) return;
      const list = json?.list ?? json?.body?.list;
      seen.push({ seq: mark, path: url.pathname, json, list });
    }).catch(() => { /* 非 JSON 或读取失败：不登记 */ });
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
  const waitForListApi = async (pageNumber) => {
    for (let attempt = 0; attempt < 24; attempt += 1) {
      for (let i = seen.length - 1; i >= 0; i -= 1) {
        try {
          const api = normalizeListApiSnapshot(seen[i].json, { path: seen[i].path });
          if (api.page === pageNumber - 1) return { api, list: seen[i].list };
        } catch { /* 不是可用的列表快照 */ }
      }
      await sleep(250);
    }
    throw fail('LIST_API_UNOBSERVED', `no list API response observed for page ${pageNumber}`);
  };

  await page.goto(ENTRY, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await settle(3500);
  const regionClicked = await page.evaluate((region) => {
    const norm = (s) => String(s || '').replace(/\s+/gu, ' ').trim();
    const el = [...document.querySelectorAll('.category1-btn')].find((x) => norm(x.innerText) === region);
    if (!el || el.offsetParent === null) return false;
    el.click(); return true;
  }, AREA);
  if (!regionClicked) throw fail('REGION_NOT_FOUND', `region tab not visible: ${AREA}`);
  await settle(3000);
  stopOnRisk();

  const gotoPage = async (number) => {
    const ok = await page.evaluate((target) => {
      const pager = document.querySelector('div.paging');
      if (!pager) return false;
      const exact = [...pager.querySelectorAll('div.item')].find((x) => String(x.innerText).trim() === String(target));
      if (exact && exact.offsetParent !== null) { exact.click(); return true; }
      const next = [...pager.querySelectorAll('div.item, button, a')]
        .find((x) => /^(下一页|next|>|›)$/iu.test(String(x.innerText).trim()) && x.offsetParent !== null);
      if (!next) return false;
      next.click(); return true;
    }, number);
    if (!ok) return false;
    await settle(2500);
    stopOnRisk();
    return true;
  };

  let totalPage = 1;
  for (let pageNumber = 1; pageNumber <= Math.min(totalPage, MAX_PAGES); pageNumber += 1) {
    if (pageNumber > 1) {
      const moved = await gotoPage(pageNumber);
      if (!moved) { receipt.errors.push(`pager-stuck-at:${pageNumber}`); break; }
    }
    const { api, list } = await waitForListApi(pageNumber);
    if (pageNumber === 1) { totalPage = api.totalPage; receipt.totalPage = api.totalPage; receipt.totalItem = api.totalItem; }
    const raw = api.ids.map((id, index) => {
      const item = list[index] || {};
      return { id, name: typeof item.name === 'string' ? item.name : null, date: item.date ?? null, type: item.type ?? null, lockStatus: item.lockStatus ?? null };
    });
    for (const [index, entry] of raw.entries()) {
      const base = { sourceId: entry.id, page: pageNumber, index, date: entry.date ?? null, type: entry.type ?? null, lockStatus: entry.lockStatus ?? null };
      if (typeof entry.name !== 'string' || !entry.name.length) {
        receipt.items.push({ ...base, titleHash: null, titleLen: null });
        continue;
      }
      receipt.items.push({ ...base, titleHash: hash12(entry.name), titleLen: entry.name.length });
    }
    receipt.pagesRead = pageNumber;
    if (pageNumber < totalPage) await sleep(GAP);
  }
  const unique = new Map(receipt.items.map((item) => [item.sourceId, item]));
  if (unique.size !== receipt.items.length) {
    receipt.errors.push(`duplicate-ids-dropped:${receipt.items.length - unique.size}`);
    receipt.items = [...unique.values()];
  }
  receipt.truncated = Number.isInteger(receipt.totalPage) && receipt.pagesRead < receipt.totalPage;
  if (receipt.truncated) receipt.errors.push(`truncated:${receipt.pagesRead}/${receipt.totalPage}`);
  receipt.status = 'ok';
} catch (error) {
  receipt.status = error.code || 'error';
  receipt.errors.push(String(error.message || error));
  exitCode = error.code === 'RISK_SIGNAL' ? 3 : 1;
} finally {
  if (session) {
    receipt.blockedWrites = session.stats?.blockedWrites ?? 0;
    await session.close().catch(() => {});
  }
}

// 只有哈希与元数据；即便写进 work 目录也不会泄露标题正文。
await fs.mkdir(path.dirname(OUT), { recursive: true });
await fs.writeFile(OUT, `${JSON.stringify({ ...receipt, finishedAt: new Date().toISOString() }, null, 2)}\n`);
console.log(JSON.stringify({
  area: receipt.area, status: receipt.status, pagesRead: receipt.pagesRead, totalPage: receipt.totalPage,
  items: receipt.items.length, risk: receipt.risk, blockedWrites: receipt.blockedWrites, errors: receipt.errors,
}));
process.exit(exitCode);
