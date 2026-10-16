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
