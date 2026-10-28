#!/usr/bin/env python3
"""Per-paper reading packet: structure facts + sampled excerpts, written to evidence/.

Usage: python3 -I sweep.py [--ranks 1,2,3] [--depth full|spot]
Prints one compact JSON line per paper; the full packet goes to evidence/NNN-*.txt.
"""
import argparse, hashlib, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
PR140 = os.path.join(HERE, "repo-pr140")
BASE = "/home/fjd/scratch/gwy-format-final-20261028/structure/out/baseline/receipts.jsonl"
Q1 = "/home/fjd/scratch/gwy-fenbi-qa-parallel-20261027/q1-snapshots/out/source-map.jsonl"
EV = os.path.join(HERE, "evidence")

src_map = {}
for line in open(Q1, encoding="utf-8"):
    r = json.loads(line); src_map[r["key"]] = r.get("primary_document_sha256") or ""
base = {}
for line in open(BASE, encoding="utf-8"):
    r = json.loads(line); base[r["path"]] = r

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

def clip(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n] + f"…(+{len(s)-n})"

def packet(r, depth):
    path = r["path"]; fp = os.path.join(MAIN, path)
    blob = open(fp, "rb").read(); text = blob.decode("utf-8"); lines = text.split("\n")
    fm = front(text)
    subj = "xingce" if str(fm.get("科目")) in ("行测", "xingce") else "shenlun"
    sid = str(fm.get("源试卷ID") or "").strip(); key = f"{subj}:{sid}" if sid else ""
    prp = os.path.join(PR140, path); pb = open(prp, "rb").read() if os.path.exists(prp) else b""

    qs = [(i, l) for i, l in enumerate(lines) if re.match(r"^#{2,4}\s*第\s*(\d+)\s*题", l)]
    qstats = []
    opt_labels_hist = {}
    ans_empty = 0; multi_ans = 0; no_ana = 0; dup_jiexi = 0; hr_in_details = 0
    for idx, (i, head) in enumerate(qs):
        end = qs[idx + 1][0] if idx + 1 < len(qs) else len(lines)
        block = "\n".join(lines[i:end])
        det = "<details" in block
        pre = block.split("<details", 1)[0]
        opts = [x for x in pre.split("\n") if re.match(r"^\s*(?:[-*+]\s*)?(?:\*\*)?[A-H](?:\*\*)?\s*[.、．]", x)]
        labels = "".join(re.match(r"^\s*(?:[-*+]\s*)?(?:\*\*)?([A-H])", o).group(1) for o in opts)
        opt_labels_hist[labels or "-"] = opt_labels_hist.get(labels or "-", 0) + 1
        m = re.search(r"参考答案[^\n]*\n+([^\n]+)", block) or re.search(r"\*\*答案\*\*\s*[：:]\s*([^\n]+)", block)
        ans = (m.group(1).strip() if m else "")
        if not ans: ans_empty += 1
        if re.fullmatch(r"[A-H]{2,}", ans): multi_ans += 1
        if not re.search(r"\*\*(?:官方)?解析\*\*|\*\*答案解析\*\*", block): no_ana += 1
        if re.search(r"\*\*(?:官方)?解析\*\*\s*\n+\s*解析\s", block): dup_jiexi += 1
        if re.search(r"\n---\s*\n+</details>", block): hr_in_details += 1
        mref = re.search(r"关联材料\s*[：:]\s*([^\n]+)", pre)
        qstats.append({"n": idx + 1, "line": i + 1, "det": det, "opts": labels or "-", "ans": ans[:6],
                       "ana": "Y" if re.search(r"\*\*(?:官方)?解析\*\*|\*\*答案解析\*\*", block) else "N",
                       "ref": (mref.group(1) if mref else "")[:24]})

    images = len(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)) + len(re.findall(r'<img[^>]+src="([^"]+)"', text))
    tables = len(re.findall(r"(?m)^\|.*\|\s*$", text))
    latex = text.count("$")
    longest = max((len(x) for x in lines), default=0)
    ph = len(re.findall(r"暂未收录|来源缺题|题位保留|缺原题|正在搜集中", text))
    h2 = [l for l in lines if re.match(r"^## ", l)]
    h3 = [l for l in lines if re.match(r"^### ", l)]

    meta = {
        "path": path, "file_sha": sha(blob), "bytes": len(blob),
        "pr140_sha": sha(pb) if pb else "", "pr140_same": (pb == blob) if pb else None,
        "key": key, "source_sha": src_map.get(key, ""),
        "area": fm.get("地区"), "year": fm.get("年份"), "subject": fm.get("科目"),
        "variant": fm.get("卷型"), "nature": fm.get("真题性质"), "validation": fm.get("校验状态"),
        "source_class": r.get("source_class", ""), "template": base.get(path, {}).get("template"),
        "qcount": len(qs), "h2": len(h2), "h3": len(h3), "tables": tables, "images": images,
        "latex_dollars": latex, "placeholder_marks": ph, "longest_line": longest,
        "answers_empty": ans_empty, "multi_answers": multi_ans, "no_analysis_marker": no_ana,
        "dup_jiexi_label": dup_jiexi, "hr_inside_details": hr_in_details,
        "opt_label_hist": opt_labels_hist,
        "flags": [f["code"] for f in base.get(path, {}).get("issues", []) if f["severity"] != "info"],
    }

    os.makedirs(EV, exist_ok=True)
    out = []
    out.append(f"# PACKET {path}")
    out.append("META " + json.dumps(meta, ensure_ascii=False))
    out.append("")
    out.append("## FRONTMATTER")
    for k in ("考试", "地区", "年份", "科目", "卷型", "真题性质", "来源", "源试卷ID", "采集时间", "校验状态"):
        if k in fm: out.append(f"- {k}: {clip(str(fm[k]), 200)}")
    out.append("")
    out.append("## OUTLINE (non-question headings)")
    for i, l in enumerate(lines, 1):
        if re.match(r"^#{1,3} ", l) and not re.match(r"^#{2,4}\s*第\s*\d+\s*题", l):
            out.append(f"  L{i} {l[:70]}")
    out.append("")
    out.append(f"## QUESTION TABLE ({len(qstats)})")
    for q in qstats:
        out.append(f"  Q{q['n']:>3}@{q['line']:<6} d={'Y' if q['det'] else 'N'} opts={q['opts']:<6} ans={q['ans']:<6} ana={q['ana']} ref={q['ref']}")
    samples = [0] if len(qs) == 1 else [0, len(qs) // 2, len(qs) - 1]
    if depth == "full" and len(qs) > 3:
        samples += [1, len(qs) - 2]
    out.append("")
    out.append(f"## SAMPLED EXCERPTS ({len(samples)})")
    for idx in samples:
        i, head = qs[idx]
        end = qs[idx + 1][0] if idx + 1 < len(qs) else len(lines)
        block = "\n".join(lines[i:end])
        pre = block.split("<details", 1)[0]
        out.append(f"--- Q{idx+1} @L{i+1}: {head.strip()[:70]}")
        out.append(clip(pre, 700))
        det = re.search(r"<details.*?</details>", block, re.S)
        if det:
            body = det.group(0)
            ans = re.search(r"参考答案[^\n]*\n+([^\n]+)", body) or re.search(r"\*\*答案\*\*\s*[：:]\s*([^\n]+)", body)
            out.append("  ANS: " + clip(ans.group(1), 160) if ans else "  ANS: (none)")
            ana = re.search(r"\*\*(?:官方)?解析\*\*\s*\n+(.{0,400})", body, re.S)
            if ana:
                out.append("  ANA: " + clip(ana.group(1), 300))
            else:
                out.append("  ANA: (no 解析 marker)")
    packet_path = os.path.join(EV, f"{r['rank']:03d}-" + re.sub(r"[^\w]+", "-", path)[-60:] + ".txt")
    open(packet_path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    meta["packet"] = os.path.relpath(packet_path, HERE)
    return meta

ap = argparse.ArgumentParser()
ap.add_argument("--ranks", default="")
ap.add_argument("--depth", choices=["full", "spot"], default="spot")
a = ap.parse_args()
sample = [json.loads(l) for l in open(os.path.join(HERE, "sample.jsonl"), encoding="utf-8")]
want = {int(x) for x in a.ranks.split(",") if x.strip()} if a.ranks else {r["rank"] for r in sample}
for r in sample:
    if r["rank"] in want:
        print(json.dumps(packet(r, a.depth), ensure_ascii=False))
