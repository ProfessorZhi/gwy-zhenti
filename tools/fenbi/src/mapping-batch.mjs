#!/usr/bin/env node
/**
 * Bounded incremental validation CLI. One run, one batch, one metadata receipt.
 *
 *   node src/mapping-batch.mjs --input batch.json --out receipt.json
 *        [--max-papers 10] [--max-questions 100] [--gate-module ./my-gate.mjs]
 *
 * The input is a JSON document of the form
 *   { "handoffSha256": "…"?, "papers": [ { "label", "sourceRights", "source": {"questions": []},
 *                                          "repository": {"questions": []} } ] }
 * where each question may carry `stub: true` (the producer's own collection-stub decision) and
 * `imageBytes` verified manifests (see mapping.mjs).
 *
 * `--gate-module` optionally loads a module whose default export is `(question) => boolean`, so the
 * authoritative eligibility gate (for example PR #45's `isCollectionStub`) can be plugged in without
 * this CLI inventing or duplicating a policy. Without it, only explicitly marked stubs and rows with
 * no comparable content are refused.
 *
 * Exit codes: 0 = produced, nothing needs a human; 2 = produced but human review / blocked / over
 * limit; 1 = usage or parse error. The receipt never contains question text, options or image bytes.
 */
import fs from 'node:fs/promises';
import { parseArgs } from 'node:util';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { buildIncrementalReceipt, validateReceipt, DEFAULT_LIMITS } from './incremental-validator.mjs';

const HELP = `Bounded incremental question-mapping validation (metadata-only receipt)
  node src/mapping-batch.mjs --input FILE --out FILE
      [--max-papers ${DEFAULT_LIMITS.maxPapers}] [--max-questions ${DEFAULT_LIMITS.maxQuestions}] [--gate-module FILE]
Exit: 0 clean · 2 needs human review / blocked / over limit · 1 usage or parse error`;

async function loadGate(filename) {
  if (!filename) return null;
  const module = await import(pathToFileURL(path.resolve(filename)).href);
  if (typeof module.default !== 'function') throw new Error('gate module must default-export a predicate');
  return module.default;
}

async function main() {
  const { values } = parseArgs({ options: {
    input: { type: 'string' }, out: { type: 'string' },
    'max-papers': { type: 'string' }, 'max-questions': { type: 'string' },
    'gate-module': { type: 'string' }, help: { type: 'boolean', default: false },
  } });
  if (values.help) { console.log(HELP); return 0; }
  if (!values.input || !values.out) { console.error(HELP); return 1; }

  let input;
  try { input = JSON.parse(await fs.readFile(values.input, 'utf8')); }
  catch (error) {
    console.error(`Could not read the batch input (${error.code ?? error.name}).`);
    return 1;
  }
  const maxPapers = Number(values['max-papers'] ?? DEFAULT_LIMITS.maxPapers);
  const maxQuestions = Number(values['max-questions'] ?? DEFAULT_LIMITS.maxQuestions);
  if (!Number.isInteger(maxPapers) || maxPapers < 1 || !Number.isInteger(maxQuestions) || maxQuestions < 1) {
    console.error('--max-papers and --max-questions must be positive integers');
    return 1;
  }

  let gate = null;
  try { gate = await loadGate(values['gate-module']); }
  catch (error) {
    console.error(`Could not load the gate module (${error.code ?? error.name}).`);
    return 1;
  }
  // The default gate refuses what the producer marked as a stub, and nothing it did not mark.
  // No implicit allow-all beyond that; the authoritative placeholder policy stays with its owner.
  const isEligible = gate ?? ((question) => question?.stub !== true);

  let receipt;
  try {
    receipt = buildIncrementalReceipt({ papers: input.papers, isEligible, handoffSha256: input.handoffSha256 ?? null,
      limits: { maxPapers, maxQuestions } });
  } catch (error) {
    console.error(`Validation failed (${error.message}).`);
    return 1;
  }
  const check = validateReceipt(receipt);
  if (!check.ok) { console.error(`Receipt contract violated: ${check.problems.slice(0, 5).join('; ')}`); return 1; }
  await fs.writeFile(values.out, `${JSON.stringify(receipt, null, 2)}\n`, { flag: 'wx' }).catch((error) => {
    if (error.code === 'EEXIST') throw new Error('refusing to overwrite an existing receipt; choose a new path');
    throw error;
  });

  const { counts } = receipt;
  console.log(JSON.stringify({ out: values.out, kind: receipt.kind, papers: counts.papers, rows: counts.rows,
    blocked: receipt.blocked, humanReviewRequired: counts.humanReviewRequired,
    categories: Object.fromEntries(Object.entries(counts).filter(([key]) => !['papers', 'blockedPapers', 'humanReviewRequired', 'rows', 'overLimit'].includes(key))) }, null, 2));
  return receipt.blocked || counts.humanReviewRequired > 0 ? 2 : 0;
}

main().then((code) => { process.exitCode = code; }).catch((error) => {
  console.error(`mapping-batch failed (${error.code ?? error.name}).`);
  process.exitCode = 1;
});
