#!/usr/bin/env node
/**
 * CLI for the offline quality-repair workflow. Default OFF: refuses to run unless
 * QUALITY_REPAIR=1. Never performs network I/O; an optional provider module path is
 * accepted only for a caller-supplied authorized fetcher and is not used here.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { detectQualityGaps, buildRepairPlan, handoffCandidate } from './quality-repair.mjs';

const USAGE = 'usage: quality-repair-run.mjs --papers FILE --donors FILE --out DIR [--reviewed FILE] [--apply]';

async function readJson (file) {
  return JSON.parse(await fs.readFile(file, 'utf8'));
}

export async function runCli (argv = process.argv.slice(2), env = process.env) {
  if (env.QUALITY_REPAIR !== '1') return {ok: false, stage: 'disabled', reason: 'quality-repair-disabled'};
  const opts = {apply: false};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (key === '--apply') opts.apply = true;
    else if (['--papers', '--donors', '--out', '--reviewed', '--trusted-root'].includes(key)) {
      const value = argv[++i];
      if (!value) return {ok: false, stage: 'usage', reason: 'missing-value:' + key, usage: USAGE};
      opts[key.slice(2).replaceAll('-', '_')] = value;
    } else return {ok: false, stage: 'usage', reason: 'unknown-option:' + key, usage: USAGE};
  }
  if (!opts.papers || !opts.donors || !opts.out) return {ok: false, stage: 'usage', reason: 'missing-required', usage: USAGE};

  const papers = await readJson(opts.papers);
  const donors = await readJson(opts.donors);
  const reviewed = opts.reviewed ? await readJson(opts.reviewed) : [];
  const summaries = [];
  let eligible = 0;
  for (const paper of papers) {
    const gaps = detectQualityGaps(paper, {rightsStatus: paper.rightsStatus ?? 'unverified'});
    const result = await buildRepairPlan({target: paper, donors, reviewedPairs: reviewed, outDir: opts.out, apply: opts.apply, trustedRoot: opts.trusted_root ?? null});
    if (result.eligible) eligible += result.eligible;
    summaries.push({
      sourceId: paper.sourceId, path: paper.path, gaps: gaps.kinds.length, gapQuestions: gaps.gaps.length,
      eligible: result.eligible ?? 0, ok: Boolean(result.ok), qc: result.qc?.verdict ?? 'none',
      review: (result.reviewQueue ?? []).map(r => ({number: r.number, reason: r.reason})),
      handoff: handoffCandidate(result)
    });
  }
  return {ok: eligible > 0, stage: opts.apply ? 'applied' : 'dry-run', eligible, papers: summaries.length, summaries};
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  runCli().then(r => {
    console.log(JSON.stringify(r));
    if (!r.ok && r.stage !== 'disabled') process.exitCode = 3;
  }).catch(e => { console.error(e.code || e.message); process.exitCode = 1; });
}
