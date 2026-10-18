import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { classifyShard, validateShard } from '../checker.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHA = (c) => c.repeat(64);

function shard(overrides = {}) {
  return {
    schemaVersion: 1,
    kind: 'gwy-zhenti-fingerprint-shard',
    paper: { paperSourceId: '9000001', year: 2026, area: '广东', subject: 'xingce', variant: '统考' },
    rights: { redistribution: 'local_only' },
    source: {
      questionCount: 10,
      questions: [
        { number: 1, textSha256: SHA('1'), imageShas: [SHA('a')] },
        { number: 2, textSha256: SHA('2'), imageShas: [SHA('b')] },
        { number: 3, status: 'placeholder' },
        { number: 4, textSha256: SHA('4') },
        { number: 5, textSha256: SHA('5') },
        { number: 6, textSha256: SHA('6') },
        { number: 7 },
        { number: 8 },
        { number: 9, status: 'image_only', imageShas: [SHA('c')] },
        { number: 10, textSha256: SHA('e') },
      ],
    },
    repository: {
      questionCount: 9,
      questions: [
        { number: 1, textSha256: SHA('1'), imageShas: [SHA('a')] },
        { number: 2, textSha256: SHA('2'), imageShas: [SHA('9')] },
        { number: 4, textSha256: SHA('4') },
        { number: 5, textSha256: SHA('5') },
        { number: 6, textSha256: SHA('6') },
        { number: 7, textSha256: SHA('7') },
        { number: 8, textSha256: SHA('8') },
        { number: 9, textSha256: SHA('9') },
        { number: 10, textSha256: SHA('e') },
      ],
    },
    mapping: [
      { sourceNumber: 1, repositoryNumber: 1, grade: 'exact' },
      { sourceNumber: 2, repositoryNumber: 2, grade: 'exact' },
      { sourceNumber: 4, repositoryNumber: 4, grade: 'weak' },
      { sourceNumber: 7, repositoryNumber: 7, grade: 'exact', normalizedEqual: true },
      { sourceNumber: 8, repositoryNumber: 8, grade: 'exact' },
      { sourceNumber: 10, repositoryNumber: 10, grade: 'exact' },
    ],
    reviewCandidates: [
      { sourceNumber: 6, candidateRepositoryNumbers: [5, 6], score: 1, reason: 'tie_in_best_score_not_bound' },
    ],
    ...overrides,
  };
}

test('fingerprint statuses: exact, normalized_equal, image conflict, placeholder, needs_review, ambiguous, unmatched', () => {
  const report = classifyShard(shard());
  assert.equal(report.officialVerification, false);
  assert.equal(report.counts.fingerprint_exact, 1, 'Q1 text+image hashes match');
  assert.equal(report.counts.image_conflict, 1, 'Q2 image hashes differ');
  assert.equal(report.counts.placeholder, 1, 'Q3 placeholder is not content');
  assert.equal(report.counts.needs_review, 1, 'Q4 weak grade');
  assert.equal(report.counts.ambiguous, 1, 'Q6 tie');
  assert.equal(report.counts.unmatched, 1, 'Q5 has no mapping');
  assert.equal(report.counts.blocked_missing_fingerprint, 1, 'Q8 exact grade but no hashes');
  assert.equal(report.counts.normalized_equal_mapping_only, 1, 'Q7 advisory normalizedEqual');
  assert.equal(report.counts.image_only_not_comparable, 1, 'Q9 image-only slide');
  assert.equal(report.counts.normalized_equal, 1, 'Q10 text equal, no images');
  const q1 = report.slots.find((s) => s.sourceNumber === 1);
  assert.equal(q1.status, 'fingerprint_exact');
  const q2 = report.slots.find((s) => s.sourceNumber === 2);
  assert.equal(q2.status, 'image_conflict');
  const q3 = report.slots.find((s) => s.sourceNumber === 3);
  assert.equal(q3.status, 'placeholder');
});

test('one-to-one mapping, local_only rights and content-free input fail closed', () => {
  const duplicate = shard();
  duplicate.mapping.push({ sourceNumber: 5, repositoryNumber: 1, grade: 'exact' });
  assert.throws(() => validateShard(duplicate), /SHARD_MAPPING_NOT_ONE_TO_ONE/);
  const loose = shard();
  loose.rights.redistribution = 'allowed';
  assert.throws(() => validateShard(loose), /SHARD_RIGHTS/);
  const content = shard();
  content.source.questions[0].text = 'raw question text';
  assert.throws(() => validateShard(content), /SHARD_CONTENT_FORBIDDEN/);
  const url = shard();
  url.source.questions[0].textSha256 = 'https://evil.test/a.png';
  assert.throws(() => validateShard(url), /SHARD_URL_FORBIDDEN|SHARD_INVALID/);
  const unknownRepo = shard();
  unknownRepo.mapping.push({ sourceNumber: 5, repositoryNumber: 999, grade: 'exact' });
  assert.throws(() => validateShard(unknownRepo), /SHARD_INVALID/);
});

test('CLI writes a 0600 metadata-only report and exits 0', async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'shard-qa-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  await fs.chmod(dir, 0o700);
  const input = path.join(dir, 'shard.json');
  const output = path.join(dir, 'report.json');
  await fs.writeFile(input, JSON.stringify(shard()), { mode: 0o600 });
  const result = await new Promise((resolve) => {
    execFile(process.execPath, [path.join(HERE, '..', 'checker.mjs'), '--shard', input, '--out', output], { timeout: 20_000 }, (error, stdout) => {
      resolve({ code: error?.code ?? 0, stdout });
    });
  });
  assert.equal(result.code, 0);
  const report = JSON.parse(await fs.readFile(output, 'utf8'));
  assert.equal(report.counts.total, 10);
  assert.equal(report.officialVerification, false);
  const stat = await fs.stat(output);
  assert.equal(stat.mode & 0o777, 0o600);
  const text = JSON.stringify(report);
  assert.doesNotMatch(text, /<html|contentHtml|https?:\/\//i);
});
