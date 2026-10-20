#!/usr/bin/env node
/**
 * Fail-closed gate for automatically fast-forwarding pure question-bank content to main.
 *
 * Supports both in-repo paper schemas:
 *   A: question section + "A. ..." options, answers in independent <details> blocks;
 *   B: "- **A**." options, "**答案**：" + "**解析**" / "来源参考解析" inside <details>.
 * Answers are bound per question number from that question's own <details> block; the last
 * question never absorbs the answer area, and option letters inside 材料/申论 answers never
 * count as xingce options.
 *
 * Code, docs, deletions, renames, symlinks, image-only or manifest-only diffs never pass.
 * Rights are checked separately by auto-main-content.mjs.
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

function answerParts (text) {
  const answer = /(?:【答案】|(?:\*\*)?参考答案[^\n]*|(?:\*\*)?答案(?:\*\*)?\s*[:：])\s*([\s\S]*?)(?=\n\s*(?:【解析】|\*\*解析\*\*|(?:\*\*)?来源参考解析|解析\s*[:：])|$)/u.exec(text);
  const explanation = /(?:【解析】|\*\*解析\*\*|(?:\*\*)?来源参考解析\s*[:：]?|解析\s*[:：])\s*([\s\S]*)/u.exec(text);
  return {answer: answer?.[1]?.trim() || '', explanation: explanation?.[1]?.trim() || ''};
}

function optionCount (body) {
  const schemaA = [...body.matchAll(/^[A-D][.、．)]\s*\S/gmu)].length;
  const schemaB = [...body.matchAll(/^\s*[-*]\s*\*\*[A-D]\*\*\s*[.、．)]?\s*\S/gmu)].length;
  return schemaA + schemaB;
}

/** Parse one paper. Returns {questions, answers, explanations, reasons}. */
export function parsePaperMarkdown (md, {isXingce = false, row = {}} = {}) {
  const reasons = [];
  const detailsStart = md.search(/^<details\b/mu);
  const answerHeading = md.search(/^##\s*(?:参考答案|答案与解析|答案)\s*$/mu);
  const qHeading = md.search(/^##\s*题目\s*$/mu);
  const ends = [detailsStart, answerHeading].filter(index => index >= 0);
  const regionEnd = ends.length ? Math.min(...ends) : md.length;
  const region = md.slice(qHeading >= 0 ? qHeading : 0, regionEnd);
  // Allow an optional, verifiable metadata suffix such as ` <sub>qid 13319187 · 毛中特</sub>`;
  // anything else after the number keeps the heading from being a question heading.
  const heads = [...region.matchAll(/^#{2,3}\s*第\s*(\d+)\s*题[^\S\n]*(?:<sub>[^<\n]{1,80}<\/sub>)?[^\S\n]*$/gmu)]
    .map(m => ({n: Number(m[1]), start: m.index + m[0].length}));
  if (heads.length === 0) return {questions: 0, answers: 0, explanations: 0, reasons: ['paper-no-questions']};
  const numbers = heads.map(h => h.n).sort((a, b) => a - b);
  if (numbers.some((n, i) => n !== i + 1)) reasons.push('question-numbers-not-contiguous');

  const details = new Map();
  for (const m of md.matchAll(/^<details>\s*<summary>\s*第\s*(\d+)\s*题\s*<\/summary>([\s\S]*?)^<\/details>/gmu)) {
    const n = Number(m[1]);
    if (details.has(n)) reasons.push(`duplicate-answer-block:${n}`);
    else details.set(n, m[2]);
  }

  let answers = 0, explanations = 0;
  for (const [index, head] of heads.entries()) {
    const body = region.slice(head.start, heads[index + 1]?.start ?? region.length);
    if (PLACEHOLDER.test(body)) reasons.push(`placeholder-question:${head.n}`);
    const own = details.get(head.n);
    if (detailsStart >= 0 && !own) reasons.push(`missing-answer-block:${head.n}`);
    const inline = answerParts(body);
    const sourced = own ? answerParts(own) : {answer: '', explanation: ''};
    const answer = inline.answer || sourced.answer;
    const explanation = inline.explanation || sourced.explanation;
    if (!answer) reasons.push(`missing-answer:${head.n}`); else answers++;
    if (!explanation) reasons.push(`missing-explanation:${head.n}`); else explanations++;
    if (isXingce && optionCount(body) < 2) reasons.push(`options-missing:${head.n}`);
  }
  for (const n of details.keys()) if (!numbers.includes(n)) reasons.push(`orphan-answer-block:${n}`);

  const declared = Number.isInteger(row.declared_questions) ? row.declared_questions
    : Number.isInteger(row.questions) ? row.questions : null;
  const answerBlocks = Number.isInteger(row.answer_blocks) ? row.answer_blocks
    : Number.isInteger(row.answers) ? row.answers : null;
  if (declared !== null && declared !== heads.length) reasons.push('manifest-questions-mismatch');
  if (answerBlocks !== null && answerBlocks !== answers) reasons.push('manifest-answers-mismatch');
  return {questions: heads.length, answers, explanations, reasons: [...new Set(reasons)]};
}

export function checkPaperMarkdown (md, row, {isXingce = /行测/u.test(row?.path || '')} = {}) {
  return parsePaperMarkdown(md, {isXingce, row}).reasons;
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

export async function checkContent ({repo, base = 'origin/main'}) {
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
    try {
      const stat = await fs.lstat(path.join(repo, file));
      if (stat.isSymbolicLink()) reasons.push(`changed-path-symlink:${file}`);
      if (!stat.isFile() && !stat.isSymbolicLink()) reasons.push(`changed-path-not-file:${file}`);
    } catch { reasons.push(`changed-path-missing:${file}`); }
  }
  const papers = changed.filter(c => (c.status === 'A' || c.status === 'M') && PAPER.test(c.file)).map(c => c.file);
  // A manifest-only or image-only diff has no audited paper to bind credentials to.
  if (papers.length === 0 && changed.length > 0) reasons.push('no-papers-changed');
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
    const declared = Number.isInteger(row.declared_questions) ? row.declared_questions
      : Number.isInteger(row.questions) ? row.questions : null;
    const answerBlocks = Number.isInteger(row.answer_blocks) ? row.answer_blocks
      : Number.isInteger(row.answers) ? row.answers : null;
    if (declared === null) reasons.push(`manifest-questions-missing:${file}`);
    if (answerBlocks === null) reasons.push(`manifest-answers-missing:${file}`);
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
