import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCaptureBatchMetrics } from '../src/capture-metrics.mjs';

test('capture metrics do not confuse a partial or cached paper with a newly complete one', () => {
  const run = {
    results: [
      { ok: true, value: { status: 'complete', observedQuestions: 100 } },
      { ok: true, value: { status: 'partial', observedQuestions: 90 } },
      { ok: true, value: { status: 'cached_complete' } },
      { ok: false, error: new Error('network failure') },
      null,
    ],
    concurrency: 2, stopped: true, reason: 'rate-limited', skipped: [4],
  };
  const metrics = buildCaptureBatchMetrics(run, {
    startedAtMs: 1000000, endedAtMs: 1600000, planned: 5, spacingMs: 2500,
  });
  assert.deepEqual(metrics.counts, {
    newlyComplete: 1, newlyReadable: 2, questionSlotsObserved: 190,
    cachedComplete: 1, partial: 1, failed: 1, skipped: 1,
  });
  assert.equal(metrics.newlyCompletePerHour, 6);
  assert.equal(metrics.newlyReadablePerHour, 12);
  assert.equal(metrics.minimumNavigationSpacingMs, 2500);
  assert.equal(metrics.stopReason, 'rate-limited');
  assert.equal(metrics.pagesUsed, 2);
  assert.equal(JSON.stringify(metrics).includes('network failure'), false);
});

test('zero-duration metrics never manufacture an hourly throughput rate', () => {
  const metrics = buildCaptureBatchMetrics({
    results: [{ ok: true, value: { status: 'cached_complete' } }],
    concurrency: 1, stopped: false, reason: null, skipped: [],
  }, { startedAtMs: 2000000, endedAtMs: 2000000, planned: 1, spacingMs: 2500 });
  assert.equal(metrics.newlyReadablePerHour, null);
  assert.equal(metrics.newlyCompletePerHour, null);
  assert.equal(metrics.counts.cachedComplete, 1);
  assert.equal(metrics.counts.newlyReadable, 0);
});

test('refuses inconsistent scheduling counts', () => {
  assert.throws(() => buildCaptureBatchMetrics({
    results: [], concurrency: 2, stopped: false, reason: null, skipped: [],
  }, { startedAtMs: 1, endedAtMs: 2, planned: 1, spacingMs: 2500 }),
  /differs from scheduled jobs/);
});
