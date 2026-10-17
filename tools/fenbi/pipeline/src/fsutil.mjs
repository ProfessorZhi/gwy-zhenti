import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';

export const digest = (value) => crypto.createHash('sha256').update(value).digest('hex');
export const randomToken = () => crypto.randomUUID();
export const nowIso = (now = Date.now()) => new Date(now).toISOString();

export function safeChild(root, relative) {
  if (typeof relative !== 'string' || !relative || path.isAbsolute(relative) || relative.includes('\0')) {
    throw Object.assign(new Error('Invalid relative path'), { code: 'INVALID_PATH' });
  }
  const resolvedRoot = path.resolve(root);
  const result = path.resolve(resolvedRoot, relative);
  const rel = path.relative(resolvedRoot, result);
  if (rel === '' || rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) {
    throw Object.assign(new Error('Path escapes its data directory'), { code: 'INVALID_PATH' });
  }
  return result;
}

export async function ensurePrivateDir(directory) {
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const stat = await fs.lstat(directory);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw Object.assign(new Error('Data directory must be a real directory, not a link'), { code: 'UNSAFE_DIRECTORY' });
  }
  await fs.chmod(directory, 0o700).catch(() => {});
  return directory;
}

/** Write JSON through a same-directory temporary file, fsync, then rename. */
export async function atomicWriteJson(filename, value, { mode = 0o600 } = {}) {
  const directory = path.dirname(filename);
  await ensurePrivateDir(directory);
  const temporary = path.join(directory, `.${path.basename(filename)}.${randomToken()}.tmp`);
  let handle;
  try {
    handle = await fs.open(temporary, 'wx', mode);
    await handle.writeFile(JSON.stringify(value, null, 2) + '\n', 'utf8');
    await handle.sync();
    await handle.close();
    handle = null;
    await fs.rename(temporary, filename);
    await fs.chmod(filename, mode).catch(() => {});
    // Persist the directory entry too; a crash may leave the rename unflushed otherwise.
    try {
      const dir = await fs.open(directory, 'r');
      try { await dir.sync(); } finally { await dir.close(); }
    } catch { /* Some filesystems refuse directory fsync; the rename is still atomic. */ }
  } finally {
    if (handle) await handle.close().catch(() => {});
    await fs.rm(temporary, { force: true }).catch(() => {});
  }
}

export async function readJson(filename, fallback) {
  try {
    return JSON.parse(await fs.readFile(filename, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT' && fallback !== undefined) return fallback;
    throw error;
  }
}

/** Read one JSON file and require it to be a plain object. */
export async function readObject(filename) {
  const value = JSON.parse(await fs.readFile(filename, 'utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw Object.assign(new Error(`Expected an object in ${path.basename(filename)}`), { code: 'INVALID_STATE' });
  }
  return value;
}

export async function sha256File(filename) {
  const hash = crypto.createHash('sha256');
  let bytes = 0;
  for await (const chunk of (await import('node:fs')).createReadStream(filename)) {
    hash.update(chunk);
    bytes += chunk.length;
  }
  return { sha256: hash.digest('hex'), bytes };
}

export async function fileSize(filename) {
  return (await fs.stat(filename)).size;
}

export async function diskFreeBytes(directory) {
  const stat = await fs.statfs(directory);
  return Number(stat.bavail) * Number(stat.bsize);
}

export async function pathExists(filename) {
  try { await fs.lstat(filename); return true; } catch (error) { if (error.code === 'ENOENT') return false; throw error; }
}

/**
 * A short-lived advisory lock for read-modify-write of one job file. Stage durability is handled
 * by leases; this lock only prevents two simultaneous completions from losing an update.
 * A lock older than `staleMs` is moved aside (not deleted) so a crashed writer cannot wedge the
 * queue forever. The caller still re-reads under the lock.
 */
export async function withFileLock(directory, name, task, { timeoutMs = 5000, staleMs = 30000, now = Date.now } = {}) {
  await ensurePrivateDir(directory);
  const filename = safeChild(directory, name);
  const token = randomToken();
  const deadline = now() + timeoutMs;
  for (;;) {
    try {
      const handle = await fs.open(filename, 'wx', 0o600);
      try {
        await handle.writeFile(JSON.stringify({ pid: process.pid, token, at: nowIso(now()) }), 'utf8');
        await handle.sync();
      } finally { await handle.close(); }
      break;
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let current = null;
      let readable = true;
      try { current = await readJson(filename, null); } catch { readable = false; }
      const stat = await fs.stat(filename).catch(() => null);
      // An unreadable but fresh lock may be mid-write: wait rather than stealing it.
      const age = readable && current && Number.isFinite(Date.parse(current.at))
        ? now() - Date.parse(current.at)
        : stat ? now() - stat.mtimeMs : Infinity;
      if (age > staleMs) {
        // Rename is atomic: exactly one contender can move the stale lock aside.
        const stale = `${filename}.stale-${randomToken()}`;
        try { await fs.rename(filename, stale); } catch (renameError) { if (renameError.code === 'ENOENT') continue; throw renameError; }
        await fs.rm(stale, { force: true }).catch(() => {});
        continue;
      }
      if (now() >= deadline) throw Object.assign(new Error(`Timed out waiting for ${name}`), { code: 'LOCK_TIMEOUT' });
      await sleep(15 + Math.floor(Math.random() * 20));
    }
  }
  try {
    return await task();
  } finally {
    try {
      const current = await readJson(filename, null);
      if (current?.token === token) await fs.unlink(filename);
    } catch { /* A replacement lock is never removed. */ }
  }
}
