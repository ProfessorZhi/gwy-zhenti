#!/usr/bin/env node
// 申论候选：把已采集的全国目录（shenlun-national-catalog）与浙江清单合成一条按优先级排好的队列。
// 三层顺序：浙江 → 重点地区（FOCUS_REGIONS）→ 其余地区；同层内按地区、年份升序。
// 目录项只有 {id, year, variant}，没有标题——申论列表页也不返回标题原文。因此候选用「页码 + 页内行号」
// 定位，点行前再按年份/卷型标记核对一次，对不上就报错而不点，绝不靠猜。
//
// 环境变量：
//   FENBI_WORK_DIR         运行目录（默认 <repo>/work/fenbi）
//   SHENLUN_CANDIDATES_FILE 输出文件（默认 $WORK/shenlun-candidates.json）
//   SHENLUN_LIMIT          只取前 N 条（试跑用）
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { yearAllowed } from './year-policy.mjs';
import { FOCUS_REGIONS } from './focus-schedule.mjs';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const RUN = path.join(WORK, 't2-20261019');
const CATALOG = path.join(RUN, 'shenlun-national-catalog');
const INVENTORY = path.join(RUN, 'shenlun-inventory-zhejiang.json');
const CAPTURE = path.join(WORK, 'shenlun-capture');
const PAPERS = path.join(WORK, 'papers');
const OUT = process.env.SHENLUN_CANDIDATES_FILE || path.join(WORK, 'shenlun-candidates.json');
const LIMIT = Number(process.env.SHENLUN_LIMIT || 0);

const readJson = async (file, fallback = null) => { try { return JSON.parse(await fs.readFile(file, 'utf8')); } catch { return fallback; } };
const exists = file => fs.access(file).then(() => true, () => false);

// 优先级：0 = 浙江（L1），1 = 重点地区（L2），2 = 其余（L3）。
const focusIndex = new Map(FOCUS_REGIONS.map((name, index) => [name, index]));
const tierOf = area => area === '浙江' ? 0 : focusIndex.has(area) ? 1 : 2;

// ---------- 已抓集合：申论缓存目录 + papers 里的申论卷 ----------
const captured = new Set();
for (const dir of await fs.readdir(CAPTURE).catch(() => [])) {
  if (!(await exists(path.join(CAPTURE, dir, 'document.json')))) continue;
  captured.add(String(dir));
}
for (const dir of await fs.readdir(PAPERS).catch(() => [])) {
  const run = await readJson(path.join(PAPERS, dir, 'run-summary.json'));
  if (run?.subject === 'shenlun' && run?.sourceId != null) captured.add(String(run.sourceId));
}

// ---------- 目录：逐批展开 categories[].pages[].apiItems[] ----------
const files = (await fs.readdir(CATALOG).catch(() => [])).filter(name => /^national-catalog-batch\d+\.json$/u.test(name));
const byId = new Map();
const excluded = { duplicate: 0, outOfYear: 0, paid: 0, noId: 0, alreadyCaptured: 0 };
let scanned = 0;
for (const file of files.sort((a, b) => {
  const n = name => Number((name.match(/batch(\d+)/u) || [])[1] || 0);
  return n(a) - n(b);
})) {
  const batch = await readJson(path.join(CATALOG, file), {});
  for (const category of batch.categories || []) {
    if (!category?.observed) continue;
    const area = String(category.category || '').trim();
    if (!area) continue;
    for (const page of category.pages || []) {
      const items = page.apiItems || [];
      items.forEach((item, index) => {
        scanned++;
        if (item?.id == null) { excluded.noId++; return; }
        const id = String(item.id);
        const year = Number(item.year);
        if (!yearAllowed(area, year)) { excluded.outOfYear++; return; }
        if (item.paidFlag === true) { excluded.paid++; return; }
        if (captured.has(id)) { excluded.alreadyCaptured++; return; }
        if (byId.has(id)) { excluded.duplicate++; return; }
        byId.set(id, { id, year, variant: String(item.variant || 'unknown'), area, region: area,
          subject: 'shenlun', page: Number(page.page), index });
      });
    }
  }
}

const candidates = [...byId.values()].sort((a, b) =>
  (tierOf(a.area) - tierOf(b.area))
  || (a.area.localeCompare(b.area, 'zh'))
  || (a.year - b.year)
  || a.id.localeCompare(b.id));
const limited = LIMIT > 0 ? candidates.slice(0, LIMIT) : candidates;

const tiers = { L1: 0, L2: 0, L3: 0 };
for (const candidate of candidates) tiers[['L1', 'L2', 'L3'][tierOf(candidate.area)]]++;
const byArea = {};
for (const candidate of candidates) byArea[candidate.area] = (byArea[candidate.area] || 0) + 1;

const payload = { schemaVersion: 1, at: new Date().toISOString(), subject: 'shenlun',
  ordering: 'L1 浙江 → L2 重点地区 → L3 其余地区；同层按地区、年份升序',
  source: { catalogFiles: files.length, inventory: path.basename(INVENTORY) },
  stats: { scanned, candidates: candidates.length, emitted: limited.length, tiers, byArea, excluded,
    alreadyCaptured: captured.size },
  candidates: limited };
await fs.writeFile(OUT + '.tmp', JSON.stringify(payload, null, 2) + '\n', { mode: 0o600 });
await fs.rename(OUT + '.tmp', OUT);
console.log(JSON.stringify({ ok: true, out: OUT, ...payload.stats }, null, 1));
