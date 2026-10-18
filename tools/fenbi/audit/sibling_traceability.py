#!/usr/bin/env python3
"""Measure whether a sibling paper can legitimately supply a paper's gap numbers.

Provincial exams often reuse questions across A/B/C or 县级/乡镇 papers, so a
natural shortcut for a missing number is "the same-numbered question in the
sibling paper". This tool measures how safe that shortcut is instead of assuming
it, by comparing the papers at the numbers BOTH of them hold.

The decisive metric is `identical_rate`: of the numbers held by both papers, what
fraction are textually identical after the aligner's normalization.

* A rate near 1.0 would mean the two files are the same paper under two names —
  substitution would be safe.
* A low rate means same-number coincidence, and substitution would be fabrication.

On this catalog every A/B/C and 县级/乡镇 pair measures well below 1.0, so the
tool never marks a substitution as justified: a gap number is reported as a
*candidate lead* with its measured base rate, never as a recovery.

No question text is emitted — only counts, rates and verdicts.

Usage:
    python3 tools/fenbi/audit/sibling_traceability.py --repo . \
        --paper 省考/江苏/2024/行测-A类.md [--out FILE]

    # or survey every paper that declares gaps
    python3 tools/fenbi/audit/sibling_traceability.py --repo . --all-gap-papers
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    default_repo_root, normalize_comparison_text, parse_frontmatter,
    parse_int_list, parse_paper, read_text,
)

MANIFEST = "catalog/manifest.jsonl"

# Substitution is only defensible when the two files are effectively one paper.
# Below this rate the same-number question is coincidence, not identity.
SUBSTITUTION_RATE_THRESHOLD = 0.95


def load_records(repo):
    with open(os.path.join(repo, MANIFEST), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def fingerprint(record_or_path, repo):
    """number -> normalized stem, for same-number comparison."""
    path = (record_or_path["path"] if isinstance(record_or_path, dict)
            else record_or_path)
    _, body = parse_frontmatter(read_text(os.path.join(repo, path)))
    parsed = parse_paper(body)
    return {n: normalize_comparison_text(q["stem"])["formatOnly"]
            for n, q in parsed["questions"].items()}


def compare_pair(a_fp, b_fp):
    """Same-number overlap and how much of it is textually identical."""
    common = sorted(set(a_fp) & set(b_fp))
    identical = [n for n in common if a_fp[n] and b_fp[n] and a_fp[n] == b_fp[n]]
    rate = (len(identical) / len(common)) if common else None
    return {
        "same_number_overlap": len(common),
        "text_identical": len(identical),
        "identical_rate": round(rate, 4) if rate is not None else None,
        "identical_numbers": identical,
    }


def sibling_records(record, records):
    """Papers of the same area, year and subject with a different 卷型."""
    return [
        r for r in records
        if r["area"] == record["area"]
        and str(r["year"]) == str(record["year"])
        and r["subject"] == record["subject"]
        and r.get("paper_type") != record.get("paper_type")
    ]


def analyse(repo, record, records, fps=None):
    """Full traceability analysis for one paper."""
    path = record["path"]
    frontmatter, body = parse_frontmatter(read_text(os.path.join(repo, path)))
    declared = sorted(parse_int_list(frontmatter.get("缺失原题号", "")))
    a_fp = (fps or {}).get(path) or fingerprint(path, repo)

    siblings = []
    for sib in sibling_records(record, records):
        sib_fp = (fps or {}).get(sib["path"]) or fingerprint(sib["path"], repo)
        pair = compare_pair(a_fp, sib_fp)
        siblings.append({
            "path": sib["path"],
            "paper_type": sib.get("paper_type"),
            "question_anchors": sib.get("question_anchors"),
            "sibling_missing_count": len(sib.get("missing_original_numbers") or []),
            "same_number_overlap": pair["same_number_overlap"],
            "text_identical": pair["text_identical"],
            "identical_rate": pair["identical_rate"],
            # The rule this tool exists to enforce.
            "substitution_justified": bool(
                pair["identical_rate"] is not None
                and pair["identical_rate"] >= SUBSTITUTION_RATE_THRESHOLD),
            "identical_numbers_sample": pair["identical_numbers"][:10],
        })

    items = []
    for number in declared:
        candidates = []
        for sib in siblings:
            sib_fp = (fps or {}).get(sib["path"]) or fingerprint(sib["path"], repo)
            candidates.append({
                "sibling": sib["path"],
                "sibling_has_this_number": number in sib_fp,
                "identical_rate_at_shared_numbers": sib["identical_rate"],
                "usable_as_source": False,
            })
        rated = [c["identical_rate_at_shared_numbers"] for c in candidates
                 if c["identical_rate_at_shared_numbers"] is not None]
        items.append({
            "number": number,
            "candidate_leads": candidates,
            "best_identical_rate": max(rated) if rated else None,
            "evidence_level": "unconfirmed",
            "substitution_justified": False,
            "blocked_reason": (
                "a sibling paper's same-numbered question is a lead, not evidence: the "
                "measured identical rate is far below the threshold, so identity of the "
                "missing question cannot be assumed"),
        })

    return {
        "paper": {
            "path": path,
            "area": record["area"],
            "year": str(record["year"]),
            "subject": record["subject"],
            "paper_type": record.get("paper_type"),
            "question_anchors": record.get("question_anchors"),
            "declared_missing": declared,
            "declared_missing_count": len(declared),
        },
        "siblings": siblings,
        "items": items,
        "summary": {
            "gap_numbers": len(declared),
            "siblings_examined": len(siblings),
            "siblings_justified_as_source": sum(
                1 for s in siblings if s["substitution_justified"]),
            "gap_numbers_with_any_lead": sum(
                1 for i in items
                if any(c["sibling_has_this_number"] for c in i["candidate_leads"])),
            "gap_numbers_recovered": 0,
        },
        "policy": [
            f"Substitution is justified only when the identical rate reaches "
            f"{SUBSTITUTION_RATE_THRESHOLD}, i.e. the files are effectively one paper.",
            "A same-number question in a different 卷型 is a LEAD, never a recovery.",
            "No question text is emitted; only counts and rates.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--paper", default=None)
    ap.add_argument("--all-gap-papers", action="store_true",
                    help="survey every paper that declares missing original numbers")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    records = load_records(args.repo)
    if args.all_gap_papers:
        targets = [r for r in records if r.get("missing_original_numbers")]
    elif args.paper:
        match = [r for r in records if r["path"] == args.paper]
        if not match:
            print(f"error: no manifest record for {args.paper}", file=sys.stderr)
            return 2
        targets = match
    else:
        print("error: pass --paper or --all-gap-papers", file=sys.stderr)
        return 2

    fps = {}
    for record in records:
        try:
            fps[record["path"]] = fingerprint(record["path"], args.repo)
        except FileNotFoundError:
            continue

    results = [analyse(args.repo, r, records, fps) for r in targets]
    doc = {
        "audit": "sibling-traceability",
        "date": "2026-10-18",
        "threshold": SUBSTITUTION_RATE_THRESHOLD,
        "papers": results,
    }

    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    for result in results:
        p, s = result["paper"], result["summary"]
        print(f"{p['path']}: gaps={p['declared_missing_count']} siblings={s['siblings_examined']} "
              f"justified={s['siblings_justified_as_source']} leads={s['gap_numbers_with_any_lead']}")
        for sib in result["siblings"]:
            print(f"    vs {sib['paper_type']:<8} overlap={sib['same_number_overlap']:<4} "
                  f"identical={sib['text_identical']:<4} rate={sib['identical_rate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
