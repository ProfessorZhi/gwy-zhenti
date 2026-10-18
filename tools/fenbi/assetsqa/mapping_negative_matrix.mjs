#!/usr/bin/env node
// Synthetic-only negative matrix for the candidate-mapping verifier.
//
// Every string is fabricated filler. No paper, capture, image bytes or credential
// is read. The matrix pins the cases where an advisory verifier must refuse to
// call two questions identical.
//
// Usage:
//   node mapping_negative_matrix.mjs --mapping <path/to/src/mapping.mjs> [--out f.json]
//
// Exit 0 = every expectation held. Exit 1 = at least one expectation failed.
// Exit 2 = bad arguments.
//
// Expectations (each row states what it wants, not what the code does):
//   A  caption + same verified image SHA          -> exact, auto-acceptable
//   B  caption + DIFFERENT verified image SHA     -> not exact, not auto
//   C  caption + image bytes never verified       -> not exact, not auto
//   D  long text + image refs never verified      -> exact allowed (text is substantive)
//   E  short stem "如图所示" + different verified  -> not exact
//   F  graphic tiling differs (1 image vs 2)      -> not exact
//   G  conflicting material ids                   -> not exact
//   H  identical material ids                     -> exact
//   I  one side carries no option bodies          -> not exact
//   J  option label order conflict                -> not exact

import { pathToFileURL } from 'node:url';
import { writeFileSync } from 'node:fs';

const argv = process.argv.slice(2);
const arg = (n) => { const i = argv.indexOf(`--${n}`); return i >= 0 ? argv[i + 1] : null; };
const mappingPath = arg('mapping');
const outPath = arg('out');
if (!mappingPath) {
  console.error('usage: mapping_negative_matrix.mjs --mapping <src/mapping.mjs> [--out f.json]');
  process.exit(2);
}
const M = await import(pathToFileURL(mappingPath).href);

const A = 'a'.repeat(64), B = 'b'.repeat(64), C = 'c'.repeat(64);
const OPT = [
  { label: 'A', contentHtml: '<p>甲</p>' }, { label: 'B', contentHtml: '<p>乙</p>' },
  { label: 'C', contentHtml: '<p>丙</p>' }, { label: 'D', contentHtml: '<p>丁</p>' },
];
const q = (caption, options = OPT, extra = {}) => ({
  number: 1, contentHtml: `<p>${caption}<img src="x.png"></p>`, options, ...extra,
});

const rows = [];
function run(id, label, src, rep, expect) {
  const score = M.scorePair(src, rep);
  const report = M.buildMappingReport({
    source: { questions: [src] }, repository: { questions: [rep] },
    sourceRights: 'cleared', isEligible: () => true,
  });
  const a = report.assignments[0] ?? {};
  const got = { exact: score.grade === 'exact', auto: a.autoAcceptable === true,
                blockedBy: score.exactBlockedBy ?? null };
  const pass = expect.exact === got.exact && expect.auto === got.auto;
  rows.push({ id, label, expect, got, pass, images: score.signals?.images ?? null });
}

run('A', 'caption + SAME verified sha', q('图', OPT, { imageBytes: [{ sha256: A, verified: true }] }),
    q('图', OPT, { imageBytes: [{ sha256: A, verified: true }] }), { exact: true, auto: true });
run('B', 'caption + DIFFERENT verified sha', q('图', OPT, { imageBytes: [{ sha256: A, verified: true }] }),
    q('图', OPT, { imageBytes: [{ sha256: B, verified: true }] }), { exact: false, auto: false });
run('C', 'caption + UNVERIFIED image bytes', q('图'), q('图'), { exact: false, auto: false });
run('D', 'long text + UNVERIFIED image bytes', q('这是一个足够长的题干文本内容用于区分'),
    q('这是一个足够长的题干文本内容用于区分'), { exact: true, auto: true });
run('E', 'short stem 如图所示 + different verified sha',
    q('如图所示', OPT, { imageBytes: [{ sha256: A, verified: true }] }),
    q('如图所示', OPT, { imageBytes: [{ sha256: C, verified: true }] }), { exact: false, auto: false });
run('F', 'graphic tiling: 1 image vs 2 images',
    q('图', OPT, { imageBytes: [{ sha256: A, verified: true }] }),
    q('图', OPT, { imageBytes: [{ sha256: A, verified: true }, { sha256: B, verified: true }] }),
    { exact: false, auto: false });
run('G', 'conflicting material ids', q('材料题干', OPT, { materialIds: ['m1'] }),
    q('材料题干', OPT, { materialIds: ['m2'] }), { exact: false, auto: false });
run('H', 'identical material ids', q('材料题干', OPT, { materialIds: ['m1'] }),
    q('材料题干', OPT, { materialIds: ['m1'] }), { exact: true, auto: true });
run('I', 'one side has no option bodies', { number: 1, contentHtml: '<p>题干</p>', options: OPT },
    { number: 1, contentHtml: '<p>题干</p>', options: [] }, { exact: false, auto: false });
run('J', 'option label order conflict', q('题干'),
    { number: 1, contentHtml: '<p>题干<img src="x.png"></p>',
      options: [OPT[0], OPT[1], OPT[3], OPT[2]] }, { exact: false, auto: false });

const failures = rows.filter((r) => !r.pass);
const doc = { fixture: 'synthetic filler only', total: rows.length,
              passed: rows.length - failures.length, failed: failures.length, rows };
const text = JSON.stringify(doc, null, 1);
if (outPath) writeFileSync(outPath, text); else console.log(text);
process.exit(failures.length ? 1 : 0);
