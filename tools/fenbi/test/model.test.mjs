import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createDocument, absorbPayload, extractCatalog, collectAssetUrls } from '../src/model.mjs';
import { paperProvenance, validateDocument } from '../src/validate.mjs';

function fixture(subject = 'xingce') {
  const doc = createDocument({ id: 'paper-1', title: '2025年江苏省行测C类', subject, year: 2025, area: '江苏', variant: 'C类' }, { url: 'https://www.fenbi.com/spa/tiku' });
  absorbPayload(doc, { paperId: 'paper-1', questionCount: 1, materialCount: 0, questions: [{ id: 'q-100', number: 1, content: '问题正文', options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }], answer: 'B', analysis: '根据题干条件，乙符合要求。' }] });
  return doc;
}

test('explicit complete no-image Xingce paper passes, unknown totals do not', async () => {
  const doc = fixture();
  assert.equal((await validateDocument(doc)).status, 'complete');
  doc.expected.questions = null;
  assert.equal((await validateDocument(doc)).status, 'partial');
});

test('source IDs and array positions never become original question numbers', async () => {
  const doc = fixture(); doc.questions = [];
  absorbPayload(doc, { data: { questions: [{ id: 3921, content: '正文' }] } });
  assert.equal(doc.questions[0].number, null);
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'question-number-invalid'));
});

test('numeric answers need explicit encoding and matching real labels', async () => {
  const doc = fixture(); doc.questions = [];
  const q = { id: 1, number: 1, content: '题干', options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }], answer: 1, analysis: '独立解析' };
  absorbPayload(doc, { questions: [q] });
  assert.equal(doc.questions[0].answerHtml, '1');
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'answer-option-mismatch'));
  const encoded = fixture(); encoded.questions = [];
  absorbPayload(encoded, { answerEncoding: 'zero-based-index', questions: [q] });
  assert.equal(encoded.questions[0].answerHtml, 'B');
});

test('long materials remain intact and conflicting shorter versions never replace them', () => {
  const doc = fixture('shenlun'), long = '材料全文。'.repeat(3000);
  absorbPayload(doc, { materials: [{ id: 'm', content: long }] });
  absorbPayload(doc, { accessories: [{ id: 'm', content: '材料全文。' }] });
  assert.equal(doc.materials[0].contentHtml, long);
  assert.equal(doc.conflicts.length, 1);
});

test('independent answers join by explicit source ID, unmatched answers remain evidence', () => {
  const doc = fixture(); doc.questions[0].answerHtml = '';
  absorbPayload(doc, { data: { answers: [{ questionId: 'q-100', answer: 'B' }, { questionId: 'absent', answer: 'A' }] } });
  assert.equal(doc.questions[0].answerHtml, 'B');
  assert.ok(doc.evidence.some((e) => e.type === 'unmatched-answer'));
});

test('catalog is not a paper body and labels are not guessed into papers', async () => {
  const payload = { data: { papers: [{ id: 3, name: '2025江苏行测C', questionCount: 130 }], labels: [{ id: 4, name: '江苏' }] } };
  const catalog = extractCatalog(payload, { subject: 'xingce', labelId: 1 });
  assert.equal(catalog.papers.length, 1); assert.equal(catalog.labels.length, 1);
  assert.equal(catalog.papers[0].year, 2025);
  const doc = fixture(); doc.questions = []; absorbPayload(doc, payload);
  assert.equal(doc.questions.length, 0);
  assert.notEqual((await validateDocument(doc)).status, 'complete');
});

test('missing explanations, placeholder answers, missing options, and duplicate numbers fail', async () => {
  const doc = fixture();
  doc.questions[0].answerHtml = '查看答案'; doc.questions[0].explanationHtml = '<div></div>'; doc.questions[0].options = [];
  doc.questions.push({ ...doc.questions[0], id: 'other' }); doc.expected.questions = 2;
  const result = await validateDocument(doc);
  for (const code of ['answer-empty', 'explanation-empty', 'options-missing', 'question-number-invalid']) assert.ok(result.issues.some((i) => i.code === code), code);
});

test('Shenlun must retain requirements and resolvable material associations', async () => {
  const doc = fixture('shenlun');
  doc.questions[0].answerHtml = '这是完整参考作答的正文。'.repeat(20);
  const result = await validateDocument(doc);
  for (const code of ['shenlun-materials-empty', 'material-reference-missing', 'requirements-empty']) assert.ok(result.issues.some((i) => i.code === code), code);
  doc.questions[0].materialIds = ['missing'];
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'material-reference-broken'));
});

test('field mapping is explicit and does not recursively mistake arbitrary data for questions', () => {
  const doc = fixture(); doc.questions = [];
  absorbPayload(doc, { unrelated: [{ id: 1, content: 'not a question' }] });
  assert.equal(doc.questions.length, 0);
  absorbPayload(doc, { result: { items: [{ sourceId: 'mapped', position: 9, body: '显式题干' }] } }, { fieldMap: { questions: 'result.items', questionId: 'sourceId', number: 'position', contentHtml: 'body' } });
  assert.equal(doc.questions[0].number, 9); assert.equal(doc.questions[0].contentHtml, '显式题干');
});

test('assets include question, options, materials, answer and explanation images', () => {
  const doc = fixture();
  doc.materials.push({ id: 'm', contentHtml: '<img src="/material.png">' });
  doc.questions[0].options[0].contentHtml = '<img data-src="/option.png">';
  doc.questions[0].answerHtml = '<img src="/answer.png">';
  doc.questions[0].explanationHtml = '<img src="/analysis.png">';
  assert.equal(collectAssetUrls(doc).length, 4);
});

test('missing images and out-of-root paths cannot pass; file reads stay inside root', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'fenbi-test-'));
  try {
    const doc = fixture(); doc.questions[0].contentHtml += '<img src="https://example.test/image.png">';
    assert.ok((await validateDocument(doc, { assetRoot: root })).issues.some((i) => i.code === 'asset-reference-missing'));
    doc.assets.push({ url: 'https://example.test/image.png', localPath: '../outside.png', sha256: 'a'.repeat(64), bytes: 20, width: 1, height: 1, status: 'downloaded' });
    assert.equal((await validateDocument(doc, { assetRoot: root })).status, 'blocked');
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('header-only image integrity never claims a full decode', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'fenbi-test-'));
  try {
    const bytes = Buffer.alloc(24); Buffer.from([137,80,78,71,13,10,26,10]).copy(bytes); bytes.writeUInt32BE(2,16); bytes.writeUInt32BE(3,20);
    await writeFile(path.join(root, 'truncated.png'), bytes);
    const doc = fixture(); doc.questions[0].contentHtml += '<img src="https://example.test/image.png">';
    doc.assets.push({ url: 'https://example.test/image.png', localPath: 'truncated.png', sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length, width: 2, height: 3, status: 'downloaded' });
    const result = await validateDocument(doc, { assetRoot: root });
    assert.equal(result.status, 'partial'); assert.ok(result.issues.some((i) => i.code === 'asset-decode-unverified'));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('observed authentication challenges block capture completion', async () => {
  const doc = fixture(); doc.evidence.push({ type: 'login-required' });
  assert.equal((await validateDocument(doc)).status, 'blocked');
});

test('prefetched responses from another paper are rejected before merging', async () => {
  const doc = fixture();
  absorbPayload(doc, { data: { paper: { id: 'another-paper' }, questions: [{ id: 'intruder', number: 2, content: '其他卷' }] } });
  assert.equal(doc.questions.length, 1);
  assert.ok(doc.evidence.some((e) => e.type === 'rejected-paper-mismatch'));
  assert.notEqual((await validateDocument(doc)).status, 'complete');
});

test('questionIds order is evidence only and never fills original numbers', () => {
  const doc = fixture(); doc.questions = [];
  absorbPayload(doc, { questionIds: ['a'], questions: [{ id: 'a', content: '题干' }] });
  assert.equal(doc.questions[0].number, null);
  assert.ok(doc.evidence.some((e) => e.type === 'source-question-id-order' && e.numberingVerified === false));
});

test('links, explicit drafting placeholders, and invalid image sources are incomplete', async () => {
  const doc = fixture('shenlun');
  doc.questions[0].answerHtml = '<a href="https://example.test">这是一条很长很长但仍然只是来源链接的文字，不是参考作答正文。</a>';
  doc.questions[0].contentHtml = '<img src="javascript:alert(1)">';
  const result = await validateDocument(doc);
  assert.ok(result.issues.some((i) => i.code === 'answer-empty'));
  assert.ok(result.issues.some((i) => i.code === 'image-reference-invalid'));
  doc.questions[0].answerHtml = '第一段正文。此处填写具体案例。' + '参考正文'.repeat(20);
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'answer-placeholder'));
});

test('answers arriving before questions survive and later join without a numeric guess', async () => {
  const doc = fixture(); doc.questions = [];
  absorbPayload(doc, { answers: [{ questionId: 'later', answer: 1, analysis: '先到达的解析', privateCredential: 'must-not-survive' }] });
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'unmatched-answer'));
  assert.ok(!JSON.stringify(doc).includes('must-not-survive'));
  absorbPayload(doc, { questions: [{ id: 'later', number: 1, content: '题干', options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }] }] });
  assert.equal(doc.questions[0].answerHtml, '1');
  assert.equal(doc.questions[0].explanationHtml, '先到达的解析');
  assert.ok(!doc.evidence.some((item) => item.type === 'unmatched-answer'));
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'answer-option-mismatch'));
  const encoded = fixture(); encoded.questions = [];
  absorbPayload(encoded, { answerEncoding: 'one-based-index', answers: [{ questionId: 'later', answer: 2 }] });
  absorbPayload(encoded, { questions: [{ id: 'later', number: 1, content: '题干', options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }] }] });
  assert.equal(encoded.questions[0].answerHtml, 'B');
});

test('successful browser decoding must bind the exact hash and dimensions', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'fenbi-test-'));
  try {
    const bytes = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64');
    const sha256 = createHash('sha256').update(bytes).digest('hex');
    await writeFile(path.join(root, 'pixel.gif'), bytes);
    const doc = fixture(); doc.questions[0].contentHtml += '<img src="https://example.test/pixel.gif">';
    doc.assets.push({ url: 'https://example.test/pixel.gif', localPath: 'pixel.gif', sha256, bytes: bytes.length, width: 1, height: 1, status: 'downloaded', decoded: true,
      decode: { method: 'browser-image-decode', sha256, width: 1, height: 1 } });
    assert.equal((await validateDocument(doc, { assetRoot: root })).status, 'complete');
    doc.assets[0].decode.sha256 = 'a'.repeat(64);
    assert.equal((await validateDocument(doc, { assetRoot: root })).status, 'partial');
    doc.assets[0].decode.sha256 = sha256; doc.assets[0].decode.width = 2;
    assert.equal((await validateDocument(doc, { assetRoot: root })).status, 'partial');
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('Shenlun completeness checks explicit source word limits and does not count links', async () => {
  const doc = fixture('shenlun');
  doc.expected.materials = 1;
  doc.materials = [{ id: 'm', contentHtml: '真实材料内容。'.repeat(50) }];
  const q = doc.questions[0]; q.materialIds = ['m']; q.requirementsHtml = '围绕材料作答，不少于800字。'; q.answerHtml = '完整正文'.repeat(30);
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'answer-below-word-minimum'));
  q.requirementsHtml = '作答不超过100字。';
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'answer-above-word-maximum'));
  q.requirementsHtml = '概括主要做法，不超过200字。';
  assert.equal((await validateDocument(doc)).status, 'complete');
  q.requirementsHtml = '每项不超过100字，共三项。';
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'word-limits-manual-review'));
  q.requirementsHtml = '围绕材料作答。';
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'word-limits-unknown'));
  q.explanationHtml = '<a href="https://example.test">很长的参考解析来源链接，但仍然没有独立解析正文。</a>';
  assert.ok((await validateDocument(doc)).issues.some((i) => i.code === 'explanation-empty'));
});

test('string options get labels only from an explicit verified mapping of equal length', () => {
  const payload = { questions: [{ id: 'mapped', content: '题干', options: ['甲', '乙'] }] };
  const unknown = fixture(); unknown.questions = []; absorbPayload(unknown, payload);
  assert.deepEqual(unknown.questions[0].options.map((option) => option.label), ['', '']);
  const explicit = fixture(); explicit.questions = [];
  absorbPayload(explicit, payload, { fieldMap: { optionLabels: ['A', 'B'] } });
  assert.deepEqual(explicit.questions[0].options.map((option) => option.label), ['A', 'B']);
  const mismatched = fixture(); mismatched.questions = [];
  absorbPayload(mismatched, payload, { fieldMap: { optionLabels: ['A', 'B', 'C', 'D'] } });
  assert.deepEqual(mismatched.questions[0].options.map((option) => option.label), ['', '']);
  const duplicated = fixture(); duplicated.questions = [];
  absorbPayload(duplicated, payload, { fieldMap: { optionLabels: ['A', 'A'] } });
  assert.deepEqual(duplicated.questions[0].options.map((option) => option.label), ['', '']);
});

test('explicit original-number map fills missing numbers, never overrides a source number', async () => {
  const doc = fixture(); doc.questions = [];
  absorbPayload(doc, { questions: [{ id: 'a', content: '甲' }, { id: 'b', number: 9, content: '乙' }, { id: 'c', number: 'not-a-number', content: '丙' }] },
    { fieldMap: { questionNumbersById: { a: 3, b: 4, c: 5 } } });
  assert.equal(doc.questions[0].number, 3);
  assert.equal(doc.questions[1].number, 9);
  assert.equal(doc.questions[2].number, null);
  assert.ok(doc.conflicts.some((item) => item.id === 'b' && item.field === 'number'));
  assert.notEqual((await validateDocument(doc)).status, 'complete');
});

test('paper-declared source question IDs must be unique and match captured IDs', async () => {
  const doc = fixture();
  absorbPayload(doc, { questionIds: ['expected-A'] });
  assert.ok((await validateDocument(doc)).issues.some((issue) => issue.code === 'source-question-id-set-mismatch'));
  doc.evidence = doc.evidence.filter((item) => item.type !== 'source-question-id-order');
  absorbPayload(doc, { questionIds: ['q-100', 'q-100'] });
  assert.ok((await validateDocument(doc)).issues.some((issue) => issue.code === 'source-question-id-set-mismatch'));
});

test('unbound responses stay partial even when all bodies are present', async () => {
  const doc = fixture();
  doc.evidence = [];
  assert.ok((await validateDocument(doc)).issues.some((issue) => issue.code === 'paper-binding-unverified'));
  absorbPayload(doc, { questionIds: ['q-100'] });
  assert.equal((await validateDocument(doc)).status, 'complete');
  assert.equal(doc.questions[0].number, 1);
  doc.evidence = [{ type: 'operator-verified-source', paperId: 'paper-1', url: doc.source.url, verified: false }];
  assert.equal((await validateDocument(doc)).status, 'partial');
  doc.evidence[0].verified = true;
  assert.equal((await validateDocument(doc)).status, 'complete');
});

// ── per-paper provenance and the page-route gate ────────────────────────────────────────────

test('a page that is not on the job route blocks the capture instead of reading the wrong page', async () => {
  for (const reason of ['stayed-on-entry-page', 'paper-opened-in-another-page', 'page-not-on-fenbi']) {
    const doc = fixture();
    doc.evidence.push({ type: 'page-route-mismatch', reason,
      landed: 'https://www.fenbi.com/spa/tiku', expected: 'https://www.fenbi.com/spa/tiku/exam/1' });
    const result = await validateDocument(doc);
    assert.equal(result.status, 'blocked', reason);
    assert.ok(result.issues.some((issue) => issue.code === 'page-route-mismatch'), reason);
    assert.equal(result.dimensions.identity.status, 'blocked', reason);
  }
});

test('a normal landing is recorded but never blocks, and does not by itself make a paper complete', async () => {
  const doc = fixture();
  doc.evidence.push({ type: 'page-landed', url: 'https://www.fenbi.com/spa/tiku/exam/1', expected: doc.source.url, otherObservedPages: [] });
  const result = await validateDocument(doc);
  assert.equal(result.status, 'complete');
  assert.ok(!result.issues.some((issue) => issue.code === 'page-route-mismatch'));
});

test('per-paper provenance names the source of each dimension and refuses to call unbound answers consistent', async () => {
  const doc = fixture();
  doc.evidence.push({ type: 'page-landed', url: 'https://www.fenbi.com/spa/tiku/exam/1' });
  const bound = paperProvenance(doc);
  assert.equal(bound.binding, 'source-paper-identity');
  assert.equal(bound.sources.questions, 'observed-json');
  assert.equal(bound.sources.materials, 'not-observed');
  assert.equal(bound.sources.answers, 'observed');
  assert.equal(bound.sources.explanations, 'observed');
  assert.equal(bound.sources.images, 'not-observed');
  assert.equal(bound.pageLanded, 'https://www.fenbi.com/spa/tiku/exam/1');
  assert.equal(bound.routeMismatch, null);
  assert.equal(bound.consistent, true);

  // The same content with no verified paper binding must not be reported as consistent.
  const unbound = fixture();
  unbound.evidence = [];
  const loose = paperProvenance(unbound);
  assert.equal(loose.binding, 'unverified');
  assert.equal(loose.answersObserved, 1);
  assert.equal(loose.consistent, false);

  // A route mismatch makes the record inconsistent regardless of how much content arrived.
  unbound.evidence = [{ type: 'source-paper-identity', paperId: 'paper-1', url: unbound.source.url },
    { type: 'page-route-mismatch', reason: 'page-not-on-fenbi' }];
  const mismatched = paperProvenance(unbound);
  assert.equal(mismatched.consistent, false);
  assert.equal(mismatched.routeMismatch, 'page-not-on-fenbi');
});

test('a DOM-adapter capture is attributed to the adapter, not to a generic observed payload', () => {
  const doc = fixture();
  doc.evidence = [{ type: 'dom-question-keys', namespace: 'fenbi-question-key', count: 1 }];
  const provenance = paperProvenance(doc);
  assert.equal(provenance.sources.questions, 'dom-adapter');
  assert.equal(provenance.binding, 'unverified', 'the DOM route carries no paper identity by itself');
  assert.equal(provenance.consistent, false);
});
