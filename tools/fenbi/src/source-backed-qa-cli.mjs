#!/usr/bin/env node
/**
 * CLI for the source-backed per-question QA comparator.
 *
 * Compares a local source cache (document.json per paper) against an archive markdown
 * tree pinned at a commit, and writes metadata-only receipts. Offline and read-only.
 *
 *   node src/source-backed-qa-cli.mjs \
 *     --papers DIR --pr-repo DIR --pr-head SHA --ids id1,id2 [--manifest REL] [--out DIR]
 *
 * Nothing is written outside --out, and the receipt carries ids, question numbers,
 * counts, sha256 values and reason codes only. No question text, option text, answer
 * letter, explanation, url or image bytes.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { comparePaper, findSourceDir, selectPrPath, gitShow } from './source-backed-qa.mjs';

const USAGE = 'usage: source-backed-qa-cli.mjs --papers DIR --pr-repo DIR --pr-head SHA --ids id1,id2 [--manifest catalog/manifest.jsonl] [--out DIR] [--quiet]';

function parse (argv) {
  const o = { manifest: 'catalog/manifest.jsonl', out: 'out', quiet: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--quiet') { o.quiet = true; continue; }
    if (!['--papers', '--pr-repo', '--pr-head', '--ids', '--manifest', '--out'].includes(k)) return { error: 'unknown-option:' + k };
    const v = argv[++i];
    if (!v) return { error: 'missing-value:' + k };
    o[k.slice(2).replaceAll('-', '_')] = v;
  }
  for (const req of ['papers', 'pr_repo', 'pr_head']) if (!o[req]) return { error: 'missing-' + req };
  if (!/^[0-9a-f]{40}$/u.test(o.pr_head)) return { error: 'pr-head-not-sha1' };
  o.ids = String(o.ids ?? '').split(',').map((x) => x.trim()).filter(Boolean);
  if (o.ids.length === 0) return { error: 'missing-ids' };
  return o;
}

const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

function main (argv) {
  const o = parse(argv);
  if (o.error) return { ok: false, stage: 'usage', reason: o.error, usage: USAGE };

  let manifest;
  try {
    manifest = gitShow(o.pr_repo, o.pr_head, o.manifest).trim().split('\n').filter(Boolean).map(JSON.parse);
  } catch { return { ok: false, stage: 'input', reason: 'manifest-unreadable' }; }

  fs.mkdirSync(o.out, { recursive: true, mode: 0o700 });
  const rows = [], revisions = [], skipped = [];
  for (const sid of o.ids) {
    const t0 = process.hrtime.bigint();
    const dir = findSourceDir(o.papers, sid);
    if (!dir) { skipped.push({ sourceId: sid, reason: 'NO_SOURCE_CACHE' }); continue; }
    const doc = JSON.parse(fs.readFileSync(path.join(dir, 'document.json'), 'utf8'));
    const sel = selectPrPath(manifest, doc.identity ?? {});
    if (!sel.ok) { skipped.push({ sourceId: sid, reason: sel.reason, candidates: sel.candidates }); continue; }
    let md;
    try { md = gitShow(o.pr_repo, o.pr_head, sel.path); } catch { skipped.push({ sourceId: sid, reason: 'PR_BLOB_UNREADABLE' }); continue; }
    const r = comparePaper({ sourceDir: dir, prMarkdown: md, prPath: sel.path, sourceId: sid });
    r.elapsedMs = Number(process.hrtime.bigint() - t0) / 1e6;
    rows.push(r);
    revisions.push({ sourceId: sid, prPath: sel.path, sourceDocSha12: r.sourceDocSha12,
      prBlobSha12: r.prBlobSha12, revision: r.revision, at: new Date().toISOString() });
    fs.writeFileSync(path.join(o.out, `qa-${sid}.json`), JSON.stringify(r, null, 1) + '\n', { mode: 0o600 });
  }

  const sum = (k) => rows.reduce((a, r) => a + (Array.isArray(r[k]) ? r[k].length : 0), 0);
  const receipt = {
    schemaVersion: 1, metadataOnly: true, generatedAt: new Date().toISOString(), prHead: o.pr_head,
    requested: o.ids.length, completed: rows.length, skipped,
    totals: { sourceQ: rows.reduce((a, r) => a + r.sourceQ, 0), prQ: rows.reduce((a, r) => a + r.prQ, 0),
      sourceStubQ: rows.reduce((a, r) => a + r.sourceStubQ, 0), strictExactMatches: sum('strictMatches'),
      prefixCandidates: sum('prefixCandidates'), prefixRejected: sum('prefixRejected'),
      optionOrderChanged: sum('optionOrderChanged'), stemSameOptionDiff: sum('stemSameOptionDiff'),
      answerSameStrict: sum('answerSameStrict'), answerConflictStrict: sum('answerConflictStrict'),
      answerUnknownStrict: sum('answerUnknownStrict'), answerSameCandidate: sum('answerSameCandidate'),
      answerConflictCandidate: sum('answerConflictCandidate'), answerUnknownCandidate: sum('answerUnknownCandidate'),
      explanationSame: sum('explanationSame'), explanationDiff: sum('explanationDiff'),
      explanationMissing: sum('explanationMissing'), unmatchedSource: sum('unmatchedSource'),
      unmatchedPr: sum('unmatchedPr'), stubContentMatched: sum('stubContentMatched'),
      partitionConsistent: rows.every((r) => r.partitionConsistent), partitionSum: rows.reduce((a, r) => a + r.partitionSum, 0),
      verdicts: rows.reduce((m, r) => ((m[r.qaVerdict] = (m[r.qaVerdict] ?? 0) + 1), m), {}) },
    coverage: { areas: [...new Set(rows.map((r) => r.area))],
      schemaA: rows.filter((r) => r.prHasAnswerSection).length,
      schemaB: rows.filter((r) => !r.prHasAnswerSection).length },
    papers: rows.map((r) => ({ sourceId: r.sourceId, area: r.area, year: r.year, variant: r.variant, prPath: r.prPath,
      sourceQ: r.sourceQ, prQ: r.prQ, sourceStubQ: r.sourceStubQ, strict: r.strictMatchCount,
      prefix: r.prefixCandidateCount, prefixRejected: r.prefixRejected.length, stemDiff: r.stemSameOptionDiff.length,
      order: r.optionOrderChanged.length, ansSameS: r.answerSameStrict.length, ansConfS: r.answerConflictStrict.length,
      ansUnkS: r.answerUnknownStrict.length, ansSameC: r.answerSameCandidate.length,
      ansConfC: r.answerConflictCandidate.length, ansUnkC: r.answerUnknownCandidate.length,
      expSame: r.explanationSame.length, expDiff: r.explanationDiff.length, expMissing: r.explanationMissing.length,
      unmatchedS: r.unmatchedSource.length, unmatchedP: r.unmatchedPr.length, stubContentMatched: r.stubContentMatched.length,
      partition: r.partitionSum, partitionOk: r.partitionConsistent, coverageEligible: r.coverageClaimEligible,
      verdict: r.qaVerdict, imageSha: r.imageShaEvidence, rights: r.rightsStatus, elapsedMs: +r.elapsedMs.toFixed(1),
      sourceDocSha12: r.sourceDocSha12, prBlobSha12: r.prBlobSha12 })),
    safety: { network: false, browser: false, sourceWrites: 0, productionWrites: 0, publisherTouched: false,
      githubWrites: 0, prMainUntouched: true }
  };
  fs.writeFileSync(path.join(o.out, 'receipts.jsonl'), rows.map((r) => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : ''), { mode: 0o600 });
  fs.writeFileSync(path.join(o.out, 'source-revisions.jsonl'), revisions.map((r) => JSON.stringify(r)).join('\n') + (revisions.length ? '\n' : ''), { mode: 0o600 });
  fs.writeFileSync(path.join(o.out, 'run-receipt.json'), JSON.stringify(receipt, null, 1) + '\n', { mode: 0o600 });

  if (!o.quiet) console.log(JSON.stringify({ completed: receipt.completed, skipped: receipt.skipped, totals: receipt.totals,
    wallMs: +rows.reduce((a, r) => a + r.elapsedMs, 0).toFixed(0) }));
  return { ok: true, receipt };
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  const r = main(process.argv.slice(2));
  if (!r.ok) { console.error(JSON.stringify(r)); process.exitCode = 3; }
}
