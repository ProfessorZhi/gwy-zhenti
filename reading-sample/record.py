#!/usr/bin/env python3
"""Merge human/AI judgments with machine metadata and append to receipts.jsonl.

Usage: python3 -I record.py batch1.json
Each batch item: {path, read_mode, verdicts{...}, review_type, status, issues[], notes}
"""
import hashlib, json, os, sys

MAIN = "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
PR140 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repo-pr140")
Q1 = "/home/fjd/scratch/gwy-fenbi-qa-parallel-20261027/q1-snapshots/out/source-map.jsonl"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts.jsonl")

def sha(b): return hashlib.sha256(b).hexdigest()

def front(text):
    if not text.startswith("---"): return {}
    lines = text.splitlines(); end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---": end = i; break
    if end is None: return {}
    d = {}
    for line in lines[1:end]:
        if ":" not in line: continue
        k, _, v = line.partition(":"); v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            try: v = json.loads(v)
            except Exception: v = v.strip('"')
        d[k.strip()] = v
    return d

src_map = {}
if os.path.exists(Q1):
    for line in open(Q1, encoding="utf-8"):
        r = json.loads(line)
        src_map[r["key"]] = r.get("primary_document_sha256") or ""

items = json.load(open(sys.argv[1], encoding="utf-8"))
rank_of = {}
sample = "/home/fjd/scratch/gwy-format-final-20261028/structure/reading-sample/sample.jsonl"
for line in open(sample, encoding="utf-8"):
    r = json.loads(line); rank_of[r["path"]] = r

existing = set()
if os.path.exists(OUT):
    for line in open(OUT, encoding="utf-8"):
        existing.add(json.loads(line)["path"])

added = 0
with open(OUT, "a", encoding="utf-8") as fh:
    for it in items:
        path = it["path"]
        if path in existing:
            print("skip duplicate", path); continue
        blob = open(os.path.join(MAIN, path), "rb").read()
        text = blob.decode("utf-8")
        fm = front(text)
        subj = "xingce" if str(fm.get("科目")) in ("行测", "xingce") else "shenlun"
        sid = str(fm.get("源试卷ID") or "").strip()
        key = f"{subj}:{sid}" if sid else ""
        prp = os.path.join(PR140, path)
        pb = open(prp, "rb").read() if os.path.exists(prp) else b""
        meta = rank_of.get(path, {})
        rec = {
            "rank": meta.get("rank"),
            "path": path,
            "source_sha": src_map.get(key, ""),
            "source_key": key,
            "file_sha": sha(blob),
            "pr140_sha": sha(pb) if pb else "",
            "pr140_same": (pb == blob) if pb else None,
            "area": fm.get("地区"), "year": fm.get("年份"), "subject": fm.get("科目"),
            "variant": fm.get("卷型"), "nature": fm.get("真题性质"),
            "validation": fm.get("校验状态"),
            "source_class": meta.get("source_class", ""),
            "qcount": meta.get("risk", {}).get("stats", {}).get("questions"),
            "template": meta.get("risk", {}).get("template"),
            "read_mode": it["read_mode"],
            "full_read": it["read_mode"] == "full",
            "full_file": bool(it.get("full_file", False)),
            "verdicts": it["verdicts"],
            "review_type": it["review_type"],
            "status": it["status"],
            "issues": it.get("issues", []),
            "visual_pending": it.get("visual_pending", []),
            "notes": it.get("notes", ""),
            "lane": "AI-assisted reading evaluation (not human L3)",
        }
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        added += 1
print(json.dumps({"added": added, "total": len(existing) + added}, ensure_ascii=False))
