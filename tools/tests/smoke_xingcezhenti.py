# -*- coding: utf-8 -*-
"""真库冒烟：读本机 xingcezhenti 克隆，核对题数与排除项。手工运行。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.xingcezhenti import XingceZhentiAdapter      # noqa: E402

ROOT = r"D:\projects\_gwy-upstream\xingcezhenti"


def main():
    res = XingceZhentiAdapter().scan(ROOT)
    total = sum(r["n_questions"] for r in res.records)
    print("records %d | unparsed %d | excluded %d | 题数合计 %d"
          % (len(res.records), len(res.unparsed), len(res.excluded), total))
    reasons = {}
    for e in res.excluded:
        reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
    for k in sorted(reasons):
        print("  excluded %4d  %s" % (reasons[k], k))
    assert total == 58890, "题数合计应为 58890，实得 %d" % total


if __name__ == "__main__":
    main()
