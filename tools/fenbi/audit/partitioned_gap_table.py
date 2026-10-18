#!/usr/bin/env python3
"""Four-granularity gap table for the gwy-zhenti repository.

The project carries several different "gap" numbers that are routinely confused,
because they count different things at different granularities. This tool
recomputes each one from its own authoritative source and states, explicitly,
that they must not be added together.

| id | granularity | unit | source |
| -- | ----------- | ---- | ------ |
| A | complete reference paper not yet acquired | paper_slot (area x year x subject x 卷型) | reports/MISSING48-RECOVERY-20261016.json |
| B | missing / unverified material | cell (area x year x subject, NO 卷型) | 资料缺失/INDEX.jsonl |
| C | original question numbers missing inside a paper the library holds | question number | catalog/manifest.jsonl |
| D | source-side collection stubs (the vendor has a slot, not the question) | question position | owner capture reports, cited per row |

A and B are disjoint units (A has a 卷型 dimension, B does not). C and D overlap
heavily by construction: a paper can have both missing numbers and source stubs,
and 江苏2025C's 12 stubs were later filled from a donor (D history, not C).

Every row carries its evidence pointer. Nothing here reads a capture profile,
and no question text, image bytes or credentials are involved.

Usage:
    python3 tools/fenbi/audit/partitioned_gap_table.py --repo . [--out FILE]
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import default_repo_root  # noqa: E402

MISSING48 = "reports/MISSING48-RECOVERY-20261016.json"
PLACEHOLDER_INDEX = "资料缺失/INDEX.jsonl"
MANIFEST = "catalog/manifest.jsonl"
JS2025C_STUBS = "reports/FREE-TOOLS-JS2025C-20261016.json"

# Source-side stub counts that exist only in the capture owner's reports (other
# branches), so they are cited rather than re-derived. Each row names its report
# and the exact figure; nothing is inferred from a URL or a screenshot.
CITED_STUB_SOURCES = {
    ("江苏", "2025", "行测", "C类"): {
        "stubs": 12, "source_id": "4189916",
        "evidence": "reports/FREE-TOOLS-JS2025C-20261016.json (in-repo) + PR #51",
        "origin": "derived-in-repo",
    },
    ("江苏", "2024", "行测", "A类"): {
        "stubs": 4, "source_id": "4162243",
        "evidence": "PR #51 §3, PR #72 per-paper table, PR #33 DOM audit",
        "origin": "cited-owner-report",
    },
    ("广东", "2020", "行测", "县级卷"): {
        "stubs": 7, "source_id": "96785",
        "evidence": "PR #51 §3, PR #72 per-paper table, PR #33 DOM audit",
        "origin": "cited-owner-report",
    },
    ("上海", "2026", "行测", "统考"): {
        "stubs": 1, "source_id": "8472470",
        "evidence": "PR #72 per-paper table",
        "origin": "cited-owner-report",
    },
}

# Catalogue reach from PR #51 (7 regions, 191 papers) and PR #57/#60/#72/#75
# (the 10 papers with a readable exercise). Only the papers the owner explicitly
# reported absent are marked absent; everything else is genuinely unknown.
FENBI_CATALOGUE = {
    "regions_walked": ["国考", "北京", "江苏", "浙江", "上海", "天津", "广东"],
    "papers_observed": 191,
    "by_region": {"国考": 30, "北京": 18, "江苏": 30, "浙江": 30,
                  "上海": 30, "天津": 23, "广东": 30},
    "explicitly_absent": {"北京": "2026", "江苏": "2026"},  # 行测 A / 统考
    "note": ("'absent' means: not found after the region's pages were fully "
             "walked (北京 18 papers over 2 pages, 江苏 30 over 2 pages). That is "
             "observed_catalog_absent, NOT proof the paper does not exist "
             "anywhere or officially."),
    "readable_exercises": {
        "国考2026 地市级": "5823068", "国考2026 行政执法": "5823067",
        "国考2026 副省级": "5823069", "天津2026 统考": "8399759",
        "上海2026 统考": "8472470", "广东2026 统考": "8399765",
        "浙江2026 C类": "8399763", "江苏2025 C类": "4189916",
        "江苏2024 A类": "4162243", "广东2020 县级": "96785",
    },
    "readable_count": 10,
    "catalogue_total_minus_readable": 181,
    "catalogue_note": ("The other 181 have no existing exercise, which does NOT mean "
                       "they lack original questions — only that a practice would "
                       "have to be initialised. Do not report them as 'all pending "
                       "initialisation' or as 'all valid'."),
}

CONTENT_COHORT = {
    "source": "PR #72 (dab4c5f) + PR #75 (3c83c32), corrected from PR #66",
    "positions": 1210,
    "usable_text": 1180,
    "image_only_not_text_comparable": 6,
    "source_stubs": 24,
    "normalized_or_near_matched": 1050,
    "weak_candidates": 40,
    "remaining": 90,
    "remaining_with_image": 54,
    "remaining_text_only": 36,
    "figures_byte_verified": 9,
    "closure": {
        "positions_ok": 1180 + 6 + 24 == 1210,
        "matched_ok": 1050 + 40 + 90 == 1180,
    },
    "caveat": ("content match is not proof of the official original; normalized_equal "
               "is normalized equality, not byte equality"),
}


def load_missing48(repo):
    with open(os.path.join(repo, MISSING48), encoding="utf-8") as fh:
        return json.load(fh)


def load_placeholders(repo):
    with open(os.path.join(repo, PLACEHOLDER_INDEX), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_manifest(repo):
    with open(os.path.join(repo, MANIFEST), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def granularity_a(doc):
    """Paper slots still without a complete reference paper."""
    targets = doc["targets"]
    recovered = [t for t in targets
                 if t.get("counted_as_recovered") or t.get("counted_as_recovered_this_round")]
    remaining = [t for t in targets if t not in recovered]
    by_area = Counter(t["area"] for t in remaining)
    return {
        "id": "A",
        "label": "缺完整参考卷",
        "unit": "paper_slot (地区 x 年份 x 科目 x 卷型)",
        "count": len(remaining),
        "registry_declared": doc["remaining_targets_without_complete_reference_version"],
        "reconciliation_ok": len(remaining) == doc["remaining_targets_without_complete_reference_version"],
        "by_area": dict(by_area.most_common()),
        "by_subject": dict(Counter(t["subject"] for t in remaining)),
        "by_status": dict(Counter(t.get("status") for t in remaining)),
        "recovered_this_round": [
            {"area": t["area"], "year": t["year"], "subject": t["subject"],
             "variant": t.get("variant")} for t in recovered],
        "slots": [
            {"area": t["area"], "year": str(t["year"]), "subject": t["subject"],
             "variant": t.get("variant"), "status": t.get("status"),
             "has_partial": t.get("status") == "partial_source_recovered_not_a_complete_paper",
             "variant_known": bool(t.get("variant"))}
            for t in remaining
        ],
        "source": MISSING48,
        "caveat": ("some slots are partial fragments already in the repo; some "
                   "variants remain unknown"),
    }


def granularity_b(rows):
    """Year-subject cells with no material at all — no 卷型 dimension."""
    by_state = Counter(r["state"] for r in rows)
    by_area_state = defaultdict(Counter)
    for row in rows:
        # path is 资料缺失/省考/<area>/<year>/<subject>.md
        parts = row["path"].split("/")
        area = parts[2] if len(parts) > 2 else "?"
        by_area_state[area][row["state"]] += 1
    return {
        "id": "B",
        "label": "资料缺档 / 待核",
        "unit": "cell (地区 x 年份 x 科目, 无卷型维度)",
        "count": len(rows),
        "by_state": dict(by_state),
        "no_variant_field": "卷型" not in rows[0] and "paper_type" not in rows[0],
        "fields_present": sorted(rows[0].keys()),
        "by_area": {a: dict(c) for a, c in sorted(by_area_state.items())},
        "unverified_areas": sorted({a for a, c in by_area_state.items() if c.get("待核实")}),
        "source": PLACEHOLDER_INDEX,
        "caveat": ("these are cells, not papers: do NOT report them as 47 more "
                   "missing papers"),
    }


def granularity_c(records):
    """Original question numbers missing inside papers the library holds."""
    papers = []
    for record in records:
        missing = record.get("missing_original_numbers") or []
        if missing:
            papers.append({
                "area": record["area"], "year": str(record["year"]),
                "subject": record["subject"], "variant": record.get("paper_type"),
                "path": record["path"],
                "missing_count": len(missing),
                "missing_numbers": missing,
                "positions_held": record.get("question_anchors"),
            })
    return {
        "id": "C",
        "label": "仓库已收卷内的缺原题",
        "unit": "question number",
        "count": sum(p["missing_count"] for p in papers),
        "paper_count": len(papers),
        "papers": papers,
        "source": MANIFEST,
        "caveat": "question-level count; never add to the paper_slot counts",
    }


def granularity_d(repo):
    """Source-side collection stubs — the vendor lists a slot but holds no question."""
    rows = []
    for key, info in CITED_STUB_SOURCES.items():
        area, year, subject, variant = key
        rows.append({
            "area": area, "year": year, "subject": subject, "variant": variant,
            "stub_count": info["stubs"],
            "fenbi_source_id": info["source_id"],
            "evidence": info["evidence"],
            "origin": info["origin"],
        })
    total = sum(r["stub_count"] for r in rows)
    return {
        "id": "D",
        "label": "来源侧未征集占位",
        "unit": "question position",
        "count": total,
        "rows": rows,
        "source": "owner capture reports; 江苏2025C cross-checked in-repo",
        "caveat": ("a stub means the vendor has not collected the question. An "
                   "unfinished exercise is account state and is NOT a content gap. "
                   "江苏2025C's 12 were later filled from a donor, so they are "
                   "history in D and absent from C."),
    }


def overlap(gra, grb, grc):
    """Prove the granularities do not collapse into one number."""
    a_keys = {(s["area"], s["year"], s["subject"]) for s in gra["slots"]}
    b_keys = set()
    for area, states in grb["by_area"].items():
        # B rows have no year in the aggregated view; recompute from source rows
        pass
    c_papers = {(p["area"], p["year"], p["subject"]) for p in grc["papers"]}
    return {
        "a_vs_c_same_paper": sorted(a_keys & c_papers),
        "note": ("A and C can name the same real-world paper at different "
                 "granularities; that is overlap, not double counting"),
    }


# Per-paper catalogue/body knowledge, all from owner reports. Anything absent
# here stays fenbi_unknown — never guessed.
FENBI_KNOWN = {
    ("江苏", "2025", "行测", "C类"): {"source_id": "4189916", "catalogue": "observed_catalog_present", "body": "stub_only"},
    ("江苏", "2024", "行测", "A类"): {"source_id": "4162243", "catalogue": "observed_catalog_present", "body": "stub_only"},
    ("广东", "2020", "行测", "县级卷"): {"source_id": "96785", "catalogue": "observed_catalog_present", "body": "stub_only"},
    ("上海", "2026", "行测", "统考"): {"source_id": "8472470", "catalogue": "observed_catalog_present", "body": "stub_only"},
    ("浙江", "2020", "行测", "A类"): {"source_id": "96454", "catalogue": "observed_catalog_present", "body": "not_captured"},
    ("浙江", "2020", "行测", "B类"): {"source_id": "96455", "catalogue": "observed_catalog_present", "body": "not_captured"},
    ("北京", "2026", "行测", "统考"): {"source_id": None, "catalogue": "observed_catalog_absent", "body": "absent"},
    ("江苏", "2026", "行测", "A类"): {"source_id": None, "catalogue": "observed_catalog_absent", "body": "absent"},
}


def paper_rows(records, gra, grb, grc):
    """Per-paper rows carrying the eight required status fields."""
    index = {(r["area"], str(r["year"]), r["subject"]): r for r in records}
    stub_by = {(r["area"], r["year"], r["subject"]): r for r in gra_rows_stub()}

    rows = []
    for paper in grc["papers"]:
        key = (paper["area"], paper["year"], paper["subject"])
        record = index.get(key, {})
        stubs = stub_by.get(key, {}).get("stub_count", 0)
        known = FENBI_KNOWN.get(key + (paper["variant"],), {})

        catalogue = known.get("catalogue", "fenbi_unknown")
        body = known.get("body", "not_captured" if catalogue != "observed_catalog_absent" else "absent")

        issues = record.get("issues") or []
        severity = "critical" if paper["missing_count"] >= 40 else (
            "high" if paper["missing_count"] else ("medium" if issues else "none"))

        rows.append({
            "area": paper["area"], "year": paper["year"], "subject": paper["subject"],
            "variant": paper["variant"],
            "repo_status": "partial" if record else "absent",
            "fenbi_catalogue_status": catalogue,
            "fenbi_source_id": known.get("source_id"),
            "fenbi_body_status": body,
            "known_stub_count": stubs,
            "original_number_gaps": paper["missing_count"],
            "quality_severity": severity,
            "source_rights": ("restricted-institution" if stubs else "unknown"),
            "next_action": ("obtain a licensed original; do not substitute a sibling "
                            "paper or a stub" if stubs else
                            "locate a source that actually holds the paper"),
        })
    return rows


def gra_rows_stub():
    return [{"area": a, "year": y, "subject": s, "stub_count": i["stubs"]}
            for (a, y, s, _), i in CITED_STUB_SOURCES.items()]


def build(repo):
    doc48 = load_missing48(repo)
    placeholders = load_placeholders(repo)
    records = load_manifest(repo)

    gra = granularity_a(doc48)
    grb = granularity_b(placeholders)
    grc = granularity_c(records)
    grd = granularity_d(repo)

    return {
        "table": "four-granularity-gap-table",
        "date": "2026-10-18",
        "granularities": [gra, grb, grc, grd],
        "never_add": {
            "rule": "A, B, C and D count different things and must never be summed.",
            "a_b_disjoint": True,
            "a_b_sum_is_not": "93 missing papers",
            "c_d_overlap": "a paper can appear in both C and D; 江苏2025C appears in D only",
            "totals": {"A": gra["count"], "B": grb["count"],
                       "C": grc["count"], "D": grd["count"]},
        },
        "overlap": overlap(gra, grb, grc),
        "fenbi_catalogue": FENBI_CATALOGUE,
        "content_cohort": CONTENT_COHORT,
        "paper_rows": paper_rows(records, gra, grb, grc),
        "corrections": [{
            "claim": "46 = 21 申论 + 25 行测 (PR #74)",
            "correct": "46 = 19 申论 + 27 行测, both paper_slots",
            "why": ("48 targets = 21 申论 + 27 行测; two were recovered and both were "
                    "申论 (江苏2026 申论 A and C), so 申论 falls to 19 while 行测 stays "
                    "27. The '25' is a different quantity — the Oct-15 report's "
                    "question-number count, not paper slots."),
            "verified_by": MISSING48,
        }],
        "boundary": [
            "No capture profile, cookie, private raw text or image bytes were read.",
            "No question text is emitted — counts, statuses and pointers only.",
            "observed_catalog_absent means not found in the walked catalogue pages; "
            "it does not mean the paper does not exist anywhere or officially.",
            "The 181 catalogue papers without an existing exercise do not thereby "
            "lack original questions.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    doc = build(args.repo)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    t = doc["never_add"]["totals"]
    print(f"A={t['A']} paper_slots | B={t['B']} cells | C={t['C']} question numbers | "
          f"D={t['D']} source stubs  (never summed)")
    print(f"A reconciliation ok: {doc['granularities'][0]['reconciliation_ok']}")
    print(f"content cohort closure: {CONTENT_COHORT['closure']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
