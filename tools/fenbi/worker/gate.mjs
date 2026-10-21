// 自动合入 main 的完整闸门。content-gate 的结构检查之外，逐卷核对：
//   - 每份改动的试卷都有 batch-ingest 回执，回执的 markdownSha256 与文件字节一致，sourceId 合法，等级为 A
//   - 授权文件覆盖该 sourceId（schemaVersion 1、allowGitHubStorage、evidence；coverAllCapturedSources 或列出）
//   - 题数等于回执题数且连续编号，且不少于 base 上同一路径的题数（不倒退）
//   - 没有残留"征集中"之类的占位文字
//   - 清单里该路径的 sha256 与文件一致
//   - 新增图片只能是 assets-fenbi-<sourceId>/<sha256>.<扩展名>，内容哈希与文件名一致；已有图片不允许改写
// 任何一项不过，整批不合入 main（仍推送集成分支），原因写进回执。
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { checkContent, changes } from '../src/content-gate.mjs';
import { RENDERED_COLLECTION_STUB } from '../src/collection-stub.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const PAPER = /^(?:国考|省考)\/.+\.md$/u;
const IMAGE = /\.(?:png|jpe?g|gif|webp|svg|avif|bmp)$/iu;
const FENBI_IMAGE = /\/assets-fenbi-(\d{1,15})\/([0-9a-f]{64})\.(?:png|jpg|gif|webp|svg|avif|bmp)$/u;
const anchors = md => [...md.matchAll(/^#{2,3}\s+第\s*(\d+)\s*题/gmu)].map(m => Number(m[1]));

async function receiptsByPath(candidateRoot) {
  const out = new Map();
  for (const e of await fs.readdir(candidateRoot, { withFileTypes: true }).catch(() => [])) {
    if (!e.isDirectory()) continue;
    try {
      const r = JSON.parse(await fs.readFile(path.join(candidateRoot, e.name, 'receipt.json'), 'utf8'));
      if (r?.path) (out.get(r.path) || out.set(r.path, []).get(r.path)).push(r);
    } catch {}
  }
  return out;
}

function rightsCover(proof, sourceId) {
  if (proof?.schemaVersion !== 1 || proof.allowGitHubStorage !== true || typeof proof.evidence !== 'string' || proof.evidence.trim().length < 8) return false;
  return proof.coverAllCapturedSources === true || (proof.sourceIds || []).map(String).includes(String(sourceId));
}

const atBase = (repo, base, file) => {
  try { return execFileSync('git', ['-C', repo, 'show', `${base}:${file}`], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] }); }
  catch { return null; }
};

export async function fullGate({ repo, base = 'origin/main', candidateRoot, rightsFile }) {
  const structural = await checkContent({ repo, base });
  const reasons = [...structural.reasons];
  if (structural.reasonCount > structural.reasons.length) reasons.push(`more-structural-reasons: ${structural.reasonCount - structural.reasons.length}`);
  let proof = null;
  try { proof = JSON.parse(await fs.readFile(rightsFile, 'utf8')); } catch { reasons.push('rights-file-unreadable'); }
  const changed = changes(repo, base);
  const receipts = await receiptsByPath(candidateRoot);
  let manifest = new Map();
  try {
    const rows = (await fs.readFile(path.join(repo, 'catalog/manifest.jsonl'), 'utf8')).split(/\r?\n/u).filter(Boolean).map(l => JSON.parse(l));
    manifest = new Map(rows.map(r => [r.path, r]));
  } catch {}
  const papers = [];
  for (const { status, file } of changed) {
    if (status === 'D') continue;
    if (PAPER.test(file)) {
      const bytes = await fs.readFile(path.join(repo, file));
      const digest = sha(bytes), md = bytes.toString('utf8');
      const receipt = (receipts.get(file) || []).find(r => r.markdownSha256 === digest);
      if (!receipt) { reasons.push(`no-matching-receipt: ${file}`); continue; }
      if (receipt.grade !== 'A') reasons.push(`receipt-not-grade-A: ${file}`);
      if (!/^\d{1,15}$/u.test(String(receipt.sourceId))) reasons.push(`bad-source-id: ${file}`);
      if (proof && !rightsCover(proof, receipt.sourceId)) reasons.push(`rights-not-covering: ${file}`);
      const q = anchors(md), count = receipt.counts?.sourceQuestions;
      if (q.length !== count || q.some((n, i) => n !== i + 1)) reasons.push(`question-anchors-invalid: ${file}`);
      const before = atBase(repo, base, file);
      if (before !== null && anchors(before).length > q.length) reasons.push(`question-count-regressed: ${file} ${anchors(before).length}->${q.length}`);
      if (RENDERED_COLLECTION_STUB.test(md)) reasons.push(`collection-stub-remains: ${file}`);
      if (manifest.get(file)?.sha256 !== digest) reasons.push(`manifest-sha-mismatch: ${file}`);
      papers.push({ path: file, sourceId: String(receipt.sourceId), questions: q.length, replaced: before !== null });
    } else if (IMAGE.test(file)) {
      if (status !== 'A') { reasons.push(`image-rewritten: ${file}`); continue; }
      const m = file.match(FENBI_IMAGE);
      if (!m) { reasons.push(`image-not-content-addressed: ${file}`); continue; }
      if (sha(await fs.readFile(path.join(repo, file))) !== m[2]) reasons.push(`image-sha-mismatch: ${file}`);
    }
  }
  return { ok: structural.ok && reasons.length === 0, changedFiles: changed.length, papers: papers.length,
    replaced: papers.filter(p => p.replaced).length, reasons: reasons.slice(0, 50), reasonCount: reasons.length, paperList: papers };
}
