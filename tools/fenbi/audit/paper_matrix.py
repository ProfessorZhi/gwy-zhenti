#!/usr/bin/env python3
"""Offline evidence matrix for the three papers under verification.

Covers the 23 items that workstream A is responsible for:
  江苏2025C  27/29/35/36/37/42/75/77/78/80/81/85   (12)
  江苏2024A  76/96/110/111                          (4)
  广东2020县级 69/70/71/72/73/74/75                  (7)

For every item it records what the library actually holds on seven dimensions
(题号 / 题干 / 选项 / 共用材料 / 公式与图案资源 / 答案 / 解析), and states plainly
which dimensions cannot be compared because no source capture exists yet.

The status vocabulary is deliberately the same four states the capture-time
aligner uses (tools/fenbi/src/align.mjs): same / different / unknown /
not_compared, with the same reason strings, so an offline matrix and a future
alignment.json can be read side by side.

Nothing here is inferred. A dimension with no source is `unknown`; it is never
promoted to `same` on the strength of similar text, and no answer is ever
derived from a donor paper.

Usage:
    python3 tools/fenbi/audit/paper_matrix.py [--repo DIR] [--out FILE]
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    default_repo_root, detect_placeholders, image_refs, parse_frontmatter,
    parse_paper, read_text, resolve_image_ref,
)

# The three papers this workstream verifies. Numbers are the library's own
# (original-paper) numbering, as declared in each file's 缺失原题号.
PAPERS = (
    {
        "label": "江苏2025C类",
        "path": "省考/江苏/2025/行测-C类.md",
        "fenbi_source_id": "4189916",
        "numbers": [27, 29, 35, 36, 37, 42, 75, 77, 78, 80, 81, 85],
        "note": ("These 12 were restored between the report baseline and the audited "
                 "head from 省考/江苏/2025/行测-A类.md. The A-class donor is NOT "
                 "evidence for the C paper: nothing in the A file can establish that "
                 "C question N is the same question as A question M."),
    },
    {
        "label": "江苏2024A类",
        "path": "省考/江苏/2024/行测-A类.md",
        "fenbi_source_id": "4162243",
        "numbers": [76, 96, 110, 111],
        "note": "Still absent in the library at the audited head.",
    },
    {
        "label": "广东2020县级卷",
        "path": "省考/广东/2020/行测-县级卷.md",
        "fenbi_source_id": "96785",
        "numbers": [69, 70, 71, 72, 73, 74, 75],
        "note": "Still absent in the library at the audited head.",
    },
)

# Dimensions compared, in report order. Each is one of the four aligner states.
DIMENSIONS = ("number", "stem", "options", "materials", "images", "answer", "explanation")


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest_block(text):
    stripped = text.strip()
    return {"present": bool(stripped), "chars": len(stripped),
            "sha256": sha256_text(stripped) if stripped else None}


def own_image_dir(frontmatter):
    """The image directory this paper's own resources belong in.

    Convention: 图片/省考-<地区>-<年份>-<科目>-<卷型>/ — derived from the file's own
    front matter rather than the filename, so a mismatch is detectable.
    """
    parts = [frontmatter.get(k, "") for k in ("地区", "年份", "科目", "卷型")]
    if not all(parts):
        return None
    return "省考-" + "-".join(parts)


def image_provenance(refs, own_dir):
    """Split image references into own-paper and foreign-paper groups."""
    own, foreign = [], []
    for ref in refs:
        src = ref.get("src", "")
        marker = "/图片/"
        if marker not in src:
            own.append(ref)
            continue
        directory = src.split(marker, 1)[1].split("/")[0]
        (own if own_dir and directory == own_dir else foreign).append(
            {**ref, "image_dir": directory})
    return own, foreign


def library_state(repo, paper_rel, number, parsed, own_dir=None):
    """What the library holds for this number, per dimension."""
    question = parsed["questions"].get(number)
    if question is None:
        return {"heading_present": False}

    state = {"heading_present": True, "qid": question["qid"]}
    state["stem"] = digest_block(question["stem"])
    state["stem"]["placeholder_markers"] = detect_placeholders(question["stem"])

    options = question["options"]
    state["options"] = {
        "count": len(options),
        "labels": "".join(o["label"] for o in options),
        "sha256": sha256_text("\n".join(o["text"] for o in options)) if options else None,
        "placeholder_markers": detect_placeholders("\n".join(o["text"] for o in options)),
    }

    material_ids = question["material_ids"]
    state["materials"] = {
        "linked_ids": material_ids,
        "count": len(material_ids),
        "present": all(any(m["id"] == mid for m in parsed["materials"]) for mid in material_ids),
    }

    # Figures and formulas are separate resources in this repository
    # (图片/<paper>/题目图 and /公式图); both are counted and resolved.
    refs = image_refs(question["stem"]) + [r for o in options for r in image_refs(o["text"])]
    resolved = [resolve_image_ref(repo, paper_rel, r["src"]) for r in refs]
    for ref, info in zip(refs, resolved):
        info["flag"] = ref["flag"]
    own_refs, foreign_refs = image_provenance(resolved, own_dir)
    state["images"] = {
        "total": len(resolved),
        "formula": sum(1 for r in resolved if r.get("kind") == "formula"),
        "figure": sum(1 for r in resolved if r.get("kind") == "figure"),
        "missing": sum(1 for r in resolved if not r.get("exists")),
        "own_paper": len(own_refs),
        "foreign_paper": len(foreign_refs),
        "foreign_paper_dirs": sorted({r["image_dir"] for r in foreign_refs}),
        "digests": [r.get("sha256") for r in resolved if r.get("sha256")],
        "details": resolved,
    }

    state["answer"] = digest_block(question.get("answer", ""))
    state["explanation"] = digest_block(question.get("explanation", ""))
    return state


def source_alignment(lib):
    """Per-dimension comparison state, honest about having no capture yet.

    Without a captured source document every source-facing dimension is
    `unknown`. Where the library itself is empty the reason says so, because
    that is a different situation from "the library has content we cannot yet
    check".
    """
    if not lib.get("heading_present"):
        absent = {"status": "unknown", "reason": "source-content-not-observed",
                  "library_side": "repository-content-absent"}
        return {dim: dict(absent) for dim in DIMENSIONS}

    out = {}
    for dim in DIMENSIONS:
        out[dim] = {"status": "unknown", "reason": "source-content-not-observed"}
    out["number"] = {
        "status": "not_compared",
        "reason": "number-is-the-join-key-not-a-compared-value",
    }
    return out


def internal_findings(lib):
    """Library-internal problems detectable without any source."""
    issues = []
    if not lib.get("heading_present"):
        return issues
    if lib["options"]["count"] and lib["options"]["labels"] not in ("ABCD", "ABC", "ABCDEF"):
        issues.append(f"option-labels-unexpected:{lib['options']['labels']}")
    if lib["images"]["missing"]:
        issues.append(f"image-reference-unresolved:{lib['images']['missing']}")
    if lib["images"].get("foreign_paper"):
        # This question's figure comes from another paper's image tree. For a
        # figure-reasoning item the figure IS the question, so the question's
        # content has that other paper's provenance.
        issues.append(
            "image-from-another-paper:"
            + ",".join(lib["images"]["foreign_paper_dirs"]))
    if lib["stem"].get("placeholder_markers"):
        issues.append("stem-carries-placeholder-marker")
    if lib["options"].get("placeholder_markers"):
        issues.append("options-carry-placeholder-marker")
    if not lib["answer"]["present"]:
        issues.append("no-answer-in-library")
    if not lib["explanation"]["present"]:
        issues.append("no-explanation-in-library")
    return issues


def build(repo, donor_map=None):
    papers = []
    items = []
    for spec in PAPERS:
        rel = spec["path"]
        full = os.path.join(repo, rel)
        frontmatter, body_md = parse_frontmatter(read_text(full))
        parsed = parse_paper(body_md)
        own_dir = own_image_dir(frontmatter)
        paper_record = {
            "label": spec["label"],
            "path": rel,
            "fenbi_source_id": spec["fenbi_source_id"],
            "file_sha256": sha256_text(read_text(full)),
            "own_image_dir": own_dir,
            "declared_missing": [
                int(x) for x in __import__("re").findall(
                    r"\d+", frontmatter.get("缺失原题号", "") or "")],
            "declared_total": frontmatter.get("对照题本题量"),
            "actual_questions": len(parsed["questions"]),
            "materials": len(parsed["materials"]),
            "note": spec["note"],
        }
        # Whole-paper image provenance: which image tree does each question's
        # figure actually come from? A question whose figures live in another
        # paper's tree carries that paper's provenance, which matters most for
        # figure-reasoning items where the figure is the question.
        foreign_questions = {}
        for number, question in parsed["questions"].items():
            refs = image_refs(question["stem"]) + [
                r for o in question["options"] for r in image_refs(o["text"])]
            refs = [resolve_image_ref(repo, rel, r["src"]) for r in refs]
            _, foreign = image_provenance(refs, own_dir)
            if foreign:
                foreign_questions[number] = sorted({r["image_dir"] for r in foreign})
        paper_record["questions_with_foreign_paper_images"] = sorted(foreign_questions)
        paper_record["foreign_paper_image_dirs"] = sorted(
            {d for dirs in foreign_questions.values() for d in dirs})
        papers.append(paper_record)

        for number in spec["numbers"]:
            lib = library_state(repo, rel, number, parsed, own_dir=own_dir)
            item = {
                "id": f"{spec['label']}-{number}",
                "paper": rel,
                "label": spec["label"],
                "fenbi_source_id": spec["fenbi_source_id"],
                "number": number,
                "library": lib,
                "source_alignment": source_alignment(lib),
                "library_internal_findings": internal_findings(lib),
                "verifiability": {
                    "paper_identity": "unverified",
                    "paper_identity_reason": (
                        "The fenbi catalogue response carries no paperId; binding "
                        "rests on the catalogue click path and matching title. "
                        "Unchanged by anything in this repository."),
                    "library_side": "verified" if lib.get("heading_present") else "repository-content-absent",
                    "source_side": "unknown",
                    "answer": "unknown",
                    "explanation": "unknown",
                },
                "what_would_resolve": [],
            }
            if not lib.get("heading_present"):
                item["what_would_resolve"] = [
                    "a capture of this number on the source practice page",
                    "confirmation of the source paper identity (paperId) for the whole paper",
                ]
            else:
                item["what_would_resolve"] = [
                    "a capture of this number on the source practice page, to compare "
                    "stem/options/materials/images against the library copy",
                    "confirmation of the source paper identity (paperId) for the whole paper",
                ]
                if not lib["answer"]["present"] or not lib["explanation"]["present"]:
                    item["what_would_resolve"].append(
                        "answer/explanation evidence from a source that actually "
                        "publishes them (the practice page does not)")
            if donor_map and number in donor_map:
                item["cross_number"] = donor_map[number]
            items.append(item)

    return {
        "audit": "three-paper-offline-matrix",
        "dimensions": list(DIMENSIONS),
        "status_vocabulary": {
            "same": "compared and equal after the aligner's normalization",
            "different": "compared and unequal",
            "unknown": "cannot be decided with the evidence available",
            "not_compared": "not a comparable value by design",
        },
        "papers": papers,
        "items": items,
        "summary": {
            "papers": len(papers),
            "items": len(items),
            "items_with_library_content": sum(
                1 for i in items if i["library"].get("heading_present")),
            "items_absent_in_library": sum(
                1 for i in items if not i["library"].get("heading_present")),
            "items_with_internal_findings": sum(
                1 for i in items if i["library_internal_findings"]),
            "dimensions_unknown_pending_source": sum(
                1 for i in items for d, s in i["source_alignment"].items()
                if s["status"] == "unknown"),
        },
    }


def load_donor_map(repo):
    """Cross-number donor mapping for the restored C items, if the record exists."""
    pack_path = os.path.join(repo, "reports/FREE-TOOLS-JS2025C-20261016.json")
    if not os.path.exists(pack_path):
        return {}
    pack = json.loads(read_text(pack_path))
    out = {}
    for record in pack.get("questions", []):
        reuse = record.get("reused_from") or {}
        out[record["number"]] = {
            "donor_paper": reuse.get("path"),
            "donor_number": reuse.get("question_number"),
            "donor_is_evidence_for_this_paper": False,
            "reason": ("Reusing the A-class text cannot establish that this C-class "
                       "number is that question; only a C-class source can."),
            "scan_clip_metadata_recorded": len(record.get("source_scan_clips") or []),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    doc = build(args.repo, donor_map=load_donor_map(args.repo))
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    print(json.dumps(doc["summary"], ensure_ascii=False, indent=2))
    for paper in doc["papers"]:
        print(f"  {paper['label']:14} questions={paper['actual_questions']:>4} "
              f"materials={paper['materials']:>2} declared_missing={paper['declared_missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
