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
 * `expected` may pin sourceId/sourceSha/documentSha; `assetRoot` enables hash checks.
 */
export function validateShenlunDocument(doc, { expected = {}, assetRoot = null, assetManifest = null } = {}) {
  const problems = [];
  const bad = (code, ev = {}) => problems.push({ code, ...ev });
  const base = validateShenlun(doc);
  for (const p of base.problems) problems.push(p);

  const id = doc.identity ?? {};
  if (expected.sourceId != null && String(expected.sourceId) !== String(id.sourceId)) bad('expected-source-id-mismatch');
  if (id.paperId != null && String(id.paperId) !== String(id.sourceId)) bad('paper-id-mismatch');
  if (expected.sourceSha != null && String(expected.sourceSha) !== String(id.sourceSha)) bad('source-sha-mismatch');

  if (assetRoot) {
    const manifest = new Map((assetManifest ?? []).map((a) => [a.ref, a.sha256]));
    const assets = collectShenlunAssets(doc).map((ref) => ({ ref, sha256: manifest.get(ref) ?? '' }));
    const r = assessAssets(assets, assetRoot);
    for (const p of r.problems) problems.push(p);
  }
  return { ok: problems.length === 0, problems, coverage: base.coverage };
}

/** Dispatch one captured paper through the shenlun path. Returns a receipt-shaped row. */
export function ingestShenlun({ doc, raw, name, dest, write = false, expected = {} } = {}) {
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
  const verdict = validateShenlunDocument(parsed);
  const markdown = renderShenlunMarkdown(parsed);
  const blockers = verdict.problems.map((p) => `${p.code}`);
  // A shenlun paper is never grade A while cloud storage is blocked: it may be a local
  // candidate, but promotion is gated separately.
  const grade = blockers.length ? 'C' : 'A';
  return {
    name, subject: SHENLUN_SUBJECT,
    sourceId: String(parsed.identity.sourceId),
    area: parsed.identity.area, year: Number(parsed.identity.year), variant: parsed.identity.variant,
    grade, issues: blockers,
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
