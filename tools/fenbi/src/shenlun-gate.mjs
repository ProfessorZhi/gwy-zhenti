/**
 * Shenlun (essay) gate — Node-native.
 *
 * The S4 adapter (`shenlun-adapter/shenlun_adapter.py`, sha256 231691de…) is a pure Python
 * library with no CLI entry point. Rather than bolt a Python subprocess onto the Node pipeline,
 * the rules that matter for gating are ported here: identity checks, per-field state tallies,
 * asset SHA verification, and the coverage contract. No Python dependency, so the tests run
 * under plain `node --test`.
 *
 * Two independent things are enforced:
 *
 * 1. **Structure.** Shenlun has no A-D options, so no xingce option/label gate may run. Absence is
 *    first-class: every field is `observed` / `absent` / `unknown`, and `absent` counts as known
 *    while `unknown` does not. `explanationsRequired` is false at source — that is a statement
 *    about explanations only, never "the whole paper is fine, publish it".
 *
 * 2. **Rights.** A shenlun paper defaults to `rightsStatus: 'unverified'` and
 *    `cloudStorageBlocked: true`. Free to read on the source is not permission to redistribute.
 *    Nothing but an explicit, paper-specific clearance may lift that.
 *
 * Nothing here writes question text, answers, explanations or images anywhere.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

export const SHENLUN = 'shenlun';
export const STATES = Object.freeze(['observed', 'absent', 'unknown']);
const SHA256_RE = /^[0-9a-f]{64}$/iu;

export const DEFAULT_RIGHTS = Object.freeze({
  rightsStatus: 'unverified',
  cloudStorageBlocked: true,
  rightsEvidence: null,
});

export function defaultShenlunMetadata(extra = {}) {
  return { subject: SHENLUN, ...DEFAULT_RIGHTS, ...extra };
}

export const isShenlun = identity => String(identity?.subject ?? '').trim() === SHENLUN;

/**
 * A shenlun paper may be published only when rights were explicitly cleared, the clearance is
 * recorded as evidence, and the block was lifted for this paper. Anything else blocks.
 */
export function cloudStorageAllowed(metadata = {}) {
  if (metadata.subject !== SHENLUN) return { allowed: true, reason: 'not-shenlun' };
  if (metadata.cloudStorageBlocked !== false) return { allowed: false, reason: 'shenlun-cloud-storage-blocked' };
  if (metadata.rightsStatus !== 'cleared') return { allowed: false, reason: 'shenlun-rights-unverified' };
  if (!metadata.rightsEvidence || String(metadata.rightsEvidence).trim().length < 8) {
    return { allowed: false, reason: 'shenlun-rights-evidence-missing' };
  }
  return { allowed: true, reason: 'shenlun-rights-cleared' };
}

const state = node => (node && STATES.includes(node.state) ? node.state : 'unknown');

function tally(values) {
  const out = { observed: 0, absent: 0, unknown: 0 };
  for (const value of values) out[STATES.includes(value) ? value : 'unknown']++;
  return out;
}

/** Verify declared image assets against files under `root`. Never repairs. */
export function assessShenlunAssets(assets = [], root = null) {
  const problems = [];
  let verified = 0;
  for (const asset of assets) {
    const ref = String(asset?.ref ?? '');
    const want = String(asset?.sha256 ?? '');
    if (!SHA256_RE.test(want)) { problems.push({ code: 'asset-sha-malformed', ref }); continue; }
    if (!ref || ref.split('/').includes('..')) { problems.push({ code: 'asset-ref-invalid', ref }); continue; }
    const file = root ? path.resolve(root, ref) : null;
    if (!file || !file.startsWith(path.resolve(root) + path.sep)) { problems.push({ code: 'asset-ref-invalid', ref }); continue; }
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { problems.push({ code: 'asset-missing', ref }); continue; }
    const got = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
    if (got !== want.toLowerCase()) { problems.push({ code: 'asset-sha-mismatch', ref }); continue; }
    verified++;
  }
  return { ok: problems.length === 0, verified, problems };
}

/**
 * Structural assessment of S1's *metadata* for one shenlun paper.
 * Returns null-ish `{ ok:false, code }` on identity problems so the caller grades `unknown`.
 */
export function assessShenlunStructure(source = {}, { assetRoot = null, expected = {} } = {}) {
  const identity = source.identity || {};
  if (identity.subject !== SHENLUN) return { ok: false, code: 'not-shenlun' };
  for (const key of ['area', 'year', 'variant', 'sourceId']) {
    if (identity[key] == null || String(identity[key]).trim() === '') return { ok: false, code: `identity-${key}-unknown` };
  }
  // A capture may only be graded against the evidence it was pinned to. If the caller pins a
  // value the source does not carry, the pin cannot be verified — that is a mismatch, not a pass.
  for (const key of ['sourceId', 'sourceSha256', 'documentSha256']) {
    if (expected[key] == null) continue;
    if (identity[key] == null || String(expected[key]) !== String(identity[key])) {
      return { ok: false, code: `${key}-mismatch` };
    }
  }
  if (identity.paperId != null && String(identity.paperId) !== String(identity.sourceId)) {
    return { ok: false, code: 'paperId-sourceId-mismatch' };
  }

  const materials = source.materials || [];
  const questions = source.questions || [];
  if (!questions.length) return { ok: false, code: 'no-questions' };

  const answerByQ = new Map((source.referenceAnswers || []).map(a => [a.questionId, a]));
  const explanationByQ = new Map((source.explanations || []).map(e => [e.questionId, e]));
  const images = [];
  for (const q of questions) {
    const answer = answerByQ.get(q.id);
    for (const img of answer?.images || []) images.push(img);
  }

  const coverage = {
    materials: tally(materials.map(m => state(m))),
    prompts: tally(questions.map(q => state(q))),
    referenceAnswers: tally(questions.map(q => (answerByQ.has(q.id) ? state(answerByQ.get(q.id)) : 'unknown'))),
    explanations: tally(questions.map(q => (explanationByQ.has(q.id) ? state(explanationByQ.get(q.id)) : 'unknown'))),
    // Explanations may legitimately be absent at source; that alone never blocks structure.
    explanationsRequired: false,
  };
  coverage.complete = coverage.prompts.unknown === 0 && coverage.materials.unknown === 0
    && coverage.referenceAnswers.unknown === 0;

  const assets = assetRoot ? assessShenlunAssets(images, assetRoot) : { ok: false, verified: 0, problems: [{ code: 'asset-root-missing', ref: '' }] };
  return { ok: true, code: null, identity, coverage, assets, issues: [] };
}

/** Structural grade for shenlun. Deliberately separate from xingce's structureGrade. */
export function shenlunStructuralGrade(assessment = null, metadata = {}) {
  const blockers = [];
  if (assessment == null || assessment.ok === false) {
    blockers.push('shenlun-structure-unknown:' + (assessment?.code ?? 'no-assessment'));
  } else {
    if (assessment.issues?.length) for (const issue of assessment.issues) blockers.push('shenlun-source:' + issue.code);
    if (!assessment.coverage.complete) blockers.push('shenlun-coverage-incomplete');
    if (assessment.assets?.ok === false) {
      for (const problem of assessment.assets.problems) blockers.push('shenlun-asset:' + problem.code);
    }
  }
  const rights = cloudStorageAllowed(metadata);
  const structural = blockers.length ? 'C' : 'A';
  return {
    grade: structural === 'A' && rights.allowed ? 'A' : 'C',
    structuralGrade: structural,
    blockers: [...new Set(blockers)],
    publishable: structural === 'A' && rights.allowed,
    rights,
    holdReason: rights.allowed ? null : rights.reason,
  };
}

/** Receipt fragment for a shenlun paper. Never carries text. */
export function shenlunReceiptFields(assessment, metadata = {}) {
  const graded = shenlunStructuralGrade(assessment, metadata);
  return {
    subject: SHENLUN,
    grade: graded.grade,
    structuralGrade: graded.structuralGrade,
    issues: graded.blockers,
    publishable: graded.publishable,
    holdReason: graded.holdReason,
    rightsStatus: metadata.rightsStatus ?? DEFAULT_RIGHTS.rightsStatus,
    cloudStorageBlocked: metadata.cloudStorageBlocked !== false,
    coverage: assessment?.coverage ?? null,
  };
}
