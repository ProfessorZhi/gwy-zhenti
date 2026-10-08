# -*- coding: utf-8 -*-
"""G1–G6 验收闸门。逐卷实算，不抽样、不口头。

本模块**只读**（`catalog/`、导出树、`work/manifest.jsonl`、上游源），不写任何东西。

设计口径（与简报的差异见 `task-10-report.md`）：
  * 每条闸门都**能红** —— 报告里附了逐闸的变异验证（在副本上把输入改坏 ⇒ 该闸确实变红）。
    一条永远不红的闸门比没有闸门更糟：它给的是**假的安心**。
  * 判据对**全量**成立（`limit` 只用于冒烟，见 `run_all` 里 G6 的口径说明）。
  * 「被引用但源缺失」的图**恰好一类**（见 `KNOWN_SOURCE_GAPS`），它被**点名**而**非**静默放过；
    清单之外的一切缺失 = 缺陷 ⇒ 判负。
"""
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field

from . import export, mdread, render
from .model import PaperKey

IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')
# 简报原稿漏了 `re.M` ⇒ `^` 只在**全文起点**成立 ⇒ `finditer` 恒取不到题号 ⇒ G1 对**每一卷**都报
# 「无题目」而恒红（恒红与恒绿一样废）。此处补 `re.M`（`mdread.QHEAD` 是逐行 `.match`，无需）。
QHEAD = re.compile(r'^#{2,4}\s*第\s*(\d+)\s*题', re.M)
# 卷首引言行 `> 行测 · 3 题 · 四川 2016`（`render.render_paper` 产出）；只在正文之前出现，
# 故用 `search` 取到的**首个**匹配恒为引言行，不会被正文里的引用块误伤。
DECL = re.compile(r'^>\s*[^\n]*?·\s*(\d+)\s*题\s*·', re.M)
FM_KEYS = ("考试", "地区", "年份", "科目", "卷型")
IMG_SEGS = ("题目图", "公式图")

# **已知**上游缺图清单（显式、可审计，不是「凡缺皆放过」）。
#
# 真库实测（2026-10-09，`D:\projects\_gwy-upstream\xingcezhenti`）：全量导出里
# 「被 md 引用、但上游 `90-图片/<图类>/` 下没有源文件」的图**恰好 1 张** ——
# 2018 湖北 421 联考（网友回忆版）行测的公式图。上游自带的《图片缺失清单.txt》有 2 行，
# 另一行 `formula-4daf9a3762c10376.png` 只被已排除的 2016 深圳市考引用，不在 M1 范围内。
#
# 命中本清单的缺图：G2/G4 在说明里**点名文件**并**不判负**；本清单之外的任何缺图一律判负。
# （`export.run` 对缺图记 `skipped` 理由串 `源图片缺失: <name>` 并继续，不崩。）
KNOWN_SOURCE_GAPS = frozenset({"formula-2c7a9ff6774e3af2.png"})


@dataclass
class GatesReport:
    results: list = field(default_factory=list)     # [(名称, bool, 说明)]
    ok: bool = False


def _md_files(repo_root):
    out = []
    for sub in ("国考", "省考"):
        base = os.path.join(repo_root, sub)
        for dp, _, fns in os.walk(base):
            for fn in fns:
                if fn.endswith(".md"):
                    out.append(os.path.join(dp, fn))
    return sorted(out)


def _tag(md_path, repo_root, detail):
    return "%s: %s" % (os.path.relpath(md_path, repo_root).replace(os.sep, "/"), detail)


def _g1(md_path):
    """卷完整：① 题号连续无缺无重；② frontmatter 契约键齐；③ 卷内题数 == 卷首声明的题数。"""
    with io.open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    nums = [int(m.group(1)) for m in QHEAD.finditer(text)]
    if not nums:
        return False, "无题目"
    if nums != list(range(1, len(nums) + 1)):
        return False, "题号不连续: %s" % nums[:20]
    lack = [k for k in FM_KEYS if k not in mdread.read_frontmatter(text)]
    if lack:
        return False, "frontmatter 缺键: %s" % lack
    m = DECL.search(text)
    if m is None:
        return False, "无题数声明行"
    if int(m.group(1)) != len(nums):
        return False, "题数声明 %s != 实得 %d" % (m.group(1), len(nums))
    return True, "%d 题" % len(nums)


def _g2(md_path, img_root, repo_root):
    """图片**导出侧**双向闭合：① md 里每个 `src=` 都真实落盘；② 该卷图片目录里无「落了盘但无人引用」。

    缺失按 `KNOWN_SOURCE_GAPS` 分类：清单内 → 收进第三个返回值（由调用方**点名**、不判负）；
    清单外 → 缺陷。**返回 (ok, 说明, 命中的清单名集合)。**

    **反向必须锚在 `图片/<slug>/` 上，不能只锚在「引用出现过的目录」上** —— 否则一卷若
    引用被删光（`used` 为空 ⇒ 根集合为空），反向会**整支跳过**而假绿。变异实捕获（见报告 ③）。
    `img_root` 由 catalog 行的 slug 权威给出；行找不到时退回「引用反推」，并如实降级。
    """
    with io.open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    base = os.path.dirname(md_path)
    used, missing, known = set(), [], set()
    for src in IMG.findall(text):
        abs_p = os.path.normpath(os.path.join(base, src.replace("/", os.sep)))
        used.add(abs_p)
        if os.path.exists(abs_p):
            continue
        name = os.path.basename(src.replace("\\", "/"))
        if name in KNOWN_SOURCE_GAPS:
            known.add(name)
        else:
            missing.append(name)
    # 反向：该卷图片目录**整棵子树**里，不许有落盘却无人引用的文件
    # （整棵而非仅出现过的图类子目录 ⇒「整类图落了盘但引用全丢」也看不见不了）。
    roots = set()
    if img_root:
        roots.add(os.path.normpath(os.path.join(repo_root, img_root)))
    roots |= {os.path.dirname(os.path.dirname(p)) for p in used}
    orphan = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dp, _, fns in os.walk(root):
            for fn in fns:
                p = os.path.normpath(os.path.join(dp, fn))
                if p not in used:
                    orphan.append(os.path.relpath(p, root).replace(os.sep, "/"))
    if missing:
        return False, "引用但未落盘: %s" % sorted(set(missing))[:5], known
    if orphan:
        return False, "落盘但未被引用: %s" % sorted(set(orphan))[:5], known
    return True, "双向闭合 %d 张" % len(used), known


def _g3(md_path):
    """答案不泄露：正文无 ✅；每卷有独立答案板块且答案已折叠。"""
    with io.open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    if "✅" in text:
        return False, "残留 ✅"
    if "## 答案与解析" not in text:
        return False, "无独立答案板块"
    if "<details>" not in text or "</details>" not in text:
        return False, "答案未折叠"
    return True, "无泄露"


def _g4_manifest(repo_root):
    """幂等代理：`work/manifest.jsonl` 里每个文件的 sha256 必须与磁盘一致（重跑不变 ⇒ 一致）。

    缺 manifest ⇒ **判负**（不能因为「没账本」就静默通过）。
    """
    man = os.path.join(repo_root, "work", "manifest.jsonl")
    if not os.path.exists(man):
        return False, "缺 work/manifest.jsonl"
    ok, detail = True, []
    with io.open(man, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            e = json.loads(line)
            p = os.path.join(repo_root, e["path"].replace("/", os.sep))
            if not os.path.exists(p):
                ok = False
                detail.append("缺 %s" % e["path"])
                continue
            with open(p, "rb") as fh2:
                actual = hashlib.sha256(fh2.read()).hexdigest()
            if actual != e["sha256"]:
                ok = False
                detail.append("sha 不符 %s" % e["path"])
    if not ok:
        return False, "；".join(detail[:3])
    return True, "一致"


def _g4_source(md_path, upstream_xingce):
    """**上游侧**缺图账：md 里每个 `src=` 对应的源图必须在上游 `90-图片/<图类>/` 里真实存在。

    这是 G2 的**另一面**：G2 只问「导出树里有没有」，此处问「上游到底有没有」。
    清单内缺口被点名、不判负；清单外一律判负。**返回 (ok, 说明, 命中的清单名集合)。**
    """
    with io.open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    srcs = IMG.findall(text)
    gaps, known = [], set()
    for src in srcs:
        parts = src.replace("\\", "/").split("/")
        if len(parts) < 2 or parts[-2] not in IMG_SEGS:
            gaps.append("图类不可判定: %s" % src)
            continue
        seg, name = parts[-2], parts[-1]
        if os.path.exists(os.path.join(upstream_xingce, "90-图片", seg, name)):
            continue
        if name in KNOWN_SOURCE_GAPS:
            known.add(name)
        else:
            gaps.append(name)
    if gaps:
        return False, "上游无源: %s" % sorted(set(gaps))[:5], known
    return True, "上游源齐（引用 %d 张）" % len(srcs), known


def _g5(md_path, row, upstream_xingce, repo_root):
    """保真：导出正文 vs 源，逐行**多重集**比较（`render.diff_report`），要求零内容增删。

    `row` 由 `run_all` 一次性建好的 **md_rel → catalog 行**索引给出（简报原稿在**每卷**里
    重扫一遍整份 catalog ⇒ O(卷²)；真库 429 卷 × 1263 行 ≈ 54 万次重复解析，纯浪费，不改语义）。
    """
    if row is None:
        return False, "catalog 里找不到该卷: %s" % os.path.relpath(md_path, repo_root).replace(os.sep, "/")
    parts, _ = export._parts_for(row, upstream_xingce)
    if not parts:
        return False, "源文件缺失"
    with io.open(md_path, encoding="utf-8") as fh:
        out_text = fh.read()
    removed, added = render.diff_report(out_text, parts)
    if removed or added:
        return False, "源有导出无 %d 行 / 导出有源无 %d 行；例：%s" % (
            len(removed), len(added), (removed or added)[:2])
    return True, "零内容增删"


def _g6(catalog_dir, upstream_xingce, repo_root, mds, limit, failed):
    """覆盖账（**catalog → 落盘**的反向对账）。判据对全量成立：

      * catalog 里**取得到正文**的每一卷，都必须在导出树里落盘（抓**整卷静默丢失** —— 本任务最贵的事故）；
      * 不设 `limit` 时，落盘 md 数必须**恰好等于**可导出卷数（抓多出来的 / 少掉的卷）。

    方向与 G5 相反：G5 从 md 出发找 catalog 行，看不见「catalog 声称有、树里没有」的整卷。
    `limit` 生效时**不做**「数相等」那一条 —— 因为 `export.run` 按 **catalog 行序**切片、
    而 `mds` 按**路径排序**切片，两者不是同一子集，硬比会假红。
    「已入库」只指**通过 G1–G5** 的卷（spec §7 G6），故在此如实报出。
    """
    rows = export.load_catalog(catalog_dir)
    scope = rows[:limit] if limit else rows
    exportable, absent = 0, []
    for r in scope:
        parts, _ = export._parts_for(r, upstream_xingce)
        if not parts:
            continue
        exportable += 1
        md_rel, _ = export.repo_paths(
            PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
        if not os.path.exists(os.path.join(repo_root, md_rel.replace("/", os.sep))):
            absent.append(md_rel)
    ok = not absent
    note = ""
    if not limit and len(mds) != exportable:
        ok = False
        note = "；落盘 md 数 %d != 可导出卷数 %d" % (len(mds), exportable)
    if limit:
        note += "；limit 生效，未做「数相等」对账"
    return ok, "catalog %d 卷（本次对账 %d）| 可导出 %d | 落盘 md %d | 通过 G1–G5 的卷 %d%s%s" % (
        len(rows), len(scope), exportable, len(mds), len(mds) - len(failed), note,
        "；未落盘: %s" % absent[:3] if absent else "")


def _index(catalog_dir):
    """md 相对路径（os.sep 形态）→ catalog 行。G2 用它拿权威的 `图片/<slug>`，G5 用它拿源。"""
    out = {}
    for r in export.load_catalog(catalog_dir):
        md_rel, _ = export.repo_paths(
            PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
        out[md_rel.replace("/", os.sep)] = r
    return out


def _img_root(row):
    if row is None:
        return None
    return export.repo_paths(
        PaperKey(row["level"], row["region"], row["year"], row["subject"], row["ptype"]),
        row["slug"])[1].replace("/", os.sep)


def run_all(catalog_dir, uproots, repo_root, limit=None):
    rep = GatesReport()
    mds = _md_files(repo_root)
    if limit:
        mds = mds[:limit]
    xingce = uproots["xingcezhenti"]
    index = _index(catalog_dir)
    failed = set()          # 未通过 G1–G5 的 md（G6 用它报「已入库」）

    # ---- G1 卷完整 ----
    ok, detail = True, []
    for md in mds:
        good, d = _g1(md)
        if not good:
            ok = False
            failed.add(md)
            detail.append(_tag(md, repo_root, d))
    rep.results.append(("G1 卷完整（题号连续·题数一致·frontmatter 契约）", ok,
                        " | ".join(detail[:3]) if detail else "全部通过 %d 卷" % len(mds)))

    # ---- G2 图片双向闭合（导出侧） ----
    ok, detail, known = True, [], set()
    for md in mds:
        row = index.get(os.path.relpath(md, repo_root))
        good, d, k = _g2(md, _img_root(row), repo_root)
        known |= k
        if not good:
            ok = False
            failed.add(md)
            detail.append(_tag(md, repo_root, d))
    if known:
        detail.append("已知上游缺图 %d 张（清单内，非缺陷）：%s" % (len(known), sorted(known)))
    rep.results.append(("G2 图片双向闭合（引用↔落盘）", ok,
                        " | ".join(detail[:4]) if detail else "全部通过 %d 卷" % len(mds)))

    # ---- G3 答案不泄露 ----
    ok, detail = True, []
    for md in mds:
        good, d = _g3(md)
        if not good:
            ok = False
            failed.add(md)
            detail.append(_tag(md, repo_root, d))
    rep.results.append(("G3 答案不泄露（无 ✅ · 独立答案板块 · 已折叠）", ok,
                        " | ".join(detail[:3]) if detail else "全部通过 %d 卷" % len(mds)))

    # ---- G4 幂等（manifest↔文件 sha）+ 上游侧缺图账 ----
    man_ok, man_detail = _g4_manifest(repo_root)
    src_ok, src_detail, known2 = True, [], set()
    for md in mds:
        good, d, k = _g4_source(md, xingce)
        known2 |= k
        if not good:
            src_ok = False
            failed.add(md)
            src_detail.append(_tag(md, repo_root, d))
    if known2:
        src_detail.append("已知上游缺图 %d 张（清单内，非缺陷）：%s" % (len(known2), sorted(known2)))
    rep.results.append((
        "G4 幂等（manifest↔文件 sha）与上游缺图账", man_ok and src_ok,
        "manifest: %s ｜ 上游源: %s" % (
            man_detail, " | ".join(src_detail[:3]) if src_detail else "全部齐全 %d 卷" % len(mds))))

    # ---- G5 保真（源↔导出逐行多重集） ----
    ok, detail = True, []
    for md in mds:
        good, d = _g5(md, index.get(os.path.relpath(md, repo_root)), xingce, repo_root)
        if not good:
            ok = False
            failed.add(md)
            detail.append(_tag(md, repo_root, d))
    rep.results.append(("G5 保真（源↔导出逐行多重集）", ok,
                        " | ".join(detail[:3]) if detail else "全部通过 %d 卷" % len(mds)))

    # ---- G6 覆盖账（catalog 实算） ----
    ok6, detail6 = _g6(catalog_dir, xingce, repo_root, mds, limit, failed)
    rep.results.append(("G6 覆盖账（catalog→落盘反向对账）", ok6, detail6))

    rep.ok = all(x for _, x, _ in rep.results)
    return rep
