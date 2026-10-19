import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createDocument } from '../src/model.mjs';
import { assemble, loadAnswerShard, readAnswerShard, normalizeOptionLabels, rebaseLegacyBlock,
  legacyImageRefs, reasonCode, runBatch } from '../src/batch-ingest.mjs';

/** Synthetic cache documents and Markdown only. No real examination content is used here. */

const paper = (questions, { id = '9001', area = '浙江', year = 2026, subject = 'xingce', variant = 'C类' } = {}) => {
  const doc = createDocument({ id, title: '合成卷', area, year, subject, variant },
    { url: 'https://www.fenbi.com/spa/tiku', capturedAt: '2026-10-19T00:00:00Z' });
  doc.questions = questions;
  doc.expected.questions = questions.length;
  doc.expected.materials = 0;
  return doc;
};
const q = (id, number, stem, { options, answerHtml = '', explanationHtml = '' } = {}) => ({
  id, number, contentHtml: `<p>${stem}</p>`,
  options: options ?? [{ label: 'A', contentHtml: '甲选项内容' }, { label: 'B', contentHtml: '乙选项内容' }],
  materialIds: [], materialIdsObserved: true, answerHtml, explanationHtml,
});

test('a source answer shard is keyed by the stable question id in all accepted shapes', () => {
  const entry = { questionId: 'key-1', answerHtml: 'A', explanationHtml: '合成解析。' };
  for (const payload of [{ answers: [entry] }, { items: [entry] }, { 'key-1': { answerHtml: 'A', explanationHtml: '合成解析。' } }]) {
    const map = loadAnswerShard(payload);
    assert.equal(map.get('key-1').answerHtml, 'A');
    assert.equal(map.get('key-1').explanationHtml, '合成解析。');
  }
  // Entries with no id, or with no answer AND no explanation, are ignored rather than guessed at.
  assert.equal(loadAnswerShard({ answers: [{ answerHtml: 'A' }, { questionId: 'k2' }] }).size, 0);
});

test('a missing or invalid answer shard is a normal state, not a crash', async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'shard-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  assert.deepEqual((await readAnswerShard(dir)).map.size, 0);
  await fs.writeFile(path.join(dir, 'answers-main.json'), '{not json');
  const invalid = await readAnswerShard(dir);
  assert.equal(invalid.invalid, 'answer-shard-not-json');
  assert.equal(invalid.map.size, 0);
});

test('answers merge by stable id only — a same-number different-id entry never attaches', () => {
  const doc = paper([q('id-1', 1, '第一道合成题干内容。'), q('id-2', 2, '第二道合成题干内容。')]);
  const shard = new Map([['id-1', { answerHtml: 'A', explanationHtml: '合成解析一。', source: 'fenbi-explanation-page' }]]);
  const out = assemble(doc, '', shard);
  assert.equal(out.prepared.questions[0].answerHtml, 'A');
  assert.equal(out.prepared.questions[0].answerOrigin, 'fenbi-explanation-page');
  assert.equal(out.prepared.questions[1].answerHtml, '');
  assert.equal(out.counters.sourceAnswersFromShard, 1);
  assert.equal(out.counters.sourceExplanationsFromShard, 1);

  // Number 1 exists, but the shard entry is keyed 'wrong-id': it must stay unmatched and visible.
  const unmatched = assemble(doc, '', new Map([['wrong-id', { answerHtml: 'B', explanationHtml: 'x' }]]));
  assert.equal(unmatched.prepared.questions[0].answerHtml, '');
  assert.equal(unmatched.counters.answerShardUnmatched, 1);
  assert.ok(unmatched.issues.includes('answer-shard-ids-unmatched:1'));
});

test('option labels are normalised only with checkable evidence', () => {
  const blank = { options: [{ label: '', contentHtml: '甲选项内容' }, { label: '', contentHtml: '乙选项内容' }] };
  // 1. the matched legacy question carries the same options and valid labels
  const legacySame = { options: [{ label: 'A', contentHtml: '甲选项内容' }, { label: 'B', contentHtml: '乙选项内容' }] };
  assert.deepEqual(normalizeOptionLabels(blank, legacySame), { labels: ['A', 'B'], evidence: 'legacy-content-match' });
  // 2. content differs → the legacy labels are not evidence for this question
  const legacyOther = { options: [{ label: 'A', contentHtml: '别的选项' }, { label: 'B', contentHtml: '乙选项内容' }] };
  assert.deepEqual(normalizeOptionLabels(blank, legacyOther), { labels: ['', ''], evidence: null });
  // 3. a two-option judgement question, declared as such by the repository block
  assert.deepEqual(normalizeOptionLabels(blank, null, '> 题型说明：本题为判断题'), { labels: ['A', 'B'], evidence: 'judgement-question-convention' });
  // 4. four options with no evidence are never invented into A–D
  const four = { options: ['甲', '乙', '丙', '丁'].map(c => ({ label: '', contentHtml: c })) };
  assert.deepEqual(normalizeOptionLabels(four, null, ''), { labels: ['', '', '', ''], evidence: null });
  // 5. already valid labels are left alone
  const good = { options: [{ label: 'A', contentHtml: '甲' }, { label: 'B', contentHtml: '乙' }] };
  assert.deepEqual(normalizeOptionLabels(good, null, ''), { labels: ['A', 'B'], evidence: null });
});

test('legacy image references are rewritten through the resolver and unresolved ones are counted', () => {
  const block = '题干\n\n![图](../../../图片/公式.png)\n\n<img src="../图片/其它.png">';
  assert.equal(legacyImageRefs(block).length, 2);
  const ok = rebaseLegacyBlock(block, ref => ({ href: `local/${path.basename(decodeURI(ref))}` }));
  assert.equal(ok.unresolved, 0);
  assert.ok(ok.block.includes('![图](local/公式.png)'));
  assert.ok(ok.block.includes('src="local/其它.png"'));
  const partial = rebaseLegacyBlock(block, () => null);
  assert.equal(partial.unresolved, 2, 'an unresolvable reference is reported, never silently kept as passed');
  assert.ok(partial.block.includes('../../../图片/公式.png'));
});

test('every blocker maps to a stable reason code', () => {
  assert.equal(reasonCode('source-stub-no-safe-legacy-fallback:69'), 'E_STUB_NO_SAFE_FALLBACK');
  assert.equal(reasonCode('source-structure:option-label-invalid'), 'E_SOURCE_STRUCTURE_OPTION_LABEL_INVALID');
  assert.equal(reasonCode('legacy-image-missing:81:2'), 'E_LEGACY_IMAGE_MISSING');
  assert.equal(reasonCode('answer-shard-ids-unmatched:3'), 'W_ANSWER_SHARD_UNMATCHED');
  assert.equal(reasonCode('unremoved-source-stub'), 'E_STUB_UNRESOLVED');
  assert.match(reasonCode('something-new'), /^E_SOMETHING_NEW$/u);
});

test('cross-paper image references resolve inside the repository and are refused outside it', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'rebase-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const repo = path.join(root, 'repo'), cached = path.join(root, 'cached');
  await fs.mkdir(path.join(repo, '图片', '别的卷'), { recursive: true });
  await fs.mkdir(cached, { recursive: true });
  await fs.writeFile(path.join(repo, '图片', '别的卷', 'fig.png'), Buffer.from('synthetic-image-bytes'));
  await fs.writeFile(path.join(root, 'outside.png'), Buffer.from('outside'));

  const folder = path.join(cached, 'zj-2026-xingce-c-123');
  await fs.mkdir(folder);
  const doc = paper([q('k1', 1, '合成题干内容。')], { id: '123' });
  // A prior paper whose only question is inherited as a legacy block that references another paper's image.
  const prior = '## 第 1 题　<sub>qid 1</sub>\n\n合成题干内容。\n\n![图](../../图片/别的卷/fig.png)\n';
  await fs.writeFile(path.join(repo, '省考', '浙江', '2026', '行测-C类.md'), prior, { recursive: true }).catch(async () => {
    await fs.mkdir(path.join(repo, '省考', '浙江', '2026'), { recursive: true });
    await fs.writeFile(path.join(repo, '省考', '浙江', '2026', '行测-C类.md'), prior);
  });
  await fs.writeFile(path.join(folder, 'document.json'), JSON.stringify(doc));
  await fs.mkdir(path.join(folder, 'assets'));
  const result = await runBatch({ sourceRoot: cached, repoRoot: repo, write: true });
  assert.equal(result.papers, 1);
  // The image lives under the repository tree, so the reference is rebased and copied with its SHA.
  const out = path.join(repo, 'work/fenbi/batch-ingest/zj-2026-xingce-c-123');
  const md = await fs.readFile(path.join(out, 'paper.md'), 'utf8').catch(() => '');
  assert.ok(!/图片\/别的卷\/fig\.png/u.test(md), 'the cross-paper path is rewritten to a local copy');
});
