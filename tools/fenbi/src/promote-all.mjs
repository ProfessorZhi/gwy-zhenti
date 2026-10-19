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

export async function promoteAll({ candidateRoot, repoRoot, rightsFile, allowReplace = false, apply = false }) {
  const { pending, already, duplicates } = await listPending(candidateRoot, repoRoot);
  const summary = { pending: pending.length, alreadyPromoted: already.length, duplicateSources: duplicates.length,
    promoted: 0, replaced: 0, blocked: {} };
  if (!pending.length) return summary;
  const rights = await effectiveRights(rightsFile, pending);
  try {
    for (const { dir, receipt } of pending) {
      try {
        await promoteOne({ candidateDir: dir, repoRoot, rightsFile: rights.file }, { apply, allowReplace });
        summary.promoted++;
        if (receipt.oldSha256) summary.replaced++;
      } catch (error) {
        const reason = error.code || error.message || 'error';
        (summary.blocked[reason] ||= []).push(receipt.path);
      }
    }
  } finally { await rights.cleanup(); }
  return summary;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), opts = { apply: false, allowReplace: false };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--apply') opts.apply = true;
    else if (a === '--allow-replace') opts.allowReplace = true;
    else if (['--candidate-root', '--repo-root', '--rights-file'].includes(a)) opts[a.slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = args[++i];
    else throw Error('unknown-option:' + a);
  }
  if (!opts.candidateRoot || !opts.repoRoot || !opts.rightsFile) throw Error('usage: --candidate-root DIR --repo-root DIR --rights-file FILE [--apply] [--allow-replace]');
  promoteAll(opts).then(s => console.log(JSON.stringify(s))).catch(e => { console.error(e.code || e.message); process.exitCode = 1; });
}
