import path from 'node:path';
import { atomicWriteJson, nowIso, readJson } from './fsutil.mjs';
import { queuePaths } from './config.mjs';

export const MAX_CONCURRENCY = 3;

/** Mirrors tools/fenbi/src/schedule.mjs#clampConcurrency so a queue job can never exceed the
 * profile-wide page ceiling when the PR28 scheduler is present. */
export function clampConcurrency(value, fallback = 1) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1) return fallback;
  return Math.min(number, MAX_CONCURRENCY);
}

export function hostOf(value) {
  try { return new URL(value).hostname.toLowerCase(); } catch { return null; }
}

const RETRYABLE = new Set([429, 503]);
const AUTH_CHALLENGE = new Set([401, 403]);

export function classifyStatus(status) {
  const number = Number(status);
  if (RETRYABLE.has(number)) return 'retryable';
  if (AUTH_CHALLENGE.has(number)) return 'auth';
  return 'other';
}

function freshState(config, now) {
  return {
    schemaVersion: 1, updatedAt: nowIso(now), minIntervalMs: config.throttle.minIntervalMs,
    maxIntervalMs: config.throttle.maxIntervalMs, stopNewTasks: false, blocked: null, hosts: {},
  };
}

function hostState(state, host, config) {
  state.hosts[host] ??= {
    intervalMs: config.throttle.minIntervalMs, penalties: 0, nextAt: 0, blocked: null,
  };
  return state.hosts[host];
}

/**
 * Load the throttle across hourly invocations. A 401/captcha stop is *not* cleared by elapsed
 * time alone: `stopNewTasks` requires an explicit `throttle reset` after a human checks the
 * profile. 429/503 backoff does relax after its own cooldown.
 */
export async function loadThrottle(dataDir, config, now = Date.now()) {
  const filename = path.join(queuePaths(dataDir).state, 'throttle.json');
  let state;
  try { state = await readJson(filename, null); } catch { state = null; }
  if (!state || state.schemaVersion !== 1 || typeof state.hosts !== 'object') state = freshState(config, now);
  state.minIntervalMs = config.throttle.minIntervalMs;
  state.maxIntervalMs = config.throttle.maxIntervalMs;
  for (const [host, entry] of Object.entries(state.hosts)) {
    if (entry.blocked && entry.blocked.kind === 'rate_limit' && now - entry.blocked.at >= config.throttle.cooldownMs) {
      entry.blocked = null;
      entry.intervalMs = config.throttle.minIntervalMs;
      entry.penalties = 0;
      entry.nextAt = 0;
    }
  }
  if (state.blocked && state.blocked.kind === 'rate_limit' && now - state.blocked.at >= config.throttle.cooldownMs) state.blocked = null;
  state.stopNewTasks = Boolean(state.blocked) || Object.values(state.hosts).some((entry) => entry.blocked?.kind === 'auth');
  return state;
}

export async function saveThrottle(dataDir, state, now = Date.now()) {
  state.updatedAt = nowIso(now);
  state.stopNewTasks = Boolean(state.blocked) || Object.values(state.hosts).some((entry) => entry.blocked?.kind === 'auth');
  const filename = path.join(queuePaths(dataDir).state, 'throttle.json');
  await atomicWriteJson(filename, state);
  return state;
}

/** Reserve one request slot synchronously; the returned promise is the required wait. */
export function reserve(state, host, config, now = Date.now()) {
  const entry = hostState(state, host, config);
  if (entry.blocked?.kind === 'auth') return { allowed: false, waitMs: 0, blocked: entry.blocked };
  const base = Number.isInteger(entry.intervalMs) ? entry.intervalMs : config.throttle.minIntervalMs;
  const at = Number.isFinite(entry.nextAt) ? entry.nextAt : 0;
  const waitMs = Math.max(0, at - now);
  entry.nextAt = Math.max(now, at) + base;
  return { allowed: true, waitMs, intervalMs: base };
}

/** 429/503 widen this host's spacing; repeated penalties are visible to backpressure/status. */
export function penalize(state, host, status, config, now = Date.now()) {
  const entry = hostState(state, host, config);
  const current = Number.isInteger(entry.intervalMs) ? entry.intervalMs : config.throttle.minIntervalMs;
  const widened = Math.min(config.throttle.maxIntervalMs, Math.max(config.throttle.minIntervalMs, current * 2));
  entry.intervalMs = widened;
  entry.penalties = (entry.penalties ?? 0) + 1;
  entry.nextAt = Math.max(now, entry.nextAt ?? 0) + widened;
  const kind = classifyStatus(status);
  if (kind === 'auth') {
    entry.blocked = { kind: 'auth', status: Number(status), at: now, reason: 'authentication/captcha challenge; stop opening new tasks' };
    state.stopNewTasks = true;
  } else if (kind === 'retryable') {
    entry.blocked = { kind: 'rate_limit', status: Number(status), at: now };
  }
  return { host, status: Number(status), intervalMs: widened, penalties: entry.penalties, blocked: entry.blocked };
}

/** A clean request narrows this host back toward the floor, one halving at a time. */
export function settle(state, host, config) {
  const entry = state.hosts[host];
  if (!entry || entry.blocked?.kind === 'auth') return null;
  const relaxed = Math.max(config.throttle.minIntervalMs, Math.floor((entry.intervalMs ?? config.throttle.minIntervalMs) / 2));
  entry.intervalMs = relaxed;
  if (relaxed === config.throttle.minIntervalMs) { entry.penalties = 0; entry.blocked = null; }
  return relaxed;
}

/** Explicit human reset after a 401/captcha stop; never called automatically. */
export function resetThrottle(state, host = null) {
  if (host) {
    if (state.hosts[host]) state.hosts[host] = { intervalMs: state.minIntervalMs, penalties: 0, nextAt: 0, blocked: null };
  } else {
    state.hosts = {};
    state.blocked = null;
  }
  state.stopNewTasks = Boolean(state.blocked) || Object.values(state.hosts).some((entry) => entry.blocked?.kind === 'auth');
  return state;
}

export function throttleSnapshot(state) {
  return {
    stopNewTasks: state.stopNewTasks,
    blocked: state.blocked,
    hosts: Object.fromEntries(Object.entries(state.hosts).map(([host, entry]) => [host, {
      intervalMs: entry.intervalMs, penalties: entry.penalties ?? 0, nextAt: entry.nextAt ?? 0,
      blocked: entry.blocked ?? null,
    }])),
  };
}
