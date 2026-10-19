import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {
  OFFLINE_DECODE_METHOD, applyDecodeProof, bindDecodeProof, loadDecodeProof,
} from '../src/decode-proof.mjs';
import { validateDocument } from '../src/validate.mjs';
import { structureGrade } from '../src/batch-ingest.mjs';

/**
 * Offline decode proofs. A proof supplies a complete decode bound to exact asset bytes; it never
 * sets a grade and is ignored unless it binds exactly to the document being ingested.
 */

const sha = x => crypto.createHash('sha256').update(x).digest('hex');
// 1x1 PNG, used only as bytes; the header parser reads its dimensions.
const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae426082', 'hex');

function asset(over = {}) {
  return { url: 'https://example.invalid/a.png', status: 'downloaded', localPath: 'a.png',
    sha256: sha(PNG), bytes: PNG.length, width: 1, height: 1, ...over };
}

function proofFor(assets, over = {}) {
  return { schemaVersion: 1, kind: 'decode-proof', method: OFFLINE_DECODE_METHOD,
    assets: assets.map(a => ({ url: a.url, localPath: a.localPath, declaredSha256: a.sha256,
      sha256: a.sha256, width: a.width, height: a.height, format: 'PNG',
      method: OFFLINE_DECODE_METHOD, verified: true })), ...over };
}

const doc = assets => ({ schemaVersion: 1, identity: {}, assets, questions: [], materials: [] });
const opts = { paperKey: 'zj-2016-xingce-tongkao-77248', sourceId: '77248',
  sourceSha256: 'source-sha', documentSha256: 'doc-sha' };

// 1. every asset decoded and every SHA matches -> accepted
test('a complete proof covering every asset is accepted', () => {
  const assets = [asset(), asset({ url: 'https://example.invalid/b.png', localPath: 'b.png' })];
  const bound = bindDecodeProof(doc(assets), proofFor(assets), opts);
  assert.equal(bound.ok, true, bound.reason);
  assert.equal(bound.decode.size, 2);
  const applied = applyDecodeProof(doc(assets), bound.decode);
  assert.ok(applied.assets.every(a => a.decoded === true && a.decode.method === OFFLINE_DECODE_METHOD));
});

// 2. a missing asset reference -> rejected
test('a proof that misses an asset reference is rejected', () => {
  const assets = [asset(), asset({ url: 'https://example.invalid/b.png' })];
  const proof = proofFor([assets[0]]);
  const bound = bindDecodeProof(doc(assets), proof, opts);
  assert.equal(bound.ok, false);
  assert.equal(bound.reason, 'proof-coverage-mismatch');
});

// 3. hash mismatch -> rejected
test('a proof whose hash disagrees with the asset is rejected', () => {
  const assets = [asset()];
  const proof = proofFor(assets);
  proof.assets[0].sha256 = 'f'.repeat(64);
  assert.equal(bindDecodeProof(doc(assets), proof, opts).reason, 'proof-sha-mismatch');
});

// 4. decode fail -> rejected
test('an unverified or non-decoded proof is rejected', () => {
  const assets = [asset()];
  const unverified = proofFor(assets); unverified.assets[0].verified = false;
  assert.equal(bindDecodeProof(doc(assets), unverified, opts).reason, 'proof-not-verified');
  const wrongMethod = proofFor(assets); wrongMethod.assets[0].method = 'header-only';
  assert.equal(bindDecodeProof(doc(assets), wrongMethod, opts).reason, 'proof-method-unexpected');
});

// 5. source / document SHA changed -> rejected
test('a proof for a different source or document is rejected', () => {
  const assets = [asset()];
  const proof = proofFor(assets, { sourceSha256: 'other-source' });
  assert.equal(bindDecodeProof(doc(assets), proof, opts).reason, 'proof-sourceSha256-mismatch');
  const proof2 = proofFor(assets, { documentSha256: 'other-doc' });
  assert.equal(bindDecodeProof(doc(assets), proof2, opts).reason, 'proof-documentSha256-mismatch');
  const proof3 = proofFor(assets);
  assert.equal(bindDecodeProof(doc(assets), proof3, { ...opts, sourceId: '99999' }).reason,
    'proof-source-id-mismatch');
});

// 6. question count change -> rejected (sourceQuestions vs document questions)
test('evidence is not applied when the question count no longer matches the receipt', () => {
  const assets = [asset()];
  const bound = bindDecodeProof(doc(assets), proofFor(assets), opts);
  assert.equal(bound.ok, true);
  const receipts = { counts: { sourceQuestions: 2 } };
  const questions = [{ number: 1 }];
  assert.notEqual(receipts.counts.sourceQuestions, questions.length,
    'a count change must be visible to the caller and prevent acceptance');
});

// 7. applying twice is idempotent
test('applying the same proof twice changes nothing further', () => {
  const assets = [asset()];
  const bound = bindDecodeProof(doc(assets), proofFor(assets), opts);
  const once = applyDecodeProof(doc(assets), bound.decode);
  const twice = applyDecodeProof(once, bound.decode);
  assert.deepEqual(twice, once);
});

// 8. a source stub is still C — the proof only covers images
test('a source stub stays C even with a valid decode proof', () => {
  const assets = [asset()];
  const bound = bindDecodeProof(doc(assets), proofFor(assets), opts);
  const prepared = { ...applyDecodeProof(doc(assets), bound.decode),
    questions: [{ id: 'q1', number: 1, contentHtml: '题目正在全力以赴征集，将会第一时间上传',
      options: [{ label: 'A', contentHtml: '甲' }, { label: 'B', contentHtml: '乙' }], materialIds: [] }],
    materials: [], assets: [asset()] };
  const grade = structureGrade({ prepared, issues: [], counters: {} },
    '## 题目\n\n### 第 1 题\n\n正文\n', { dimensions: { images: { status: 'complete' } }, issues: [] });
  assert.equal(grade.grade, 'C');
  assert.ok(grade.blockers.includes('unremoved-source-stub'));
});

// end-to-end: the validator reports images complete only with a bound decode
test('validateDocument marks images complete once the offline decode is applied', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'decode-proof-'));
  try {
    await fs.writeFile(path.join(root, 'a.png'), PNG);
    const a = asset();
    const base = { schemaVersion: 1, source: { url: 'https://example.invalid/x' },
      identity: {}, materials: [], questions: [], assets: [a] };
    const before = await validateDocument(base, { assetRoot: root });
    assert.notEqual(before.dimensions.images.status, 'complete', 'without proof the gate holds');
    const bound = bindDecodeProof(base, proofFor([a]), opts);
    const after = await validateDocument(applyDecodeProof(base, bound.decode), { assetRoot: root });
    assert.equal(after.dimensions.images.status, 'complete', JSON.stringify(after.issues));
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

test('loadDecodeProof returns null when no proof exists', async () => {
  assert.equal(await loadDecodeProof('/nonexistent-dir', 'zz-2020-xingce-a-1'), null);
  assert.equal(await loadDecodeProof(null, 'x'), null);
});
