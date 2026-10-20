import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { detectQualityGaps, buildRepairPlan, handoffCandidate, collectEvidence } from '../src/quality-repair.mjs';
import { runCli } from '../src/quality-repair-run.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const HEX = n => 'a'.repeat(64);
const here = path.dirname(fileURLToPath(import.meta.url));
const hook = path.join(here, '..', 'quality-repair-hook.example.sh');

function q (n, stem, {answer = 'A', explanation = '合成解析' + n, options = ['甲', '乙', '丙', '丁']} = {}) {
  return ['### 第 ' + n + ' 题', stem, ...options.map((t, i) => `${'ABCD'[i]}. ${t}`), answer ? '【答案】' + answer : '', explanation ? '【解析】' + explanation : ''].join('\n');
}
const doc = parts => ['## 题目', ...parts, ''].join('\n');

async function trusted (root) {
  const dir = path.join(root, 'trusted');
  await fs.mkdir(dir, {recursive: true});
  const files = {qa: Buffer.from('synthetic independent QA report'), license: Buffer.from('synthetic copyright license'), target: Buffer.from('synthetic target rights license')};
  await fs.writeFile(path.join(dir, 'qa.txt'), files.qa);
  await fs.writeFile(path.join(dir, 'license.txt'), files.license);
  await fs.writeFile(path.join(dir, 'target-license.txt'), files.target);
  return {root: dir, qaS: sha(files.qa), licS: sha(files.license), tgtS: sha(files.target)};
}

function target ({stub2 = false, gap2 = false, t} = {}) {
  return {
    sourceId: '1001', path: '省考/上海/2020/行测-A.md', area: '上海', year: 2020, subject: 'xingce', variant: 'A',
    rightsStatus: 'cleared', rightsEvidencePath: 'target-license.txt', rightsEvidenceSha256: t?.tgtS ?? HEX(),
    markdown: doc([
      q(1, '题干一的合成测试文本。', {answer: '', explanation: ''}),
      stub2 ? q(2, '题目正在全力以赴征集')
        : gap2 ? q(2, '无捐赠者的独特题干。', {answer: '', explanation: ''})
          : q(2, '题干二的合成测试文本。')
    ]),
    assets: []
  };
}

function donor (t, overrides = {}) {
  return {
    donorId: 'd1', sourceId: '2002', area: '上海', year: 2020, subject: 'xingce', variant: 'A',
    rights: {basis: 'copyright-holder-license', evidencePath: 'license.txt', evidenceSha256: t?.licS ?? HEX(), holder: 'synthetic'},
    qa: {verdict: 'pass', reportPath: 'qa.txt', reportSha256: t?.qaS ?? HEX(), reviewedAt: '2026-10-20T00:00:00Z'},
    markdown: doc([
      q(1, '题干一的合成测试文本。', {answer: 'A', explanation: '捐赠解析一'}),
      q(2, '题干二的合成测试文本。', {answer: 'B', explanation: '捐赠解析二'})
    ]),
    assets: [], ...overrides
  };
}

async function ctx () {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'qr-'));
  const t = await trusted(root);
  return {root, t};
}

test('1 stub target without a signed review stays REVIEW_REQUIRED', async () => {
  const {root, t} = await ctx();
  const r = await buildRepairPlan({target: target({stub2: true, t}), donors: [donor(t)], trustedRoot: t.root, outDir: root, apply: true});
  assert.equal(r.eligible, 0);
  assert.ok(r.reviewQueue.some(x => x.number === 2 && x.reason === 'signed-review-required'));
  assert.equal(r.qc.verdict, 'PARTIAL_REVIEW');
});

test('2 conflicting donors are refused', async () => {
  const {t} = await ctx();
  const r = await buildRepairPlan({target: target({t}), donors: [donor(t), donor(t, {donorId: 'd2', sourceId: '3003'})], trustedRoot: t.root});
  assert.equal(r.eligible, 0);
  assert.ok(r.reviewQueue.some(x => x.reason === 'conflicting-donors'));
});

test('3 answer without a usable donor question is refused', async () => {
  const {t} = await ctx();
  const d = donor(t, {markdown: doc([q(1, '题干一的合成测试文本。', {options: [], answer: 'A', explanation: 'x'})])});
  const r = await buildRepairPlan({target: target({t}), donors: [d], trustedRoot: t.root});
  assert.equal(r.eligible, 0);
});

test('4 donor without verbatim explanation is refused', async () => {
  const {t} = await ctx();
  const d = donor(t, {markdown: doc([q(1, '题干一的合成测试文本。', {answer: 'A', explanation: ''})])});
  const r = await buildRepairPlan({target: target({t}), donors: [d], trustedRoot: t.root});
  assert.ok(r.reviewQueue.some(x => x.reason === 'no-verbatim-explanation'));
});

test('5 asset sha mismatch is refused', async () => {
  const {t} = await ctx();
  const d = donor(t, {
    markdown: doc([q(1, '题干一的合成测试文本。 ![图](assets/d.png)', {answer: 'A', explanation: 'x'})]),
    assets: [{path: 'assets/d.png', sha256: 'not-a-sha'}]
  });
  const r = await buildRepairPlan({target: target({t}), donors: [d], trustedRoot: t.root});
  assert.ok(r.reviewQueue.some(x => x.reason === 'donor-asset-missing-or-sha'));
});

test('6 shenlun sub-question merge is refused', async () => {
  const {t} = await ctx();
  const tg = {...target({t}), subject: 'shenlun', markdown: doc([q(1, '请根据材料回答。', {options: [], answer: '', explanation: ''})])};
  const d = donor(t, {subject: 'shenlun', markdown: doc([q(1, '请根据材料回答。', {options: [], answer: '（1）甲（2）乙（3）丙', explanation: 'x'})])});
  const r = await buildRepairPlan({target: tg, donors: [d], trustedRoot: t.root});
  assert.equal(r.eligible, 0);
});

test('7 self-authorized/unlicensed donor is rejected', async () => {
  const {t} = await ctx();
  const d = donor(t, {rights: {basis: 'user-self-authorization', evidencePath: 'license.txt', evidenceSha256: t.licS}});
  const r = await buildRepairPlan({target: target({t}), donors: [d], trustedRoot: t.root});
  assert.equal(r.eligible, 0);
  assert.ok(r.reviewQueue.some(x => x.reason === 'no-donor-match'));
});

test('8 legal donor + unique fingerprint yields a pass QC and isolated patch', async () => {
  const {root, t} = await ctx();
  const original = target({t});
  const r = await buildRepairPlan({target: original, donors: [donor(t)], trustedRoot: t.root, outDir: root, apply: true});
  assert.equal(r.ok, true, JSON.stringify(r.qc));
  assert.equal(r.plan.qc.verdict, 'pass');
  assert.ok(r.plan.patchFile.startsWith(root));
  assert.match(original.markdown, /【答案】\n?/); // original object untouched
  assert.equal(handoffCandidate(r).ok, true);
});

test('9 P0-A partial repair cannot pass QC or handoff', async () => {
  const {root, t} = await ctx();
  const r = await buildRepairPlan({target: target({gap2: true, t}), donors: [donor(t)], trustedRoot: t.root, outDir: root, apply: true});
  assert.equal(r.ok, false);
  assert.equal(r.eligible, 0);
  assert.notEqual(r.qc.verdict, 'pass');
  assert.equal(handoffCandidate(r).ok, false);
  assert.ok(r.plan.partialReceipt);
  const files = await fs.readdir(root);
  assert.ok(!files.some(f => f.startsWith('repair-') && f.endsWith('.md')));
});

test('10 missing target rights evidence cannot pass', async () => {
  const {t} = await ctx();
  const tg = {...target({t}), rightsStatus: 'unverified', rightsEvidencePath: 'missing-license.txt'};
  const r = await buildRepairPlan({target: tg, donors: [donor(t)], trustedRoot: t.root});
  assert.equal(r.ok, false);
  assert.equal(r.eligible, 0);
  assert.equal(r.qc.checks.targetRightsVerified, false);
});

test('11 cross-region/year/variant donor is not matched', async () => {
  const {t} = await ctx();
  for (const over of [{area: '北京'}, {year: 2021}, {variant: 'B'}, {subject: 'shenlun'}]) {
    const r = await buildRepairPlan({target: target({t}), donors: [donor(t, over)], trustedRoot: t.root});
    assert.ok(r.reviewQueue.some(x => x.reason === 'no-donor-match'), JSON.stringify(over));
  }
});

test('12 duplicate target stem blocks bidirectional matching', async () => {
  const {t} = await ctx();
  const tg = {...target({t}), markdown: doc([q(1, '同一题干。', {answer: '', explanation: ''}), q(2, '同一题干。', {answer: '', explanation: ''})])};
  const d = donor(t, {markdown: doc([q(1, '同一题干。', {answer: 'A', explanation: 'x'})])});
  const r = await buildRepairPlan({target: tg, donors: [d], trustedRoot: t.root});
  assert.equal(r.eligible, 0);
  assert.ok(r.reviewQueue.some(x => x.reason === 'duplicate-target-stem'));
});

test('13 forged human review without signed approval hash is refused', async () => {
  const {t} = await ctx();
  const r = await buildRepairPlan({
    target: target({stub2: true, t}), donors: [donor(t)], trustedRoot: t.root,
    reviewedPairs: [{targetNumber: 2, donorId: 'd1', donorNumber: 2, humanReviewedBy: 'anyone'}]
  });
  assert.equal(r.eligible, 0);
  assert.ok(r.reviewQueue.some(x => x.reason === 'signed-review-required'));
});

test('14 last question never absorbs the independent answer area', async () => {
  const {root, t} = await ctx();
  const tg = {
    ...target({t}), markdown: ['## 题目', '### 第 1 题', '题目正在全力以赴征集', '',
      '## 参考答案', '<details><summary>第 1 题</summary>**答案**：A **解析**：合成解析</details>', ''].join('\n')
  };
  const d = donor(t);
  const r = await buildRepairPlan({
    target: tg, donors: [d], trustedRoot: t.root, outDir: root, apply: true,
    reviewedPairs: [{targetNumber: 1, donorId: 'd1', donorNumber: 1, humanReviewedBy: 's1-owner', signedBy: 's1-owner', reviewerScope: 's1-owner', approvalSha256: 'b'.repeat(64)}]
  });
  assert.equal(r.ok, true, JSON.stringify(r.qc));
  const written = await fs.readFile(r.plan.patchFile, 'utf8');
  assert.match(written, /## 参考答案/);
  assert.match(written, /<details>/);
});

test('15 no question headings is graded C, never A', () => {
  const gaps = detectQualityGaps({sourceId: 'x', markdown: '仅有一段材料，没有题块。', assets: [], rightsStatus: 'cleared'});
  assert.equal(gaps.structuralGrade, 'C');
  assert.ok(gaps.kinds.includes('no-question-blocks'));
});

test('16 zero eligible yields no handoff', async () => {
  const {t} = await ctx();
  const r = await buildRepairPlan({target: target({t}), donors: [], trustedRoot: t.root});
  assert.equal(r.ok, false);
  assert.deepEqual(handoffCandidate(r), {ok: false, reason: 'not-repairable'});
});

test('17 CLI is default OFF; fetcher disabled without provider', async () => {
  assert.equal((await runCli(['--papers', 'x', '--donors', 'y', '--out', 'z'], {})).stage, 'disabled');
  assert.equal((await collectEvidence({requests: [{sourceId: '1'}], allowlist: ['1']})).reason, 'fetch-disabled');
  assert.equal((await collectEvidence({provider: {fetch: async () => ({})}, requests: [{sourceId: '1'}], allowlist: []})).reason, 'allowlist-required');
});

test('18 fake authorized provider fetches only allowlisted evidence', async () => {
  let calls = 0;
  const provider = {async fetch (r) { calls++; return {markdown: 'synthetic ' + r.sourceId, license: {basis: 'official-public-release', evidenceSha256: HEX()}}; }};
  const r = await collectEvidence({provider, requests: [{sourceId: '1'}, {sourceId: '2'}], allowlist: ['1']});
  assert.equal(r.ok, true);
  assert.equal(r.fetched.length, 1);
  assert.equal(calls, 1);
});

test('19 out dir must be private', async () => {
  const {root, t} = await ctx();
  const out = path.join(root, 'out');
  await fs.mkdir(out, {recursive: true, mode: 0o755});
  await fs.chmod(out, 0o755);
  const r = await buildRepairPlan({target: target({t}), donors: [donor(t)], trustedRoot: t.root, outDir: out, apply: true});
  assert.equal(r.ok, false);
  assert.deepEqual(r.reasons, ['out-dir-not-private']);
});

test('20 QUALITY_REPAIR_APPLY only exact 1 adds --apply', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'qr-hook-'));
  const bin = path.join(root, 'bin');
  await fs.mkdir(bin, {recursive: true});
  const argsFile = path.join(root, 'args.txt');
  await fs.writeFile(path.join(bin, 'node'), '#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_FILE"\n', {mode: 0o755});
  const papers = path.join(root, 'p.json'); await fs.writeFile(papers, '[]');
  const donors = path.join(root, 'd.json'); await fs.writeFile(donors, '[]');
  const out = path.join(root, 'out'); await fs.mkdir(out);
  for (const value of ['0', 'false', '']) {
    const env = {...process.env, PATH: bin + ':' + process.env.PATH, QUALITY_REPAIR: '1', QUALITY_REPAIR_APPLY: value,
      QUALITY_REPAIR_PAPERS: papers, QUALITY_REPAIR_DONORS: donors, QUALITY_REPAIR_OUT: out, ARGS_FILE: argsFile};
    execFileSync('bash', [hook], {env, encoding: 'utf8'});
    assert.ok(!(await fs.readFile(argsFile, 'utf8')).includes('--apply'), value);
    await fs.rm(argsFile, {force: true});
  }
  const env = {...process.env, PATH: bin + ':' + process.env.PATH, QUALITY_REPAIR: '1', QUALITY_REPAIR_APPLY: '1',
    QUALITY_REPAIR_PAPERS: papers, QUALITY_REPAIR_DONORS: donors, QUALITY_REPAIR_OUT: out, ARGS_FILE: argsFile};
  execFileSync('bash', [hook], {env, encoding: 'utf8'});
  assert.ok((await fs.readFile(argsFile, 'utf8')).includes('--apply'));
});

test('21 synthetic throughput benchmark (CPU only)', async () => {
  const {t} = await ctx();
  const started = process.hrtime.bigint();
  for (let i = 0; i < 30; i++) await buildRepairPlan({target: target({t}), donors: [donor(t)], trustedRoot: t.root});
  const ms = Number(process.hrtime.bigint() - started) / 1e6;
  assert.ok(ms < 10000);
  console.log(JSON.stringify({benchmark: '30 synthetic plans', ms: Math.round(ms)}));
});
