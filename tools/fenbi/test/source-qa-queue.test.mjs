import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { classifyReceipt, evaluateReceipts, runQueue, canonicalPayload } from '../src/source-qa-queue.mjs';

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

async function setup () {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const reviewer = signer('reviewer-a', 'reviewer');
  const approver = signer('approver-b', 'approver');
  return {root, t, reviewer, approver, registry: [reviewer, approver].map(s => ({id: s.id, role: s.role, publicKeyJwk: s.publicKeyJwk}))};
}

test('1 signed current snapshot reaches READY, never promoted', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[0].primaryStatus, 'READY_FOR_PRIVATE_REVIEW', JSON.stringify(r.rows[0].allReasons));
  assert.equal(r.summary.promoted, 0);
  assert.equal(r.summary.fieldwiseQaPass, 1);
});

test('2 source stub blocks even with valid signatures', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, stub: true, answer: 'missing', explanation: 'missing'}, {number: 2, match: 'same', answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_SOURCE_STUB');
});

test('3 same question with different content is an answer conflict', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, answer: 'conflict', explanation: 'verified'}, {number: 2, answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_ANSWER_CONFLICT');
});

test('4 answer present without question is refused', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, answer: 'present-without-question', explanation: 'verified'}, {number: 2, answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_ANSWER_CONFLICT');
});

test('5 missing textual explanation blocks', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {questions: [{number: 1, answer: 'verified', explanation: 'missing'}, {number: 2, answer: 'verified', explanation: 'verified'}]})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_EXPLANATION');
});

test('6 unknown image sha is UNMAPPED', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {images: [{path: 'assets/图1.png', sha256: 'unknown'}]})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[0].primaryStatus, 'UNMAPPED');
});

test('7 stale revision and missing previous are STALE_REVISION', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const oldRev = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {receiptRevision: 'rev-0'})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(oldRev.rows[0].primaryStatus, 'STALE_REVISION');

  const noPrev = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: new Map(), trustRegistry: registry});
  assert.equal(noPrev.rows[0].primaryStatus, 'STALE_REVISION');
  assert.ok(noPrev.rows[0].allReasons.includes('previous-missing'));
});

test('8 self-approval and same signer are refused', async () => {
  const {t, reviewer, reviewer: _r, registry} = await setup();
  const same = signer('reviewer-a', 'approver');
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, same, {}, {}, {approvedBy: reviewer.id})], trustedRoot: t.root, previous: prev(), trustRegistry: [...registry, {id: same.id, role: 'approver', publicKeyJwk: same.publicKeyJwk}].slice(0, 1).concat([{id: same.id, role: 'approver', publicKeyJwk: same.publicKeyJwk}])});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('self-approval'));
});

test('9 unknown / forbidden rights and self-declared approvals fail closed', async () => {
  const {t, reviewer, approver, registry} = await setup();
  for (const rights of [
    {basis: 'unknown', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: true},
    {basis: 'user-self-authorization', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: true},
    {basis: 'copyright-holder-license', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: false}
  ]) {
    const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {rights})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
    assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  }
  const unsigned = makeReceipt(t, reviewer, approver);
  delete unsigned.qa.attestation;
  delete unsigned.approval.attestation;
  const u = await evaluateReceipts({receipts: [unsigned], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(u.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(u.rows[0].allReasons.includes('qa-attestation-missing'));
  assert.ok(u.rows[0].allReasons.includes('approval-attestation-missing'));
});

test('10 forged evidence sha fails closed', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const rights = {basis: 'copyright-holder-license', evidenceSha256: H('f'), evidencePath: 'license.txt', holder: 'x', redistributable: true};
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver, {rights})], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('evidence-sha-mismatch'));
});

test('11 duplicate sourceId and malformed envelope are UNMAPPED', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver), makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(r.rows[1].primaryStatus, 'UNMAPPED');
  assert.ok(r.rows[1].allReasons.includes('duplicate-source-id'));
  assert.equal(classifyReceipt({paper: {}}).primaryStatus, 'UNMAPPED');
});

test('12 no trust registry means nothing is READY', async () => {
  const {t, reviewer, approver} = await setup();
  const r = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: prev(), trustRegistry: null});
  assert.equal(r.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(r.rows[0].allReasons.includes('qa-trust-registry-missing'));
});

test('13 changed revision is queued, unchanged is not re-queued', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const same = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: new Map([['8472470', null], ['8472470:revision', 'rev-1']]), trustRegistry: registry});
  assert.equal(same.summary.sourceChecked, 1);
  assert.equal(same.summary.sourceChanged, 0);
  const changed = await evaluateReceipts({receipts: [makeReceipt(t, reviewer, approver)], trustedRoot: t.root, previous: new Map([['8472470', null], ['8472470:revision', 'rev-0']]), trustRegistry: registry});
  assert.equal(changed.rows[0].primaryStatus, 'STALE_REVISION');
  assert.equal(changed.summary.sourceChanged, 1);
});

test('14 stub plus illegal rights reports both reasons', async () => {
  const {t, reviewer, approver, registry} = await setup();
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
  const {t, reviewer, approver, registry} = await setup();
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
  const {t, reviewer, approver, registry} = await setup();
  const rogue = signer('rogue', 'reviewer');
  const r = makeReceipt(t, reviewer, approver, {}, {reviewer: 'alice'});
  r.qa.attestation = {signer: rogue.id, signature: rogue.sign({sourceId: r.paper.sourceId, sourceDocSha: r.paper.sourceDocSha, targetPaperSha: r.paper.targetPaperSha, prHeadSha: r.paper.prHeadSha, sourceRevision: r.paper.sourceRevision, kind: 'source-qa-review', reportSha256: r.qa.reportSha256, reviewer: 'alice'})};
  const res = await evaluateReceipts({receipts: [r], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(res.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(res.rows[0].allReasons.some(x => x.startsWith('qa-signer-not-trusted')));
});

test('17 stale signature over an old snapshot is rejected', async () => {
  const {t, reviewer, approver, registry} = await setup();
  const r = makeReceipt(t, reviewer, approver);
  const old = {sourceId: r.paper.sourceId, sourceDocSha: r.paper.sourceDocSha, targetPaperSha: H('9'), prHeadSha: r.paper.prHeadSha, sourceRevision: r.paper.sourceRevision, kind: 'source-qa-review', reportSha256: r.qa.reportSha256, reviewer: r.qa.reviewer};
  r.qa.attestation = {signer: reviewer.id, signature: reviewer.sign(old)};
  const res = await evaluateReceipts({receipts: [r], trustedRoot: t.root, previous: prev(), trustRegistry: registry});
  assert.equal(res.rows[0].primaryStatus, 'BLOCKED_RIGHTS');
  assert.ok(res.rows[0].allReasons.includes('qa-signature-invalid'));
});

test('18 CLI dry-run reads JSONL with trust registry and writes nothing', async () => {
  const {root, t, reviewer, approver, registry} = await setup();
  const file = path.join(root, 'receipts.jsonl');
  const prevFile = path.join(root, 'previous.json');
  const regFile = path.join(root, 'registry.json');
  await fs.writeFile(file, JSON.stringify(makeReceipt(t, reviewer, approver)) + '\n');
  await fs.writeFile(prevFile, JSON.stringify({[`8472470`]: {qaSha: null, revision: 'rev-1'}}));
  await fs.writeFile(regFile, JSON.stringify(registry));
  const result = await runQueue(['--receipts', file, '--trusted-root', t.root, '--previous', prevFile, '--trust-registry', regFile, '--dry-run']);
  assert.equal(result.ok, true);
  assert.equal(result.summary.receipts, 1);
  assert.equal(result.summary.promoted, 0);
  assert.equal(result.rows[0].primaryStatus, 'READY_FOR_PRIVATE_REVIEW', JSON.stringify(result.rows[0].allReasons));
});
