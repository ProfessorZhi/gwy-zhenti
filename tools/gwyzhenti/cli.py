# -*- coding: utf-8 -*-
"""命令行入口：catalog（段一）| export（段二）| gate（闸门）。"""
import argparse
import os
import sys

from . import catalog


def _uproots(args):
    return {
        "xingcezhenti": os.path.join(args.upstream, "xingcezhenti"),
        "linfukai186": os.path.join(args.upstream, "gongkao-tiku"),
    }


def cmd_catalog(args):
    rep = catalog.build(_uproots(args), args.out)
    print("段一完成 →", args.out)
    print("  卷 %d | 卷×模块记录 %d | 题 %d" % (rep.papers, rep.records, rep.questions))
    print("  未解析 %d | 已排除 %d" % (rep.unparsed, rep.excluded))
    return 0


def cmd_export(args):
    from . import export
    rep = export.run(args.catalog, _uproots(args), args.repo,
                     limit=args.limit, since=(args.since or None))
    print("段二完成 →", args.repo)
    print("  卷 %d | md %d | 图片 %d" % (rep.papers, rep.files, rep.images))
    if rep.skipped:
        print("  跳过 %d 项（详见报告）" % len(rep.skipped))
    if rep.collided:
        # 撞 slug：同一键在 xingcezhenti 侧有多名 ⇒ 只导了第一个，其余记在此。**必须显式打印** ——
        # 它与「没导出」是两种事故，混在 skipped 里会让人以为只是上游缺文件（裁定 R-T8-1）。
        print("  撞 slug 未导的卷名 %d 条（详见报告）" % len(rep.collided))
    return 0


def cmd_gate(args):
    from . import gates
    rep = gates.run_all(args.catalog, _uproots(args), args.repo, limit=args.limit)
    for name, ok, detail in rep.results:
        print("  [%s] %s —— %s" % ("OK" if ok else "FAIL", name, detail))
    return 0 if rep.ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gwyzhenti")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("catalog", help="段一：产清单，不碰正文")
    c.add_argument("--upstream", required=True, help=r"上游克隆根目录，如 D:\projects\_gwy-upstream")
    c.add_argument("--out", required=True, help=r"产物目录，如 <repo>\work\catalog")
    c.set_defaults(func=cmd_catalog)

    e = sub.add_parser("export", help="段二：逐卷导出")
    e.add_argument("--catalog", required=True)
    e.add_argument("--upstream", required=True)
    e.add_argument("--repo", required=True)
    e.add_argument("--limit", type=int, default=0)
    e.add_argument("--since", default="", help="只导出该年及以后（如 2016）；空 = 不过滤")
    e.set_defaults(func=cmd_export)

    g = sub.add_parser("gate", help="跑 G1–G6")
    g.add_argument("--catalog", required=True)
    g.add_argument("--upstream", required=True)
    g.add_argument("--repo", required=True)
    g.add_argument("--limit", type=int, default=0)
    g.set_defaults(func=cmd_gate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
