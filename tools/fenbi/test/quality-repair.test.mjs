import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { detectQualityGaps, buildRepairPlan, handoffCandidate, collectEvidence } from '../src/quality-repair.mjs';
import { runCli } from '../src/quality-repair-run.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const HEX = n => 'a'.repeat(64);

function q (n, stem, {answer = 'A', explanation = '合成解析' + n, options = ['甲', '乙', '丙', '丁']} = {}) {
  return ['### 第 ' + n + ' 题', stem, ...options.map((t, i) => `${'ABCD'[i]}. ${t}`), answer ? '【答案】' + answer : '', explanation ? '【解析】' + explanation : ''].join('\n');
}

function doc (parts, {title = '## 题目'} = {}) { return [title, ...parts, ''].join('\n'); }

function target ({stub2 = false, complete = true} = {}) {
  return {
    sourceId: '1001', path: '省考/上海/2020/行测-A.md', area: '上海', year: 2020, subject: 'xingce',
    markdown: doc([
      q(1, '题干一的合成测试文本。', {answer: complete ? '' : 'A', explanation: complete ? '' : '解析一'}),
      stub2 ? q(2, '题目正在全力以赴征集') : q(2, '题干二的合成测试文本。', {answer: 'B', explanation: '解析二'})
    ]),
    assets: []
  };
}

function donor (overrides = {}) {
  return {
    donorId: 'd1', sourceId: '2002', area: '上海', year: 2020, subject: 'xingce', variant: 'A',
    rights: {basis: 'copyright-holder-license', evidenceSha256: HEX(), holder: 'synthetic'},
    qa: {verdict: 'pass', reportSha256: HEX(), reviewedAt: '2026-10-20T00:00:00Z'},
    markdown: doc([
      q(1, '题干一的合成测试文本。', {answer: 'A', explanation: '捐赠解析一'}),
      q(2, '题干二的合成测试文本。', {answer: 'B', explanation: '捐赠解析二'})
    ]),
    assets: [],
    ...overrides
  };
}

test('1 stub target is not matched by number: REVIEW_REQUIRED', async () => {
  const result = await buildRepairPlan({target: target({stub2: true}), donors: [donor()]});
  assert.ok(result.reviewQueue.some(r => r.number === 2 && r.reason === 'no-independent-fingerprint'));
  assert.ok(result.plan.repairs.every(r => r.number !== 2));
});

test('2 conflicting donors are refused', async () => {
  const second = donor({donorId: 'd2', sourceId: '3003'});
  const result = await buildRepairPlan({target: target(), donors: [donor(), second]});
  assert.equal(result.ok, false);
  assert.ok(result.reviewQueue.some(r => r.reason === 'conflicting-donors'));
});

test('3 answer without a usable donor question is refused', async () => {
  const answerOnly = donor({
    markdown: doc([q(1, '题干一的合成测试文本。', {options: [], answer: 'A', explanation: '解析'})])
  });
  const result = await buildRepairPlan({target: target(), donors: [answerOnly]});
  assert.equal(result.ok, false);
  assert.ok(result.reviewQueue.some(r => r.reason === 'donor-answer-without-question'));
});

test('4 donor without per-question textual explanation is refused', async () => {
  const noExp = donor({
    markdown: doc([q(1, '题干一的合成测试文本。', {answer: 'A', explanation: ''})])
  });
  const result = await buildRepairPlan({target: target(), donors: [noExp]});
  assert.equal(result.ok, false);
  assert.ok(result.reviewQueue.some(r => r.reason === 'no-verbatim-explanation'));
});

test('5 donor asset missing or sha mismatch is refused', async () => {
  const withImage = donor({
    markdown: doc([q(1, '题干一的合成测试文本。 ![图](assets/d.png)', {answer: 'A', explanation: '解析'})]),
    assets: [{path: 'assets/d.png', sha256: 'not-a-sha'}]
  });
  const missing = await buildRepairPlan({target: target(), donors: [withImage]});
  assert.equal(missing.ok, false);
  assert.ok(missing.reviewQueue.some(r => r.reason === 'donor-asset-missing-or-sha'));
});

test('6 shenlun sub-question merge is refused', async () => {
  const t = target();
  t.subject = 'shenlun';
  t.markdown = doc([q(1, '请根据材料回答。', {answer: '', explanation: '', options: ['甲']})]);
  const d = donor({
    subject: 'shenlun',
    markdown: doc([q(1, '请根据材料回答。', {options: [], answer: '（1）甲（2）乙（3）丙', explanation: '解析'})])
  });
  const result = await buildRepairPlan({target: t, donors: [d]});
  assert.equal(result.ok, false);
  assert.ok(result.reviewQueue.some(r => ['shenlun-subquestion-merge', 'donor-answer-without-question'].includes(r.reason)));
});

test('7 unlicensed / self-authorized donor is rejected', async () => {
  const bad = donor({rights: {basis: 'user-self-authorization', evidenceSha256: HEX()}});
  const result = await buildRepairPlan({target: target(), donors: [bad]});
  assert.equal(result.ok, false);
  assert.equal(result.eligible, 0);
  assert.ok(result.reviewQueue.some(r => r.reason === 'no-donor-match'));
});

test('8 legal donor + unique fingerprint produces an isolated plan and QC receipt', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'repair-'));
  const original = target();
  const result = await buildRepairPlan({target: original, donors: [donor()], outDir: root, apply: true});
  assert.equal(result.ok, true, JSON.stringify(result.reviewQueue));
  assert.equal(result.plan.qc.verdict, 'pass');
  assert.notEqual(result.plan.beforeSha, result.plan.afterSha);
  assert.ok(result.plan.patchFile.startsWith(root));
  const written = await fs.readFile(result.plan.patchFile, 'utf8');
  assert.match(written, /【答案】A/);
  assert.match(original.markdown, /【答案】/); // original object untouched
  const handoff = handoffCandidate(result);
  assert.equal(handoff.ok, true);
  assert.ok(handoff.requires.includes('S1-rights-verification'));
});

test('9 stub repaired only with an explicit human-reviewed pair, never by number', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'repair-review-'));
  const result = await buildRepairPlan({
    target: target({stub2: true}), donors: [donor()], outDir: root, apply: true,
    reviewedPairs: [{targetNumber: 2, donorId: 'd1', donorNumber: 2, humanReviewedBy: 's1-owner'}]
  });
  assert.equal(result.ok, true, JSON.stringify(result.reviewQueue));
  const repaired2 = result.plan.repairs.find(r => r.number === 2);
  assert.equal(repaired2.matchedBy, 'human-reviewed');
});

test('10 zero eligible yields no handoff', async () => {
  const result = await buildRepairPlan({target: target(), donors: []});
  assert.equal(result.ok, false);
  assert.deepEqual(handoffCandidate(result), {ok: false, reason: 'not-repairable'});
});

test('11 CLI is default OFF and the fetcher is disabled without a provider', async () => {
  const off = await runCli(['--papers', 'x', '--donors', 'y', '--out', 'z'], {});
  assert.equal(off.stage, 'disabled');
  const noProvider = await collectEvidence({requests: [{sourceId: '1001'}], allowlist: ['1001']});
  assert.equal(noProvider.reason, 'fetch-disabled');
  const noAllow = await collectEvidence({provider: {fetch: async () => ({})}, requests: [{sourceId: '1001'}], allowlist: []});
  assert.equal(noAllow.reason, 'allowlist-required');
});

test('12 fake authorized provider adds evidence; unallowlisted requests are queued', async () => {
  const provider = {
    calls: 0,
    async fetch (request) {
      this.calls++;
      return {markdown: 'synthetic evidence ' + request.sourceId, license: {basis: 'official-public-release', evidenceSha256: HEX()}};
    }
  };
  const result = await collectEvidence({provider, requests: [{sourceId: '1001'}, {sourceId: '9999'}], allowlist: ['1001']});
  assert.equal(result.ok, true);
  assert.equal(result.fetched.length, 1);
  assert.equal(provider.calls, 1);
  assert.equal(result.queued[0].reason, 'not-allowlisted');
});

test('13 gaps detector separates structure from QA and flags rights', () => {
  const gaps = detectQualityGaps(target({stub2: true}), {rightsStatus: 'unverified'});
  assert.equal(gaps.structuralGrade, 'C');
  assert.ok(gaps.kinds.includes('missing-question'));
  assert.ok(gaps.kinds.includes('rights-unverified'));
  const complete = {...target(), markdown: doc([q(1, '题干一的合成测试文本。'), q(2, '题干二的合成测试文本。')])};
  const clean = detectQualityGaps(complete, {rightsStatus: 'cleared'});
  assert.equal(clean.structuralGrade, 'A');
});

test('14 synthetic throughput benchmark (CPU only)', async () => {
  const donors = [donor()];
  const started = process.hrtime.bigint();
  for (let i = 0; i < 100; i++) await buildRepairPlan({target: target(), donors});
  const ms = Number(process.hrtime.bigint() - started) / 1e6;
  assert.ok(ms < 5000, 'benchmark too slow: ' + ms.toFixed(0) + 'ms');
  console.log(JSON.stringify({benchmark: '100 synthetic plans', ms: Math.round(ms), papersPerSecond: Math.round(100000 / ms)}));
});
