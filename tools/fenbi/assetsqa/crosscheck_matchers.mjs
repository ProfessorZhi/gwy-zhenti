#!/usr/bin/env node
// Synthetic-only conformance cross-check between two independent matcher modules.
//
// Nothing here reads a paper, a capture, a profile or the network. Every string
// is fabricated filler. The point is to pin down *where the two matchers define
// the same words differently*, so a reviewer can tell whether one report's
// numbers can be compared with the other's.
//
// Usage:
//   node crosscheck_matchers.mjs \
//     --reorder <path/to/tools/fenbi/src/reorder.mjs> \
//     --mapping <path/to/tools/fenbi/src/mapping.mjs> \
//     [--out result.json]
//
// Exit 0 = ran and produced a result. Divergences are data, not failures.

import { pathToFileURL } from 'node:url';
import { writeFileSync } from 'node:fs';

const argv = process.argv.slice(2);
const arg = (name) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : null;
};

const reorderPath = arg('reorder');
const mappingPath = arg('mapping');
const outPath = arg('out');

if (!reorderPath || !mappingPath) {
  console.error('usage: crosscheck_matchers.mjs --reorder <reorder.mjs> --mapping <mapping.mjs> [--out f.json]');
  process.exit(2);
}

const reorder = await import(pathToFileURL(reorderPath).href);
const mapping = await import(pathToFileURL(mappingPath).href);

// ---------------------------------------------------------------- fixture
// Filler characters only; no exam content.
const q = (n, stem, opts = null) => ({
  number: n,
  contentHtml: `<p>${stem}</p>`,
  options: (opts ?? ['甲', '乙', '丙', '丁']).map((t, i) => ({
    label: 'ABCD'[i],
    // unique option text per question, so a shared option set cannot create a fake tie
    contentHtml: `<p>${stem}${t}${i}</p>`,
  })),
});
const imageOnly = (n) => ({
  number: n,
  contentHtml: '<p>图<img src="filler.png"></p>',
  options: ['A', 'B', 'C', 'D'].map((l) => ({ label: l, contentHtml: `<p>${l}</p>` })),
  imageCount: 1,
});

// S1->R2 and S2->R1 are reordered; S3->R3 is same-number; S4 has two identical
// repo candidates; S5 is image-only; S6 has no candidate; R6 is repo-only.
const source = [
  q(1, '甲甲甲甲甲甲甲甲'), q(2, '乙乙乙乙乙乙乙乙'), q(3, '丙丙丙丙丙丙丙丙'),
  q(4, '丁丁丁丁丁丁丁丁'), imageOnly(5), q(6, '戊戊戊戊戊戊戊戊'),
];
const repository = [
  q(1, '乙乙乙乙乙乙乙乙'), q(2, '甲甲甲甲甲甲甲甲'), q(3, '丙丙丙丙丙丙丙丙'),
  q(4, '丁丁丁丁丁丁丁丁'), q(5, '丁丁丁丁丁丁丁丁'), q(6, '己己己己己己己己'),
];

const result = { fixture: 'synthetic filler only', cases: {} };

// ---------------------------------------------------------------- reorder
if (typeof reorder.matchQuestions === 'function') {
  const m = reorder.matchQuestions(source, repository, { low: 0.45 });
  const rows = reorder.classifyQuestions(source, repository, m, { suggest: 0.85 });
  result.cases.reorder = {
    counts: reorder.summarize(rows),
    coverage: reorder.coverage(source, rows),
    mappingPairs: m.matches.map((x) => [source[x.i].number, repository[x.j].number, x.exact]),
    ambiguousSourceIndexes: m.multiCandidates.map((x) => x.sourceIndex),
    // A pair whose source was classified ambiguous but which still appears in
    // matches: this is the "prose says unbound, data says bound" gap.
    ambiguousButBound: m.matches
      .filter((x) => m.multiCandidates.some((mc) => mc.sourceIndex === x.i))
      .map((x) => [source[x.i].number, repository[x.j].number]),
  };
}

// ---------------------------------------------------------------- mapping
if (typeof mapping.buildMappingReport === 'function') {
  const build = (rights, eligible = () => true) => mapping.buildMappingReport({
    source: { label: 'synthetic-src', questions: source },
    repository: { label: 'synthetic-repo', questions: repository },
    sourceRights: rights,
    isEligible: eligible,
  });
  const cleared = build('cleared');
  const restricted = build('restricted');
  const gated = build('cleared', (x) => x.number !== 5);
  result.cases.mapping = {
    counts: cleared.counts,
    assignments: cleared.assignments.map((a) =>
      [a.sourceNumber, a.repositoryNumber, a.grade, a.autoAcceptable, a.sameNumber]),
    ambiguous: cleared.ambiguous.map((a) =>
      [a.sourceNumber, a.reason, a.candidates.map((c) => c.repositoryNumber)]),
    unmatchedSource: cleared.unmatchedSource.map((a) => [a.sourceNumber, a.reason]),
    unmatchedRepository: cleared.unmatchedRepository.map((a) => a.repositoryNumber),
    validate: mapping.validateMappingReport(cleared),
    rightsVeto: { blocked: restricted.blocked, assignments: restricted.assignments.length },
    eligibilityGate: {
      rejected: gated.source.rejected,
      unmatchedSource: gated.unmatchedSource.map((a) => [a.sourceNumber, a.reason]),
    },
  };
}

// ---------------------------------------------------------------- semantics
// `exact` in the reorder module is normalized equality, not verbatim equality.
if (typeof reorder.normalizeText === 'function') {
  result.cases.exactSemantics = {
    normalizedA: reorder.normalizeText('甲，乙。丙！丁？'),
    normalizedB: reorder.normalizeText('甲 乙 丙 丁'),
    equalAfterNormalization:
      reorder.normalizeText('甲，乙。丙！丁？') === reorder.normalizeText('甲 乙 丙 丁'),
    conclusion: 'exact means normalized-equal (punctuation/whitespace/fullwidth folded), not verbatim',
  };
}

// `imageSignal` in the mapping module hashes the image *reference string*.
if (typeof mapping.scorePair === 'function') {
  const QA = (n, src) => ({
    number: n, contentHtml: `<p>看下图<img src="${src}"></p>`,
    options: ['甲', '乙', '丙', '丁'].map((t, i) => ({ label: 'ABCD'[i], contentHtml: `<p>${t}</p>` })),
  });
  const sig = (x, y) => mapping.scorePair(QA(1, x), QA(1, y)).signals.images;
  result.cases.imageSignal = {
    sameReference: sig('../../图片/a/same.png', '../../图片/a/same.png'),
    differentPathSameFile: sig('../../图片/a/same.png', 'https://cdn.test/a/same.png'),
    differentFile: sig('../../图片/a/same.png', '../../图片/a/other.png'),
    conclusion: 'image signal compares reference strings, not image bytes',
  };
}

const text = JSON.stringify(result, null, 1);
if (outPath) { writeFileSync(outPath, text); } else { console.log(text); }
process.exit(0);
