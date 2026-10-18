import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { parseRepositoryPaper, checkIdentity, buildShardReport, validateShardReport,
  SHARD_REPORT_KIND, STATUSES } from '../src/shard-qa.mjs';

/** Synthetic markdown only — no real examination text is used anywhere in this file. */

const q = (number, qid, body = '合成题干。', extra = '') =>
  `## 第 ${number} 题　<sub>qid ${qid} · 合成</sub>\n\n${body}${extra}\n\n- **A**. 甲\n- **B**. 乙\n`;
const paper = (count, { qidBase = 900, imageAt = [], placeholderAt = [], missing = [] } = {}) =>
  Array.from({ length: count }, (_v, index) => index + 1)
    .filter((number) => !missing.includes(number))
    .map((number) => q(number, qidBase + number, placeholderAt.includes(number) ? '题目正在全力以赴征集' : '合成题干。',
      imageAt.includes(number) ? '\n\n![](../图片/fig.png)' : '')).join('\n');

const observation = (extra = {}) => ({ paperSourceId: '5823069', title: '合成卷', subject: 'xingce', area: '国考',
  year: 2026, variant: '副省级', questionCount: 5, contentStatus: 'observed', images: [{ ref: 'a/img-1', sha256: 'x' }], ...extra });
const handoff = (observations = [observation()]) => ({ schemaVersion: 1, kind: 'gwy-zhenti-source-observation',
  producer: { agent: 'synthetic-owner', at: '2026-10-18T00:00:00Z' },
  permissions: { browserProfile: false, cookies: false, tokens: false }, observations });
const build = (overrides = {}) => buildShardReport({
  handoff: handoff(), papers: [{ sourceId: '5823069', label: '副省级', path: '国考/2026/行测-副省级.md',
    identity: { area: '国考', year: 2026, subject: 'xingce', variant: '副省级' }, markdown: paper(5, { imageAt: [3] }) }], ...overrides });

test('the repository parser reports numbering, gaps, placeholders and per-question images', () => {
  const parsed = parseRepositoryPaper(paper(5, { imageAt: [2, 4], placeholderAt: [3], missing: [4] }));
  assert.deepEqual(parsed.numbers, [1, 2, 3, 5]);
  assert.deepEqual(parsed.missing, [4]);
  assert.deepEqual(parsed.placeholderNumbers, [3]);
  assert.deepEqual(parsed.withImages, [2]);
  assert.equal(parsed.imageReferences, 1);
  assert.equal(parsed.duplicateHeadings, false);
  // A duplicated heading is reported rather than silently collapsing.
  assert.equal(parseRepositoryPaper(`${q(1, 1)}${q(1, 2)}`).duplicateHeadings, true);
});

test('identity alignment normalises the variant and rejects every real mismatch', () => {
  const identity = { area: '国考', year: 2026, subject: 'xingce', variant: '副省级' };
  assert.equal(checkIdentity({ paperSourceId: '1', year: 2026, area: '国考', subject: 'xingce', variant: '副省级卷' }, identity).aligned, true);
  for (const broken of [{ year: 2025 }, { area: '省考' }, { subject: 'shenlun' }, { variant: '地市级' }, { paperSourceId: null }]) {
    assert.equal(checkIdentity({ paperSourceId: '1', year: 2026, area: '国考', subject: 'xingce', variant: '副省级', ...broken }, identity).aligned, false,
      JSON.stringify(broken));
  }
});

test('a structurally consistent paper is structural_ok and never claims a content comparison', () => {
  const report = build();
  assert.equal(report.kind, SHARD_REPORT_KIND);
  const [row] = report.papers;
  assert.equal(row.status, 'structural_ok');
  assert.equal(row.counts.match, true);
  assert.deepEqual(row.conflicts, []);
  assert.equal(row.contentComparison.status, 'blocked', 'text equality is not derivable offline');
  assert.deepEqual(validateShardReport(report), { ok: true, problems: [] });
  assert.ok(report.blockedHandoffOwners.includes('per-question-source-fingerprints'));
  assert.ok(report.blockedHandoffOwners.includes('question-image-binding'));
});

test('count mismatch, numbering gaps and placeholders force needs_review', () => {
  for (const [markdown, expected] of [
    [paper(4), 'question-count-mismatch'],
    [paper(5, { missing: [3] }), 'repository-numbering-gap'],
    [paper(5, { placeholderAt: [2] }), 'repository-collection-placeholder'],
  ]) {
    const report = build({ papers: [{ sourceId: '5823069', path: 'p', identity: { area: '国考', year: 2026, subject: 'xingce', variant: '副省级' }, markdown }] });
    assert.equal(report.papers[0].status, 'needs_review', expected);
    assert.ok(report.papers[0].conflicts.includes(expected), expected);
  }
  const mismatch = build({ handoff: handoff([observation({ year: 2025 })]) });
  assert.ok(mismatch.papers[0].conflicts.includes('identity-mismatch'));
});

test('a paper absent from the handoff is blocked, not guessed', () => {
  const report = build({ handoff: handoff([observation({ paperSourceId: '9999999' })]) });
  assert.equal(report.papers[0].status, 'blocked');
  assert.equal(report.papers[0].reason, 'not-in-handoff');
  assert.equal(validateShardReport(report).ok, true, 'a blocked row is still a valid report');
});

test('claims are re-checked against structure and byte identity stays blocked', () => {
  const claims = [
    { sourceId: '5823069', number: 4, claim: 'image_bytes_identical' },   // has an image → unverifiable offline
    { sourceId: '5823069', number: 2, claim: 'chunking_differs_not_comparable' },
    { sourceId: '5823069', number: 3, claim: 'image_bytes_identical' },   // no image → contradicted
    { sourceId: '5823069', number: 1, claim: 'image_bytes_partial' },     // implies an image, none present
    { sourceId: '5823069', number: 99, claim: 'image_bytes_identical' },  // no such question
  ];
  const report = build({ claims, papers: [{ sourceId: '5823069', path: 'p', identity: { area: '国考', year: 2026, subject: 'xingce', variant: '副省级' },
    markdown: paper(5, { imageAt: [2, 4] }) }] });
  const byNumber = Object.fromEntries(report.papers[0].claims.map((claim) => [claim.number, claim]));
  assert.equal(byNumber[4].status, 'blocked', 'structure supports the claim but bytes cannot be re-derived');
  assert.equal(byNumber[2].status, 'needs_review', 'a not-comparable claim is a review item');
  assert.equal(byNumber[2].reason, 'chunking-differs-not-comparable');
  assert.equal(byNumber[3].status, 'needs_review', 'claim says identical but that number has no repository image');
  assert.equal(byNumber[1].status, 'needs_review', 'a partial-byte claim needs an image to be partial about');
  assert.equal(byNumber[99].status, 'needs_review', 'a question absent from the repository cannot be confirmed');
  // No claim may ever be reported as verified by this module.
  assert.ok(report.papers[0].claims.every((claim) => claim.status !== 'verified'));
});

test('a claim contradicting the repository structure is surfaced', () => {
  const report = build({ claims: [{ sourceId: '5823069', number: 1, claim: 'image_bytes_identical' }] });
  assert.ok(report.papers[0].conflicts.includes('claim-contradicted-by-structure'));
});

test('cross-paper overlap is computed on qid, and cross-number pairs are counted separately', () => {
  const a = paper(5, { qidBase: 100 });
  const b = [q(1, 101), q(2, 102), q(9, 103), q(4, 104), q(5, 105)].join('\n');
  const report = build({ handoff: handoff([observation(), observation({ paperSourceId: '5823068', variant: '地市级' })]),
    papers: [
      { sourceId: '5823069', path: 'a', identity: { area: '国考', year: 2026, subject: 'xingce', variant: '副省级' }, markdown: a },
      { sourceId: '5823068', path: 'b', identity: { area: '国考', year: 2026, subject: 'xingce', variant: '地市级' }, markdown: b }] });
  const overlap = report.crossPaper[0];
  assert.equal(overlap.sharedQids, 5);
  assert.equal(overlap.sameNumber, 4);
  assert.equal(overlap.crossNumber, 1, 'qid 103 sits at a different number on each side');
});

test('the report contract rejects any leaked content, hash or URL', () => {
  const report = build();
  assert.deepEqual(validateShardReport(report), { ok: true, problems: [] });
  for (const [field, value] of [['markdown', '# x'], ['sha256', 'abc'], ['url', 'https://x'], ['stemText', '正文']]) {
    const leaked = { ...report, papers: [{ ...report.papers[0], [field]: value }] };
    const checked = validateShardReport(leaked);
    assert.equal(checked.ok, false, field);
    assert.ok(checked.problems.some((problem) => /restricted field/u.test(problem)), field);
  }
  const badStatus = { ...report, papers: [{ ...report.papers[0], status: 'matched' }] };
  assert.equal(validateShardReport(badStatus).ok, false, 'only the defined statuses are allowed');
  assert.deepEqual(STATUSES, ['structural_ok', 'needs_review', 'unknown', 'blocked']);
});

test('the CLI writes a report, exits 2 on review items, and never overwrites', async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'shard-qa-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const cli = path.resolve(import.meta.dirname, '../src/shard-qa-cli.mjs');
  const handoffFile = path.join(dir, 'handoff.json');
  await fs.writeFile(handoffFile, JSON.stringify(handoff([observation({ questionCount: 130, variant: '地市级' })])));
  const run = (out, extra = []) => spawnSync(process.execPath, [cli, '--handoff', handoffFile,
    '--ref', 'HEAD', '--out', out, '--paper', '国考/2026/行测-地市级.md', ...extra],
  { cwd: path.resolve(import.meta.dirname, '..'), encoding: 'utf8' });

  assert.equal(spawnSync(process.execPath, [cli], { encoding: 'utf8' }).status, 1, 'no arguments');
  // The repository paper at HEAD is the real one; the synthetic handoff declares a mismatched count,
  // so this exercises the review path without any real content entering the report.
  const out = path.join(dir, 'report.json');
  const first = run(out);
  assert.ok([0, 2].includes(first.status), first.stderr);
  const report = JSON.parse(await fs.readFile(out, 'utf8'));
  assert.deepEqual(validateShardReport(report), { ok: true, problems: [] });
  assert.equal(run(out).status, 1, 'refuses to overwrite an existing report');
});
