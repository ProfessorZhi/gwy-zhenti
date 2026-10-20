// Integration glue between the production fenbi pipeline and the shenlun adapter.
//
// Rules enforced here (mirrored by the offline tests):
//   * subject dispatch: a shenlun document never enters the xingce assembly path;
//   * validation: shenlun has materials/prompts/reference answers, never A-D options;
//   * identity: paperId/sourceId/sourceSha/documentSha must agree with the capture;
//   * publishing: refuse cloud promotion unless rights are cleared AND storage unblocked.

import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import {
  parseShenlun, validateShenlun, renderShenlunMarkdown, assessAssets,
  assertCloudPublishable, coverage, SHENLUN_SUBJECT, ShenlunError,
} from './shenlun-adapter.mjs';

export { ShenlunError, SHENLUN_SUBJECT };

export const isShenlun = (identity) => identity?.subject === SHENLUN_SUBJECT;

const sha256 = (buf) => createHash('sha256').update(buf).digest('hex');

/** Collect the asset refs a shenlun document declares. */
export function collectShenlunAssets(doc = {}) {
  const refs = new Set();
  for (const a of doc.referenceAnswers ?? []) for (const src of a.answerImages ?? []) if (src) refs.add(src);
  for (const m of doc.materials ?? []) for (const a of m.assets ?? []) if (a?.src) refs.add(a.src);
  return [...refs];
}

/**
 * Validate a shenlun document. Never requires options; explanation absence is legal.
 * `expected` may pin sourceId/sourceSha/documentSha and independently observed
 * prompt/answer counts; `assetRoot` enables hash checks. Count matching is not
 * proof of semantic answer correctness or of publication rights.
 */
export function validateShenlunDocument(doc, { expected = {}, assetRoot = null, assetManifest = null, evidenceBytes = null } = {}) {
  const problems = [];
  const bad = (code, ev = {}) => problems.push({ code, ...ev });
  const base = validateShenlun(doc);
  for (const p of base.problems) problems.push(p);

  const id = doc.identity ?? {};
  const countsClaimed = expected.observedPromptCount != null || expected.observedAnswerCount != null;
  const evidenceSha = expected.observedEvidenceSha256;
  // Bind caller-reported counts to the immutable raw DOM snapshot from which they were
  // extracted. A digest alone does NOT prove the extraction algorithm or semantics.
  if (countsClaimed) {
    if (!(Buffer.isBuffer(evidenceBytes) || evidenceBytes instanceof Uint8Array) ||
        !/^[0-9a-f]{64}$/u.test(String(evidenceSha ?? '')))
      bad('observed-evidence-unbound');
    else if (sha256(evidenceBytes) !== evidenceSha)
      bad('observed-evidence-sha-mismatch');
  }
  if (expected.sourceId != null && String(expected.sourceId) !== String(id.sourceId)) bad('expected-source-id-mismatch');
  if (id.paperId != null && String(id.paperId) !== String(id.sourceId)) bad('paper-id-mismatch');
  if (expected.sourceSha != null && String(expected.sourceSha) !== String(id.sourceSha)) bad('source-sha-mismatch');
  // A visible DOM can contain several distinct prompts under one captured question.
  // Only compare independently observed counts; never infer them from this same doc.
  if (expected.observedPromptCount != null) {
    if (!Number.isSafeInteger(expected.observedPromptCount) || expected.observedPromptCount < 1)
      bad('observed-prompt-count-invalid');
    else if ((doc.questions ?? []).length !== expected.observedPromptCount)
      bad('observed-prompt-count-mismatch', {
        expected: expected.observedPromptCount, represented: (doc.questions ?? []).length,
      });
  }
  if (expected.observedAnswerCount != null) {
    if (!Number.isSafeInteger(expected.observedAnswerCount) || expected.observedAnswerCount < 0)
      bad('observed-answer-count-invalid');
    else {
      const represented = (doc.referenceAnswers ?? []).filter(a => a.state === 'observed').length;
      if (represented !== expected.observedAnswerCount)
        bad('observed-answer-count-mismatch', { expected: expected.observedAnswerCount, represented });
    }
  }

  if (assetRoot) {
    const manifest = new Map((assetManifest ?? []).map((a) => [a.ref, a.sha256]));
    const assets = collectShenlunAssets(doc).map((ref) => ({ ref, sha256: manifest.get(ref) ?? '' }));
    const r = assessAssets(assets, assetRoot);
    for (const p of r.problems) problems.push(p);
  }
  return { ok: problems.length === 0, problems, coverage: base.coverage };
}

/** Dispatch one captured paper through the shenlun path. Returns a receipt-shaped row. */
export function ingestShenlun({ doc, raw, name, dest, write = false, expected = {}, evidenceBytes = null } = {}) {
  const sourceSha = sha256(raw ?? Buffer.from(JSON.stringify(doc)));
  let parsed;
  try {
    parsed = parseShenlun(doc, { expected: { ...expected, sourceSha: undefined } });
  } catch (e) {
    // A malformed capture is a graded-C receipt with a reason code, never a crash in the batch.
    return {
      name, subject: SHENLUN_SUBJECT, grade: 'C',
      issues: [e.code || e.message || 'shenlun-parse-error'],
      sourceId: String(doc?.identity?.id ?? doc?.identity?.sourceId ?? ''),
      area: doc?.identity?.area ?? null, year: doc?.identity?.year ?? null,
      variant: doc?.identity?.variant ?? null,
      counts: { materials: 0, questions: 0, referenceAnswers: 0, explanations: 0 },
      rightsStatus: doc?.rightsStatus ?? 'unverified',
      cloudStorageBlocked: doc?.cloudStorageBlocked ?? true,
      sourceSha256: sourceSha, markdownSha256: null, write, dest,
    };
  }
  const verdict = validateShenlunDocument(parsed, { expected, evidenceBytes });
  const markdown = renderShenlunMarkdown(parsed);
  const blockers = verdict.problems.map((p) => `${p.code}`);
  // Grade A means local structural checks only, NOT independent content QA or
  // permission to publish. Rights remain a separate fail-closed promotion gate.
  const grade = blockers.length ? 'C' : 'A';
  return {
    name, subject: SHENLUN_SUBJECT,
    sourceId: String(parsed.identity.sourceId),
    area: parsed.identity.area, year: Number(parsed.identity.year), variant: parsed.identity.variant,
    grade, issues: blockers,
    boundaryEvidence: {
      promptCount: expected.observedPromptCount ?? null,
      answerCount: expected.observedAnswerCount ?? null,
      observedEvidenceSha256: expected.observedEvidenceSha256 ?? null,
      status: blockers.includes('observed-evidence-unbound') ||
        blockers.includes('observed-evidence-sha-mismatch') ? 'unbound' :
        blockers.some(code => code.endsWith('-count-invalid')) ? 'invalid' :
        blockers.some(code => code.endsWith('-count-mismatch')) ? 'mismatch' :
        (expected.observedPromptCount == null || expected.observedAnswerCount == null
          ? 'unverified' : 'counts-match-snapshot-bound-only'),
    },
    counts: {
      materials: parsed.materials.length,
      questions: parsed.questions.length,
      referenceAnswers: parsed.referenceAnswers.length,
      explanations: parsed.explanations.length,
      coverage: parsed.coverage,
    },
    rightsStatus: parsed.identity.rightsStatus,
    cloudStorageBlocked: parsed.identity.cloudStorageBlocked,
    markdownSha256: sha256(Buffer.from(markdown)),
    sourceSha256: sourceSha,
    doc: parsed,
    markdown,
    write,
    dest,
  };
}

/** Throwing gate used by promote. */
export function assertShenlunPromotable(doc) {
  return assertCloudPublishable(doc);
}

export function coverageOf(doc) { return coverage(doc); }
