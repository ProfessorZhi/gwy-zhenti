#!/usr/bin/env node
// 申论本地档案 publish-preflight CLI。
//
// 默认只读：扫描 → 输出 JSON/Markdown。只有显式 --snapshot-out 才写派生元数据，
// 只有显式 --apply-repairs 才复制图片字节，而且只补缺失/哈希不符的目标，不删除、
// 不重写题目或权利标记。
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { scanArchive, renderMarkdown } from './archive-preflight.mjs';

const sha256File = (file) => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sha256 = (value) => createHash('sha256').update(value).digest('hex');

function parseArgs(argv) {
  const options = { assetStores: [], priorAnswerPaths: null };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const take = () => {
      const value = argv[index + 1];
      if (value === undefined || value.startsWith('--')) throw new Error(`${arg} requires a value`);
      index += 1;
      return value;
    };
    if (arg === '--archive') options.archive = take();
    else if (arg === '--main-manifest') options.mainManifest = take();
    else if (arg === '--inventory') options.inventory = take();
    else if (arg === '--asset-store') options.assetStores.push(take());
    else if (arg === '--out') options.out = take();
    else if (arg === '--markdown') options.markdown = take();
    else if (arg === '--snapshot-out') options.snapshotOut = take();
    else if (arg === '--repair-plan') options.repairPlanOut = take();
    else if (arg === '--apply-repairs') options.applyRepairs = true;
    else if (arg === '--strict') options.strict = true;
    else if (arg === '--json') options.json = true;
    else if (arg === '--help' || arg === '-h') options.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return options;
}

function usage() {
  return [
    'Usage: node tools/fenbi/src/archive-preflight-cli.mjs --archive <dir> [options]',
    '',
    '  --archive <dir>          private Shenlun archive root (read-only)',
    '  --main-manifest <file>   repo catalog/manifest.jsonl for overlap matching',
    '  --inventory <file>       optional inventory.json for capture document SHA checks',
    '  --asset-store <dir>      repeatable; local image stores for repair planning',
    '  --out <file>             write metadata-only JSON report',
    '  --markdown <file>        write metadata-only Markdown summary',
    '  --snapshot-out <dir>     write derived metadata snapshot (no content)',
    '  --repair-plan <file>     write repair plan JSON (never applied unless asked)',
    '  --apply-repairs          apply copy-only repairs from the just-built plan',
    '  --strict                 exit 1 when any volume is FAIL/SKIP',
    '  --json                   print the metadata-only report to stdout',
  ].join('\n');
}

function writeAtomic(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(temp, data);
  fs.renameSync(temp, file);
}

function writeSnapshot(outDir, report) {
  fs.mkdirSync(outDir, { recursive: true });
  const volumesDir = path.join(outDir, 'volumes');
  fs.mkdirSync(volumesDir, { recursive: true });
  for (const volume of report.volumes) {
    writeAtomic(path.join(volumesDir, `${volume.sourceId}.json`), `${JSON.stringify(volume, null, 1)}\n`);
  }
  writeAtomic(path.join(outDir, 'matrix.json'), `${JSON.stringify(report, null, 1)}\n`);
  const archive = report.archive.root;
  for (const name of ['catalog/index.jsonl', 'rights-provenance.json']) {
    const source = path.join(archive, name);
    if (!fs.existsSync(source)) continue;
    const bytes = fs.readFileSync(source);
    writeAtomic(path.join(outDir, name.replace(/\//gu, '-')), bytes);
  }
  writeAtomic(path.join(outDir, 'README.md'), [
    '# Derived metadata snapshot',
    '',
    'This directory contains only counts, hashes, relative asset paths and issue codes.',
    'No question stem, material, answer, explanation, title, URL or image byte is copied.',
    '',
    `Archive: ${archive}`,
    `Index SHA256: ${report.archive.indexSha256}`,
    `Generated: ${report.generatedAt}`,
  ].join('\n'));
}

/** 只做 copy 修复：目标已存在且哈希正确则跳过；其余情况原子替换。 */
export function applyRepairPlan({ plan, archiveRoot, dryRun = true, log = () => {} }) {
  const result = { applied: [], skipped: [], failed: [] };
  for (const operation of plan?.operations ?? []) {
    if (operation.op !== 'copy') { result.skipped.push({ ...operation, reason: 'not-copy-op' }); continue; }
    const target = path.join(archiveRoot, 'papers', operation.sourceId, operation.file);
    const assetsDir = path.join(archiveRoot, 'papers', operation.sourceId, 'assets');
    if (!target.startsWith(assetsDir + path.sep)) {
      result.failed.push({ ...operation, reason: 'target-escapes-assets' });
      continue;
    }
    let targetOk = false;
    if (fs.existsSync(target)) {
      try { targetOk = sha256File(target) === operation.sha256; } catch { targetOk = false; }
    }
    if (targetOk) { result.skipped.push({ ...operation, reason: 'already-verified' }); continue; }
    if (!fs.existsSync(operation.from)) { result.failed.push({ ...operation, reason: 'source-missing' }); continue; }
    if (sha256File(operation.from) !== operation.sha256) {
      result.failed.push({ ...operation, reason: 'source-sha-mismatch' });
      continue;
    }
    if (dryRun) { result.applied.push({ ...operation, dryRun: true }); continue; }
    fs.mkdirSync(assetsDir, { recursive: true });
    const temp = `${target}.tmp-${process.pid}`;
    fs.copyFileSync(operation.from, temp);
    if (sha256File(temp) !== operation.sha256) {
      fs.rmSync(temp, { force: true });
      result.failed.push({ ...operation, reason: 'copied-sha-mismatch' });
      continue;
    }
    fs.renameSync(temp, target);
    log(`copied ${operation.sourceId}/${operation.file}`);
    result.applied.push({ ...operation, dryRun: false });
  }
  return result;
}

function main() {
  let options;
  try { options = parseArgs(process.argv.slice(2)); } catch (error) {
    console.error(error.message);
    console.error(usage());
    process.exit(2);
  }
  if (options.help || !options.archive) { console.log(usage()); process.exit(options.help ? 0 : 2); }

  const report = scanArchive({
    archiveRoot: options.archive,
    mainManifestPath: options.mainManifest ?? null,
    inventoryPath: options.inventory ?? null,
    assetStores: options.assetStores,
  });

  if (options.out) writeAtomic(options.out, `${JSON.stringify(report, null, 1)}\n`);
  if (options.markdown) writeAtomic(options.markdown, renderMarkdown(report));
  if (options.snapshotOut) writeSnapshot(options.snapshotOut, report);
  if (options.repairPlanOut) writeAtomic(options.repairPlanOut, `${JSON.stringify(report._repairPlan ?? report.repairPlan, null, 1)}\n`);
  if (options.applyRepairs) {
    const applied = applyRepairPlan({
      plan: report._repairPlan ?? report.repairPlan, archiveRoot: report.archive.root, dryRun: false, log: (line) => console.error(line),
    });
    console.error(`repairs: applied=${applied.applied.length} skipped=${applied.skipped.length} failed=${applied.failed.length}`);
  }
  if (options.json) console.log(JSON.stringify(report, null, 1));

  console.error([
    `archive=${report.archive.root}`,
    `volumes=${report.archive.volumeCount}`,
    `technical PASS/FAIL/SKIP=${report.gates.technical.PASS}/${report.gates.technical.FAIL}/${report.gates.technical.SKIP}`,
    `publication BLOCKED/ELIGIBLE/VIOLATION=${report.gates.publication.BLOCKED}/${report.gates.publication.ELIGIBLE}/${report.gates.publication.POLICY_VIOLATION}`,
    `snapshotStable=${report.archive.snapshotStable}`,
  ].join(' '));

  if (options.strict && (report.gates.technical.FAIL > 0 || report.gates.technical.SKIP > 0)) process.exit(1);
  if (report.gates.publication.ELIGIBLE > 0) process.exit(3);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
