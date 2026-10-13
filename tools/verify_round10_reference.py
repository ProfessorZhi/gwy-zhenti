#!/usr/bin/env python3
"""Verify R10 answer delivery and construct an exact R9 baseline snapshot."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import round5_bulk as parser
from r7_reference_audit import assess

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "ROUND10-ORIGINAL-ANSWERS-20261013.jsonl"
DRAFT = "ROUND10-ORIGINAL-ANSWER-DRAFTS-20261013.json"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def records(root: Path) -> list[dict]:
    return [
        json.loads(line) for line in (root / "reports" / RECEIPT).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def reverse(text: str, receipt: dict) -> str:
    """Restore exact R9 paper bytes without rewinding R9/R8 changes."""
    if sha(text) != receipt["after_sha256"]:
        raise ValueError("R10 delivered SHA mismatch: " + receipt["path"])
    section = "\n\n## 答案与解析"
    if text.count(section) != 1:
        raise ValueError("R10 answer section missing or repeated: " + receipt["path"])
    start = text.index("材料一：")
    end = text.index(section, start)
    body = text[start:end].rstrip()
    if (sha(body) != receipt["original_materials_and_task_body_sha256"]
            or len(body) != receipt["original_materials_and_task_body_length"]):
        raise ValueError("R10 original material/task changed: " + receipt["path"])
    old = (receipt["before_header_prefix"] + body +
           receipt["before_materials_trailing_whitespace"])
    if sha(old) != receipt["before_sha256"]:
        raise ValueError("R10 exact preimage restoration failed: " + receipt["path"])
    return old


def verify(root: Path) -> dict:
    root = Path(root).resolve()
    rows = records(root)
    drafts = json.loads((root / "reports" / DRAFT).read_text(encoding="utf-8"))
    if len(rows) != 2 or len(drafts) != 6:
        raise ValueError("R10 count mismatch")
    pending = {(x["path"], x["n"]): x for x in drafts}
    if len(pending) != 6:
        raise ValueError("Duplicated R10 draft targets")
    seen = set()
    existing_exam_questions = 0
    for row in rows:
        rel = row["path"]
        path = (root / rel).resolve()
        if (rel in seen or not path.is_relative_to(root)
                or not rel.startswith("省考/深圳/2025/申论-") or not path.is_file()):
            raise ValueError("Invalid R10 path " + rel)
        seen.add(rel)
        current = path.read_text(encoding="utf-8")
        original = reverse(current, row)
        old_paper = parser.parse(original, rel)
        new_paper = parser.parse(current, rel)
        if not old_paper or not new_paper or set(old_paper["questions"]) != {1, 2, 3}:
            raise ValueError("R10 expected original 3-question exam")
        if old_paper["questions"] != new_paper["questions"]:
            raise ValueError("R10 modified task text: " + rel)
        if any(old_paper["answers"].values()) or old_paper["answers"]:
            raise ValueError("R10 overwrote pre-existing answers: " + rel)
        if new_paper["missing"] or set(new_paper["answers"]) != {1, 2, 3}:
            raise ValueError("R10 incomplete answer delivery: " + rel)
        if "已收录参考答案题号: [1, 2, 3]" not in current:
            raise ValueError("R10 navigation/header not refreshed")
        previous_answer_ids = set()
        for row_answer in row["answers"]:
            number = row_answer["number"]
            key = (rel, number)
            if number in previous_answer_ids or key not in pending:
                raise ValueError("Duplicate/unexpected answer id")
            previous_answer_ids.add(number)
            draft = pending.pop(key)
            answer = new_paper["answers"][number]
            size = len("".join(c for c in draft["answer"] if not c.isspace() and c != "*"))
            if size != row_answer["chars"] or not draft["min"] <= size <= draft["max"]:
                raise ValueError("R10 wrong answer length: " + rel)
            if draft["answer"].strip() not in answer:
                raise ValueError("R10 draft text missing from delivered answer")
            if ("原创示范作答（AI辅助编写；非机构原文，未经实考评分）" not in answer
                    or draft["source"] not in answer):
                raise ValueError("R10 source/AI writing boundary missing")
            if assess(new_paper["questions"][number], answer)["status"] != "已收录":
                raise ValueError("R10 answer body is not readable: " + rel)
        if previous_answer_ids != {1, 2, 3}:
            raise ValueError("Missing R10 answers in receipt")
        existing_exam_questions += len(old_paper["questions"])
    if pending:
        raise ValueError("Unmatched authored R10 targets")
    return {"status": "passed", "modified_papers": len(rows),
            "new_complete_answer_positions": 6, "new_full_length_essay_positions": 2,
            "preserved_original_exam_questions": existing_exam_questions,
            "historical_restoration": "exact R9 file bytes restored and SHA256 verified",
            "boundary": "AI-assisted original examples; not official or scored high-score scripts"}


def historical_snapshot(root: Path, destination: Path) -> None:
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    shutil.copytree(root / "reports", destination / "reports")
    for top in ("国考", "省考"):
        if (root / top).is_dir():
            shutil.copytree(root / top, destination / top)
    for receipt in records(root):
        path = destination / receipt["path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(reverse(text, receipt), encoding="utf-8", newline="\n")
    # Preserve all non-paper historical receipt dependencies, including any images.
    from verify_repair_receipts import RECEIPTS
    names = RECEIPTS + (
        "ROUND4-ANSWERS-20261012.jsonl",
        "ROUND5-ANSWERS-20261012.jsonl",
        "ROUND6-OWNED-ANSWERS-20261013.jsonl",
        "ROUND7-REFERENCES-20261013.jsonl",
        "ROUND8-ORIGINAL-ANSWERS-20261013.jsonl",
        "ROUND9-ORIGINAL-ANSWERS-20261013.jsonl",
    )
    for name in names:
        source_receipt = root / "reports" / name
        if not source_receipt.is_file():
            continue
        for line in source_receipt.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rel = json.loads(line)["path"]
            src = (root / rel).resolve()
            dest = (destination / rel).resolve()
            if (not src.is_relative_to(root) or not dest.is_relative_to(destination)
                    or not src.is_file()):
                raise ValueError("Unsafe/absent historical R10 dependency: " + rel)
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
    (destination / "reports" / RECEIPT).unlink()


if __name__ == "__main__":
    print(json.dumps(verify(ROOT), ensure_ascii=False))
