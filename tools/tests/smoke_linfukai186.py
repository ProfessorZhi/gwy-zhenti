# -*- coding: utf-8 -*-
"""真库冒烟：读本机 gongkao-tiku 克隆，核对四个类目的分桶。手工运行。

本脚本断言的是**本机克隆的冻结值**（分桶计数 `2767/0/309`）；上游变动时它会失败，这是设计意图。

`unparsed == 0` 是**实测结论**，但**不是**「地区别名表没漏词」那么简单：
四类目 `index.json` 共 **1,475** 个卷键，其中 **56 条是无地区的「模考」卷**
（100% 在 `shengkao-shenlun`）—— 它们靠 `classify` 的**检查顺序**
（排除族 → 标题排除词 → 地区为空）落进 `excluded` 的 `试卷名含排除词`，而非 `unparsed`。
若这个顺序被改回去，`unparsed` 会立刻涨到 56。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.linfukai186 import Linfukai186Adapter      # noqa: E402

ROOT = r"D:\projects\_gwy-upstream\gongkao-tiku"


def main():
    res = Linfukai186Adapter().scan(ROOT)
    per = {}
    for r in res.records:
        k = (r["subject"], r["region"])
        per[k] = per.get(k, 0) + r["n_questions"]
    print("records %d | unparsed %d | excluded %d | 题数合计 %d"
          % (len(res.records), len(res.unparsed), len(res.excluded),
             sum(r["n_questions"] for r in res.records)))
    for subj in ("行测", "申论"):
        rows = [r for r in res.records if r["subject"] == subj]
        provs = sorted({r["region"] for r in rows})
        print("  %s: %d 卷·模块行 | %d 个地区 | 地区: %s"
              % (subj, len(rows), len(provs), " ".join(provs)))
    reasons = {}
    for e in res.excluded:
        reasons[e["reason"].split(":")[0].strip()] = \
            reasons.get(e["reason"].split(":")[0].strip(), 0) + 1
    for k in sorted(reasons):
        print("  excluded %4d  %s" % (reasons[k], k))

    # 冻结哨兵：数字来源 = 本机 `D:\projects\_gwy-upstream\gongkao-tiku` 克隆实测（2026-10-09）。
    # 上游变动时它会失败，这是设计意图。
    assert (len(res.records), len(res.unparsed), len(res.excluded)) == (2767, 0, 309), \
        "分桶计数漂移：%d/%d/%d" % (len(res.records), len(res.unparsed), len(res.excluded))
    assert set(reasons) == {"试卷名含排除词", "非国省考地区"}, "排除理由分布漂移：%s" % reasons
    assert res.unparsed == [], "地区别名表漏词：%s" % [u["title"] for u in res.unparsed[:5]]
    assert [r for r in res.records if r["subject"] == "行测"], "行测一条都没有："
    assert [r for r in res.records if r["subject"] == "申论"], "申论一条都没有："


if __name__ == "__main__":
    main()
