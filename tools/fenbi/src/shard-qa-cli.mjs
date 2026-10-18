#!/usr/bin/env node
/**
 * Run the shard QA over a bounded set of papers, from a credential-free observation handoff plus
 * the repository markdown. Read-only: it only runs `git show` on a ref and reads one JSON file.
 *
 *   node src/shard-qa-cli.mjs --handoff FILE --ref REF --out FILE \
 *        [--paper 国考/2026/行测-副省级.md]... [--claims FILE]
 *
 * The report contains counts, numbers, statuses and reasons only — never question text, image
 * bytes, hashes or URLs. Exit: 0 = every paper structurally ok and no contradicting claim,
 * 2 = review/blocked item, 1 = usage or parse error.
 */
import fs from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import path from 'node:path';
import { buildShardReport, validateShardReport, shardKey } from './shard-qa.mjs';

const normaliseVariant = (value) => String(value ?? '').normalize('NFKC').replace(/[\s()（）]/gu, '').replace(/[类卷]/gu, '');

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../..');
const HELP = `Shard QA from a credential-free handoff (metadata-only report)
  node src/shard-qa-cli.mjs --handoff FILE --ref REF --out FILE [--paper PATH]... [--claims FILE]`;

/** Derive identity from the repository path: 国考/2026/行测-副省级.md */
export function identityFromPath(paperPath) {
  const parts = String(paperPath).split('/');
  const [area, year, file] = [parts[0], parts[1], parts[parts.length - 1]];
  const match = /^(行测|申论)-(.+)\.md$/u.exec(file ?? '');
  return { area, year: Number(year),
    subject: match?.[1] === '申论' ? 'shenlun' : match?.[1] === '行测' ? 'xingce' : null,
    variant: match?.[2] ?? null };
}

function readBlob(ref, paperPath) {
  return execFileSync('git', ['show', `${ref}:${paperPath}`], { cwd: REPO, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
}

async function main() {
  const { values } = parseArgs({ options: {
    handoff: { type: 'string' }, ref: { type: 'string' }, out: { type: 'string' },
    paper: { type: 'string', multiple: true }, claims: { type: 'string' }, help: { type: 'boolean', default: false },
  } });
  if (values.help) { console.log(HELP); return 0; }
  if (!values.handoff || !values.ref || !values.out || !values.paper?.length) { console.error(HELP); return 1; }

  let handoff, claims = [];
  try { handoff = JSON.parse(await fs.readFile(values.handoff, 'utf8')); }
  catch (error) { console.error(`Could not read the handoff (${error.code ?? error.name}).`); return 1; }
  if (values.claims) {
    try { claims = JSON.parse(await fs.readFile(values.claims, 'utf8')); }
    catch (error) { console.error(`Could not read the claims file (${error.code ?? error.name}).`); return 1; }
  }

  const papers = [];
  for (const paperPath of values.paper) {
    let markdown;
    try { markdown = readBlob(values.ref, paperPath); }
    catch { console.error(`Could not read ${paperPath} at ${values.ref.slice(0, 12)}.`); return 1; }
    const identity = identityFromPath(paperPath);
    // Match the handoff observation by identity, never by position or by a guessed id.
    const observation = (handoff.observations ?? []).find((item) => String(item.year) === String(identity.year)
      && String(item.area) === identity.area && String(item.subject) === identity.subject
      && normaliseVariant(item.variant) === normaliseVariant(identity.variant));
    const sourceId = observation?.paperSourceId ?? null;
    papers.push({ sourceId, label: identity.variant, path: paperPath, identity, markdown });
  }

  let report;
  try { report = buildShardReport({ handoff, papers, claims }); }
  catch (error) { console.error(`Shard QA failed (${error.message}).`); return 1; }
  const check = validateShardReport(report);
  if (!check.ok) { console.error(`Report contract violated: ${check.problems.slice(0, 5).join('; ')}`); return 1; }
  await fs.writeFile(values.out, `${JSON.stringify(report, null, 2)}\n`, { flag: 'wx' }).catch((error) => {
    if (error.code === 'EEXIST') throw new Error('refusing to overwrite an existing report; choose a new path');
    throw error;
  });

  console.log(JSON.stringify({ out: values.out, shard: shardKey(papers.map((paper) => paper.path)),
    counts: report.counts, blockedHandoffOwners: report.blockedHandoffOwners,
    papers: report.papers.map((row) => ({ sourceId: row.sourceId, status: row.status, counts: row.counts, conflicts: row.conflicts })) }, null, 2));
  return report.counts.needsReview > 0 || report.counts.blocked > 0 ? 2 : 0;
}

main().then((code) => { process.exitCode = code; }).catch((error) => {
  console.error(`shard-qa failed (${error.code ?? error.name}).`);
  process.exitCode = 1;
});
