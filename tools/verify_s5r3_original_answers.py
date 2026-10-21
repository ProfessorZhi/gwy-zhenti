#!/usr/bin/env python3
"""Verify S5R3 original study-answer and scoring-note delivery (five papers)."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "reports/S5R3-ORIGINAL-ANSWERS-20261021.jsonl"
DRAFT = "reports/S5R3-ORIGINAL-ANSWER-DRAFTS-20261021.json"
LABEL = "原创学习参考作答（非官方/非粉笔原解析"
EXPL = "作答思路与得分要点（原创学习解析，非原参考答案说明）"
DETAIL = re.compile(r"<summary>第\s*(\d+)\s*题</summary>(.*?)</details>", re.S)
HEADING = re.compile(r"\n##\s*答案与解析\s*\n")

def sha(b): return hashlib.sha256(b).hexdigest()
def size(s): return len(re.sub(r"[\s*#>]", "", s))

def body_without_answers(text):
    body = HEADING.split(text, maxsplit=1)[0]
    m = re.search(r"^材料[一1]", body, re.M)
    return (body[m.start():] if m else body).rstrip()

def records(root=ROOT):
    return [json.loads(l) for l in (root / RECEIPT).read_text(encoding="utf-8").splitlines() if l.strip()]

def blocks(text):
    return {int(n): b for n, b in DETAIL.findall(text)}

def reverse(text, row):
    if sha(text.encode()) != row["after_sha256"]:
        raise ValueError("S5R3 delivered SHA mismatch: " + row["path"])
    for op in sorted(row["operations"], key=lambda x: x["new_start"], reverse=True):
        if text[op["new_start"]:op["new_end"]] != op["new"]:
            raise ValueError("S5R3 operation mismatch: " + row["path"])
        text = text[:op["new_start"]] + op["old"] + text[op["new_end"]:]
    if sha(text.encode()) != row["before_sha256"]:
        raise ValueError("S5R3 preimage restoration failed: " + row["path"])
    return text

def verify(root=ROOT):
    root = Path(root).resolve()
    rows = records(root)
    drafts = json.loads((root / DRAFT).read_text(encoding="utf-8"))
    if len(rows) != 5:
        raise ValueError("S5R3 expects exactly 5 modified papers")
    pending = {(d["path"], d["n"]): d for d in drafts}
    if len(pending) != 14:
        raise ValueError("S5R3 expects 14 authored items")
    answers = explanations = preserved = 0
    for row in rows:
        rel = row["path"]; path = (root / rel).resolve()
        if not path.is_relative_to(root) or not rel.startswith("省考/") or "/申论-" not in rel:
            raise ValueError("Invalid S5R3 path: " + rel)
        current = path.read_text(encoding="utf-8")
        old = reverse(current, row)
        if sha(body_without_answers(current).encode()) != row["original_body_sha256"]:
            raise ValueError("Materials/questions changed: " + rel)
        cur_b = blocks(current); old_b = blocks(old)
        for item in row["added_answers"]:
            n = item["number"]; key = (rel, n)
            if key not in pending or n not in cur_b:
                raise ValueError("Unmatched authored answer: %s:%s" % (rel, n))
            d = pending.pop(key); b = cur_b[n]
            if LABEL not in b or d["answer"].strip() not in b:
                raise ValueError("Missing label/text: %s:%s" % (rel, n))
            if "**作答思路与得分要点**" not in b or "写作依据：本卷给定材料" not in b:
                raise ValueError("Missing scoring points/basis: %s:%s" % (rel, n))
            measured = size(d["answer"])
            if measured != item["chars"] or not d["min"] <= measured <= d["max"]:
                raise ValueError("Length mismatch: %s:%s" % (rel, n))
            if sha(d["answer"].strip().encode()) != item["text_sha256"]:
                raise ValueError("Answer text hash mismatch: %s:%s" % (rel, n))
            answers += 1
        for item in row["added_explanations"]:
            n = item["number"]; key = (rel, n)
            if key not in pending or n not in cur_b:
                raise ValueError("Unmatched authored explanation: %s:%s" % (rel, n))
            d = pending.pop(key); b = cur_b[n]
            if EXPL not in b or d["answer"].strip() not in b:
                raise ValueError("Missing explanation marker/text: %s:%s" % (rel, n))
            if "不是原答案附带的机构解析" not in b:
                raise ValueError("Missing explanation boundary: %s:%s" % (rel, n))
            if sha(d["answer"].strip().encode()) != item["text_sha256"]:
                raise ValueError("Explanation hash mismatch: %s:%s" % (rel, n))
            explanations += 1
        for num, expected in (row.get("preserved_answers") or {}).items():
            n = int(num)
            if n not in old_b:
                raise ValueError("Preserved answer missing: %s:%s" % (rel, n))
            if sha(re.sub(r"\s", "", old_b[n]).encode()) != expected:
                raise ValueError("Pre-existing answer changed: %s:%s" % (rel, n))
            preserved += 1
        declared = re.search(r"^已收录参考答案题号:\s*(\[[^\]]*\])", current, re.M)
        missing = re.search(r"^缺参考答案题号:\s*(\[[^\]]*\])", current, re.M)
        if not declared or not missing:
            raise ValueError("Answer-id frontmatter missing: " + rel)
        if json.loads(missing.group(1)) != row["remaining_answer_ids"]:
            raise ValueError("Missing ids mismatch: " + rel)
        if set(json.loads(declared.group(1))) != {a["number"] for a in row["added_answers"]} | {int(x) for x in row["preserved_answers"]}:
            raise ValueError("Declared ids mismatch: " + rel)
    if pending:
        raise ValueError("Unmatched S5R3 drafts remain")
    return {"status": "passed", "modified_papers": len(rows), "new_authored_answers": answers,
            "new_original_explanations": explanations, "preserved_existing_answers": preserved,
            "boundary": "AI-assisted original study answers/notes; not official keys or fenbi analysis"}

def historical_snapshot(root: Path, destination: Path) -> None:
    import shutil
    root = Path(root).resolve(); destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "reports", destination / "reports")
    for top in ("国考", "省考"):
        src = root / top
        if not src.is_dir(): continue
        for md in src.rglob("*.md"):
            dst = destination / md.relative_to(root); dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(md, dst)
    for row in records(root):
        p = destination / row["path"]
        p.write_text(reverse(p.read_text(encoding="utf-8"), row), encoding="utf-8", newline="\n")
    from verify_repair_receipts import RECEIPTS
    names = RECEIPTS + ("ROUND4-ANSWERS-20261012.jsonl", "ROUND5-ANSWERS-20261012.jsonl",
        "ROUND6-OWNED-ANSWERS-20261013.jsonl", "ROUND7-REFERENCES-20261013.jsonl",
        "ROUND8-ORIGINAL-ANSWERS-20261013.jsonl", "ROUND9-ORIGINAL-ANSWERS-20261013.jsonl",
        "ROUND10-ORIGINAL-ANSWERS-20261013.jsonl", "S5-ORIGINAL-ANSWERS-20261021.jsonl",
        "S5R2-ORIGINAL-ANSWERS-20261021.jsonl")
    for name in names:
        f = root / "reports" / name
        if not f.is_file(): continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            rel = json.loads(line)["path"]
            src = (root / rel).resolve(); dst = (destination / rel).resolve()
            if (not src.is_relative_to(root) or not dst.is_relative_to(destination) or not src.is_file()):
                raise ValueError("Unsafe/absent S5R3 dependency: " + rel)
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
    (destination / RECEIPT).unlink()

if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
