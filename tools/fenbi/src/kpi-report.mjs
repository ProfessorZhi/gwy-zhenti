#!/usr/bin/env node
/**
 * Daily single KPI, read-only:
 *   verified source-backed papers on main / unique in-scope catalog papers.
 * The numerator needs the current main SHA, sourceId, subject and an independent QA
 * binding per paper. If the catalog lacks sourceId the KPI is UNKNOWN, never inferred
 * from historical promoted counts or PR totals.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { computeKpi, loadPolicy } from './policy.mjs';

export async function readJsonLines (file) {
  const text = await fs.readFile(file, 'utf8');
  return text.split(/\r?\n/u).filter(Boolean).map((line, i) => {
    try { return JSON.parse(line); } catch { throw Object.assign(new Error('invalid-jsonl:' + (i + 1)), {code: 'invalid-jsonl'}); }
  });
}

export async function runKpi ({manifestPath, papersPath, mainSha, policyPath} = {}) {
  if (!manifestPath || !papersPath) return {ok: false, reason: 'usage: --manifest FILE --papers FILE --main-sha SHA'};
  let catalog, papers;
  try { catalog = await readJsonLines(manifestPath); } catch (e) { return {ok: false, reason: 'manifest-unreadable:' + (e.code || e.message)}; }
  try { papers = JSON.parse(await fs.readFile(papersPath, 'utf8')); } catch (e) { return {ok: false, reason: 'papers-unreadable:' + (e.code || e.message)}; }
  let policy;
  try { policy = await loadPolicy(policyPath); } catch (e) { return {ok: false, reason: e.code || e.message}; }
  const result = computeKpi({mainSha, papers: Array.isArray(papers) ? papers : [], catalog, policy});
  return {ok: true, kpi: result};
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  const args = process.argv.slice(2), opts = {};
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    if (['--manifest', '--papers', '--main-sha', '--policy'].includes(key)) {
      const value = args[++i];
      if (!value) { console.error('missing-value:' + key); process.exit(1); }
      opts[key === '--main-sha' ? 'mainSha' : key.slice(2) + 'Path'] = value;
    } else { console.error('unknown-option:' + key); process.exit(1); }
  }
  runKpi({
    manifestPath: opts.manifestPath, papersPath: opts.papersPath, mainSha: opts.mainSha,
    policyPath: opts.policyPath
  }).then(r => { console.log(JSON.stringify(r)); if (!r.ok) process.exitCode = 3; })
    .catch(e => { console.error(e.code || e.message); process.exitCode = 1; });
}
