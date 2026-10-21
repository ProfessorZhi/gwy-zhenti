#!/usr/bin/env node
// 一次性修复：早先落盘的粉笔卷用拼音卷型命名（行测-tongkao.md），和本库原卷（行测-统考.md）并排成了两份。
// 按 paper-label.mjs 的规则把粉笔卷移到本库同一卷的文件名上，粉笔为准覆盖原卷；清单同步。
//   粉笔题数少于原卷、或目标已是另一份粉笔卷时不动，列在回执里。
//
//   node worker/fix-paper-names.mjs <仓库根目录> [--write]     不加 --write 只出回执
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { paperLabel, labelsIn } from '../src/paper-label.mjs';

const FENBI = 'Fenbi-priority structural check';
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const isAscii = s => !/[^\x00-\x7f]/u.test(s);

export async function fixPaperNames(repo, { write = false } = {}) {
  const manifestPath = path.join(repo, 'catalog/manifest.jsonl');
  const rows = (await fs.readFile(manifestPath, 'utf8')).split('\n').filter(Boolean).map(l => JSON.parse(l));
  const byPath = new Map(rows.map(r => [r.path, r]));
  const drop = new Set(), out = { moved: 0, replaced: 0, skipped: {}, examples: [] };
  const skip = (why, p) => { (out.skipped[why] ||= []).push(p); };
  for (const r of rows) {
    if (r.source_validation !== FENBI) continue;
    const dir = path.posix.dirname(r.path), file = path.posix.basename(r.path, '.md');
    const subject = file.split('-')[0], cur = file.slice(subject.length + 1);
    if (!isAscii(cur)) continue;
    const md = await fs.readFile(path.join(repo, r.path), 'utf8');
    const title = (md.match(/^# (.+)$/mu) || [])[1] || '';
    const label = paperLabel({ title, variant: cur, existing: labelsIn(await fs.readdir(path.join(repo, dir)), subject) });
    const target = `${dir}/${subject}-${label}.md`;
    const old = byPath.get(target);
    if (old?.source_validation === FENBI) { skip('target-is-fenbi', r.path); continue; }
    if (old && Number(old.declared_questions) > Number(r.declared_questions)) { skip('fenbi-fewer-questions', r.path); continue; }
    const fixed = md.replace(/^卷型: .*$/mu, `卷型: ${JSON.stringify(label)}`);
    if (old) { drop.add(old); out.replaced++; } else out.moved++;
    if (out.examples.length < 10) out.examples.push(`${r.path} -> ${target}${old ? '（覆盖原卷）' : ''}`);
    if (write) {
      await fs.writeFile(path.join(repo, target), fixed);
      await fs.unlink(path.join(repo, r.path));
    }
    byPath.delete(r.path);
    Object.assign(r, { path: target, paper_type: label, sha256: sha(fixed), bytes: Buffer.byteLength(fixed) });
    byPath.set(target, r);
  }
  if (write) await fs.writeFile(manifestPath, rows.filter(r => !drop.has(r)).map(r => JSON.stringify(r)).join('\n') + '\n');
  return { ...out, skipped: Object.fromEntries(Object.entries(out.skipped).map(([k, v]) => [k, { count: v.length, paths: v.slice(0, 20) }])), written: write };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const repo = path.resolve(process.argv[2] || '.');
  fixPaperNames(repo, { write: process.argv.includes('--write') })
    .then(s => console.log(JSON.stringify(s, null, 1))).catch(e => { console.error(e.message); process.exitCode = 1; });
}
