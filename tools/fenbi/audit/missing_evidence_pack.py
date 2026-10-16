#!/usr/bin/env python3
"""Per-question evidence state for the 11 gap numbers, after the PR #33 correction.

Scope: the numbers the library leaves empty in
  江苏2024A (fenbi 4162243): 76, 96, 110, 111
  广东2020县级 (fenbi 96785): 69, 70, 71, 72, 73, 74, 75

**Corrected 2026-10-17.** An earlier version of this pack asserted that these 11
questions were "confirmed present on the source, content captured". That was
wrong. The source lists these NUMBERS, but at every one of them the page holds a
collection stub — "题目正在全力以赴征集…" — not question text. A question number,
or a question container in the DOM, proves only that a slot exists.

`reports/FENBI-AUDIT-CORRECTION-20261017.md` (PR #33, by the capture owner) is the
authority for that correction, having audited the captured DOM per item. This pack
takes it as given and records, per question, that no source content is available.

So: candidate status is **blocked**, `source_content_available` is **false**, and
nothing here asks anyone to authorise a repair from the fenbi capture. Writing
stays unauthorised, and the source is never described as an official paper.

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
    default_repo_root, detect_placeholders, parse_frontmatter, parse_paper, read_text,
)

# The correction that establishes what the source actually holds at these numbers.
CORRECTION = {
    "path": "reports/FENBI-AUDIT-CORRECTION-20261017.md",
    "commit": "f19ff2fadb6ee765a2f5c842f1827029460ca623",
    "pr": 33,
    "sha256": "0ad5ff44b9d9cedcf34f6f9a6d76f2841bd9a0aebdce1512ec989a3989e6dc2a",
    "authority": ("written by the capture owner from a per-item audit of the captured "
                  "DOM; this pack treats it as the authority for what the source holds"),
}

# The earlier, now-retracted evidence this pack was built on.
SUPERSEDED = {
    "path": "reports/FENBI-LIVE-THIRD-BATCH-20261017.md",
    "pr": 29,
    "retracted_claim": ("that the 4 江苏2024A and 7 广东2020 gap numbers were "
                        "'真实存在且可见' and '已被本次采集取得' — i.e. captured content"),
    "why_wrong": ("the aligner reported `no-safe-unique-match`, which was read as "
                  "'content differs'. It actually meant the source slot holds a "
                  "collection stub, so there was nothing to match."),
}

# What a handoff would have to supply for a candidate to become writable — still
# unmet, since no source currently holds any of this.
REQUIRED_FIELDS = [
    "a non-stub stem, from a source that has actually collected the question",
    "options[] (label + text, in order)",
    "material_linkage (which shared material the question hangs off, if any)",
    "figure_bytes + sha256 for every figure/formula",
    "the source's own numbering for the question",
    "the licence/permission to redistribute that source into this repository",
]

PAPERS = (
    {
        "label": "江苏2024A类",
        "path": "省考/江苏/2024/行测-A类.md",
        "fenbi_source_id": "4162243",
        "source_question_count": 135,
        "capture": "papers/js-2024-xingce-a-4162243/",
        "numbers": [76, 96, 110, 111],
        "stub_numbers": [76, 96, 110, 111],
        "note": ("The four source-only numbers coincide exactly with the library's "
                 "declared gaps — but each is an uncollected stub, so the source "
                 "cannot supply these questions."),
    },
    {
        "label": "广东2020县级卷",
        "path": "省考/广东/2020/行测-县级卷.md",
        "fenbi_source_id": "96785",
        "source_question_count": 100,
        "capture": "papers/gd-2020-xingce-county-96785/",
        "numbers": [69, 70, 71, 72, 73, 74, 75],
        "stub_numbers": [69, 70, 71, 72, 73, 74, 75],
        "note": ("The seven source-only numbers coincide exactly with the library's "
                 "declared gaps, and all seven are uncollected stubs. Separately, 14 "
                 "OTHER numbers in this paper are genuine content differences "
                 "(18,22,64,66,67,79,87,91,92,94,96,98,99,100) — a different question "
                 "from these gaps, and it still needs per-item manual review."),
    },
)

# Every source consulted so far, and what it actually contributes.
SUPPORTING_SOURCES = [
    {"name": "上岸通 fixed reference", "role": "pinned by the repo's own report",
     "status": "placeholder-no-content", "supplies_content": False},
    {"name": "展鸿教育 2024江苏A 真题 PDF", "role": "independent institution edition",
     "status": "placeholder-no-content", "supplies_content": False},
    {"name": "星光公考 100题版 广东2020", "role": "independent institution edition",
     "status": "placeholder-no-content", "supplies_content": False},
    {"name": "崖门/丫门 pinned PDF 广东2020", "role": "pinned by the repo's own report",
     "status": "number-absent-from-source", "supplies_content": False},
    {"name": "粉笔 third-batch capture", "role": "vendor recollection edition",
     "status": "uncollected-placeholder-stub", "supplies_content": False,
     "note": ("at every one of the 11 numbers the page holds a collection stub, per "
              "the PR #33 per-item DOM audit")},
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


def anchor(repo, spec, local_file=None):
    path = None
    for candidate in (local_file, os.path.join(repo, spec["path"])):
        if candidate and os.path.isfile(candidate):
            path = candidate
            break
    digest = sha256_file(path) if path else None
    return {
        "path": spec["path"],
        "commit": spec.get("commit"),
        "pr": spec.get("pr"),
        "sha256_recorded": spec.get("sha256"),
        "sha256_local": digest,
        "sha256_verified": (digest == spec["sha256"]) if (digest and spec.get("sha256")) else None,
    }


def build(repo, correction_file=None):
    correction_anchor = anchor(repo, CORRECTION, correction_file)

    items = []
    for spec in PAPERS:
        full = os.path.join(repo, spec["path"])
        frontmatter, body = parse_frontmatter(read_text(full))
        parsed = parse_paper(body)
        library_numbers = sorted(parsed["questions"])
        library_set = set(library_numbers)
        positional_would_use = {
            n: library_numbers[n - 1]
            for n in spec["numbers"]
            if n - 1 < len(library_numbers) and library_numbers[n - 1] != n
        }

        for number in spec["numbers"]:
            is_stub = number in spec["stub_numbers"]
            items.append({
                "id": f"{spec['label']}-{number}",
                "paper": spec["path"],
                "label": spec["label"],
                "original_number": number,
                "library": {
                    "heading_present": number in library_set,
                    "state": ("already-present" if number in library_set
                              else "absent-gap-preserved"),
                },
                "mapping": {
                    "source_number": number,
                    "join": "number",
                    "join_basis": ("the source numbers questions the same way the library "
                                   "does (偏移 = 0), so source N == library N"),
                    "insert_at_original_number": number,
                    "renumbering_required": False,
                    "positional_join_would_use_library_number": positional_would_use.get(number),
                    "positional_join_is_wrong": number in positional_would_use,
                },
                "source_slot": {
                    "fenbi_source_id": spec["fenbi_source_id"],
                    "capture_dir": spec["capture"],
                    "slot_exists": True,
                    "slot_kind": ("uncollected-placeholder-stub" if is_stub
                                  else "unknown-needs-audit"),
                    "source_content_available": False if is_stub else None,
                    "observed": ("the page holds a collection stub ('题目正在全力以赴征集…'), "
                                 "not question text" if is_stub
                                 else "not established by the available evidence"),
                    "evidence_anchor": correction_anchor,
                },
                "candidate_status": "blocked",
                "repair_state": "blocked-no-source-content",
                "blocked_reason": (
                    "The source lists this number but has not collected the question; "
                    "there is no source text to repair from." if is_stub
                    else "No source content established."),
                "established": {
                    "number_listed_on_source": True,
                    "content_available": False,
                    "answer": "unknown",
                    "explanation": "unknown",
                },
                "required_evidence": list(REQUIRED_FIELDS),
                "provenance_class": "recollection-institution",
                "is_official": False,
                "write_authorization": "not-confirmed",
                "answer_policy": ("The source publishes no answers or explanations. They stay "
                                  "unknown; they are not to be inferred, and no AI-generated "
                                  "question or option text may stand in for source text."),
            })

    return {
        "pack": "missing-evidence-pack",
        "date": "2026-10-17",
        "revision": "2 — corrected after PR #33",
        "repo_head": repo_head(repo),
        "correction": {
            "date": "2026-10-17",
            "supersedes": ("revision 1 of this pack, which asserted the 11 questions were "
                           "'confirmed present on the source with content captured'"),
            "authority": correction_anchor,
            "superseded_evidence": SUPERSEDED,
            "what_actually_holds": ("at all 11 numbers the source page holds an uncollected "
                                    "collection stub; a question number or DOM container "
                                    "proves a slot exists, not that content was collected"),
            "corroboration": ("the same stub string is what the pinned third-party "
                              "references print at these numbers (verified in the PR #24 "
                              "probe of 上岸通/展鸿/星光), so the two directions agree"),
            "not_claimed": ("PR #33 corrects a misreading of the capture; it is NOT an "
                            "official-paper certification of anything, and this pack does "
                            "not present it as one"),
        },
        "scope": {
            "papers": len(PAPERS),
            "questions": sum(len(p["numbers"]) for p in PAPERS),
            "statement": ("The 11 gap numbers. Their source slots exist but hold no content, "
                          "so no repair is possible from the fenbi capture. Separate from "
                          "the 江苏2025C backfill, which must not be overwritten."),
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
            "stub_numbers": p["stub_numbers"],
            "source_content_available": False,
            "is_official": False,
            "note": p["note"],
        } for p in PAPERS],
        "supporting_sources": SUPPORTING_SOURCES,
        "items": items,
        "summary": {
            "questions": len(items),
            "candidate_status_blocked": sum(1 for i in items
                                            if i["candidate_status"] == "blocked"),
            "source_content_available": sum(1 for i in items
                                            if i["established"]["content_available"]),
            "waiting_on_a_source_that_has_the_question": len(items),
        },
        "authorization_checklist": {
            "state": "NOT CONFIRMED",
            "note": ("No repair can be authorised from the fenbi capture for these 11: there "
                     "is no content there to authorise. A different source is needed first."),
            "required_before_writing": [
                "a source that has actually collected these questions",
                "the licence/permission to redistribute that source into this repository",
                "a handoff supplying the per-question evidence fields above",
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
            "The 江苏2025C backfill is not touched.",
            "Nothing here is described as an official paper; every source consulted is an "
            "institution or recollection edition.",
            "This pack does not ask anyone to authorise a repair from the fenbi capture, "
            "because that capture holds no question content for these numbers.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--correction-file", default=None,
                    help="local copy of the PR #33 correction report, to re-verify its digest")
    ap.add_argument("--third-batch-file", dest="correction_file", help=argparse.SUPPRESS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    doc = build(args.repo, correction_file=args.correction_file)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    print(json.dumps(doc["summary"], ensure_ascii=False))
    print("correction anchor verified:",
          doc["correction"]["authority"]["sha256_verified"])
    for paper in doc["papers"]:
        print(f"  {paper['label']:14} library={paper['library_question_count']:>4} "
              f"source={paper['source_question_count']:>4} "
              f"stub_numbers={paper['stub_numbers']} "
              f"content_available={paper['source_content_available']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
