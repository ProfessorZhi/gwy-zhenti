#!/usr/bin/env python3
"""Verify the E5NW Northwest/Northeast shenlun original-answer delivery.

Checks, per modified paper:
  * the reverse-applied operations reproduce the pre-change SHA256;
  * materials/questions (everything before `## 答案与解析`) are unchanged;
  * every pre-existing answer block is unchanged;
  * each new block carries the non-official label, scoring notes, material basis,
    the measured length inside the stated limit, and the recorded text SHA;
  * frontmatter answer ids and `catalog/manifest.jsonl` agree with the file;
  * no 40-character run is copied from the materials or a preserved answer.
"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "reports/E5NW-ORIGINAL-ANSWERS-20261022.jsonl"
DRAFT = "reports/E5NW-ORIGINAL-ANSWER-DRAFTS-20261022.json"
UPDATES = "reports/E5NW-MANIFEST-UPDATES-20261022.json"
LABEL = "原创学习参考作答（非官方/非粉笔原解析"
SCORES = "**作答思路与得分要点**"
BASIS = "写作依据：本卷给定材料"
PROVINCES = {"黑龙江", "吉林", "辽宁", "内蒙古", "山西", "陕西", "甘肃", "青海", "宁夏", "新疆"}

def sha(b) -> str:
    return hashlib.sha256(b.encode("utf-8") if isinstance(b, str) else b).hexdigest()

def count(s: str) -> int:
    return len(re.sub(r"[\s*#>]", "", s))

def blocks(text: str):
    return {int(n): b for n, b in re.findall(r"<summary>第\s*(\d+)\s*题</summary>(.*?)</details>", text, re.S)}

def body_without_answers(text: str) -> str:
    body = text.split("## 答案与解析", 1)[0]
    m = re.search(r"^材料[一1]", body, re.M)
    return (body[m.start():] if m else body).rstrip()

def reverse(text: str, row: dict) -> str:
    if sha(text) != row["after_sha256"]:
        raise ValueError("E5NW delivered SHA mismatch: " + row["path"])
    for op in sorted(row["operations"], key=lambda x: x["new_start"], reverse=True):
        if text[op["new_start"]:op["new_end"]] != op["new"]:
            raise ValueError("E5NW operation mismatch: " + row["path"])
        text = text[:op["new_start"]] + op["old"] + text[op["new_end"]:]
    if sha(text) != row["before_sha256"]:
        raise ValueError("E5NW preimage restoration failed: " + row["path"])
    return text

def ngrams(s: str, n: int = 40):
    s = re.sub(r"[\s*#>]", "", s)
    return {s[i:i+n] for i in range(max(0, len(s) - n + 1))}

def verify(root=ROOT):
    root = Path(root).resolve()
    rows = [json.loads(l) for l in (root / RECEIPT).read_text(encoding="utf-8").splitlines() if l.strip()]
    drafts = json.loads((root / DRAFT).read_text(encoding="utf-8"))
    if len(rows) != 14:
        raise ValueError(f"E5NW expects 14 modified papers, got {len(rows)}")
    pending = {(d["path"], d["n"]): d for d in drafts}
    if len(pending) != 19:
        raise ValueError(f"E5NW expects 19 authored items, got {len(pending)}")
    manifest = {}
    for line in (root / "catalog/manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line); manifest[r["path"]] = r

    answers = preserved_total = 0
    paths = set()
    for row in rows:
        rel = row["path"]; paths.add(rel)
        if not rel.startswith("省考/") or "/申论-" not in rel:
            raise ValueError("Invalid E5NW path: " + rel)
        prov = rel.split("/")[1]
        if prov not in PROVINCES:
            raise ValueError("Out-of-scope province: " + prov)
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Unsafe/absent path: " + rel)
        current = path.read_text(encoding="utf-8")
        old = reverse(current, row)
        if sha(body_without_answers(current)) != row["original_body_sha256"]:
            raise ValueError("Materials/questions changed: " + rel)
        cur_b, old_b = blocks(current), blocks(old)
        material_text = body_without_answers(current)
        if len(material_text) < 1500:
            raise ValueError("Paper materials look incomplete: " + rel)
        qmap = {int(n): q for n, q in re.findall(
            r"^## 第\s*(\d+)\s*题\s*\n(.*?)(?=^## 第\s*\d+\s*题|^## 答案与解析)", current, re.M | re.S)}
        for item in row["added_answers"]:
            n = item["number"]; key = (rel, n)
            if key not in pending or n not in cur_b:
                raise ValueError(f"Unmatched authored answer: {rel}:{n}")
            d = pending.pop(key); b = cur_b[n]
            if LABEL not in b or d["answer"].strip() not in b:
                raise ValueError(f"Missing label/text: {rel}:{n}")
            if SCORES not in b or BASIS not in b:
                raise ValueError(f"Missing scoring notes/material basis: {rel}:{n}")
            if "非官方" not in b or "未经实考评分" not in b:
                raise ValueError(f"Boundary label incomplete: {rel}:{n}")
            qtext = qmap.get(n, "")
            if len(qtext.strip()) < 20 or "要求" not in qtext:
                raise ValueError(f"Question prompt/requirements missing: {rel}:{n}")
            measured = count(d["answer"])
            if measured != item["chars"] or not d["min"] <= measured <= d["max"]:
                raise ValueError(f"Length mismatch: {rel}:{n} {measured} {d['min']}-{d['max']}")
            if sha(d["answer"].strip()) != item["text_sha256"]:
                raise ValueError(f"Answer text hash mismatch: {rel}:{n}")
            leaked = ngrams(d["answer"]) & ngrams(material_text)
            if leaked:
                raise ValueError(f"Answer copies a 40-char run from materials: {rel}:{n}: {next(iter(leaked))}")
            for pn, pb in old_b.items():
                if pn == n:
                    continue
                if ngrams(d["answer"]) & ngrams(pb):
                    raise ValueError(f"Answer copies a 40-char run from answer {pn}: {rel}:{n}")
            answers += 1
        for num, expected in (row.get("preserved_answers") or {}).items():
            n = int(num)
            if n not in old_b or n not in cur_b:
                raise ValueError(f"Preserved answer missing: {rel}:{n}")
            if sha(re.sub(r"\s", "", old_b[n])) != expected:
                raise ValueError(f"Pre-existing answer hash mismatch: {rel}:{n}")
            if re.sub(r"\s", "", old_b[n]) != re.sub(r"\s", "", cur_b[n]):
                raise ValueError(f"Pre-existing answer changed: {rel}:{n}")
            preserved_total += 1
        declared = re.search(r"^已收录参考答案题号:\s*(\[[^\]]*\])", current, re.M)
        missing = re.search(r"^缺参考答案题号:\s*(\[[^\]]*\])", current, re.M)
        added_ids = re.search(r"^新增原创学习参考作答题号:\s*(\[[^\]]*\])", current, re.M)
        if not (declared and missing and added_ids):
            raise ValueError("Answer-id frontmatter missing: " + rel)
        if json.loads(missing.group(1)) != row["remaining_answer_ids"]:
            raise ValueError("Missing ids mismatch: " + rel)
        if json.loads(added_ids.group(1)) != sorted(i["number"] for i in row["added_answers"]):
            raise ValueError("Added ids mismatch: " + rel)
        if set(json.loads(declared.group(1))) != {a["number"] for a in row["added_answers"]} | {int(x) for x in row["preserved_answers"]}:
            raise ValueError("Declared ids mismatch: " + rel)
        # manifest row must describe the delivered file
        if rel not in manifest:
            raise ValueError("Manifest row missing: " + rel)
        mrow = manifest[rel]
        if mrow["sha256"] != row["after_sha256"]:
            raise ValueError("Manifest SHA does not match file: " + rel)
        if mrow["bytes"] != path.stat().st_size:
            raise ValueError("Manifest bytes do not match file: " + rel)
        if mrow["missing_answer_numbers"] != row["remaining_answer_ids"]:
            raise ValueError("Manifest missing ids mismatch: " + rel)
        if mrow["answer_blocks"] != len(row["added_answers"]) + len(row["preserved_answers"]):
            raise ValueError("Manifest answer_blocks mismatch: " + rel)
        if "E5NW" not in (mrow.get("source_validation") or ""):
            raise ValueError("Manifest audit note missing: " + rel)
    if pending:
        raise ValueError("Unmatched E5NW drafts remain: " + str(next(iter(pending))))
    if len(paths) != 14:
        raise ValueError("Duplicate paths in receipt")
    return {"status": "passed", "modified_papers": len(rows), "new_authored_answers": answers,
            "preserved_existing_answers": preserved_total,
            "provinces": sorted({p.split("/")[1] for p in paths}),
            "boundary": "AI-assisted original study answers; not official keys or fenbi analysis",
            "manifest": "row-level updates only; untouched rows byte-identical"}

if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))

def records(root=ROOT):
    root = Path(root)
    return [json.loads(l) for l in (root / RECEIPT).read_text(encoding="utf-8").splitlines() if l.strip()]

def historical_snapshot(root: Path, destination: Path) -> None:
    """Rebuild the pre-E5NW tree so older receipts can be verified unchanged."""
    import shutil
    root = Path(root).resolve(); destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "reports", destination / "reports")
    for top in ("国考", "省考"):
        src = root / top
        if not src.is_dir():
            continue
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
        "S5R2-ORIGINAL-ANSWERS-20261021.jsonl", "S5R3-ORIGINAL-ANSWERS-20261021.jsonl",
        "SOURCED-SUPPLEMENT-20261013.jsonl")
    for name in names:
        f = root / "reports" / name
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rel = json.loads(line)["path"]
            src = (root / rel).resolve(); dst = (destination / rel).resolve()
            if (not src.is_relative_to(root) or not dst.is_relative_to(destination) or not src.is_file()):
                raise ValueError("Unsafe/absent E5NW dependency: " + rel)
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
    (destination / RECEIPT).unlink()
