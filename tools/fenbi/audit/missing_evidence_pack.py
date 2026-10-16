#!/usr/bin/env python3
"""Per-question evidence packages for the 11 confirmed missing questions.

Covers the two papers whose gaps were CONFIRMED to exist on the live source in
the third capture batch:

  江苏2024A (fenbi 4162243): 76, 96, 110, 111
  广东2020县级 (fenbi 96785): 69, 70, 71, 72, 73, 74, 75

For each question it records the number mapping, what the library holds, which
sources establish what, and exactly which evidence is still required before a
repair candidate could be written. It emits **no question text**: the fields a
handoff must supply are listed by name, not filled in.

Two things it is careful about:

* **The mapping.** Both sources were captured with 偏移 = 0, i.e. the source
  numbers questions the same way the library does — original numbering with the
  same gaps. So the correct join is by number and each new question is inserted
  at its own original number. A positional join would have mapped 广东 source 69
  onto library 76; the pack records that explicitly so it cannot be repeated.

* **Provenance.** The fenbi paper is a 网友回忆版 — an institution/recollection
  edition. It is not an official paper, and nothing here may be described as
  one. Answers and explanations are not published by the source and stay
  unknown.

Usage:
    python3 tools/fenbi/audit/missing_evidence_pack.py [--repo DIR] [--out FILE]
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    default_repo_root, parse_frontmatter, parse_paper, read_text,
)

# The capture report that establishes source-side existence for these numbers.
# Pinned by commit and by content digest so the claim can be re-checked.
THIRD_BATCH = {
    "path": "reports/FENBI-LIVE-THIRD-BATCH-20261017.md",
    "commit": "a23c5bd275bbf6088995e27872574ef1562e6f3f",
    "pr": 29,
    "sha256": "c836e2f3939982df34069819d613252fdd77ac691abd9e0d625b211e909bf599",
    "establishes": "source-side existence of the missing numbers, with 偏移 = 0",
}

# What a handoff must supply for a candidate to become writable.
REQUIRED_FIELDS = [
    "stem_text",            # or a digest plus the original bytes, for verification
    "options[]",            # label + text for every option, in order
    "material_linkage",     # which shared material the question hangs off, if any
    "figure_bytes+sha256",  # every figure/formula image, by content digest
    "source_number",        # the source's own numbering for this question
]

PAPERS = (
    {
        "label": "江苏2024A类",
        "path": "省考/江苏/2024/行测-A类.md",
        "fenbi_source_id": "4162243",
        "source_question_count": 135,
        "capture": "papers/js-2024-xingce-a-4162243/",
        "numbers": [76, 96, 110, 111],
        "source_kind": "recollection-institution",
        "source_title_kind": "网友回忆版",
        "confirm_note": ("Source holds 135 questions, the library 131. The four source-only "
                         "numbers are exactly 76/96/110/111 — the library's declared gaps."),
    },
    {
        "label": "广东2020县级卷",
        "path": "省考/广东/2020/行测-县级卷.md",
        "fenbi_source_id": "96785",
        "source_question_count": 100,
        "capture": "papers/gd-2020-xingce-county-96785/",
        "numbers": [69, 70, 71, 72, 73, 74, 75],
        "source_kind": "recollection-institution",
        "source_title_kind": "网友回忆版",
        "confirm_note": ("Source holds 100 questions, the library 93. The seven source-only "
                         "numbers are exactly 69–75 — the library's declared gaps. The "
                         "capture also flags 14 same-number content differences elsewhere "
                         "in this paper, which are a separate question from these gaps."),
    },
)

# Other sources checked in the earlier audit: they confirm the gap but carry no
# content, so they must not be presented as supplying it.
SUPPORTING_SOURCES = [
    {
        "name": "上岸通 fixed reference",
        "role": "pinned by the repo's own report",
        "status": "placeholder-no-content",
        "applies_to": ["江苏2024A类", "广东2020县级卷"],
    },
    {
        "name": "展鸿教育 2024江苏A 真题 PDF",
        "role": "independent institution edition",
        "status": "placeholder-no-content",
        "applies_to": ["江苏2024A类"],
    },
    {
        "name": "星光公考 100题版 广东2020县级",
        "role": "independent institution edition",
        "status": "placeholder-no-content",
        "applies_to": ["广东2020县级卷"],
    },
    {
        "name": "崖门/丫门 pinned PDF 广东2020",
        "role": "pinned by the repo's own report",
        "status": "number-absent-from-source",
        "applies_to": ["广东2020县级卷"],
    },
]


def repo_head(repo):
    try:
        return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return None


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build(repo, third_batch_file=None):
    # The capture report lives on the capture branch, not on this one. Prefer a
    # local copy when given one, so the recorded digest can be re-verified.
    third_batch_local = None
    for candidate in (third_batch_file,
                      os.path.join(repo, THIRD_BATCH["path"])):
        if candidate and os.path.isfile(candidate):
            third_batch_local = candidate
            break
    third_batch_sha = sha256_file(third_batch_local) if third_batch_local else None
    third_batch_verified = (third_batch_sha == THIRD_BATCH["sha256"]
                            if third_batch_sha else None)

    items = []
    for spec in PAPERS:
        full = os.path.join(repo, spec["path"])
        frontmatter, body = parse_frontmatter(read_text(full))
        parsed = parse_paper(body)
        library_numbers = sorted(parsed["questions"])
        library_set = set(library_numbers)
        # The correct join, derived from the actual numbers on both sides.
        source_numbers = list(range(1, spec["source_question_count"] + 1))
        positional_would_use = {
            n: sorted(library_numbers)[n - 1]
            for n in spec["numbers"]
            if n - 1 < len(library_numbers) and sorted(library_numbers)[n - 1] != n
        }

        for number in spec["numbers"]:
            present_in_library = number in library_set
            item = {
                "id": f"{spec['label']}-{number}",
                "paper": spec["path"],
                "label": spec["label"],
                "original_number": number,
                "library": {
                    "heading_present": present_in_library,
                    "state": "already-present" if present_in_library else "absent-gap-preserved",
                },
                "mapping": {
                    "source_number": number,
                    "join": "number",
                    "join_basis": ("source captured with 偏移 = 0: it numbers questions the "
                                   "same way the library does, so source N == library N"),
                    "insert_at_original_number": number,
                    "renumbering_required": False,
                    "positional_join_would_use_library_number": positional_would_use.get(number),
                    "positional_join_is_wrong": number in positional_would_use,
                },
                "source": {
                    "fenbi_source_id": spec["fenbi_source_id"],
                    "capture_dir": spec["capture"],
                    "source_kind": spec["source_kind"],
                    "source_title_kind": spec["source_title_kind"],
                    "is_official": False,
                    "attribution_note": ("Institution/recollection edition (网友回忆版). Must "
                                         "not be described as an official paper."),
                    "evidence_anchor": {
                        "path": THIRD_BATCH["path"],
                        "commit": THIRD_BATCH["commit"],
                        "pr": THIRD_BATCH["pr"],
                        "sha256_recorded": THIRD_BATCH["sha256"],
                        "sha256_local": third_batch_sha,
                        "sha256_verified": third_batch_verified,
                        "verify_hint": ("fetch the file at the recorded commit and pass it "
                                        "with --third-batch-file to re-check the digest"),
                        "establishes": THIRD_BATCH["establishes"],
                    },
                },
                "established": {
                    "existence_on_source": "confirmed",
                    "content_available": "pending-handoff",
                    "answer": "unknown",
                    "explanation": "unknown",
                },
                "required_evidence": list(REQUIRED_FIELDS),
                "provenance_class": spec["source_kind"],
                "repair_state": "candidate-not-written",
                "write_authorization": "not-confirmed",
                "answer_policy": ("The source publishes no answers or explanations. They stay "
                                  "unknown; they are not to be inferred, and no AI-generated "
                                  "option or answer may stand in for source text."),
            }
            items.append(item)

    return {
        "pack": "missing-evidence-pack",
        "date": "2026-10-17",
        "repo_head": repo_head(repo),
        "scope": {
            "papers": len(PAPERS),
            "questions": sum(len(p["numbers"]) for p in PAPERS),
            "statement": ("The 11 questions whose gaps are confirmed to exist on the live "
                          "source. Separate from the 江苏2025C backfill, which must not be "
                          "overwritten."),
        },
        "papers": [{
            "label": p["label"],
            "path": p["path"],
            "fenbi_source_id": p["fenbi_source_id"],
            "source_question_count": p["source_question_count"],
            "library_question_count": len(parse_paper(
                parse_frontmatter(read_text(os.path.join(repo, p["path"])))[1])["questions"]),
            "declared_missing": [int(x) for x in __import__("re").findall(
                r"\d+", parse_frontmatter(
                    read_text(os.path.join(repo, p["path"])))[0].get("缺失原题号", "") or "")],
            "source_kind": p["source_kind"],
            "is_official": False,
            "confirm_note": p["confirm_note"],
        } for p in PAPERS],
        "supporting_sources": SUPPORTING_SOURCES,
        "items": items,
        "authorization_checklist": {
            "state": "NOT CONFIRMED",
            "required_before_writing": [
                "the source's licence/permission for redistribution into this repository",
                "confirmation that the third-batch capture may be used as a repair source",
                "a handoff supplying the per-question evidence fields listed above",
            ],
            "until_confirmed": [
                "no question text is written into 省考/ or any tracked path",
                "full candidate material stays in a gitignored restricted directory",
                "only a machine-readable patch plan, source pointers and digests are published",
            ],
        },
        "restricted_dir_convention": {
            "path": "work/missing25-candidates/",
            "gitignored": True,
            "holds": "full candidate text and image bytes, local only",
        },
        "boundary": [
            "No question text, option text, answer or explanation is included in this pack.",
            "No file under 国考/, 省考/, 图片/ or catalog/ is modified.",
            "The 江苏2025C backfill is not touched: those 12 remain as recorded, with their "
            "own unresolved evidence question.",
            "Nothing here is described as an official paper; the source is a recollection "
            "edition.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--third-batch-file", default=None,
                    help="local copy of the capture report, to re-verify its digest")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    doc = build(args.repo, third_batch_file=args.third_batch_file)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    print(json.dumps(doc["scope"], ensure_ascii=False))
    for paper in doc["papers"]:
        print(f"  {paper['label']:14} library={paper['library_question_count']:>4} "
              f"source={paper['source_question_count']:>4} "
              f"declared_missing={paper['declared_missing']}")
    shifted = [i["id"] for i in doc["items"]
               if i["mapping"]["positional_join_is_wrong"]]
    print("  items where a positional join would mis-map:", shifted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
