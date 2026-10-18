import test from 'node:test';
import assert from 'node:assert/strict';
import { placeholderVerdict, sanitizeSourceUrl, taskKeyFor } from '../src/identity.mjs';
import { STAGES, ROLE_STAGES, EXIT } from '../src/constants.mjs';
import { MAX_CONCURRENCY, clampConcurrency } from '../src/throttle.mjs';
import { validateConfig } from '../src/config.mjs';
import { newQueue, enqueueInput, claimAndComplete } from './helpers.mjs';
import { buildHandoff } from '../src/handoff.mjs';

test('PR28 compatibility: one profile, at most three pages, identical clamp semantics', () => {
  assert.equal(MAX_CONCURRENCY, 3);
  assert.equal(clampConcurrency(1), 1);
  assert.equal(clampConcurrency(2), 2);
  assert.equal(clampConcurrency(3), 3);
  assert.equal(clampConcurrency(4), 3);
  assert.equal(clampConcurrency(0), 1);
  assert.equal(clampConcurrency('2'), 2);
  assert.equal(clampConcurrency('nope', 2), 2);
  assert.throws(() => validateConfig({ maxConcurrency: 4 }), /maxConcurrency/);
  assert.equal(validateConfig({ maxConcurrency: 3 }).maxConcurrency, 3);
});

test('PR36 compatibility: the same placeholder vocabulary is a terminal skip, not a completion', () => {
  for (const value of ['暂无解析', '暂无答案', '待补充', '待填写', '查看答案', '答案略', '略', 'TODO', 'PLACEHOLDER', '参考答案', '点击查看']) {
    assert.equal(placeholderVerdict(value).placeholder, true, value);
  }
  // PR45: the wording the live page actually renders, including the courtesy tail.
  for (const value of [
    '题目正在全力以赴征集',
    '题目正在全力以赴征集，将会第一时间上传',
    '题目正在全力以赴征集，将会在征集到后第一时间上传',
    '题目正在全力以赴征集，请稍后再试',
    '正在搜集中', '本题暂无收集到', '网友未回忆起', '题目缺失',
    '非客观题，请交卷后查看参考解析估分',
  ]) assert.equal(placeholderVerdict(value).placeholder, true, value);
  for (const value of [
    'B 项正确，材料反映了……',
    '本题解析见材料第三段',
    '参考答案：A',
    // A genuine stem that merely quotes the marker must not be swallowed by the bounded tail.
    '题目正在全力以赴征集，这是命题组的工作节奏，而考生需要做的是把握已有材料。'.repeat(2),
    '关于网友未回忆起的内容，下列说法正确的是：',
  ]) assert.equal(placeholderVerdict(value).placeholder, false, value);
  assert.equal(placeholderVerdict('<p>暂无解析</p>').placeholder, true);
  assert.equal(EXIT.BLOCKED, 2);
});

test('PR31 compatibility: stage vocabulary separates candidate_ready from verified', () => {
  assert.deepEqual(STAGES, ['capture_ready', 'normalized', 'aligned', 'assets_qa', 'answer_explanation_qa', 'human_review', 'candidate_ready']);
  assert.deepEqual(ROLE_STAGES.collector, ['capture_ready']);
  assert.deepEqual(ROLE_STAGES.assets_qa, ['assets_qa']);
  assert.deepEqual(ROLE_STAGES.answer_qa, ['answer_explanation_qa']);
  assert.equal(Object.keys(ROLE_STAGES).includes('verifier'), true);
  assert.equal(STAGES.includes('verified'), false, 'verification is a receipt-backed job state, not a claimable stage');
});

test('PR31 compatibility: a minimal handoff carries no browser session surface', async (t) => {
  const { queue } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const { job } = await claimAndComplete(queue, {
    jobId, stage: 'capture_ready', role: 'collector', owner: 'c1',
    artifact: { name: 'staged.json' },
  });
  const handoff = buildHandoff({ job, stage: 'capture_ready', artifacts: job.stages.capture_ready.artifacts });
  assert.deepEqual(Object.keys(handoff.permissions).sort(), ['browserProfile', 'cookies', 'localOnly', 'redistribution', 'tokens']);
  assert.equal(handoff.permissions.browserProfile, false);
  assert.equal(handoff.permissions.cookies, false);
  assert.equal(handoff.permissions.tokens, false);
  assert.equal(handoff.permissions.localOnly, true);
  assert.equal(handoff.review.required, false, 'capture handoff needs no answer-provenance review');
  for (const key of ['profileDir', 'cookieJar', 'storageState', 'authorization', 'headers']) assert.equal(key in handoff, false);
});

test('task keys are stable per stage and the URL sanitizer drops unlisted parameters', () => {
  const identity = { paperSourceId: '123', version: 'v1' };
  assert.equal(taskKeyFor(identity, 'normalized'), taskKeyFor(identity, 'normalized'));
  assert.notEqual(taskKeyFor(identity, 'normalized'), taskKeyFor(identity, 'aligned'));
  assert.equal(sanitizeSourceUrl('https://www.fenbi.com/spa/tiku?labelId=3&utm_source=x#token=y'), 'https://www.fenbi.com/spa/tiku?labelId=3');
  assert.throws(() => sanitizeSourceUrl('https://www.fenbi.com/spa/tiku?token=x'), /credential-like/);
});

test('configuration rejects unknown fields instead of silently ignoring them', () => {
  assert.throws(() => validateConfig({ maxConcurency: 3 }), /Unknown configuration field/);
  assert.throws(() => validateConfig({ maxConcurrency: 0 }), /maxConcurrency/);
  assert.throws(() => validateConfig({ backpressure: { maxQueueLength: -1 } }), /maxQueueLength/);
  assert.throws(() => validateConfig({ allowedCaptureHosts: [] }), /allowedCaptureHosts/);
});

test('an authorised-source allowlist blocks capture outside the operator-approved set', async (t) => {
  const { queue } = await newQueue(t, { authorizedSourceIds: ['approved-1'] });
  const input = enqueueInput({ paperSourceId: 'not-approved' });
  await assert.rejects(queue.enqueue(input), /CAPTURE_SOURCE_UNAUTHORIZED/);
  const approved = await queue.enqueue(enqueueInput({ paperSourceId: 'approved-1' }));
  assert.equal(approved.created, true);
  const empty = await newQueue(t, { authorizedSourceIds: [] });
  await assert.rejects(empty.queue.enqueue(enqueueInput({ paperSourceId: 'approved-1' })), /CAPTURE_SOURCE_UNAUTHORIZED/);
});

test('per-image references retain safe static URLs and reject absolute/credentialed paths', async (t) => {
  const { queue } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput({
    images: [
      { ref: 'material/q1.png', sourceUrl: 'https://img.fbstatic.cn/a.png?width=640' },
      { ref: 'options/q1-a.png' },
    ],
  }));
  const job = await queue.getJob(jobId);
  assert.equal(job.images.length, 2);
  assert.equal(job.images[0].sourceUrl, 'https://img.fbstatic.cn/a.png?width=640');
  assert.equal(job.images[1].sourceUrl, undefined);
  await assert.rejects(queue.enqueue(enqueueInput({ images: [{ ref: '/absolute.png' }] })), /escapes|relative/);
  await assert.rejects(queue.enqueue(enqueueInput({ images: [{ ref: 'q.png', sourceUrl: 'https://evil.test/q.png' }] })), /authorised static host/);
  await assert.rejects(queue.enqueue(enqueueInput({ images: [{ ref: 'q.png', sourceUrl: 'https://img.fbstatic.cn/q.png?token=x' }] })), /credential-like/);
});
