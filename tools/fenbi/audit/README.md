# missing-25 evidence audit toolkit

Reproducible checks behind `reports/FENBI-MISSING25-EVIDENCE-20261017.{md,json}`.

These scripts audit **evidence**, not content. They never write to `国考/`, `省考/`,
`图片/` or `catalog/`, never fetch anything with credentials, and never emit question
text — only source pointers, digests, similarity scores and verdicts.

The subject is the 25 missing 行测 original questions named in
`reports/FULL-REPAIR-20261015.md`. That is **not** the library-wide missing-行测 count
(106), which is a larger and different set.

## Requirements

Python 3 standard library only. For the network step, plain HTTPS access.
`pdftotext` (poppler) is needed only if you want to probe a PDF reference; run
`pdftotext -layout in.pdf out.txt` yourself first and pass the `.txt`.

No credentials, tokens, cookies or logins are used or needed anywhere.

## Offline checks (no network)

```bash
bash tools/fenbi/audit/run_gap_audit.sh /tmp/m25-out
```

1. **`gap_audit.py`** — for each of the four papers, compares the front-matter
   declaration (`缺失原题号`) against the question headings actually present.
   Flags a paper as `GAP_CHANGED_SINCE_REPORT` when the declared gap no longer
   matches the tree.
2. **`donor_compare.py`** — re-derives, from the markdown itself, the provenance
   recorded in `reports/FREE-TOOLS-JS2025C-20261016.json`: which question of
   `省考/江苏/2025/行测-A类.md` each restored `行测-C类.md` block came from, whether
   they are identical after folding whitespace/punctuation, and how many of them
   cross question numbers.

## Three-paper evidence matrix (workstream A)

```bash
python3 tools/fenbi/audit/paper_matrix.py --repo . \
    --out reports/FENBI-THREE-PAPER-MATRIX-20261017.json
```

Covers the 23 items in 江苏2025C / 江苏2024A / 广东2020县级 across seven dimensions
(题号 / 题干 / 选项 / 共用材料 / 图片与公式 / 答案 / 解析), using the same four states
as `tools/fenbi/src/align.mjs` (`same` / `different` / `unknown` / `not_compared`).

Offline, every source-facing dimension is `unknown` with reason
`source-content-not-observed` — that is the honest answer while no capture
exists, and it is never promoted to `same` on the strength of similar text.

It also reports two things that are checkable without any capture:

- **cross-paper image provenance** — a question whose figures live in another
  paper's image tree carries that paper's provenance. For figure-reasoning items
  the figure *is* the question, so this matters. Currently the only such
  references in the library are 江苏2025C questions 81 and 85, which point at the
  A-class image tree.
- **join hazard** — this library preserves original numbering with gaps, so a
  direct number join misaligns everything after the first gap.

## Reconciling a capture (handoff)

See [HANDOFF.md](HANDOFF.md) for the input format and the join-strategy trap.

```bash
python3 tools/fenbi/audit/handoff_reconcile.py --repo . \
    --handoff <captured.json> [--paper <library path>] [--join auto] --out <matrix.json>
```

Accepts either the reduced `fenbi-candidate-handoff-v1` projection or a framework
`document.json`. Reports only; nothing is written back. Source answers that were
never published stay `unknown` — they are never borrowed from the library or
from a sibling paper.

`auto` scores both join strategies against the real numbers on each side. Because
a score cannot tell an aligned join from a coincidental one, any paper whose
library preserves numbering gaps also gets an unconditional `join.warning`
naming the gap numbers and the specific mis-mapping a positional join would
produce. The live capture confirmed both target papers are gap-preserving on the
source side too, so `--join number` is the correct choice for them.

## Missing-question evidence packs

```bash
python3 tools/fenbi/audit/missing_evidence_pack.py --repo . \
    [--third-batch-file <local copy of the capture report>] --out <pack.json>
```

Builds a per-question package for the 11 gap numbers (江苏2024A 76/96/110/111,
广东2020县级 69–75): number mapping, what the library holds, what the source
actually holds, and the evidence still required.

**These 11 numbers are slots the source has not collected.** The page lists the
number but holds a collection stub ("题目正在全力以赴征集…"), so there is no
source text to repair from. Every item is therefore `candidate_status: blocked`
and `source_content_available: false`, and the pack does not request
authorisation to repair from that capture — there is nothing there to authorise.
A question number, or a question container in the DOM, proves only that a slot
exists. The correction is anchored to PR #33's per-item DOM audit; the pack also
records the earlier claim it supersedes.

It emits no question text — required fields are named, not filled. Answers and
explanations stay `unknown`, and provenance is always `recollection-institution`
(never official).

## Vetting a candidate source before comparing it

```bash
python3 tools/fenbi/audit/source_candidate_vet.py --repo . \
    --paper <paper path> [--source <candidate file>] [--source-format text|html]
```

`handoff_reconcile.py` compares a capture against the library. This runs one step
earlier and answers a different question: **does the candidate even contain the
missing questions?** It reads the gap list from the paper's own front matter
(never hardcoded) and classifies each number as `content`, `stub` (a collection
placeholder), `absent`, or `not-supplied`. Only `content` counts as recovered —
a stub is never counted as partial recovery. It also checks the candidate's
identity tokens (year / province / subject) and infers what each gap probably
held from the nearest surviving neighbour, skipping over consecutive gaps.

With no `--source` it emits the manifest-side matrix and verdict
`blocked-no-source-supplied`, which is a useful artefact on its own.

## Offline target inventory from the catalog

```bash
python3 tools/fenbi/audit/fenbi_target_inventory.py --repo . --top 50 --handoff 30 \
    --out reports/FENBI-TARGET-INVENTORY-20261017.json \
    --handoff-out reports/FENBI-TARGET-HANDOFF-20261017.json
```

Reads `catalog/manifest.jsonl` — no network, no capture profile, metadata only — and
produces the paper-identity list, a ranked shortlist, and a directory-only handoff
for whoever runs the capture.

Three rules it enforces, each of which has already cost this project real work:

- **A null fenbi id is never `capture_ready`.** Only an observed id that has not
  already been captured qualifies. Everything else is `false` with a reason.
- **A canonical identity that merges divergent bytes is never auto-merged.** On this
  catalog, every `X` / `X卷` alias pair has different content and usually a different
  question count; they are reported for curation with a suggested survivor instead.
- **`declared_questions` is not the recovered count.** It is the current file's own
  claim (it equals `question_anchors` library-wide); the original paper size is
  derived as `positions_held + missing_count`.

## Tests

```bash
python3 -m unittest discover -s tools/fenbi/audit/tests -t .
```

Fixtures are generated from the repository's own markdown at run time, so no
question text is committed in the test suite.

## Network step (optional, no credentials)

```bash
python3 tools/fenbi/audit/fetch_pinned_sources.py --out /tmp/pinned-25
```

Downloads the reference documents pinned by
`reports/FULL-REPAIR-APTITUDE-25-MISSING-SOURCE-PACK-20261015.json` and checks each
sha256 against the value the pack records — i.e. whether the report's 固定源证据 is
still intact. It refuses to write inside the repository tree, because these are
third-party documents. A host that does not resolve is reported as `DNS_FAILURE`,
which is a statement about reachability now, not about the domain's permanence.

## Probing a reference at the missing numbers

```bash
python3 tools/fenbi/audit/reference_probe.py \
    --file /tmp/pinned-25/江苏-2024-行测-A类__fixed_reference \
    --format html --label "江苏2024A" --numbers 76,96,110,111
```

Classifies each number as `PLACEHOLDER_AT_SOURCE`, `TEXT_PRESENT_AT_SOURCE` or
`NUMBER_ABSENT_FROM_SOURCE`. Both heading shapes found in these exports are handled:
a bare number on its own line (HTML exports) and a number opening a line followed by
punctuation (PDF text layers).

## Regenerating the report

```bash
python3 tools/fenbi/audit/build_evidence_ledger.py --repo . \
    [--probes DIR] --out reports/FENBI-MISSING25-EVIDENCE-20261017.json
```

`--probes DIR` merges any `reference_probe.py` outputs you produced. The section is
empty if omitted, since it depends on locally held reference copies that are not
committed here.

## Interpreting the verdicts

- `GENUINE_GAP` — the number is missing from the library *and* from every reachable
  source of record. Nothing to restore.
- `BACKFILLED_IN_PR20_INDEPENDENT_SOURCE_NOT_REACHABLE` — the number was restored
  between the report baseline and the audited head, but the document that would
  confirm the paper mapping is currently unreachable and unarchived. **This is a
  statement about verifiability from one environment, not a finding that the
  restoration is wrong.**
