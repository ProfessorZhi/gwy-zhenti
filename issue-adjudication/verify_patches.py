#!/usr/bin/env python3
"""Prove the candidate patches never change 题干/选项/材料/答案 text."""
import hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
PR140 = "/home/fjd/scratch/gwy-format-final-20261028/structure/reading-sample/repo-pr140"

def rd(base, p): return open(os.path.join(base, p), encoding="utf-8").read()
def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()

def drop_hr(text):
    lines = text.split("\n"); out = []
    for i, l in enumerate(lines):
        if l.strip() == "---":
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().startswith("</details"):
                continue
        out.append(l)
    return "\n".join(out)

def drop_dup_label(text):
    return re.sub(r"(\*\*官方解析\*\*\s*\n+\s*)解析[ 　]?", r"\1", text)

def strip_rules(text):
    return "\n".join(l for l in text.split("\n") if l.strip() != "---")

def split_details(text):
    out, blocks, pos = [], [], 0
    for m in re.finditer(r"<details\b[^>]*>(.*?)</details>", text, re.S):
        out.append(text[pos:m.start()]); blocks.append(m.group(1)); pos = m.end()
    out.append(text[pos:])
    return "".join(out), blocks

def answer_part(block):
    inner = re.sub(r"<summary\b[^>]*>.*?</summary>", "", block, flags=re.S)
    m = re.search(r"\*\*(?:官方)?解析\*\*", inner)
    return inner[: m.start()] if m else inner

def analysis_body(block):
    inner = re.sub(r"<summary\b[^>]*>.*?</summary>", "", block, flags=re.S)
    m = re.search(r"\*\*官方解析\*\*\s*\n+\s*(.*)", inner, re.S)
    return m.group(1) if m else None

CASES = [
    ("0001", "省考/上海/2017/行测-统考.md", "hr+dup"),
    ("0002", "省考/广东/2016/行测-广州市考.md", "hr"),
    ("0003", "省考/江苏/2024/行测-C类.md", "hr"),
    ("0004", "省考/北京/2026/申论-选调生.md", "pr140"),
    ("0005", "省考/青海/2014/行测-统考.md", "pr140"),
]

rows = []
for tag, p, kind in CASES:
    before = rd(MAIN, p)
    after = rd(os.path.join(HERE, "work"), p)
    problems = []
    if kind == "hr":
        expect = drop_hr(before)
    elif kind == "hr+dup":
        expect = drop_dup_label(drop_hr(before))
    else:
        expect = rd(PR140, p)
    if after != expect:
        problems.append("output differs from intended transformation")

    ob, bb = split_details(before)
    oa, ba = split_details(after)
    if ob != oa:
        problems.append("text outside <details> changed")
    if [answer_part(x) for x in bb] != [answer_part(x) for x in ba]:
        problems.append("answer section changed")
    if kind in ("hr",):
        if strip_rules(before) != strip_rules(after):
            problems.append("non-rule text changed")
    if kind == "hr+dup":
        # every analysis body may only lose the duplicated 解析 label
        for x, y in zip(bb, ba):
            ax, ay = analysis_body(x), analysis_body(y)
            if ax is None and ay is None:
                continue
            nb = "\n".join(l for l in re.sub(r"^解析[ \u3000]?", "", ax or "").split("\n") if l.strip() != "---")
            na = "\n".join(l for l in (ay or "").split("\n") if l.strip() != "---")
            if nb != na:
                problems.append("analysis body changed beyond the duplicated label")
                break
        before_rules = sum(1 for l in before.split("\n") if l.strip() == "---")
        after_rules = sum(1 for l in drop_dup_label(before).split("\n") if l.strip() == "---")
        if before_rules != after_rules:
            problems.append("dedup touched a thematic rule")
    if kind == "pr140":
        if tag == "0004":
            strip = lambda s: re.sub(r"<[^>]+>", "", s)
            if strip(before) != strip(after):
                problems.append("visible text changed")
        else:
            bl, al = before.split("\n"), after.split("\n")
            changed = [x for x in bl if x not in al]
            if len(changed) != 1 or len(bl) != len(al):
                problems.append("more than one line changed")

    rows.append({
        "patch": tag, "path": p, "kind": kind,
        "before_sha": sha(before), "after_sha": sha(after),
        "bytes_before": len(before.encode()), "bytes_after": len(after.encode()),
        "questions": len(bb), "answers_identical": not any("answer" in x for x in problems),
        "pass": not problems, "problems": problems,
    })

json.dump(rows, open(os.path.join(HERE, "patch-verification.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
ok = True
for r in rows:
    print(f"{r['patch']} {'PASS' if r['pass'] else 'FAIL'} {r['path']}")
    print(f"   sha {r['before_sha'][:16]} -> {r['after_sha'][:16]}  bytes {r['bytes_before']} -> {r['bytes_after']}  blocks={r['questions']}")
    if r["problems"]:
        print("   problems:", r["problems"])
        ok = False
sys.exit(0 if ok else 1)
