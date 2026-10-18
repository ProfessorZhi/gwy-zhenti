/**
 * Shard QA for a bounded group of papers, from credential-free metadata only.
 *
 * Inputs are (a) a `gwy-zhenti-source-observation` handoff produced by the authorised browser
 * owner and (b) the repository paper markdown. This module never reads a profile, a cookie, a raw
 * capture directory or the network, and it never emits question text, image bytes, hashes or URLs.
 *
 * What it can actually decide offline:
 *   - identity alignment (year / area / subject / variant / sourceId),
 *   - question-count and numbering completeness on the repository side,
 *   - placeholder stubs,
 *   - whether a claimed figure question has an image reference at that number,
 *   - cross-paper qid overlap, which is the only sound basis for comparing two 国考 papers.
 *
 * What it cannot decide, and must report as blocked rather than guess:
 *   - per-question text equality (the handoff carries no stem fingerprints),
 *   - per-question image byte equality (the handoff images carry no question binding),
 *   - anything requiring OCR, a chunking model or the source text itself.
 */
import { createHash } from 'node:crypto';

export const SHARD_REPORT_KIND = 'gwy-zhenti-shard-qa-report';
export const SHARD_REPORT_SCHEMA_VERSION = 1;

export const STATUSES = Object.freeze(['structural_ok', 'needs_review', 'unknown', 'blocked']);

const PLACEHOLDER = /题目正在全力以赴征集|本题暂无收集到|网友未回忆起|题目缺失|正在搜集中/u;
const QUESTION_HEADING = /^#{1,6}\s*第\s*(\d+)\s*题\s*(?:<sub>\s*qid\s+(\S+?)(?:\s*·\s*[^<]*)?<\/sub>)?\s*$/gmu;
const IMAGE_REF = /<(?:img|image)\b[^>]*>|!\[[^\]]*\]\([^)]*\)/gu;

/** Parse the repository paper into per-number structure. Pure; no I/O. */
export function parseRepositoryPaper(markdown) {
  const text = String(markdown ?? '');
  const marks = [...text.matchAll(QUESTION_HEADING)];
  const questions = new Map();
  for (let index = 0; index < marks.length; index++) {
    const mark = marks[index];
    const end = marks[index + 1]?.index ?? text.length;
    const block = text.slice(mark.index, end);
    const number = Number(mark[1]);
    questions.set(number, {
      number,
      hasQid: Boolean(mark[2]),
      images: (block.match(IMAGE_REF) ?? []).length,
      placeholder: PLACEHOLDER.test(block),
    });
  }
  const numbers = [...questions.keys()].sort((a, b) => a - b);
  const max = numbers.length ? numbers[numbers.length - 1] : 0;
  const missing = [];
  for (let n = 1; n <= max; n++) if (!questions.has(n)) missing.push(n);
  return {
    headings: numbers.length,
    numbers, missing,
    duplicateHeadings: numbers.length !== marks.length,
    placeholderNumbers: [...questions.values()].filter((q) => q.placeholder).map((q) => q.number),
    withImages: [...questions.values()].filter((q) => q.images > 0).map((q) => q.number),
    imageReferences: [...questions.values()].reduce((sum, q) => sum + q.images, 0),
    questions,
  };
}

const normaliseVariant = (value) => String(value ?? '').normalize('NFKC').replace(/[\s()（）]/gu, '').replace(/[类卷]/gu, '');

/** Compare a handoff observation with the repository paper's identity. */
export function checkIdentity(observation, paperIdentity) {
  const checks = {
    sourceId: Boolean(observation?.paperSourceId),
    year: Number(observation?.year) === Number(paperIdentity?.year),
    area: String(observation?.area ?? '') === String(paperIdentity?.area ?? ''),
    subject: String(observation?.subject ?? '') === String(paperIdentity?.subject ?? ''),
    variant: normaliseVariant(observation?.variant) === normaliseVariant(paperIdentity?.variant),
  };
  return { aligned: Object.values(checks).every(Boolean), checks };
}

/** The claims an auditor wants re-checked, as `[{ sourceId, number, claim }]`. */
function checkClaim(claim, parsed) {
  const question = parsed.questions.get(claim.number);
  if (!question) {
    return { ...claim, repositoryImages: 0, status: 'needs_review', reason: 'repository-question-absent' };
  }
  if (question.placeholder) {
    return { ...claim, repositoryImages: question.images, status: 'needs_review', reason: 'repository-is-collection-placeholder' };
  }
  if (claim.claim === 'image_bytes_identical' && question.images === 0) {
    return { ...claim, repositoryImages: 0, status: 'needs_review', reason: 'claim-says-identical-but-repository-has-no-image' };
  }
  // A claim that the two sides are not comparable is a review item, not something to re-derive.
  if (claim.claim === 'chunking_differs_not_comparable') {
    return { ...claim, repositoryImages: question.images, status: 'needs_review', reason: 'chunking-differs-not-comparable' };
  }
  // A "partial byte match" claim implies an image exists; with none at that number the claim is
  // contradicted by the repository, not merely unverifiable.
  if (claim.claim === 'image_bytes_partial' && question.images === 0) {
    return { ...claim, repositoryImages: 0, status: 'needs_review', reason: 'claim-implies-image-but-repository-has-none' };
  }
  if (question.images > 0) {
    // The structure supports the claim, but byte identity itself cannot be re-derived offline:
    // the handoff has no question→image binding and no repository-side hashes.
    return { ...claim, repositoryImages: question.images, status: 'blocked', reason: 'image-byte-identity-needs-question-image-binding' };
  }
  return { ...claim, repositoryImages: 0, status: 'unknown', reason: 'no-image-at-this-number' };
}

/**
 * Build the shard report.
 *
 * @param {object} input
 * @param {object} input.handoff        Parsed `gwy-zhenti-source-observation` document.
 * @param {object[]} input.papers       `[{ sourceId, path, identity, markdown }]`
 * @param {object[]} [input.claims]     Figure claims to re-check (metadata only).
 */
export function buildShardReport({ handoff, papers, claims = [] } = {}) {
  if (!handoff || !Array.isArray(handoff.observations)) throw new Error('handoff.observations is required');
  if (!Array.isArray(papers) || !papers.length) throw new Error('papers are required');
  const byId = new Map(handoff.observations.map((observation) => [String(observation.paperSourceId), observation]));
  const rows = [], blocked = new Set(), pairOverlap = [];

  for (const paper of papers) {
    const sourceId = String(paper.sourceId);
    const observation = byId.get(sourceId);
    const parsed = parseRepositoryPaper(paper.markdown);
    if (!observation) {
      rows.push({ sourceId, label: paper.label ?? null, status: 'blocked', reason: 'not-in-handoff',
        repository: { path: paper.path }, claims: [] });
      blocked.add('handoff-paper-entry');
      continue;
    }
    const identity = checkIdentity(observation, paper.identity);
    const countMatch = Number(observation.questionCount) === parsed.headings;
    const declarations = observation.images?.length ?? 0;
    const paperClaims = claims.filter((claim) => String(claim.sourceId) === sourceId).map((claim) => checkClaim(claim, parsed));
    const conflicts = [];
    if (!identity.aligned) conflicts.push('identity-mismatch');
    if (!countMatch) conflicts.push('question-count-mismatch');
    if (parsed.missing.length) conflicts.push('repository-numbering-gap');
    if (parsed.duplicateHeadings) conflicts.push('repository-duplicate-heading');
    if (parsed.placeholderNumbers.length) conflicts.push('repository-collection-placeholder');
    if (paperClaims.some((claim) => claim.status === 'needs_review')) conflicts.push('claim-contradicted-by-structure');

    rows.push({
      sourceId, label: paper.label ?? null,
      identity,
      counts: { sourceDeclared: Number(observation.questionCount) ?? null, repositoryHeadings: parsed.headings,
        match: countMatch, handoffImages: declarations, repositoryImageReferences: parsed.imageReferences },
      repository: { path: paper.path, numbersComplete: parsed.missing.length === 0, missingNumbers: parsed.missing.slice(0, 20),
        placeholderNumbers: parsed.placeholderNumbers.slice(0, 20), imageQuestions: parsed.withImages.length },
      claims: paperClaims,
      conflicts,
      // Content equality is never claimed here.
      contentComparison: { status: 'blocked', reason: 'handoff-has-no-per-question-fingerprints' },
      status: conflicts.length ? 'needs_review' : 'structural_ok',
    });
    blocked.add('per-question-source-fingerprints');
    blocked.add('question-image-binding');
  }

  // Cross-paper overlap: the only sound basis for comparing two 国考 papers is the shared qid.
  for (let i = 0; i < papers.length; i++) {
    for (let j = i + 1; j < papers.length; j++) {
      const a = qidIndex(papers[i]), b = qidIndex(papers[j]);
      const shared = [...a.keys()].filter((qid) => b.has(qid));
      const sameNumber = shared.filter((qid) => a.get(qid) === b.get(qid)).length;
      pairOverlap.push({ a: String(papers[i].sourceId), b: String(papers[j].sourceId),
        sharedQids: shared.length, sameNumber, crossNumber: shared.length - sameNumber });
    }
  }

  const counts = { papers: rows.length, structuralOk: rows.filter((r) => r.status === 'structural_ok').length,
    needsReview: rows.filter((r) => r.status === 'needs_review').length,
    blocked: rows.filter((r) => r.status === 'blocked').length,
    claims: rows.reduce((sum, r) => sum + (r.claims ?? []).length, 0),
    claimsNeedingReview: rows.reduce((sum, r) => sum + (r.claims ?? []).filter((c) => c.status === 'needs_review').length, 0),
    claimsBlocked: rows.reduce((sum, r) => sum + (r.claims ?? []).filter((c) => c.status === 'blocked').length, 0) };

  return {
    schemaVersion: SHARD_REPORT_SCHEMA_VERSION,
    kind: SHARD_REPORT_KIND,
    metadataOnly: true,
    advisoryOnly: true,
    generatedAt: new Date().toISOString(),
    handoff: { kind: handoff.kind ?? null, schemaVersion: handoff.schemaVersion ?? null,
      producer: handoff.producer?.agent ?? null, paperCount: handoff.observations.length,
      permissions: handoff.permissions ?? null },
    papers: rows,
    crossPaper: pairOverlap,
    blockedHandoffOwners: [...blocked].sort(),
    counts,
    limitation: 'Structural QA only. No question text, image bytes, hashes or URLs are included. Text and byte identity are blocked until the owner supplies per-question fingerprints and a question→image binding.',
  };
}

function qidIndex(paper) {
  const index = new Map();
  const text = String(paper.markdown ?? '');
  for (const match of text.matchAll(/^#{1,6}\s*第\s*(\d+)\s*题\s*<sub>\s*qid\s+(\S+?)\s*·/gmu)) index.set(match[2], Number(match[1]));
  return index;
}

/** Structural contract for downstream consumers. */
export const SHARD_REPORT_SCHEMA = Object.freeze({
  schemaVersion: 'number', kind: 'string', metadataOnly: 'boolean', advisoryOnly: 'boolean',
  generatedAt: 'string', handoff: 'object', papers: 'array', crossPaper: 'array',
  blockedHandoffOwners: 'array', counts: 'object', limitation: 'string',
});

const typeOf = (value) => value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;

export function validateShardReport(report) {
  const problems = [];
  if (!report || typeof report !== 'object') return { ok: false, problems: ['report is not an object'] };
  for (const [key, expected] of Object.entries(SHARD_REPORT_SCHEMA)) {
    const actual = typeOf(report[key]);
    if (actual !== expected) problems.push(`${key}: expected ${expected}, got ${actual}`);
  }
  if (report.kind !== SHARD_REPORT_KIND) problems.push(`kind must be ${SHARD_REPORT_KIND}`);
  if (report.metadataOnly !== true) problems.push('metadataOnly must be true');
  if (report.advisoryOnly !== true) problems.push('advisoryOnly must be true');
  const forbidden = new Set(['markdown', 'contentHtml', 'stemText', 'options', 'answerHtml', 'explanationHtml',
    'sha256', 'sourceUrl', 'route', 'url', 'raw']);
  const scan = (value, path) => {
    if (Array.isArray(value)) { value.forEach((entry, index) => scan(entry, `${path}[${index}]`)); return; }
    if (!value || typeof value !== 'object') return;
    for (const [key, entry] of Object.entries(value)) {
      if (forbidden.has(key)) problems.push(`restricted field leaked at ${path}.${key}`);
      else scan(entry, `${path}.${key}`);
    }
  };
  scan(report.papers, 'papers');
  scan(report.crossPaper, 'crossPaper');
  for (const [index, row] of (report.papers ?? []).entries()) {
    if (!STATUSES.includes(row.status)) problems.push(`papers[${index}].status "${row.status}" is not a known status`);
    if (row.contentComparison && row.contentComparison.status !== 'blocked') {
      problems.push(`papers[${index}] claims a content comparison this module cannot make`);
    }
  }
  return { ok: problems.length === 0, problems };
}

/** A short, stable identifier for a shard, so a report can be named after it. */
export function shardKey(sourceIds) {
  return createHash('sha256').update([...sourceIds].map(String).sort().join(',')).digest('hex').slice(0, 12);
}
