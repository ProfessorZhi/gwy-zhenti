#!/usr/bin/env python3
"""Offline fenbi target inventory built from the repository's own catalog.

Reads `catalog/manifest.jsonl` and produces:
  1. the full distinct paper-identity list (area x year x subject x canonical 卷型),
  2. a ranked shortlist of papers with the most information to gain from a
     source-catalogue lookup,
  3. a directory-only handoff list for whoever runs the capture.

This tool never touches the network, never reads a capture profile, and never
emits question text. It only restates catalog metadata.

Three rules it enforces, because getting them wrong has already cost this
project real work:

* **Identity is (area, year, subject, canonical 卷型).** Two records with the
  same tuple are a duplicate and are reported as such; the tool refuses to
  silently merge them.
* **An unknown fenbi id is never capture-ready.** `capture_ready` is true only
  when the id is known AND the paper has not already been captured. Anything
  else is explicitly false with a reason.
* **A paper's question count is not its recovered count.** `declared_questions`
  is what the paper claims; `question_anchors` is what the library actually
  holds. A missing number is a gap even though the paper "has 135 questions".

Usage:
    python3 tools/fenbi/audit/fenbi_target_inventory.py [--repo DIR] \
        [--top 50] [--handoff 30] [--out FILE] [--handoff-out FILE]
"""

import argparse
import json
import os
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import default_repo_root  # noqa: E402

MANIFEST = "catalog/manifest.jsonl"

# Alias canonicalisation. Deliberately conservative: only forms that differ by a
# trailing 卷/类 marker on the SAME stem are merged. Anything that could be a
# genuinely different paper is left alone and recorded under `not_merged`.
ALIAS_MAP = {
    "乡镇卷": "乡镇", "县乡卷": "县乡", "县级卷": "县级", "市县卷": "市县",
    "省市卷": "省市", "省级卷": "省级", "行政执法卷": "行政执法",
    "通用卷": "通用", "统考卷": "统考",
}

# Forms that look like aliases but are NOT merged, with the reason. 甲/乙 and
# 一/二/三卷 are separate papers in their provinces; A卷/B卷 are not assumed to be
# the same taxonomy as A类/B类.
NOT_MERGED = {
    "A卷/B卷": "A卷 refers to a province's own paper split; A类/B类 is a different taxonomy",
    "甲级/乙级": "distinct papers (province-specific rank split)",
    "一卷/二卷/三卷": "distinct papers in the same year",
    "上半年/下半年": "distinct exams",
    "乡镇/县级/县乡": "distinct recruitment tracks, kept separate even when one stems from another",
}

# fenbi source ids observed in this repository's own reports. Anything not here
# is null — never inferred, never guessed.
KNOWN_FENBI_IDS = {
    ("浙江", "2026", "行测", "C类"): {"id": "8399763", "status": "captured",
                                  "evidence": "reports/FENBI-LIVE-FIRST-BATCH-20261017.md"},
    ("浙江", "2020", "行测", "A类"): {"id": "96454", "status": "catalog-confirmed-only",
                                  "evidence": "reports/FENBI-LIVE-SECOND-BATCH-20261017.md"},
    ("浙江", "2020", "行测", "B类"): {"id": "96455", "status": "catalog-confirmed-only",
                                  "evidence": "reports/FENBI-LIVE-SECOND-BATCH-20261017.md"},
    ("江苏", "2025", "行测", "C类"): {"id": "4189916", "status": "initialized-captured",
                                  "evidence": "reports/FENBI-LIVE-THIRD-BATCH-20261017.md"},
    ("江苏", "2024", "行测", "A类"): {"id": "4162243", "status": "initialized-captured",
                                  "evidence": "reports/FENBI-LIVE-THIRD-BATCH-20261017.md"},
    ("广东", "2020", "行测", "县级"): {"id": "96785", "status": "initialized-captured",
                                  "evidence": "reports/FENBI-LIVE-THIRD-BATCH-20261017.md"},
}

# Issues that describe a specific, checkable defect rather than the broad
# "module order never verified" notice carried by most of the library.
SPECIFIC_ISSUE_MARKERS = ("缺", "不一致", "未收录", "争议", "非连续")


def canonical_type(paper_type):
    """Canonical 卷型 and whether an alias rule was applied."""
    if not paper_type:
        return "未标注", False
    if paper_type in ALIAS_MAP:
        return ALIAS_MAP[paper_type], True
    return paper_type, False


def load_manifest(repo):
    path = os.path.join(repo, MANIFEST)
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def raw_identity(record):
    """Authoritative identity: the paper_type exactly as the manifest states it.

    Distinctness is judged on this. 1,169 records give 1,169 raw identities.
    """
    return (record["area"], str(record["year"]), record["subject"],
            record.get("paper_type"))


def identity(record):
    """Canonicalised identity, used ONLY to surface near-duplicates for curation.

    This deliberately collapses `X` and `X卷`. On this catalog every such collapse
    is divergent content, so the value must never be used as a dedup key.
    """
    canonical, _ = canonical_type(record.get("paper_type"))
    return (record["area"], str(record["year"]), record["subject"], canonical)


def has_specific_issue(record):
    for issue in record.get("issues") or []:
        text = str(issue)
        if any(marker in text for marker in SPECIFIC_ISSUE_MARKERS):
            return True
    return False


def has_order_issue(record):
    return any("题序未获原卷证据核对" in str(i) for i in record.get("issues") or [])


def information_gain(record):
    """Rank by what a source-catalogue lookup could actually resolve.

    Weighted so the real gaps dominate: a missing original question is worth far
    more than a generic order-verification notice, which hundreds of papers
    carry.
    """
    missing_original = len(record.get("missing_original_numbers") or [])
    missing_option = len(record.get("missing_option_numbers") or [])
    missing_shared = len(record.get("missing_shared_condition_numbers") or [])
    missing_stem_condition = len(record.get("missing_stem_condition_numbers") or [])
    missing_stem_figure = len(record.get("missing_stem_figure_numbers") or [])
    missing_answer = len(record.get("missing_answer_numbers") or [])

    canonical, _ = canonical_type(record.get("paper_type"))
    type_ambiguous = canonical == "统考"

    score = (
        1000 * missing_original
        + 200 * missing_option
        + 150 * missing_shared
        + 100 * missing_stem_condition
        + 100 * missing_stem_figure
        + 50 * missing_answer
        + 20 * (1 if has_specific_issue(record) else 0)
        + 5 * (1 if has_order_issue(record) else 0)
        + 3 * (1 if type_ambiguous else 0)
    )
    return {
        "score": score,
        "components": {
            "missing_original_numbers": missing_original,
            "missing_option_numbers": missing_option,
            "missing_shared_condition_numbers": missing_shared,
            "missing_stem_condition_numbers": missing_stem_condition,
            "missing_stem_figure_numbers": missing_stem_figure,
            "missing_answer_numbers": missing_answer,
            "specific_defect": has_specific_issue(record),
            "order_unverified": has_order_issue(record),
            "type_ambiguous": type_ambiguous,
        },
    }


def capture_view(record):
    """Known fenbi id and capture state, with an explicit readiness rule."""
    key = identity(record)
    known = KNOWN_FENBI_IDS.get(key)
    if known:
        fenbi_id = known["id"]
        status = known["status"]
        evidence = known["evidence"]
    else:
        fenbi_id = None
        status = "not-observed"
        evidence = None

    already_captured = status in ("captured", "initialized-captured")
    if fenbi_id is None:
        ready, reason = False, "fenbi-id-unknown"
    elif already_captured:
        ready, reason = False, f"already-{status}"
    else:
        ready, reason = True, "id-known-and-not-yet-captured"

    return {
        "fenbi_source_id": fenbi_id,
        "capture_status": status,
        "evidence": evidence,
        "capture_ready": ready,
        "capture_ready_reason": reason,
    }


def original_total_estimate(record):
    """Held positions + missing numbers, when both are known.

    `declared_questions` in this manifest is the CURRENT FILE's declared count
    (it equals `question_anchors` throughout), not the original paper's size. The
    original size has to be derived, and only when the missing count is known.
    """
    held = record.get("question_anchors")
    missing = len(record.get("missing_original_numbers") or [])
    if held is None or not missing:
        return None
    return held + missing


def identity_caveat(record):
    """Surface the manifest's own warning when the 卷型 label is not a real one."""
    notes = record.get("notes") or []
    for note in notes:
        text = str(note)
        if "未归属卷型" in text or "不自动视为独立原卷" in text:
            return {"flag": "paper-type-label-is-internal-placeholder", "note": text}
    return None


def paper_entry(record, rank=None):
    canonical, alias_applied = canonical_type(record.get("paper_type"))
    gain = information_gain(record)
    declared = record.get("declared_questions")
    anchors = record.get("question_anchors")
    missing = record.get("missing_original_numbers") or []
    entry = {
        "identity": {
            "area": record["area"],
            "year": str(record["year"]),
            "subject": record["subject"],
            "paper_type": record.get("paper_type"),
            "canonical_type": canonical,
            "alias_applied": alias_applied,
            "type_ambiguous": canonical == "统考",
            "caveat": identity_caveat(record),
        },
        "repository_path": record["path"],
        "sha256": record.get("sha256"),
        "question_state": {
            "declared_total": declared,
            "positions_held": anchors,
            "original_total_estimate": original_total_estimate(record),
            "missing_original_numbers": missing,
            "missing_original_count": len(missing),
            "note": ("declared_total is the current file's own count; positions_held is what "
                     "the library has; original_total_estimate = held + missing. A source "
                     "placeholder is never a held question."),
        },
        "image_references": record.get("image_references"),
        "information_gain": gain,
        "capture": capture_view(record),
    }
    if rank is not None:
        entry["rank"] = rank
    return entry


def alias_collisions(records):
    """Groups that canonicalisation would merge — reported, never merged.

    Measured on this catalog: every such group turns out to have DIFFERENT bytes
    and, in most cases, a different question count (4 vs 2-3). They are distinct
    versions sharing an identity tuple, not duplicates. Merging them silently
    would delete real content, so the tool only reports them and suggests which
    record looks fuller.
    """
    groups = {}
    for record in records:
        groups.setdefault(identity(record), []).append(record)

    collisions = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        digests = {m.get("sha256") for m in members}
        full = max(members, key=lambda m: (m.get("question_anchors") or 0))
        collisions.append({
            "canonical_identity": list(key),
            "members": [{
                "path": m["path"],
                "paper_type": m.get("paper_type"),
                "sha256": m.get("sha256"),
                "question_anchors": m.get("question_anchors"),
                "declared_questions": m.get("declared_questions"),
            } for m in members],
            "byte_identical": len(digests) == 1,
            "content_diverges": len(digests) > 1,
            "suggested_survivor": full["path"],
            "auto_merge": False,
            "reason": ("divergent content under one identity — needs curation, "
                       "not a dedup"),
        })
    return collisions


def build(repo, top=50, handoff=30):
    records = load_manifest(repo)

    # Raw identity is authoritative: (area, year, subject, paper_type).
    # Canonicalisation is used only to *surface* near-duplicates for curation.
    raw_keys = Counter(raw_identity(r) for r in records)
    raw_duplicates = [{"identity": list(k), "count": v}
                      for k, v in raw_keys.items() if v > 1]
    collisions = alias_collisions(records)

    alias_hits = Counter()
    for record in records:
        _, applied = canonical_type(record.get("paper_type"))
        if applied:
            alias_hits[record.get("paper_type")] += 1

    ranked = sorted(records, key=lambda r: (-information_gain(r)["score"], r["path"]))
    shortlist = [paper_entry(r, rank=i + 1) for i, r in enumerate(ranked[:top])]

    # Handoff: directory identity only, for the runner to look up in the catalog.
    # A known id is included where one has been observed; otherwise it is null and
    # the entry is explicitly NOT capture-ready — it is a lookup target, not an
    # instruction to open a specific paper.
    handoff_entries = []
    for record in ranked:
        view = capture_view(record)
        if view["capture_status"] in ("captured", "initialized-captured"):
            continue
        handoff_entries.append({
            "area": record["area"],
            "year": str(record["year"]),
            "subject": record["subject"],
            "paper_type": record.get("paper_type"),
            "canonical_type": canonical_type(record.get("paper_type"))[0],
            "fenbi_source_id": view["fenbi_source_id"],
            "id_source": ("observed-in-repo" if view["fenbi_source_id"] else "unknown"),
            "catalog_lookup_needed": view["fenbi_source_id"] is None,
            "capture_ready": view["capture_ready"],
            "capture_ready_reason": view["capture_ready_reason"],
            "capture_status": view["capture_status"],
            "evidence": view["evidence"],
            "repository_path": record["path"],
            "questions_to_look_for": record.get("question_anchors"),
            "original_total_estimate": original_total_estimate(record),
            "missing_original_count": len(record.get("missing_original_numbers") or []),
            "identity_caveat": identity_caveat(record),
        })
        if len(handoff_entries) >= handoff:
            break

    known_ids_in_handoff = sum(1 for e in handoff_entries
                               if e["fenbi_source_id"] is not None)

    return {
        "inventory": "fenbi-target-inventory",
        "date": "2026-10-17",
        "source_manifest": MANIFEST,
        "manifest_records": len(records),
        "distinct_identities": len(raw_keys),
        "duplicate_identities": raw_duplicates,
        "alias_collisions": {
            "count": len(collisions),
            "divergent_content": sum(1 for c in collisions if c["content_diverges"]),
            "byte_identical": sum(1 for c in collisions if c["byte_identical"]),
            "policy": ("A canonical identity that merges records with different bytes is "
                       "NEVER auto-merged; it is reported for curation with a suggested "
                       "survivor."),
            "groups": collisions,
        },
        "alias_normalisation": {
            "map": ALIAS_MAP,
            "applied_counts": dict(alias_hits),
            "deliberately_not_merged": NOT_MERGED,
        },
        "coverage": {
            "by_subject": dict(Counter(r["subject"] for r in records)),
            "by_area": dict(Counter(r["area"] for r in records).most_common()),
            "years": sorted({str(r["year"]) for r in records}),
            "paper_types_raw": dict(Counter(r.get("paper_type") for r in records).most_common()),
        },
        "missing_original_summary": {
            "papers_with_gaps": sum(1 for r in records
                                    if r.get("missing_original_numbers")),
            "total_missing_numbers": sum(len(r.get("missing_original_numbers") or [])
                                         for r in records),
            "breakdown": [
                {"path": r["path"],
                 "count": len(r["missing_original_numbers"]),
                 "numbers": r["missing_original_numbers"]}
                for r in records if r.get("missing_original_numbers")
            ],
        },
        "shortlist_top": shortlist,
        "handoff": {
            "note": ("Identity only. Contains no question text, no answers, no images and no "
                     "credentials. Entries with a null fenbi id are LOOKUP TARGETS for the "
                     "directory, never capture-ready."),
            "count": len(handoff_entries),
            "with_known_id": known_ids_in_handoff,
            "lookup_needed": len(handoff_entries) - known_ids_in_handoff,
            "entries": handoff_entries,
        },
        "policy": [
            "An unknown fenbi id is null and is never capture-ready.",
            "A canonical identity merging divergent bytes is reported, never auto-merged.",
            "declared_total is not the recovered count; a source placeholder is not a question.",
            "This inventory is metadata only and performs no network access.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--handoff", type=int, default=30)
    ap.add_argument("--out", default=None)
    ap.add_argument("--handoff-out", default=None,
                    help="write the directory-only handoff list to its own file")
    args = ap.parse_args()

    doc = build(args.repo, args.top, args.handoff)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    if args.handoff_out:
        payload = {
            "handoff": "fenbi-directory-targets",
            "date": doc["date"],
            "note": doc["handoff"]["note"],
            "count": doc["handoff"]["count"],
            "entries": doc["handoff"]["entries"],
        }
        with open(args.handoff_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"wrote {args.handoff_out}")

    print(f"records={doc['manifest_records']} distinct={doc['distinct_identities']} "
          f"duplicates={len(doc['duplicate_identities'])}")
    print(f"papers_with_gaps={doc['missing_original_summary']['papers_with_gaps']} "
          f"missing_numbers={doc['missing_original_summary']['total_missing_numbers']}")
    print(f"handoff_entries={doc['handoff']['count']}")
    for e in doc["shortlist_top"][:5]:
        print(f"  #{e['rank']} score={e['information_gain']['score']} "
              f"{e['repository_path']} missing={e['question_state']['missing_original_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
