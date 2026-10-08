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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gwyzhenti")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("catalog", help="段一：产清单，不碰正文")
    c.add_argument("--upstream", required=True, help=r"上游克隆根目录，如 D:\projects\_gwy-upstream")
    c.add_argument("--out", required=True, help=r"产物目录，如 <repo>\work\catalog")
    c.set_defaults(func=cmd_catalog)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
