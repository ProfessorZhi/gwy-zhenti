// 申论目录 discover + candidate builder（只读、离线回放）。
//
// 只读 work/fenbi 下已经保存的真实目录快照，生成：
//   * 按 sourceId 去重的申论目录（地区/年份/卷型/费用状态）
//   * 候选队列 + 需要 Owner 现场核实免费状态的队列
//   * 覆盖矩阵与未知范围（未观察地区、部分页、缺字段）
// 不联网、不开浏览器、不读 profile、不写 papers/catalog-live。
//
// 用法：
//   node tools/fenbi/driver/shenlun-catalog-build.mjs \
//     --national-dir work/fenbi/t2-20261019/shenlun-national-catalog \
//     --inventory work/fenbi/t2-20261019/shenlun-inventory-zhejiang.json \
//     --captured-dir work/fenbi/shenlun-capture \
//     --out work/fenbi/shenlun-catalog-20261021.json
//
// 退出码：0 成功；2 输入/参数错误；1 运行时错误。

import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { buildShenlunCatalog } from './shenlun-catalog-core.mjs';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const MAX_JSON_BYTES = 64 * 1024 * 1024;
const MAX_CAPTURE_DIRS = 20000;
const SKIP_DIRS = new Set(['.git', 'node_modules', 'profiles', 'assets', 'images', 'img', 'payloads', 'snapshots', 'dom']);

const HELP = `Usage: shenlun-catalog-build.mjs [options]

Offline replay of saved shenlun catalog snapshots. No browser, no network.

  --national-dir DIR        directory with national-catalog-batch*.json (repeatable/comma)
  --inventory FILE|DIR      shenlun-inventory-*.json (repeatable/comma)
  --catalog-live-dir DIR    directory with catalog-*.json region observations
  --api-snapshot FILE       saved list response (body.list) (repeatable/comma)
  --api-dir DIR             directory with shenlun-api-*.json
  --area NAME               area for the supplied api snapshots (default: infer from title)
  --captured-dir DIR        scan for meta.json / run-summary.json / document.json sourceIds
  --cached-ids FILE         JSON array, {sourceIds:[]} or {papers:{...}}
  --out FILE                output path (default: $FENBI_WORK_DIR/shenlun-catalog-<date>.json)
  --now ISO                 fixed clock for deterministic replay
  --include-titles          include raw titles in the local output (never commit it)
  --include-mock            include type=2 mock papers in candidates
  -h, --help                this text
`;

class InputError extends Error {
  constructor(code, detail = '') {
    super(detail ? `${code}: ${detail}` : code);
    this.code = code;
  }
}

const values = (() => {
  try {
    return parseArgs({
      options: {
        'national-dir': { type: 'string', multiple: true },
        inventory: { type: 'string', multiple: true },
        'catalog-live-dir': { type: 'string', multiple: true },
        'api-snapshot': { type: 'string', multiple: true },
        'api-dir': { type: 'string', multiple: true },
        area: { type: 'string' },
        'captured-dir': { type: 'string', multiple: true },
        'cached-ids': { type: 'string', multiple: true },
        out: { type: 'string' },
        now: { type: 'string' },
        'include-titles': { type: 'boolean', default: false },
        'include-mock': { type: 'boolean', default: false },
        help: { type: 'boolean', short: 'h', default: false },
      },
    }).values;
  } catch (error) {
    console.log(JSON.stringify({ ok: false, code: 'BAD_ARGS', error: String(error.message || error) }));
    process.exit(2);
  }
})();

if (values.help) {
  process.stdout.write(HELP);
  process.exit(0);
}

const flatten = (input) => (input || []).flatMap((value) => String(value).split(',')).map((s) => s.trim()).filter(Boolean);
const exists = async (file) => fs.stat(file).then((s) => s.isFile()).catch(() => false);
const isDir = async (file) => fs.stat(file).then((s) => s.isDirectory()).catch(() => false);

async function readJson(file) {
  const stat = await fs.stat(file).catch(() => null);
  if (!stat || !stat.isFile()) throw new InputError('MISSING_FILE', path.basename(file));
  if (stat.size > MAX_JSON_BYTES) throw new InputError('FILE_TOO_LARGE', path.basename(file));
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'));
  } catch (error) {
    throw new InputError('BAD_JSON', `${path.basename(file)}: ${String(error.message || error)}`);
  }
}

async function fileSha256(file) {
  const hash = createHash('sha256');
  hash.update(await fs.readFile(file));
  return hash.digest('hex');
}

async function listDir(dir, pattern) {
  if (!await isDir(dir)) throw new InputError('MISSING_DIR', dir);
  const names = await fs.readdir(dir);
  return names.filter((name) => pattern.test(name)).sort().map((name) => path.join(dir, name));
}

async function addSnapshot(kind, file, { area = null } = {}) {
  return {
    kind,
    file: path.basename(file),
    sha256: await fileSha256(file),
    observedAt: null,
    area,
    json: await readJson(file),
  };
}

async function collectCaptured(dirs) {
  const ids = new Set();
  let dirsVisited = 0;
  let truncated = false;
  const walk = async (dir, depth) => {
    if (depth > 4) return;
    if (dirsVisited >= MAX_CAPTURE_DIRS) { truncated = true; return; }
    dirsVisited += 1;
    let entries;
    try { entries = await fs.readdir(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) await walk(full, depth + 1);
        continue;
      }
      if (!entry.isFile() || !['meta.json', 'run-summary.json', 'document.json'].includes(entry.name)) continue;
      const stat = await fs.stat(full).catch(() => null);
      if (!stat || stat.size > MAX_JSON_BYTES) continue;
      if (entry.name === 'document.json' && stat.size > 16 * 1024 * 1024) continue;
      const json = await readJson(full).catch(() => null);
      if (!json) continue;
      const candidates = [json.sourceId, json.paperId, json.identity?.sourceId, json.identity?.id];
      for (const value of candidates) if (value != null && /^\d+$/u.test(String(value))) ids.add(String(value));
    }
  };
  for (const dir of dirs) await walk(path.resolve(dir), 0);
  return { ids, truncated, scanned: dirsVisited };
}

async function readCachedIds(files) {
  const ids = new Set();
  for (const file of files) {
    const json = await readJson(file);
    if (Array.isArray(json)) for (const value of json) ids.add(String(value));
    else if (Array.isArray(json.sourceIds)) for (const value of json.sourceIds) ids.add(String(value));
    else if (json.papers && typeof json.papers === 'object') {
      for (const [key, value] of Object.entries(json.papers)) {
        ids.add(String(key));
        if (value?.sourceId != null) ids.add(String(value.sourceId));
      }
    }
  }
  return ids;
}

async function main() {
  const nationalDirs = flatten(values['national-dir']);
  const inventories = flatten(values.inventory);
  const liveDirs = flatten(values['catalog-live-dir']);
  const apiFiles = flatten(values['api-snapshot']);
  const apiDirs = flatten(values['api-dir']);
  const capturedDirs = flatten(values['captured-dir']);
  const cachedFiles = flatten(values['cached-ids']);

  if (!nationalDirs.length && !inventories.length && !liveDirs.length && !apiFiles.length && !apiDirs.length) {
    throw new InputError('NO_SNAPSHOTS', 'pass at least one snapshot source');
  }

  const now = values.now ? new Date(values.now) : new Date();
  if (Number.isNaN(now.getTime())) throw new InputError('BAD_NOW', values.now);

  const snapshots = [];
  for (const dir of nationalDirs) {
    for (const file of await listDir(path.resolve(dir), /^national-catalog-batch\d+\.json$/u)) {
      snapshots.push(await addSnapshot('national', file));
    }
  }
  for (const target of inventories) {
    const resolved = path.resolve(target);
    const files = await isDir(resolved)
      ? await listDir(resolved, /(?:^|[-_])inventory[-_].*\.json$/iu)
      : [resolved];
    for (const file of files) snapshots.push(await addSnapshot('inventory', file));
  }
  for (const dir of liveDirs) {
    for (const file of await listDir(path.resolve(dir), /^catalog-.*\.json$/u)) {
      snapshots.push(await addSnapshot('catalog-live', file));
    }
  }
  for (const file of apiFiles) snapshots.push(await addSnapshot('api', path.resolve(file), { area: values.area || null }));
  for (const dir of apiDirs) {
    for (const file of await listDir(path.resolve(dir), /^shenlun-api-\d+\.json$/u)) {
      snapshots.push(await addSnapshot('api', file, { area: values.area || null }));
    }
  }

  for (const snapshot of snapshots) snapshot.observedAt = snapshot.json?.at ?? null;

  const captured = await collectCaptured(capturedDirs);
  const capturedIds = captured.ids;
  for (const id of await readCachedIds(cachedFiles)) capturedIds.add(id);

  const catalog = buildShenlunCatalog({
    snapshots,
    capturedIds,
    now,
    includeTitles: values['include-titles'] === true,
    includeMock: values['include-mock'] === true,
  });

  catalog.captureInput = {
    capturedIds: capturedIds.size,
    scannedDirs: captured.scanned,
    scanTruncated: captured.truncated,
  };
  const outFile = path.resolve(values.out || path.join(WORK, `shenlun-catalog-${now.toISOString().slice(0, 10).replace(/-/gu, '')}.json`));
  const toolRoot = path.join(B, 'tools') + path.sep;
  if (outFile.startsWith(toolRoot)) throw new InputError('OUT_INSIDE_TOOLS', 'refusing to write snapshot output under tracked tools/');
  const protectedDirs = [path.join(WORK, 'papers'), path.join(WORK, 'profiles'), path.join(B, '.git')];
  if (protectedDirs.some((dir) => outFile === dir || outFile.startsWith(dir + path.sep))) {
    throw new InputError('OUT_PROTECTED', 'refusing to write into papers/, profiles/ or .git');
  }
  if (outFile.split(path.sep).some((segment) => segment.startsWith('catalog-live-'))) {
    throw new InputError('OUT_PROTECTED', 'refusing to write into a catalog-live snapshot directory');
  }
  await fs.mkdir(path.dirname(outFile), { recursive: true, mode: 0o700 });
  const tmp = outFile + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(catalog, null, 2) + '\n', { mode: 0o600 });
  await fs.rename(tmp, outFile);

  console.log(JSON.stringify({
    ok: true,
    offline: true,
    out: path.basename(outFile),
    sources: catalog.sources.length,
    ...catalog.totals,
    excluded: catalog.excluded,
    coverage: {
      observedAreas: catalog.coverage.observedAreas,
      partialAreas: catalog.coverage.partialAreas,
      unobservedRegions: catalog.coverage.unobservedRegions,
    },
    capturedIds: capturedIds.size,
    capturedScanTruncated: captured.truncated,
  }));
}

main().catch((error) => {
  const code = error instanceof InputError ? error.code : 'RUNTIME_ERROR';
  console.log(JSON.stringify({ ok: false, code, error: String(error.message || error) }));
  process.exit(code === 'RUNTIME_ERROR' ? 1 : 2);
});
