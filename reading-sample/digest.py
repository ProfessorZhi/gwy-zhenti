#!/usr/bin/env python3
"""Bounded reading digest for one paper (read-only)."""
import argparse, hashlib, json, os, re, sys

MAIN = "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
PR140 = "/home/fjd/scratch/gwy-format-final-20261028/structure/reading-sample/repo-pr140"
BASE = "/home/fjd/scratch/gwy-format-final-20261028/structure/out/baseline/receipts.jsonl"
Q1 = "/home/fjd/scratch/gwy-fenbi-qa-parallel-20261027/q1-snapshots/out/source-map.jsonl"

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--mode", choices=["full", "spot", "table"], default="full")
    ap.add_argument("--max-q", type=int, default=0)
    a = ap.parse_args()

    rel = a.path
    fp = os.path.join(MAIN, rel)
    blob = open(fp, "rb").read()
    text = blob.decode("utf-8")
    fm = front(text)
    prp = os.path.join(PR140, rel)
    pr_sha = ""
    pr_same = None
    if os.path.exists(prp):
        pb = open(prp, "rb").read()
        pr_sha = sha(pb)
        pr_same = (pb == blob)

    # baseline issues for this path
    flags = []
    if os.path.exists(BASE):
        for line in open(BASE, encoding="utf-8"):
            r = json.loads(line)
            if r["path"] == rel:
                flags = r["issues"]; tmpl = r["template"]; stats = r["stats"]
                break
    else:
        tmpl = ""; stats = {}

    # source sha
    src_sha = ""
    key = ""
    subj = "xingce" if str(fm.get("科目")) in ("行测", "xingce") else "shenlun"
    sid = str(fm.get("源试卷ID") or "").strip()
    if sid:
        key = f"{subj}:{sid}"
        if os.path.exists(Q1):
            for line in open(Q1, encoding="utf-8"):
                r = json.loads(line)
                if r["key"] == key:
                    src_sha = r.get("primary_document_sha256") or ""
                    break

    lines = text.split("\n")
    meta = {
        "path": rel, "file_sha": sha(blob), "bytes": len(blob),
        "pr140_sha": pr_sha, "pr140_same": pr_same,
        "key": key, "source_sha": src_sha,
        "area": fm.get("地区"), "year": fm.get("年份"), "subject": fm.get("科目"),
        "variant": fm.get("卷型"), "nature": fm.get("真题性质"), "validation": fm.get("校验状态"),
        "template": tmpl, "stats": stats,
        "flags": [f for f in flags if f["severity"] != "info"],
    }
    print("=== META " + json.dumps(meta, ensure_ascii=False))

    # outline
    print("=== OUTLINE")
    hd = [(i, l) for i, l in enumerate(lines, 1) if re.match(r"^(#{1,4})\s+", l)]
    cap = a.mode == "spot" or len(hd) > 45
    shown = 0
    for i, l in hd:
        m = re.match(r"^(#{1,4})\s+(.*)$", l)
        if re.match(r"^#{2,4}\s*第\s*\d+\s*题", l) and len(hd) > 12:
            continue
        if cap and len(m.group(1)) >= 3:
            continue
        print(f"  L{i} {m.group(1)} {m.group(2)[:60]}")
        shown += 1
    if cap and shown < len(hd):
        print(f"  … 另有 {len(hd)-shown} 个标题（题目标题见下表）")

    # overview
    s = text.find("<!-- gwy:overview:start -->"); e = text.find("<!-- gwy:overview:end -->")
    if s != -1 and e > s:
        print("=== OVERVIEW")
        print(clip(text[s:e + 25], 500))

    # materials
    print("=== MATERIALS")
    mat = re.split(r"(?m)^(?=###?\s*(?:给定)?材料\s*\d+)", text)
    for chunk in mat[1:]:
        first = chunk.split("\n", 1)[0]
        body = chunk[len(first):]
        body_txt = re.sub(r"!\[\]\([^)]*\)", "[图]", body)
        print(f"  {first.strip()} :: {clip(body_txt, 160)} (段落 {len([x for x in body.split('\n') if x.strip()])})")

    # questions
    qs = [(i, l) for i, l in enumerate(lines) if re.match(r"^#{2,4}\s*第\s*\d+\s*题", l)]
    print(f"=== QUESTIONS {len(qs)}")
    if a.mode == "table":
        for idx, (i, head) in enumerate(qs):
            end = qs[idx + 1][0] if idx + 1 < len(qs) else len(lines)
            block = "\n".join(lines[i:end])
            det = "Y" if re.search(r"<details\b", block) else "N"
            pre = block.split("<details", 1)[0]
            stem = [x for x in pre.split("\n")[1:] if x.strip() and not re.match(r"^\s*(?:[-*+]\s*)?(?:\*\*)?[A-H](?:\*\*)?\s*[.、．]", x) and not x.strip().startswith(("关联材料", "作答要求"))]
            opts = [x.strip() for x in pre.split("\n") if re.match(r"^\s*(?:[-*+]\s*)?(?:\*\*)?[A-H](?:\*\*)?\s*[.、．]", x)]
            labels = "".join(re.match(r"^\s*(?:[-*+]\s*)?(?:\*\*)?([A-H])", o).group(1) for o in opts) if opts else "-"
            mref = re.search(r"关联材料\s*[：:]\s*([^\n]+)", pre)
            m = re.search(r"参考答案[^\n]*\n+([^\n]+)", block) or re.search(r"\*\*答案\*\*\s*[：:]\s*([^\n]+)", block)
            ans = (m.group(1).strip() if m else "")
            ana = "Y" if re.search(r"\*\*(?:官方)?解析\*\*|\*\*分析\*\*|\*\*答案解析\*\*", block) else "N"
            qflags = [f["code"] for f in flags if i + 1 <= f["line"] < end and f["line"] > 0]
            print(f"  Q{idx+1:>3}@{i+1:<6} d={det} opts={labels:<6} ans={clip(ans,18):<18} ana={ana} "
                  f"ref={clip(mref.group(1),12) if mref else '-':<12} | {clip(' '.join(stem), 70)}"
                  + (f" | !!{','.join(qflags[:3])}" if qflags else ""))
        print(f"=== TABLE_LINES {len(re.findall(r'(?m)^\|.*\|\s*$', text))} IMAGES {len(re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text))}")
        return
    picks = list(range(len(qs)))
    if a.mode == "spot" and len(qs) > 3:
        picks = [0, len(qs) // 2, len(qs) - 1]
    if a.max_q:
        picks = picks[: a.max_q]
    for idx in picks:
        i, head = qs[idx]
        end = qs[idx + 1][0] if idx + 1 < len(qs) else len(lines)
        block = "\n".join(lines[i:end])
        det = re.search(r"<details\b", block)
        pre = block[: det.start()] if det else block
        stem_lines = [x for x in pre.split("\n")[1:] if x.strip() and not re.match(r"^[-*+]\s*\*\*[A-H]", x) and not re.match(r"^[A-H]\s*[.、．]", x)]
        opts = [x.strip() for x in pre.split("\n") if re.match(r"^\s*(?:[-*+]\s*)?(?:\*\*)?[A-H](?:\*\*)?\s*[.、．]", x)]
        ans = ""
        m = re.search(r"参考答案[^\n]*\n+([^\n]+)", block)
        if m: ans = m.group(1)
        if not ans:
            m = re.search(r"\*\*答案\*\*\s*[：:]\s*([^\n]+)", block)
            if m: ans = m.group(1)
        ana = ""
        m = re.search(r"\*\*(?:官方)?解析\*\*\s*\n+([^\n]+)", block)
        if m: ana = m.group(1)
        print(f"-- Q{idx+1} @L{i+1} {head.strip()[:60]} | details={'Y' if det else 'N'} | opts={len(opts)}")
        print(f"   STEM: {clip(' '.join(stem_lines), 360)}")
        if opts:
            print("   OPTS: " + " | ".join(clip(o, 60) for o in opts[:6]))
        print(f"   ANS : {clip(ans, 120)}")
        if ana:
            print(f"   ANA : {clip(ana, 200)}")
        qflags = [f for f in flags if i + 1 <= f["line"] < end and f["line"] > 0]
        if qflags:
            print("   FLAGS: " + "; ".join(f"{f['code']}@{f['line']} {f['message'][:50]}" for f in qflags[:4]))

    # tables/images
    tb = len(re.findall(r"(?m)^\|.*\|\s*$", text))
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text) + re.findall(r'<img[^>]+src="([^"]+)"', text)
    print(f"=== TABLE_LINES {tb} IMAGES {len(imgs)}")
    for u in imgs[:6]:
        print("   IMG " + clip(u, 90))
    if len(imgs) > 6:
        print(f"   … +{len(imgs)-6} more")

if __name__ == "__main__":
    main()
