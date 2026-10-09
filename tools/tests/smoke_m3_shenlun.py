# -*- coding: utf-8 -*-
"""真源只读冒烟：全量 468 卷渲染，多重集比较源行与导出行（判据健全性，R-M3-7）。

成员资格检查（`x not in out.body`）会漏掉「多出来的行」，也数不清「少了几份同一行」；
改用 `collections.Counter` 的多重集差（源行 − 导出行 / 导出行 − 源行）。
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import shenlun
from gwyzhenti.model import PaperKey

UP = r"D:\projects\_gwy-upstream\gongkao-tiku"
CAT = r"D:\projects\gwy-zhenti\work\catalog\catalog.jsonl"


def _diff(qs, out):
    cs = collections.Counter(shenlun.source_lines(qs))
    co = collections.Counter(shenlun.strip_structure(out.body))
    return sorted((cs - co).elements()), sorted((co - cs).elements())


src = shenlun.load_source(UP)
rows = [json.loads(l) for l in open(CAT, encoding="utf-8") if l.strip()]
sl = [r for r in rows if r["subject"] == "申论" and r["year"] >= "2016"]
print("源卷数", len(src), "| 2016+ 申论行", len(sl))

bad = []
for r in sl:
    qs = shenlun.questions_for_titles(src, shenlun.titles_of(r))
    key = PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"])
    out = shenlun.render_paper(qs, key, nature=r["nature"], form=r["form"], sources=r["sources"])
    missing, extra = _diff(qs, out)
    print(" %-34s 题 %2d/%2d | 源行缺失 %d | 导出独有 %d | md %d 字节"
          % (r["slug"], out.n_questions, r["n_questions"], len(missing), len(extra),
             len(out.body.encode("utf-8"))))
    if missing or extra:
        bad.append((r["slug"], len(missing), len(extra), missing[:5], extra[:5]))

for slug, nm, ne, m, e in bad[:10]:
    print("  差异卷 %-34s 缺 %d / 多 %d | 缺样 %r | 多样 %r" % (slug, nm, ne, m, e))
print("有差异的卷 =", len(bad), "/", len(sl))
