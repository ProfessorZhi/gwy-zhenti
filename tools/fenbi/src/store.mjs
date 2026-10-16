import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { safeChild } from './config.mjs';

export const digest = value => crypto.createHash('sha256').update(typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value)).digest('hex');
export const jobKey = job => digest({ id: job.identity.id, subject: job.identity.subject, url: job.url }).slice(0, 24);

export async function writeJson(filename, value) {
  await fs.mkdir(path.dirname(filename), { recursive: true, mode: 0o700 });
  const temporary = `${filename}.${crypto.randomUUID()}.tmp`;
  try {
    await fs.writeFile(temporary, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
    await fs.rename(temporary, filename);
  } finally { await fs.rm(temporary, { force: true }); }
}

export async function readJson(filename, fallback) {
  try { return JSON.parse(await fs.readFile(filename, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT' && fallback !== undefined) return fallback; throw error; }
}

export async function acquireLock(directory, name = '.capture.lock') {
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const filename = safeChild(directory, name);
  let handle;
  try { handle = await fs.open(filename, 'wx', 0o600); }
  catch (error) { if (error.code === 'EEXIST') throw new Error('Another capture owns this work directory. Close it or inspect the existing lock; it is never removed automatically.'); throw error; }
  const marker = crypto.randomUUID();
  await handle.writeFile(JSON.stringify({ pid: process.pid, marker, startedAt: new Date().toISOString() }));
  await handle.close();
  return async () => {
    const current = await readJson(filename, null);
    if (current?.marker === marker) await fs.unlink(filename);
  };
}

export async function resumeBundle(workDir, job, configFingerprint, validate) {
  const bundleDir = safeChild(workDir, `papers/${jobKey(job)}`);
  const state = await readJson(path.join(bundleDir, 'checkpoint.json'), null);
  if (!state || state.status !== 'complete' || state.configFingerprint !== configFingerprint || state.jobFingerprint !== digest(job)) return null;
  if (typeof state.documentFile !== 'string' || !state.documentFile || path.basename(state.documentFile) !== state.documentFile) return null;
  const filename = path.join(bundleDir, state.documentFile);
  // documentFile is written by this tool, but still treat checkpoints as untrusted input.
  if (!filename.startsWith(bundleDir + path.sep) || path.basename(state.documentFile) !== state.documentFile) return null;
  const bytes = await fs.readFile(filename).catch(() => null);
  if (!bytes || digest(bytes) !== state.sha256) return null;
  let document;
  try { document = JSON.parse(bytes.toString('utf8')); } catch { return null; }
  const verdict = await validate(document, { assetRoot: path.join(bundleDir, 'assets') });
  return verdict.status === 'complete' ? { document, verdict, bundleDir } : null;
}
