# -*- coding: utf-8 -*-
"""真源只读冒烟：抽 3 卷渲染，断言题数与源一致、且源行全在导出里。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import shenlun
from gwyzhenti.model import PaperKey

UP = r"D:\projects\_gwy-upstream\gongkao-tiku"
CAT = r"D:\projects\gwy-zhenti\work\catalog\catalog.jsonl"

src = shenlun.load_source(UP)
rows = [json.loads(l) for l in open(CAT, encoding="utf-8") if l.strip()]
sl = [r for r in rows if r["subject"] == "申论" and r["year"] >= "2016"]
print("源卷数", len(src), "| 2016+ 申论行", len(sl))
for r in sl[:3]:
    qs = shenlun.questions_for_titles(src, shenlun.titles_of(r))
    key = PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"])
    out = shenlun.render_paper(qs, key, nature=r["nature"], form=r["form"], sources=r["sources"])
    missing = [x for x in shenlun.source_lines(qs) if x not in out.body]
    print(" %-34s 题 %2d/%2d | 源行缺失 %d | md %d 字节"
          % (r["slug"], out.n_questions, r["n_questions"], len(missing), len(out.body.encode("utf-8"))))
