import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { classifyReceipt, evaluateReceipts, runQueue, canonicalPayload, registryPayload } from '../src/source-qa-queue.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const H = ch => ch.repeat(64);

function signer (id, role) {
  const {publicKey, privateKey} = crypto.generateKeyPairSync('ed25519');
  return {id, role, publicKeyJwk: publicKey.export({format: 'jwk'}),
    sign: payload => crypto.sign(null, Buffer.from(canonicalPayload(payload)), privateKey).toString('base64')};
}

async function trusted (root) {
  const dir = path.join(root, 'trusted');
  await fs.mkdir(dir, {recursive: true});
  const files = {qa: Buffer.from('synthetic qa report'), license: Buffer.from('synthetic license'), approval: Buffer.from('synthetic approval')};
  for (const [name, buf] of Object.entries(files)) await fs.writeFile(path.join(dir, name + '.txt'), buf);
  return {root: dir, qaS: sha(files.qa), licS: sha(files.license), appS: sha(files.approval)};
}

function makeReceipt (t, reviewer, approver, overrides = {}, qaOverride = {}, approvalOverride = {}) {
  const paper = {
    sourceId: '8472470', sourceDocSha: H('1'), targetPaperSha: H('2'), prHeadSha: 'a'.repeat(40), sourceRevision: 'rev-1',
    declaredQuestions: 2,
    identity: {area: '上海', year: 2026, subject: 'xingce', variant: 'A'}
  };
  const base = {sourceId: paper.sourceId, sourceDocSha: paper.sourceDocSha, targetPaperSha: paper.targetPaperSha, prHeadSha: paper.prHeadSha, sourceRevision: paper.sourceRevision};
  const qa = {verdict: 'pass', reportSha256: t.qaS, reportPath: 'qa.txt', reviewer: reviewer.id, ...qaOverride};
  const approval = {approvedBy: approver.id, approvalSha256: t.appS, approvalPath: 'approval.txt', ...approvalOverride};
  qa.attestation = {signer: qa.reviewer, signature: reviewer.sign({...base, kind: 'source-qa-review', reportSha256: qa.reportSha256, reviewer: qa.reviewer})};
  approval.attestation = {signer: approval.approvedBy, signature: approver.sign({...base, kind: 'rights-approval', approvalSha256: approval.approvalSha256, approvedBy: approval.approvedBy})};
  return {
    paper, receiptRevision: 'rev-1', receiptTargetPaperSha: paper.targetPaperSha, receiptPrHeadSha: paper.prHeadSha,
    questions: [
      {number: 1, match: 'same', stub: false, answer: 'verified', explanation: 'verified'},
      {number: 2, match: 'same', stub: false, answer: 'verified', explanation: 'verified'}
    ],
    mapping: {detailsByNumber: 'verified', materialsByRange: 'verified'},
    images: [{path: 'assets/图1.png', sha256: H('3')}],
    qa,
    rights: {basis: 'copyright-holder-license', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'synthetic holder', redistributable: true},
    approval,
    ...overrides
  };
}

const prev = () => new Map([['8472470', null], ['8472470:revision', 'rev-1']]);

function makeEnvelope (rootKey, entries, overrides = {}) {
  const registry = {
    scope: 'source-qa', version: 1, issuedAt: '2026-10-20T00:00:00Z',
    expiresAt: '2027-10-20T00:00:00Z', entries, ...overrides
  };
  return {registry, signature: {signerRootId: 'root-1', signature: rootKey.sign(registryPayload(registry))}};
}

async function setup () {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const reviewer = signer('reviewer-a', 'reviewer');
  const approver = signer('approver-b', 'approver');
  const rootKey = signer('root-1', 'root');
  const entries = [reviewer, approver].map(s => ({id: s.id, role: s.role, publicKeyJwk: s.publicKeyJwk}));
  const envelope = makeEnvelope(rootKey, entries);
  return {root, t, reviewer, approver, rootKey, entries, envelope, pinned: rootKey.publicKeyJwk, registry: entries};
}

test('1 signed current snapshot reaches READY, never promoted', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'READY_FOR_PRIVATE_REVIEW', JSON.stringify(r.rows[0].allReasons));
  assert.equal(r.summary.promoted, 0);
  assert.equal(r.summary.fieldwiseQaPass, 1);
});

test('2 source stub blocks even with valid signatures', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, stub: true, answer: 'missing', explanation: 'missing'}, {number: 2, match: 'same', answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_SOURCE_STUB');
});

test('3 same question with different content is an answer conflict', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, answer: 'conflict', explanation: 'verified'}, {number: 2, answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_ANSWER_CONFLICT');
});

test('4 answer present without question is refused', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, answer: 'present-without-question', explanation: 'verified'}, {number: 2, answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_ANSWER_CONFLICT');
});

test('5 missing textual explanation blocks', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, answer: 'verified', explanation: 'missing'}, {number: 2, answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_EXPLANATION');
});

test('6 unknown image sha is UNMAPPED', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {images: [{path: 'assets/图1.png', sha256: 'unknown'}]})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'UNMAPPED');
});

test('7 stale revision and missing previous are STALE_REVISION', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const oldRev = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {receiptRevision: 'rev-0'})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(oldRev.rows[0].primaryStatus, 'STALE_REVISION');

  const noPrev = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: new Map(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(noPrev.rows[0].primaryStatus, 'STALE_REVISION');
  assert.ok(noPrev.rows[0].allReasons.includes('previous-missing'));
});

test('8 self-approval and same signer are refused', async () => {
  const {t, reviewer, rootKey} = await setup();
  const same = signer('reviewer-a', 'approver');
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, same, {}, {}, {approvedBy: reviewer.id})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: makeEnvelope(rootKey, [{id: reviewer.id, role: 'reviewer', publicKeyJwk: reviewer.publicKeyJwk}, {id: same.id, role: 'approver', publicKeyJwk: same.publicKeyJwk}]), pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('self-approval'));
});

test('9 unknown / forbidden rights and self-declared approvals fail closed', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  for (const rights of [
    {basis: 'unknown', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: true},
    {basis: 'user-self-authorization', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: true},
    {basis: 'copyright-holder-license', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: false}
  ]) {
    const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {rights})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
    assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  }
  const unsigned = makeReceipt(t, reviewer, approver);
  delete unsigned.qa.attestation;
  delete unsigned.approval.attestation;
  const u = await evaluateReceipts({receipts: [unsigned], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(u.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(u.rows[0].allReasons.includes('qa-attestation-missing'));
  assert.ok(u.rows[0].allReasons.includes('approval-attestation-missing'));
});

test('10 forged evidence sha fails closed', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const rights = {basis: 'copyright-holder-license', evidenceSha256: H('f'), evidencePath: 'license.txt', holder: 'x', redistributable: true};
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {rights})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('evidence-sha-mismatch'));
});

test('11 duplicate sourceId and malformed envelope are UNMAPPED', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver), makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(r.rows[1].primaryStatus, 'UNMAPPED');
  assert.ok(r.rows[1].allReasons.includes('duplicate-source-id'));
  assert.equal(classifyReceipt({paper: {}}).primaryStatus, 'UNMAPPED');
});

test('12 no trust registry means nothing is READY', async () => {
  const {t, reviewer, approver} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: null, pinnedRootPublicKeyJwk: null});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('trust-pinned-root-missing'));
});

test('13 changed revision is queued, unchanged is not re-queued', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const same = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: new Map([['8472470', null], ['8472470:revision', 'rev-1']]), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(same.summary.sourceChecked, 1);
  assert.equal(same.summary.sourceChanged, 0);
  const changed = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: new Map([['8472470', null], ['8472470:revision', 'rev-0']]), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(changed.rows[0].primaryStatus, 'STALE_REVISION');
  assert.equal(changed.summary.sourceChanged, 1);
});

test('14 stub plus illegal rights reports both reasons', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({
    receipts: [makeReceipt(t, reviewer, approver, {
      questions: [{number: 1, stub: true, answer: 'missing', explanation: 'missing'}, {number: 2, stub: true, answer: 'missing', explanation: 'missing'}],
      rights: {basis: 'user-self-authorization', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: false}
    })], trustedRoot: t.root, previous: prev(), trustRegistry: registry
  });
  assert.ok(r.rows[0].states.includes('BLOCKED_SOURCE_STUB'));
  assert.ok(r.rows[0].states.includes('BLOCKED_RIGHTS'));
  assert.ok(r.rows[0].allReasons.includes('rights-basis-forbidden'));
  assert.ok(r.rows[0].allReasons.some(x => x.startsWith('source-stub')));
});

test('15 answer conflict plus missing explanation reports both', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({
    receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, answer: 'conflict', explanation: 'missing'}, {number: 2, answer: 'verified', explanation: 'missing'}]})],
    trustedRoot: t.root, previous: prev(), trustRegistry: registry
  });
  assert.ok(r.rows[0].states.includes('BLOCKED_ANSWER_CONFLICT'));
  assert.ok(r.rows[0].states.includes('BLOCKED_EXPLANATION'));
  assert.ok(r.rows[0].allReasons.some(x => x.startsWith('answer-conflict')));
  assert.ok(r.rows[0].allReasons.some(x => x.startsWith('explanation-missing')));
});

test('16 signature by an untrusted identity is not accepted', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const rogue = signer('rogue', 'reviewer');
  const r = makeReceipt(t, reviewer, approver, {}, {reviewer: 'alice'});
  r.qa.attestation = {signer: rogue.id, signature: rogue.sign({sourceId: r.paper.sourceId, sourceDocSha: r.paper.sourceDocSha, targetPaperSha: r.paper.targetPaperSha, prHeadSha: r.paper.prHeadSha, sourceRevision: r.paper.sourceRevision, kind: 'source-qa-review', reportSha256: r.qa.reportSha256, reviewer: 'alice'})};
  const res = await evaluateReceipts({receipts: [r], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(res.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(res.rows[0].allReasons.some(x => x.startsWith('qa-signer-not-trusted')));
});

test('17 stale signature over an old snapshot is rejected', async () => {
  const {t, reviewer, approver, registry, envelope, rootKey} = await setup();
  const r = makeReceipt(t, reviewer, approver);
  const old = {sourceId: r.paper.sourceId, sourceDocSha: r.paper.sourceDocSha, targetPaperSha: H('9'), prHeadSha: r.paper.prHeadSha, sourceRevision: r.paper.sourceRevision, kind: 'source-qa-review', reportSha256: r.qa.reportSha256, reviewer: r.qa.reviewer};
  r.qa.attestation = {signer: reviewer.id, signature: reviewer.sign(old)};
  const res = await evaluateReceipts({receipts: [r], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: Date.parse('2026-10-21T00:00:00Z')});
  assert.equal(res.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(res.rows[0].allReasons.includes('qa-signature-invalid'));
});

test('18 CLI dry-run reads JSONL with trust registry and writes nothing', async () => {
  const {root, t, reviewer, approver, envelope, rootKey} = await setup();
  const file = path.join(root, 'receipts.jsonl');
  const prevFile = path.join(root, 'previous.json');
  const regFile = path.join(root, 'registry.json');
  const rootFile = path.join(root, 'pinned-root.json');
  await fs.writeFile(file, JSON.stringify(makeReceipt(t, reviewer, approver)) + '\n');
  await fs.writeFile(prevFile, JSON.stringify({[`8472470`]: {qaSha: null, revision: 'rev-1'}}));
  await fs.writeFile(regFile, JSON.stringify(envelope));
  await fs.writeFile(rootFile, JSON.stringify(rootKey.publicKeyJwk));
  const result = await runQueue(['--receipts', file, '--trusted-root', t.root, '--previous', prevFile, '--trust-registry', regFile, '--pinned-root', rootFile, '--expected-registry-version', '1', '--dry-run']);
  assert.equal(result.ok, true);
  assert.equal(result.summary.receipts, 1);
  assert.equal(result.summary.promoted, 0);
  assert.equal(result.rows[0].primaryStatus, 'READY_FOR_PRIVATE_REVIEW', JSON.stringify(result.rows[0].allReasons));
});

const NOW = Date.parse('2026-10-21T00:00:00Z');

test('19 caller-made registry with two self-signed roles and no pinned root is BLOCKED', async () => {
  const {t, reviewer, approver, rootKey} = await setup();
  const forged = makeEnvelope(rootKey, [
    {id: reviewer.id, role: 'reviewer', publicKeyJwk: reviewer.publicKeyJwk},
    {id: approver.id, role: 'approver', publicKeyJwk: approver.publicKeyJwk}
  ]);
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: forged, pinnedRootPublicKeyJwk: null, now: NOW});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.equal(r.summary.licensed, 0);
  assert.ok(r.rows[0].allReasons.includes('trust-pinned-root-missing'));
});

test('20 a self-claimed registrySha/version cannot substitute for the pinned root', async () => {
  const {t, reviewer, approver, rootKey} = await setup();
  const forged = makeEnvelope(rootKey, [
    {id: reviewer.id, role: 'reviewer', publicKeyJwk: reviewer.publicKeyJwk},
    {id: approver.id, role: 'approver', publicKeyJwk: approver.publicKeyJwk}
  ]);
  forged.registrySha256 = H('e');
  forged.registry.version = 1;
  const noRoot = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: forged, pinnedRootPublicKeyJwk: null, now: NOW});
  assert.equal(noRoot.rows[0].primaryStatus, 'BLOCKED_RIGHTS');

  const wrongRoot = signer('root-2', 'root');
  const swapped = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: forged, pinnedRootPublicKeyJwk: wrongRoot.publicKeyJwk, now: NOW});
  assert.equal(swapped.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(swapped.rows[0].allReasons.includes('trust-registry-signature-invalid'));
});

test('21 a genuine in-memory root signing two independent roles reaches READY only', async () => {
  const {t, reviewer, approver, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, expectedRegistryVersion: 1, now: NOW});
  assert.equal(r.rows[0].primaryStatus, 'READY_FOR_PRIVATE_REVIEW', JSON.stringify(r.rows[0].allReasons));
  assert.equal(r.rows[0].readyForPrivateReview, true);
  assert.equal(r.rows[0].independentlyReviewed, true);
  assert.equal(r.rows[0].licensed, false);
  assert.equal(r.rows[0].rightsInstrumentVerified, false);
  assert.equal(r.summary.licensed, 0);
  assert.equal(r.summary.promoted, 0);
  assert.equal(r.trust.usable, true);
});

test('22 registry signed by a non-root role key is rejected', async () => {
  const {t, reviewer, approver, rootKey} = await setup();
  const wrongSigner = makeEnvelope(reviewer, [
    {id: reviewer.id, role: 'reviewer', publicKeyJwk: reviewer.publicKeyJwk},
    {id: approver.id, role: 'approver', publicKeyJwk: approver.publicKeyJwk}
  ]);
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: wrongSigner, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: NOW});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('trust-registry-signature-invalid'));
});

test('23 expired registry is rejected', async () => {
  const {t, reviewer, approver, rootKey, entries} = await setup();
  const expired = makeEnvelope(rootKey, entries, {expiresAt: '2026-10-20T00:00:00Z'});
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: expired, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: NOW});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('trust-registry-expired'));
});

test('24 signature replayed from an older revision is rejected', async () => {
  const {t, reviewer, approver, envelope, rootKey} = await setup();
  const r = makeReceipt(t, reviewer, approver);
  const old = {sourceId: r.paper.sourceId, sourceDocSha: r.paper.sourceDocSha, targetPaperSha: r.paper.targetPaperSha, prHeadSha: r.paper.prHeadSha, sourceRevision: 'rev-0', kind: 'source-qa-review', reportSha256: r.qa.reportSha256, reviewer: r.qa.reviewer};
  r.qa.attestation = {signer: reviewer.id, signature: reviewer.sign(old)};
  const res = await evaluateReceipts({receipts: [r], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: NOW});
  assert.equal(res.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(res.rows[0].allReasons.includes('qa-signature-invalid'));
});

test('25 the same registered identity cannot review and approve', async () => {
  const {t, reviewer, rootKey} = await setup();
  const dual = signer('reviewer-a', 'approver');
  const entries = [
    {id: reviewer.id, role: 'reviewer', publicKeyJwk: reviewer.publicKeyJwk},
    {id: dual.id, role: 'approver', publicKeyJwk: dual.publicKeyJwk}
  ];
  const envelope = makeEnvelope(rootKey, entries);
  const res = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, dual, {}, {}, {approvedBy: reviewer.id})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: NOW});
  assert.equal(res.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(res.rows[0].allReasons.includes('same-signer-for-review-and-approval'));
});

test('26 independently signed QA is a review signal, never a license', async () => {
  const {t, reviewer, approver, envelope, rootKey} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: NOW});
  assert.equal(r.rows[0].primaryStatus, 'READY_FOR_PRIVATE_REVIEW');
  assert.equal(r.rows[0].rightsClaimReviewed, true);
  assert.equal(r.rows[0].rightsInstrumentVerified, false);
  assert.equal(r.rows[0].licensed, false);
  assert.equal(r.summary.licensed, 0);
  assert.equal(r.summary.rightsInstrumentVerified, 0);
  assert.equal(r.summary.promoted, 0);
  assert.match(r.summary.rightsNote, /licensed is always 0/u);
});

test('27 self-claimed rights fields cannot flip licensed, even when signed', async () => {
  const {t, reviewer, approver, envelope, rootKey} = await setup();
  const claimed = {basis: 'copyright-holder-license', evidenceSha256: H('9'), evidencePath: 'license.txt', holder: 'self-claimed', redistributable: true};
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {rights: claimed})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: NOW});
  assert.equal(r.rows[0].licensed, false);
  assert.equal(r.rows[0].rightsInstrumentVerified, false);
  assert.equal(r.summary.licensed, 0);
  // Forged evidence sha fails closed entirely.
  const forged = {...claimed, evidenceSha256: H('f')};
  const bad = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {rights: forged})], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: rootKey.publicKeyJwk, now: NOW});
  assert.equal(bad.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.equal(bad.summary.licensed, 0);
});

test('28 without a pinned root every metric stays zero', async () => {
  const {t, reviewer, approver, envelope} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistryEnvelope: envelope, pinnedRootPublicKeyJwk: null, now: NOW});
  assert.equal(r.summary.independentlyReviewed, 0);
  assert.equal(r.summary.readyForPrivateReview, 0);
  assert.equal(r.summary.rightsClaimReviewed, 0);
  assert.equal(r.summary.rightsInstrumentVerified, 0);
  assert.equal(r.summary.licensed, 0);
  assert.equal(r.summary.promoted, 0);
});
