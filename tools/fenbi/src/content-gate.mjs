#!/usr/bin/env node
/**
 * Fail-closed gate for automatically fast-forwarding pure question-bank content to main.
 *
 * Passes only when the diff relative to the base ref changes 国考/, 省考/, 图片/ or
 * catalog/manifest.jsonl and nothing else, and every changed paper:
 *   - has exactly one manifest row with matching path, sha256, bytes, questions and answers;
 *   - has contiguous 题号, non-placeholder bodies, per-question answer and explanation;
 *   - references only in-repo images (realpath inside the repo, no scheme/absolute/..);
 * Code, docs, deletions and renames never pass. Rights are checked separately by
 * auto-main-content.mjs; this gate never treats "user chose A" as a rights grant.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';

const CONTENT = /^(?:国考|省考|图片)\//u;
const MANIFEST = 'catalog/manifest.jsonl';
const PAPER = /^(?:国考|省考)\/.+\.md$/u;
const PLACEHOLDER = /未征集|占位|待补充|本卷暂无|暂无题目|placeholder|TODO/iu;
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function changedPaths (repo, base) {
  const out = execFileSync('git', ['-C', repo, '-c', 'core.quotepath=false', 'diff', '--name-status', '--no-renames', `${base}...HEAD`], {encoding: 'utf8'});
  return out.split('\n').filter(Boolean).map(line => {
    const tab = line.indexOf('\t');
    return {status: line.slice(0, tab), file: line.slice(tab + 1)};
  });
}

export function checkPaperMarkdown (md, row, {isXingce = /行测/u.test(row?.path || '')} = {}) {
  const reasons = [];
  const heads = [...md.matchAll(/^#{2,3}\s*第\s*(\d+)\s*题[^\n]*$/gmu)]
    .map(m => ({n: Number(m[1]), start: m.index + m[0].length}));
  if (heads.length === 0) return ['paper-no-questions'];
  const numbers = heads.map(h => h.n).sort((a, b) => a - b);
  if (numbers.some((n, i) => n !== i + 1)) reasons.push('question-numbers-not-contiguous');
  let answers = 0;
  heads.forEach((head, i) => {
    const body = md.slice(head.start, heads[i + 1]?.start ?? md.length);
    if (PLACEHOLDER.test(body)) reasons.push(`placeholder-question:${head.n}`);
    if (!/【答案】|答案\s*[:：]/u.test(body)) reasons.push(`missing-answer:${head.n}`);
    else answers++;
    if (!/【解析】|解析\s*[:：]/u.test(body)) reasons.push(`missing-explanation:${head.n}`);
    const options = [...body.matchAll(/^\s*[A-D][.、．)]\s*\S/gmu)].length;
    if (isXingce && options < 2) reasons.push(`options-missing:${head.n}`);
    if (!isXingce && options > 0) reasons.push(`shenlun-options-present:${head.n}`);
  });
  if (Number.isInteger(row?.questions) && row.questions !== heads.length) reasons.push('manifest-questions-mismatch');
  if (Number.isInteger(row?.answers) && row.answers !== answers) reasons.push('manifest-answers-mismatch');
  return [...new Set(reasons)];
}

async function imageReasons (repo, repoReal, paperFile, md) {
  const reasons = [];
  const re = /!\[[^\]]*\]\(([^)\s]+)\)|<img\b[^>]*\bsrc=["']([^"']+)["']/giu;
  for (const m of md.matchAll(re)) {
    let ref;
    try { ref = decodeURIComponent(m[1] || m[2]); } catch { reasons.push(`image-ref-invalid:${paperFile}`); continue; }
    if (/^[a-z][a-z0-9+.-]*:/iu.test(ref) || ref.startsWith('//') || ref.startsWith('/') || ref.split(/[\\/]/u).includes('..')) {
      reasons.push(`image-external-or-absolute:${paperFile}:${ref}`);
      continue;
    }
    let real;
    try { real = await fs.realpath(path.resolve(repo, path.dirname(paperFile), ref)); } catch { real = null; }
    if (!real) { reasons.push(`missing-image:${paperFile}:${ref}`); continue; }
    if (real !== repoReal && !real.startsWith(repoReal + path.sep)) reasons.push(`image-escape:${paperFile}:${ref}`);
  }
  return reasons;
}

export async function readManifest (repo) {
  const reasons = [];
  let rows = [];
  try {
    const text = await fs.readFile(path.join(repo, MANIFEST), 'utf8');
    rows = text.split(/\r?\n/u).filter(Boolean).map((line, i) => {
      try { return JSON.parse(line); } catch { reasons.push(`manifest-unparsable:${i + 1}`); return null; }
    }).filter(Boolean);
  } catch (e) { reasons.push(`manifest-unreadable:${e.code || e.message}`); }
  const paths = rows.map(r => r?.path);
  if (new Set(paths).size !== paths.length) reasons.push('manifest-duplicate-path');
  for (const r of rows) {
    if (typeof r?.path !== 'string' || r.path.startsWith('/') || r.path.split(/[\\/]/u).includes('..')) reasons.push(`manifest-invalid-path:${r?.path}`);
  }
  return {rows, reasons};
}

export async function checkContent ({repo, base = 'origin/main', credentialPaperPaths = null}) {
  const reasons = [];
  let repoReal;
  try { repoReal = await fs.realpath(repo); } catch { return {ok: false, changedFiles: 0, papers: 0, reasons: ['repo-unreadable'], reasonCount: 1}; }
  let changed;
  try { changed = changedPaths(repo, base); } catch (e) { return {ok: false, changedFiles: 0, papers: 0, reasons: [`git-diff-failed:${e.message}`], reasonCount: 1}; }
  if (changed.length === 0) reasons.push('no-changes');
  for (const {status, file} of changed) {
    if (status !== 'A' && status !== 'M') reasons.push(`unsupported-change:${status}:${file}`);
    if (file !== MANIFEST && !CONTENT.test(file)) reasons.push(`non-content-path:${file}`);
    if (status === 'D' && PAPER.test(file)) reasons.push(`paper-deleted:${file}`);
  }
  const papers = changed.filter(c => (c.status === 'A' || c.status === 'M') && PAPER.test(c.file)).map(c => c.file);
  const {rows, reasons: manifestReasons} = await readManifest(repo);
  reasons.push(...manifestReasons);
  const byPath = new Map(rows.filter(r => typeof r?.path === 'string').map(r => [r.path, r]));
  for (const file of papers) {
    const row = byPath.get(file);
    if (!row) { reasons.push(`paper-not-in-manifest:${file}`); continue; }
    const abs = path.join(repo, file);
    const bytes = await fs.readFile(abs);
    if (!row.sha256 || row.sha256 !== sha(bytes)) reasons.push(`manifest-sha256-mismatch:${file}`);
    if (!Number.isInteger(row.bytes) || row.bytes !== bytes.length) reasons.push(`manifest-bytes-mismatch:${file}`);
    if (!Number.isInteger(row.questions)) reasons.push(`manifest-questions-missing:${file}`);
    if (!Number.isInteger(row.answers)) reasons.push(`manifest-answers-missing:${file}`);
    if (credentialPaperPaths && !credentialPaperPaths.has(file)) reasons.push(`rights-credential-missing:${file}`);
    reasons.push(...checkPaperMarkdown(bytes.toString('utf8'), row).map(r => `${r}:${file}`));
    reasons.push(...await imageReasons(repo, repoReal, file, bytes.toString('utf8')));
  }
  const unique = [...new Set(reasons)];
  return {ok: unique.length === 0 && changed.length > 0, changedFiles: changed.length, papers: papers.length, reasons: unique.slice(0, 80), reasonCount: unique.length};
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  const [repo, base='origin/main'] = process.argv.slice(2);
  if (!repo) { console.error('usage: content-gate.mjs REPO [BASE_REF]'); process.exitCode = 1; }
  else checkContent({repo, base}).then(r => { console.log(JSON.stringify(r)); if (!r.ok) process.exitCode = 3; })
    .catch(e => { console.error(e.message); process.exitCode = 1; });
}
