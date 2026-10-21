#!/usr/bin/env node
// 申论采集的离线解析/验收命令行。默认只输出 metadata-only 回执，不打印任何题干/材料/答案正文。
//
//   node src/shenlun-cli.mjs inspect --capture <采集目录> [--receipt <文件>] [--document <文件>]
//   node src/shenlun-cli.mjs render  --capture <采集目录> --out <本地候选目录>
//
// `--document`/`render` 会把正文写到本地路径；不要指向正式题库目录，也不要把产物提交到 Git。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadShenlunCapture, parseShenlunCapture, metadataReceipt, publicationBlockers } from './shenlun.mjs';
import { validateDocument } from './validate.mjs';
import { renderCandidate } from './render.mjs';

function parseArgs(argv) {
  const opts = { command: argv[0] ?? 'inspect' };
  for (let index = 1; index < argv.length; index++) {
    const flag = argv[index];
    if (!['--capture', '--out', '--receipt', '--document'].includes(flag)) throw new Error(`unknown-option:${flag}`);
    const value = argv[++index];
    if (!value) throw new Error(`missing-value:${flag}`);
    opts[flag.slice(2)] = value;
  }
  if (!opts.capture) throw new Error('capture-required');
  return opts;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const capture = await loadShenlunCapture(opts.capture);
  const { doc } = parseShenlunCapture(capture);
  const verdict = await validateDocument(doc);
  const receipt = metadataReceipt(doc, verdict);
  if (opts.receipt) {
    await fs.mkdir(path.dirname(path.resolve(opts.receipt)), { recursive: true, mode: 0o700 });
    await fs.writeFile(path.resolve(opts.receipt), JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
  }
  if (opts.command === 'inspect') {
    console.log(JSON.stringify(receipt, null, 2));
    if (opts.document) {
      await fs.mkdir(path.dirname(path.resolve(opts.document)), { recursive: true, mode: 0o700 });
      await fs.writeFile(path.resolve(opts.document), JSON.stringify(doc, null, 2) + '\n', { mode: 0o600 });
    }
    if (verdict.status !== 'complete') process.exitCode = 2;
    return;
  }
  if (opts.command === 'render') {
    if (!opts.out) throw new Error('out-required');
    if (verdict.status !== 'complete') {
      console.log(JSON.stringify({ ...receipt, rendered: false, reason: `validation-${verdict.status}` }, null, 2));
      process.exitCode = 2;
      return;
    }
    const blockers = publicationBlockers(doc);
    const target = path.resolve(opts.out);
    await fs.mkdir(target, { recursive: true, mode: 0o700 });
    const markdown = renderCandidate(doc, verdict);
    await fs.writeFile(path.join(target, 'paper.md'), markdown + '\n', { flag: 'wx', mode: 0o600 });
    await fs.writeFile(path.join(target, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    console.log(JSON.stringify({ ...receipt, rendered: true, publicationBlockers: blockers }, null, 2));
    return;
  }
  throw new Error(`unknown-command:${opts.command}`);
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) main().catch(error => { console.error(error.code || error.message); process.exitCode = 1; });
