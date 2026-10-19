import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import {
  isShenlun, ingestShenlun, validateShenlunDocument, assertShenlunPromotable,
  collectShenlunAssets, coverageOf, SHENLUN_SUBJECT,
} from '../src/shenlun-integration.mjs';

// Synthetic filler only — no real exam material, answers or materials.
const FILLER = '合成示例文本，仅用于集成结构测试，不代表任何真题内容。'.repeat(2);
const SH = 'a'.repeat(64);

const ident = (o = {}) => ({ area: '浙江', year: 2026, subject: 'shenlun', variant: 'A类', sourceId: '5254748', ...o });
const mat = (o = {}) => ({ materialId: 'm1', contentHtml: `<p>${FILLER}</p>`, ...o });
const q = (o = {}) => ({ questionId: 'q1', order: 0, promptHtml: `<p>${FILLER}</p>`, materialIds: ['m1'], ...o });
const src = (o = {}) => ({
  identity: ident(), paperId: '5254748', sourceSha: SH, observedAt: '2026-10-20T00:00:00Z',
  materials: [mat()], questions: [q()],
  referenceAnswers: [{ questionId: 'q1', answerHtml: `<p>${FILLER}</p>` }],
  explanations: [{ questionId: 'q1', state: 'absent' }], ...o,
});
const sha = (b) => createHash('sha256').update(b).digest('hex');

// ---------------------------------------------------------------- dispatch
test('subject dispatch recognises shenlun only', () => {
  assert.equal(isShenlun({ subject: 'shenlun' }), true);
  assert.equal(isShenlun({ subject: 'xingce' }), false);
  assert.equal(isShenlun({}), false);
});

test('a shenlun capture is ingested without any options', () => {
  const row = ingestShenlun({ doc: src(), name: 'synthetic-sl' });
  assert.equal(row.subject, SHENLUN_SUBJECT);
  assert.equal(row.grade, 'A');
  assert.deepEqual(row.issues, []);
  assert.equal('options' in row.doc.questions[0], false);
});

test('an incomplete shenlun capture grades C with a reason', () => {
  const row = ingestShenlun({ doc: src({ questions: [{ ...q(), promptHtml: '' }] }), name: 'synthetic-bad' });
  assert.equal(row.grade, 'C');
  assert.ok(row.issues.includes('question-prompt-missing'));
});

test('xingce identity is graded C, never ingested as shenlun', () => {
  const row = ingestShenlun({ doc: src({ identity: ident({ subject: 'xingce' }) }), name: 'x' });
  assert.equal(row.grade, 'C');
  assert.deepEqual(row.issues, ['not-shenlun']);
  assert.equal(row.doc, undefined);          // nothing was parsed as a shenlun document
});

// ---------------------------------------------------------------- validation
test('paperId must match sourceId', () => {
  const doc = ingestShenlun({ doc: src(), name: 'p' }).doc;
  const v = validateShenlunDocument({ ...doc, identity: { ...doc.identity, paperId: '999' } });
  assert.equal(v.ok, false);
  assert.ok(v.problems.some((p) => p.code === 'paper-id-mismatch'));
});

test('expected sourceId mismatch is rejected', () => {
  const doc = ingestShenlun({ doc: src(), name: 'p' }).doc;
  const v = validateShenlunDocument(doc, { expected: { sourceId: '999' } });
  assert.ok(v.problems.some((p) => p.code === 'expected-source-id-mismatch'));
});

test('sourceSha mismatch is rejected', () => {
  const doc = ingestShenlun({ doc: src(), name: 'p' }).doc;
  const v = validateShenlunDocument(doc, { expected: { sourceSha: 'b'.repeat(64) } });
  assert.ok(v.problems.some((p) => p.code === 'source-sha-mismatch'));
});

test('a missing explanation is legal and does not fail validation', () => {
  const doc = ingestShenlun({ doc: src({ explanations: [] }), name: 'p' }).doc;
  const v = validateShenlunDocument(doc);
  assert.equal(v.coverage.explanationsRequired, false);
  assert.equal(v.problems.some((p) => p.code.includes('explanation')), false);
});

test('duplicate questionId is graded C', () => {
  const row = ingestShenlun({ doc: src({ questions: [q(), q({ order: 1 })] }), name: 'dup' });
  assert.equal(row.grade, 'C');
  assert.ok(row.issues.includes('duplicate-question-key'));
});

test('zero and many materials both parse', () => {
  const zero = ingestShenlun({ doc: src({ materials: [], questions: [q({ materialIds: [] })] }), name: 'z' });
  assert.equal(zero.counts.materials, 0);
  const many = ingestShenlun({
    doc: src({ materials: ['m1', 'm2', 'm3'].map((id) => mat({ materialId: id })),
      questions: [q({ materialIds: ['m1', 'm2', 'm3'] })] }), name: 'm',
  });
  assert.equal(many.counts.materials, 3);
});

test('many questions keep order', () => {
  const row = ingestShenlun({
    doc: src({ questions: [q({ questionId: 'q2', order: 1 }), q({ questionId: 'q1', order: 0 })],
      referenceAnswers: [] }), name: 'ord',
  });
  assert.deepEqual(row.doc.questions.map((x) => x.questionId), ['q1', 'q2']);
});

// ---------------------------------------------------------------- assets
test('asset hashes verify against disk', () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'sl-int-'));
  const body = Buffer.from('synthetic-image-bytes');
  writeFileSync(path.join(dir, 'a.png'), body);
  const doc = ingestShenlun({ doc: src({
    referenceAnswers: [{ questionId: 'q1', answerHtml: '', answerImages: ['a.png'] }] }), name: 'a' }).doc;
  const v = validateShenlunDocument(doc, {
    assetRoot: dir, assetManifest: [{ ref: 'a.png', sha256: sha(body) }],
  });
  rmSync(dir, { recursive: true, force: true });
  assert.equal(v.ok, true, JSON.stringify(v.problems));
});

test('missing asset is reported', () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'sl-int-'));
  const doc = ingestShenlun({ doc: src({
    referenceAnswers: [{ questionId: 'q1', answerHtml: '', answerImages: ['zzz.png'] }] }), name: 'a' }).doc;
  const v = validateShenlunDocument(doc, { assetRoot: dir, assetManifest: [{ ref: 'zzz.png', sha256: SH }] });
  rmSync(dir, { recursive: true, force: true });
  assert.ok(v.problems.some((p) => p.code === 'asset-missing'));
});

test('wrong asset hash is reported', () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'sl-int-'));
  writeFileSync(path.join(dir, 'a.png'), Buffer.from('x'));
  const doc = ingestShenlun({ doc: src({
    referenceAnswers: [{ questionId: 'q1', answerHtml: '', answerImages: ['a.png'] }] }), name: 'a' }).doc;
  const v = validateShenlunDocument(doc, { assetRoot: dir, assetManifest: [{ ref: 'a.png', sha256: '0'.repeat(64) }] });
  rmSync(dir, { recursive: true, force: true });
  assert.ok(v.problems.some((p) => p.code === 'asset-sha-mismatch'));
});

test('declared asset refs are collected from materials and answers', () => {
  const doc = ingestShenlun({ doc: src({
    materials: [mat({ contentHtml: '<p>x</p><img src="m.png" />' })],
    referenceAnswers: [{ questionId: 'q1', answerHtml: '', answerImages: ['a.png'] }],
  }), name: 'c' }).doc;
  assert.deepEqual(collectShenlunAssets(doc).sort(), ['a.png', 'm.png']);
});

// ---------------------------------------------------------------- promote gate
test('default capture is blocked from cloud promotion', () => {
  const row = ingestShenlun({ doc: src(), name: 'p' });
  assert.equal(row.rightsStatus, 'unverified');
  assert.equal(row.cloudStorageBlocked, true);
  assert.throws(() => assertShenlunPromotable(row.doc), (e) => e.code === 'shenlun-cloud-blocked');
});

test('cleared rights alone do not unblock promotion', () => {
  const row = ingestShenlun({ doc: src({ rightsStatus: 'cleared' }), name: 'p' });
  assert.throws(() => assertShenlunPromotable(row.doc), (e) => e.detail === 'cloudStorageBlocked-not-lifted');
});

test('cleared rights plus lifted block allows promotion', () => {
  const row = ingestShenlun({ doc: src({ rightsStatus: 'cleared', cloudStorageBlocked: false }), name: 'p' });
  assert.equal(assertShenlunPromotable(row.doc), true);
});

test('a captured sample with unknown coverage is not silently complete', () => {
  const row = ingestShenlun({ doc: src({ explanations: [] }), name: 'p' });
  const cov = coverageOf(row.doc);
  assert.equal(cov.complete, false);
  assert.equal(cov.explanations.unknown, 1);
});

test('receipt carries hashes needed by promote', () => {
  const row = ingestShenlun({ doc: src(), name: 'p' });
  assert.match(row.sourceSha256, /^[0-9a-f]{64}$/u);
  assert.match(row.markdownSha256, /^[0-9a-f]{64}$/u);
});
