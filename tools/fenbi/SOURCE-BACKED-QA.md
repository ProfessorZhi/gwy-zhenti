# Source-backed per-question QA

Offline comparator that links a locally cached source paper to an archive markdown paper and
reports, per question, whether the two sides are the same question and whether the answer and
the explanation agree. It exists so that a source owner can prove paper quality with evidence
instead of asserting it.

Files: `src/source-backed-qa.mjs` (comparator), `src/source-backed-qa-cli.mjs` (CLI),
`test/source-backed-qa.test.mjs` (synthetic cases).

## Matching contract

1. **Paper level.** `selectPrPath` needs exactly one manifest row with the same `area`, `year`,
   `subject = 行测` and normalised `paper_type`/variant. Zero rows is `NO_PR_MATCH`, more than
   one is `AMBIGUOUS_PR_PATH`. A source `sourceId` never selects a path on its own.
2. **Question identity never uses question numbers.** The key is
   `sha256(normalize(stem) || normalize(option1..4))`, with `normalize` = NFKC, lower case,
   strip every non letter/number character.
   - `exact_unique`: identical stem and all four option texts in order, unique on both sides.
     Only this status counts as a match and only here are answers scored.
   - `option_diff`: the same options in a different order (answers are still compared after
     resolving each side's letter to its own option text), or identical stem with different
     option text.
   - `prefix_candidate`: one side's stem is a prefix of the other's, all four option texts
     identical in order, unique in both directions. This is a **candidate only** — archive
     markdown often appends material or instruction text after the question, and a generic
     stem plus matching options can otherwise fake a match. Candidates are excluded from
     strict counts, from strict answer statistics and from any whole-paper coverage claim.
     A candidate is refused outright when the shorter stem is under 12 normalised characters,
     when options are empty or duplicated, when the stem is a generic prompt
     (`下列说法`/`根据这段材料`/…), or when the appended text dwarfs the stem.
3. Anything else is `unmatched`; a source question whose content is a placeholder is
   `source_stub`. Both stay unknown; a question number match is never accepted as evidence.
   A stub that happens to match content stays a stub and is reported in `stubContentMatched`.
4. **Answers are compared by option text.** Each side's letter is resolved through its own
   option list. Strict and candidate comparisons are counted separately:
   `answerSameStrict`/`answerConflictStrict`/`answerUnknownStrict` versus the `…Candidate`
   triple. Unknown is never counted in a denominator.
5. `qaVerdict` is `PENDING_REVIEW` or `PENDING_REVIEW_STRONG_MATCH`. There is no pass state:
   structural checks alone never certify a paper. `qaComplete` requires every question to be
   `exact_unique`, equal question counts, no strict conflict or unknown, no missing
   explanation, no stub, no candidate and no `option_diff`. `coverageClaimEligible` stays
   `false` regardless; it is a receipt, not a certification.

## Receipt fields (metadata only)

Per paper (`out/qa-<sourceId>.json`, concatenated in `out/receipts.jsonl`):

- `sourceId`, `prPath`, `area`, `year`, `subject`, `variant`
- `sourceDocSha12`, `prBlobSha12`, `revision` (composite sha12)
- `sourceQ`, `prQ`, `sourceStubQ`, `prStubQ`, `sourceNumbers`, `sourceStubNumbers`
- `strictMatches`, `strictMatchCount`, `prefixCandidates`, `prefixCandidateCount`,
  `prefixRejected` (with a reason code), `prStemExtraChars`
- `optionOrderChanged`, `stemSameOptionDiff`, `optionDiffCount`, `ambiguous`,
  `unmatchedSource`, `unmatchedPr`, `stubContentMatched`
- `matchStatusCounts` (`exact_unique` / `prefix_candidate` / `option_diff` / `unmatched` /
  `source_stub`), `partitionSum`, `partitionConsistent`
- `answerSameStrict`, `answerConflictStrict`, `answerUnknownStrict`,
  `answerSameCandidate`, `answerConflictCandidate`, `answerUnknownCandidate`
- `explanationSame`, `explanationDiff`, `explanationMissing` (scoped to strict matches only)
- `imageQuestions`, `imageShaEvidence`, `assetsTotal`, `assetsWithSha`
- `qaVerdict`, `qaComplete`, `structuralOnly`, `matchStrength`, `coverageClaimEligible`,
  `legacyStrongMatchesInclusive`, `rightsStatus`, `publishable`, `independentQa`

`legacyStrongMatchesInclusive` is kept only to explain older receipts, where it mixed exact
matches, prefix candidates and option differences into one number; it must never be used as a
coverage figure. Question numbers are the paper's original numbers; gaps are preserved, never
renumbered. No stem, option text, answer letter, explanation, url, cookie or image bytes are
written. `rightsStatus` is always `unverified` and `publishable` always `false`; a hash is not
a licence.

`out/source-revisions.jsonl` records one line per paper for change tracking, and
`out/run-receipt.json` aggregates totals, coverage and safety flags.

## CLI

```
node src/source-backed-qa-cli.mjs \
  --papers DIR --pr-repo DIR --pr-head SHA --ids id1,id2 [--manifest path] [--out DIR]
```

Reads the source cache read-only and the archive through `git show` at a pinned commit.
The output directory is created `0700` and every file is written `0600`. No network, no
browser, no writes to the source cache or to the archive.

## Downstream

The receipts are shaped to feed a source-QA queue contract (the `source-qa-queue` module,
introduced separately) through a metadata-only adapter. Fields the queue needs but this
comparator cannot honestly produce — per-image `{path, sha256}` pairs,
`mapping.detailsByNumber = verified`, reviewer and approver Ed25519 attestations, rights basis
and evidence — are left absent or null. An adapter must never synthesise them from ids or
hashes.
