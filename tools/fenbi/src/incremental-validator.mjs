/**
 * Bounded, incremental per-paper validation for the matching/receipt pipeline.
 *
 * Runs on a small batch of papers (default ≤10 papers / ≤100 questions per run) and produces a
 * **metadata-only receipt**: numbers, ids, statuses, reasons and content hashes — never question
 * text, option text, image bytes or credentials. The receipt is therefore safe to hand to the queue
 * or to the browser owner as an evidence回执, and it can be attached to a `gwy-zhenti-staged-qa-handoff`
 * artifact later without a live link (see README: the handoff contract belongs to PR #65; this module
 * only consumes and emits plain metadata, it does not import or require that branch).
 *
 * It builds on `mapping.mjs` (PR #63). The risk rules it adds on top:
 *   - a question whose normalized text is equal but whose raw visible text differs is HIGH RISK and
 *     never auto-accepted: `normalized_equal` is not "official verbatim identity";
 *   - a pure-image question can only be exact with a verified content SHA (mapping.mjs already
 *     enforces this) — a reference path or a label never counts;
 *   - anything not strictly compared is reported as advisory / human review, never as passed;
 *   - a number that happens to match but whose content is not comparable is NOT "ordered same number".
 */
import { createHash } from 'node:crypto';
import { buildMappingReport, validateMappingReport, DEFAULT_POLICY } from './mapping.mjs';
import { normalizeComparisonText } from './align.mjs';

export const RECEIPT_SCHEMA_VERSION = 1;
export const RECEIPT_KIND = 'gwy-zhenti-incremental-validation-receipt';

/** Hard bounds for one run. A larger request is refused rather than truncated. */
export const DEFAULT_LIMITS = Object.freeze({ maxPapers: 10, maxQuestions: 100 });

/** The categories the receipt must report separately. */
export const CATEGORIES = Object.freeze([
  'ordered_same_number',      // same number, strictly equal content
  'cross_number',             // strictly equal content, different numbers
  'recollection_variant',     // likely the same question, wording differs → human review
  'material_or_image_not_compared', // pair limited because materials/images lack evidence
  'image_content_conflict',   // verified image bytes differ on both sides → never auto-accept
  'missing_options',          // one side has no option bodies
  'uncollected_stub',         // caller's eligibility gate rejected the row (征集占位等)
  'answer_source_missing',    // answer/explanation present but no source receipt
  'answer_unknown',           // no answer/explanation observed at all
  'ambiguous',                // candidates within the margin
  'unmatched_source',
  'unmatched_repository',
]);

/** Risk flags that force human review regardless of score. */
export const RISK_FLAGS = Object.freeze([
  'version_wording_differs',      // the two sides carry different version labels
  'image_content_conflict',       // both sides have verified image bytes and they differ
  'image_evidence_unverified',
  'materials_not_comparable',
  'options_not_comparable',
  'number_only_no_content',
]);

// Version qualifiers that describe *how* a paper was obtained. They are metadata, not question
// content, so they are compared between the two sides rather than scored.
const VERSION_MARKERS = Object.freeze(['网友回忆', '考生回忆', '回忆版', '据回忆', '修订版', '整理版', '还原版']);
export function versionMarkers(text) {
  // Checked one marker at a time: a single alternation would let `网友回忆` swallow the overlapping
  // `回忆版` in the same string.
  const value = str(text);
  return VERSION_MARKERS.filter((marker) => value.includes(marker)).sort();
}

const sha = (value) => createHash('sha256').update(String(value ?? '')).digest('hex');
const str = (value) => value == null ? '' : String(value);
const visible = (html) => normalizeComparisonText(html).strict;
const rawVisible = (html) => {
  // Whitespace-collapsed text WITHOUT fullwidth/NFKC folding, so a wording or numeric-script
  // difference that normalization would erase is still visible here.
  const $text = str(html).replace(/<[^>]*>/gu, ' ').replace(/&[a-z#0-9]+;/giu, ' ').replace(/\s+/gu, ' ').trim();
  return $text;
};
const textOnly = (html) => normalizeComparisonText(html).strict.split('⟦IMAGE⟧').join('').trim();
const hasOptions = (question) => (question?.options ?? []).some((option) => textOnly(option.contentHtml));
const hasAnswer = (question) => Boolean(textOnly(question?.answerHtml));
const hasExplanation = (question) => Boolean(textOnly(question?.explanationHtml));

/**
 * Evidence grade for one matched pair, plus the risk flags that make it advisory.
 *
 * `identity` is deliberately never "verbatim": a normalized-equal pair proves the two bodies agree
 * after whitespace/markup/width folding, not that they are character-for-character the official
 * text. `verbatimIdentical` is only true when the two raw bodies match after trivial trimming.
 */
export function assessPair(source, repository, mapping, { versionDiffers = false } = {}) {
  const flags = [];
  const sourceText = textOnly(source.contentHtml), repositoryText = textOnly(repository.contentHtml);
  const normalizedEqual = Boolean(sourceText && repositoryText)
    && visible(source.contentHtml) === visible(repository.contentHtml);
  const rawIdentical = str(source.contentHtml).trim() === str(repository.contentHtml).trim();
  const identity = normalizedEqual ? 'normalized-equal' : sourceText && repositoryText ? 'similar' : 'none';
  if (versionDiffers) flags.push('version_wording_differs');
  if (!hasOptions(source) || !hasOptions(repository)) flags.push('missing_options');
  // "There are pictures but their bytes were never verified" is a risk. "Neither side has any
  // picture" is simply not part of the comparison and must not push the paper into review.
  const images = mapping?.evidence?.images;
  // Verified bytes on both sides that do not agree are a content conflict, not a close call. This is
  // checked here as well as in mapping.mjs so the receipt stays safe even if it is run against an
  // older mapping module that would still call the pair exact.
  if (images?.available === true && typeof images.similarity === 'number' && images.similarity < 1) {
    flags.push('image_content_conflict');
  }
  if (images?.available === false && ['image-bytes-not-verified', 'image-manifest-missing-on-one-side'].includes(images.reason)) {
    flags.push('image_evidence_unverified');
  }
  const materials = mapping?.evidence?.materials;
  if (materials?.available === true && materials.similarity === 0 && !materials.contradictory) flags.push('materials_not_comparable');
  const options = mapping?.evidence?.options;
  if (options?.available === true && options.similarity === 0) flags.push('options_not_comparable');
  if (mapping?.sameNumber && identity === 'none') flags.push('number_only_no_content');
  // Any content conflict or missing-evidence flag keeps the row out of the auto-accept path.
  const requiresHumanReview = Boolean(mapping?.requiresHumanReview) || flags.some((flag) => [
    'version_wording_differs', 'number_only_no_content', 'image_evidence_unverified',
    'image_content_conflict', 'materials_not_comparable', 'options_not_comparable',
  ].includes(flag));
  return { flags: [...new Set(flags)], requiresHumanReview, identity, verbatimIdentical: rawIdentical && normalizedEqual };
}

/** Classify one assignment or unmatched row into the receipt's category vocabulary. */
function categorize({ row, flags }) {
  if (row.status === 'unmatched') return row.sourceNumber == null ? 'unmatched_repository' : 'unmatched_source';
  // A verified image conflict outranks the "exact" branch: nothing may be reported as an ordered,
  // machine-accepted match while the picture bytes disagree.
  if (flags.includes('image_content_conflict')) return 'image_content_conflict';
  if (flags.includes('missing_options')) return 'missing_options';
  // Content decides first. "Not compared" only describes a pair that is otherwise equal but whose
  // material/image evidence is unavailable — it must never mask a genuine text difference.
  if (row.grade === 'exact') {
    if (flags.includes('image_evidence_unverified') || flags.includes('materials_not_comparable')) {
      return 'material_or_image_not_compared';
    }
    return row.sameNumber ? 'ordered_same_number' : 'cross_number';
  }
  return 'recollection_variant';
}

function answerFlag(source) {
  if (!hasAnswer(source) && !hasExplanation(source)) return 'answer_unknown';
  if ((hasAnswer(source) || hasExplanation(source)) && !source.answerReceipt && !source.explanationReceipt) return 'answer_source_missing';
  return null;
}

/**
 * Build the receipt for one bounded batch.
 *
 * @param {object} input
 * @param {object[]} input.papers  Each: { label, sourceRights, source:{questions}, repository:{questions} }
 * @param {(q: object) => boolean} input.isEligible  Required caller gate (stub / rights / observation).
 * @param {object} [input.limits]
 * @param {string} [input.handoffSha256]  Optional sha of a PR #65 handoff this batch came from.
 */
export function buildIncrementalReceipt({ papers, isEligible, limits = DEFAULT_LIMITS, handoffSha256 = null, policy = DEFAULT_POLICY } = {}) {
  if (!Array.isArray(papers)) throw new Error('papers must be an array');
  if (typeof isEligible !== 'function') throw new Error('isEligible is required');
  const maxPapers = Number.isInteger(limits.maxPapers) ? limits.maxPapers : DEFAULT_LIMITS.maxPapers;
  const maxQuestions = Number.isInteger(limits.maxQuestions) ? limits.maxQuestions : DEFAULT_LIMITS.maxQuestions;

  const questionTotal = papers.reduce((sum, paper) => sum
    + (paper?.source?.questions?.length ?? 0) + (paper?.repository?.questions?.length ?? 0), 0);
  const overLimit = papers.length > maxPapers || questionTotal > maxQuestions * 2;
  const rows = [], perPaper = [], tally = Object.fromEntries(CATEGORIES.map((name) => [name, 0]));
  let blockedPapers = 0, humanReview = 0;

  for (const paper of overLimit ? [] : papers) {
    const label = str(paper?.label) || null;
    const mapping = buildMappingReport({
      source: { label, questions: paper?.source?.questions ?? [] },
      repository: { label, questions: paper?.repository?.questions ?? [] },
      sourceRights: paper?.sourceRights ?? 'unknown',
      isEligible,
      policy,
    });
    if (!validateMappingReport(mapping).ok) throw new Error(`mapping report contract failed for ${label}`);
    if (mapping.blocked) blockedPapers += 1;

    // Version labels are metadata about provenance. When the two sides disagree the whole paper is
    // advisory: equal question text in two different versions is not one verbatim paper.
    const sourceVersion = str(paper?.sourceVersion) || null;
    const repositoryVersion = str(paper?.repositoryVersion) || null;
    const versionDiffers = Boolean(sourceVersion && repositoryVersion && sourceVersion !== repositoryVersion);
    const sourceById = new Map((paper?.source?.questions ?? []).map((q) => [str(q.id), q]));
    const repositoryById = new Map((paper?.repository?.questions ?? []).map((q) => [str(q.id), q]));
    const paperRows = [];
    for (const row of mapping.assignments) {
      const source = sourceById.get(str(row.sourceId)) ?? { contentHtml: '' };
      const repository = repositoryById.get(str(row.repositoryId)) ?? { contentHtml: '' };
      const { flags, requiresHumanReview, identity, verbatimIdentical } = assessPair(source, repository, row, { versionDiffers });
      const answer = answerFlag(source);
      const category = categorize({ row, flags });
      if (answer) tally[answer] += 1;
      tally[category] += 1;
      if (requiresHumanReview) humanReview += 1;
      paperRows.push({ label, sourceNumber: row.sourceNumber, repositoryNumber: row.repositoryNumber,
        sourceId: row.sourceId, repositoryId: row.repositoryId, sameNumber: row.sameNumber,
        category, grade: row.grade, score: row.score,
        autoAcceptable: row.autoAcceptable && !requiresHumanReview && !versionDiffers
          && !flags.includes('image_content_conflict'),
        requiresHumanReview: requiresHumanReview || versionDiffers || flags.includes('image_content_conflict'),
        identity, verbatimIdentical, flags, ...(answer ? { answer } : {}),
        textSha256: { source: sha(visible(source.contentHtml)), repository: sha(visible(repository.contentHtml)) } });
    }
    for (const row of mapping.ambiguous) { tally.ambiguous += 1; humanReview += 1; paperRows.push({ label, category: 'ambiguous', reason: row.reason, sourceNumber: row.sourceNumber, candidates: row.candidates }); }
    for (const row of mapping.unmatchedSource) {
      const question = sourceById.get(str(row.sourceId)) ?? null;
      const category = question && !hasOptions(question) ? 'missing_options' : 'unmatched_source';
      tally[category] += 1;
      paperRows.push({ label, category, sourceNumber: row.sourceNumber, reason: row.reason, bestScore: row.bestScore });
    }
    for (const row of mapping.unmatchedRepository) { tally.unmatched_repository += 1; paperRows.push({ label, category: 'unmatched_repository', repositoryNumber: row.repositoryNumber }); }
    for (const row of mapping.source.rejected) { tally.uncollected_stub += 1; paperRows.push({ label, category: 'uncollected_stub', sourceNumber: row.number, reason: row.reason }); }

    rows.push(...paperRows);
    perPaper.push({ label, sourceRights: mapping.sourceRights, blocked: mapping.blocked,
      version: { source: sourceVersion, repository: repositoryVersion, differs: versionDiffers },
      sourceTotal: mapping.source.total, eligible: mapping.source.eligible, rejected: mapping.source.rejected.length,
      repositoryTotal: mapping.repository.total, counts: Object.fromEntries(Object.entries(mapping.counts)) });
  }

  return {
    schemaVersion: RECEIPT_SCHEMA_VERSION,
    kind: RECEIPT_KIND,
    // Metadata only: no question text, options, image bytes or credentials are included.
    metadataOnly: true,
    advisoryOnly: true,
    // Normalized equality is never reported as character-for-character official identity.
    verbatimIdentityNotClaimed: true,
    generatedAt: new Date().toISOString(),
    handoffSha256,
    limits: { maxPapers, maxQuestions, papers: papers.length, questionSlots: questionTotal },
    blocked: overLimit ? 'batch-over-limit' : blockedPapers ? 'some-papers-blocked-by-rights' : null,
    papers: perPaper,
    rows,
    counts: { ...tally, papers: papers.length, blockedPapers, humanReviewRequired: humanReview,
      rows: rows.length, overLimit },
    limitation: 'Advisory metadata receipt. No row here is a verification: strict identity is only what comparePaper reports. Text is represented by hashes, never echoed.',
  };
}

export const RECEIPT_SCHEMA = Object.freeze({
  schemaVersion: 'number', kind: 'string', metadataOnly: 'boolean', advisoryOnly: 'boolean',
  verbatimIdentityNotClaimed: 'boolean',
  generatedAt: 'string', handoffSha256: 'string|null', limits: 'object', blocked: 'string|null',
  papers: 'array', rows: 'array', counts: 'object', limitation: 'string',
});

const typeOf = (value) => value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;

/** Validate a receipt against the contract, and enforce the metadata-only promise. */
export function validateReceipt(receipt) {
  const problems = [];
  if (!receipt || typeof receipt !== 'object') return { ok: false, problems: ['receipt is not an object'] };
  for (const [key, expected] of Object.entries(RECEIPT_SCHEMA)) {
    const actual = typeOf(receipt[key]);
    const ok = expected.includes('|') ? expected.split('|').includes(actual) : actual === expected;
    if (!ok) problems.push(`${key}: expected ${expected}, got ${actual}`);
  }
  if (receipt.kind !== RECEIPT_KIND) problems.push(`kind must be ${RECEIPT_KIND}`);
  if (receipt.metadataOnly !== true) problems.push('metadataOnly must be true');
  if (receipt.advisoryOnly !== true) problems.push('advisoryOnly must be true');
  if (receipt.verbatimIdentityNotClaimed !== true) problems.push('verbatimIdentityNotClaimed must be true');
  const forbidden = new Set(['contentHtml', 'answerHtml', 'explanationHtml', 'options', 'materialIds', 'imageBytes', 'text']);
  const scan = (value, path) => {
    if (Array.isArray(value)) { value.forEach((entry, index) => scan(entry, `${path}[${index}]`)); return; }
    if (!value || typeof value !== 'object') return;
    for (const [key, entry] of Object.entries(value)) {
      if (forbidden.has(key)) problems.push(`row content leaked at ${path}.${key}`);
      else scan(entry, `${path}.${key}`);
    }
  };
  scan(receipt.rows, 'rows');
  for (const [index, row] of (receipt.rows ?? []).entries()) {
    if (!CATEGORIES.includes(row.category)) problems.push(`rows[${index}].category "${row.category}" is not a known category`);
    if (row.autoAcceptable === true && row.requiresHumanReview === true) problems.push(`rows[${index}] is both auto-acceptable and human-review`);
    if (row.autoAcceptable === true && row.grade && row.grade !== 'exact') problems.push(`rows[${index}] auto-acceptable with grade ${row.grade}`);
    if (row.verbatimIdentical === true && row.identity !== 'normalized-equal') problems.push(`rows[${index}] claims verbatim identity without normalized equality`);
    if (row.autoAcceptable === true && row.flags?.includes('version_wording_differs')) problems.push(`rows[${index}] auto-acceptable across differing version labels`);
  }
  return { ok: problems.length === 0, problems };
}
