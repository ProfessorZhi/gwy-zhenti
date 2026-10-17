import fs from 'node:fs/promises';
import path from 'node:path';
import { atomicWriteJson, ensurePrivateDir, randomToken, readJson, pathExists } from './fsutil.mjs';
import { queuePaths } from './config.mjs';
import { STAGES } from './constants.mjs';

function leaseError(code, message, extra = {}) {
  return Object.assign(new Error(`[${code}] ${message}`), { code, ...extra });
}

export function parseLeaseName(filename) {
  const base = path.basename(filename);
  if (!base.endsWith('.json')) return null;
  const parts = base.slice(0, -'.json'.length).split('.');
  if (parts.length < 3) return null;
  const stage = parts.pop();
  const jobId = parts.join('.');
  return STAGES.includes(stage) ? { jobId, stage } : null;
}

/**
 * Claim one (job, stage) with O_EXCL. Exactly one process can create the lease file. An expired
 * lease is *moved aside* (kept for audit) by one contender via atomic rename, then generation is
 * incremented, so an old process that wakes up cannot commit over the new owner.
 */
export async function acquireLease(dataDir, jobId, stage, { owner, ttlMs = 15 * 60 * 1000, now = Date.now } = {}) {
  const clock = typeof now === 'function' ? now : () => now;
  if (!STAGES.includes(stage)) throw leaseError('INVALID_STAGE', `Unknown stage: ${stage}`);
  if (typeof owner !== 'string' || !/^[A-Za-z0-9_.:-]{1,64}$/.test(owner)) throw leaseError('INVALID_OWNER', 'Lease owner must be a short stable identifier');
  if (!Number.isInteger(ttlMs) || ttlMs < 1000) throw leaseError('INVALID_TTL', 'Lease TTL must be at least one second');
  const paths = queuePaths(dataDir);
  await ensurePrivateDir(paths.leases);
  await ensurePrivateDir(paths.staleLeases);
  const filename = paths.leaseFile(jobId, stage);
  let lastGeneration = 0;

  for (let attempt = 0; attempt < 20; attempt += 1) {
    let previous = null;
    let handle;
    try {
      handle = await fs.open(filename, 'wx', 0o600);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      // Re-read *after* EEXIST: a lease may have been created between any earlier read and now.
      try { previous = await readJson(filename, null); } catch { previous = null; }
      if (Number.isInteger(previous?.generation)) lastGeneration = Math.max(lastGeneration, previous.generation);
      if (previous && Number.isFinite(previous.expiresAt) && previous.expiresAt > clock()) {
        throw leaseError('LEASE_HELD', 'Another consumer owns this stage', {
          owner: previous.owner, expiresAt: previous.expiresAt,
        });
      }
      // Expired or unreadable: one atomic rename wins; the rest retry the O_EXCL open.
      const stale = path.join(paths.staleLeases, `${jobId}.${stage}.${randomToken()}.json`);
      try { await fs.rename(filename, stale); } catch (renameError) { if (renameError.code === 'ENOENT') continue; throw renameError; }
      continue;
    }
    const token = randomToken();
    const generation = Math.max(
      Number.isInteger(previous?.generation) ? previous.generation : 0,
      lastGeneration,
    ) + 1;
    const acquiredAt = clock();
    const lease = {
      schemaVersion: 1, jobId, stage, owner, token, generation,
      acquiredAt, expiresAt: acquiredAt + ttlMs, pid: process.pid,
    };
    try {
      await handle.writeFile(JSON.stringify(lease, null, 2) + '\n', 'utf8');
      await handle.sync();
    } catch (writeError) {
      await handle.close().catch(() => {});
      await fs.rm(filename, { force: true }).catch(() => {});
      throw writeError;
    } finally {
      await handle.close().catch(() => {});
    }
    return {
      ...lease,
      async release() { await releaseLease(dataDir, jobId, stage, { token, generation }); },
      async assert() { return assertLease(dataDir, jobId, stage, { token, generation, now }); },
    };
  }
  throw leaseError('LEASE_RACE', 'Could not claim the stage lease after repeated contention');
}

export async function readLease(dataDir, jobId, stage) {
  const paths = queuePaths(dataDir);
  return readJson(paths.leaseFile(jobId, stage), null);
}

export async function releaseLease(dataDir, jobId, stage, { token, generation }) {
  const paths = queuePaths(dataDir);
  const filename = paths.leaseFile(jobId, stage);
  const current = await readJson(filename, null);
  if (!current) return false;
  if (current.token !== token || current.generation !== generation) return false;
  await fs.unlink(filename);
  return true;
}

/** Throws unless this exact generation still owns an unexpired lease. */
export async function assertLease(dataDir, jobId, stage, { token, generation, now = Date.now }) {
  const clock = typeof now === 'function' ? now : () => now;
  const current = await readLease(dataDir, jobId, stage);
  if (!current) throw leaseError('LEASE_LOST', 'The stage lease no longer exists');
  if (current.token !== token || current.generation !== generation) {
    throw leaseError('LEASE_LOST', 'Another consumer reclaimed this stage', { generation: current.generation });
  }
  if (!(current.expiresAt > clock())) throw leaseError('LEASE_EXPIRED', 'The stage lease expired before commit');
  return current;
}

/** Move every expired/unreadable lease aside. The caller then repairs job state via reconcile. */
export async function reclaimExpiredLeases(dataDir, { now = Date.now } = {}) {
  const paths = queuePaths(dataDir);
  await ensurePrivateDir(paths.staleLeases);
  let entries = [];
  try { entries = await fs.readdir(paths.leases, { withFileTypes: true }); } catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  const reclaimed = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith('.json')) continue;
    const parsed = parseLeaseName(entry.name);
    if (!parsed) continue;
    const filename = path.join(paths.leases, entry.name);
    let lease;
    try { lease = await readJson(filename, null); } catch { lease = null; }
    if (lease && Number.isFinite(lease.expiresAt) && lease.expiresAt > now()) continue;
    const stale = path.join(paths.staleLeases, `${entry.name}.${randomToken()}`);
    try {
      await fs.rename(filename, stale);
      reclaimed.push({ ...parsed, owner: lease?.owner ?? null, generation: lease?.generation ?? null, reason: lease ? 'expired' : 'unreadable' });
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  return reclaimed;
}

export async function leaseOwnerIsAlive(dataDir, jobId, stage) {
  const lease = await readLease(dataDir, jobId, stage);
  if (!lease) return false;
  if (!Number.isInteger(lease.pid)) return true;
  try { process.kill(lease.pid, 0); return true; }
  catch (error) { return error.code === 'EPERM'; }
}
