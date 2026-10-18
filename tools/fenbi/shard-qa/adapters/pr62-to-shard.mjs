#!/usr/bin/env node
/**
 * Convert PR #62's advisory reorder-audit JSON into a fingerprint-only shard.
 * The audit has numbers/grades/normalizedEqual but no text or image hashes, so the checker can
 * only produce `normalized_equal_mapping_only`/needs_review — never `fingerprint_exact`.
 */
import fs from 'node:fs/promises';
import { writeReport } from '../checker.mjs';

const PAPERS = {
  '8399765': { year: 2026, area: '广东', subject: 'xingce', variant: '统考', imageOnly: [35] },
  '8472470': { year: 2026, area: '上海', subject: 'xingce', variant: '统考', imageOnly: [] },
};

const [auditPath, sourceId = '8399765'] = process.argv.slice(2);
if (!auditPath) throw Object.assign(new Error('usage: pr62-to-shard.mjs AUDIT_JSON [sourceId]'), { code: 'USAGE' });
const audit = JSON.parse(await fs.readFile(auditPath, 'utf8'));
const auditCase = (audit.cases ?? []).find((item) => String(item.sourceId) === String(sourceId));
if (!auditCase) throw Object.assign(new Error(`sourceId ${sourceId} not found in audit`), { code: 'NOT_FOUND' });
const paper = PAPERS[sourceId];
if (!paper) throw Object.assign(new Error(`no paper identity mapping for ${sourceId}`), { code: 'UNSUPPORTED' });

const sourceQuestions = Array.from({ length: auditCase.sourceQuestions }, (_, index) => {
  const number = index + 1;
  return paper.imageOnly.includes(number) ? { number, status: 'image_only' } : { number };
});
const repositoryQuestions = Array.from({ length: auditCase.repositoryQuestions }, (_, index) => ({ number: index + 1 }));
const mapping = Object.values(auditCase.mapping ?? {}).map((entry) => ({
  sourceNumber: entry.sourceNumber,
  repositoryNumber: entry.repositoryNumber,
  grade: String(entry.grade).startsWith('normalized_equal') ? 'exact' : entry.grade,
  method: entry.sourceNumber === entry.repositoryNumber ? 'same_number' : 'one_to_one_reorder',
  normalizedEqual: entry.normalizedEqual === true,
}));
const reviewCandidates = Object.values(auditCase.reviewCandidates ?? {}).map((entry) => ({
  sourceNumber: entry.sourceNumber,
  candidateRepositoryNumbers: entry.candidateRepositoryNumbers,
  score: entry.score,
  reason: entry.reason,
}));

const shard = {
  schemaVersion: 1,
  kind: 'gwy-zhenti-fingerprint-shard',
  paper: {
    paperSourceId: sourceId,
    year: paper.year,
    area: paper.area,
    subject: paper.subject,
    variant: paper.variant,
    repoPath: auditCase.repoPaper,
  },
  rights: { redistribution: 'local_only' },
  source: { questionCount: sourceQuestions.length, questions: sourceQuestions },
  repository: { questionCount: repositoryQuestions.length, questions: repositoryQuestions },
  mapping,
  reviewCandidates,
  provenance: {
    basis: 'PR#62 advisory reorder audit (numbers/grades/normalizedEqual only; no text or image hashes)',
    officialVerification: false,
  },
};
await writeReport(process.argv[4] ?? `shard-${sourceId}.json`, shard);
process.stdout.write(JSON.stringify({ ok: true, shard: process.argv[4] ?? `shard-${sourceId}.json`, sourceId, mapping: mapping.length, reviewCandidates: reviewCandidates.length }, null, 2) + '\n');
