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
   - exact: the key is unique on both sides;
   - multiset: the same with options sorted, reported as `optionOrderChanged`;
   - prefix: one side's stem is a prefix of the other's, at least 8 normalised characters,
     all four option texts identical in order, unique in both directions. Archive markdown
     often appends material or instruction text after the question; such matches are reported
     separately in `stemPrefixMatch` and never silent.
3. Anything else is `stemSameOptionDiff` (stem equal, options differ) or `unmatchedSource`.
   Both stay unknown; a question number match is never accepted as evidence.
4. **Answers are compared by option text.** Each side's letter is resolved through its own
   option list, so a reordered option list does not create a false conflict. A missing letter
   on either side is `answerUnknown`.
5. `qaVerdict` is `PENDING_REVIEW` or `PENDING_REVIEW_STRONG_MATCH`. There is no pass state:
   structural checks alone never certify a paper. `qaComplete` additionally requires exact
   (non-prefix) unique matches for every question, equal question counts on both sides, no
   answer conflict or unknown, no missing explanation and no option difference.

## Receipt fields (metadata only)

Per paper (`out/qa-<sourceId>.json`, concatenated in `out/receipts.jsonl`):

- `sourceId`, `prPath`, `area`, `year`, `subject`, `variant`
- `sourceDocSha12`, `prBlobSha12`, `revision` (composite sha12)
- `sourceQ`, `prQ`, `sourceStubQ`, `prStubQ`, `sourceNumbers`, `sourceStubNumbers`
- `strongMatches`, `stemPrefixMatch`, `prStemExtraChars`, `optionOrderChanged`,
  `stemSameOptionDiff`, `ambiguous`, `unmatchedSource`, `unmatchedPr`
- `answerMatch`, `answerConflict`, `answerUnknown`
- `explanationSame`, `explanationDiff`, `explanationMissing`
- `imageQuestions`, `imageShaEvidence`, `assetsTotal`, `assetsWithSha`
- `qaVerdict`, `qaComplete`, `structuralOnly`, `rightsStatus`, `publishable`, `independentQa`

Question numbers are the paper's original numbers; gaps are preserved, never renumbered.
No stem, option text, answer letter, explanation, url, cookie or image bytes are written.
`rightsStatus` is always `unverified` and `publishable` always `false`; a hash is not a licence.

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
