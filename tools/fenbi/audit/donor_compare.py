#!/usr/bin/env python3
"""Check the 江苏2025C backfill against its recorded donor blocks.

reports/FREE-TOOLS-JS2025C-20261016.json records, for each of the 12 question
numbers restored into 省考/江苏/2025/行测-C类.md, which question of
省考/江苏/2025/行测-A类.md it was taken from. This script re-derives that
comparison from the markdown itself, so the claim can be checked rather than
trusted.

It reports identity and similarity scores plus sha256 digests. Question text is
deliberately NOT emitted: the restored blocks already live in this repository,
and the point of the check is provenance, not reproduction.

Usage:
    python3 tools/fenbi/audit/donor_compare.py [--repo DIR] [--pack FILE] [--out FILE]
"""

import argparse
import difflib
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    default_repo_root, fold_for_compare, parse_frontmatter, question_blocks,
    read_text,
)

RECIPIENT = "省考/江苏/2025/行测-C类.md"
DONOR = "省考/江苏/2025/行测-A类.md"
DEFAULT_PACK = "reports/FREE-TOOLS-JS2025C-20261016.json"


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_report(repo, pack_path):
    """Assemble the donor-comparison document for a repository root."""
    pack = json.loads(read_text(pack_path))
    _, recipient_body = parse_frontmatter(read_text(os.path.join(repo, RECIPIENT)))
    _, donor_body = parse_frontmatter(read_text(os.path.join(repo, DONOR)))
    recipient_blocks = question_blocks(recipient_body)
    donor_blocks = question_blocks(donor_body)

    items = []
    for record in pack.get("questions", []):
        number = record["number"]
        reuse = record.get("reused_from") or {}
        donor_number = reuse.get("question_number")
        r_text = recipient_blocks.get(number)
        d_text = donor_blocks.get(donor_number)

        item = {
            "number": number,
            "declared_donor_number": donor_number,
            "declared_donor_qid": reuse.get("qid"),
            "donor_number_differs_from_recipient": (
                donor_number is not None and donor_number != number),
            "recipient_block_present": r_text is not None,
            "donor_block_present": d_text is not None,
            "saved_scan_clip_metadata_count": len(record.get("source_scan_clips") or []),
            "source_pages": record.get("source_pages"),
        }
        if r_text is not None and d_text is not None:
            fr, fd = fold_for_compare(r_text), fold_for_compare(d_text)
            item["folded_identical_to_donor"] = fr == fd
            item["folded_similarity"] = round(
                difflib.SequenceMatcher(None, fr, fd).ratio(), 4)
            item["recipient_block_sha256"] = sha256_text(r_text)
            item["donor_block_sha256"] = sha256_text(d_text)
        items.append(item)

    doc = {
        "audit": "missing25-donor-compare",
        "recipient": RECIPIENT,
        "donor": DONOR,
        "provenance_record": os.path.relpath(pack_path, repo),
        "note": ("Question text is intentionally not included; digests and scores "
                 "are sufficient to re-check provenance."),
        "items": items,
        "summary": {
            "total": len(items),
            "folded_identical_to_donor": sum(
                1 for i in items if i.get("folded_identical_to_donor")),
            "donor_number_differs_from_recipient": sum(
                1 for i in items if i.get("donor_number_differs_from_recipient")),
            "with_saved_scan_clip_metadata": sum(
                1 for i in items if i.get("saved_scan_clip_metadata_count")),
            "without_saved_scan_clip_metadata": sum(
                1 for i in items if not i.get("saved_scan_clip_metadata_count")),
        },
    }
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--pack", default=None,
                    help=f"backfill provenance record (default: {DEFAULT_PACK})")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    pack_path = args.pack or os.path.join(args.repo, DEFAULT_PACK)
    if not os.path.exists(pack_path):
        print(f"error: provenance record not found: {pack_path}", file=sys.stderr)
        return 2

    doc = build_report(args.repo, pack_path)

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
