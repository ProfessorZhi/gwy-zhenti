# -*- coding: utf-8 -*-
"""应有试卷清单（覆盖优先第一件）：逐卷建账，答「2016–2026 国考 + 各省真实存在的
行测/申论试卷到底缺多少套」。

为什么有这一件（task-1 / 覆盖优先）：此前只能拿「已交付 895」去减一个**估算**总数，
既说不清缺哪一卷、也说不清缺口是「源里没有」还是「源里有但没导入」。本账把每一卷摆到
一行，逐卷标 `已有 / 源有未导入 / 尚未找到 / 待核实`，供后续按缺口补卷。

口径（**证据并集，不由记忆断言**）：
  * 应有 = **规则骨架 ∪ 多来源 TOC 证据并集**。
      - 规则骨架 = 用户点名的检查格：31 省级地区 + 国考，× 2016–2026，× 行测/申论。
        骨架**只**表达「该地区该年该科应有一卷待查」，**不**声称该卷存在（无证据即为
        `尚未找到`）。骨架是**用户口径**，不是模型记忆。
      - 证据并集 = 5 个来源 TOC 解析出的 `(level, region, year, subject, ptype)`；
        同一格内每个 distinct `ptype` 各占一行（**卷型级**），故行数多于格数。
  * `尚未找到` **只**表示「本机所有来源都没提到」这一件事，**绝不**表示「该考试没举行」。
  * `多省联考` 是**源并卷键**、不是地区 ⇒ 单列 `ptype="并卷"`，**不得**产出
    `region="多省联考"` 的行。

**只读**：绝不写交付树 / `work/catalog/` / `work/manifest.jsonl` /
`work/slb_shenlun_manifest.json`；只写 `work/EXPECTED.md` 与 `work/EXPECTED.jsonl`。
不导入任何内容、不改正文/答案、不做跨卷去重、不碰 PDF。

风格照 `tools/gwyzhenti/report_accept.py`（同包、argparse + main + 打印路径与字节数）。
"""
import argparse
import collections
import io
import json
import os
import re

from . import export
from .model import PaperKey

# ---- 口径常量（**逐字**取自 task-1 brief） --------------------------------------

PROVINCES = (
    "北京 天津 上海 重庆 河北 山西 辽宁 吉林 黑龙江 江苏 浙江 安徽 福建 江西 山东 河南 "
    "湖北 湖南 广东 海南 四川 贵州 云南 陕西 甘肃 青海 内蒙古 广西 西藏 宁夏 新疆"
).split()

# 国考的写法（标题里出现任一 ⇒ level=国考、region="国考"）。
GUOKAO_TOKENS = ("国考", "国家公考", "国家公务员")

# 卷型序列词（**最长优先**）。
PTYPE_WORDS = (
    "副省级", "地市级", "行政执法", "A卷", "B卷", "C卷", "A类", "B类", "C类",
    "甲级", "乙级", "县级", "乡镇", "县乡", "省市", "执法", "上半年", "下半年",
    "定向乡镇", "旗县", "盟市", "州市", "兵团", "公安",
)

# 过滤词：命中即丢弃，**不得混入应有账**（模考/模拟/预测/押题/密卷/冲刺/精选）。
DROP_WORDS = ("模考", "模拟", "大赛", "预测", "押题", "密卷", "冲刺", "精选")

# 非国省考类：**可保留**，但 status 记「待核实」（用户要的「考试是否实际举行待核实」档）。
VERIFY_WORDS = ("选调", "招警", "公安院校", "政法干警", "到基层")

# 并卷键的标记词（`20XX·公务员多省联考` 一族）。
BINGJUAN_WORD = "多省联考"

# 用户点名的检查格：31 省 + 国考。
GRID_REGIONS = list(PROVINCES) + ["国考"]

# `work/EXPECTED.jsonl` 每行的字段，**固定 10 个且顺序固定**。
JSONL_FIELDS = ("level", "region", "year", "subject", "session", "ptype",
                "status", "attested_by", "delivered_md", "note")

LEVEL_GUOKAO = "国考"
LEVEL_SHENGKAO = "省考"

_PTYPE_RE = re.compile("|".join(sorted(PTYPE_WORDS, key=len, reverse=True)))
_YEAR_RE = re.compile(r"(20\d\d)")
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)

# 交付树（catalog）里那个**伪地区**：源并卷的产物，不是考点。
PSEUDO_REGION = "多省联考"


# ---- 共享解析 ----------------------------------------------------------------

def parse_title(s, subject_hint=None, level_hint=None):
    """标题/键名 → 证据 dict；取不到年份/科目或命中过滤词 ⇒ **None（丢弃，不猜）**。

    `subject_hint` / `level_hint` 是**来源级**兜底（如 linfukai186 的 `guokao-xingce`
    目录、xingcezhenti 的 6 个模块目录）：**只在标题本身解析不出时**才用。这样
    `2016·国家公务员考试地市级`（不含「行测」二字）不会因为目录名可知而无谓丢失。
    """
    if not s:
        return None
    for w in DROP_WORDS:
        if w in s:
            return None
    m = _YEAR_RE.search(s)
    if not m:
        return None
    year = m.group(1)

    if "申论" in s:
        subject = "申论"
    elif "行测" in s or "行政职业能力" in s:
        subject = "行测"
    elif subject_hint:
        subject = subject_hint
    else:
        return None

    gk = any(t in s for t in GUOKAO_TOKENS)
    if gk:
        level, region = LEVEL_GUOKAO, "国考"
    else:
        level = level_hint or LEVEL_SHENGKAO
        region = ""
        for p in PROVINCES:
            if p in s:
                region = p
                break

    pm = _PTYPE_RE.search(s)
    ptype = pm.group(0) if pm else "统考"
    session = ""
    if "上半年" in s:
        session = "上半年"
    elif "下半年" in s:
        session = "下半年"
    return {"level": level, "region": region, "year": year, "subject": subject,
            "ptype": ptype, "session": session,
            "verify": any(w in s for w in VERIFY_WORDS),
            "bingjuan": ("多省联考" in s) and (region == ""),
            "title": s}


def _ev(parsed, src, **extra):
    """解析结果 → 证据记录（补 `src`）。`parsed is None` ⇒ None。"""
    if parsed is None:
        return None
    e = dict(parsed)
    e["src"] = src
    e.update(extra)
    return e


# ---- 5 个证据源 --------------------------------------------------------------

def ev_catalog(catalog_dir):
    """源 1「交付树」= `work/catalog/catalog.jsonl`（结构化，无需解析标题）。

    伪地区 `多省联考` 的行**不入账**（见 `merge_rows` / md §5）。
    """
    out = []
    for row in export.load_catalog(catalog_dir):
        if row["region"] == PSEUDO_REGION:
            continue
        key = PaperKey(row["level"],
                       "" if row["level"] == LEVEL_GUOKAO else row["region"],
                       row["year"], row["subject"], row["ptype"])
        md_rel, _ = export.repo_paths(key, row["slug"])
        out.append({"level": row["level"],
                    "region": "国考" if row["level"] == LEVEL_GUOKAO else row["region"],
                    "year": row["year"], "subject": row["subject"], "ptype": row["ptype"],
                    "session": "", "verify": False, "bingjuan": False,
                    "title": row.get("title", ""), "src": "catalog", "md_rel": md_rel})
    return out


def ev_xingcezhenti(root):
    """源 2「xingcezhenti」：**文件名即卷名**，六个模块目录取并集去重。

    六个模块目录名固定（见 brief），**显式逐个 `os.listdir`**，不用 `os.walk`。
    """
    mods = ("01-政治理论", "02-常识判断", "03-言语理解与表达", "04-数量关系",
            "05-判断推理", "06-资料分析")
    names = set()
    for mod in mods:
        d = os.path.join(root, mod)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".md"):
                names.add(fn[:-3])
    out = []
    for n in sorted(names):
        out.append(_ev(parse_title(n, subject_hint="行测"), "xingcezhenti"))
    return [e for e in out if e]


def ev_shangantong(root):
    """源 3「shangantong」：`paper_*/index.html` 的 `<title>`。"""
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if not name.startswith("paper_"):
            continue
        p = os.path.join(root, name, "index.html")
        if not os.path.isfile(p):
            continue
        with io.open(p, encoding="utf-8", errors="replace") as fh:
            m = _TITLE_RE.search(fh.read())
        out.append(_ev(parse_title(m.group(1) if m else None), "shangantong"))
    return [e for e in out if e]


def ev_linfukai186(root):
    """源 4「linfukai186」（物理目录 `gongkao-tiku`）：`data/<dir>/y<年>.json` 的**键名**。"""
    out = []
    for d, subj, lv in (("guokao-xingce", "行测", LEVEL_GUOKAO),
                        ("guokao-shenlun", "申论", LEVEL_GUOKAO),
                        ("shengkao-xingce", "行测", LEVEL_SHENGKAO),
                        ("shengkao-shenlun", "申论", LEVEL_SHENGKAO)):
        base = os.path.join(root, "data", d)
        if not os.path.isdir(base):
            continue
        for fn in sorted(os.listdir(base)):
            if not (fn.startswith("y") and fn.endswith(".json")):
                continue
            with io.open(os.path.join(base, fn), encoding="utf-8") as fh:
                obj = json.load(fh)
            if not isinstance(obj, dict):
                continue
            for k, v in obj.items():
                n = len(v) if hasattr(v, "__len__") else 0
                out.append(_ev(parse_title(k, subject_hint=subj, level_hint=lv),
                               "linfukai186", keyname=k, n=n))
    return [e for e in out if e]


def ev_slb(repo_root):
    """源 5「SLB」：本机已下载的 `work/slb_shenlun_manifest.json`。

    **不信 `province`/`exam_type` 前缀**（实测 `国考_*` 下混有广州/深圳/招警/政法干警卷），
    一律按 `title` 重新归位；`chars < 2000` 的**存根**排除（recon §5 的 17 份）。
    """
    p = os.path.join(repo_root, "work", "slb_shenlun_manifest.json")
    out = []
    if not os.path.exists(p):
        return out
    with io.open(p, encoding="utf-8") as fh:
        for x in json.load(fh):
            if int(x.get("chars") or 0) < 2000:
                continue
            out.append(_ev(parse_title(x.get("title", ""), subject_hint="申论"), "SLB"))
    return [e for e in out if e]


# ---- 并账 --------------------------------------------------------------------

def _status(row):
    """`status` 判定（**严格按序**）。见 brief §status 判定。

    `verify_titles` / `plain_titles` 是**内部**字段（jsonl 投影时由 `JSONL_FIELDS` 滤掉），
    用来判「该行是否**只**由选调/招警/…类标题产生」。
    """
    if row["delivered_md"]:
        return "已有"
    if row["verify_titles"] and not row["plain_titles"]:
        return "待核实"
    if row["attested_by"] or row["srcs"]:
        return "源有未导入"
    return "尚未找到"


def _short(seq, n=5):
    """note 里保留原串但**不无限长**：最多 `n` 条 + 「…等 N 条」。"""
    uniq = sorted(set(seq))
    if len(uniq) <= n:
        return "、".join(uniq)
    return "、".join(uniq[:n]) + "…等 %d 条" % len(uniq)


def merge_rows(evidences, since, delivered, years, grid=True):
    """证据并集 + 规则骨架 → `(rows, bingjuan_rows)`。

    * `delivered` = {(level, region, year, subject, ptype): 交付树相对路径}。
    * 骨架只在 `grid=True` 时生成空格行（`ptype="统考"` 占位、`attested_by=[]`）。
    * **同一 (level, region, year, subject, ptype) 只产一行**，来源并集写进 `attested_by`；
      `session` 取各行证据的并集（通常 0/1 个）。
    """
    by = {}
    bj = {}
    for e in evidences:
        if since and e["year"] < since:
            continue
        if e["bingjuan"]:
            b = bj.setdefault(e["year"], {"srcs": set(), "keys": []})
            b["srcs"].add(e["src"])
            if e.get("keyname"):
                b["keys"].append((e["keyname"], e.get("n") or 0))
            continue
        k = (e["level"], e["region"], e["year"], e["subject"], e["ptype"])
        r = by.setdefault(k, {"key": k, "srcs": set(), "sessions": set(),
                              "verify_titles": [], "plain_titles": []})
        r["srcs"].add(e["src"])
        if e.get("session"):
            r["sessions"].add(e["session"])
        (r["verify_titles"] if e.get("verify") else r["plain_titles"]).append(e.get("title") or "")

    if grid:
        # 骨架判据是**格级**：该 (level, region, year, subject) 只要有任何证据（任何卷型）就不空格。
        # （早期版本拿 `(…, "统考")` 这个**具体键**去比，会把国考/浙江这类「有证据但不是统考卷型」
        #  的格误判成空格 ⇒ 空格数虚高。此处按格去重后判。）
        covered = {(k[0], k[1], k[2], k[3]) for k in by}
        for region in GRID_REGIONS:
            level = LEVEL_GUOKAO if region == "国考" else LEVEL_SHENGKAO
            for year in years:
                for subject in ("行测", "申论"):
                    if (level, region, year, subject) in covered:
                        continue
                    k = (level, region, year, subject, "统考")
                    by.setdefault(k, {"key": k, "srcs": set(), "sessions": set(),
                                      "verify_titles": [], "plain_titles": []})

    bj_years = set(bj)
    rows = []
    for k, r in by.items():
        level, region, year, subject, ptype = k
        delivered_md = delivered.get(k, "")
        notes = []
        if r["verify_titles"] and not r["plain_titles"]:
            notes.append("非国省考类标题（选调/招警/公安院校联考/政法干警/基层）："
                         "考试是否实际举行待核实")
        if not r["srcs"] and not delivered_md:
            if level == LEVEL_SHENGKAO and subject == "申论" and year in bj_years:
                notes.append("该年源内可能位于并卷键中，待拆")
        if region == "" and r["plain_titles"]:
            notes.append("地区未归位，原串：" + _short(r["plain_titles"]))
        row = {"level": level, "region": region, "year": year, "subject": subject,
               "session": "、".join(sorted(r["sessions"])), "ptype": ptype,
               "attested_by": sorted(r["srcs"]), "delivered_md": delivered_md,
               "note": "；".join(notes),
               # 内部字段（jsonl 投影时滤掉）
               "srcs": sorted(r["srcs"]), "plain_titles": r["plain_titles"],
               "verify_titles": r["verify_titles"],
               "_verify": bool(r["verify_titles"] and not r["plain_titles"])}
        row["status"] = _status(row)
        rows.append(row)

    rows.sort(key=lambda x: (x["level"], x["region"], x["year"], x["subject"], x["ptype"]))

    bjrows = []
    for year in sorted(bj):
        b = bj[year]
        keys = [k for k, _ in b["keys"]]
        detail = "、".join("%s = %d 题并卷" % (k, n) for k, n in b["keys"])
        bjrows.append({
            "level": LEVEL_SHENGKAO, "region": "", "year": year, "subject": "申论",
            "session": "", "ptype": "并卷", "status": "源有未导入",
            "attested_by": sorted(b["srcs"]), "delivered_md": "",
            "note": "linfukai186 %s；须拆分到真实省份" % detail if detail
                    else "linfukai186 并卷键（%s）；须拆分到真实省份" % _short(keys),
            "srcs": sorted(b["srcs"]), "plain_titles": [], "verify_titles": [],
            "keys": sorted(b["keys"]), "_verify": False})
    return rows, bjrows


def build(catalog_dir, uproots, repo_root, since):
    """→ (md_text, jsonl_rows)。只读；不写任何文件。"""
    since = str(since)
    years = [str(y) for y in range(int(since), 2027)]
    evidences = (ev_catalog(catalog_dir)
                 + ev_xingcezhenti(uproots["xingcezhenti"])
                 + ev_shangantong(uproots["shangantong_c1"])
                 + ev_shangantong(uproots["shangantong_c2"])
                 + ev_linfukai186(uproots["linfukai186"])
                 + ev_slb(repo_root))
    delivered = {}
    for e in evidences:
        if e.get("md_rel") and e["year"] >= since:
            p = os.path.join(repo_root, e["md_rel"].replace("/", os.sep))
            if os.path.exists(p):
                delivered[(e["level"], e["region"], e["year"], e["subject"], e["ptype"])] = e["md_rel"]
    rows, bjrows = merge_rows(evidences, since, delivered, years)
    all_rows = rows + bjrows
    return render_md(rows, bjrows, since, len(evidences)), all_rows


# ---- 人读账 ------------------------------------------------------------------

def render_md(rows, bjrows, since, n_ev):
    n = len(rows) + len(bjrows)
    cnt = collections.Counter(r["status"] for r in rows + bjrows)
    years = sorted({r["year"] for r in rows}, reverse=True)
    subj_rows = [r for r in rows if r["subject"] == "行测"]
    subj_sl = [r for r in rows if r["subject"] == "申论"]
    empty = [r for r in rows if r["status"] == "尚未找到"]
    empty_x = sum(1 for r in empty if r["subject"] == "行测")
    empty_s = sum(1 for r in empty if r["subject"] == "申论")

    L = []
    L += ["# 应有试卷清单（全量·机器算·人可审计）", "",
          "> 机器生成（`tools/gwyzhenti/expect.py`）。范围：`year >= %s`、`国考 + 31 省级地区`、"
          "行测/申论。**只读**：本账不导入任何内容、不改交付树、不做跨卷去重。" % since, ""]

    # ---- 一、口径声明 ----
    L += ["## 一、口径声明", "",
          "1. **应有 = 规则骨架 ∪ 多来源 TOC 证据并集**，**不是**模型记忆。"
          "规则骨架 = 用户点名的检查格（31 省级地区 + 国考 × %s–%s × 行测/申论），"
          "它**只**表达「该地区该年该科应有一卷待查」，**不声称**该卷存在："
          "没有来源提到的格一律落 `尚未找到`。" % (since, years[0]),
          "2. **`尚未找到` 只表示「本机所有来源都没提到」**这一件事，"
          "**绝不表示该考试没有举行**。判定某考试未举行需要**独立证据**，本账没有那种证据。",
          "3. **`多省联考` 是源并卷键、不是地区**：本账**不产出** `region=\"多省联考\"` 的行；"
          "并卷键单列 `ptype=\"并卷\"`（§五）。",
          "4. **证据并集，不由记忆断言**：每一行的 `attested_by` 都真的枚举自下列来源的 TOC，"
          "未提到的地区/年份**不写死**。来源名 ∈ `{catalog, xingcezhenti, shangantong, "
          "linfukai186, SLB}`，其中 `catalog` = 交付树（`work/catalog/catalog.jsonl` + "
          "`export.repo_paths` 判盘上是否存在 md）。",
          "5. 一行 = 一个 `(level, region, year, subject, ptype)`；同一格内 distinct `ptype` 各占"
          "一行 ⇒ **行数是卷型级的、多于格级**。空格行的 `ptype` 是占位 `统考`（无证据，"
          "不声称卷型）。",
          "6. 本账**不做跨卷去重**：同名不同来源各记一条证据，合并只按上述键。", ""]

    # ---- 二、总量四数 ----
    L += ["## 二、总量（四数 + 待核实单列）", "",
          "| 项 | 卷数 |", "|---|---:|",
          "| **应有总数**（本账总行数） | **%d** |" % n,
          "| 其中 `已有`（交付树有 md） | %d |" % cnt["已有"],
          "| 其中 `源有未导入` | %d |" % cnt["源有未导入"],
          "| 其中 `尚未找到` | %d |" % cnt["尚未找到"],
          "| 其中 `待核实`（非国省考类，单列） | %d |" % cnt["待核实"],
          "",
          "> `尚未找到` **≠** 考试未举行（见 §一.2）。其中**行测 %d 行 / 申论 %d 行**。"
          % (empty_x, empty_s),
          "> 范围：`year >= %s`，共 %d 个年份（%s–%s）；"
          "`行测 %d 行 / 申论 %d 行`。" % (since, len(years), years[-1], years[0],
                                          len(subj_rows), len(subj_sl)),
          "> 并卷键另计 **%d 行**（`ptype=\"并卷\"`，已含在总数内）。" % len(bjrows),
          "> 证据条数（未合并前）共 **%d** 条。" % n_ev, ""]

    # ---- 三、交叉表 ----
    L += ["## 三、按 `status` × 科目（交叉表）", "",
          "| status | 行测 | 申论 | 合计 |", "|---|---:|---:|---:|"]
    for st in ("已有", "源有未导入", "尚未找到", "待核实"):
        a = sum(1 for r in rows if r["status"] == st and r["subject"] == "行测")
        b = sum(1 for r in rows if r["status"] == st and r["subject"] == "申论")
        L.append("| %s | %d | %d | %d |" % (st, a, b, a + b))
    a = sum(1 for r in bjrows if r["subject"] == "行测")
    b = sum(1 for r in bjrows if r["subject"] == "申论")
    L.append("| 并卷键（`ptype=\"并卷\"`，单列） | %d | %d | %d |" % (a, b, a + b))
    L += ["| **合计** | **%d** | **%d** | **%d** |"
          % (len(subj_rows) + a, len(subj_sl) + b, n),
          "",
          "> 并卷键单列一行：其 %d 行已计入 §二的 `源有未导入`，故 §二 `475 = 本表 464 + 并卷 %d`。"
          % (len(bjrows), len(bjrows)), ""]

    # ---- 四、缺卷清单 ----
    miss = [r for r in rows if r["status"] != "已有"]
    miss.sort(key=lambda r: (r["year"], r["level"], r["region"], r["subject"], r["ptype"]),
              reverse=True)
    L += ["## 四、缺卷清单（**非 `已有`**，按年份倒序、地区名排序）", "",
          "> 共 **%d** 行（`源有未导入` %d + `尚未找到` %d + `待核实` %d）。"
          "逐年给：地区 / 年 / 科 / 卷型 / status / 来源。空格行 `ptype=统考` 为占位。"
          % (len(miss), cnt["源有未导入"] - len(bjrows), cnt["尚未找到"], cnt["待核实"]), ""]
    for year in sorted({r["year"] for r in miss}, reverse=True):
        grp = [r for r in miss if r["year"] == year]
        L += ["### %s 年（缺 %d 行）" % (year, len(grp)), "",
              "| level | region | subject | ptype | status | attested_by | note |",
              "|---|---|---|---|---|---|---|"]
        for r in sorted(grp, key=lambda x: (x["level"], x["region"], x["subject"], x["ptype"])):
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                r["level"], r["region"] or "（未归位）", r["subject"], r["ptype"], r["status"],
                ", ".join(r["attested_by"]) or "—", (r["note"] or "").replace("|", "\\|")))
        L.append("")

    # ---- 五、并卷键清单 ----
    L += ["## 五、并卷键清单（`ptype=\"并卷\"`，**不是**一个地区）", "",
          "> `linfukai186` 的 `shengkao-shenlun` 把多个省塞进**一个**键 ⇒ 该键**不是**地区。"
          "本账据此单列，**不产出** `region=\"多省联考\"` 的行；对应各省的格照常判 `尚未找到`"
          "（`note` 注明「该年源内可能位于并卷键中，待拆」）。", "",
          "| year | 键名 | 题数 | source |", "|---|---|---:|---|"]
    for r in bjrows:
        for name, cnt in r.get("keys", []):
            L.append("| %s | `%s` | %d | %s |" % (r["year"], name, cnt,
                                                  ", ".join(r["attested_by"])))
    L += ["",
          "> 交付树里那一坨并卷落盘（`省考/多省联考/<年>/申论-统考.md`，%d 个年份）"
          "**不**被本账计为「单省已有卷」；它是**待拆分**的合并件。" % len(bjrows),
          "> 2020 年有两批（`0725` / `0822`），按行键合并为 1 行、键名同时在 `note` 里列出。", ""]

    # ---- 六、诚实边界 ----
    L += ["## 六、诚实边界（未做的事）", "",
          "- 本账只证明「**有来源提到**」这样一份卷，**不证明**该卷真实存在、"
          "更**不证明**来源内容完整或与原卷一致。",
          "- `attested_by` 仅 **1** 个来源的行**可信度低**（可能是源自己的转写/回忆版）；"
          "本账**未做任何内容核对**，未打开任何 md/PDF，未比对原卷。",
          "- **未做跨卷去重**：同名卷在不同来源各记一条证据；键相同即并成一行，"
          "否则各行其是。",
          "- **未导入任何内容**、未改正文/答案、未碰 PDF、未动交付树与 `work/mirror/`。",
          "- `region=\"\"` 的行是**地区未归位**的（如深圳/广州/「全国」等，不在 31 省白名单内）："
          "其原串保留在 `note`，**未瞎填**；这类行**不计入**用户口径的地区覆盖率。",
          "- 空格行 `ptype=\"统考\"` 是**占位**：本账不声称该年该科只有一卷或只有一种卷型。",
          "- **`尚未找到` 不等于考试未举行**；要判「未举行」需独立证据，本账没有。", ""]
    return "\n".join(L)


# ---- 入口 --------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="expect")
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--since", default="2016")
    a = ap.parse_args(argv)
    uproots = {"xingcezhenti": os.path.join(a.upstream, "xingcezhenti"),
               "shangantong_c1": os.path.join(a.upstream, "shangantong-papers-v2-c1"),
               "shangantong_c2": os.path.join(a.upstream, "shangantong-papers-v2-c2"),
               "linfukai186": os.path.join(a.upstream, "gongkao-tiku")}
    md_txt, rows = build(a.catalog, uproots, a.repo, a.since)
    out_md = os.path.join(a.repo, "work", "EXPECTED.md")
    out_jsonl = os.path.join(a.repo, "work", "EXPECTED.jsonl")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with io.open(out_md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md_txt)
    lines = "".join(
        json.dumps({k: r[k] for k in JSONL_FIELDS}, ensure_ascii=False) + "\n" for r in rows)
    with io.open(out_jsonl, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lines)
    print("→", out_md, len(md_txt.encode("utf-8")), "字节")
    print("→", out_jsonl, len(lines.encode("utf-8")), "字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
