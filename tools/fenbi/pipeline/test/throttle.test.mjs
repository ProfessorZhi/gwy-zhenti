import test from 'node:test';
import assert from 'node:assert/strict';
import { temporary, makeConfig } from './helpers.mjs';
import {
  classifyStatus, loadThrottle, penalize, reserve, resetThrottle, saveThrottle, settle, throttleSnapshot, MAX_CONCURRENCY, clampConcurrency,
} from '../src/throttle.mjs';
import { evaluateBackpressure, capacityFor, hostPressure } from '../src/backpressure.mjs';

test('429/503 widen the persistable host interval and a clean call settles it', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  let state = await loadThrottle(dir, config, 1000);
  assert.equal(state.stopNewTasks, false);
  const first = reserve(state, 'www.fenbi.com', config, 1000);
  assert.equal(first.waitMs, 0);
  const second = reserve(state, 'www.fenbi.com', config, 1000);
  assert.equal(second.waitMs, 100, 'the second synchronous reservation must wait for the first');
  const penalty = penalize(state, 'www.fenbi.com', 429, config, 1000);
  assert.equal(penalty.intervalMs, 200);
  assert.equal(penalty.penalties, 1);
  assert.equal(penalty.blocked.kind, 'rate_limit');
  await saveThrottle(dir, state, 1000);
  state = await loadThrottle(dir, config, 1500);
  assert.equal(state.hosts['www.fenbi.com'].intervalMs, 200, 'backoff survives the next hourly invocation');
  state = await loadThrottle(dir, config, 5000);
  assert.equal(state.hosts['www.fenbi.com'].blocked, null, 'rate-limit backoff relaxes after its cooldown');
  assert.equal(state.hosts['www.fenbi.com'].intervalMs, config.throttle.minIntervalMs);
  const relaxed = settle(state, 'www.fenbi.com', config);
  assert.equal(relaxed, config.throttle.minIntervalMs);
});

test('401 and captcha stop new tasks until an explicit human reset', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  let state = await loadThrottle(dir, config, 1000);
  const penalty = penalize(state, 'www.fenbi.com', 401, config, 1000);
  assert.equal(penalty.blocked.kind, 'auth');
  assert.equal(state.stopNewTasks, true);
  await saveThrottle(dir, state, 1000);
  state = await loadThrottle(dir, config, 60 * 60 * 1000);
  assert.equal(state.stopNewTasks, true, 'auth stop is not cleared by elapsed time');
  const reservation = reserve(state, 'www.fenbi.com', config, 60 * 60 * 1000);
  assert.equal(reservation.allowed, false);
  resetThrottle(state, 'www.fenbi.com');
  await saveThrottle(dir, state, 60 * 60 * 1000);
  state = await loadThrottle(dir, config, 60 * 60 * 1000);
  assert.equal(state.stopNewTasks, false);
  assert.equal(reserve(state, 'www.fenbi.com', config, 60 * 60 * 1000).allowed, true);
});

test('status classification and PR28 concurrency compatibility', () => {
  assert.equal(classifyStatus(429), 'retryable');
  assert.equal(classifyStatus(503), 'retryable');
  assert.equal(classifyStatus(401), 'auth');
  assert.equal(classifyStatus(403), 'auth');
  assert.equal(classifyStatus(200), 'other');
  assert.equal(MAX_CONCURRENCY, 3);
  assert.equal(clampConcurrency(2), 2);
  assert.equal(clampConcurrency(9), 3);
  assert.equal(clampConcurrency(0), 1);
  assert.equal(clampConcurrency('bad', 2), 2);
});

test('backpressure pauses capture first, then all writes at the disk floor', () => {
  const config = makeConfig('/tmp/synthetic-data', {
    backpressure: { maxQueueLength: 50, maxPendingReview: 10, diskFreeFloorBytes: 1000, perPaperBytes: 1024 },
  });
  const base = { queueLength: 0, pendingReview: 0, diskFreeBytes: 1_000_000, oldestPendingAt: null };
  assert.equal(evaluateBackpressure({ status: base, config }).level, 'ok');
  const longQueue = evaluateBackpressure({ status: { ...base, queueLength: 50 }, config });
  assert.equal(longQueue.level, 'pause_capture');
  assert.equal(longQueue.allow.collector, false);
  assert.equal(longQueue.allow.normalizer, true);
  assert.ok(longQueue.reasons.some((reason) => reason.code === 'queue-length'));
  const backlog = evaluateBackpressure({ status: { ...base, pendingReview: 10 }, config });
  assert.equal(backlog.level, 'pause_capture');
  assert.equal(backlog.allow.reviewer, true, 'reviewers must still be able to drain the backlog');
  const disk = evaluateBackpressure({ status: { ...base, diskFreeBytes: 10 }, config });
  assert.equal(disk.level, 'pause_all');
  assert.equal(disk.allow.collector, false);
  assert.equal(disk.allow.reviewer, false);
  const stale = evaluateBackpressure({ status: { ...base, oldestPendingAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString() }, config });
  assert.equal(stale.level, 'degrade');
});

test('busy hosts reduce collector pages and worker slots instead of running at full speed', () => {
  const config = makeConfig('/tmp/synthetic-data');
  const normal = hostPressure({ cpus: 20, load1: 1, freeMemBytes: 8 * 1024 ** 3 });
  assert.equal(normal.degraded, false);
  const busy = hostPressure({ cpus: 20, load1: 30, freeMemBytes: 8 * 1024 ** 3 });
  assert.equal(busy.degraded, true);
  const backpressure = { allow: { collector: true, normalizer: true } };
  assert.equal(capacityFor({ role: 'collector', config, pressure: normal, backpressure, queued: 10 }), 2);
  assert.equal(capacityFor({ role: 'collector', config, pressure: busy, backpressure, queued: 10 }), 1);
  assert.equal(capacityFor({ role: 'normalizer', config, pressure: normal, backpressure, queued: 10 }), 8);
  assert.equal(capacityFor({ role: 'normalizer', config, pressure: busy, backpressure, queued: 10 }), 4);
  assert.equal(capacityFor({ role: 'normalizer', config, pressure: normal, backpressure: { allow: { normalizer: false } }, queued: 10 }), 0);
  assert.equal(throttleSnapshot({ stopNewTasks: false, blocked: null, hosts: {} }).stopNewTasks, false);
});
