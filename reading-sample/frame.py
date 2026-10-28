#!/usr/bin/env python3
"""Build the sampling frame from the read-only main snapshot + baseline receipts."""
import json, os, re, sys

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
BASE = sys.argv[2] if len(sys.argv) > 2 else "/home/fjd/scratch/gwy-format-final-20261028/structure/out/baseline/receipts.jsonl"
Q1 = "/home/fjd/scratch/gwy-fenbi-qa-parallel-20261027/q1-snapshots/out/source-map.jsonl"
OUT = sys.argv[3] if len(sys.argv) > 3 else "frame.jsonl"

def front(text):
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i; break
    if end is None:
        return {}
    d = {}
    for line in lines[1:end]:
        if ":" not in line or not line.strip():
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            try: v = json.loads(v)
            except Exception: v = v.strip('"')
        elif v.startswith("["):
            try: v = json.loads(v)
            except Exception: pass
        d[k.strip()] = v
    return d

risk = {}
if os.path.exists(BASE):
    for line in open(BASE, encoding="utf-8"):
        r = json.loads(line)
        risk[r["path"]] = {
            "template": r["template"],
            "counts": r["counts"],
            "codes": sorted({i["code"] for i in r["issues"]}),
            "stats": r["stats"],
        }

src = {}
if os.path.exists(Q1):
    for line in open(Q1, encoding="utf-8"):
        r = json.loads(line)
        src[r["key"]] = {"class": r["class"], "content": r.get("content"), "title": r.get("title")}

rows = []
for dp, dn, fn in os.walk(REPO):
    dn[:] = [d for d in dn if d != ".git"]
    for name in sorted(fn):
        if not name.endswith(".md") or not (name.startswith("行测-") or name.startswith("申论-")):
            continue
        full = os.path.join(dp, name)
        rel = os.path.relpath(full, REPO)
        text = open(full, encoding="utf-8").read()
        fm = front(text)
        subject = "xingce" if str(fm.get("科目")) in ("行测", "xingce") else "shenlun"
        sid = str(fm.get("源试卷ID") or "").strip()
        key = f"{subject}:{sid}" if sid else ""
        s = src.get(key, {})
        rows.append({
            "path": rel,
            "area": str(fm.get("地区") or fm.get("考试") or ""),
            "exam": str(fm.get("考试") or ""),
            "year": str(fm.get("年份") or ""),
            "subject": fm.get("科目") or "",
            "subject_key": subject,
            "variant": str(fm.get("卷型") or ""),
            "nature": str(fm.get("真题性质") or ""),
            "validation": str(fm.get("校验状态") or ""),
            "source_id": sid,
            "key": key,
            "source_class": s.get("class", ""),
            "source_title": s.get("title", ""),
            "risk": risk.get(rel, {}),
        })

with open(OUT, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print(json.dumps({"papers": len(rows), "out": OUT, "with_source": sum(1 for r in rows if r["key"])}, ensure_ascii=False))
