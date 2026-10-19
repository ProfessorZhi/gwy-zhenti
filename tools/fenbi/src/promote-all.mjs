#!/usr/bin/env node
/**
 * Promote every grade-A batch-ingest candidate that is not yet in the integration worktree.
 * Wraps promoteOne; one failure never stops the rest. Prints one JSON summary line.
 *
 * Rights: the rights file is the user's explicit approval. When it carries
 * `coverAllCapturedSources: true`, the user has approved every captured Fenbi source, so the
 * source list is extended to the candidates in this run; otherwise only listed sourceIds pass.
 */
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { promoteOne } from './batch-promote.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');

async function readReceipt(dir) {
  try { return JSON.parse(await fs.readFile(path.join(dir, 'receipt.json'), 'utf8')); } catch { return null; }
}

export async function listPending(candidateRoot, repoRoot) {
  const entries = await fs.readdir(candidateRoot, { withFileTypes: true }).catch(() => []);
  const pending = [], already = [];
  for (const entry of entries.filter(e => e.isDirectory()).map(e => e.name).sort()) {
    const dir = path.join(candidateRoot, entry), receipt = await readReceipt(dir);
    if (!receipt || receipt.grade !== 'A') continue;
    const current = await fs.readFile(path.join(repoRoot, receipt.path)).catch(() => null);
    if (current && sha(current) === receipt.markdownSha256) already.push(entry);
    else pending.push({ dir, receipt });
  }
  return { pending, already };
}

async function effectiveRights(rightsFile, pending) {
  const proof = JSON.parse(await fs.readFile(rightsFile, 'utf8'));
  if (proof.coverAllCapturedSources !== true) return { file: rightsFile, cleanup: async () => {} };
  const ids = new Set((proof.sourceIds || []).map(String));
  for (const { receipt } of pending) ids.add(String(receipt.sourceId));
  const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'fenbi-rights-'));
  const file = path.join(tmp, 'rights.json');
  await fs.writeFile(file, JSON.stringify({ ...proof, sourceIds: [...ids] }), { mode: 0o600 });
  return { file, cleanup: () => fs.rm(tmp, { recursive: true, force: true }) };
}

const normVariant = v => {
  const s = String(v ?? '').trim().toLowerCase();
  const map = { tongkao: '统考', '统考': '统考', a: 'a', b: 'b', c: 'c', 'a类': 'a', 'b类': 'b', 'c类': 'c',
    county: '县级', '县级': '县级', township: '乡镇', '乡镇': '乡镇', dishiji: '地市级', '地市级': '地市级',
    fushengji: '副省级', '副省级': '副省级', xingzheng: '行政执法', '行政执法': '行政执法' };
  return map[s] || s.replace(/[类卷]/g, '');
};
const normSubject = s => ({ 行测: 'xingce', xingce: 'xingce', 申论: 'shenlun', shenlun: 'shenlun' }[String(s ?? '').trim()] || String(s ?? '').trim());
const identityKey = r => [r.area, String(r.year), normSubject(r.subject ?? r.paper_type), normVariant(r.variant ?? r.paper_type)].join('|');

async function readManifestIdentities(repoRoot) {
  const text = await fs.readFile(path.join(repoRoot, 'catalog/manifest.jsonl'), 'utf8').catch(() => '');
  const map = new Map();
  for (const line of text.split(/\r?\n/u).filter(Boolean)) {
    try { const row = JSON.parse(line); const key = identityKey(row); if (!map.has(key)) map.set(key, []); map.get(key).push(row.path); } catch {}
  }
  return map;
}

export async function promoteAll({ candidateRoot, repoRoot, rightsFile, allowReplace = false, apply = false, onlySourceIds = null }) {
  const { pending: allPending, already: allAlready } = await listPending(candidateRoot, repoRoot);
  const only = onlySourceIds ? new Set(onlySourceIds.map(String)) : null;
  const pending = only ? allPending.filter(({ receipt }) => only.has(String(receipt.sourceId))) : allPending;
  const alreadyReceipts = await Promise.all(allAlready.map(async (name) => ({ name, receipt: await readReceipt(path.join(candidateRoot, name)) })));
  const already = only ? alreadyReceipts.filter(({ receipt }) => receipt && only.has(String(receipt.sourceId))) : alreadyReceipts;
  const summary = { pending: pending.length, alreadyPromoted: already.length, preflightOk: 0, promoted: 0, replaced: 0, blocked: {} };
  if (!pending.length) return summary;
  const manifest = await readManifestIdentities(repoRoot);
  const byIdentity = new Map(), byPath = new Map();
  for (const item of pending) {
    const key = identityKey(item.receipt);
    if (!byIdentity.has(key)) byIdentity.set(key, []); byIdentity.get(key).push(item);
    if (!byPath.has(item.receipt.path)) byPath.set(item.receipt.path, []); byPath.get(item.receipt.path).push(item);
  }
  const safe = [];
  for (const item of pending) {
    const { receipt } = item;
    const current = await fs.readFile(path.join(repoRoot, receipt.path)).catch(() => null);
    const existingPaths = manifest.get(identityKey(receipt)) || [];
    let reason = null;
    if (current) {
      if (!receipt.oldSha256) reason = 'existing-target-without-old-sha';
      else if (sha(current) !== receipt.oldSha256) reason = 'repository-paper-changed-since-candidate';
    } else if (receipt.oldSha256) {
      reason = 'old-paper-not-found-in-integration-branch';
    } else if (existingPaths.length) {
      reason = 'duplicate-identity-in-repository';
    } else if ((byIdentity.get(identityKey(receipt)) || []).length > 1 || (byPath.get(receipt.path) || []).length > 1) {
      reason = 'duplicate-identity-in-batch';
    }
    if (reason) (summary.blocked[reason] ||= []).push(receipt.path);
    else safe.push(item);
  }
  if (!safe.length) return summary;
  const rights = await effectiveRights(rightsFile, safe);
  try {
    for (const { dir, receipt } of safe) {
      try {
        await promoteOne({ candidateDir: dir, repoRoot, rightsFile: rights.file }, { apply, allowReplace });
        if (apply) {
          summary.promoted++;
          if (receipt.oldSha256) summary.replaced++;
        } else {
          summary.preflightOk++;
        }
      } catch (error) {
        const reason = error.code || error.message || 'error';
        (summary.blocked[reason] ||= []).push(receipt.path);
      }
    }
  } finally { await rights.cleanup(); }
  return summary;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), opts = { apply: false, allowReplace: false, onlySourceIds: null };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--apply') opts.apply = true;
    else if (a === '--allow-replace') opts.allowReplace = true;
    else if (['--candidate-root', '--repo-root', '--rights-file'].includes(a)) opts[a.slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = args[++i];
    else if (a === '--only-source-ids') opts.onlySourceIds = args[++i].split(',').map(x => x.trim()).filter(Boolean);
    else throw Error('unknown-option:' + a);
  }
  if (!opts.candidateRoot || !opts.repoRoot || !opts.rightsFile) throw Error('usage: --candidate-root DIR --repo-root DIR --rights-file FILE [--apply] [--allow-replace]');
  promoteAll(opts).then(s => console.log(JSON.stringify(s))).catch(e => { console.error(e.code || e.message); process.exitCode = 1; });
}
