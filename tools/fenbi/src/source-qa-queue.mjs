#!/usr/bin/env node
/**
 * Source-QA queue: read metadata-only QA receipts produced by the S1 source owner and
 * decide, per paper, which queue state it belongs to. Read-only and offline.
 *
 * Receipts never contain question text, answer letters or explanations: only status and
 * evidence sha256 values. Self-declared names, self-declared "pass" flags and sha256 of a
 * writable file are NOT evidence. A receipt reaches READY_FOR_PRIVATE_REVIEW only when:
 *   - an Ed25519 attestation signed by a reviewer key in an explicit trust registry binds
 *     the exact current snapshot (sourceId, sourceDocSha, targetPaperSha, prHeadSha,
 *     sourceRevision, report sha),
 *   - a separate approver key (different identity, also registered) signs the rights
 *     approval over the same snapshot,
 *   - the approval file and QA report exist under the trusted root with matching sha,
 *   - the revision chain proves this receipt is current (no replay).
 * A QA signature is never a copyright license; rights remain a separate legal question.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

const HEX64 = /^[0-9a-f]{64}$/u;
const SAFE_ID = /^[0-9A-Za-z_-]{1,64}$/u;
const ALLOWED_BASIS = new Set(['copyright-holder-license', 'copyright-holder-written-permission', 'official-public-release', 'public-domain']);
const FORBIDDEN_BASIS = new Set(['user-self-authorization', 'private-repo-preference', 'user-chose-a']);
const STATES = ['BLOCKED_SOURCE_STUB', 'BLOCKED_ANSWER_CONFLICT', 'BLOCKED_EXPLANATION', 'UNMAPPED', 'STALE_REVISION', 'BLOCKED_RIGHTS', 'READY_FOR_PRIVATE_REVIEW'];
const PRIORITY = ['BLOCKED_SOURCE_STUB', 'BLOCKED_ANSWER_CONFLICT', 'BLOCKED_EXPLANATION', 'UNMAPPED', 'STALE_REVISION', 'BLOCKED_RIGHTS', 'READY_FOR_PRIVATE_REVIEW'];
const hex = v => typeof v === 'string' && HEX64.test(v);

function sortKeys (value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(k => [k, sortKeys(value[k])]));
  }
  return value;
}

export function canonicalPayload (fields) {
  return JSON.stringify(sortKeys(fields));
}

/** Canonical payload the pinned root signs to publish a trust registry. */
export function registryPayload (registry) {
  return {kind: 'trust-registry', scope: registry.scope, version: registry.version, issuedAt: registry.issuedAt, expiresAt: registry.expiresAt, entries: registry.entries};
}

/**
 * Verify a signed registry envelope against a pinned root public key that must come from
 * the Publisher's controlled configuration — never from the receipts file or caller flag.
 */
export function verifyRegistry ({envelope, pinnedRootPublicKeyJwk, expectedVersion = null, now = Date.now()}) {
  if (!pinnedRootPublicKeyJwk) return {ok: false, reason: 'pinned-root-missing'};
  const registry = envelope?.registry;
  const signature = envelope?.signature;
  if (!registry || typeof registry !== 'object' || !signature?.signature) return {ok: false, reason: 'registry-unsigned'};
  if (registry.scope !== 'source-qa') return {ok: false, reason: 'registry-scope-invalid'};
  if (expectedVersion !== null && String(registry.version) !== String(expectedVersion)) return {ok: false, reason: 'registry-version-mismatch'};
  const expires = Date.parse(registry.expiresAt);
  if (!Number.isFinite(expires) || expires <= now) return {ok: false, reason: 'registry-expired'};
  if (!Array.isArray(registry.entries) || registry.entries.length === 0) return {ok: false, reason: 'registry-empty'};
  for (const entry of registry.entries) {
    if (typeof entry?.id !== 'string' || !['reviewer', 'approver'].includes(entry?.role) || typeof entry?.publicKeyJwk !== 'object') {
      return {ok: false, reason: 'registry-entry-invalid'};
    }
  }
  try {
    const key = crypto.createPublicKey({key: pinnedRootPublicKeyJwk, format: 'jwk'});
    const good = crypto.verify(null, Buffer.from(canonicalPayload(registryPayload(registry))), key, Buffer.from(signature.signature, 'base64'));
    if (!good) return {ok: false, reason: 'registry-signature-invalid'};
  } catch { return {ok: false, reason: 'registry-signature-unverifiable'}; }
  return {ok: true, entries: registry.entries, version: registry.version};
}

/** Verify an Ed25519 attestation against a verified registry entries list. Fail closed. */
export function verifyAttestation ({attestation, payload, trustRegistry, requiredRole}) {
  if (!Array.isArray(trustRegistry) || trustRegistry.length === 0) return {ok: false, reason: 'trust-registry-missing'};
  if (!attestation || typeof attestation.signature !== 'string' || !attestation.signature) return {ok: false, reason: 'attestation-missing'};
  const entry = trustRegistry.find(e => e && e.id === attestation.signer && e.role === requiredRole);
  if (!entry) return {ok: false, reason: 'signer-not-trusted:' + String(attestation.signer ?? '?')};
  if (!entry.publicKeyJwk || typeof entry.publicKeyJwk !== 'object') return {ok: false, reason: 'trusted-key-missing'};
  try {
    const key = crypto.createPublicKey({key: entry.publicKeyJwk, format: 'jwk'});
    const ok = crypto.verify(null, Buffer.from(canonicalPayload(payload)), key, Buffer.from(attestation.signature, 'base64'));
    return ok ? {ok: true, signer: entry.id} : {ok: false, reason: 'signature-invalid'};
  } catch { return {ok: false, reason: 'signature-unverifiable'}; }
}

async function verifyEvidence (trustedRoot, relPath, expected) {
  if (!trustedRoot) return 'trusted-root-missing';
  if (typeof relPath !== 'string' || !relPath || relPath.startsWith('/') || relPath.split(/[\\/]/u).includes('..')) return 'evidence-path-invalid';
  let root, real;
  try { root = await fs.realpath(trustedRoot); } catch { return 'trusted-root-unreadable'; }
  try { real = await fs.realpath(path.resolve(root, relPath)); } catch { return 'evidence-unreadable'; }
  if (!real.startsWith(root + path.sep)) return 'evidence-escape';
  const st = await fs.lstat(real);
  if (st.isSymbolicLink() || !st.isFile()) return 'evidence-not-regular-file';
  const digest = crypto.createHash('sha256').update(await fs.readFile(real)).digest('hex');
  if (digest !== expected) return 'evidence-sha-mismatch';
  return null;
}

function snapshotPayload (paper, extra) {
  return {
    sourceId: paper.sourceId,
    sourceDocSha: paper.sourceDocSha,
    targetPaperSha: paper.targetPaperSha,
    prHeadSha: paper.prHeadSha,
    sourceRevision: paper.sourceRevision,
    ...extra
  };
}

/** Structural classification. Returns every finding, not just the first. */
export function classifyReceipt (receipt, {seenSourceIds = new Set(), previousRevision = null, previousQaSha = null, trust = null} = {}) {
  const states = [], reasons = [];
  const add = (state, reason) => { states.push(state); reasons.push(reason); };
  if (!receipt || typeof receipt !== 'object') return {primaryStatus: 'UNMAPPED', states: ['UNMAPPED'], allReasons: ['receipt-invalid']};
  const paper = receipt.paper ?? {};
  const id = paper.identity ?? {};

  if (!SAFE_ID.test(String(paper.sourceId ?? ''))) add('UNMAPPED', 'source-id-invalid');
  if (!hex(paper.sourceDocSha)) add('UNMAPPED', 'source-doc-sha-invalid');
  if (!hex(paper.targetPaperSha)) add('UNMAPPED', 'target-paper-sha-invalid');
  if (typeof paper.prHeadSha !== 'string' || !/^[0-9a-f]{40}$/u.test(paper.prHeadSha)) add('UNMAPPED', 'pr-head-sha-invalid');
  if (typeof paper.sourceRevision !== 'string' || !paper.sourceRevision) add('UNMAPPED', 'source-revision-missing');
  if (typeof id.area !== 'string' || !id.area || /[\\/]/u.test(id.area)) add('UNMAPPED', 'identity-area');
  if (!Number.isInteger(id.year)) add('UNMAPPED', 'identity-year');
  if (!['xingce', 'shenlun'].includes(id.subject)) add('UNMAPPED', 'identity-subject');
  if (typeof id.variant !== 'string' || !id.variant) add('UNMAPPED', 'identity-variant');
  if (seenSourceIds.has(paper.sourceId)) add('UNMAPPED', 'duplicate-source-id');

  // Version binding: a receipt is only usable when the chain proves it is current.
  if (previousRevision === null) add('STALE_REVISION', 'previous-missing');
  else if (previousRevision !== paper.sourceRevision) add('STALE_REVISION', 'revision-changed-since-previous');
  if (receipt.receiptRevision !== undefined && receipt.receiptRevision !== paper.sourceRevision) add('STALE_REVISION', 'receipt-revision-mismatch');
  if (receipt.receiptTargetPaperSha !== undefined && receipt.receiptTargetPaperSha !== paper.targetPaperSha) add('STALE_REVISION', 'target-sha-mismatch');
  if (receipt.receiptPrHeadSha !== undefined && receipt.receiptPrHeadSha !== paper.prHeadSha) add('STALE_REVISION', 'pr-head-mismatch');
  if (receipt.qaBaseReceiptSha !== null && receipt.qaBaseReceiptSha !== undefined) {
    if (!hex(receipt.qaBaseReceiptSha)) add('STALE_REVISION', 'qa-base-sha-invalid');
    else if (previousQaSha !== receipt.qaBaseReceiptSha) add('STALE_REVISION', 'qa-chain-mismatch');
  }

  const questions = Array.isArray(receipt.questions) ? receipt.questions : [];
  if (questions.length === 0) add('UNMAPPED', 'no-question-metadata');
  if (!Number.isInteger(paper.declaredQuestions) || paper.declaredQuestions !== questions.length) add('UNMAPPED', 'declared-question-mismatch');
  const numbers = questions.map(q => Number(q?.number)).sort((a, b) => a - b);
  if (new Set(numbers).size !== numbers.length) add('UNMAPPED', 'duplicate-question-number');
  if (numbers.some((n, i) => n !== i + 1)) add('UNMAPPED', 'question-numbers-not-contiguous');

  const stubs = questions.filter(q => q?.stub === true || q?.match === 'stub').map(q => q.number);
  if (stubs.length) add('BLOCKED_SOURCE_STUB', 'source-stub:' + stubs.join(','));
  const answerConflicts = questions.filter(q => ['conflict', 'present-without-question', 'missing'].includes(q?.answer)).map(q => q.number);
  if (answerConflicts.length) add('BLOCKED_ANSWER_CONFLICT', 'answer-conflict:' + answerConflicts.join(','));
  const noExplanation = questions.filter(q => q?.explanation !== 'verified').map(q => q.number);
  if (noExplanation.length) add('BLOCKED_EXPLANATION', 'explanation-missing:' + noExplanation.join(','));

  const mapping = receipt.mapping ?? {};
  if (mapping.detailsByNumber !== 'verified') add('UNMAPPED', 'details-mapping-unverified');
  if (mapping.materialsByRange !== 'verified') add('UNMAPPED', 'material-mapping-unverified');
  for (const img of Array.isArray(receipt.images) ? receipt.images : []) {
    if (!hex(img?.sha256)) add('UNMAPPED', 'image-sha-missing:' + (img?.path ?? '?'));
  }

  // QA attestation: registry + Ed25519 signature over the current snapshot.
  const qa = receipt.qa ?? {};
  if (qa.verdict !== 'pass') add('BLOCKED_RIGHTS', 'qa-not-passed');
  if (!hex(qa.reportSha256)) add('BLOCKED_RIGHTS', 'qa-report-sha-missing');
  if (typeof qa.reviewer !== 'string' || !qa.reviewer) add('BLOCKED_RIGHTS', 'reviewer-missing');
  let qaSig = {ok: false, signer: null}, apprSig = {ok: false, signer: null};
  if (!trust?.ok) add('BLOCKED_RIGHTS', 'trust-' + (trust?.reason ?? 'pinned-root-missing'));
  else qaSig = verifyAttestation({
    attestation: qa.attestation, trustRegistry: trust.entries, requiredRole: 'reviewer',
    payload: snapshotPayload(paper, {kind: 'source-qa-review', reportSha256: qa.reportSha256, reviewer: qa.reviewer})
  });
  if (trust?.ok && !qaSig.ok) add('BLOCKED_RIGHTS', 'qa-' + qaSig.reason);

  // Rights: allowed basis, holder, redistribution and a separate approver signature.
  const rights = receipt.rights ?? {};
  if (FORBIDDEN_BASIS.has(rights.basis)) add('BLOCKED_RIGHTS', 'rights-basis-forbidden');
  else if (!ALLOWED_BASIS.has(rights.basis)) add('BLOCKED_RIGHTS', 'rights-basis-missing');
  if (!hex(rights.evidenceSha256)) add('BLOCKED_RIGHTS', 'rights-evidence-sha-missing');
  if (typeof rights.holder !== 'string' || !rights.holder) add('BLOCKED_RIGHTS', 'rights-holder-missing');
  if (rights.redistributable !== true) add('BLOCKED_RIGHTS', 'redistribution-not-granted');
  const approval = receipt.approval ?? {};
  if (typeof approval.approvedBy !== 'string' || !approval.approvedBy) add('BLOCKED_RIGHTS', 'approval-missing');
  if (approval.approvedBy === qa.reviewer) add('BLOCKED_RIGHTS', 'self-approval');
  if (!hex(approval.approvalSha256)) add('BLOCKED_RIGHTS', 'approval-sha-missing');
  if (trust?.ok) apprSig = verifyAttestation({
    attestation: approval.attestation, trustRegistry: trust.entries, requiredRole: 'approver',
    payload: snapshotPayload(paper, {kind: 'rights-approval', approvalSha256: approval.approvalSha256, approvedBy: approval.approvedBy})
  });
  if (trust?.ok && !apprSig.ok) add('BLOCKED_RIGHTS', 'approval-' + apprSig.reason);
  if (qaSig.ok && apprSig.ok && qaSig.signer === apprSig.signer) add('BLOCKED_RIGHTS', 'same-signer-for-review-and-approval');

  const allReasons = [...new Set(reasons)];
  if (allReasons.length === 0) return {primaryStatus: 'READY_FOR_PRIVATE_REVIEW', states: ['READY_FOR_PRIVATE_REVIEW'], allReasons: [], qaSigner: qaSig.signer, approverSigner: apprSig.signer};
  const primaryStatus = PRIORITY.find(s => states.includes(s)) ?? 'UNMAPPED';
  return {primaryStatus, states: [...new Set(states)], allReasons, qaSigner: qaSig.ok ? qaSig.signer : null, approverSigner: apprSig.ok ? apprSig.signer : null};
}

export async function evaluateReceipts ({receipts = [], trustedRoot = null, previous = new Map(), trustRegistryEnvelope = null, pinnedRootPublicKeyJwk = null, expectedRegistryVersion = null, now = Date.now()} = {}) {
  const trust = pinnedRootPublicKeyJwk
    ? verifyRegistry({envelope: trustRegistryEnvelope, pinnedRootPublicKeyJwk, expectedVersion: expectedRegistryVersion, now})
    : {ok: false, reason: 'pinned-root-missing'};
  const seen = new Set();
  const rows = [];
  const counts = Object.fromEntries(STATES.map(s => [s, 0]));
  let compared = 0;
  for (const receipt of receipts) {
    const sourceId = receipt?.paper?.sourceId ?? null;
    const previousRevision = sourceId ? previous.get(sourceId + ':revision') ?? null : null;
    const previousQaSha = sourceId ? previous.get(sourceId) ?? null : null;
    let result = classifyReceipt(receipt, {seenSourceIds: seen, previousRevision, previousQaSha, trust});
    if (result.primaryStatus === 'READY_FOR_PRIVATE_REVIEW') {
      const err = await verifyEvidence(trustedRoot, receipt.rights?.evidencePath, receipt.rights?.evidenceSha256) ||
        await verifyEvidence(trustedRoot, receipt.qa?.reportPath, receipt.qa?.reportSha256) ||
        await verifyEvidence(trustedRoot, receipt.approval?.approvalPath, receipt.approval?.approvalSha256);
      if (err) result = {primaryStatus: 'BLOCKED_RIGHTS', states: ['BLOCKED_RIGHTS'], allReasons: [err], qaSigner: result.qaSigner, approverSigner: result.approverSigner};
    }
    if (sourceId) seen.add(sourceId);
    const revisionVerified = previousRevision !== null && previousRevision === receipt?.paper?.sourceRevision;
    if (revisionVerified) compared++;
    const changed = previousRevision !== null && previousRevision !== receipt?.paper?.sourceRevision;
    counts[result.primaryStatus]++;
    rows.push({
      sourceId, area: receipt?.paper?.identity?.area ?? null, year: receipt?.paper?.identity?.year ?? null,
      subject: receipt?.paper?.identity?.subject ?? null,
      primaryStatus: result.primaryStatus,
      states: result.states,
      allReasons: result.allReasons,
      sourceRevision: receipt?.paper?.sourceRevision ?? null,
      effectiveComparison: revisionVerified,
      sourceChecked: revisionVerified,
      sourceChanged: changed,
      // Independent QA review is a quality signal only. It says nothing about whether a
      // copyright holder granted redistribution rights, so licensing stays false.
      independentlyReviewed: result.primaryStatus === 'READY_FOR_PRIVATE_REVIEW',
      readyForPrivateReview: result.primaryStatus === 'READY_FOR_PRIVATE_REVIEW',
      fieldwiseQaPass: result.primaryStatus === 'READY_FOR_PRIVATE_REVIEW',
      rightsClaimReviewed: result.primaryStatus === 'READY_FOR_PRIVATE_REVIEW',
      rightsInstrumentVerified: false,
      licensed: false,
      promoted: false
    });
  }
  const summary = {
    receipts: receipts.length,
    sourceChecked: compared,
    sourceChanged: rows.filter(r => r.sourceChanged).length,
    fieldwiseQaPass: rows.filter(r => r.fieldwiseQaPass).length,
    independentlyReviewed: rows.filter(r => r.independentlyReviewed).length,
    readyForPrivateReview: rows.filter(r => r.readyForPrivateReview).length,
    rightsClaimReviewed: rows.filter(r => r.rightsClaimReviewed).length,
    rightsInstrumentVerified: 0,
    licensed: 0,
    promoted: 0,
    rightsNote: 'licensed is always 0: no independent copyright-holder redistribution instrument is verified by this tool',
    states: counts
  };
  return {ok: true, dryRun: true, trust: {usable: trust.ok, reason: trust.ok ? null : trust.reason, version: trust.version ?? null}, summary, rows};
}

const USAGE = 'usage: source-qa-queue.mjs --receipts FILE [--trust-registry FILE] [--pinned-root FILE] [--expected-registry-version V] [--trusted-root DIR] [--previous FILE] [--dry-run]';

export async function runQueue (argv = process.argv.slice(2)) {
  const opts = {dryRun: true};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (key === '--dry-run') opts.dryRun = true;
    else if (['--receipts', '--trusted-root', '--previous', '--trust-registry', '--pinned-root', '--expected-registry-version'].includes(key)) {
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
  let trustRegistryEnvelope = null, pinnedRootPublicKeyJwk = null;
  if (opts.trust_registry) {
    try { trustRegistryEnvelope = JSON.parse(await fs.readFile(opts.trust_registry, 'utf8')); } catch (e) { return {ok: false, stage: 'input', reason: 'trust-registry-unreadable:' + (e.code || e.message)}; }
  }
  if (opts.pinned_root) {
    try { pinnedRootPublicKeyJwk = JSON.parse(await fs.readFile(opts.pinned_root, 'utf8')); } catch (e) { return {ok: false, stage: 'input', reason: 'pinned-root-unreadable:' + (e.code || e.message)}; }
  }
  const previous = new Map();
  if (opts.previous) {
    try {
      const raw = JSON.parse(await fs.readFile(opts.previous, 'utf8'));
      for (const [id, value] of Object.entries(raw)) {
        if (typeof value === 'string') previous.set(id, value);
        else { previous.set(id, value.qaSha ?? null); previous.set(id + ':revision', value.revision ?? null); }
      }
    } catch (e) { return {ok: false, stage: 'input', reason: 'previous-unreadable:' + (e.code || e.message)}; }
  }
  return evaluateReceipts({receipts, trustedRoot: opts.trusted_root ?? null, previous, trustRegistryEnvelope, pinnedRootPublicKeyJwk, expectedRegistryVersion: opts.expected_registry_version ?? null});
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  runQueue().then(r => { console.log(JSON.stringify(r)); if (!r.ok) process.exitCode = 3; })
    .catch(e => { console.error(e.code || e.message); process.exitCode = 1; });
}

export const __test = {STATES, PRIORITY, ALLOWED_BASIS, FORBIDDEN_BASIS};
