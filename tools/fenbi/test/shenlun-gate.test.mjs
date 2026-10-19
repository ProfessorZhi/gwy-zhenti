import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {
  DEFAULT_RIGHTS, SHENLUN, assessShenlunAssets, assessShenlunStructure,
  cloudStorageAllowed, defaultShenlunMetadata, isShenlun, shenlunReceiptFields,
  shenlunStructuralGrade,
} from '../src/shenlun-gate.mjs';

/**
 * Shenlun dispatch and the cloud-storage block. Synthetic structural metadata only — no captured
 * question text, materials, answers, explanations or images appear in these fixtures.
 */

const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae426082', 'hex');

function tmpdir(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'shenlun-gate-'));
  t.after?.(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

/** One paper shaped like the S1 sample: 3 materials (2 with bodies, 1 empty), 2 subjective questions. */
function source(over = {}) {
  return {
    identity: { subject: 'shenlun', area: '浙江', year: 2020, variant: 'a', sourceId: '5254748', paperId: '5254748' },
    materials: [
      { id: 'm1', state: 'observed' },
      { id: 'm2', state: 'observed' },
      { id: 'm3', state: 'absent' },      // source declares this material body empty
    ],
    questions: [
      { id: 'q1', number: 1, state: 'observed', requirements: { state: 'observed' }, wordLimit: { state: 'observed' } },
      { id: 'q2', number: 2, state: 'observed', requirements: { state: 'observed' }, wordLimit: { state: 'observed' } },
    ],
    referenceAnswers: [
      { questionId: 'q1', state: 'observed', images: [{ ref: 'a.png', sha256: sha(PNG) }] },
      { questionId: 'q2', state: 'observed', images: [{ ref: 'b.png', sha256: sha(PNG) }] },
    ],
    explanations: [],                       // source publishes none: absent, not unknown-forever
    ...over,
  };
}

function assetsDir(t, names = ['a.png', 'b.png']) {
  const dir = tmpdir(t);
  for (const n of names) fs.writeFileSync(path.join(dir, n), PNG);
  return dir;
}

// 1. dispatch: xingce is not shenlun and keeps its own path
test('subject dispatch keeps xingce out of the shenlun gate', () => {
  assert.equal(isShenlun({ subject: 'xingce' }), false);
  assert.equal(isShenlun({ subject: 'shenlun' }), true);
  assert.equal(isShenlun({ subject: '未知' }), false);
  assert.equal(cloudStorageAllowed({ subject: 'xingce' }).allowed, true);
});

// 2. shenlun dispatch produces a structure assessment
test('a shenlun paper is assessed and reports coverage', t => {
  const a = assessShenlunStructure(source(), { assetRoot: assetsDir(t) });
  assert.equal(a.ok, true);
  assert.equal(a.coverage.materials.observed, 2);
  assert.equal(a.coverage.materials.absent, 1);
  assert.equal(a.coverage.complete, true);
});

// 3. unknown subject is rejected
test('an unknown subject is rejected rather than guessed', () => {
  const a = assessShenlunStructure(source({ identity: { subject: '未知', area: '浙江', year: 2020, variant: 'a', sourceId: '1' } }));
  assert.equal(a.ok, false);
  assert.equal(a.code, 'not-shenlun');
});

// 4. three materials, one legitimately empty, are accepted; an unmarked empty is not
test('an explicitly empty material is accepted, an unexplained one is unknown', t => {
  const ok = assessShenlunStructure(source(), { assetRoot: assetsDir(t) });
  assert.equal(ok.coverage.complete, true);
  const bad = assessShenlunStructure(source({ materials: [
    { id: 'm1', state: 'observed' }, { id: 'm2', state: 'observed' }, { id: 'm3' } ] }), { assetRoot: assetsDir(t) });
  assert.equal(bad.coverage.materials.unknown, 1);
  assert.equal(bad.coverage.complete, false);
  assert.equal(shenlunStructuralGrade(bad, {}).structuralGrade, 'C');
});

// 5. shenlun questions carry no options and none are required
test('shenlun questions have no options and the gate does not demand them', t => {
  const a = assessShenlunStructure(source(), { assetRoot: assetsDir(t) });
  assert.equal(a.ok, true);
  assert.equal(a.identity.subject, SHENLUN);
  assert.equal('options' in (a.questions?.[0] ?? {}), false);
  assert.equal(shenlunStructuralGrade(a, defaultShenlunMetadata()).structuralGrade, 'A');
});

// 6. reference-answer image SHA: complete / missing / wrong
test('reference answer images must exist and hash to their declared value', t => {
  const dir = assetsDir(t, ['a.png']);            // b.png deliberately absent
  const missing = assessShenlunStructure(source(), { assetRoot: dir });
  assert.equal(missing.assets.ok, false);
  assert.ok(missing.assets.problems.some(p => p.code === 'asset-missing'));

  const bad = tmpdir(t);
  fs.writeFileSync(path.join(bad, 'a.png'), PNG);
  fs.writeFileSync(path.join(bad, 'b.png'), Buffer.from('not the image'));
  const mismatch = assessShenlunStructure(source(), { assetRoot: bad });
  assert.ok(mismatch.assets.problems.some(p => p.code === 'asset-sha-mismatch'));

  const good = assessShenlunStructure(source(), { assetRoot: assetsDir(t) });
  assert.equal(good.assets.ok, true);
});

test('an asset path may not escape the asset root', () => {
  const r = assessShenlunAssets([{ ref: '../secret.png', sha256: sha(PNG) }], '/tmp/shenlun-root');
  assert.equal(r.ok, false);
  assert.equal(r.problems[0].code, 'asset-ref-invalid');
});

test('a malformed asset digest is rejected', () => {
  const r = assessShenlunAssets([{ ref: 'a.png', sha256: 'not-a-digest' }], '/tmp');
  assert.equal(r.problems[0].code, 'asset-sha-malformed');
});

// 7. sourceId / paperId mismatch
test('a paperId that disagrees with sourceId is rejected', () => {
  const a = assessShenlunStructure(source({
    identity: { subject: 'shenlun', area: '浙江', year: 2020, variant: 'a', sourceId: '5254748', paperId: '9999999' } }));
  assert.equal(a.ok, false);
  assert.equal(a.code, 'paperId-sourceId-mismatch');
});

// 8. sourceSha / documentSha mismatch
test('evidence pinned to another capture is rejected', t => {
  const s = source();
  const pinned = { sourceSha256: 'deadbeef'.repeat(8), documentSha256: 'cafebabe'.repeat(8) };
  assert.equal(assessShenlunStructure(s, { assetRoot: assetsDir(t), expected: { ...pinned, sourceSha256: 'x' } }).code,
    'sourceSha256-mismatch');
  assert.equal(assessShenlunStructure(s, { assetRoot: assetsDir(t), expected: { documentSha256: 'y' } }).code,
    'documentSha256-mismatch');
});

// 9. rights unverified blocks publication even when structure is A
test('unverified rights block publication of a structurally fine paper', t => {
  const a = assessShenlunStructure(source(), { assetRoot: assetsDir(t) });
  const graded = shenlunStructuralGrade(a, defaultShenlunMetadata());
  assert.equal(graded.structuralGrade, 'A');
  assert.equal(graded.publishable, false);
  assert.equal(graded.grade, 'C');
  assert.equal(graded.holdReason, 'shenlun-cloud-storage-blocked');
});

test('clearing the block without rights evidence still blocks', () => {
  const meta = defaultShenlunMetadata({ cloudStorageBlocked: false });
  assert.equal(cloudStorageAllowed(meta).reason, 'shenlun-rights-unverified');
  const meta2 = defaultShenlunMetadata({ cloudStorageBlocked: false, rightsStatus: 'cleared' });
  assert.equal(cloudStorageAllowed(meta2).reason, 'shenlun-rights-evidence-missing');
});

test('an explicit paper-specific clearance allows a dry run but is still metadata only', t => {
  const a = assessShenlunStructure(source(), { assetRoot: assetsDir(t) });
  const meta = defaultShenlunMetadata({ cloudStorageBlocked: false, rightsStatus: 'cleared',
    rightsEvidence: 'synthetic clearance record for tests' });
  const graded = shenlunStructuralGrade(a, meta);
  assert.equal(graded.publishable, true);
  const fields = shenlunReceiptFields(a, meta);
  assert.equal(fields.grade, 'A');
  assert.equal(fields.cloudStorageBlocked, false);
  // The receipt carries coverage metadata only — no text fields exist at all.
  assert.equal('contentHtml' in fields, false);
  assert.equal('answerHtml' in fields, false);
});

// 10. a source stub stays C
test('a source stub remains C and is never lifted by explanationsRequired=false', t => {
  const a = assessShenlunStructure(source({
    questions: [{ id: 'q1', number: 1, state: 'unknown' }, { id: 'q2', number: 2, state: 'observed' }] }),
    { assetRoot: assetsDir(t) });
  const graded = shenlunStructuralGrade(a, defaultShenlunMetadata({ cloudStorageBlocked: false, rightsStatus: 'cleared',
    rightsEvidence: 'synthetic clearance record for tests' }));
  assert.equal(graded.structuralGrade, 'C');
  assert.ok(graded.blockers.includes('shenlun-coverage-incomplete'));
  assert.equal(graded.publishable, false);
  assert.equal(a.coverage.explanationsRequired, false, 'false here only means explanations are optional');
});

// 11. repeated assessment is idempotent
test('assessing the same metadata twice yields the identical result', t => {
  const dir = assetsDir(t);
  const once = assessShenlunStructure(source(), { assetRoot: dir });
  const twice = assessShenlunStructure(source(), { assetRoot: dir });
  assert.deepEqual(twice, once);
  assert.deepEqual(shenlunStructuralGrade(twice, defaultShenlunMetadata()),
    shenlunStructuralGrade(once, defaultShenlunMetadata()));
});

// 12. an old repository shenlun markdown is not a fenbi source
test('legacy repository markdown cannot stand in for a captured source', () => {
  // The gate requires a sourceId and a capture identity; a markdown file has neither.
  const legacy = { path: '省考/浙江/2020/申论-A类.md', identity: { subject: 'shenlun', area: '浙江', year: 2020, variant: 'A类' } };
  const a = assessShenlunStructure({ identity: legacy.identity });
  assert.equal(a.ok, false);
  assert.equal(a.code, 'identity-sourceId-unknown');
});

test('default metadata is unverified and cloud blocked', () => {
  const meta = defaultShenlunMetadata();
  assert.equal(meta.rightsStatus, DEFAULT_RIGHTS.rightsStatus);
  assert.equal(meta.cloudStorageBlocked, true);
  assert.equal(cloudStorageAllowed(meta).allowed, false);
});
