import { test } from 'node:test';
import assert from 'node:assert/strict';
import { evaluateRepairHandoff, publisherGate } from '../src/repair-handoff-contract.mjs';

const H = n => String(n).repeat(64).slice(0, 64);
const base = () => ({
  sourceId: '8472470',
  identity: {area: '上海', year: 2026, subject: 'xingce', variant: '统考'},
  paper: {declaredQuestions: 130},
  questionCount: 130, afterQuestionCount: 130,
  beforeSha: H('a'), afterSha: H('b'),
  sourceDom: {sha256: H('c'), sourceId: '8472470', capturedBy: 's1-owner', capturedAt: '2026-10-21T00:00:00Z'},
  gapsBefore: [{number: 80, gaps: ['missing-question']}, {number: 130, gaps: ['missing-question']}],
  gapsAfter: [],
  repairedNumbers: [80, 130],
  qa: {
    verdict: 'pass', reportSha256: H('d'),
    perQuestion: [
      {number: 80, approvalSha256: H('e'), reviewedBy: 'reviewer-a', scope: 's1-owner'},
      {number: 130, approvalSha256: H('f'), reviewedBy: 'reviewer-b', scope: 's1-owner'}
    ]
  },
  images: {refs: ['assets/图1.png'], assets: [{path: 'assets/图1.png', sha256: H('1')}]},
  rights: {basis: 'copyright-holder-license', evidenceSha256: H('2'), holder: 'synthetic holder', redistributable: true},
  shenlunSubQuestionsMerged: false
});

test('complete evidence yields READY but still no ingestion', () => {
  const v = evaluateRepairHandoff(base());
  assert.equal(v.status, 'READY');
  assert.equal(v.independentlyQaComplete, true);
  assert.equal(v.rightsCleared, true);
  assert.equal(v.publisherIngestionEligible, false);
  assert.equal(publisherGate(base()).stage, 'preflight-only');
});

test('forged/unchanged sha is PENDING', () => {
  const same = {...base(), afterSha: H('a')};
  assert.equal(evaluateRepairHandoff(same).status, 'PENDING_REVIEW');
  const bad = {...base(), afterSha: 'not-a-sha'};
  assert.ok(evaluateRepairHandoff(bad).missing.includes('after-sha-invalid'));
});

test('one repaired question with another gap left is PENDING', () => {
  const partial = {...base(), repairedNumbers: [80], gapsAfter: [{number: 130, gaps: ['missing-question']}],
    qa: {...base().qa, perQuestion: [{number: 80, approvalSha256: H('e'), reviewedBy: 'r', scope: 's1-owner'}]}};
  const v = evaluateRepairHandoff(partial);
  assert.equal(v.status, 'PENDING_REVIEW');
  assert.ok(v.missing.includes('gaps-remain'));
});

test('readable source without redistribution rights is PENDING', () => {
  const noLicense = {...base(), rights: {basis: 'user-self-authorization', evidenceSha256: H('2'), holder: 'x', redistributable: false}};
  const v = evaluateRepairHandoff(noLicense);
  assert.equal(v.status, 'PENDING_REVIEW');
  assert.equal(v.rightsCleared, false);
  assert.ok(v.missing.includes('rights-basis-forbidden'));
  assert.ok(v.missing.includes('redistribution-not-granted'));
});

test('shenlun with three merged sub-questions is PENDING', () => {
  const shenlun = {...base(), identity: {area: '上海', year: 2026, subject: 'shenlun', variant: 'A'},
    shenlunSubQuestionsMerged: true};
  assert.ok(evaluateRepairHandoff(shenlun).missing.includes('shenlun-subquestions-merged'));
});

test('missing per-question independent review is PENDING', () => {
  const reviewedOnce = {...base(), qa: {...base().qa, perQuestion: [{number: 80, approvalSha256: H('e'), reviewedBy: 'r', scope: 's1-owner'}]}};
  const v = evaluateRepairHandoff(reviewedOnce);
  assert.equal(v.status, 'PENDING_REVIEW');
  assert.ok(v.missing.includes('per-question-review:130'));
});

test('unsafe image reference or missing asset sha is PENDING', () => {
  const escape = {...base(), images: {refs: ['../../etc/passwd'], assets: []}};
  assert.ok(evaluateRepairHandoff(escape).missing.includes('image-ref-unsafe'));
  const noSha = {...base(), images: {refs: ['assets/图1.png'], assets: [{path: 'assets/图1.png', sha256: 'nope'}]}};
  assert.ok(evaluateRepairHandoff(noSha).missing.includes('image-sha-missing:assets/图1.png'));
});
