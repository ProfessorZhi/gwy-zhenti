#!/usr/bin/env node
/**
 * Fingerprint-only shard QA checker.
 *
 * A shard contains identities, one-to-one mappings and SHA-256 fingerprints only. It never
 * contains question text, options, answers, image bytes or URLs. `normalized_equal` metadata from
 * another audit is advisory; only equal text+image fingerprints can be called `fingerprint_exact`,
 * and even that is NOT independent official verification.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { parseArgs } from 'node:util';

const SHA256 = /^[a-f0-9]{64}$/i;
const GRADES = new Set(['exact', 'near', 'weak', 'ambiguous']);
const STATUSES = new Set(['present', 'placeholder', 'unknown', 'image_only']);
const FORBIDDEN_KEY = /^(?:url|href|text|content|contentHtml|stem|stemHtml|options|optionsHtml|answer|answerHtml|analysis|analysisHtml|raw|rawHtml|imageBytes|bytes)$/i;
const CREDENTIAL = [/(?:^|[?&;])(?:token|auth|sessionid|cookie|signature)=/i, /\bbearer\s+[A-Za-z0-9._~+/-]{16,}/i];
const WRITE_ROUTE = /\/(?:submit|initialize|init|create|start|finish|save)(?:\/|$)/i;

function shardError(code, message) { return Object.assign(new Error(`[${code}] ${message}`), { code }); }
function isObject(value) { return Boolean(value) && typeof value === 'object' && !Array.isArray(value); }

function assertNoForbidden(value, route = '$') {
  if (typeof value === 'string') {
    for (const pattern of CREDENTIAL) if (pattern.test(value)) throw shardError('SHARD_CREDENTIAL_LEAK', `credential-like value at ${route}`);
    if (/^https?:\/\//i.test(value) || /^\/\/[^/]/.test(value)) throw shardError('SHARD_URL_FORBIDDEN', `URL at ${route}`);
    return;
  }
  if (Array.isArray(value)) { value.forEach((item, index) => assertNoForbidden(item, `${route}[${index}]`)); return; }
  if (!isObject(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (FORBIDDEN_KEY.test(key)) throw shardError('SHARD_CONTENT_FORBIDDEN', `content-like key at ${route}.${key}`);
    assertNoForbidden(child, `${route}.${key}`);
  }
}

function hashArray(value, label) {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > 256) throw shardError('SHARD_INVALID', `${label} must be a hash array`);
  const result = value.map((item) => String(item).toLowerCase());
  for (const item of result) if (!SHA256.test(item)) throw shardError('SHARD_INVALID', `${label} contains a non-SHA-256 value`);
  if (new Set(result).size !== result.length) throw shardError('SHARD_INVALID', `${label} contains duplicate hashes`);
  return [...result].sort();
}

function questionList(value, label) {
  if (!Array.isArray(value) || !value.length || value.length > 2000) throw shardError('SHARD_INVALID', `${label} must be a question array`);
  const seen = new Set();
  return value.map((question, index) => {
    if (!isObject(question)) throw shardError('SHARD_INVALID', `${label}[${index}] must be an object`);
    const number = Number(question.number);
    if (!Number.isInteger(number) || number < 1) throw shardError('SHARD_INVALID', `${label}[${index}].number is invalid`);
    if (seen.has(number)) throw shardError('SHARD_INVALID', `${label} repeats question ${number}`);
    seen.add(number);
    const status = question.status ?? 'present';
    if (!STATUSES.has(status)) throw shardError('SHARD_INVALID', `${label}[${index}].status is invalid`);
    const textSha256 = question.textSha256 ?? null;
    if (textSha256 !== null && !SHA256.test(String(textSha256))) throw shardError('SHARD_INVALID', `${label}[${index}].textSha256 is invalid`);
    return { number, status, textSha256: textSha256 ? String(textSha256).toLowerCase() : null, imageShas: hashArray(question.imageShas, `${label}[${index}].imageShas`) };
  });
}

export function validateShard(shard) {
  if (!isObject(shard) || shard.schemaVersion !== 1 || shard.kind !== 'gwy-zhenti-fingerprint-shard') throw shardError('SHARD_INVALID', 'Unsupported shard schema');
  assertNoForbidden(shard);
  const paper = shard.paper;
  if (!isObject(paper)) throw shardError('SHARD_INVALID', 'paper is required');
  for (const key of ['paperSourceId', 'area', 'subject', 'variant']) {
    if (typeof paper[key] !== 'string' || !paper[key].trim()) throw shardError('SHARD_INVALID', `paper.${key} is required`);
  }
  if (!Number.isInteger(Number(paper.year))) throw shardError('SHARD_INVALID', 'paper.year is required');
  if (!['xingce', 'shenlun'].includes(paper.subject)) throw shardError('SHARD_INVALID', 'paper.subject must be xingce or shenlun');
  if (!isObject(shard.rights) || shard.rights.redistribution !== 'local_only') throw shardError('SHARD_RIGHTS', 'Only local_only shards are accepted');
  const source = shard.source;
  const repository = shard.repository;
  if (!isObject(source) || !isObject(repository)) throw shardError('SHARD_INVALID', 'source and repository are required');
  const sourceQuestions = questionList(source.questions, 'source.questions');
  const repositoryQuestions = questionList(repository.questions, 'repository.questions');
  if (Number(source.questionCount) !== sourceQuestions.length || Number(repository.questionCount) !== repositoryQuestions.length) {
    throw shardError('SHARD_INVALID', 'questionCount must match the question arrays');
  }
  const sourceNumbers = new Set(sourceQuestions.map((q) => q.number));
  const repositoryNumbers = new Set(repositoryQuestions.map((q) => q.number));
  const mapping = Array.isArray(shard.mapping) ? shard.mapping : [];
  if (!mapping.length || mapping.length > 2000) throw shardError('SHARD_INVALID', 'mapping is required');
  const usedSource = new Set(), usedRepository = new Set();
  const normalizedMapping = mapping.map((entry, index) => {
    if (!isObject(entry)) throw shardError('SHARD_INVALID', `mapping[${index}] must be an object`);
    const sourceNumber = Number(entry.sourceNumber);
    const repositoryNumber = Number(entry.repositoryNumber);
    if (!sourceNumbers.has(sourceNumber) || !repositoryNumbers.has(repositoryNumber)) throw shardError('SHARD_INVALID', `mapping[${index}] references an unknown question`);
    if (usedSource.has(sourceNumber)) throw shardError('SHARD_MAPPING_NOT_ONE_TO_ONE', `source ${sourceNumber} is mapped more than once`);
    if (usedRepository.has(repositoryNumber)) throw shardError('SHARD_MAPPING_NOT_ONE_TO_ONE', `repository ${repositoryNumber} is mapped more than once`);
    usedSource.add(sourceNumber); usedRepository.add(repositoryNumber);
    if (!GRADES.has(entry.grade)) throw shardError('SHARD_INVALID', `mapping[${index}].grade is invalid`);
    return {
      sourceNumber, repositoryNumber, grade: entry.grade,
      method: entry.method ?? (sourceNumber === repositoryNumber ? 'same_number' : 'one_to_one_reorder'),
      normalizedEqual: entry.normalizedEqual === true,
    };
  });
  const reviewCandidates = (shard.reviewCandidates ?? []).map((entry, index) => {
    if (!isObject(entry)) throw shardError('SHARD_INVALID', `reviewCandidates[${index}] must be an object`);
    const sourceNumber = Number(entry.sourceNumber);
    if (!sourceNumbers.has(sourceNumber)) throw shardError('SHARD_INVALID', `reviewCandidates[${index}] source is unknown`);
    if (usedSource.has(sourceNumber)) throw shardError('SHARD_MAPPING_NOT_ONE_TO_ONE', `source ${sourceNumber} is both mapped and ambiguous`);
    const candidates = (entry.candidateRepositoryNumbers ?? []).map(Number);
    if (!candidates.length || candidates.some((number) => !repositoryNumbers.has(number))) throw shardError('SHARD_INVALID', `reviewCandidates[${index}] has an unknown candidate`);
    return { sourceNumber, candidateRepositoryNumbers: candidates, score: Number(entry.score) || null, reason: String(entry.reason ?? 'ambiguous') };
  });
  return { paper, rights: shard.rights, sourceQuestions, repositoryQuestions, mapping: normalizedMapping, reviewCandidates };
}

export function classifyShard(shard) {
  const v = validateShard(shard);
  const repository = new Map(v.repositoryQuestions.map((q) => [q.number, q]));
  const mapping = new Map(v.mapping.map((m) => [m.sourceNumber, m]));
  const candidates = new Map(v.reviewCandidates.map((r) => [r.sourceNumber, r]));
  const counts = {
    total: v.sourceQuestions.length, fingerprint_exact: 0, normalized_equal: 0,
    normalized_equal_mapping_only: 0, needs_review: 0, image_conflict: 0,
    ambiguous: 0, unmatched: 0, placeholder: 0, unknown: 0,
    image_only_not_comparable: 0, blocked_missing_fingerprint: 0,
  };
  const slots = [];
  for (const source of v.sourceQuestions) {
    const base = { sourceNumber: source.number, repositoryNumber: null, grade: null, method: null };
    if (source.status === 'placeholder') { counts.placeholder += 1; slots.push({ ...base, status: 'placeholder', reason: 'source-placeholder-not-content' }); continue; }
    if (source.status === 'image_only') { counts.image_only_not_comparable += 1; slots.push({ ...base, status: 'image_only_not_comparable', reason: 'image-only-slide-not-comparable' }); continue; }
    if (source.status === 'unknown') { counts.unknown += 1; slots.push({ ...base, status: 'unknown', reason: 'source-content-unknown' }); continue; }
    if (candidates.has(source.number)) {
      counts.ambiguous += 1;
      const candidate = candidates.get(source.number);
      slots.push({ ...base, status: 'ambiguous', candidates: candidate.candidateRepositoryNumbers, reason: candidate.reason });
      continue;
    }
    const match = mapping.get(source.number);
    if (!match) { counts.unmatched += 1; slots.push({ ...base, status: 'unmatched', reason: 'no-one-to-one-mapping' }); continue; }
    const repo = repository.get(match.repositoryNumber);
    base.repositoryNumber = match.repositoryNumber;
    base.grade = match.grade;
    base.method = match.method;
    if (!repo) { counts.unmatched += 1; slots.push({ ...base, status: 'unmatched', reason: 'mapped-repository-question-missing' }); continue; }
    if (match.grade === 'near' || match.grade === 'weak') {
      counts.needs_review += 1;
      slots.push({ ...base, status: 'needs_review', reason: `mapping-grade-${match.grade}` });
      continue;
    }
    if (match.grade === 'ambiguous') { counts.ambiguous += 1; slots.push({ ...base, status: 'ambiguous', reason: 'mapping-grade-ambiguous' }); continue; }
    if (source.textSha256 && repo.textSha256) {
      if (source.textSha256 !== repo.textSha256) {
        counts.needs_review += 1;
        slots.push({ ...base, status: 'needs_review', reason: 'text-fingerprint-mismatch' });
        continue;
      }
      const srcImages = source.imageShas;
      const repoImages = repo.imageShas;
      if (srcImages.length || repoImages.length) {
        if (!srcImages.length || !repoImages.length) {
          counts.image_conflict += 1;
          slots.push({ ...base, status: 'image_conflict', reason: 'image-evidence-missing-on-one-side' });
          continue;
        }
        if (srcImages.join(',') !== repoImages.join(',')) {
          counts.image_conflict += 1;
          slots.push({ ...base, status: 'image_conflict', reason: 'image-sha-set-differs' });
          continue;
        }
        counts.fingerprint_exact += 1;
        slots.push({ ...base, status: 'fingerprint_exact', reason: 'text-and-image-sha256-equal' });
        continue;
      }
      counts.normalized_equal += 1;
      slots.push({ ...base, status: 'normalized_equal', reason: 'text-sha256-equal-no-images' });
      continue;
    }
    if (match.normalizedEqual) {
      counts.normalized_equal_mapping_only += 1;
      slots.push({ ...base, status: 'normalized_equal_mapping_only', reason: 'pr62-normalized-equal-metadata-no-local-hashes' });
      continue;
    }
    counts.blocked_missing_fingerprint += 1;
    slots.push({ ...base, status: 'blocked_missing_fingerprint', reason: 'one-side-lacks-text-sha256' });
  }
  const report = {
    schemaVersion: 1,
    kind: 'gwy-zhenti-shard-qa-report',
    generatedAt: new Date().toISOString(),
    paper: v.paper,
    rights: { redistribution: 'local_only' },
    officialVerification: false,
    basis: 'sha256-fingerprints-only; normalized_equal metadata is advisory; no text/image bytes read',
    counts,
    slots,
    notes: [
      'fingerprint_exact means the supplied text+image hashes match; it is not independent official verification.',
      'placeholder/unknown/image_only slots are never counted as valid content.',
      'near/weak/ambiguous/unmatched/image_conflict slots remain needs_review or blocked.',
    ],
  };
  return report;
}

export async function writeReport(filename, report) {
  await fs.mkdir(path.dirname(filename), { recursive: true, mode: 0o700 });
  const temporary = `${filename}.${crypto.randomUUID()}.tmp`;
  try {
    await fs.writeFile(temporary, JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
    await fs.rename(temporary, filename);
    await fs.chmod(filename, 0o600);
  } finally { await fs.rm(temporary, { force: true }).catch(() => {}); }
  return filename;
}

async function main() {
  const { values } = parseArgs({ options: {
    shard: { type: 'string' }, out: { type: 'string' },
  } });
  if (!values.shard) throw shardError('SHARD_INVALID', '--shard FILE is required');
  const shard = JSON.parse(await fs.readFile(values.shard, 'utf8'));
  const report = classifyShard(shard);
  if (values.out) await writeReport(values.out, report);
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try { await main(); }
  catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, error: { code: error.code ?? 'ERROR', message: error.message } }, null, 2) + '\n');
    process.exitCode = 2;
  }
}
