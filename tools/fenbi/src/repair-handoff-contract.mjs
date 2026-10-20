#!/usr/bin/env node
/**
 * Metadata-only handoff contract between S1 (private source evidence) and the Publisher.
 *
 * A repair candidate may only be marked `independentlyQaComplete && rightsCleared` when
 * every item below is present and verifiable. Anything missing stays PENDING_REVIEW and
 * must not enter ingestion or preflight. This module performs no I/O and accepts no
 * question text; it validates metadata only.
 */
const HEX64 = /^[0-9a-f]{64}$/u;
const SAFE_ID = /^[0-9A-Za-z_-]{1,64}$/u;
const ALLOWED_BASIS = new Set(['copyright-holder-license', 'copyright-holder-written-permission', 'official-public-release', 'public-domain']);
const FORBIDDEN_BASIS = new Set(['user-self-authorization', 'private-repo-preference', 'user-chose-a']);

const hex = v => typeof v === 'string' && HEX64.test(v);

export function evaluateRepairHandoff (candidate = {}) {
  const missing = [];
  const paper = candidate.paper ?? {};
  const identity = candidate.identity ?? {};
  const dom = candidate.sourceDom ?? {};
  const rights = candidate.rights ?? {};
  const image = candidate.images ?? {};
  const qa = candidate.qa ?? {};

  if (!hex(candidate.beforeSha)) missing.push('before-sha-invalid');
  if (!hex(candidate.afterSha)) missing.push('after-sha-invalid');
  if (candidate.beforeSha && candidate.afterSha && candidate.beforeSha === candidate.afterSha) missing.push('no-content-change');

  // Strong same-paper identity: region/year/subject/variant plus an independent source capture.
  if (typeof identity.area !== 'string' || !identity.area || identity.area.length > 40 || /[\\/]/u.test(identity.area)) missing.push('identity-area');
  if (!Number.isInteger(identity.year)) missing.push('identity-year');
  if (!['xingce', 'shenlun'].includes(identity.subject)) missing.push('identity-subject');
  if (typeof identity.variant !== 'string' || !identity.variant) missing.push('identity-variant');
  if (!SAFE_ID.test(String(candidate.sourceId ?? ''))) missing.push('source-id');
  if (!Number.isInteger(candidate.questionCount) || candidate.questionCount !== candidate.afterQuestionCount) missing.push('question-count-mismatch');
  if (!Number.isInteger(paper.declaredQuestions) || paper.declaredQuestions !== candidate.questionCount) missing.push('declared-question-mismatch');

  // Original source DOM proof bound to the same sourceId/capture.
  if (!hex(dom.sha256)) missing.push('source-dom-sha');
  if (dom.sourceId !== candidate.sourceId) missing.push('source-dom-source-id');
  if (typeof dom.capturedBy !== 'string' || !dom.capturedBy) missing.push('source-dom-capturer');
  if (typeof dom.capturedAt !== 'string' || !dom.capturedAt) missing.push('source-dom-time');

  // Every original gap must be gone and every repaired number reviewed independently.
  const gapsBefore = Array.isArray(candidate.gapsBefore) ? candidate.gapsBefore : null;
  const gapsAfter = Array.isArray(candidate.gapsAfter) ? candidate.gapsAfter : null;
  if (!gapsBefore || gapsBefore.length === 0) missing.push('no-original-gaps');
  if (!gapsAfter) missing.push('post-gaps-missing');
  else if (gapsAfter.length !== 0) missing.push('gaps-remain');
  const repaired = Array.isArray(candidate.repairedNumbers) ? candidate.repairedNumbers : [];
  if (repaired.length === 0) missing.push('no-repaired-numbers');
  if (new Set(repaired).size !== repaired.length) missing.push('duplicate-repaired-numbers');
  const reviews = Array.isArray(qa.perQuestion) ? qa.perQuestion : [];
  for (const n of repaired) {
    const review = reviews.find(r => Number(r.number) === Number(n));
    if (!review || !hex(review.approvalSha256) || typeof review.reviewedBy !== 'string' || !review.reviewedBy || review.scope !== 's1-owner') {
      missing.push('per-question-review:' + n);
    }
  }
  if (qa.verdict !== 'pass') missing.push('qa-not-passed');
  if (!hex(qa.reportSha256)) missing.push('qa-report-sha');

  // All referenced images must be local, hashed and match the asset list.
  const refs = Array.isArray(image.refs) ? image.refs : [];
  const assets = Array.isArray(image.assets) ? image.assets : [];
  const byPath = new Map(assets.map(a => [a?.path, a?.sha256]));
  for (const ref of refs) {
    if (typeof ref !== 'string' || ref.startsWith('/') || ref.includes('..') || /^[a-z][a-z0-9+.-]*:/iu.test(ref)) { missing.push('image-ref-unsafe'); continue; }
    if (!hex(byPath.get(ref))) missing.push('image-sha-missing:' + ref);
  }
  for (const a of assets) if (!hex(a?.sha256)) missing.push('image-asset-sha-invalid');

  // Redistribution rights: an allowed basis with evidence, holder and explicit redistribution.
  if (FORBIDDEN_BASIS.has(rights.basis)) missing.push('rights-basis-forbidden');
  if (!ALLOWED_BASIS.has(rights.basis)) missing.push('rights-basis-missing');
  if (!hex(rights.evidenceSha256)) missing.push('rights-evidence-sha');
  if (typeof rights.holder !== 'string' || !rights.holder) missing.push('rights-holder');
  if (rights.redistributable !== true) missing.push('redistribution-not-granted');

  // A shenlun paper with merged sub-questions is never a complete repair.
  if (identity.subject === 'shenlun' && candidate.shenlunSubQuestionsMerged !== false) missing.push('shenlun-subquestions-merged');

  const ready = missing.length === 0;
  return {
    status: ready ? 'READY' : 'PENDING_REVIEW',
    independentlyQaComplete: ready && qa.verdict === 'pass' && reviews.length >= repaired.length,
    rightsCleared: ready && ALLOWED_BASIS.has(rights.basis) && rights.redistributable === true,
    missing: [...new Set(missing)],
    publisherIngestionEligible: false,
    note: 'Metadata contract only. READY still requires S1 to attach the private patch and the Publisher to run its own gate.'
  };
}

/** Publisher-side guard: only a READY contract may proceed to preflight, never ingestion. */
export function publisherGate (candidate) {
  const verdict = evaluateRepairHandoff(candidate);
  if (verdict.status !== 'READY') return {allowed: false, stage: 'PENDING_REVIEW', reasons: verdict.missing};
  return {allowed: true, stage: 'preflight-only', note: 'attach private patch; Publisher gate must re-run'};
}
