import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeText, bigrams, jaccard, questionSignature, isImageOnly,
  matchQuestions, classifyQuestions, coverage, summarize,
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
  const a = bigrams('中华人民共和国');
  const b = bigrams('中华人民共和国');
  assert.equal(jaccard(a, b), 1);
  assert.equal(jaccard(bigrams(''), bigrams('x')), 0);
  assert.equal(jaccard(bigrams('abcd'), bigrams('abef')), jaccard(bigrams('abef'), bigrams('abcd')));
});

test('identity comes from exact normalized text, not from similarity', () => {
  const src = [q(1, '这是第一题的完整题干内容')];
  const rep = [q(7, '这是第一题的完整题干内容')];
  const m = matchQuestions(src, rep);
  assert.equal(m.matches.length, 1);
  assert.equal(m.matches[0].exact, true);
  assert.equal(m.matches[0].score, 1);
});

test('a reordered paper maps by content while keeping one-to-one binding', () => {
  const src = [q(1, '题目甲的内容比较长一些'), q(2, '题目乙的内容比较长一些'), q(3, '题目丙的内容比较长一些')];
  const rep = [q(11, '题目丙的内容比较长一些'), q(12, '题目甲的内容比较长一些'), q(13, '题目乙的内容比较长一些')];
  const m = matchQuestions(src, rep);
  assert.equal(m.matches.length, 3);
  assert.equal(new Set(m.matches.map((x) => x.i)).size, 3);
  assert.equal(new Set(m.matches.map((x) => x.j)).size, 3);
  const rows = classifyQuestions(src, rep, m);
  assert.equal(rows.filter((r) => r.kind === 'exact_reordered').length, 3);
  assert.equal(rows.filter((r) => r.kind === 'exact_same_number').length, 0);
  assert.equal(coverage(src, rows), 1);
});

test('identical boilerplate questions are ambiguous, never force-bound', () => {
  const same = '根据以下材料，回答后面的问题';
  const src = [q(1, same), q(2, same)];
  const rep = [q(8, same), q(9, same)];
  const m = matchQuestions(src, rep);
  // 允许匹配出若干对，但必须各自一对一
  assert.equal(new Set(m.matches.map((x) => x.i)).size, m.matches.length);
  assert.equal(new Set(m.matches.map((x) => x.j)).size, m.matches.length);
  const rows = classifyQuestions(src, rep, m);
  assert.ok(rows.some((r) => r.kind === 'ambiguous_multi_candidate'),
    'identical content must be surfaced as ambiguous rather than silently bound');
});

test('image-only questions are marked not comparable and excluded from coverage', () => {
  const src = [q(1, '', [], 2), q(2, '这是一道有足够文字的正规题目')];
  const rep = [q(1, '这是一道有足够文字的正规题目')];
  const m = matchQuestions(src, rep);
  const rows = classifyQuestions(src, rep, m);
  assert.equal(rows.filter((r) => r.kind === 'image_only_not_comparable').length, 1);
  assert.equal(coverage(src, rows), 1); // 仅剩 1 道可比较，且已映射
});

test('unmatched questions are reported, not guessed', () => {
  const src = [q(1, '完全不同的题目内容甲'), q(2, '另一种完全不同内容乙')];
  const rep = [q(1, '毫不相干的第三个题目丙')];
  const m = matchQuestions(src, rep);
  const rows = classifyQuestions(src, rep, m);
  assert.equal(rows.filter((r) => r.kind.startsWith('unmatched')).length, 2);
  assert.equal(rows.filter((r) => r.kind === 'repo_only_absent_in_source').length, 1);
});

test('summarize aggregates kinds', () => {
  const rows = [{ kind: 'exact_reordered' }, { kind: 'exact_reordered' }, { kind: 'unmatched_no_candidate' }];
  assert.deepEqual(summarize(rows), { exact_reordered: 2, unmatched_no_candidate: 1 });
});

test('questionSignature joins stem and options deterministically', () => {
  const sig = questionSignature({ stem: '题干', options: [{ text: '甲' }, { text: '乙' }] });
  assert.equal(sig.combined, '题干||甲|乙');
  assert.equal(isImageOnly(sig, 0), false);
  assert.equal(isImageOnly(questionSignature({ stem: '', options: [] }), 1), true);
});
