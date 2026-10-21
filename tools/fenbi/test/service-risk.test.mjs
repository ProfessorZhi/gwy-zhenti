import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyRisk, riskDecision } from '../driver/service-risk.mjs';

// Summaries below copy the real shapes printed by the driver children.
const collector = (risk, stopReason = 'done') => ({ ok: true, stopReason,
  metrics: { papers: 3, complete: 3, failed: 0, risk: { captcha: 0, loginLost: 0, http403: 0, http429: 0, stops: [], ...risk } }, runs: [] });
const discover = risk => ({ ok: true, error: null, regions: {}, risk: { captcha: 0, unauthorized: 0, rateLimited: 0, stopWritten: false, ...risk } });
const assets = risk => ({ requested: 4, downloaded: 4, unauthorized: 0, httpError: 0, failed: 0, rejected: 0, bytes: 1, risk: { s401_403: 0, s429_503: 0, ...risk } });

test('collector risk nested under metrics is seen', () => {
  assert.deepEqual(classifyRisk(collector({ loginLost: 1 })).hard, ['login_lost']);
  assert.deepEqual(classifyRisk(collector({}, 'captcha')).hard, ['captcha']);
  assert.deepEqual(classifyRisk(collector({}, 'rate_limited_3_per_hour')).hard, ['rate_limited_3_per_hour']);
  assert.equal(classifyRisk(collector({ http429: 2 })).soft, 2);
});

test('discovery and asset-pass risk keys are seen', () => {
  assert.deepEqual(classifyRisk(discover({ unauthorized: 1 })).hard, ['unauthorized']);
  assert.equal(classifyRisk(discover({ rateLimited: 1 })).soft, 1);
  assert.equal(classifyRisk(assets({ s401_403: 1, s429_503: 1 })).soft, 2);
});

test('clean summaries and missing summaries are ok', () => {
  const hits = [];
  assert.equal(riskDecision(collector({}), hits).action, 'ok');
  assert.equal(riskDecision(discover({}), hits).action, 'ok');
  assert.equal(riskDecision(null, hits).action, 'ok');
});

test('hard risk stops at once; 403/429 back off and stop at three within an hour', () => {
  assert.equal(riskDecision(collector({ captcha: 1 }), []).action, 'stop');
  const hits = [], t0 = Date.parse('2026-10-21T00:00:00Z');
  assert.equal(riskDecision(collector({ http403: 1 }), hits, t0).action, 'backoff');
  assert.equal(riskDecision(assets({ s429_503: 1 }), hits, t0 + 60e3).action, 'backoff');
  const third = riskDecision(discover({ rateLimited: 1 }), hits, t0 + 120e3);
  assert.deepEqual([third.action, third.reason], ['stop', 'http_403_429_limit']);
  // Hits older than an hour fall out of the window.
  const later = [];
  riskDecision(collector({ http403: 2 }), later, t0);
  assert.equal(riskDecision(collector({ http403: 1 }), later, t0 + 3601e3).action, 'backoff');
});
