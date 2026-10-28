#!/usr/bin/env python3
"""Per-case evidence collector (read-only)."""
import hashlib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
PR140 = "/home/fjd/scratch/gwy-format-final-20261028/structure/reading-sample/repo-pr140"
Q1 = "/home/fjd/scratch/gwy-fenbi-qa-parallel-20261027/q1-snapshots/out/source-map.jsonl"
RECEIPTS = "/home/fjd/scratch/gwy-format-final-20261028/structure/reading-sample/receipts.jsonl"

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

src = {}
for line in open(Q1, encoding="utf-8"):
    r = json.loads(line); src[r["key"]] = r

rec = {}
for line in open(RECEIPTS, encoding="utf-8"):
    r = json.loads(line); rec[r["path"]] = r

out = []
for line in open(os.path.join(HERE, "cases.txt"), encoding="utf-8"):
    line = line.strip()
    if not line: continue
    rank, path = line.split("|", 1)
    mb = open(os.path.join(MAIN, path), "rb").read()
    pb = open(os.path.join(PR140, path), "rb").read() if os.path.exists(os.path.join(PR140, path)) else b""
    text = mb.decode("utf-8"); lines = text.split("\n")
    fm = front(text)
    subj = "xingce" if str(fm.get("科目")) in ("行测", "xingce") else "shenlun"
    sid = str(fm.get("源试卷ID") or "").strip()
    key = f"{subj}:{sid}" if sid else ""
    s = src.get(key, {})
    diff = subprocess.run(["diff", "-u", os.path.join(MAIN, path), os.path.join(PR140, path)],
                          capture_output=True, text=True).stdout
    out.append({
        "rank": int(rank), "path": path,
        "main_sha": sha(mb), "pr140_sha": sha(pb) if pb else "", "pr140_same": pb == mb if pb else None,
        "bytes": len(mb), "lines": len(lines),
        "area": fm.get("地区"), "year": fm.get("年份"), "subject": fm.get("科目"), "variant": fm.get("卷型"),
        "nature": fm.get("真题性质"), "validation": fm.get("校验状态"),
        "source": {"type": fm.get("来源"), "source_id": sid, "key": key,
                   "class": s.get("class", ""), "doc_sha": s.get("primary_document_sha256") or "",
                   "doc_path": s.get("primary_document") or ""},
        "receipt_status": rec.get(path, {}).get("status"),
        "receipt_issues": rec.get(path, {}).get("issues", []),
        "diff_lines": len(diff.splitlines()), "diff_head": "\n".join(diff.splitlines()[:40]),
    })

json.dump(out, open(os.path.join(HERE, "collected.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for o in out:
    print(f"{o['rank']:>2} {o['path']}")
    print(f"   main {o['main_sha'][:16]} pr140 {o['pr140_sha'][:16] or '-'} same={o['pr140_same']} bytes={o['bytes']} lines={o['lines']} diffLines={o['diff_lines']}")
    print(f"   src key={o['source']['key'] or '-'} class={o['source']['class'] or '-'} doc={o['source']['doc_sha'][:16] or '-'}")
