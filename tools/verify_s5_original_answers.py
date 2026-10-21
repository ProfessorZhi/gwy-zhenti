#!/usr/bin/env python3
"""Verify S5 original study-answer delivery (content-only round).

Checks, without re-reading any capture database:
  * delivered bytes match the receipt;
  * materials/questions/image references are byte-identical to the receipt body hash;
  * every added block carries the non-official label, material basis and scoring points;
  * pre-existing answers were not overwritten;
  * frontmatter answer-id lists match what was actually delivered.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "reports/S5-ORIGINAL-ANSWERS-20261021.jsonl"
DRAFT = "reports/S5-ORIGINAL-ANSWER-DRAFTS-20261021.json"
LABEL = "原创学习参考作答（非官方/非粉笔原解析"
DETAIL = re.compile(r"<summary>第\s*(\d+)\s*题</summary>(.*?)</details>", re.S)
HEADING = re.compile(r"\n##\s*答案与解析\s*\n")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def size(text: str) -> int:
    return len(re.sub(r"[\s*#>]", "", text))


def body_without_answers(text: str) -> str:
    body = HEADING.split(text, maxsplit=1)[0]
    m = re.search(r"^材料[一1]", body, re.M)
    return (body[m.start():] if m else body).rstrip()


def records(root: Path = ROOT) -> list[dict]:
    path = root / RECEIPT
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    rows = records(root)
    drafts = json.loads((root / DRAFT).read_text(encoding="utf-8"))
    if len(rows) != 3:
        raise ValueError("S5 expects exactly 3 modified papers")
    pending = {(d["path"], d["n"]): d for d in drafts}
    if len(pending) != 6:
        raise ValueError("S5 expects exactly 6 authored answers")

    answers_added = 0
    preserved_checked = 0
    for row in rows:
        rel = row["path"]
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not rel.startswith("省考/") or "/申论-" not in rel:
            raise ValueError("Invalid S5 path: " + rel)
        current = path.read_text(encoding="utf-8")
        if sha(current.encode("utf-8")) != row["after_sha256"]:
            raise ValueError("Delivered SHA mismatch: " + rel)
        body = body_without_answers(current)
        if sha(body.encode("utf-8")) != row["original_body_sha256"] or len(body) != row["original_body_length"]:
            raise ValueError("Materials/questions changed: " + rel)
        if row["declared_questions"] != 3:
            raise ValueError("Expected a three-question paper: " + rel)

        blocks = {int(n): b for n, b in DETAIL.findall(current)}
        for item in row["added_answers"]:
            n = item["number"]
            key = (rel, n)
            if key not in pending or n not in blocks:
                raise ValueError("Unmatched authored answer: %s:%s" % (rel, n))
            draft = pending.pop(key)
            block = blocks[n]
            if LABEL not in block:
                raise ValueError("Missing originality label: %s:%s" % (rel, n))
            if "非官方答案" not in body and "非官方" not in current[:2000]:
                raise ValueError("Originality boundary missing in frontmatter: " + rel)
            if draft["answer"].strip() not in block:
                raise ValueError("Draft text absent from delivered block: %s:%s" % (rel, n))
            if "**作答思路与得分要点**" not in block or "写作依据" not in block:
                raise ValueError("Missing scoring points or material basis: %s:%s" % (rel, n))
            measured = size(draft["answer"])
            if measured != item["chars"]:
                raise ValueError("Answer length receipt mismatch: %s:%s" % (rel, n))
            if not draft["min"] <= measured <= draft["max"]:
                raise ValueError("Answer outside declared length band: %s:%s" % (rel, n))
            if sha(draft["answer"].strip().encode("utf-8")) != item["text_sha256"]:
                raise ValueError("Answer text hash mismatch: %s:%s" % (rel, n))
            answers_added += 1

        for num, expected in (row.get("preserved_answers") or {}).items():
            n = int(num)
            if n not in blocks:
                raise ValueError("Preserved answer missing: %s:%s" % (rel, n))
            if sha(re.sub(r"\s", "", blocks[n]).encode("utf-8")) != expected:
                raise ValueError("Pre-existing answer was modified: %s:%s" % (rel, n))
            preserved_checked += 1

        declared = re.search(r"^已收录参考答案题号:\s*(\[[^\]]*\])", current, re.M)
        missing = re.search(r"^缺参考答案题号:\s*(\[[^\]]*\])", current, re.M)
        if not declared or not missing:
            raise ValueError("Answer-id frontmatter missing: " + rel)
        declared_ids = json.loads(declared.group(1))
        missing_ids = json.loads(missing.group(1))
        if missing_ids != row["remaining_answer_ids"]:
            raise ValueError("Remaining answer ids mismatch: " + rel)
        if set(declared_ids) != {a["number"] for a in row["added_answers"]} | {int(x) for x in (row.get("preserved_answers") or {})}:
            raise ValueError("Declared answer ids mismatch: " + rel)

    if pending:
        raise ValueError("Unmatched S5 drafts remain")
    return {"status": "passed", "modified_papers": len(rows),
            "new_authored_answers": answers_added,
            "preserved_existing_answers": preserved_checked,
            "boundary": "AI-assisted original study references; not official keys or fenbi analysis"}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
