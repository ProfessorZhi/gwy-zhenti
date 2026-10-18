import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeText, bigrams, jaccard, questionSignature, isImageOnly,
  matchQuestions, gradeMatch, classifyQuestions, coverageTiers, orderMetrics, offsetHistogram, summarize,
} from '../src/reorder.mjs';

const q = (number, stem, options = ['甲', '乙', '丙', '丁'], imageCount = 0) => ({
  number, stem, imageCount, options: options.map((text) => ({ text })),
});

test('normalizeText folds width, strips punctuation and markup', () => {
  assert.equal(normalizeText('<p>甲　乙（　）。</p>'), '甲乙');
  assert.equal(normalizeText('ＡＢＣ１２３'), 'ABC123');
  assert.equal(normalizeText(''), '');
});

test('jaccard is symmetric and bounded', () => {
  assert.equal(jaccard(bigrams('中华人民共和国'), bigrams('中华人民共和国')), 1);
  assert.equal(jaccard(bigrams(''), bigrams('x')), 0);
  assert.equal(jaccard(bigrams('abcd'), bigrams('abef')), jaccard(bigrams('abef'), bigrams('abcd')));
});

test('F6: equality is NORMALIZED, not byte-identical', () => {
  // 仅标点/空白不同 → 规范化后相等，但原文字节并不相同。
  const a = '甲，乙。丙！丁？';
  const b = '甲 乙 丙 丁';
  assert.notEqual(a, b, 'the raw strings really do differ');
  const m = matchQuestions([q(1, a)], [q(1, b)]);
  assert.equal(m.matches.length, 1);
  assert.equal(m.matches[0].normalizedEqual, true);
  // 因此文档必须称 normalized_equal，不得称 "逐字相同/byte-identical"。
  assert.equal(gradeMatch(m.matches[0], [q(1, a)], [q(1, b)]), 'normalized_equal_same_number');
});

test('identity comes from normalized equality, and reordering is graded separately', () => {
  const src = [q(1, '这是第一题的完整题干内容')];
  const rep = [q(7, '这是第一题的完整题干内容')];
  const m = matchQuestions(src, rep);
  assert.equal(m.matches.length, 1);
  assert.equal(gradeMatch(m.matches[0], src, rep), 'normalized_equal_reordered');
});

test('F1: ambiguous ties are NEVER bound and go to reviewCandidates', () => {
  const same = '根据以下材料，回答后面的问题';
  const src = [q(1, same), q(2, same)];
  const rep = [q(8, same), q(9, same)];
  const m = matchQuestions(src, rep);
  const boundSource = new Set(m.matches.map((x) => x.i));
  const ambiguousIndexes = new Set(m.reviewCandidates.map((r) => r.sourceIndex));
  assert.ok(ambiguousIndexes.size > 0, 'tie must be reported');
  for (const i of ambiguousIndexes) assert.equal(boundSource.has(i), false, 'ambiguous source must not be bound');
  assert.equal(new Set(m.matches.map((x) => x.j)).size, m.matches.length, 'no repository index bound twice');
  // 分类层同样不得把它们当已映射
  const rows = classifyQuestions(src, rep, m);
  assert.equal(rows.filter((r) => r.kind === 'manual_review_ambiguous').length, ambiguousIndexes.size);
  const tiers = coverageTiers(src, rows);
  assert.equal(tiers.exact, 0, 'ambiguous pairs must not inflate exact coverage');
});

test('a unique tie-free mapping is one-to-one and fully covered', () => {
  const src = [q(1, '题目甲的正文内容较长'), q(2, '题目乙的正文内容较长'), q(3, '题目丙的正文内容较长')];
  const rep = [q(11, '题目丙的正文内容较长'), q(12, '题目甲的正文内容较长'), q(13, '题目乙的正文内容较长')];
  const m = matchQuestions(src, rep);
  assert.equal(m.matches.length, 3);
  assert.equal(new Set(m.matches.map((x) => x.i)).size, 3);
  assert.equal(new Set(m.matches.map((x) => x.j)).size, 3);
  const rows = classifyQuestions(src, rep, m);
  assert.equal(rows.filter((r) => r.kind === 'normalized_equal_reordered').length, 3);
  assert.equal(coverageTiers(src, rows).coverageExact, 1);
});

test('F3: coverage tiers separate exact / high-confidence(excl weak) / candidates(incl weak)', () => {
  // 构造：1 exact + 1 weak(仅低分相似) + 1 无候选
  const src = [q(1, '完全一致的题目正文内容甲'), q(2, '较弱相似的题目内容乙乙乙'),
    q(3, '毫无对应的孤立题目内容丙丙丙丙')];
  const rep = [q(1, '完全一致的题目正文内容甲'), q(2, '较弱相似但不同的题目乙丁戊')];
  const m = matchQuestions(src, rep, { low: 0.1 });
  const rows = classifyQuestions(src, rep, m, { suggest: 0.85 });
  const t = coverageTiers(src, rows);
  assert.equal(t.eligible, 3);
  assert.ok(t.exact >= 1);
  assert.ok(t.coverageHighConfidence <= t.coverageCandidates, 'high-confidence must exclude weak');
  assert.ok(t.coverageExact <= t.coverageHighConfidence);
  // 三者必须分别可得，且不为同一数值冒充
  assert.ok(typeof t.coverageExact === 'number' && typeof t.coverageHighConfidence === 'number' && typeof t.coverageCandidates === 'number');
});

test('F4: orderMetrics reports real inversions, not just adjacent descents', () => {
  // 相邻下降只有 1 次，但真实逆序对很多
  const mapping = [1, 5, 2, 3, 4].map((repN, idx) => ({ sourceNumber: idx + 1, repositoryNumber: repN }));
  const m = orderMetrics(mapping);
  assert.equal(m.count, 5);
  assert.equal(m.adjacentDescents, 1);
  assert.equal(m.inversions, 3); // 5>2,5>3,5>4
  assert.equal(m.totalPairs, 10);
  assert.ok(m.inversionRate > 0.2, 'inversion rate must be reported, not hidden behind adjacent descents');
});

test('F5: offsetHistogram enumerates every offset with frequencies', () => {
  const mapping = [
    { sourceNumber: 1, repositoryNumber: 16 }, { sourceNumber: 2, repositoryNumber: 18 },
    { sourceNumber: 3, repositoryNumber: 3 }, { sourceNumber: 4, repositoryNumber: 5 },
  ];
  const h = offsetHistogram(mapping);
  // 1→16 = +15, 2→18 = +16, 3→3 = 0, 4→5 = +1
  assert.deepEqual(h, { '0': 1, '1': 1, '15': 1, '16': 1 });
  assert.equal(Object.values(h).reduce((a, b) => a + b, 0), mapping.length, 'histogram must cover all pairs');
});

test('image-only questions are not comparable and excluded from the denominator', () => {
  const src = [q(1, '', [], 2), q(2, '这是一道有足够文字的正规题目')];
  const rep = [q(1, '这是一道有足够文字的正规题目')];
  const m = matchQuestions(src, rep);
  const rows = classifyQuestions(src, rep, m);
  assert.equal(rows.filter((r) => r.kind === 'image_only_not_comparable').length, 1);
  const t = coverageTiers(src, rows);
  assert.equal(t.eligible, 1);
  assert.equal(t.coverageExact, 1);
});

test('unmatched questions are reported, never guessed', () => {
  const src = [q(1, '完全不同的题目内容甲'), q(2, '另一种完全不同内容乙')];
  const rep = [q(1, '毫不相干的第三个题目丙')];
  const m = matchQuestions(src, rep);
  const rows = classifyQuestions(src, rep, m);
  assert.equal(rows.filter((r) => r.kind.startsWith('unmatched')).length, 2);
  assert.equal(rows.filter((r) => r.kind === 'repo_only_absent_in_source').length, 1);
});

test('nullable/empty questions never produce a spurious normalized match', () => {
  // 显式空题干 + 空选项，否则默认选项会让签名非空
  const m = matchQuestions([q(1, '', [])], [q(1, '', [])]);
  assert.equal(m.matches.length, 0, 'empty signatures must not match each other');
  const m2 = matchQuestions([q(1, '', [])], [q(1, '', [])], { low: 0 });
  assert.equal(m2.matches.length, 0, 'even at low=0 an empty signature must not self-match');
});

test('summarize aggregates kinds', () => {
  assert.deepEqual(summarize([{ kind: 'near' }, { kind: 'near' }, { kind: 'weak' }]), { near: 2, weak: 1 });
});

test('questionSignature joins stem and options deterministically', () => {
  const sig = questionSignature({ stem: '题干', options: [{ text: '甲' }, { text: '乙' }] });
  assert.equal(sig.combined, '题干||甲|乙');
  assert.equal(isImageOnly(sig, 0), false);
  assert.equal(isImageOnly(questionSignature({ stem: '', options: [] }), 1), true);
});
