#!/usr/bin/env node
// 行级 patch catalog/manifest.jsonl。默认 --check，只有 --apply 才写盘。
import fs from 'node:fs';
import { applyManifestPatch } from './manifest-patch.mjs';

function usage() {
  return [
    'Usage: node tools/fenbi/src/manifest-patch-cli.mjs --manifest <file> --updates <json> [--check|--apply] [--out <file>]',
    '',
    'updates JSON: { "updates": [ { "path": "...", "expectSha256": "...", "set": { ... } } ] }',
  ].join('\n');
}

function parseArgs(argv) {
  const options = { checkOnly: true };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const take = () => {
      const value = argv[index + 1];
      if (value === undefined || value.startsWith('--')) throw new Error(`${arg} requires a value`);
      index += 1;
      return value;
    };
    if (arg === '--manifest') options.manifest = take();
    else if (arg === '--updates') options.updates = take();
    else if (arg === '--key') options.key = take();
    else if (arg === '--out') options.out = take();
    else if (arg === '--apply') options.checkOnly = false;
    else if (arg === '--check') options.checkOnly = true;
    else if (arg === '--help' || arg === '-h') options.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return options;
}

function main() {
  let options;
  try { options = parseArgs(process.argv.slice(2)); } catch (error) {
    console.error(error.message);
    console.error(usage());
    process.exit(2);
  }
  if (options.help || !options.manifest || !options.updates) { console.log(usage()); process.exit(options.help ? 0 : 2); }
  const parsed = JSON.parse(fs.readFileSync(options.updates, 'utf8'));
  const updates = Array.isArray(parsed) ? parsed : parsed.updates ?? [];
  const result = applyManifestPatch({
    manifestPath: options.manifest,
    updates,
    key: options.key ?? 'path',
    checkOnly: options.checkOnly,
  });
  if (options.out) {
    const temp = `${options.out}.tmp-${process.pid}`;
    fs.writeFileSync(temp, `${JSON.stringify({ ok: result.ok, conflicts: result.conflicts, operations: result.operations, changed: result.changed, written: result.written ?? false }, null, 1)}\n`);
    fs.renameSync(temp, options.out);
  }
  console.log(JSON.stringify({ ok: result.ok, changed: result.changed, written: result.written ?? false, conflicts: result.conflicts.length }, null, 1));
  if (!result.ok) process.exit(1);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
