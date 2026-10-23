#!/usr/bin/env node
// 申论补抓批处理：候选 → 列表扫描（拿标题哈希）→ 逐卷只读采集 → 汇总回执。
//
// 严格串行：同一时刻只有浏览器一个进程、一个 profile。任何一步看到
// 401/403/429/503，采集脚本会以退出码 3 中止，本脚本随即放弃剩余卷，不重试。
//
// 采到的卷只落在 --out-root（必须在仓库外）；落库是另一个显式步骤（worker/land-shenlun.mjs）。
//
// 用法：
//   DISPLAY=:77 node tools/fenbi/driver/shenlun-batch.mjs \
//     --candidates work/fenbi/shenlun-candidates.json \
//     --out-root /home/fjd/tmp/shenlun-capture-20261023 \
//     [--areas 天津,甘肃] [--limit 5] [--gap-ms 30000] [--dry-run]
//
// 退出码：0 全部处理完（含被跳过的）；3 风控中止；2 参数错误；1 其他错误。

import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { setTimeout as sleep } from 'node:timers/promises';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../../..');
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(REPO, 'work/fenbi'));

const { values } = parseArgs({
  allowPositionals: false,
  options: {
    candidates: { type: 'string' }, 'out-root': { type: 'string' },
    'inventory-dir': { type: 'string' }, areas: { type: 'string' },
    limit: { type: 'string' }, 'gap-ms': { type: 'string' },
    'work-dir': { type: 'string' }, 'dry-run': { type: 'boolean' }, help: { type: 'boolean' },
  },
});
if (values.help) {
  console.log('usage: shenlun-batch.mjs --candidates FILE --out-root DIR [--areas A,B] [--limit N] [--gap-ms 30000] [--dry-run]');
  process.exit(0);
}
for (const required of ['candidates', 'out-root']) {
  if (!values[required]) { console.error(`missing-argument:--${required}`); process.exit(2); }
}
const CANDIDATES = path.resolve(values.candidates);
const OUT_ROOT = path.resolve(values['out-root']);
const WORK_DIR = values['work-dir'] ? path.resolve(values['work-dir']) : WORK;
const GAP = Math.max(5000, Number(values['gap-ms'] || 30000));
const LIMIT = Number(values.limit || 5);
const DRY = Boolean(values['dry-run']);
const inventoryDir = path.resolve(values['inventory-dir'] || path.join(WORK_DIR, 'shenlun-inventory'));

// 采集产物只能落在仓库外。
for (const [label, root] of [['repo', REPO], ['work-dir', WORK_DIR]]) {
  if (OUT_ROOT === root || OUT_ROOT.startsWith(root + path.sep)) {
    console.error(`refusing-out-root-inside-${label}`); process.exit(2);
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

const receipt = {
  at: new Date().toISOString(), candidates: CANDIDATES, outRoot: OUT_ROOT, dryRun: DRY,
  gapMs: GAP, limit: LIMIT, areas: [], captured: [], skipped: [], failed: [], aborted: null,
};
const already = new Set();
try {
  for (const entry of await fs.readdir(OUT_ROOT)) {
    if (await fs.access(path.join(OUT_ROOT, entry, 'document.json')).then(() => true, () => false)) already.add(entry);
  }
} catch { /* 输出目录还不存在 */ }

await fs.mkdir(inventoryDir, { recursive: true });
let done = 0;
let exitCode = 0;

outer:
for (const [area, list] of grouped) {
  const areaReceipt = { area, candidates: list.length, inventory: null, scanned: false };
  receipt.areas.push(areaReceipt);
  const pending = list.filter((c) => !already.has(String(c.id)));
  if (!pending.length) { areaReceipt.note = 'all-already-captured'; continue; }
  if (done >= LIMIT) break;

  const inventoryFile = path.join(inventoryDir, `inventory-${area}.json`);
  let inventory;
  try {
    inventory = JSON.parse(await fs.readFile(inventoryFile, 'utf8'));
    if (inventory.status !== 'ok') throw new Error('inventory not ok');
  } catch {
    if (DRY) { areaReceipt.note = 'would-scan'; continue; }
    const scan = await run(process.execPath, [path.join(HERE, 'shenlun-inventory-scan.mjs'),
      '--area', area, '--out', inventoryFile, '--work-dir', WORK_DIR, '--gap-ms', String(GAP)]);
    areaReceipt.scanned = true;
    areaReceipt.scanExit = scan.code;
    areaReceipt.scanSummary = scan.stdout.trim().split('\n').pop();
    if (scan.code === 3) { receipt.aborted = { step: 'scan', area, code: 3 }; exitCode = 3; break outer; }
    if (scan.code !== 0) { receipt.failed.push({ area, step: 'scan', code: scan.code, detail: scan.stderr.trim().slice(-400) }); continue; }
    inventory = JSON.parse(await fs.readFile(inventoryFile, 'utf8'));
  }
  areaReceipt.inventory = { pages: inventory.pagesRead, items: (inventory.items || []).length };
  const byId = new Map((inventory.items || []).map((item) => [String(item.sourceId), item]));

  for (const candidate of pending) {
    if (done >= LIMIT) break;
    const hit = byId.get(String(candidate.id));
    if (!hit || !hit.titleHash) { receipt.skipped.push({ area, id: String(candidate.id), reason: 'no-title-hash' }); continue; }
    if (hit.lockStatus !== 0) { receipt.skipped.push({ area, id: String(candidate.id), reason: `lock-status-${hit.lockStatus}` }); continue; }
    if (!Number.isInteger(hit.page) || !Number.isInteger(hit.index)) {
      receipt.skipped.push({ area, id: String(candidate.id), reason: 'inventory-stale-no-page-index' }); continue;
    }
    const out = path.join(OUT_ROOT, String(candidate.id));
    const args = [path.join(HERE, 'shenlun-capture-panes.mjs'),
      '--area', area, '--year', String(candidate.year), '--variant', String(candidate.variant || 'unknown'),
      '--source-id', String(candidate.id), '--title-hash', hit.titleHash, '--title-len', String(hit.titleLen),
      '--list-page', String(hit.page), '--row-index', String(hit.index),
      '--out', out, '--work-dir', WORK_DIR];
    if (DRY) { receipt.captured.push({ area, id: String(candidate.id), dryRun: true, args: args.slice(1) }); done += 1; continue; }
    const result = await run(process.execPath, args);
    const summary = result.stdout.trim().split('\n').pop();
    done += 1;
    if (result.code === 0) { receipt.captured.push({ area, id: String(candidate.id), out }); }
    else if (result.code === 3) { receipt.failed.push({ area, id: String(candidate.id), code: 3, summary }); receipt.aborted = { step: 'capture', area, id: String(candidate.id), code: 3 }; exitCode = 3; break outer; }
    else { receipt.failed.push({ area, id: String(candidate.id), code: result.code, summary }); }
    await sleep(GAP);
  }
}

await fs.mkdir(OUT_ROOT, { recursive: true });
const outFile = path.join(OUT_ROOT, `batch-${new Date().toISOString().replace(/[:.]/gu, '-')}.json`);
await fs.writeFile(outFile, `${JSON.stringify({ ...receipt, finishedAt: new Date().toISOString() }, null, 2)}\n`);
console.log(JSON.stringify({
  captured: receipt.captured.length, skipped: receipt.skipped.length, failed: receipt.failed.length,
  aborted: receipt.aborted, receipt: outFile,
}));
process.exit(exitCode);
