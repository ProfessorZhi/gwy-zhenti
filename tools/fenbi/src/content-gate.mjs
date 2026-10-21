#!/usr/bin/env node
/**
 * Gate for merging the integration branch into main without a human click.
 * Passes only when the branch, relative to the base ref, changes question-bank content and nothing else:
 *   - every changed path is under 国考/, 省考/, 图片/ or is catalog/manifest.jsonl
 *   - no paper Markdown is deleted
 *   - the manifest parses, has no duplicate paths, and lists every changed paper
 *   - every image a changed paper references exists
 * Code and docs never pass this gate; they still go through a reviewed PR.
 *
 * This is a structural pre-check only. It does not verify per-paper sourceId/SHA, QA receipts, the rights
 * boundary, question counts not regressing, or image hashes, so it must never be the sole trigger for merging
 * into main. A human (or a fuller gate covering those checks) still decides.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const CONTENT = /^(?:国考|省考|图片)\//u;
const MANIFEST = 'catalog/manifest.jsonl';
const PAPER = /^(?:国考|省考)\/.+\.md$/u;

export function changes(repo, base) {
  const out = execFileSync('git', ['-C', repo, '-c', 'core.quotepath=false', 'diff', '--name-status', '--no-renames', `${base}...HEAD`], { encoding: 'utf8' });
  return out.split('\n').filter(Boolean).map(line => { const [status, file] = line.split('\t'); return { status, file }; });
}

export async function checkContent({ repo, base = 'origin/main' }) {
  const reasons = [];
  const changed = changes(repo, base);
  for (const { status, file } of changed) {
    if (file !== MANIFEST && !CONTENT.test(file)) reasons.push(`non-content-path: ${file}`);
    if (status === 'D' && PAPER.test(file)) reasons.push(`paper-deleted: ${file}`);
  }
  const papers = changed.filter(c => c.status !== 'D' && PAPER.test(c.file)).map(c => c.file);
  let listed = new Set();
  try {
    const rows = (await fs.readFile(path.join(repo, MANIFEST), 'utf8')).split(/\r?\n/u).filter(Boolean).map(l => JSON.parse(l));
    const paths = rows.map(r => r.path);
    listed = new Set(paths);
    if (listed.size !== paths.length) reasons.push('manifest-duplicate-path');
  } catch (error) { reasons.push(`manifest-unreadable: ${error.message}`); }
  for (const file of papers) {
    if (!listed.has(file)) reasons.push(`paper-not-in-manifest: ${file}`);
    const md = await fs.readFile(path.join(repo, file), 'utf8');
    for (const m of md.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)|<img\b[^>]*\bsrc=["']([^"']+)["']/gu)) {
      const ref = decodeURI(m[1] || m[2]);
      if (/^[a-z]+:/iu.test(ref)) continue;
      await fs.access(path.resolve(path.dirname(path.join(repo, file)), ref)).catch(() => reasons.push(`missing-image: ${file} -> ${ref}`));
    }
  }
  return { ok: reasons.length === 0 && changed.length > 0, changedFiles: changed.length, papers: papers.length,
    reasons: reasons.slice(0, 50), reasonCount: reasons.length };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [repo, base] = [process.argv[2], process.argv[3] || 'origin/main'];
  if (!repo) throw Error('usage: content-gate.mjs REPO [BASE_REF]');
  checkContent({ repo, base }).then(r => { console.log(JSON.stringify(r)); if (!r.ok) process.exitCode = 3; })
    .catch(e => { console.error(e.message); process.exitCode = 1; });
}
