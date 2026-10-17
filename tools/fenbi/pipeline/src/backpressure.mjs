import os from 'node:os';
import { MAX_CONCURRENCY } from './throttle.mjs';

/**
 * Pure policy: given a queue snapshot and host pressure, decide which roles may run. It never
 * mutates the queue. `pause_all` means even reviewers stop writing; `pause_capture` keeps offline
 * consumers working down the backlog while the browser stops adding more work.
 */
export function evaluateBackpressure({ status, config, now = Date.now(), diskFreeBytes = null }) {
  const reasons = [];
  const free = diskFreeBytes ?? status.diskFreeBytes;
  if (free !== null && free < config.backpressure.diskFreeFloorBytes) {
    reasons.push({ code: 'disk-floor', freeBytes: free, floorBytes: config.backpressure.diskFreeFloorBytes });
  }
  if ((status.queueLength ?? 0) >= config.backpressure.maxQueueLength) {
    reasons.push({ code: 'queue-length', queueLength: status.queueLength, max: config.backpressure.maxQueueLength });
  }
  if ((status.pendingReview ?? 0) >= config.backpressure.maxPendingReview) {
    reasons.push({ code: 'review-backlog', pendingReview: status.pendingReview, max: config.backpressure.maxPendingReview });
  }
  if (status.oldestPendingAt && now - Date.parse(status.oldestPendingAt) > 24 * 60 * 60 * 1000) {
    reasons.push({ code: 'stale-backlog', oldestPendingAt: status.oldestPendingAt });
  }
  const disk = reasons.some((reason) => reason.code === 'disk-floor');
  const capture = disk || reasons.some((reason) => ['queue-length', 'review-backlog'].includes(reason.code));
  const level = disk ? 'pause_all' : capture ? 'pause_capture' : reasons.length ? 'degrade' : 'ok';
  return {
    level, reasons,
    allow: { collector: !disk && !capture, normalizer: !disk, matcher: !disk, assets_qa: !disk, answer_qa: !disk, reviewer: !disk, verifier: !disk },
  };
}

/** Read-only host pressure; used to reduce page/worker counts on a busy node. */
export function hostPressure({ cpus = os.cpus().length, load1 = os.loadavg()[0], freeMemBytes = os.freemem() } = {}) {
  const highLoad = load1 > cpus * 0.9;
  const lowMemory = freeMemBytes < 1024 * 1024 * 1024;
  return {
    cpus, load1, freeMemBytes, degraded: highLoad || lowMemory,
    reasons: [...(highLoad ? ['load-average'] : []), ...(lowMemory ? ['free-memory'] : [])],
  };
}

/** Capacity is a ceiling, not a target: a queue with two jobs never opens eight workers. */
export function capacityFor({ role, config, pressure, backpressure, queued = 0 }) {
  if (!backpressure.allow[role]) return 0;
  if (pressure?.degraded) return role === 'collector' ? 1 : Math.min(4, Math.max(1, queued));
  if (role === 'collector') return Math.min(config.maxConcurrency, MAX_CONCURRENCY, Math.max(1, queued));
  return Math.min(8, Math.max(1, queued));
}

export function summarizeHostPressure(pressure) {
  return {
    degraded: pressure.degraded,
    reasons: pressure.reasons,
    cpus: pressure.cpus,
    load1: Number(pressure.load1.toFixed(2)),
    freeMemBytes: pressure.freeMemBytes,
    action: pressure.degraded ? 'reduce collector pages to 1 and workers to <=4' : 'normal',
  };
}
