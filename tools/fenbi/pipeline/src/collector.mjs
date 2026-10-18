import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';
import { atomicWriteJson, ensurePrivateDir, nowIso, randomToken, readJson } from './fsutil.mjs';
import { queuePaths } from './config.mjs';
import { EXIT, NON_COMPLETION, ROLE_STAGES } from './constants.mjs';
import { loadThrottle, penalize, reserve, saveThrottle, settle, throttleSnapshot } from './throttle.mjs';
import { capacityFor } from './backpressure.mjs';

function collectorError(code, message, extra = {}) { return Object.assign(new Error(`[${code}] ${message}`), { code, ...extra }); }

function pidAlive(pid) {
  if (!Number.isInteger(pid)) return false;
  try { process.kill(pid, 0); return true; }
  catch (error) { return error.code === 'EPERM'; }
}

/**
 * The profile-owner lock is deliberately separate from a stage lease: it guarantees that only one
 * collector process exists, while stage leases decide which capture tasks that process may take.
 * A crashed collector's lock is reclaimed only when its pid is gone; an unreadable/ambiguous lock
 * stops the run instead of being deleted.
 */
export async function acquireCollectorLock(dataDir, { owner, staleMs = 60 * 60 * 1000, now = Date.now } = {}) {
  const directory = queuePaths(dataDir).state;
  await ensurePrivateDir(directory);
  const filename = path.join(directory, 'collector.owner.lock');
  const token = randomToken();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const handle = await fs.open(filename, 'wx', 0o600);
      try {
        await handle.writeFile(JSON.stringify({ owner, token, pid: process.pid, at: nowIso(now()) }), 'utf8');
        await handle.sync();
      } finally { await handle.close(); }
      return {
        token,
        async release() {
          const current = await readJson(filename, null);
          if (current?.token === token) await fs.unlink(filename).catch(() => {});
        },
      };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let current = null;
      try { current = await readJson(filename, null); } catch { current = null; }
      const alive = Boolean(current && Number.isInteger(current.pid) && pidAlive(current.pid));
      if (alive) throw collectorError('COLLECTOR_LOCKED', 'Another collector owns the browser profile', { owner: current?.owner ?? null });
      if (!current) {
        // The owner may be between O_EXCL create and its first write. Give it a moment.
        await sleep(50);
        continue;
      }
      const aside = `${filename}.stale-${token}`;
      try { await fs.rename(filename, aside); } catch (renameError) { if (renameError.code === 'ENOENT') continue; throw renameError; }
      await fs.rm(aside, { force: true }).catch(() => {});
    }
  }
  throw collectorError('COLLECTOR_LOCK_RACE', 'Could not acquire the collector lock');
}

export async function loadWorkerAdapter(modulePath) {
  if (!modulePath) return null;
  const module = await import(pathToFileURL(path.resolve(modulePath)).href);
  const adapter = module.default ?? module.adapter;
  if (!adapter || typeof adapter.process !== 'function') throw collectorError('ADAPTER_INVALID', 'Worker adapter must export process(job, context)');
  return adapter;
}

export async function loadAdapter(modulePath, { jobId } = {}) {
  if (!modulePath) return null;
  const module = await import(pathToFileURL(path.resolve(modulePath)).href);
  const adapter = module.default ?? module.adapter;
  if (!adapter || typeof adapter.capture !== 'function') throw collectorError('ADAPTER_INVALID', 'Collector adapter must export capture(job, context)');
  if (adapter.opensProfile !== false) {
    // Refuse an adapter that advertises its own persistent context; one profile, one owner.
    throw collectorError('ADAPTER_OPENS_PROFILE', 'Collector adapters may not open a second persistent profile; receive pages from the owner instead');
  }
  return adapter;
}

/**
 * Run one bounded collector drain. This is not a daemon and does not loop forever: it returns
 * `queue_empty`, `budget_exhausted`, `backpressure`, `blocked_auth` or `collector_unwired`.
 * Without an injected adapter it claims nothing, because claiming a capture task with no browser
 * owner would only strand a lease.
 */
export async function runCollector({
  queue, config, adapter = null, owner = `collector-${process.pid}`, budget = 1,
  now = Date.now, pressure = null, backpressure = null, loadThrottleState = true,
} = {}) {
  const paths = queuePaths(config.dataDir);
  await queue.init();
  await ensurePrivateDir(paths.state);
  if (!Number.isInteger(budget) || budget < 0) throw collectorError('INVALID_BUDGET', 'budget must be a non-negative integer');
  const lock = await acquireCollectorLock(config.dataDir, { owner, now: () => now() });
  let throttle = null;
  const finish = async (payload) => {
    if (throttle && loadThrottleState) await saveThrottle(config.dataDir, throttle, now());
    await lock.release();
    return { owner, throttle: throttle ? throttleSnapshot(throttle) : null, ...payload };
  };
  try {
    if (loadThrottleState) throttle = await loadThrottle(config.dataDir, config, now());
    else throttle = { schemaVersion: 1, updatedAt: nowIso(now()), minIntervalMs: config.throttle.minIntervalMs, maxIntervalMs: config.throttle.maxIntervalMs, stopNewTasks: false, blocked: null, hosts: {} };
    await atomicWriteJson(path.join(paths.state, 'collector-status.json'), {
      schemaVersion: 1,
      adapterWired: Boolean(adapter),
      lastRunAt: nowIso(now()),
      owner,
      reason: adapter ? 'adapter-present' : 'collector_unwired',
    });
    if (throttle.stopNewTasks) {
      return await finish({ reason: 'blocked_auth', exit: EXIT.BLOCKED, claimed: 0, results: [], message: 'A prior 401/captcha stop is still active; a human must reset it after checking the profile.' });
    }
    if (backpressure && !backpressure.allow.collector) {
      return await finish({ reason: 'backpressure', exit: EXIT.BACKPRESSURE, claimed: 0, results: [], backpressure });
    }
    if (!adapter) {
      return await finish({ reason: 'collector_unwired', exit: EXIT.BLOCKED, claimed: 0, results: [], message: 'No browser-owner adapter was injected. Queue code is ready, but no capture is performed.' });
    }
    const status = await queue.status({ now: now() });
    const slots = Math.min(
      capacityFor({ role: 'collector', config, pressure, backpressure: backpressure ?? { allow: { collector: true } }, queued: status.queueLength }),
      config.maxConcurrency, budget,
    );
    const claims = [];
    for (let index = 0; index < slots; index += 1) {
      const claim = await queue.claimStage('capture_ready', { role: 'collector', owner, now: now() });
      if (!claim) break;
      claims.push(claim);
    }
    if (!claims.length) return await finish({ reason: status.queueLength ? 'backoff_or_blocked' : 'queue_empty', exit: EXIT.OK, claimed: 0, results: [] });

    const runOne = async (claim, slot) => {
      const context = {
        slot, config, owner,
        host: new URL(claim.job.url).hostname,
        reserve: async () => {
          const host = new URL(claim.job.url).hostname;
          const slot = reserve(throttle, host, config, now());
          if (!slot.allowed) throw collectorError('THROTTLE_BLOCKED', 'Host is blocked by an authentication challenge');
          if (slot.waitMs > 0) await sleep(slot.waitMs);
          return slot;
        },
        penalize: (statusCode) => penalize(throttle, new URL(claim.job.url).hostname, statusCode, config, now()),
      };
      try {
        await context.reserve();
        const result = await adapter.capture(claim.job, context);
        if (!result || typeof result !== 'object') throw collectorError('ADAPTER_INVALID_RESULT', 'Adapter returned no result');
        if (result.outcome && NON_COMPLETION.includes(result.outcome)) {
          await queue.failStage({
            jobId: claim.job.jobId, stage: 'capture_ready', owner, token: claim.lease.token,
            generation: claim.lease.generation, outcome: result.outcome,
            reason: String(result.reason ?? `adapter reported ${result.outcome}`).slice(0, 1000), now: now(),
          });
          return { jobId: claim.job.jobId, outcome: result.outcome };
        }
        const artifacts = [];
        for (const item of result.artifacts ?? []) {
          const manifest = await queue.putArtifact({
            jobId: claim.job.jobId, stage: 'capture_ready', owner,
            token: claim.lease.token, generation: claim.lease.generation,
            source: item.source, name: item.name, kind: item.kind ?? 'staged_raw',
          });
          artifacts.push(manifest);
        }
        await queue.completeStage({
          jobId: claim.job.jobId, stage: 'capture_ready', owner, token: claim.lease.token,
          generation: claim.lease.generation, artifacts, declarations: result.declarations ?? {}, now: now(),
        });
        if (throttle) settle(throttle, context.host, config);
        return { jobId: claim.job.jobId, outcome: 'done' };
      } catch (error) {
        const statusCode = Number(error.statusCode ?? error.httpStatus);
        if (throttle && (statusCode === 429 || statusCode === 503)) penalize(throttle, context.host, statusCode, config, now());
        if (throttle && (statusCode === 401 || statusCode === 403 || error.code === 'CAPTCHA')) {
          penalize(throttle, context.host, statusCode || 401, config, now());
          await queue.failStage({
            jobId: claim.job.jobId, stage: 'capture_ready', owner, token: claim.lease.token,
            generation: claim.lease.generation, outcome: 'blocked_auth',
            reason: String(error.message ?? 'authentication challenge').slice(0, 1000), now: now(),
          }).catch(() => {});
          return { jobId: claim.job.jobId, outcome: 'blocked_auth', error: error.message };
        }
        await queue.failStage({
          jobId: claim.job.jobId, stage: 'capture_ready', owner, token: claim.lease.token,
          generation: claim.lease.generation, outcome: 'partial',
          reason: `collector adapter failed: ${error.message}`.slice(0, 1000), now: now(),
        }).catch(() => {});
        return { jobId: claim.job.jobId, outcome: 'partial', error: error.message, statusCode: statusCode || null };
      }
    };

    const settled = await Promise.allSettled(claims.map((claim, index) => runOne(claim, index)));
    const results = settled.map((entry, index) => entry.status === 'fulfilled'
      ? entry.value
      : { jobId: claims[index].job.jobId, outcome: 'partial', error: entry.reason?.message ?? 'unknown' });
    const blocked = results.some((item) => item.outcome === 'blocked_auth');
    const throttled = results.some((item) => item.statusCode === 429 || item.statusCode === 503);
    const reason = blocked ? 'blocked_auth' : throttled ? 'rate_limited' : results.every((item) => item.outcome === 'done') ? 'drained' : 'partial';
    return await finish({ reason, exit: blocked ? EXIT.BLOCKED : throttled ? EXIT.BACKOFF : EXIT.OK, claimed: claims.length, results });
  } finally {
    // `finish` releases on normal paths; this is a safety net for thrown errors.
    if (lock) await lock.release().catch(() => {});
  }
}

/**
 * Offline consumer drain. An external agent provides `adapter.process(job, ctx)`; without one the
 * drain refuses to claim, because holding a lease with no processor starves the queue.
 */
export async function runWorkerDrain({
  queue, config, role, stage, adapter = null, owner = `worker-${process.pid}`, budget = 1, now = Date.now,
} = {}) {
  if (!ROLE_STAGES[role]?.includes(stage)) throw collectorError('ROLE_FORBIDDEN', `Role ${role} may not claim ${stage}`);
  if (role === 'collector') throw collectorError('ROLE_FORBIDDEN', 'Use runCollector for capture_ready');
  if (!adapter) return { reason: 'worker_unwired', exit: EXIT.BLOCKED, claimed: 0, results: [] };
  if (typeof adapter.process !== 'function') throw collectorError('ADAPTER_INVALID', 'Worker adapter must export process(job, context)');
  const results = [];
  for (let index = 0; index < budget; index += 1) {
    const claim = await queue.claimStage(stage, { role, owner, now: now() });
    if (!claim) break;
    try {
      const result = await adapter.process(claim.job, { stage, owner, config });
      if (result?.outcome && NON_COMPLETION.includes(result.outcome)) {
        await queue.failStage({
          jobId: claim.job.jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation,
          outcome: result.outcome, reason: String(result.reason ?? result.outcome), now: now(),
        });
        results.push({ jobId: claim.job.jobId, outcome: result.outcome });
        continue;
      }
      const artifacts = [];
      for (const item of result?.artifacts ?? []) {
        artifacts.push(await queue.putArtifact({
          jobId: claim.job.jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation,
          source: item.source, name: item.name, kind: item.kind ?? 'data',
        }));
      }
      await queue.completeStage({
        jobId: claim.job.jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation,
        artifacts, declarations: result?.declarations ?? {}, now: now(),
      });
      results.push({ jobId: claim.job.jobId, outcome: 'done' });
    } catch (error) {
      await queue.failStage({
        jobId: claim.job.jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation,
        outcome: 'partial', reason: String(error.message).slice(0, 1000), now: now(),
      }).catch(() => {});
      results.push({ jobId: claim.job.jobId, outcome: 'partial', error: error.message });
    }
  }
  return { reason: results.length ? 'drained' : 'queue_empty', exit: EXIT.OK, claimed: results.length, results };
}

/** Reviewer/verifier drains never decide for the human; they produce a manifest to work from. */
export async function runAwaitedManifest({ queue, stage, now = Date.now } = {}) {
  const jobs = await queue.listJobs();
  const pending = jobs.filter((job) => job.stages[stage]?.status === 'pending' && (stage !== 'human_review' || job.stages.answer_explanation_qa?.status === 'done'));
  return {
    generatedAt: nowIso(now()), stage,
    count: pending.length,
    items: pending.map((job) => ({
      jobId: job.jobId, title: job.title, paperSourceId: job.paperSourceId, version: job.version,
      status: job.status, reason: job.stages[stage]?.reason ?? null,
      artifacts: job.stages[stage]?.artifacts ?? [],
      reviewRequired: stage === 'human_review',
    })),
    note: 'This manifest grants no approval. A reviewer must complete the stage with approved=true and a name.',
  };
}
