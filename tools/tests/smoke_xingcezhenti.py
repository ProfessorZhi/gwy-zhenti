# -*- coding: utf-8 -*-
"""真库冒烟：读本机 xingcezhenti 克隆，核对题数与排除项。手工运行。

本脚本断言的是本机克隆的冻结值（2497/0/459 与全库 58890）；上游变动时它会失败，这是设计意图。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import mdread                                       # noqa: E402
from gwyzhenti.sources.xingcezhenti import XingceZhentiAdapter      # noqa: E402

ROOT = r"D:\projects\_gwy-upstream\xingcezhenti"


def main():
    res = XingceZhentiAdapter().scan(ROOT)
    total = sum(r["n_questions"] for r in res.records)
    print("records %d | unparsed %d | excluded %d | 题数合计(入选) %d"
          % (len(res.records), len(res.unparsed), len(res.excluded), total))
    reasons = {}
    for e in res.excluded:
        reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
    for k in sorted(reasons):
        print("  excluded %4d  %s" % (reasons[k], k))

    # 对账：records 是**入选卷**口径，天然小于全库。要证明「没有静默丢文件」，
    # 必须把「有意排除」的卷也数一遍 —— 三桶之和 == 全库题数 58890。
    excl_total = 0
    for e in res.excluded:
        with open(os.path.join(ROOT, *e["relpath"].split("/")), encoding="utf-8") as fh:
            excl_total += mdread.count_questions(fh.read())
    print("excluded 题数 %d | 三桶合计 %d | 全库 58890" % (excl_total, total + excl_total))

    assert (len(res.records), len(res.unparsed), len(res.excluded)) == (2497, 0, 459), \
        "分桶计数漂移：%d/%d/%d" % (len(res.records), len(res.unparsed), len(res.excluded))
    assert total + excl_total == 58890, \
        "对账失败：入选 %d + 排除 %d = %d，应为 58890" % (total, excl_total, total + excl_total)


if __name__ == "__main__":
    main()
