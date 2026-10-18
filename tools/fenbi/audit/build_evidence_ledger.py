#!/usr/bin/env python3
"""Build the published missing-25 evidence ledger from fresh audit results.

This assembles reports/FENBI-MISSING25-EVIDENCE-20261017.json from the output of
gap_audit.py and donor_compare.py, so the numbers in the committed report are
always the numbers those scripts produce — re-running this regenerates it.

No question text, no third-party documents and no credentials are involved: the
ledger carries source pointers, digests, similarity scores and verdicts only.

Usage:
    python3 tools/fenbi/audit/build_evidence_ledger.py [--repo DIR] [--out FILE]
                                                       [--probes DIR]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import default_repo_root  # noqa: E402
import donor_compare  # noqa: E402
import gap_audit  # noqa: E402

# Which papers were declared missing, and which of the four are still missing at
# the audited head. Kept explicit so a change in either set is a visible edit.
REPORT_BASELINE_SHA = "f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab"
AUDITED_HEAD_SHA = "e1feb5187ec3544cde62a1a128a6269a8d63011b"

# Hand-written analysis per paper. Mechanical numbers come from the scripts; the
# prose explains what the numbers do and do not establish.
PAPER_NOTES = {
    "广东2020县级卷": {
        "verdict": "GENUINE_GAP",
        "confidence": "high",
        "evidence": [
            "Pinned reference (崖门 PDF, sha256 verified) has a text layer with 93 "
            "numbered questions and exactly 69-75 absent — the library mirrors its "
            "source of record.",
            "Independent 100-question edition (星光公考) supplies the numbers but fills "
            "these slots with a collection notice and four dummy options.",
        ],
        "remaining_reason": ("Official paper unpublished; every reachable recollection "
                             "edition is placeholder-bound at these numbers."),
    },
    "江苏2024A类": {
        "verdict": "GENUINE_GAP",
        "confidence": "high",
        "evidence": [
            "Pinned reference (上岸通) shows a collection-pending notice with absent "
            "options at all four numbers.",
            "Independent 展鸿 edition prints its own 'not yet collected' notice at the "
            "same four numbers.",
        ],
        "remaining_reason": ("Both the pinned source and the reachable independent "
                             "edition placehold these numbers."),
    },
    "江苏2025C类": {
        "verdict": "BACKFILLED_IN_PR20_INDEPENDENT_SOURCE_NOT_REACHABLE",
        "confidence": "medium-low",
        "evidence": [
            "At the report baseline this paper declared 12 missing numbers and held "
            "118/130; at the audited head it holds 130/130 with 缺失原题号 emptied.",
            f"All 12 restored blocks are identical to the donor paper's blocks after "
            f"whitespace/punctuation folding, and 4 of them take a DIFFERENT question "
            f"number from the donor.",
            "The backfill's own basis is a third-party scan recorded as a URL plus "
            "sha256; that host currently fails DNS, the document is not archived in "
            "this repository, and none of the 6 recorded scan-clip images can be "
            "located by digest in the tree.",
            "The remaining 6 of the 12 record no scan clip at all.",
            "Every other reachable edition still placeholds all 12 numbers.",
        ],
        "not_disproven": ("This is NOT evidence that the backfill is wrong. It states only "
                          "that the mapping from C-class number to A-class donor cannot be "
                          "re-verified from this environment, because the document that "
                          "would settle it is currently unreachable and unarchived."),
        "remaining_reason": ("Paper-identity of the restored blocks is unverifiable here; "
                             "the cross-numbered four depend on it most."),
    },
    "浙江2020A类": {
        "verdict": "GENUINE_GAP",
        "confidence": "high",
        "evidence": [
            "Pinned reference (上岸通) shows a collection-pending notice at both numbers.",
            "Pinned secondary PDF (whose own filename flags the two missing questions) "
            "prints a recollection placeholder in both slots.",
            "A third source listed by the report now returns HTTP 404.",
        ],
        "remaining_reason": "No reachable edition carries a stem for these two numbers.",
    },
}


def per_item_ledger(gap_doc, donor_doc):
    donor_by_number = {i["number"]: i for i in donor_doc["items"]}
    items = []
    for paper in gap_doc["papers"]:
        note = PAPER_NOTES[paper["label"]]
        for number in paper["declared_missing"]:
            restored = number in paper.get("restored_numbers", [])
            entry = {
                "id": f"{paper['label']}-{number}",
                "paper": paper["path"],
                "label": paper["label"],
                "number": number,
                "state_at_report_baseline": "ABSENT_FROM_LIBRARY",
                "state_at_audited_head": ("RESTORED" if restored else "STILL_ABSENT"),
                "verdict": note["verdict"],
                "confidence": note["confidence"],
                "remaining_reason": note["remaining_reason"],
                "repair_draft_produced": False,
            }
            if restored and number in donor_by_number:
                d = donor_by_number[number]
                entry["restoration"] = {
                    "donor_paper": donor_doc["donor"],
                    "donor_number": d["declared_donor_number"],
                    "cross_numbered": d["donor_number_differs_from_recipient"],
                    "folded_identical_to_donor": d.get("folded_identical_to_donor"),
                    "folded_similarity": d.get("folded_similarity"),
                    "restored_block_sha256": d.get("recipient_block_sha256"),
                    "donor_block_sha256": d.get("donor_block_sha256"),
                    "scan_clip_metadata_count": d["saved_scan_clip_metadata_count"],
                    "scan_clip_image_archived_in_repo": False,
                }
            items.append(entry)
    return items


def load_probes(probe_dir):
    """Merge reference_probe.py outputs, if the caller supplied a directory.

    The probe records the path of the copy it read. Those paths are local to
    whoever ran it, so only the basename is carried into the published ledger —
    the committed report should not embed anyone's working-directory layout.
    """
    if not probe_dir or not os.path.isdir(probe_dir):
        return []
    probes = []
    for name in sorted(os.listdir(probe_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(probe_dir, name), encoding="utf-8") as fh:
            try:
                probe = json.load(fh)
            except json.JSONDecodeError:
                continue
        if probe.get("source_file"):
            probe["source_file"] = os.path.basename(probe["source_file"])
            probe["source_file_note"] = "basename only; the copy read is not committed"
        probes.append(probe)
    return probes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--out", default=os.path.join(
        default_repo_root(), "reports", "FENBI-MISSING25-EVIDENCE-20261017.json"))
    ap.add_argument("--probes", default=None,
                    help="directory of reference_probe.py outputs to merge (optional)")
    args = ap.parse_args()

    gap_doc = {
        "papers": [gap_audit.audit_paper(args.repo, rel, label, nums)
                   for rel, label, nums in gap_audit.TARGETS],
    }
    donor_doc = donor_compare.build_report(
        args.repo, os.path.join(args.repo, donor_compare.DEFAULT_PACK))
    items = per_item_ledger(gap_doc, donor_doc)

    doc = {
        "report": "FENBI-MISSING25-EVIDENCE-20261017",
        "date": "2026-10-17",
        "subject": ("Evidence audit of the 25 missing 行测 original questions named in "
                    "reports/FULL-REPAIR-20261015.md"),
        "scope": {
            "reported_missing_original_questions": 25,
            "library_wide_missing_aptitude_items": 106,
            "statement": (
                "This audit covers only the 25 items the report names: 广东2020县级 69-75; "
                "江苏2024A 76/96/110/111; 江苏2025C 27/29/35/36/37/42/75/77/78/80/81/85; "
                "浙江2020A 49/50. The 106 figure is a larger, different set and is not "
                "audited here."),
        },
        "baseline": {
            "report_baseline_sha": REPORT_BASELINE_SHA,
            "audited_head_sha": AUDITED_HEAD_SHA,
            "note": ("The report's '25' describes its own baseline. Between that baseline "
                     "and the audited head, the 江苏2025C items were restored, so the "
                     "number no longer describes the current tree for that paper."),
        },
        "headline": [
            f"{gap_doc['papers'][0]['label']} and the other declared gaps: "
            f"{sum(len(p.get('still_absent_numbers', [])) for p in gap_doc['papers'])} items "
            f"are still absent at the audited head and are confirmed missing in every "
            f"reachable source of record.",
            f"{sum(len(p.get('restored_numbers', [])) for p in gap_doc['papers'])} items "
            f"(江苏2025C) were restored between the report baseline and the audited head.",
            "All of the report's pinned reference documents were fetched and their "
            "sha256 values still match the recorded ones, so its 固定源证据 is intact.",
            "The restored items' independent basis (a third-party scan) is currently "
            "unreachable and is not archived in this repository; that is a statement "
            "about verifiability from here, not a finding that the restoration is wrong.",
            "No repair draft was produced: no item has verbatim stem+options+figure "
            "evidence reachable from this environment.",
        ],
        "gap_audit": {
            "papers": gap_doc["papers"],
            "summary": {
                "declared": sum(len(p["declared_missing"]) for p in gap_doc["papers"]),
                "still_absent": sum(len(p.get("still_absent_numbers", []))
                                    for p in gap_doc["papers"]),
                "restored": sum(len(p.get("restored_numbers", []))
                                for p in gap_doc["papers"]),
            },
        },
        "backfill_provenance": donor_doc,
        "reference_probes": load_probes(args.probes),
        "papers": [{
            "label": label,
            "path": next(p["path"] for p in gap_doc["papers"] if p["label"] == label),
            "verdict": note["verdict"],
            "confidence": note["confidence"],
            "evidence": note["evidence"],
            "not_disproven": note.get("not_disproven"),
        } for label, note in PAPER_NOTES.items()],
        "items": items,
        "summary": {
            "total": len(items),
            "still_absent": sum(1 for i in items if i["state_at_audited_head"] == "STILL_ABSENT"),
            "restored": sum(1 for i in items if i["state_at_audited_head"] == "RESTORED"),
            "cross_numbered_restorations": sum(
                1 for i in items
                if i.get("restoration", {}).get("cross_numbered")),
            "restorations_without_scan_clip_metadata": sum(
                1 for i in items if i.get("restoration")
                and not i["restoration"]["scan_clip_metadata_count"]),
            "verbatim_recovery_candidates_found": 0,
            "repair_drafts_produced": 0,
        },
        "boundary": [
            "No login, captcha or paywall was bypassed; no interface was guessed and no "
            "question identifier was enumerated.",
            "Only URLs already recorded in this repository's own reports were requested.",
            "No third-party document, screenshot, cookie, phone number or token-bearing "
            "URL is included in this report; sources are cited by URL and digest only.",
            "No AI-generated or inferred question text was written anywhere, and no file "
            "under 国考/, 省考/, 图片/ or catalog/ was modified.",
            "A host that fails DNS today is reported as a DNS failure, not as a permanent "
            "domain failure.",
        ],
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"wrote {args.out}")
    print(json.dumps(doc["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
