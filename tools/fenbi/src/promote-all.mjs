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
import { better, identityKey, readManifestIdentities } from './identity.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');

async function readReceipt(dir) {
  try { return JSON.parse(await fs.readFile(path.join(dir, 'receipt.json'), 'utf8')); } catch { return null; }
}

// Several Fenbi sources can map to one paper path (re-uploads, recall versions). Promote only the
// most complete one; otherwise each cycle would replace the paper with the other version.
// `better`/`identityKey`/`readManifestIdentities` live in identity.mjs so the board agrees.

/** Manifest paths sharing this receipt's identity. Resolution requires exactly one. */
const resolveTargetPaths = (receipt, manifest) => manifest.get(identityKey(receipt)) || [];

const questionHeadingCount = text => [...String(text).matchAll(/^#{2,3}\s+第\s*\d+\s*题/gmu)].length;

export async function listPending(candidateRoot, repoRoot) {
  const entries = await fs.readdir(candidateRoot, { withFileTypes: true }).catch(() => []);
  const byPath = new Map();
  for (const entry of entries.filter(e => e.isDirectory()).map(e => e.name).sort()) {
    const dir = path.join(candidateRoot, entry), receipt = await readReceipt(dir);
    if (!receipt || receipt.grade !== 'A' || !receipt.path) continue;
    const list = byPath.get(receipt.path) || [];
    list.push({ entry, dir, receipt });
    byPath.set(receipt.path, list);
  }
  const pending = [], already = [], duplicates = [];
  for (const [rel, list] of byPath) {
    const winner = list.reduce((w, c) => better(c.receipt, w.receipt) ? c : w);
    for (const c of list) if (c !== winner) duplicates.push(c.entry);
    const current = await fs.readFile(path.join(repoRoot, rel)).catch(() => null);
    if (current && sha(current) === winner.receipt.markdownSha256) already.push(winner.entry);
    else pending.push({ dir: winner.dir, receipt: winner.receipt });
  }
  return { pending, already, duplicates };
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

export async function promoteAll({ candidateRoot, repoRoot, rightsFile, allowReplace = false, apply = false, onlySourceIds = null }) {
  const manifest = await readManifestIdentities(repoRoot);
  const only = onlySourceIds ? new Set(onlySourceIds.map(String)) : null;
  const entries = await fs.readdir(candidateRoot, { withFileTypes: true }).catch(() => []);
  const summary = { pending: 0, alreadyPromoted: 0, duplicateSources: 0, preflightOk: 0,
    promoted: 0, replaced: 0, identityResolved: 0, blocked: {} };
  const block = (reason, p) => (summary.blocked[reason] ||= []).push(p);

  // 1. Resolve every grade-A candidate to a concrete target path.
  const resolved = [];
  for (const name of entries.filter(e => e.isDirectory()).map(e => e.name).sort()) {
    const dir = path.join(candidateRoot, name), receipt = await readReceipt(dir);
    if (!receipt || receipt.grade !== 'A' || !receipt.path) continue;
    if (only && !only.has(String(receipt.sourceId))) continue;
    const direct = await fs.readFile(path.join(repoRoot, receipt.path)).catch(() => null);
    let targetPath = receipt.path, prior = direct, mode = 'direct';
    if (!direct) {
      const paths = resolveTargetPaths(receipt, manifest);
      if (!paths.length) {
        // No manifest row for this identity: a genuinely new paper. Keep its own path.
        mode = 'new';
      } else if (paths.length > 1) {
        block('identity-ambiguous-in-manifest', receipt.path); continue;
      } else {
        targetPath = paths[0];
        prior = await fs.readFile(path.join(repoRoot, targetPath)).catch(() => null);
        // A manifest row whose file is absent is a repository inconsistency, not a target.
        if (!prior) { block('duplicate-identity-in-repository', receipt.path); continue; }
        mode = 'identity-resolved';
      }
    }
    resolved.push({ name, dir, receipt, targetPath, prior, mode });
  }

  // 2. Several sources for one paper: keep only the most complete.
  const byTarget = new Map();
  for (const item of resolved) {
    const list = byTarget.get(item.targetPath) || [];
    list.push(item); byTarget.set(item.targetPath, list);
  }
  const pending = [];
  for (const [targetPath, list] of byTarget) {
    const winner = list.reduce((w, c) => better(c.receipt, w.receipt) ? c : w);
    for (const c of list) if (c !== winner) { summary.duplicateSources++; }
    if (winner.mode === 'identity-resolved') summary.identityResolved++;
    // Already published if the target holds exactly this candidate's markdown.
    if (winner.prior && sha(winner.prior) === winner.receipt.markdownSha256) { summary.alreadyPromoted++; continue; }
    pending.push({ ...winner, targetPath });
  }
  pending.sort((a, b) => a.targetPath.localeCompare(b.targetPath, 'zh-CN'));
  summary.pending = pending.length;
  if (!pending.length) return summary;

  // 3. Preflight each pending target.
  const safe = [];
  const byIdentity = new Map(), byPath = new Map();
  for (const item of pending) {
    byIdentity.set(item.targetPath, (byIdentity.get(item.targetPath) || 0) + 1);
    byPath.set(item.receipt.path, (byPath.get(item.receipt.path) || 0) + 1);
  }
  for (const item of pending) {
    const { receipt } = item;
    let reason = null;
    if (!reason && item.prior) {
      // Fenbi must not shrink a paper — applies to direct and identity-resolved targets alike,
      // matching the guard PR #91 added on main.
      const existingCount = questionHeadingCount(item.prior.toString('utf8'));
      if (existingCount > (receipt.counts?.sourceQuestions ?? 0)) reason = 'fenbi-has-fewer-questions-than-existing';
    }
    if (!reason && item.mode === 'identity-resolved' && !allowReplace) {
      // Replacing a different-named file for the same paper is only allowed explicitly.
      reason = 'explicit-allow-replace-required';
    }
    if (!reason) {
      if (item.mode === 'identity-resolved') {
        // The real old bytes were read from the canonical path above; the receipt's own
        // oldSha256 is null precisely because its slug path never existed, so it is not
        // a staleness signal here. Re-check that the file has not moved since preflight.
        if (!item.prior) reason = 'canonical-target-disappeared';
      } else if (item.prior && !receipt.oldSha256) reason = 'existing-target-without-old-sha';
      else if (item.prior && receipt.oldSha256 && sha(item.prior) !== receipt.oldSha256) reason = 'repository-paper-changed-since-candidate';
      else if (!item.prior && receipt.oldSha256) reason = 'old-paper-not-found-in-integration-branch';
      if (!reason && (byPath.get(receipt.path) || 0) > 1) reason = 'duplicate-identity-in-batch';
    }
    if (reason) block(reason, receipt.path);
    else safe.push(item);
  }
  if (!safe.length) return summary;

  // 4. Publish. The resolved path and the real old hash are handed to promoteOne instead of
  //    mutating the receipt on disk, so a rerun of batch-ingest cannot resurrect the slug path.
  const rights = await effectiveRights(rightsFile, safe);
  try {
    for (const item of safe) {
      try {
        const override = item.mode === 'identity-resolved'
          ? { path: item.targetPath, oldSha256: sha(item.prior) }
          : undefined;
        await promoteOne({ candidateDir: item.dir, repoRoot, rightsFile: rights.file, receiptOverride: override },
          { apply, allowReplace });
        if (apply) {
          summary.promoted++;
          if (item.mode === 'identity-resolved') summary.replaced++;
          else if (item.prior) summary.replaced++;
        } else {
          summary.preflightOk++;
        }
      } catch (error) {
        const reason = error.code || error.message || 'error';
        block(reason, item.receipt.path);
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
