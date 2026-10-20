import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { classifyReceipt, evaluateReceipts, runQueue } from '../src/source-qa-queue.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const H = ch => ch.repeat(64);

async function trusted (root) {
  const dir = path.join(root, 'trusted');
  await fs.mkdir(dir, {recursive: true});
  const files = {qa: Buffer.from('synthetic qa report'), license: Buffer.from('synthetic license'), approval: Buffer.from('synthetic approval')};
  for (const [name, buf] of Object.entries(files)) await fs.writeFile(path.join(dir, name + '.txt'), buf);
  return {root: dir, qaS: sha(files.qa), licS: sha(files.license), appS: sha(files.approval)};
}

function receipt (t, overrides = {}) {
  return {
    paper: {
      sourceId: '8472470',
      sourceDocSha: H('1'), targetPaperSha: H('2'), prHeadSha: 'a'.repeat(40), sourceRevision: 'rev-1',
      declaredQuestions: 2,
      identity: {area: '上海', year: 2026, subject: 'xingce', variant: 'A'}
    },
    qaBaseReceiptSha: null,
    receiptRevision: 'rev-1',
    targetPaperSha: H('2'),
    questions: [
      {number: 1, match: 'same', stub: false, answer: 'verified', explanation: 'verified'},
      {number: 2, match: 'same', stub: false, answer: 'verified', explanation: 'verified'}
    ],
    mapping: {detailsByNumber: 'verified', materialsByRange: 'verified'},
    images: [{path: 'assets/图1.png', sha256: H('3')}],
    qa: {verdict: 'pass', reportSha256: t.qaS, reportPath: 'qa.txt', reviewer: 'reviewer-a'},
    rights: {basis: 'copyright-holder-license', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'synthetic holder', redistributable: true},
    approval: {approvedBy: 'approver-b', approvalSha256: t.appS, approvalPath: 'approval.txt'},
    ...overrides
  };
}

test('1 complete metadata reaches READY_FOR_PRIVATE_REVIEW, never promoted', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = await evaluateReceipts({receipts: [receipt(t)], trustedRoot: t.root});
  assert.equal(r.rows[0].state, 'READY_FOR_PRIVATE_REVIEW');
  assert.equal(r.summary.promoted, 0);
  assert.equal(r.summary.fieldwiseQaPass, 1);
});

test('2 source stub blocks before anything else', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = receipt(t, {questions: [{number: 1, stub: true, answer: 'missing', explanation: 'missing'}, {number: 2, match: 'same', answer: 'verified', explanation: 'verified'}]});
  assert.equal((await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0].state, 'BLOCKED_SOURCE_STUB');
});

test('3 same question with different content is an answer conflict', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = receipt(t, {questions: [{number: 1, match: 'same', answer: 'conflict', explanation: 'verified'}, {number: 2, match: 'same', answer: 'verified', explanation: 'verified'}]});
  assert.equal((await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0].state, 'BLOCKED_ANSWER_CONFLICT');
});

test('4 answer present without a question is refused', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = receipt(t, {questions: [{number: 1, match: 'same', answer: 'present-without-question', explanation: 'verified'}, {number: 2, match: 'same', answer: 'verified', explanation: 'verified'}]});
  assert.equal((await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0].state, 'BLOCKED_ANSWER_CONFLICT');
});

test('5 missing textual explanation blocks', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = receipt(t, {questions: [{number: 1, match: 'same', answer: 'verified', explanation: 'missing'}, {number: 2, match: 'same', answer: 'verified', explanation: 'verified'}]});
  assert.equal((await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0].state, 'BLOCKED_EXPLANATION');
});

test('6 unknown image sha is UNMAPPED', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = receipt(t, {images: [{path: 'assets/图1.png', sha256: 'unknown'}]});
  assert.equal((await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0].state, 'UNMAPPED');
});

test('7 stale revision or old receipt sha is STALE_REVISION', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const oldReceipt = receipt(t, {receiptRevision: 'rev-0'});
  assert.equal((await evaluateReceipts({receipts: [oldReceipt], trustedRoot: t.root})).rows[0].state, 'STALE_REVISION');
  const chained = receipt(t, {qaBaseReceiptSha: H('9')});
  const r = await evaluateReceipts({receipts: [chained], trustedRoot: t.root, previous: new Map([['8472470', H('8')]])});
  assert.equal(r.rows[0].state, 'STALE_REVISION');
});

test('8 self-approval by the same reviewer is BLOCKED_RIGHTS', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = receipt(t, {approval: {approvedBy: 'reviewer-a', approvalSha256: t.appS, approvalPath: 'approval.txt'}});
  assert.equal((await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0].state, 'BLOCKED_RIGHTS');
  assert.ok((await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0].reasons.includes('self-approval'));
});

test('9 unknown / forbidden rights block', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  for (const rights of [
    {basis: 'unknown', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: true},
    {basis: 'user-self-authorization', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: true},
    {basis: 'copyright-holder-license', evidenceSha256: t.licS, evidencePath: 'license.txt', holder: 'x', redistributable: false}
  ]) {
    assert.equal((await evaluateReceipts({receipts: [receipt(t, {rights})], trustedRoot: t.root})).rows[0].state, 'BLOCKED_RIGHTS');
  }
});

test('10 forged evidence sha fails closed', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = receipt(t, {rights: {basis: 'copyright-holder-license', evidenceSha256: H('f'), evidencePath: 'license.txt', holder: 'x', redistributable: true}});
  const row = (await evaluateReceipts({receipts: [r], trustedRoot: t.root})).rows[0];
  assert.equal(row.state, 'BLOCKED_RIGHTS');
  assert.ok(row.reasons.includes('evidence-sha-mismatch'));
});

test('11 duplicate sourceId and malformed envelope are UNMAPPED', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const r = await evaluateReceipts({receipts: [receipt(t), receipt(t)], trustedRoot: t.root});
  assert.equal(r.rows[1].state, 'UNMAPPED');
  assert.ok(r.rows[1].reasons.includes('duplicate-source-id'));
  assert.equal(classifyReceipt({paper: {}}).state, 'UNMAPPED');
});

test('12 unchanged revision is not re-queued; changed revision is', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const previous = new Map([['8472470', 'rev-1'], ['8472470:revision', 'rev-1']]);
  const same = await evaluateReceipts({receipts: [receipt(t)], trustedRoot: t.root, previous});
  assert.equal(same.summary.sourceChecked, 0);
  assert.equal(same.summary.sourceChanged, 0);

  const prevOld = new Map([['8472470', 'rev-0'], ['8472470:revision', 'rev-0']]);
  const changed = await evaluateReceipts({receipts: [receipt(t)], trustedRoot: t.root, previous: prevOld});
  assert.equal(changed.summary.sourceChecked, 1);
  assert.equal(changed.summary.sourceChanged, 1);
});

test('13 CLI dry-run reads JSONL and writes nothing', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'sq-'));
  const t = await trusted(root);
  const file = path.join(root, 'receipts.jsonl');
  await fs.writeFile(file, JSON.stringify(receipt(t)) + '\n');
  const result = await runQueue(['--receipts', file, '--trusted-root', t.root, '--dry-run']);
  assert.equal(result.ok, true);
  assert.equal(result.summary.receipts, 1);
  assert.equal(result.summary.promoted, 0);
  assert.deepEqual(await fs.readdir(root), ['receipts.jsonl', 'trusted']);
});
