import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { buildIncrementalReceipt, validateReceipt, CATEGORIES, RECEIPT_KIND, versionMarkers } from '../src/incremental-validator.mjs';

/**
 * Offline synthetic fixtures only. Every stem is invented for this file; nothing here reads a
 * source, a profile, a handoff artefact or the network.
 */

const options = () => [{ label: 'A', contentHtml: '甲选项内容' }, { label: 'B', contentHtml: '乙选项内容' }];
const q = (number, stem, extra = {}) => ({
  id: `q-${number}`, number, contentHtml: `<p>${stem}</p>`, options: options(), materialIds: [],
  answerHtml: 'A', explanationHtml: '合成解析正文。', answerReceipt: 'receipt-1', explanationReceipt: 'receipt-1',
  ...extra,
});
const paper = (sourceQuestions, repositoryQuestions, extra = {}) => ({
  label: extra.label ?? 'synthetic', sourceRights: 'cleared',
  source: { questions: sourceQuestions }, repository: { questions: repositoryQuestions }, ...extra,
});
const receipt = (papers, extra = {}) => buildIncrementalReceipt({ papers, isEligible: () => true, ...extra });
const categoriesOf = (result) => result.rows.map((row) => row.category);

test('a clean same-number paper is ordered, auto-acceptable, and claims no verbatim identity from normalization', () => {
  const result = receipt([paper([q(1, '合成的第一道题干。')], [q(1, '合成的第一道题干。')])]);
  assert.equal(result.kind, RECEIPT_KIND);
  assert.equal(result.counts.ordered_same_number, 1);
  assert.equal(result.counts.humanReviewRequired, 0);
  const [row] = result.rows;
  assert.equal(row.category, 'ordered_same_number');
  assert.equal(row.autoAcceptable, true);
  assert.equal(row.identity, 'normalized-equal');
  assert.equal(result.verbatimIdentityNotClaimed, true);
  assert.deepEqual(validateReceipt(result), { ok: true, problems: [] });
});

test('reordered content is cross-number, and a matching number never makes it ordered', () => {
  const result = receipt([paper(
    [q(1, '合成题甲的内容。'), q(2, '合成题乙的内容。')],
    [q(7, '合成题甲的内容。'), q(2, '完全不同的合成题乙内容。')])]);
  const cross = result.rows.find((row) => row.sourceNumber === 1);
  assert.equal(cross.category, 'cross_number');
  assert.equal(cross.sameNumber, false);
  // Same number, different content: must not be reported as ordered.
  const same = result.rows.find((row) => row.sourceNumber === 2);
  assert.notEqual(same?.category, 'ordered_same_number');
});

test('a recollection variant is a review item, not a match', () => {
  const result = receipt([paper([q(1, '某市拟在三年内完成道路改造，预计投入约三亿元。')],
    [q(1, '某市计划在三年内完成道路改造工程，预计投入资金约三亿元。')])]);
  const [row] = result.rows;
  assert.equal(row.category, 'recollection_variant');
  assert.equal(row.autoAcceptable, false);
  assert.equal(row.requiresHumanReview, true);
  assert.equal(row.identity, 'similar');
});

test('differing version labels make the whole paper advisory', () => {
  const result = receipt([paper([q(1, '同一段合成题干。')], [q(1, '同一段合成题干。')],
    { sourceVersion: '网友回忆版', repositoryVersion: '官方原卷' })]);
  const [row] = result.rows;
  assert.equal(result.papers[0].version.differs, true);
  assert.ok(row.flags.includes('version_wording_differs'));
  assert.equal(row.requiresHumanReview, true);
  assert.equal(row.autoAcceptable, false, 'equal text across two versions is not one verbatim paper');
  assert.equal(validateReceipt(result).ok, true);
});

test('version markers are extracted as metadata, not scored as content', () => {
  assert.deepEqual(versionMarkers('2026上海行测（网友回忆版）'), ['回忆版', '网友回忆']);
  assert.deepEqual(versionMarkers('普通的合成题干，不含版本词。'), []);
});

test('an HTML/markdown pair is normalized-equal but not verbatim-identical', () => {
  const source = q(1, '合成题干内容。');
  const repository = { ...q(1, '合成题干内容。'), contentHtml: '\n\n合成题干内容。\n' };
  const result = receipt([paper([source], [repository])]);
  const [row] = result.rows;
  assert.equal(row.identity, 'normalized-equal');
  assert.equal(row.verbatimIdentical, false, 'different raw bytes are not verbatim identity');
  assert.equal(row.autoAcceptable, true, 'normalization equality is still enough to map');
});

test('a pure-image question is exact only with verified image bytes', () => {
  const hash = (text) => createHash('sha256').update(text).digest('hex');
  const withManifest = (src, verified = true) => ({
    id: 'img', number: 1, contentHtml: `<img src="${src}">`, options: options(), materialIds: [],
    answerHtml: 'A', explanationHtml: '合成解析。', answerReceipt: 'r', explanationReceipt: 'r',
    imageBytes: [{ sha256: hash('same-bytes'), verified }],
  });
  const equal = receipt([paper([withManifest('https://a.test/1.png')], [withManifest('https://b.test/2.png')])]);
  assert.equal(equal.rows[0].grade, 'exact', 'same verified bytes at different paths');
  assert.equal(equal.rows[0].identity, 'none', 'the token is not text evidence');

  const different = receipt([paper([{ ...withManifest('https://a.test/1.png'), imageBytes: [{ sha256: hash('bytes-A'), verified: true }] }],
    [{ ...withManifest('https://a.test/1.png'), imageBytes: [{ sha256: hash('bytes-B'), verified: true }] }])]);
  assert.equal(different.rows[0]?.grade === 'exact', false, 'same path, different bytes');

  const unverified = receipt([paper([withManifest('https://a.test/1.png', false)],
    [{ ...withManifest('https://a.test/1.png'), imageBytes: undefined }])]);
  assert.ok(unverified.rows[0].flags.includes('image_evidence_unverified'));
  assert.equal(unverified.rows[0].autoAcceptable, false);
});

test('missing options, uncollected stubs and answer receipts are separate categories', () => {
  const result = receipt([paper(
    [q(1, '第一道合成题干。', { options: [] }),
      q(2, '第二道合成题干。', { stub: true }),
      q(3, '第三道合成题干。', { answerHtml: '', explanationHtml: '', answerReceipt: undefined, explanationReceipt: undefined }),
      q(4, '第四道合成题干。', { answerReceipt: undefined, explanationReceipt: undefined })],
    [q(1, '第一道合成题干。'), q(2, '第二道合成题干。'), q(3, '第三道合成题干。'), q(4, '第四道合成题干。')])],
  { isEligible: (question) => question.stub !== true });
  const byNumber = Object.fromEntries(result.rows.map((row) => [row.sourceNumber, row]));
  assert.equal(byNumber[1].category, 'missing_options');
  assert.ok(byNumber[2].category === 'uncollected_stub' || byNumber[2].category === 'unmatched_source');
  assert.equal(byNumber[3].answer, 'answer_unknown');
  assert.equal(byNumber[4].answer, 'answer_source_missing');
  assert.ok(result.counts.uncollected_stub >= 1);
});

test('materials and images that exist but cannot be compared are reported, not silently equal', () => {
  const withMaterial = (id) => q(1, '带材料的合成题干。', { materialIds: [id] });
  const result = receipt([paper([withMaterial('m1')], [withMaterial('m2')])]);
  assert.ok(result.rows[0].flags.includes('materials_not_comparable'));
  assert.ok(CATEGORIES.includes(result.rows[0].category));
});

test('a batch beyond the bound is refused rather than truncated', () => {
  const many = Array.from({ length: 3 }, (_v, index) => paper([q(1, `合成题干${index}。`)], [q(1, `合成题干${index}。`)], { label: `p${index}` }));
  const overPapers = receipt(many, { limits: { maxPapers: 2, maxQuestions: 100 } });
  assert.equal(overPapers.blocked, 'batch-over-limit');
  assert.equal(overPapers.rows.length, 0);
  assert.equal(overPapers.counts.overLimit, true);
  const overQuestions = receipt([paper([q(1, '合成甲。'), q(2, '合成乙。')], [q(1, '合成甲。'), q(2, '合成乙。')])],
    { limits: { maxPapers: 10, maxQuestions: 1 } });
  assert.equal(overQuestions.blocked, 'batch-over-limit');
});

test('the receipt is metadata-only and the contract enforces it', () => {
  const secretStem = '这是绝不能出现在回执里的合成题干。';
  const result = receipt([paper([q(1, secretStem)], [q(1, secretStem)])]);
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes('绝不能出现在回执里'), 'question text must never be echoed');
  assert.ok(!serialized.includes('甲选项内容'), 'option text must never be echoed');
  assert.deepEqual(validateReceipt(result), { ok: true, problems: [] });

  const leaked = { ...result, rows: [{ ...result.rows[0], contentHtml: '<p>泄漏</p>' }] };
  const checked = validateReceipt(leaked);
  assert.equal(checked.ok, false);
  assert.ok(checked.problems.some((problem) => /content leaked/u.test(problem)));
});

test('an uncleared source produces structure but no proposals', () => {
  const result = receipt([paper([q(1, '受限来源的合成题干。')], [q(1, '受限来源的合成题干。')], { sourceRights: 'restricted' })]);
  assert.equal(result.blocked, 'some-papers-blocked-by-rights');
  assert.equal(result.counts.ordered_same_number, 0);
  assert.equal(result.papers[0].blocked, 'source-rights-not-cleared');
});

test('the CLI runs a bounded batch and reports exit 0 / 2 / 1', async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mapping-batch-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const cli = path.resolve(import.meta.dirname, '../src/mapping-batch.mjs');
  const run = (inputFile, outFile, extra = []) => spawnSync(process.execPath, [cli, '--input', inputFile, '--out', outFile, ...extra],
    { cwd: path.resolve(import.meta.dirname, '..'), encoding: 'utf8' });

  const clean = path.join(dir, 'clean.json');
  await fs.writeFile(clean, JSON.stringify({ papers: [paper([q(1, '干净批次的合成题干。')], [q(1, '干净批次的合成题干。')])] }));
  const cleanRun = run(clean, path.join(dir, 'clean-out.json'));
  assert.equal(cleanRun.status, 0, cleanRun.stderr);
  const cleanReceipt = JSON.parse(await fs.readFile(path.join(dir, 'clean-out.json'), 'utf8'));
  assert.equal(validateReceipt(cleanReceipt).ok, true);

  const review = path.join(dir, 'review.json');
  await fs.writeFile(review, JSON.stringify({ papers: [paper([q(1, '需要人工复核的合成题干。')], [q(1, '需要人工复核的合成题千。')])] }));
  const reviewRun = run(review, path.join(dir, 'review-out.json'));
  assert.equal(reviewRun.status, 2, reviewRun.stderr);

  assert.equal(run(path.join(dir, 'missing.json'), path.join(dir, 'x.json')).status, 1, 'unreadable input');
  assert.equal(run(clean, path.join(dir, 'clean-out.json')).status, 1, 'refuses to overwrite a receipt');
});

test('the eligibility gate is pluggable, so the authoritative stub policy stays with its owner', async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mapping-gate-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const gateFile = path.join(dir, 'gate.mjs');
  await fs.writeFile(gateFile, "export default (question) => !String(question?.contentHtml ?? '').includes('MARKED');\n");
  const inputFile = path.join(dir, 'batch.json');
  await fs.writeFile(inputFile, JSON.stringify({ papers: [paper([q(1, '合成 MARKED 题干。'), q(2, '正常的合成题干。')],
    [q(1, '合成 MARKED 题干。'), q(2, '正常的合成题干。')])] }));
  const cli = path.resolve(import.meta.dirname, '../src/mapping-batch.mjs');
  const result = spawnSync(process.execPath, [cli, '--input', inputFile, '--out', path.join(dir, 'out.json'), '--gate-module', gateFile],
    { cwd: path.resolve(import.meta.dirname, '..'), encoding: 'utf8' });
  assert.ok([0, 2].includes(result.status), result.stderr);
  const out = JSON.parse(await fs.readFile(path.join(dir, 'out.json'), 'utf8'));
  const rejected = out.rows.filter((row) => row.category === 'uncollected_stub');
  assert.equal(rejected.length, 1);
  assert.equal(rejected[0].sourceNumber, 1);
});
