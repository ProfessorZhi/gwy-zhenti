import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { comparePaper, selectPrPath, variantKey } from '../src/source-backed-qa.mjs';

function srcDoc(questions, { assets = [], identity = {} } = {}) {
  return { identity: { id: '1', area: '浙江', year: 2020, subject: 'xingce', variant: 'a', ...identity },
    questions: questions.map((q, i) => ({ id: 'q' + (i + 1), number: q.n ?? i + 1,
      contentHtml: '<p>' + q.stem + '</p>', answerHtml: q.ans,
      explanationHtml: q.exp == null ? '' : '<p>' + q.exp + '</p>',
      options: q.opts.map((t, k) => ({ label: 'ABCD'[k], contentHtml: '<p>' + t + '</p>' })), materialIds: [] })),
    assets, materials: [] };
}
function prDoc(questions, { answersAtEnd = true, sectionTitle = '答案与解析' } = {}) {
  const q = questions.map((x) => `### 第 ${x.n} 题\n\n${x.stem}\n\n` + x.opts.map((t, k) => `${'ABCD'[k]}. ${t}`).join('\n')).join('\n\n');
  const d = questions.map((x) => `<details>\n<summary>第 ${x.n} 题</summary>\n\n**答案（${x.ans}）**\n\n${x.ans}\n\n**解析**\n\n${x.exp ?? ''}\n\n</details>`).join('\n\n');
  return `# paper\n\n## 题目\n\n${q}\n\n` + (answersAtEnd ? `## ${sectionTitle}\n\n${d}\n` : d);
}
function tmp(doc) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'spqa-'));
  fs.writeFileSync(path.join(dir, 'document.json'), JSON.stringify(doc));
  return dir;
}
const q = (n, stem, opts, ans, exp = 'reason ' + n) => ({ n, stem, opts, ans, exp });

test('cross-variant manifest selection is rejected', () => {
  const manifest = [{ area: '浙江', year: '2020', subject: '行测', paper_type: 'b', path: 'x.md' }];
  const r = selectPrPath(manifest, { area: '浙江', year: 2020, subject: 'xingce', variant: 'a' });
  assert.equal(r.ok, false);
  assert.equal(r.reason, 'NO_PR_MATCH');
  assert.equal(variantKey('A类'), 'a');
  assert.notEqual(variantKey('A类'), variantKey('B类'));
});

test('missing question -> unmatched, no fabricated match', () => {
  const sd = tmp(srcDoc([q(1, 's1', ['a', 'b', 'c', 'd'], 'A'), q(2, 's2', ['e', 'f', 'g', 'h'], 'B'), q(3, 's3', ['i', 'j', 'k', 'l'], 'C')]));
  const pr = prDoc([q(1, 's1', ['a', 'b', 'c', 'd'], 'A'), q(2, 's2', ['e', 'f', 'g', 'h'], 'B')]);
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.deepEqual(r.unmatchedSource, [3]);
  assert.equal(r.strongMatches.length, 2);
  assert.equal(r.qaVerdict, 'PENDING_REVIEW');
});

test('qid/PR number swap is matched by content, not number', () => {
  const sd = tmp(srcDoc([q(1, 'alpha', ['a', 'b', 'c', 'd'], 'A'), q(2, 'beta', ['e', 'f', 'g', 'h'], 'B')]));
  const pr = prDoc([q(1, 'beta', ['e', 'f', 'g', 'h'], 'B'), q(2, 'alpha', ['a', 'b', 'c', 'd'], 'A')]);
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.deepEqual(r.strongMatches.sort(), [1, 2]);
  assert.equal(r.answerMatch.length, 2);
});

test('answer section at end and last question are parsed without swallowing', () => {
  const sd = tmp(srcDoc([q(1, 'one', ['a', 'b', 'c', 'd'], 'A'), q(2, 'two', ['e', 'f', 'g', 'h'], 'D')]));
  const pr = prDoc([q(1, 'one', ['a', 'b', 'c', 'd'], 'A'), q(2, 'two', ['e', 'f', 'g', 'h'], 'D')]);
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.equal(r.prDetailsBlocks, 2);
  assert.equal(r.prQ, 2);
  assert.deepEqual(r.answerMatch.sort(), [1, 2]);
});

test('option reorder: letter changed but option text answer matches', () => {
  const sd = tmp(srcDoc([q(1, 'stem', ['x', 'y', 'z', 'w'], 'A')]));
  const pr = prDoc([q(1, 'stem', ['y', 'x', 'z', 'w'], 'B')]);
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.deepEqual(r.optionOrderChanged, [1]);
  assert.deepEqual(r.answerMatch, [1]);
  assert.deepEqual(r.answerConflict, []);
  assert.equal(r.qaVerdict, 'PENDING_REVIEW');
});

test('empty explanation -> explanationMissing and no pass', () => {
  const sd = tmp(srcDoc([q(1, 'stem', ['a', 'b', 'c', 'd'], 'A', '')]));
  const pr = prDoc([q(1, 'stem', ['a', 'b', 'c', 'd'], 'A', '')]);
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.deepEqual(r.explanationMissing, [1]);
  assert.equal(r.qaVerdict, 'PENDING_REVIEW');
});

test('image referenced but asset has no SHA -> insufficient evidence', () => {
  const sd = tmp(srcDoc([{ n: 1, stem: 'stem', opts: ['a', 'b', 'c', 'd'], ans: 'A', exp: 'r' }], { assets: [{ url: 'u', sha256: null }] }));
  const doc = JSON.parse(fs.readFileSync(path.join(sd, 'document.json'), 'utf8'));
  doc.questions[0].contentHtml = '<p>stem</p><img src="u">';
  fs.writeFileSync(path.join(sd, 'document.json'), JSON.stringify(doc));
  const r = comparePaper({ sourceDir: sd, prMarkdown: prDoc([q(1, 'stem', ['a', 'b', 'c', 'd'], 'A')]), prPath: 'p.md', sourceId: '1' });
  assert.equal(r.imageShaEvidence, 'insufficient');
  assert.equal(r.assetsWithSha, 0);
});

test('stale source SHA is recorded', () => {
  const sd = tmp(srcDoc([q(1, 'stem', ['a', 'b', 'c', 'd'], 'A')]));
  const r = comparePaper({ sourceDir: sd, prMarkdown: prDoc([q(1, 'stem', ['a', 'b', 'c', 'd'], 'A')]),
    prPath: 'p.md', sourceId: '1', expected: { docSha12: 'deadbeefdead' } });
  assert.ok(r.reasons.includes('stale-source-sha'));
  assert.equal(r.revision.length, 12);
});

test('unique PR stem with extra trailing text still matches, flagged prefix', () => {
  const s = '这是第一道题的题干内容需要判断下列说法';
  const sd = tmp(srcDoc([q(1, s, ['甲项', '乙项', '丙项', '丁项'], 'A')]));
  const pr = prDoc([q(1, s + '根据上述材料下列哪一项是正确的', ['甲项', '乙项', '丙项', '丁项'], 'A')]);
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.deepEqual(r.strongMatches, [1]);
  assert.deepEqual(r.stemPrefixMatch, [1]);
  assert.ok(r.prStemExtraChars[1] > 0);
  assert.deepEqual(r.answerMatch, [1]);
  assert.equal(r.qaVerdict, 'PENDING_REVIEW');
  assert.equal(r.structuralOnly, true);
});

test('ambiguous PR stem prefix is never forced into a match', () => {
  const s = '这是第一道题的题干内容需要判断下列说法';
  const sd = tmp(srcDoc([q(1, s, ['甲项', '乙项', '丙项', '丁项'], 'A')]));
  const pr = prDoc([q(1, s + '甲乙两种补充说明文字', ['甲项', '乙项', '丙项', '丁项'], 'A'),
    q(2, s + '丙丁两种补充说明文字', ['甲项', '乙项', '丙项', '丁项'], 'A')]);
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.deepEqual(r.strongMatches, []);
  assert.deepEqual(r.stemPrefixMatch, []);
  assert.deepEqual(r.unmatchedSource, [1]);
});

test('schema B: inline details without answer section still parses', () => {
  const sd = tmp(srcDoc([q(1, '首题题干内容', ['甲', '乙', '丙', '丁'], 'B'), q(2, '次题题干内容', ['戊', '己', '庚', '辛'], 'D')]));
  const pr = prDoc([q(1, '首题题干内容', ['甲', '乙', '丙', '丁'], 'B'), q(2, '次题题干内容', ['戊', '己', '庚', '辛'], 'D')],
    { answersAtEnd: false });
  const r = comparePaper({ sourceDir: sd, prMarkdown: pr, prPath: 'p.md', sourceId: '1' });
  assert.equal(r.prHasAnswerSection, false);
  assert.equal(r.prDetailsBlocks, 2);
  assert.equal(r.prQ, 2);
  assert.deepEqual(r.answerMatch.sort(), [1, 2]);
  assert.deepEqual(r.unmatchedSource, []);
});
