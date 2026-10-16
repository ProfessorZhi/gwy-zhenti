#!/usr/bin/env python3
"""Build a per-paper quality-coverage matrix for the whole corpus.

Read-only. Joins, by `path`:
  - the delivered Markdown itself (independent `## 第 N 题` anchor scan)
  - catalog/manifest.jsonl (the repository's own machine fields)
  - essay-side answer evidence (FULL-REPAIR-LAYOUT) and aptitude-side
    (FULL-REPAIR-APTITUDE-VERIFICATION)
  - image-decode evidence at the granularity that actually exists
  - the vendor source-ID registry, only where a directory was really observed

and then MATERIALISES per-dimension quality labels.

Why this exists
---------------
`tools/fenbi/ANSWER-EVIDENCE-SOP.md` defines the label vocabulary
(`verified` / `partial` / `conflicting` / `unknown` / `not_applicable`) but no
file in the repository ever assigns it per paper. Without that, "no gaps" and
"nobody looked" are indistinguishable in every downstream report.

Assignment rule, deliberately conservative: a dimension is `verified` ONLY where
a source comparison was actually performed and passed. Where no comparison was
ever performed the label is `unknown` -- not `verified`, not `partial` -- because
"we never looked" is not "it is right".

ABSENT is reported as ABSENT and `null` means not measured. Nothing is inferred:
a vendor source ID that was not observed is `null`, never a guessed URL or label.

Usage:
    python3 -I tools/qa/coverage_matrix.py --repo . --out coverage-matrix.jsonl
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

# Vendor directory identities that were actually observed by clicking the real
# directory UI. Anything absent from this table is null -- never inferred.
SOURCE_IDS = {
    "省考/浙江/2026/行测-C类.md": ("8399763", "PR#25 first batch, labelId=31"),
    "省考/江苏/2025/行测-C类.md": ("4189916", "PR#25/27, labelId=16"),
    "省考/江苏/2024/行测-A类.md": ("4162243", "PR#25/27, labelId=16"),
    "省考/广东/2020/行测-县级卷.md": ("96785", "PR#25/27, labelId=6"),
    "省考/浙江/2020/行测-A类.md": ("96454", "PR#27 paged directory, labelId=31"),
    "省考/浙江/2020/行测-B类.md": ("96455", "PR#27 paged directory, labelId=31"),
}

# Papers that have actually been compared against the vendor source. Only one
# reaches a strict comparison today; everything else stays unknown by rule.
SOURCE_COMPARED = {
    "省考/浙江/2026/行测-C类.md": {
        "images": "partial",
        "note": "109/110 strict exact; q54 representation equivalence reviewed "
                "separately; answers not exposed by the exercise view",
    },
}

RE_ANCHOR = re.compile(r"^#{2,4}\s*第\s*(\d+)\s*题", re.M)
RE_HEADING = re.compile(r"^(#{2,4})\s*第\s*(\d+)\s*题\s*(.*)$")
RE_MATERIAL = re.compile(r"^#{2,4}\s*材料\s*(\d+)\s*[（(]\s*第\s*([0-9]+)\s*[—\-~～至]\s*([0-9]+)\s*题")
RE_MATERIAL_ONE = re.compile(r"^#{2,4}\s*材料\s*(\d+)\s*(?:[（(]\s*第\s*(\d+)\s*题)")
RE_FM = re.compile(r"^---\s*$")


def parse_frontmatter(text):
    lines = text.split("\n")
    if not lines or not RE_FM.match(lines[0]):
        return {}, 0
    fm = {}
    for i in range(1, len(lines)):
        if RE_FM.match(lines[i]):
            return fm, i + 1
        m = re.match(r"^([^:\s][^:]*):\s*(.*)$", lines[i])
        if m:
            fm[m.group(1).strip()] = m.group(2).strip()
    return fm, len(lines)


def fm_list(raw):
    """Parse a frontmatter list like '[1, 2, 3]' / '[]'. None when absent."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "null", "~"):
        return None
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        try:
            return [int(x.strip()) for x in inner.split(",")]
        except ValueError:
            return inner
    return s


def scan_md(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    fm, body = parse_frontmatter(text)
    lines = text.split("\n")
    anchors, materials = [], []
    for i in range(body, len(lines)):
        m = RE_HEADING.match(lines[i])
        if m:
            anchors.append(int(m.group(2)))
            continue
        m = RE_MATERIAL.match(lines[i]) or RE_MATERIAL_ONE.match(lines[i])
        if m:
            first = int(m.group(2))
            last = int(m.group(3)) if m.re is RE_MATERIAL else first
            materials.append({"material": int(m.group(1)), "first": first, "last": last})
    declared = None
    for key in ("对照题本题量", "参考题本量", "实有题数"):
        try:
            declared = int(fm[key])
            break
        except (KeyError, ValueError):
            continue
    hi = max([declared or 0, max(anchors) if anchors else 0]
             + ([max(fm_list(fm.get("缺失原题号")) or [0])]
                if isinstance(fm_list(fm.get("缺失原题号")), list) else [0]))
    present = set(anchors)
    return {
        "fm": fm,
        "anchors": anchors,
        "missing": [n for n in range(1, hi + 1) if n not in present],
        "materials": materials,
    }


def load_jsonl(p):
    out = []
    if not os.path.isfile(p):
        return out
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def load_json(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def source_class(nature):
    n = (nature or "").strip().strip('"')
    if "回忆" in n:
        return "third_party_recall"
    if "机构" in n:
        return "third_party_compiled"
    if "正式真题" in n:
        return "real_exam_provenance_unstated"
    if n in ("", "源未标注"):
        return "unstated"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)

    manifest = {r["path"]: r for r in load_jsonl(os.path.join(repo, "catalog/manifest.jsonl"))}
    layout = {r["path"]: r for r in
              load_jsonl(os.path.join(repo, "reports/FULL-REPAIR-LAYOUT-20261015.jsonl"))
              if r.get("path")}
    apt = {r["path"]: r for r in
           ((load_json(os.path.join(repo, "reports/FULL-REPAIR-APTITUDE-VERIFICATION-20261015.json"))
             or {}).get("papers") or []) if r.get("path")}
    per_paper_img = {r["path"]: r for r in
                     ((load_json(os.path.join(repo, "reports/MISSING50-PEER-REVIEW-20261016.json"))
                       or {}).get("papers") or []) if r.get("path")}

    rows = []
    for path, m in sorted(manifest.items()):
        full = os.path.join(repo, path)
        s = scan_md(full) if os.path.isfile(full) else {"fm": {}, "anchors": [], "missing": [], "materials": []}
        fm = s["fm"]
        declared = m.get("declared_questions")
        compared = SOURCE_COMPARED.get(path)
        sid, sid_note = SOURCE_IDS.get(path, (None, None))
        authorship = fm.get("新增答案性质")
        if authorship is not None and str(authorship).strip() in ("[]", "", '""'):
            authorship = None
        a_apt = apt.get(path)
        apt_total = None
        if a_apt:
            ex, ad = a_apt.get("existing_answers"), a_apt.get("added_answers")
            if ex is not None or ad is not None:
                apt_total = (ex or 0) + (ad or 0)
        lay = layout.get(path)
        essay_nums = fm_list(fm.get("已收录参考答案题号"))
        lay_ans = len(lay.get("current_answered") or []) if lay else None
        counts = [v for v in (m.get("answer_blocks"), apt_total, lay_ans) if v is not None]

        rows.append({
            "path": path,
            "subject": m.get("subject"), "area": m.get("area"),
            "year": m.get("year"), "paper_type": m.get("paper_type"),
            "manifest_sha256": m.get("sha256"),
            "source": {
                "vendor_source_id": sid,
                "vendor_source_id_provenance": "directory-observed" if sid else None,
                "vendor_source_id_note": sid_note,
                "source_class": source_class(fm.get("真题性质")),
                "nature_label": (fm.get("真题性质") or "").strip().strip('"'),
                "answer_authorship": authorship,
            },
            "questions": {
                "declared": declared, "present": len(s["anchors"]),
                "missing_numbers": s["missing"], "missing_count": len(s["missing"]),
            },
            "materials": {"groups": len(s["materials"]), "ranges": s["materials"],
                          "known_gap_segments": m.get("known_material_gaps")},
            "images": {
                "references": m.get("image_references"),
                "decode_verified": per_paper_img.get(path, {}).get("image_decode_all_passed"),
                "decode_scope": "per-paper" if path in per_paper_img else "aggregate-only",
            },
            "answers": {
                "manifest_answer_blocks": m.get("answer_blocks"),
                "declared_for_answers": declared,
                "essay_answered_count": len(essay_nums) if isinstance(essay_nums, list) else None,
                "layout_answered_count": lay_ans,
                "aptitude_existing_plus_added": apt_total,
                "sources_disagree": len(set(counts)) > 1,
            },
            "explanations": {
                "per_paper_count": None,
                "evidence": "ABSENT: no per-paper explanation count exists in this repository",
            },
            "labels": {
                "stem": "verified" if compared else "unknown",
                "options": "verified" if compared else "unknown",
                "number": "verified" if compared else "unknown",
                "materials": "verified" if compared else "unknown",
                "images": (compared or {}).get("images", "unknown"),
                "answer": "unknown",        # never established against source
                "explanation": "unknown",   # no per-paper evidence exists at all
                "paper_binding": "unverified",
                "whole_paper": m.get("whole_paper_acceptance") or "unknown",
            },
            "gap_flags": {k: (m.get(f) or []) for k, f in (
                ("missing_original", "missing_original_numbers"),
                ("missing_option", "missing_option_numbers"),
                ("missing_shared_condition", "missing_shared_condition_numbers"),
                ("missing_stem_condition", "missing_stem_condition_numbers"),
                ("missing_stem_figure", "missing_stem_figure_numbers"),
                ("missing_answer", "missing_answer_numbers"),
                ("source_analysis_disagreement", "source_analysis_disagreement_numbers"),
                ("material_gap", "known_material_gaps"))},
            "provenance": {"issues": m.get("issues") or [], "review_scope": m.get("review_scope")},
        })

    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    tot = collections.Counter()
    for r in rows:
        for k, v in r["gap_flags"].items():
            if v:
                tot[k] += len(v) if isinstance(v, list) else 1
    print(json.dumps({
        "papers": len(rows),
        "gap_totals": dict(tot),
        "labels": {
            "stem_verified": sum(1 for r in rows if r["labels"]["stem"] == "verified"),
            "never_source_compared": sum(1 for r in rows if r["labels"]["stem"] == "unknown"),
            "answer_unknown": sum(1 for r in rows if r["labels"]["answer"] == "unknown"),
            "paper_binding_unverified": sum(1 for r in rows if r["labels"]["paper_binding"] == "unverified"),
        },
        "vendor_source_ids_known": sum(1 for r in rows if r["source"]["vendor_source_id"]),
        "answer_count_conflicts": sum(1 for r in rows if r["answers"]["sources_disagree"]),
        "boundary": "Labels are conservative: unknown means never compared against the source, "
                    "not merely unverified. No number here is inferred.",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
