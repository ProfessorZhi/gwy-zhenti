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

// Several Fenbi sources can map to one paper path (re-uploads, recall versions). Promote only the
// most complete one; otherwise each cycle would replace the paper with the other version.
const rank = r => [r.answerNumbers?.length ?? 0, r.counts?.sourceQuestions ?? 0, Number(r.sourceId) || 0];
const better = (a, b) => { const x = rank(a), y = rank(b); for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] > y[i]; return false; };

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

/**
 * Resolve a receipt's target path.
 *
 * A batch-ingest receipt may name a slug path (行测-tongkao.md) that does not exist while the
 * SAME paper is already in the manifest under its canonical name (行测-统考.md). Resolving that
 * is safe only when the manifest identity matches EXACTLY ONE path; zero or several matches
 * stay blocked rather than guessed. The resolved path is what gets published, so the next
 * ingest/promote cycle sees a stable target instead of churning between two names.
 */
function resolveTargetPaths(receipt, manifest) {
  return manifest.get(identityKey(receipt)) || [];
}

const questionHeadingCount = text => [...String(text).matchAll(/^#{2,3}\s+第\s*\d+\s*题/gmu)].length;

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
    if (item.mode === 'identity-resolved') {
      // Replacing a different-named file for the same paper is only allowed explicitly.
      if (!allowReplace) reason = 'explicit-allow-replace-required';
      else {
        // Fenbi must not shrink a paper: same guard as PR #91 on main.
        const existingCount = questionHeadingCount(item.prior.toString('utf8'));
        if (existingCount > (receipt.counts?.sourceQuestions ?? 0)) reason = 'fenbi-has-fewer-questions-than-existing';
      }
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
