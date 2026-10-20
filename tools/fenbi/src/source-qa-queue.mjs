#!/usr/bin/env node
/**
 * Source-QA queue: read metadata-only QA receipts produced by the S1 source owner and
 * decide, per paper, which queue state it belongs to. Read-only and offline.
 *
 * Receipts never contain question text, answer letters or explanations: only status and
 * evidence sha256 values. A receipt is NOT a license; rights must be an allowed basis with
 * a verified evidence file and an approver who is not the same identity as the reviewer.
 *
 * Queue states:
 *   BLOCKED_SOURCE_STUB      source still shows a collection stub
 *   BLOCKED_ANSWER_CONFLICT  answers differ or an answer exists without a question
 *   BLOCKED_EXPLANATION      no real per-question textual explanation
 *   UNMAPPED                 details/image/question mapping not proven
 *   STALE_REVISION           receipt was produced for a different revision/sha
 *   BLOCKED_RIGHTS           rights missing, forbidden, or not independently approved
 *   READY_FOR_PRIVATE_REVIEW all checks pass; still only a private review handoff
 */
import fs from 'node:fs/promises';
import path from 'node:path';

const HEX64 = /^[0-9a-f]{64}$/u;
const SAFE_ID = /^[0-9A-Za-z_-]{1,64}$/u;
const ALLOWED_BASIS = new Set(['copyright-holder-license', 'copyright-holder-written-permission', 'official-public-release', 'public-domain']);
const FORBIDDEN_BASIS = new Set(['user-self-authorization', 'private-repo-preference', 'user-chose-a']);
const STATES = ['BLOCKED_SOURCE_STUB', 'BLOCKED_ANSWER_CONFLICT', 'BLOCKED_EXPLANATION', 'UNMAPPED', 'STALE_REVISION', 'BLOCKED_RIGHTS', 'READY_FOR_PRIVATE_REVIEW'];
const hex = v => typeof v === 'string' && HEX64.test(v);
const sha = async file => (await import('node:crypto')).createHash('sha256').update(await fs.readFile(file)).digest('hex');

async function verifyEvidence (trustedRoot, relPath, expected) {
  if (!trustedRoot) return 'trusted-root-missing';
  if (typeof relPath !== 'string' || !relPath || relPath.startsWith('/') || relPath.split(/[\\/]/u).includes('..')) return 'evidence-path-invalid';
  let root, real;
  try { root = await fs.realpath(trustedRoot); } catch { return 'trusted-root-unreadable'; }
  try { real = await fs.realpath(path.resolve(root, relPath)); } catch { return 'evidence-unreadable'; }
  if (!real.startsWith(root + path.sep)) return 'evidence-escape';
  const st = await fs.lstat(real);
  if (st.isSymbolicLink() || !st.isFile()) return 'evidence-not-regular-file';
  if ((await sha(real)) !== expected) return 'evidence-sha-mismatch';
  return null;
}

/** Validate the receipt envelope and per-question metadata. Pure; no I/O. */
export function classifyReceipt (receipt, {seenSourceIds = new Set(), previousQaSha = null} = {}) {
  const reasons = [];
  if (!receipt || typeof receipt !== 'object') return {state: 'UNMAPPED', reasons: ['receipt-invalid']};
  const paper = receipt.paper ?? {};
  const id = paper.identity ?? {};
  if (!SAFE_ID.test(String(paper.sourceId ?? ''))) reasons.push('source-id-invalid');
  if (!hex(paper.sourceDocSha)) reasons.push('source-doc-sha-invalid');
  if (!hex(paper.targetPaperSha)) reasons.push('target-paper-sha-invalid');
  if (typeof paper.prHeadSha !== 'string' || !/^[0-9a-f]{40}$/u.test(paper.prHeadSha)) reasons.push('pr-head-sha-invalid');
  if (typeof paper.sourceRevision !== 'string' || !paper.sourceRevision) reasons.push('source-revision-missing');
  if (typeof id.area !== 'string' || !id.area || /[\\/]/u.test(id.area)) reasons.push('identity-area');
  if (!Number.isInteger(id.year)) reasons.push('identity-year');
  if (!['xingce', 'shenlun'].includes(id.subject)) reasons.push('identity-subject');
  if (typeof id.variant !== 'string' || !id.variant) reasons.push('identity-variant');
  if (seenSourceIds.has(paper.sourceId)) reasons.push('duplicate-source-id');
  if (reasons.length) return {state: 'UNMAPPED', reasons};

  const stale = [];
  if (receipt.qaBaseReceiptSha !== null && receipt.qaBaseReceiptSha !== undefined && !hex(receipt.qaBaseReceiptSha)) stale.push('qa-base-sha-invalid');
  if (previousQaSha && receipt.qaBaseReceiptSha !== previousQaSha) stale.push('qa-chain-mismatch');
  if (receipt.receiptRevision && receipt.receiptRevision !== paper.sourceRevision) stale.push('receipt-revision-mismatch');
  if (receipt.targetPaperSha && receipt.targetPaperSha !== paper.targetPaperSha) stale.push('target-sha-mismatch');
  if (stale.length) return {state: 'STALE_REVISION', reasons: stale};

  const questions = Array.isArray(receipt.questions) ? receipt.questions : [];
  if (questions.length === 0) return {state: 'UNMAPPED', reasons: ['no-question-metadata']};
  if (!Number.isInteger(paper.declaredQuestions) || paper.declaredQuestions !== questions.length) {
    return {state: 'UNMAPPED', reasons: ['declared-question-mismatch']};
  }
  const numbers = questions.map(q => Number(q.number)).sort((a, b) => a - b);
  if (numbers.some((n, i) => n !== i + 1)) return {state: 'UNMAPPED', reasons: ['question-numbers-not-contiguous']};
  if (new Set(numbers).size !== numbers.length) return {state: 'UNMAPPED', reasons: ['duplicate-question-number']};

  const stubs = questions.filter(q => q.stub === true || q.match === 'stub').map(q => q.number);
  if (stubs.length) return {state: 'BLOCKED_SOURCE_STUB', reasons: ['source-stub:' + stubs.join(',')]};

  const answerConflicts = questions.filter(q => q.answer === 'conflict' || q.answer === 'present-without-question' || q.answer === 'missing').map(q => q.number);
  if (answerConflicts.length) return {state: 'BLOCKED_ANSWER_CONFLICT', reasons: ['answer-conflict:' + answerConflicts.join(',')]};

  const noExplanation = questions.filter(q => q.explanation !== 'verified').map(q => q.number);
  if (noExplanation.length) return {state: 'BLOCKED_EXPLANATION', reasons: ['explanation-missing:' + noExplanation.join(',')]};

  const mapping = receipt.mapping ?? {};
  const mappingReasons = [];
  if (mapping.detailsByNumber !== 'verified') mappingReasons.push('details-mapping-unverified');
  if (mapping.materialsByRange !== 'verified') mappingReasons.push('material-mapping-unverified');
  const images = Array.isArray(receipt.images) ? receipt.images : [];
  for (const img of images) if (!hex(img?.sha256)) mappingReasons.push('image-sha-missing:' + (img?.path ?? '?'));
  if (mappingReasons.length) return {state: 'UNMAPPED', reasons: mappingReasons};

  const qa = receipt.qa ?? {};
  if (qa.verdict !== 'pass' || !hex(qa.reportSha256)) return {state: 'UNMAPPED', reasons: ['qa-not-passed']};
  if (typeof qa.reviewer !== 'string' || !qa.reviewer) return {state: 'UNMAPPED', reasons: ['reviewer-missing']};

  const rights = receipt.rights ?? {};
  if (FORBIDDEN_BASIS.has(rights.basis)) return {state: 'BLOCKED_RIGHTS', reasons: ['rights-basis-forbidden']};
  if (!ALLOWED_BASIS.has(rights.basis)) return {state: 'BLOCKED_RIGHTS', reasons: ['rights-basis-missing']};
  if (!hex(rights.evidenceSha256)) return {state: 'BLOCKED_RIGHTS', reasons: ['rights-evidence-sha-missing']};
  if (typeof rights.holder !== 'string' || !rights.holder) return {state: 'BLOCKED_RIGHTS', reasons: ['rights-holder-missing']};
  if (rights.redistributable !== true) return {state: 'BLOCKED_RIGHTS', reasons: ['redistribution-not-granted']};
  const approval = receipt.approval ?? {};
  if (typeof approval.approvedBy !== 'string' || !approval.approvedBy) return {state: 'BLOCKED_RIGHTS', reasons: ['approval-missing']};
  if (approval.approvedBy === qa.reviewer) return {state: 'BLOCKED_RIGHTS', reasons: ['self-approval']};
  if (!hex(approval.approvalSha256)) return {state: 'BLOCKED_RIGHTS', reasons: ['approval-sha-missing']};

  return {state: 'READY_FOR_PRIVATE_REVIEW', reasons: []};
}

/** Full evaluation including trusted-root evidence checks. */
export async function evaluateReceipts ({receipts = [], trustedRoot = null, previous = new Map()} = {}) {
  const seen = new Set();
  const rows = [];
  const counts = Object.fromEntries(STATES.map(s => [s, 0]));
  for (const receipt of receipts) {
    const sourceId = receipt?.paper?.sourceId ?? null;
    const previousQaSha = sourceId ? previous.get(sourceId) ?? null : null;
    const priorRevision = previous.get(sourceId + ':revision') ?? null;
    let result = classifyReceipt(receipt, {seenSourceIds: seen, previousQaSha});
    if (result.state === 'READY_FOR_PRIVATE_REVIEW') {
      const rightsErr = await verifyEvidence(trustedRoot, receipt.rights?.evidencePath, receipt.rights?.evidenceSha256);
      const qaErr = await verifyEvidence(trustedRoot, receipt.qa?.reportPath, receipt.qa?.reportSha256);
      const approvalErr = await verifyEvidence(trustedRoot, receipt.approval?.approvalPath, receipt.approval?.approvalSha256);
      const evidenceErr = rightsErr || qaErr || approvalErr;
      if (evidenceErr) result = {state: 'BLOCKED_RIGHTS', reasons: [evidenceErr]};
    }
    if (sourceId) seen.add(sourceId);
    const changed = priorRevision !== null && priorRevision !== receipt?.paper?.sourceRevision;
    counts[result.state]++;
    rows.push({
      sourceId, area: receipt?.paper?.identity?.area ?? null, year: receipt?.paper?.identity?.year ?? null,
      subject: receipt?.paper?.identity?.subject ?? null, state: result.state, reasons: result.reasons,
      sourceRevision: receipt?.paper?.sourceRevision ?? null, changed,
      sourceChecked: changed, sourceChanged: changed,
      fieldwiseQaPass: result.state === 'READY_FOR_PRIVATE_REVIEW',
      licensed: result.state === 'READY_FOR_PRIVATE_REVIEW', promoted: false
    });
  }
  const summary = {
    receipts: receipts.length,
    sourceChecked: rows.filter(r => r.sourceChecked).length,
    sourceChanged: rows.filter(r => r.sourceChanged).length,
    fieldwiseQaPass: rows.filter(r => r.fieldwiseQaPass).length,
    licensed: rows.filter(r => r.licensed).length,
    promoted: 0,
    states: counts
  };
  return {ok: true, dryRun: true, summary, rows};
}

const USAGE = 'usage: source-qa-queue.mjs --receipts FILE [--trusted-root DIR] [--previous FILE] [--dry-run]';

export async function runQueue (argv = process.argv.slice(2)) {
  const opts = {dryRun: true};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (key === '--dry-run') opts.dryRun = true;
    else if (['--receipts', '--trusted-root', '--previous'].includes(key)) {
      const value = argv[++i];
      if (!value) return {ok: false, stage: 'usage', reason: 'missing-value:' + key, usage: USAGE};
      opts[key.slice(2).replaceAll('-', '_')] = value;
    } else return {ok: false, stage: 'usage', reason: 'unknown-option:' + key, usage: USAGE};
  }
  if (!opts.receipts) return {ok: false, stage: 'usage', reason: 'missing-receipts', usage: USAGE};
  let receipts;
  try {
    receipts = (await fs.readFile(opts.receipts, 'utf8')).split(/\r?\n/u).filter(Boolean).map((line, i) => {
      try { return JSON.parse(line); } catch { throw Object.assign(new Error('receipt-unparsable:' + (i + 1)), {code: 'receipt-unparsable'}); }
    });
  } catch (e) { return {ok: false, stage: 'input', reason: e.code || e.message}; }
  let previous = new Map();
  if (opts.previous) {
    try {
      const raw = JSON.parse(await fs.readFile(opts.previous, 'utf8'));
      for (const [id, value] of Object.entries(raw)) {
        if (typeof value === 'string') previous.set(id, value);
        else { previous.set(id, value.qaSha ?? null); previous.set(id + ':revision', value.revision ?? null); }
      }
    } catch (e) { return {ok: false, stage: 'input', reason: 'previous-unreadable:' + (e.code || e.message)}; }
  }
  return evaluateReceipts({receipts, trustedRoot: opts.trusted_root ?? null, previous});
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  runQueue().then(r => { console.log(JSON.stringify(r)); if (!r.ok) process.exitCode = 3; })
    .catch(e => { console.error(e.code || e.message); process.exitCode = 1; });
}

export const __test = {STATES, ALLOWED_BASIS, FORBIDDEN_BASIS};
