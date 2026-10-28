#!/usr/bin/env python3
"""Build the minimum-risk candidate patches (scratch only).

One patch per file against main efea3003:
  0001 SH2017  : drop trailing `---` before </details> AND drop the duplicated
                 "解析" that immediately follows **官方解析**
  0002 GD2016  : drop trailing `---` before </details>
  0003 JS2024C : drop trailing `---` before </details>
  0004 BJ2026  : drop the stray </u>            (mirror of PR#140)
  0005 QH2014  : wrap |甲-乙|=|丙-丁| in code    (mirror of PR#140)
"""
import os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
PR140 = "/home/fjd/scratch/gwy-format-final-20261028/structure/reading-sample/repo-pr140"

def read_main(p): return open(os.path.join(MAIN, p), encoding="utf-8").read()
def read_pr(p): return open(os.path.join(PR140, p), encoding="utf-8").read()

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

def emit(p, name, new):
    dst = os.path.join(HERE, "work", p)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w", encoding="utf-8").write(new)
    src = os.path.join(MAIN, p)
    d = subprocess.run(["diff", "-u", src, dst], capture_output=True, text=True).stdout
    d = d.replace(src, "a/" + p).replace(dst, "b/" + p)
    open(os.path.join(HERE, "patches", name), "w", encoding="utf-8").write(d)
    return len([l for l in d.splitlines() if l.startswith("-") and not l.startswith("---")])

counts = {}
p = "省考/上海/2017/行测-统考.md"
counts[p] = emit(p, "0001-shanghai2017-hr-and-dup-jiexi.patch", drop_dup_label(drop_hr(read_main(p))))
p = "省考/广东/2016/行测-广州市考.md"
counts[p] = emit(p, "0002-guangzhou2016xingce-drop-hr.patch", drop_hr(read_main(p)))
p = "省考/江苏/2024/行测-C类.md"
counts[p] = emit(p, "0003-jiangsu2024c-drop-hr.patch", drop_hr(read_main(p)))
p = "省考/北京/2026/申论-选调生.md"
counts[p] = emit(p, "0004-beijing2026-stray-u-close.patch", read_pr(p))
p = "省考/青海/2014/行测-统考.md"
counts[p] = emit(p, "0005-qinghai2014-pipe-math.patch", read_pr(p))
print(counts)
