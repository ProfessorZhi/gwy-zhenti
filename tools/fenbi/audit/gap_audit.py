#!/usr/bin/env python3
"""Audit the 25 declared missing 行测 original questions against the library.

Read-only. For each of the four papers named in
reports/FULL-REPAIR-20261015.md, compares the front-matter declaration
(缺失原题号) against the question headings actually present in the body, and
reports whether the declared gap still exists in the working tree.

Scope note: 25 is the count the report names. The library-wide missing-行测
count (106) is a strictly larger, different set and is not audited here.

Usage:
    python3 tools/fenbi/audit/gap_audit.py [--repo DIR] [--out FILE]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    default_repo_root, parse_frontmatter, parse_int_list, question_numbers,
    read_text,
)

# The 25 items exactly as scoped by reports/FULL-REPAIR-20261015.md.
TARGETS = (
    ("省考/广东/2020/行测-县级卷.md", "广东2020县级卷", [69, 70, 71, 72, 73, 74, 75]),
    ("省考/江苏/2024/行测-A类.md", "江苏2024A类", [76, 96, 110, 111]),
    ("省考/江苏/2025/行测-C类.md", "江苏2025C类",
     [27, 29, 35, 36, 37, 42, 75, 77, 78, 80, 81, 85]),
    ("省考/浙江/2020/行测-A类.md", "浙江2020A类", [49, 50]),
)


def audit_paper(repo, rel_path, label, declared):
    full = os.path.join(repo, rel_path)
    entry = {
        "path": rel_path,
        "label": label,
        "exists": os.path.exists(full),
        "declared_missing": declared,
        "declared_missing_count": len(declared),
    }
    if not entry["exists"]:
        entry["status"] = "FILE_ABSENT"
        return entry

    frontmatter, body = parse_frontmatter(read_text(full))
    numbers = question_numbers(body)
    present = set(numbers)
    fm_missing = parse_int_list(frontmatter.get("缺失原题号", ""))

    entry["frontmatter"] = {k: frontmatter[k] for k in
                            ("卷型", "真题性质", "对照题本题量", "实有题数",
                             "缺失原题号", "整卷核验状态") if k in frontmatter}
    entry["frontmatter_missing_numbers"] = fm_missing
    entry["frontmatter_matches_report"] = sorted(fm_missing) == sorted(declared)
    entry["heading_count"] = len(numbers)
    entry["max_heading"] = max(numbers) if numbers else None

    still_absent = [n for n in declared if n not in present]
    entry["still_absent_numbers"] = still_absent
    entry["restored_numbers"] = [n for n in declared if n in present]
    entry["status"] = ("DECLARED_GAP_STILL_PRESENT" if len(still_absent) == len(declared)
                       else "GAP_CHANGED_SINCE_REPORT")
    return entry


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root(),
                    help="repository root (default: inferred from this script's location)")
    ap.add_argument("--out", default=None, help="write JSON here (default: stdout)")
    args = ap.parse_args()

    papers = [audit_paper(args.repo, rel, label, nums)
              for rel, label, nums in TARGETS]

    doc = {
        "audit": "missing25-gap-audit",
        "scope": {
            "scoped_missing_count": sum(len(t[2]) for t in TARGETS),
            "library_wide_missing_aptitude_items": 106,
            "statement": ("Covers only the 25 items named in "
                          "reports/FULL-REPAIR-20261015.md; the 106 figure is a "
                          "larger, different set."),
        },
        "papers": papers,
        "summary": {
            "declared": sum(len(t[2]) for t in TARGETS),
            "still_absent": sum(len(p.get("still_absent_numbers", [])) for p in papers),
            "restored": sum(len(p.get("restored_numbers", [])) for p in papers),
        },
    }

    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
