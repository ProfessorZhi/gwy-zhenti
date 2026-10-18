import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { buildMappingReport, scorePair, validateMappingReport, MAPPING_REPORT_SCHEMA } from '../src/mapping.mjs';

/**
 * Offline synthetic fixtures for the advisory one-to-one mapping verifier.
 * Every stem below is invented for this test; none of it is real examination content, and nothing
 * here reads a source, a profile or the network.
 */

const OPTIONS = ['甲选项内容', '乙选项内容', '丙选项内容', '丁选项内容'];
const question = (number, stem, { options = OPTIONS, materialIds = [], id } = {}) => ({
  id: id ?? `s-${number}`, number, contentHtml: `<p>${stem}</p>`,
  options: options.map((content, index) => ({ label: 'ABCD'[index], contentHtml: `<p>${content}</p>` })),
  materialIds,
});
const ALLOW = () => true;
const report = (sourceQuestions, repositoryQuestions, extra = {}) => buildMappingReport({
  source: { label: 'synthetic-source', questions: sourceQuestions },
  repository: { label: 'synthetic-repo', questions: repositoryQuestions },
  sourceRights: 'cleared',
  isEligible: ALLOW,
  ...extra,
});

test('an identical pair is the only auto-acceptable grade, and the report stays advisory', () => {
  const stem = '某市计划在三年内完成道路改造工程，预计投入资金约三亿元。';
  const result = report([question(1, stem)], [question(1, stem)]);
  assert.equal(result.assignments.length, 1);
  const [row] = result.assignments;
  assert.equal(row.grade, 'exact');
  assert.equal(row.autoAcceptable, true);
  assert.equal(row.requiresHumanReview, false);
  assert.equal(row.sameNumber, true);
  assert.equal(result.advisoryOnly, true);
  assert.equal(result.blocked, null);
  assert.match(result.limitation, /Advisory mapping only/u);
  assert.deepEqual(validateMappingReport(result), { ok: true, problems: [] });
});

test('out-of-order papers map on content, and the number is reported but never used as evidence', () => {
  const stems = ['第一题的中性描述甲乙丙。', '第二题的中性描述丁戊己。', '第三题的中性描述庚辛壬。'];
  // Source numbering is shuffled against the repository: 1↔3, 2↔1, 3↔2.
  const source = stems.map((stem, index) => question(index + 1, stem));
  const repository = [question(1, stems[1]), question(2, stems[2]), question(3, stems[0])];
  const result = report(source, repository);
  assert.equal(result.counts.assignedExact, 3);
  const bySource = Object.fromEntries(result.assignments.map((row) => [row.sourceNumber, row.repositoryNumber]));
  assert.deepEqual(bySource, { 1: 3, 2: 1, 3: 2 });
  assert.equal(result.counts.sameNumberAssigned, 0, 'no assignment shares its number');
  // Same number with different content must never be paired.
  const mismatch = report([question(1, stems[0])], [question(1, stems[1])]);
  assert.equal(mismatch.assignments.length, 0);
});

test('a partial source maps what it can and reports the rest as unmatched on both sides', () => {
  const stems = ['甲部分的合成题干一。', '甲部分的合成题干二。', '甲部分的合成题干三。', '仅在来源中出现的合成题干。'];
  const source = stems.map((stem, index) => question(index + 1, stem));
  const repository = stems.slice(0, 3).map((stem, index) => question(index + 1, stem))
    .concat([question(9, '仅在库内出现的另一道合成题干。')]);
  const result = report(source, repository);
  assert.equal(result.counts.assignedExact, 3);
  assert.equal(result.counts.unmatchedSource, 1);
  assert.equal(result.counts.unmatchedRepository, 1);
  assert.equal(result.unmatchedSource[0].sourceNumber, 4);
  assert.equal(result.unmatchedRepository[0].repositoryNumber, 9);
});

test('a different recollection version is a candidate for review, never an automatic mapping', () => {
  const source = [question(1, '某市拟在三年内完成道路改造，预计投入约三亿元。')];
  const repository = [question(1, '某市计划在三年内完成道路改造工程，预计投入资金约三亿元。')];
  const result = report(source, repository);
  assert.equal(result.assignments.length, 1);
  const [row] = result.assignments;
  assert.notEqual(row.grade, 'exact');
  assert.equal(row.autoAcceptable, false);
  assert.equal(row.requiresHumanReview, true);
  assert.ok(row.score >= 0.72, `score ${row.score}`);
  assert.equal(row.evidence.stem.available, true);
  assert.equal(row.evidence.options.similarity, 1, 'identical options corroborate the candidate');
});

test('low similarity is never mapped, and nothing below the floor reaches a candidate', () => {
  const source = [question(1, '完全不同的合成题干，讲述海岸线测量。')];
  const repository = [question(1, '另一段无关的合成题干，讨论城市公交线路。')];
  const result = report(source, repository);
  assert.equal(result.assignments.length, 0);
  assert.equal(result.unmatchedSource.length, 1);
  assert.match(result.unmatchedSource[0].reason, /no-candidate|below-candidate-floor/u);
  // A near-miss under the floor is reported with its best score, not silently paired.
  const below = report(source, repository, { policy: { candidateFloor: 0.99, ambiguityMargin: 0.08, weights: { stem: 1, options: 0, materials: 0, images: 0 } } });
  assert.equal(below.assignments.length, 0);
  assert.ok(below.unmatchedSource[0].bestScore < 0.99);
});

test('two candidates within the ambiguity margin are reported, not chosen', () => {
  const stem = '同一段合成题干用于制造两个候选。';
  const source = [question(1, stem)];
  // Two repository rows equally close: one identical, one with a one-character edit.
  const repository = [question(5, '同一段合成题干用于制造二个候选。'), question(6, '同一段合成题干用于制造两亇候选。')];
  const result = report(source, repository);
  assert.equal(result.assignments.length, 0, 'an ambiguous pair must not be assigned');
  assert.equal(result.ambiguous.length, 1);
  assert.equal(result.ambiguous[0].reason, 'candidates-within-margin');
  assert.equal(result.ambiguous[0].candidates.length, 2);
  assert.ok(result.ambiguous[0].candidates.every((candidate) => candidate.requiresHumanReview === undefined));
});

test('two source rows competing for one repository row leave one unclaimed, not double-booked', () => {
  const stem = '库内只有一道这样的合成题干。';
  const source = [question(1, stem), question(2, stem)];
  const repository = [question(1, stem)];
  const result = report(source, repository);
  assert.equal(result.assignments.length, 1);
  assert.equal(result.ambiguous.length, 1);
  assert.equal(result.ambiguous[0].reason, 'repository-row-already-claimed');
  assert.equal(result.counts.unmatchedRepository, 0, 'the one repository row is claimed');
});

test('duplicate numbers on either side are reported as conflicts', () => {
  const result = report([question(7, '重复题号的合成题干甲。'), question(7, '重复题号的合成题干乙。')],
    [question(3, '库内重复题号甲。'), question(3, '库内重复题号乙。')]);
  assert.deepEqual(result.source.duplicateNumbers, [7]);
  assert.deepEqual(result.repository.duplicateNumbers, [3]);
  assert.ok(result.conflicts.some((item) => item.scope === 'source' && item.kind === 'duplicate-number' && item.number === 7));
  assert.ok(result.conflicts.some((item) => item.scope === 'repository' && item.kind === 'duplicate-number' && item.number === 3));
});

test('an ineligible row never enters the candidate pool', () => {
  const stem = '这道合成题在来源侧是未征集占位。';
  const source = [question(1, stem), question(2, '正常的合成题干内容。')];
  const repository = [question(1, stem), question(2, '正常的合成题干内容。')];
  const result = buildMappingReport({
    source: { label: 's', questions: source }, repository: { label: 'r', questions: repository },
    sourceRights: 'cleared',
    // Stand-in for the caller's real gate (collection stub / restricted paper / unobserved slot).
    isEligible: (row) => !/占位/u.test(row.contentHtml),
  });
  assert.equal(result.source.rejected.length, 1);
  assert.equal(result.source.rejected[0].number, 1);
  assert.equal(result.source.rejected[0].reason, 'rejected-by-eligibility-gate');
  assert.ok(!result.assignments.some((row) => row.sourceNumber === 1));
  assert.equal(result.assignments.length, 1, 'only the eligible row is mapped');
  assert.equal(result.repository.total, 2);
});

test('a row with no comparable content is rejected rather than mapped on an empty stem', () => {
  const result = report([{ id: 'empty', number: 4, contentHtml: '', options: [], materialIds: [] }],
    [question(4, '库内的合成题干。')]);
  assert.equal(result.source.rejected[0].reason, 'no-comparable-content');
  assert.equal(result.assignments.length, 0);
});

test('rights are a veto: an uncleared source yields structure but no proposals', () => {
  const stem = '权限未清的合成题干。';
  for (const rights of ['restricted', 'unknown']) {
    const result = report([question(1, stem)], [question(1, stem)], { sourceRights: rights });
    assert.equal(result.blocked, 'source-rights-not-cleared', rights);
    assert.equal(result.assignments.length, 0, rights);
    assert.equal(result.counts.sourceTotal, 1, rights);
    assert.equal(result.counts.eligible, 1, rights);
    assert.equal(validateMappingReport(result).ok, true, rights);
  }
  assert.throws(() => report([question(1, stem)], [question(1, stem)], { sourceRights: 'maybe' }), /sourceRights/u);
});

test('an explicit eligibility gate is mandatory — there is no implicit allow-all', () => {
  assert.throws(() => buildMappingReport({ source: { questions: [] }, repository: { questions: [] }, sourceRights: 'cleared' }),
    /isEligible/u);
  assert.throws(() => buildMappingReport({ source: {}, repository: { questions: [] }, sourceRights: 'cleared', isEligible: ALLOW }),
    /source\.questions/u);
});

test('option labels and order must agree; a contradiction caps the pair at weak', () => {
  const stem = '选项顺序可能不同的合成题干。';
  const source = [question(1, stem)];
  const reversed = { id: 'r-1', number: 1, contentHtml: `<p>${stem}</p>`,
    options: OPTIONS.map((content, index) => ({ label: 'BACD'[index], contentHtml: `<p>${content}</p>` })) };
  const scored = scorePair(source[0], reversed);
  assert.equal(scored.signals.options.contradictory, true);
  assert.equal(scored.grade, 'weak');
  const result = report(source, [reversed]);
  assert.equal(result.assignments.length, 0, 'a contradictory option shape is not a candidate');
});

test('material identity is an independent signal, and a one-sided link is absent evidence', () => {
  const stem = '含图形的合成题干。';
  const material = scorePair({ contentHtml: `<p>${stem}</p>`, options: [], materialIds: ['m1'] },
    { contentHtml: `<p>${stem}</p>`, options: [], materialIds: ['m1'] });
  assert.equal(material.signals.materials.score, 1);
  const noMaterial = scorePair({ contentHtml: `<p>${stem}</p>`, options: [], materialIds: [] },
    { contentHtml: `<p>${stem}</p>`, options: [], materialIds: ['m1'] });
  assert.equal(noMaterial.signals.materials.score, 0);
  assert.equal(noMaterial.signals.materials.contradictory, false, 'a one-sided material link is absent evidence, not a contradiction');
});

// ── F8: image evidence is a content SHA-256 manifest, never a reference path ────────────────
// A reference string is not a content hash: the same path can serve different bytes, and the same
// bytes can live at different paths. Only a verified content manifest may say two images are equal,
// and when it is missing the signal must be neutral instead of scoring zero.

const contentHash = (text) => createHash('sha256').update(text).digest('hex');
const manifest = (...texts) => texts.map((text) => ({ sha256: contentHash(text), verified: true }));
const imageQuestion = (src, imageBytes) => ({ contentHtml: `<img src="${src}">`, options: [], materialIds: [],
  ...(imageBytes === undefined ? {} : { imageBytes }) });

test('the same bytes at different paths are the same image; the same path with different bytes is not', () => {
  const sameBytes = scorePair(imageQuestion('https://example.test/one.png', manifest('figure-bytes')),
    imageQuestion('https://other.test/two.png', manifest('figure-bytes')));
  assert.equal(sameBytes.signals.images.available, true);
  assert.equal(sameBytes.signals.images.basis, 'image-content-sha256');
  assert.equal(sameBytes.signals.images.score, 1, 'content hash decides, not the path');

  const samePathDifferentBytes = scorePair(imageQuestion('https://example.test/same.png', manifest('bytes-A')),
    imageQuestion('https://example.test/same.png', manifest('bytes-B')));
  assert.equal(samePathDifferentBytes.signals.images.score, 0, 'an identical path must never imply identical bytes');
});

test('without a verified content manifest the image signal is neutral, not a zero', () => {
  // Text is a perfect match; an unverified image must not dilute it.
  const stem = '完全相同的合成题干文字。';
  const unverified = { contentHtml: `<p>${stem}</p><img src="https://example.test/a.png">`, options: [], materialIds: [],
    imageBytes: [{ sha256: contentHash('bytes'), verified: false }] };
  const plain = { contentHtml: `<p>${stem}</p><img src="https://example.test/a.png">`, options: [], materialIds: [] };
  const scored = scorePair(unverified, plain);
  assert.equal(scored.signals.images.available, false);
  assert.equal(scored.signals.images.reason, 'image-bytes-not-verified');
  assert.equal(scored.grade, 'exact', 'text alone still carries the exact grade');
  assert.equal(scored.score, 1);

  // A malformed hash counts as no manifest at all: trust none of it. The other side does have a
  // trustworthy manifest, so the reason names that asymmetry rather than claiming both are bad.
  const malformed = scorePair(imageQuestion('https://example.test/a.png', [{ sha256: 'not-a-sha', verified: true }]),
    imageQuestion('https://example.test/a.png', manifest('bytes')));
  assert.equal(malformed.signals.images.available, false);
  assert.equal(malformed.signals.images.reason, 'image-manifest-missing-on-one-side');
  assert.equal(malformed.signals.images.score, 0, 'neutral, never a content verdict');
});

test('an image-only question is never exact on the placeholder token alone', () => {
  const noManifest = scorePair(imageQuestion('https://example.test/a.png'), imageQuestion('https://example.test/b.png'));
  assert.equal(noManifest.signals.stem.available, false, 'the ⟦IMAGE⟧ token is not text evidence');
  assert.equal(noManifest.grade, 'none');
  assert.equal(noManifest.score, 0);

  // With verified byte evidence the pair may be exact — but only when the bytes are equal.
  const equalBytes = scorePair(imageQuestion('https://example.test/a.png', manifest('bytes')),
    imageQuestion('https://example.test/b.png', manifest('bytes')));
  assert.equal(equalBytes.grade, 'exact');
  const differentBytes = scorePair(imageQuestion('https://example.test/a.png', manifest('bytes-A')),
    imageQuestion('https://example.test/b.png', manifest('bytes-B')));
  assert.notEqual(differentBytes.grade, 'exact');
  assert.equal(differentBytes.signals.images.score, 0);
});

test('a restricted source cannot contribute image content evidence', () => {
  const restricted = (src) => ({ contentHtml: `<img src="${src}">`, options: [], materialIds: [],
    imageBytes: [{ sha256: contentHash('bytes'), verified: false }] });
  const scored = scorePair(restricted('https://example.test/a.png'), restricted('https://example.test/a.png'));
  assert.equal(scored.signals.images.available, false);
  assert.equal(scored.signals.images.score, 0, 'no verdict is produced at all');
  // And through the report, an uncleared source still emits no assignment.
  const reportBlocked = report([restricted('https://example.test/a.png')], [restricted('https://example.test/a.png')],
    { sourceRights: 'restricted' });
  assert.equal(reportBlocked.blocked, 'source-rights-not-cleared');
  assert.equal(reportBlocked.assignments.length, 0);
});

test('a text question without images is decided by text, with the image signal neutral', () => {
  const scored = scorePair(question(1, '没有配图的合成题干内容。'), question(1, '没有配图的合成题干内容。'));
  assert.equal(scored.signals.images.available, false);
  assert.equal(scored.signals.images.reason, 'no-images-on-either-side');
  assert.equal(scored.grade, 'exact', 'an absent image dimension must not block a text match');
});

test('neutral Unicode and full-width characters normalise instead of blocking a mapping', () => {
  const source = [question(1, '当 ｘ ≥ １０ 时，求 2 + 3 的值。')];
  const repository = [question(1, '当 x ≥ 10 时，求 2 + 3 的值。')];
  const result = report(source, repository);
  assert.equal(result.assignments.length, 1);
  assert.equal(result.assignments[0].grade, 'exact');
});

test('the same input produces the same report, so a run is auditable', () => {
  const source = [question(2, '可复跑的合成题干甲。'), question(1, '可复跑的合成题干乙。')];
  const repository = [question(1, '可复跑的合成题干乙。'), question(2, '可复跑的合成题干甲。')];
  assert.equal(JSON.stringify(report(source, repository)), JSON.stringify(report(source, repository)));
});

test('the report contract is enforced, not just documented', () => {
  const good = report([question(1, '契约测试的合成题干。')], [question(1, '契约测试的合成题干。')]);
  assert.deepEqual(validateMappingReport(good), { ok: true, problems: [] });
  assert.ok(Object.keys(MAPPING_REPORT_SCHEMA).length >= 13);
  const missing = { ...good }; delete missing.counts;
  assert.equal(validateMappingReport(missing).ok, false);
  const tampered = { ...good, advisoryOnly: false };
  assert.equal(validateMappingReport(tampered).ok, false);
  const badGrade = { ...good, assignments: [{ ...good.assignments[0], grade: 'strong', autoAcceptable: true }] };
  assert.equal(validateMappingReport(badGrade).ok, false, 'only an exact grade may be auto-acceptable');
});

// ── F8 residual (PR #68): a comparable image signal must agree before anything is exact ──────
// A leftover caption character ("图") makes the text look identical while the verified image bytes
// differ. Text equality alone must not turn that into an exact, auto-acceptable match.

const twoOptions = () => [{ label: 'A', contentHtml: '甲选项' }, { label: 'B', contentHtml: '乙选项' }];
const captioned = (caption, bytes, extra = {}) => ({
  contentHtml: `<p>${caption}</p><img src="https://example.test/fig.png">`,
  options: twoOptions(), materialIds: [], imageBytes: manifest(bytes), ...extra,
});

test('a caption plus different verified image bytes fails exact and needs a human', () => {
  const scored = scorePair(captioned('图', 'BYTES-A'), captioned('图', 'BYTES-B'));
  assert.equal(scored.signals.stem.score, 1, 'the caption alone still looks identical');
  assert.equal(scored.signals.images.score, 0);
  assert.equal(scored.signals.images.available, true);
  assert.notEqual(scored.grade, 'exact');
  assert.equal(scored.exactBlockedBy, 'image-evidence-mismatch');
  assert.ok(scored.score > 0.72, `composite stays high (${scored.score.toFixed(4)}) — that is why the grade must gate it`);

  const result = report([captioned('图', 'BYTES-A')], [captioned('图', 'BYTES-B')]);
  assert.equal(result.assignments.length, 1);
  const [row] = result.assignments;
  assert.equal(row.autoAcceptable, false);
  assert.equal(row.requiresHumanReview, true);
  assert.equal(row.exactBlockedBy, 'image-evidence-mismatch');
  assert.equal(result.counts.assignedExact, 0);
});

test('a caption with the same verified bytes is still exact', () => {
  const scored = scorePair(captioned('图', 'SAME-BYTES'), captioned('图', 'SAME-BYTES'));
  assert.equal(scored.grade, 'exact');
  assert.equal(scored.exactBlockedBy, null);
  const result = report([captioned('图', 'SAME-BYTES')], [captioned('图', 'SAME-BYTES')]);
  assert.equal(result.assignments[0].autoAcceptable, true);
});

test('one side having no image evidence neither forces a match nor deducts for it', () => {
  const scored = scorePair(captioned('如图，求面积。', 'BYTES'), { ...captioned('如图，求面积。', 'BYTES'), imageBytes: undefined });
  assert.equal(scored.signals.images.available, false);
  assert.equal(scored.signals.images.reason, 'image-manifest-missing-on-one-side');
  assert.equal(scored.grade, 'exact', 'text is still enough when the image dimension is simply absent');
  assert.equal(scored.exactBlockedBy, null);
});

test('a malformed or unverified manifest is neutral, not a mismatch', () => {
  for (const imageBytes of [[{ sha256: 'not-a-sha', verified: true }],
    [{ sha256: contentHash('BYTES'), verified: false }],
    [{ sha256: contentHash('BYTES') }]]) {
    const scored = scorePair(captioned('图', 'BYTES', { imageBytes }), captioned('图', 'BYTES'));
    assert.equal(scored.signals.images.available, false, JSON.stringify(imageBytes));
    assert.equal(scored.exactBlockedBy, null, 'absent evidence must not read as a conflict');
    assert.equal(scored.grade, 'exact');
  }
});

test('a question with no images behaves exactly as before', () => {
  const scored = scorePair(question(1, '完全没有配图的合成题干。'), question(1, '完全没有配图的合成题干。'));
  assert.equal(scored.signals.images.available, false);
  assert.equal(scored.signals.images.reason, 'no-images-on-either-side');
  assert.equal(scored.grade, 'exact');
  assert.equal(scored.exactBlockedBy, null);
});

test('an image-only stem with identical options but no byte evidence is never exact', () => {
  const bare = (src) => ({ contentHtml: `<img src="${src}">`, options: twoOptions(), materialIds: [] });
  const scored = scorePair(bare('https://example.test/a.png'), bare('https://example.test/b.png'));
  assert.equal(scored.signals.stem.available, false, 'the ⟦IMAGE⟧ token is not text evidence');
  assert.notEqual(scored.grade, 'exact');
  assert.equal(report([bare('https://example.test/a.png')], [bare('https://example.test/b.png')]).counts.assignedExact, 0);
});

test('a comparable material mismatch also blocks exact', () => {
  const scored = scorePair(
    { contentHtml: '<p>材料题的合成题干。</p>', options: twoOptions(), materialIds: ['m1'] },
    { contentHtml: '<p>材料题的合成题干。</p>', options: twoOptions(), materialIds: ['m2'] });
  assert.equal(scored.signals.materials.score, 0);
  assert.notEqual(scored.grade, 'exact');
  assert.equal(scored.exactBlockedBy, 'material-evidence-mismatch');
});
