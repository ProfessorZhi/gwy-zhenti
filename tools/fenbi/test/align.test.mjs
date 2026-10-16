import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createDocument } from '../src/model.mjs';
import { comparePaper, parseRepositoryPaper, normalizeComparisonText } from '../src/align.mjs';

const question = (id = '101', number = 1, contentHtml = '当 x ≥ 10 时，求 2 + 3。') => ({ id, number, contentHtml,
  options: [{ label: 'A', contentHtml: '5' }, { label: 'B', contentHtml: '6' }], materialIds: [], answerHtml: 'A', explanationHtml: '相加得5。' });
const mdQuestion = (id = '101', number = 1, content = '当 x ≥ 10 时，求 2 + 3。') => `## 第 ${number} 题 <sub>qid ${id} · 计算</sub>\n\n${content}\n\n- **A**. 5\n- **B**. 6\n`;
const answer = (number = 1) => `<details>\n<summary>第 ${number} 题</summary>\n\n**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n相加得5。\n\n---\n</details>`;
function fixture(q = question()) { const doc = createDocument({ id: 'paper', subject: 'xingce' }); doc.questions = [q]; doc.expected.questions = 1; return doc; }
const markdown = () => `${mdQuestion()}\n## 答案与解析\n${answer()}`;

test('qid aligns shifted original numbers but flags sequence and number differences', async () => {
  const doc = fixture(question('101', 2));
  const report = await comparePaper(doc, markdown());
  assert.equal(report.questions[0].matchMethod, 'qid');
  assert.equal(report.questions[0].dimensions.number.status, 'different');
  assert.equal(report.questions[0].dimensions.answer.status, 'same');
  assert.equal(report.questions[0].dimensions.explanation.status, 'same');
  assert.equal(report.paper.order.status, 'different');
  assert.equal(report.paper.orderById.status, 'same');
});

test('same original number with different text is never matched without source qid', async () => {
  const report = await comparePaper(fixture(question('', 1, '完全不同的题目。')), markdown());
  assert.equal(report.summary.matched, 0);
  assert.equal(report.summary.unmatchedSource, 1);
});

test('no qid or number requires unique full stem and options, not array position', async () => {
  const doc = fixture(question('', null));
  assert.equal((await comparePaper(doc, markdown())).questions[0].matchMethod, 'unique-content-and-options');
  doc.questions[0].options[0].contentHtml = '7';
  assert.equal((await comparePaper(doc, markdown())).summary.matched, 0);
});

test('format-only normalization keeps condition digits and mathematical operators', async () => {
  const doc = fixture(question('101', 1, '<p>当 x ≥ １０ 时，求 2 + 3。</p>'));
  assert.equal((await comparePaper(doc, markdown())).questions[0].dimensions.stem.status, 'same');
  doc.questions[0].contentHtml = '当 x > 10 时，求 2 + 3。';
  assert.equal((await comparePaper(doc, markdown())).questions[0].dimensions.stem.status, 'different');
  doc.questions[0].contentHtml = '当 x ≥ 100 时，求 2 + 3。';
  assert.equal((await comparePaper(doc, markdown())).questions[0].dimensions.stem.status, 'different');
});

test('unknown source answers and explanations remain unknown even if repository has them', async () => {
  const doc = fixture(); doc.questions[0].answerHtml = ''; doc.questions[0].explanationHtml = '';
  const report = await comparePaper(doc, markdown());
  assert.equal(report.questions[0].dimensions.answer.status, 'unknown');
  assert.equal(report.questions[0].dimensions.explanation.status, 'unknown');
  assert.equal(report.summary.allQualityPassed, false);
});

test('observed source answer missing in repository is a real difference', async () => {
  const report = await comparePaper(fixture(), mdQuestion());
  assert.equal(report.questions[0].dimensions.answer.status, 'different');
  assert.equal(report.questions[0].dimensions.explanation.status, 'different');
});

test('material heading ends previous question and range attaches shared materials', async () => {
  const md = `${mdQuestion()}\n## 材料 1（第2—3题共用）\n\n共享材料正文。\n\n${mdQuestion('102', 2, '读取材料。').replace('## 第', '### 第')}\n${mdQuestion('103', 3, '继续读取。').replace('## 第', '### 第')}`;
  const parsed = parseRepositoryPaper(md);
  assert.equal(parsed.questions[0].options[1].contentHtml, '6');
  assert.deepEqual(parsed.questions[0].materialIds, []);
  assert.deepEqual(parsed.questions[1].materialIds, ['1']);
  const doc = fixture(question('102', 2, '读取材料。'));
  doc.questions[0].materialIds = ['source-m']; doc.materials = [{ id: 'source-m', contentHtml: '<p>共享材料正文。</p>' }];
  assert.equal((await comparePaper(doc, md)).questions[0].dimensions.materials.status, 'same');
});

test('image presence is retained, unknown image content cannot pass as verified', async () => {
  const q = question('101', 1, '公式：<img src="https://example.com/formula.png">');
  const md = mdQuestion('101', 1, '公式：![公式](../../../图片/formula.png)');
  const report = await comparePaper(fixture(q), md);
  assert.equal(report.questions[0].dimensions.stem.status, 'same');
  assert.equal(report.questions[0].dimensions.images.status, 'unknown');
  assert.match(normalizeComparisonText(q.contentHtml).strict, /IMAGE/u);
  assert.equal((await comparePaper(fixture(q), mdQuestion('101', 1, '公式：'))).questions[0].dimensions.stem.status, 'different');
});

test('ambiguous fingerprints and duplicate qids never silently select first question', async () => {
  const doc = fixture(question('', null));
  assert.equal((await comparePaper(doc, mdQuestion() + mdQuestion('102', 2))).summary.matched, 0);
  assert.equal((await comparePaper(fixture(), mdQuestion() + mdQuestion('101', 2))).summary.matched, 0);
});

test('reports never include question body, authentication data, or source URL query', async () => {
  const doc = fixture(); doc.source.url = 'https://www.fenbi.com/?token=private-token'; doc.cookie = 'secret-cookie';
  const report = JSON.stringify(await comparePaper(doc, markdown()));
  assert.ok(!report.includes('当 x'));
  assert.ok(!report.includes('private-token'));
  assert.ok(!report.includes('secret-cookie'));
});

test('incomplete source captures do not certify paper counts or unseen material totals', async () => {
  const doc = fixture(); doc.expected.questions = 110;
  const report = await comparePaper(doc, markdown());
  assert.equal(report.paper.questionCount.status, 'unknown');
  assert.equal(report.paper.materialCount.status, 'unknown');
  assert.equal(report.questions[0].dimensions.materials.status, 'unknown');
});

test('mixed HTML and Markdown image references retain original order', () => {
  assert.deepEqual(normalizeComparisonText('<img src="first.png"> and ![](second.png)').images, ['first.png', 'second.png']);
});

test('image comparison verifies actual source and repository bytes rather than URL similarity', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'fenbi-align-'));
  try {
    const assetRoot = path.join(root, 'assets'), repoRoot = path.join(root, 'repo');
    await mkdir(assetRoot); await mkdir(repoRoot);
    const bytes = Buffer.from('same-image-content'), hash = createHash('sha256').update(bytes).digest('hex');
    await writeFile(path.join(assetRoot, 'image.png'), bytes); await writeFile(path.join(repoRoot, 'existing.png'), bytes);
    const doc = fixture(question('101', 1, '图形：<img src="https://example.com/source.png">'));
    doc.assets = [{ url: 'https://example.com/source.png', localPath: 'image.png', sha256: hash, status: 'downloaded' }];
    const md = mdQuestion('101', 1, '图形：![](existing.png)');
    const options = { assetRoot, repoRoot, paperPath: path.join(repoRoot, 'paper.md') };
    assert.equal((await comparePaper(doc, md, options)).questions[0].dimensions.images.status, 'same');
    await writeFile(path.join(repoRoot, 'existing.png'), Buffer.from('different-content'));
    assert.equal((await comparePaper(doc, md, options)).questions[0].dimensions.images.status, 'different');
    doc.assets[0].localPath = '../outside.png';
    assert.equal((await comparePaper(doc, md, options)).questions[0].dimensions.images.status, 'unknown');
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('Fenbi DOM keys and repository qids use separate namespaces without false ID differences', async () => {
  const doc = fixture(question('3_1_beq2d', 1));
  doc.identity.questionIdNamespace = 'fenbi-question-key';
  const report = await comparePaper(doc, markdown());
  assert.equal(report.summary.matched, 1);
  assert.equal(report.questions[0].matchMethod, 'explicit-number-and-content');
  assert.equal(report.questions[0].dimensions.qid.status, 'not_compared');
  assert.equal(report.paper.qidSet.status, 'not_compared');
  assert.equal(report.paper.orderById.status, 'not_compared');
  assert.equal(report.paper.order.status, 'same');
});

test('different namespaces never match coincidentally equal IDs or use number alone', async () => {
  const doc = fixture(question('101', 1, '不同的题干。'));
  doc.identity.questionIdNamespace = 'fenbi-question-key';
  const report = await comparePaper(doc, markdown());
  assert.equal(report.summary.matched, 0);
  assert.equal(report.paper.order.status, 'unknown');
  doc.questions[0].contentHtml = question().contentHtml;
  doc.questions[0].number = null;
  assert.equal((await comparePaper(doc, markdown())).summary.matched, 0);
});

test('explicit equal namespaces permit ID matching and missing source numbers remain unknown', async () => {
  const doc = fixture(question('101', null));
  doc.identity.questionIdNamespace = 'custom-id';
  const report = await comparePaper(doc, markdown(), { repositoryQuestionIdNamespace: 'custom-id' });
  assert.equal(report.questions[0].matchMethod, 'qid');
  assert.equal(report.questions[0].dimensions.qid.status, 'same');
  assert.equal(report.paper.order.status, 'unknown');
  assert.equal(report.paper.orderById.status, 'same');
});

test('protocol-relative and relative source images resolve against the actual captured source URL', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'fenbi-align-url-'));
  try {
    const assetRoot = path.join(root, 'assets'), repoRoot = path.join(root, 'repo');
    await mkdir(assetRoot); await mkdir(repoRoot);
    const bytes = Buffer.from('identical-image'), hash = createHash('sha256').update(bytes).digest('hex');
    await writeFile(path.join(assetRoot, 'image.png'), bytes); await writeFile(path.join(repoRoot, 'existing.png'), bytes);
    const options = { assetRoot, repoRoot, paperPath: path.join(repoRoot, 'paper.md') };
    const md = mdQuestion('101', 1, '图形：![](existing.png)');
    const doc = fixture(question('101', 1, '图形：<img src="//fb.fbstatic.cn/images/source.png">'));
    doc.source.url = 'https://www.fenbi.com/spa/tiku/paper';
    doc.assets = [{ url: 'https://fb.fbstatic.cn/images/source.png', localPath: 'image.png', sha256: hash, status: 'downloaded' }];
    assert.equal((await comparePaper(doc, md, options)).questions[0].dimensions.images.status, 'same');
    doc.questions[0].contentHtml = '图形：<img src="../images/source.png">';
    doc.assets[0].url = 'https://www.fenbi.com/spa/images/source.png';
    assert.equal((await comparePaper(doc, md, options)).questions[0].dimensions.images.status, 'same');
    doc.source.url = '';
    const missingBase = (await comparePaper(doc, md, options)).questions[0].dimensions.images;
    assert.equal(missingBase.status, 'unknown');
    assert.equal(missingBase.reason, 'source-image-base-url-not-observed');
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('superscript and subscript mathematics never collapse to ordinary condition digits', async () => {
  for (const [source, repository] of [['求 x² + 1。', '求 x2 + 1。'], ['当 a₁ = 5。', '当 a1 = 5。']]) {
    const doc = fixture(question('101', 1, source));
    assert.equal((await comparePaper(doc, mdQuestion('101', 1, repository))).questions[0].dimensions.stem.status, 'different');
    doc.questions[0].id = '';
    assert.equal((await comparePaper(doc, mdQuestion('101', 1, repository))).summary.matched, 0);
  }
  assert.equal(normalizeComparisonText('ｘ²＋１０　≥　ａ₁').strict, 'x²+10 ≥ a₁');
});
