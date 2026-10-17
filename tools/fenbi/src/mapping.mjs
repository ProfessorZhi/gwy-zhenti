/**
 * Candidate one-to-one question mapping between a captured source paper and a repository paper,
 * for the cases the strict aligner deliberately refuses to decide: the source is out of order, only
 * part of it was captured, or it is a different recollection of the same exam.
 *
 * This module is ADVISORY ONLY. `comparePaper` in align.mjs remains the only thing that may report
 * `matched`/`verified`; this produces a reviewable mapping proposal and its counts, and never a
 * verification. It also refuses to propose anything at all when the caller has not cleared the
 * source's rights, and it will not consider a row the caller's own eligibility gate rejects (a
 * collection stub, a restricted paper, an unobserved slot).
 *
 * Usage:
 *   const report = buildMappingReport({
 *     source: { label: '…', questions: [...] },
 *     repository: { label: '…', questions: [...] },
 *     sourceRights: 'cleared',
 *     isEligible: (q) => !isCollectionStub(plainText(q.contentHtml)),   // caller's own gate
 *   });
 *   // report.assignments / report.ambiguous / report.unmatchedSource / report.counts
 *
 * Nothing here reads the network, a browser or a profile.
 */
import { createHash } from 'node:crypto';
import { normalizeComparisonText } from './align.mjs';

export const MAPPING_SCHEMA_VERSION = 1;

export const DEFAULT_POLICY = Object.freeze({
  // A composite score of 1 with both text signals exactly equal is the only auto-acceptable case.
  candidateFloor: 0.72,
  // Top two candidates closer than this are not a decision; they are a question for a human.
  ambiguityMargin: 0.08,
  // Signals are re-weighted over the ones that were actually observable, so an unobserved
  // dimension is "no evidence" rather than "zero similarity".
  weights: Object.freeze({ stem: 0.55, options: 0.25, materials: 0.12, images: 0.08 }),
});

const sha = (value) => createHash('sha256').update(String(value ?? '')).digest('hex');
const str = (value) => value == null ? '' : String(value);
const clamp01 = (value) => Math.min(1, Math.max(0, value));

/** Character bigram Dice coefficient over the normalised text. 1 = identical, 0 = nothing shared. */
function similarity(a, b) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  if (a.length < 2 || b.length < 2) return a === b ? 1 : 0;
  const grams = (text) => {
    const out = new Map();
    for (let index = 0; index < text.length - 1; index++) {
      const gram = text.slice(index, index + 2);
      out.set(gram, (out.get(gram) ?? 0) + 1);
    }
    return out;
  };
  const left = grams(a), right = grams(b);
  let shared = 0, total = 0;
  for (const [gram, count] of left) { shared += Math.min(count, right.get(gram) ?? 0); total += count; }
  for (const count of right.values()) total += count;
  return total ? (2 * shared) / total : 0;
}

const IMAGE_TOKEN_TEXT = '⟦IMAGE⟧';
const textOf = (html) => normalizeComparisonText(html).strict;
// Every picture collapses to the same placeholder token, so the token is not text evidence: two
// different pictures would otherwise look identical (the PR #42 defect). Strip it before comparing.
const textOnly = (html) => normalizeComparisonText(html).strict.split(IMAGE_TOKEN_TEXT).join('').trim();
const imagesOf = (html) => normalizeComparisonText(html).images;

/**
 * The only image evidence this verifier accepts is a **content** manifest: a SHA-256 of the bytes,
 * declared verified against the same authorised source. A reference path is never a content hash —
 * the same path can serve different bytes and the same bytes can live at different paths.
 */
function imageManifest(question) {
  const entries = question?.imageBytes;
  if (!Array.isArray(entries)) return null;
  const hashes = [];
  for (const entry of entries) {
    const hash = typeof entry === 'string' ? '' : str(entry?.sha256).toLowerCase();
    if (!/^[0-9a-f]{64}$/u.test(hash)) return null;      // malformed manifest: trust none of it
    if (entry?.verified !== true) return null;           // bytes not verified against the source
    hashes.push(hash);
  }
  return hashes;
}

function optionSignal(sourceOptions = [], repositoryOptions = []) {
  if (!sourceOptions.length && !repositoryOptions.length) return { available: false, score: 0, contradictory: false };
  if (!sourceOptions.length || !repositoryOptions.length) return { available: true, score: 0, contradictory: true };
  const sourceLabels = sourceOptions.map((option) => str(option.label));
  const repositoryLabels = repositoryOptions.map((option) => str(option.label));
  // A different label set or order is a contradiction, not a low score: the two sides are not the
  // same question shape, so no amount of text similarity should be able to override it.
  const contradictory = sourceLabels.join() !== repositoryLabels.join();
  if (contradictory) return { available: true, score: 0, contradictory: true };
  const perOption = sourceOptions.map((option, index) =>
    similarity(textOf(option.contentHtml), textOf(repositoryOptions[index].contentHtml)));
  return { available: true, contradictory: false, score: perOption.reduce((a, b) => a + b, 0) / perOption.length };
}

function materialSignal(source, repository) {
  const sourceIds = Array.isArray(source.materialIds) ? source.materialIds : [];
  const repositoryIds = Array.isArray(repository.materialIds) ? repository.materialIds : [];
  if (!sourceIds.length && !repositoryIds.length) return { available: false, score: 0, contradictory: false };
  const sourceHashes = new Set(sourceIds.map((id) => sha(str(id))));
  const repositoryHashes = repositoryIds.map((id) => sha(str(id)));
  if (!sourceHashes.size || !repositoryHashes.length) return { available: true, score: 0, contradictory: false };
  const shared = repositoryHashes.filter((hash) => sourceHashes.has(hash)).length;
  return { available: true, contradictory: false, score: shared / Math.max(sourceHashes.size, repositoryHashes.length) };
}

function imageSignal(source, repository) {
  const basis = 'image-content-sha256';
  // Distinguish "this question has no pictures at all" (nothing to compare, expected) from
  // "pictures are referenced but their bytes were never verified" (evidence unavailable).
  const referenceCount = (question) => [
    ...imagesOf(question?.contentHtml ?? ''),
    ...(question?.options ?? []).flatMap((option) => imagesOf(option?.contentHtml ?? '')),
  ].length;
  if (!referenceCount(source) && !referenceCount(repository)) {
    return { available: false, score: 0, contradictory: false, basis, reason: 'no-images-on-either-side' };
  }
  const sourceHashes = imageManifest(source), repositoryHashes = imageManifest(repository);
  // No trustworthy manifest on either side: this is "no evidence", not "no match". Scoring it 0
  // would silently dilute a pair whose text is a perfect match.
  if (sourceHashes === null || repositoryHashes === null) {
    return { available: false, score: 0, contradictory: false, basis,
      reason: sourceHashes === null && repositoryHashes === null ? 'image-bytes-not-verified' : 'image-manifest-missing-on-one-side' };
  }
  if (!sourceHashes.length || !repositoryHashes.length) {
    return { available: true, score: 0, contradictory: false, basis, reason: 'images-present-on-one-side-only' };
  }
  const shared = repositoryHashes.filter((hash) => sourceHashes.includes(hash)).length;
  return { available: true, contradictory: false, basis,
    score: shared / Math.max(sourceHashes.length, repositoryHashes.length) };
}

/**
 * Score one candidate pair. `number` is deliberately NOT part of the score: the whole point of this
 * verifier is papers whose numbering does not correspond, so using it would reintroduce the guess it
 * exists to prevent. It is reported separately as an observation only.
 */
export function scorePair(source, repository) {
  const sourceText = textOnly(source.contentHtml), repositoryText = textOnly(repository.contentHtml);
  const stem = sourceText && repositoryText
    ? { available: true, score: similarity(sourceText, repositoryText), contradictory: false, basis: 'text' }
    : { available: false, score: 0, contradictory: false, basis: 'no-text-beside-images' };
  const options = optionSignal(source.options, repository.options);
  const materials = materialSignal(source, repository);
  const images = imageSignal(source, repository);
  const signals = { stem, options, materials, images };
  // A different option label set or order means the two sides are not the same question shape.
  // No amount of stem similarity may override that, so the pair is not mappable at all.
  if (signals.options.contradictory) return { score: 0, grade: 'weak', signals, contradictory: true };
  const usable = Object.entries(signals).filter(([, value]) => value.available && !value.contradictory);
  if (!stem.score && !options.score && !materials.score && !images.score) {
    return { score: 0, grade: 'none', signals, contradictory: Object.values(signals).some((value) => value.contradictory) };
  }
  const weightTotal = usable.reduce((sum, [name]) => sum + DEFAULT_POLICY.weights[name], 0);
  const score = weightTotal ? usable.reduce((sum, [name, value]) => sum + value.score * DEFAULT_POLICY.weights[name], 0) / weightTotal : 0;
  // For an image-only stem the exact evidence is byte-identical verified pictures, never the token.
  const stemExact = stem.available ? stem.score === 1 : (images.available && images.score === 1);
  const exact = stemExact && (!options.available || (options.score === 1 && !options.contradictory));
  const independent = usable.filter(([, value]) => value.score > 0).length;
  const grade = exact ? 'exact' : !Object.values(signals).some((value) => value.contradictory) && independent >= 2 ? 'strong' : 'weak';
  return { score: clamp01(score), grade, signals, contradictory: Object.values(signals).some((value) => value.contradictory) };
}

function usableSourceRow(question) {
  const hasStem = Boolean(textOf(question.contentHtml));
  const hasOptions = (question.options ?? []).some((option) => textOf(option.contentHtml));
  const hasImages = Boolean(imagesOf(question.contentHtml).length);
  return hasStem || hasOptions || hasImages;
}

const numbersOf = (questions) => questions.map((question) => question.number).filter((n) => Number.isInteger(n));
const duplicatesOf = (values) => [...new Set(values.filter((value, index) => values.indexOf(value) !== index))];

/**
 * Build the advisory mapping report. See the module comment for the workflow.
 *
 * @param {object} input
 * @param {{label?: string, questions: object[]}} input.source
 * @param {{label?: string, questions: object[]}} input.repository
 * @param {'cleared'|'restricted'|'unknown'} input.sourceRights  Must be assessed by the operator.
 * @param {(question: object) => boolean} input.isEligible  The caller's own gate (stub, rights,
 *   observation state). A row it rejects never enters the candidate pool.
 * @param {object} [input.policy]
 */
export function buildMappingReport({ source, repository, sourceRights, isEligible, policy = DEFAULT_POLICY } = {}) {
  if (!source || !Array.isArray(source.questions) || !repository || !Array.isArray(repository.questions)) {
    throw new Error('buildMappingReport needs source.questions and repository.questions');
  }
  if (typeof isEligible !== 'function') {
    // Refusing an implicit "everything is eligible" default keeps this from silently bypassing the
    // stub / rights / observation gates the caller already has.
    throw new Error('buildMappingReport needs an explicit isEligible predicate');
  }
  if (!['cleared', 'restricted', 'unknown'].includes(sourceRights)) {
    throw new Error('sourceRights must be assessed as cleared, restricted or unknown');
  }

  const sourceRows = source.questions.map((question, index) => ({ question, index }));
  const repositoryRows = repository.questions;
  const rejected = [];
  const eligible = sourceRows.filter(({ question }) => {
    if (!usableSourceRow(question)) { rejected.push({ number: question.number ?? null, id: str(question.id) || null, reason: 'no-comparable-content' }); return false; }
    if (!isEligible(question)) { rejected.push({ number: question.number ?? null, id: str(question.id) || null, reason: 'rejected-by-eligibility-gate' }); return false; }
    return true;
  });

  const sourceNumbers = numbersOf(eligible.map(({ question }) => question));
  const repositoryNumbers = numbersOf(repositoryRows);
  const conflicts = [];
  for (const number of duplicatesOf(sourceNumbers)) conflicts.push({ scope: 'source', kind: 'duplicate-number', number });
  for (const number of duplicatesOf(repositoryNumbers)) conflicts.push({ scope: 'repository', kind: 'duplicate-number', number });

  const pairings = [];
  for (const { question: sourceQuestion, index: sourceIndex } of eligible) {
    for (const [repositoryIndex, repositoryQuestion] of repositoryRows.entries()) {
      const scored = scorePair(sourceQuestion, repositoryQuestion);
      if (scored.score <= 0) continue;
      pairings.push({ sourceIndex, repositoryIndex, sourceQuestion, repositoryQuestion, ...scored });
    }
  }
  // Highest score first; ties broken by source order then repository order so the run is repeatable.
  pairings.sort((a, b) => b.score - a.score || a.sourceIndex - b.sourceIndex || a.repositoryIndex - b.repositoryIndex);

  // Rights veto: structure is reported, but no proposal is emitted.
  const blocked = sourceRights === 'cleared' ? null : 'source-rights-not-cleared';
  const assignedSource = new Set(), assignedRepository = new Set();
  const assignments = [], ambiguous = [], unmatchedSource = [];
  const bySource = new Map();
  for (const pairing of pairings) {
    if (!bySource.has(pairing.sourceIndex)) bySource.set(pairing.sourceIndex, []);
    bySource.get(pairing.sourceIndex).push(pairing);
  }
  if (blocked) {
    for (const { question: sourceQuestion } of eligible) {
      unmatchedSource.push({ sourceNumber: sourceQuestion.number ?? null, sourceId: str(sourceQuestion.id) || null,
        reason: blocked, bestScore: 0 });
    }
  }
  for (const { question: sourceQuestion, index: sourceIndex } of (blocked ? [] : eligible)) {
    const candidates = bySource.get(sourceIndex) ?? [];
    const best = candidates[0];
    if (!best || best.score < policy.candidateFloor) {
      unmatchedSource.push({ sourceNumber: sourceQuestion.number ?? null, sourceId: str(sourceQuestion.id) || null,
        reason: best ? 'below-candidate-floor' : 'no-candidate', bestScore: best ? Number(best.score.toFixed(4)) : 0 });
      continue;
    }
    // A second candidate within the margin means the evidence cannot choose; a human must.
    const rival = candidates.find((candidate) => candidate.repositoryIndex !== best.repositoryIndex && best.score - candidate.score <= policy.ambiguityMargin);
    if (rival) {
      ambiguous.push({ sourceNumber: sourceQuestion.number ?? null, sourceId: str(sourceQuestion.id) || null, reason: 'candidates-within-margin',
        candidates: [best, rival].map((candidate) => ({ repositoryNumber: candidate.repositoryQuestion.number ?? null,
          repositoryId: str(candidate.repositoryQuestion.id) || null, score: Number(candidate.score.toFixed(4)), grade: candidate.grade })) });
      continue;
    }
    if (assignedSource.has(sourceIndex) || assignedRepository.has(best.repositoryIndex)) {
      ambiguous.push({ sourceNumber: sourceQuestion.number ?? null, sourceId: str(sourceQuestion.id) || null, reason: 'repository-row-already-claimed',
        candidates: [{ repositoryNumber: best.repositoryQuestion.number ?? null, repositoryId: str(best.repositoryQuestion.id) || null,
          score: Number(best.score.toFixed(4)), grade: best.grade }] });
      continue;
    }
    assignedSource.add(sourceIndex);
    assignedRepository.add(best.repositoryIndex);
    const autoAcceptable = best.grade === 'exact';
    assignments.push({
      sourceNumber: sourceQuestion.number ?? null, sourceId: str(sourceQuestion.id) || null,
      repositoryNumber: best.repositoryQuestion.number ?? null, repositoryId: str(best.repositoryQuestion.id) || null,
      // Reported, never scored: a matching number is an observation, not evidence of identity.
      sameNumber: Number.isInteger(sourceQuestion.number) && sourceQuestion.number === best.repositoryQuestion.number,
      method: best.grade === 'exact' ? 'exact-content' : 'similarity',
      grade: best.grade, score: Number(best.score.toFixed(4)),
      autoAcceptable, requiresHumanReview: !autoAcceptable,
      evidence: Object.fromEntries(Object.entries(best.signals).map(([name, value]) => [name,
        { available: value.available, contradictory: value.contradictory, similarity: Number(value.score.toFixed(4)),
          ...(value.basis ? { basis: value.basis } : {}), ...(value.reason ? { reason: value.reason } : {}) }])),
    });
  }
  const unmatchedRepositoryRows = repositoryRows
    .map((question, index) => ({ question, index }))
    .filter(({ index }) => !assignedRepository.has(index))
    .map(({ question }) => ({ repositoryNumber: question.number ?? null, repositoryId: str(question.id) || null }));

  return {
    schemaVersion: MAPPING_SCHEMA_VERSION,
    kind: 'question-number-mapping-report',
    // This report may never be read as a verification; comparePaper owns that.
    advisoryOnly: true,
    sourceRights,
    blocked,
    policy: { candidateFloor: policy.candidateFloor, ambiguityMargin: policy.ambiguityMargin, weights: { ...policy.weights } },
    source: { label: str(source.label) || null, total: source.questions.length, eligible: eligible.length, rejected,
      duplicateNumbers: duplicatesOf(sourceNumbers) },
    repository: { label: str(repository.label) || null, total: repositoryRows.length, duplicateNumbers: duplicatesOf(repositoryNumbers) },
    assignments, ambiguous, unmatchedSource, unmatchedRepository: unmatchedRepositoryRows, conflicts,
    counts: {
      sourceTotal: source.questions.length, eligible: eligible.length, rejected: rejected.length,
      assignedExact: assignments.filter((row) => row.grade === 'exact').length,
      assignedCandidate: assignments.filter((row) => row.grade !== 'exact').length,
      ambiguous: ambiguous.length, unmatchedSource: unmatchedSource.length,
      unmatchedRepository: unmatchedRepositoryRows.length,
      sameNumberAssigned: assignments.filter((row) => row.sameNumber).length,
    },
    limitation: 'Advisory mapping only. Every assignment is a proposal for human review; nothing here is a verified match, and the number itself is never used as evidence.',
  };
}

/** Structural contract for downstream consumers. Unknown keys are allowed; these must be present. */
export const MAPPING_REPORT_SCHEMA = Object.freeze({
  schemaVersion: 'number', kind: 'string', advisoryOnly: 'boolean', sourceRights: 'string',
  blocked: 'string|null', policy: 'object',
  source: { label: 'string|null', total: 'number', eligible: 'number', rejected: 'array', duplicateNumbers: 'array' },
  repository: { label: 'string|null', total: 'number', duplicateNumbers: 'array' },
  assignments: 'array', ambiguous: 'array', unmatchedSource: 'array', unmatchedRepository: 'array',
  conflicts: 'array', counts: 'object', limitation: 'string',
});
const ASSIGNMENT_SCHEMA = Object.freeze({ sourceNumber: 'number|null', sourceId: 'string|null',
  repositoryNumber: 'number|null', repositoryId: 'string|null', sameNumber: 'boolean', method: 'string',
  grade: 'string', score: 'number', autoAcceptable: 'boolean', requiresHumanReview: 'boolean', evidence: 'object' });

const typeOf = (value) => value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;

/** Validate a report against the contract without pulling in a schema library. */
export function validateMappingReport(report) {
  const problems = [];
  const check = (object, schema, prefix) => {
    for (const [key, expected] of Object.entries(schema)) {
      const value = object?.[key];
      const actual = typeOf(value);
      const ok = typeof expected === 'string'
        ? (expected.includes('|') ? expected.split('|').includes(actual) : actual === expected)
        : expected && typeof expected === 'object' ? actual === 'object' : actual === expected;
      if (!ok) problems.push(`${prefix}${key}: expected ${expected}, got ${actual}`);
      else if (typeof expected === 'object' && expected && value && typeof value === 'object') check(value, expected, `${prefix}${key}.`);
    }
  };
  if (!report || typeof report !== 'object') return { ok: false, problems: ['report is not an object'] };
  check(report, MAPPING_REPORT_SCHEMA, '');
  if (report.advisoryOnly !== true) problems.push('advisoryOnly must be true');
  if (report.blocked === null && report.assignments.some((row) => !row.requiresHumanReview && row.grade !== 'exact')) {
    problems.push('only an exact grade may be auto-acceptable');
  }
  for (const [index, row] of (report.assignments ?? []).entries()) check(row, ASSIGNMENT_SCHEMA, `assignments[${index}].`);
  return { ok: problems.length === 0, problems };
}
