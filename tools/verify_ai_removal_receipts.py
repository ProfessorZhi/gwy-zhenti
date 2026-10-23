#!/usr/bin/env python3
"""Verify the two 2026-10-22 AI-removal receipts byte-for-byte (time-pinned, opt-in).

These receipts record the exact pre-AI state of 23 papers (14 papers / 25 answers / 6
explanations in REMOVED-AI-CONTENT-20261022.json, 9 papers / 24 blocks in
REMOVED-AI-CONTENT-LEGACY-20261022.json). The checks below assert the *delivered bytes* of
those papers, the answers that were preserved next to them, and the manifest annotations
written at removal time.

That snapshot is only valid on the tree it was taken from: commit 04e756aa ("全仓排版,
1,422 卷, 答案随题折叠") re-laid out every paper, so after_sha256/body_sha256 and the
preserved-answer digests no longer match HEAD, and they never will again. It is therefore
**not** part of main CI (same treatment as tools/verify_repair_receipts.py). Run it when
deliberately auditing the receipt chain:

    # against its own commit
    git worktree add /tmp/ai-receipts de8832f57
    (cd /tmp/ai-receipts && python tools/verify_ai_removal_receipts.py)
    git worktree remove /tmp/ai-receipts

    # against the current tree: expected to report mismatches, exit code 1
    python tools/verify_ai_removal_receipts.py

Exits 0 only when every check passes; prints a JSON summary plus the first mismatches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import round5_bulk as parser
from round4_gap_repair import digest

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
RECEIPTS = ("reports/REMOVED-AI-CONTENT-20261022.json",
            "reports/REMOVED-AI-CONTENT-LEGACY-20261022.json")
# Frozen facts of the receipts themselves (they are read-only history, so these cannot
# drift with the corpus): papers, removed answers, removed explanations.
EXPECTED = {
    "reports/REMOVED-AI-CONTENT-20261022.json": {"papers": 14, "answers": 25, "explanations": 6},
    "reports/REMOVED-AI-CONTENT-LEGACY-20261022.json": {"papers": 9, "blocks": 24},
}
DETAIL = re.compile(r"<summary>第\s*(\d+)\s*题[^<]*</summary>(.*?)</details>", re.S)
MANIFEST_KEYS = ("sha256", "bytes", "answer_blocks", "has_answer_content",
                 "missing_answer_numbers", "issues", "notes", "source_validation")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def body(text: str, legacy: bool) -> str:
    # The two receipts were produced by different scripts and captured the body start
    # differently; each body_sha256 is only meaningful with the reader that made it.
    cut = re.split(r"\n##\s*答案与解析\s*\n", text, maxsplit=1)[0]
    pattern = r"^(?:##\s*给定资料|材料[一1])" if legacy else r"^材料[一1]"
    m = re.search(pattern, cut, re.M)
    return (cut[m.start():] if m else cut).rstrip()


def verify(root: Path) -> dict:
    root = root.resolve()
    problems: list[str] = []
    manifest = {}
    manifest_path = root / "catalog/manifest.jsonl"
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            manifest[row["path"]] = row

    checked = {}
    for name in RECEIPTS:
        rows = json.loads((root / name).read_text(encoding="utf-8"))
        expected = EXPECTED[name]
        if len(rows) != expected["papers"]:
            problems.append(f"{name}: {len(rows)} papers, expected {expected['papers']}")
        if "answers" in expected:
            answers = sum(len(r["removed_answer_numbers"]) for r in rows)
            explanations = sum(len(r["removed_explanation_numbers"]) for r in rows)
            if answers != expected["answers"]:
                problems.append(f"{name}: {answers} removed answers, expected {expected['answers']}")
            if explanations != expected["explanations"]:
                problems.append(f"{name}: {explanations} removed explanations, expected {expected['explanations']}")
        else:
            blocks = sum(len(r["removed_answer_numbers"]) for r in rows)
            if blocks != expected["blocks"]:
                problems.append(f"{name}: {blocks} removed blocks, expected {expected['blocks']}")

        for row in rows:
            rel = row["path"]
            path = root / rel
            if not path.is_file():
                problems.append(f"{rel}: missing delivered file")
                continue
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            if sha(raw) != row["after_sha256"]:
                problems.append(f"{rel}: after_sha256 differs from delivered bytes")
            if len(raw) != row["after_bytes"]:
                problems.append(f"{rel}: after_bytes {len(raw)} != {row['after_bytes']}")
            if sha(body(text, legacy=name == RECEIPTS[1]).encode("utf-8")) != row["body_sha256"]:
                problems.append(f"{rel}: body_sha256 differs from delivered body")
            entry = manifest.get(rel)
            if entry is None:
                problems.append(f"{rel}: not in catalog/manifest.jsonl")
            else:
                for key in MANIFEST_KEYS:
                    if key in row["manifest_after"] and row["manifest_after"][key] != entry.get(key):
                        problems.append(f"{rel}: manifest_after.{key} differs from catalog/manifest.jsonl")
            blocks = {int(n): b for n, b in DETAIL.findall(text)}
            if name == RECEIPTS[1]:
                try:
                    parsed = parser.parse(text, rel)
                except ValueError as exc:
                    # The parser only understands the pre-04e756aa layout; on a reformatted
                    # tree this is the expected, reported outcome rather than a crash.
                    problems.append(f"{rel}: cannot re-parse for preserved answers ({exc})")
                else:
                    for number, expected_digest in row["preserved_answer_sha256"].items():
                        if digest(parsed["answers"].get(int(number), "")) != expected_digest:
                            problems.append(f"{rel}: preserved answer {number} changed")
            else:
                for number, expected_digest in row["preserved_answer_sha256"].items():
                    block = blocks.get(int(number))
                    if block is None:
                        problems.append(f"{rel}: preserved answer {number} block not found")
                    elif sha(re.sub(r"\s", "", block).encode("utf-8")) != expected_digest:
                        problems.append(f"{rel}: preserved answer {number} changed")
        checked[name] = len(rows)

    return {"status": "passed" if not problems else "failed",
            "receipts": checked,
            "checked_papers": sum(checked.values()),
            "problems": problems[:50],
            "problem_count": len(problems)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    args = ap.parse_args()
    result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
