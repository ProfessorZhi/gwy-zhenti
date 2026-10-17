import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { safeChild } from './fsutil.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(HERE, '../../../..');
export const DEFAULT_DATA_DIR = path.join(REPO, 'work', 'fenbi', 'pipeline');

export const DEFAULTS = Object.freeze({
  dataDir: null,
  maxConcurrency: 2,
  hardMaxConcurrency: 3,
  leaseTtlMs: 15 * 60 * 1000,
  collectorLeaseTtlMs: 30 * 60 * 1000,
  maxAttempts: 3,
  backoff: Object.freeze({ baseMs: 60_000, factor: 4, maxMs: 60 * 60 * 1000, jitter: 0.2 }),
  throttle: Object.freeze({ minIntervalMs: 1200, maxIntervalMs: 120_000, cooldownMs: 300_000 }),
  backpressure: Object.freeze({
    maxQueueLength: 500,
    maxPendingReview: 50,
    diskFreeFloorBytes: 5 * 1024 * 1024 * 1024,
    perPaperBytes: 512 * 1024 * 1024,
  }),
  allowedCaptureHosts: Object.freeze(['fenbi.com']),
  allowedImageHosts: Object.freeze(['fenbi.com', 'fbstatic.cn', 'fb.fenbike.cn']),
  // PR54: observed routing parameters (e.g. routecs) must be declared explicitly. Undeclared
  // parameters are still dropped, and a dropped non-tracking parameter makes the URL
  // non-reproducible. Credential-shaped names are rejected even if declared.
  routeParams: Object.freeze([]),
  // Fail closed: a production config must list the paper source IDs that were explicitly
  // authorised. null is only used by synthetic tests and means "policy intentionally unset".
  authorizedSourceIds: [],
  requireObservedUrl: true,
});

export const CREDENTIAL_QUERY_NAME = /token|key|secret|auth|session|cookie|signature|sign|credential|password|phone|mobile|code/i;
export const ROUTE_PARAM_VALUE = /^[A-Za-z0-9_,.:-]{0,200}$/;

function integer(value, label, min, max) {
  if (!Number.isInteger(value) || value < min || value > max) throw new Error(`Invalid ${label}`);
}

export function validateConfig(raw = {}) {
  for (const key of Object.keys(raw)) if (!(key in DEFAULTS)) throw new Error(`Unknown configuration field: ${key}`);
  const config = {
    ...DEFAULTS,
    ...raw,
    backoff: { ...DEFAULTS.backoff, ...(raw.backoff ?? {}) },
    throttle: { ...DEFAULTS.throttle, ...(raw.throttle ?? {}) },
    backpressure: { ...DEFAULTS.backpressure, ...(raw.backpressure ?? {}) },
    allowedCaptureHosts: raw.allowedCaptureHosts ?? [...DEFAULTS.allowedCaptureHosts],
    allowedImageHosts: raw.allowedImageHosts ?? [...DEFAULTS.allowedImageHosts],
  };
  integer(config.maxConcurrency, 'maxConcurrency', 1, 3);
  integer(config.hardMaxConcurrency, 'hardMaxConcurrency', 1, 3);
  if (config.maxConcurrency > config.hardMaxConcurrency) throw new Error('maxConcurrency exceeds hardMaxConcurrency');
  integer(config.leaseTtlMs, 'leaseTtlMs', 1_000, 24 * 60 * 60 * 1000);
  integer(config.collectorLeaseTtlMs, 'collectorLeaseTtlMs', 1_000, 24 * 60 * 60 * 1000);
  integer(config.maxAttempts, 'maxAttempts', 1, 20);
  integer(config.backoff.baseMs, 'backoff.baseMs', 1, 24 * 60 * 60 * 1000);
  integer(config.backoff.factor, 'backoff.factor', 1, 10);
  integer(config.backoff.maxMs, 'backoff.maxMs', config.backoff.baseMs, 7 * 24 * 60 * 60 * 1000);
  if (typeof config.backoff.jitter !== 'number' || config.backoff.jitter < 0 || config.backoff.jitter > 1) throw new Error('Invalid backoff.jitter');
  integer(config.throttle.minIntervalMs, 'throttle.minIntervalMs', 100, 60_000);
  integer(config.throttle.maxIntervalMs, 'throttle.maxIntervalMs', config.throttle.minIntervalMs, 60 * 60 * 1000);
  integer(config.throttle.cooldownMs, 'throttle.cooldownMs', 1_000, 24 * 60 * 60 * 1000);
  integer(config.backpressure.maxQueueLength, 'backpressure.maxQueueLength', 1, 100_000);
  integer(config.backpressure.maxPendingReview, 'backpressure.maxPendingReview', 0, 100_000);
  integer(config.backpressure.diskFreeFloorBytes, 'backpressure.diskFreeFloorBytes', 0, Number.MAX_SAFE_INTEGER);
  integer(config.backpressure.perPaperBytes, 'backpressure.perPaperBytes', 1, Number.MAX_SAFE_INTEGER);
  if (!Array.isArray(config.allowedCaptureHosts) || !config.allowedCaptureHosts.length ||
      config.allowedCaptureHosts.some((host) => typeof host !== 'string' || !/^[a-z0-9.-]+$/i.test(host))) {
    throw new Error('Invalid allowedCaptureHosts');
  }
  if (!Array.isArray(config.allowedImageHosts) || !config.allowedImageHosts.length ||
      config.allowedImageHosts.some((host) => typeof host !== 'string' || !/^[a-z0-9.-]+$/i.test(host))) {
    throw new Error('Invalid allowedImageHosts');
  }
  if (config.authorizedSourceIds !== null) {
    if (!Array.isArray(config.authorizedSourceIds) || config.authorizedSourceIds.some((id) => typeof id !== 'string' || !/^[A-Za-z0-9_.:-]{1,120}$/.test(id))) {
      throw new Error('Invalid authorizedSourceIds');
    }
    config.authorizedSourceIds = [...new Set(config.authorizedSourceIds)];
  }
  if (!Array.isArray(config.routeParams) || config.routeParams.length > 16) throw new Error('Invalid routeParams');
  for (const name of config.routeParams) {
    if (typeof name !== 'string' || !/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(name)) throw new Error('Invalid routeParams name');
    if (CREDENTIAL_QUERY_NAME.test(name)) throw new Error('routeParams may not contain credential-shaped names');
  }
  config.routeParams = [...new Set(config.routeParams)];
  if (typeof config.requireObservedUrl !== 'boolean') throw new Error('Invalid requireObservedUrl');
  if (config.dataDir !== null && (typeof config.dataDir !== 'string' || !path.isAbsolute(config.dataDir))) throw new Error('dataDir must be an absolute path');
  config.dataDir = config.dataDir ? path.resolve(config.dataDir) : DEFAULT_DATA_DIR;
  config.profileDir = null;
  return Object.freeze(config);
}

export async function loadPipelineConfig(filename) {
  const raw = filename ? JSON.parse(await fs.readFile(filename, 'utf8')) : {};
  return validateConfig(raw);
}

export function queuePaths(dataDir) {
  const root = path.resolve(dataDir);
  return Object.freeze({
    root,
    jobs: path.join(root, 'jobs'),
    leases: path.join(root, 'leases'),
    staleLeases: path.join(root, 'leases', 'stale'),
    artifacts: path.join(root, 'artifacts'),
    handoffs: path.join(root, 'handoffs'),
    deadLetter: path.join(root, 'dead-letter'),
    state: path.join(root, 'state'),
    review: path.join(root, 'review'),
    jobFile: (jobId) => safeChild(path.join(root, 'jobs'), `${jobId}.json`),
    jobLock: (jobId) => safeChild(path.join(root, 'jobs'), `.${jobId}.lock`),
    leaseFile: (jobId, stage) => safeChild(path.join(root, 'leases'), `${jobId}.${stage}.json`),
    artifactDir: (jobId, stage) => safeChild(path.join(root, 'artifacts'), `${jobId}/${stage}`),
    handoffFile: (jobId, stage) => safeChild(path.join(root, 'handoffs'), `${jobId}.${stage}.json`),
  });
}
