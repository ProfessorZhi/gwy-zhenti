import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import {
  DEFAULT_POLICY_PATH, loadPolicy, validatePolicy, isReplaceEnabled,
  countQuestions, assertReplacementAllowed, classifyPartialSource, computeKpi,
  findIdentityConflicts
} from '../src/policy.mjs';

async function validPolicy () {
  return JSON.parse(await fs.readFile(DEFAULT_POLICY_PATH, 'utf8'));
}

function q (n, {stub = false} = {}) {
  const body = stub ? '题目正在全力以赴征集' : `题干${n}。`;
  return [`### 第 ${n} 题`, body, 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁', '【答案】A', '【解析】解析'].join('\n');
}
const doc = parts => ['## 题目', ...parts, ''].join('\n');

test('1 shipped policy.json validates with fixed enums', async () => {
  const policy = await loadPolicy();
  assert.equal(policy.schemaVersion, 1);
  assert.equal(policy.replace, 'if_question_count_not_less');
  assert.equal(policy.stub, 'mark_missing_and_publish');
  assert.equal(policy.legalRights.publicRedistributionRequiresRightsHolderInstrument, true);
});

test('2 invalid enum fails closed', async () => {
  const policy = await validPolicy();
  policy.replace = 'always';
  assert.equal(validatePolicy(policy).ok, false);
  policy.replace = 'if_question_count_not_less';
  policy.stub = 'silently_fix';
  assert.equal(validatePolicy(policy).ok, false);
  policy.stub = 'mark_missing_and_publish';
  policy.legalRights.privateStorageUserConsentRecorded = false;
  assert.equal(validatePolicy(policy).ok, false);
  const typo = await validPolicy();
  typo.replacee = 'if_question_count_not_less';
  assert.equal(validatePolicy(typo).ok, false);
  const badException = await validPolicy();
  badException.exceptionHandling.captchaa = 'stop_notify';
  assert.equal(validatePolicy(badException).ok, false);
});

test('3 ALLOW_REPLACE "0"/"false" never enable replacement', () => {
  assert.equal(isReplaceEnabled('1'), true);
  for (const value of ['0', 'false', '', 'yes', undefined]) assert.equal(isReplaceEnabled(value), false);
});

test('4 run-pipeline.sh strict shell switch agrees with policy', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'policy-sh-'));
  for (const value of ['0', 'false', '1']) {
    const out = execFileSync('bash', ['-c', `ALLOW_REPLACE=${value}; REPLACE_FLAG=""; if [ "\${ALLOW_REPLACE:-0}" = 1 ]; then REPLACE_FLAG=--allow-replace; fi; printf '%s' "$REPLACE_FLAG"`], {encoding: 'utf8'});
    assert.equal(out, value === '1' ? '--allow-replace' : '', value);
  }
  const script = await fs.readFile(path.join(import.meta.dirname, '..', 'run-pipeline.sh'), 'utf8');
  assert.ok(!script.includes('${ALLOW_REPLACE:+--allow-replace}'), 'non-empty test would enable on 0');
});

test('5 equal effective question counts allow replacement', async () => {
  const policy = await loadPolicy();
  const prior = doc([q(1), q(2), q(3)]);
  const next = doc([q(1), q(2), q(3)]);
  const verdict = assertReplacementAllowed(policy, {priorMarkdown: prior, newMarkdown: next});
  assert.equal(verdict.allowed, true);
});

test('6 fewer effective questions are rejected even when slots match', async () => {
  const policy = await loadPolicy();
  const prior = doc([q(1), q(2), q(3)]);
  const next = doc([q(1), q(2, {stub: true}), q(3, {stub: true})]);
  const verdict = assertReplacementAllowed(policy, {priorMarkdown: prior, newMarkdown: next});
  assert.equal(verdict.allowed, false);
  assert.ok(verdict.reasons.includes('effective-question-count-decreased'));
});

test('7 120 slots with 8 stubs can be replaced by 120 complete', async () => {
  const policy = await loadPolicy();
  const prior = doc(Array.from({length: 120}, (_, i) => q(i + 1, {stub: i < 8})));
  const next = doc(Array.from({length: 120}, (_, i) => q(i + 1)));
  assert.equal(countQuestions(prior).effective, 112);
  const verdict = assertReplacementAllowed(policy, {priorMarkdown: prior, newMarkdown: next});
  assert.equal(verdict.allowed, true);
});

test('8 stub partial is marked missing, never complete A', async () => {
  const policy = await loadPolicy();
  const result = classifyPartialSource(policy, {stubNumbers: [5, 9], totalSlots: 130});
  assert.equal(result.status, 'PARTIAL_SOURCE_MISSING');
  assert.equal(result.publishable, false);
  assert.equal(result.completeness, 'partial');
  assert.deepEqual(result.missingNumbers, [5, 9]);
  assert.equal(result.status === 'A', false);
});

test('9 options-missing or multi-part is not a collection stub', async () => {
  const policy = await loadPolicy();
  assert.equal(classifyPartialSource(policy, {stubNumbers: [1], optionsMissing: [2], totalSlots: 5}).status, 'BLOCKED');
  assert.equal(classifyPartialSource(policy, {stubNumbers: [1], multiPart: [3], totalSlots: 5}).status, 'BLOCKED');
});

test('10 answer conflict policy keeps Fenbi as display baseline, not truth', async () => {
  const policy = await loadPolicy();
  assert.equal(policy.answer_conflict, 'use_fenbi_note_other');
  assert.equal(policy.source_priority, 'fenbi');
});

test('11 private storage consent is not public redistribution rights', async () => {
  const policy = await loadPolicy();
  assert.equal(policy.storage, 'private_repo_approved');
  assert.equal(policy.legalRights.privateStorageUserConsentRecorded, true);
  assert.equal(policy.legalRights.publicRedistributionRequiresRightsHolderInstrument, true);
  // No policy field may assert a copyright holder license.
  assert.ok(!JSON.stringify(policy).includes('rightsGranted'));
});

test('12 KPI numerator needs main SHA plus per-paper QA binding', async () => {
  const policy = await loadPolicy();
  const mainSha = 'a'.repeat(40);
  const catalog = [
    {sourceId: '1', subject: 'xingce', area: '浙江', year: 2020},
    {sourceId: '2', subject: 'xingce', area: '浙江', year: 2020},
    {sourceId: '3', subject: 'shenlun', area: '浙江', year: 2020}
  ];
  const papers = [
    {mainSha, sourceId: '1', subject: 'xingce', qa: {verdict: 'pass', reportSha256: 'b'.repeat(64)}},
    {sourceId: '2', subject: 'xingce', qa: {verdict: 'pass', reportSha256: 'b'.repeat(64)}} // no mainSha
  ];
  const kpi = computeKpi({mainSha, papers, catalog, policy});
  assert.equal(kpi.status, 'UNKNOWN');
  assert.equal(kpi.reason, 'numerator-unverifiable');
  assert.equal(kpi.denominator, 3);
});

test('13 KPI is UNKNOWN without catalog or main sha', async () => {
  const policy = await loadPolicy();
  assert.equal(computeKpi({mainSha: null, papers: [], catalog: [], policy}).status, 'UNKNOWN');
  assert.equal(computeKpi({mainSha: 'a'.repeat(40), papers: [], catalog: null, policy}).status, 'UNKNOWN');
});

test('14 same area/year/subject/variant with two sourceIds is an identity conflict', () => {
  const conflicts = findIdentityConflicts([
    {area: '浙江', year: 2020, subject: 'xingce', variant: 'A', sourceId: '1'},
    {area: '浙江', year: 2020, subject: 'xingce', variant: 'A', sourceId: '2'},
    {area: '浙江', year: 2021, subject: 'xingce', variant: 'A', sourceId: '3'}
  ]);
  assert.equal(conflicts.length, 1);
  assert.deepEqual(conflicts[0].sourceIds.sort(), ['1', '2']);
});

test('15 replacement policy is read from policy.json, not env strings', async () => {
  const policy = await loadPolicy();
  const verdict = assertReplacementAllowed({...policy, replace: 'never'}, {priorMarkdown: doc([q(1)]), newMarkdown: doc([q(1)])});
  assert.equal(verdict.allowed, false);
  assert.deepEqual(verdict.reasons, ['replace-disabled-by-policy']);
});

test('16 KPI is OK only with real main blob shas and a QA verifier', async () => {
  const policy = await loadPolicy();
  const mainSha = 'a'.repeat(40);
  const catalog = [{sourceId: '1', subject: 'xingce', area: '浙江', year: 2020}];
  const papers = [{
    path: '省考/浙江/2020/行测-A.md', mainSha, sourceId: '1', subject: 'xingce',
    mainBlobSha256: 'c'.repeat(64), qa: {verdict: 'pass', reportSha256: 'b'.repeat(64)}
  }];
  const ok = computeKpi({
    mainSha, papers, catalog, policy,
    mainFileSha256ByPath: {'省考/浙江/2020/行测-A.md': 'c'.repeat(64)},
    verifyQaAttestation: () => true
  });
  assert.equal(ok.status, 'OK');
  assert.equal(ok.value, 1);
  const bad = computeKpi({
    mainSha, papers, catalog, policy,
    mainFileSha256ByPath: {'省考/浙江/2020/行测-A.md': 'd'.repeat(64)},
    verifyQaAttestation: () => true
  });
  assert.equal(bad.status, 'OK');
  assert.equal(bad.numerator, 0);
});
