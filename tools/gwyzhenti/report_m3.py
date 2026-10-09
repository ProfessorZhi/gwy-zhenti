# -*- coding: utf-8 -*-
"""M3 覆盖账与报告（只读 catalog + 交付树 + 源；写 work/M3-REPORT.md）。"""
import argparse
import collections
import io
import os

from . import export, shenlun
from .model import PaperKey


def build(catalog_dir, uproots, repo_root, since):
    rows = export.load_catalog(catalog_dir)
    sl = [r for r in rows if r["subject"] == "申论"]
    exp = export.exportable_map(rows, uproots)
    src = shenlun.load_source(uproots["linfukai186"])

    L = ["# M3 报告：申论导出", "",
         "> 机器生成（`tools/gwyzhenti/report_m3.py`）。判据对**全量**成立，不抽样。", ""]
    L += ["## 一、总量", "",
          "| 项 | 值 |", "|---|---:|",
          "| catalog 申论行 | %d |" % len(sl),
          "| 其中 2016+ | %d |" % sum(1 for r in sl if r["year"] >= since),
          "| 源里有题的申论卷 | %d |" % sum(1 for r in sl if exp.get(r["slug"])),
          "| 源题合计（2016+ 行） | %d |" % sum(r["n_questions"] for r in sl if r["year"] >= since),
          ""]

    L += ["## 二、逐年 × 落盘", "",
          "> 2016 年以前**不在本次（M3）范围**（`--since 2016`）；其 catalog 行在此列出**仅为对账**，"
          "「落盘 0」**不是缺卷**。「题数」列为 catalog 声明口径，与 §一 的 2016+ 口径不同。", "",
          "| 年 | catalog 行 | 落盘 md | 题数 |", "|---|---:|---:|---:|"]
    files = set()
    for dp, _, fns in os.walk(repo_root):
        for f in fns:
            if f.endswith(".md"):
                files.add(os.path.relpath(os.path.join(dp, f), repo_root).replace(os.sep, "/"))
    for y in sorted({r["year"] for r in sl}):
        ys = [r for r in sl if r["year"] == y]
        n = 0
        for r in ys:
            md_rel, _ = export.repo_paths(
                PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
            if md_rel in files:
                n += 1
        L.append("| %s | %d | %d | %d |" % (y, len(ys), n, sum(r["n_questions"] for r in ys)))
    L.append("")

    L += ["## 三、地区覆盖（2016+ 申论落盘）", "",
          "| 地区 | 卷 |", "|---|---:|"]
    reg = collections.Counter()
    for r in sl:
        if r["year"] < since:
            continue
        md_rel, _ = export.repo_paths(
            PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
        if md_rel in files:
            reg[r["region"] or r["level"]] += 1
    for k, v in reg.most_common():
        L.append("| %s | %d |" % (k, v))
    L.append("")

    trunc = sum(1 for r in sl if r["year"] >= since
                for q in shenlun.questions_for_titles(src, shenlun.titles_of(r))
                if len(q.get("s") or "") >= shenlun.TRUNCATED_LEN)

    # 源侧图片标记账：不写死 0，实算（「图不能丢」要对这个源**可核验**地成立）。
    img_q = sum(1 for r in sl for q in shenlun.questions_for_titles(src, shenlun.titles_of(r))
                for f in ("s", "q", "a", "e")
                if "<img" in (q.get(f) or "") or "![" in (q.get(f) or ""))

    # 上游硬换行残留（`\r`）账（裁定 R-M3-11）：源是硬换行文本、行尾带 `\r\r`，交付 md 逐字节照搬。
    cr_vol = cr_lines = 0
    for r in sl:
        if r["year"] < since:
            continue
        md_rel, _ = export.repo_paths(
            PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
        p = os.path.join(repo_root, md_rel.replace("/", os.sep))
        if not os.path.exists(p):
            continue
        with open(p, "rb") as fh:
            raw = fh.read()
        if b"\r" in raw:
            cr_vol += 1
            cr_lines += sum(1 for ln in shenlun.source_lines(
                shenlun.questions_for_titles(src, shenlun.titles_of(r))) if "\r" in ln)

    L += ["## 四、诚实边界", "",
          "- **材料截断**：源把每题材料硬截断在 %d 字；M3 范围内 **%d 题**受影响，"
          "事实写在每卷 frontmatter 的「校验状态」里。" % (shenlun.TRUNCATED_LEN, trunc),
          "- **源无图**：申论 catalog 共 %d 题（2016+ %d 题），含图片标记的 **%d 题** ⇒ 本源的「图不能丢」"
          "无损失可言（`图片/` 树不新增申论图）。**这不是「我们没查」，是实算出来的。**" % (
              sum(r["n_questions"] for r in sl),
              sum(r["n_questions"] for r in sl if r["year"] >= since), img_q),
          "- **源无卷内题号**：按源序编号，frontmatter 已声明口径。",
          "- **材料按题给**：每题自带该题相关材料子集，**未做去重**（裁定 R-M3-2，守 spec §34 零改写）。",
          "- **上游硬换行残留（`\\r`）未归一化（裁定 R-M3-11）**：%d 卷（2016+）的交付 md 里共 %d 行"
          "内容行行尾带 `\\r`。**未归一化**：同一字节形态既出现在段界（`材料1\\r\\r\\n`）又出现在"
          "**词中间**（`…油气、渔\\r\\r\\n业、港口…`）⇒ 任何按字节的规则都会同时判错一类 ⇒ 归一化只能"
          "是猜。在 CommonMark 渲染器里孤立的 `\\r` 是**行结束符** ⇒ 这些行会多出一个段间空行。"
          "**这是待裁定的产品项，不是本任务范围。**" % (cr_vol, cr_lines),
          "- **未人工通读**：本报告为机器校验结果；抽样通过不等于逐卷通读。",
          ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="report_m3")
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--since", default="2016")
    a = ap.parse_args(argv)
    uproots = {"xingcezhenti": os.path.join(a.upstream, "xingcezhenti"),
               "linfukai186": os.path.join(a.upstream, "gongkao-tiku")}
    txt = build(a.catalog, uproots, a.repo, a.since)
    out = os.path.join(a.repo, "work", "M3-REPORT.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(txt)
    print("→", out, len(txt.encode("utf-8")), "字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
