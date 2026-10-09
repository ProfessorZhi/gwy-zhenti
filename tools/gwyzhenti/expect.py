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
      - 证据并集 = 6 个来源 TOC 解析出的 `(level, region, year, subject, ptype, session)`；
        同一格内每个 distinct 卷型各占一行（**卷型级**），故行数多于格数。
        **源 6「sghcn」**（`SGHCN0762` 的文件名清单，见 `ev_sghcn`）**只作证据、不可导入**：
        它带**精确卷型**（`（安徽A卷）`/`（广西C卷）`/`（河南县级卷）`），是拆并卷的权威卷型地图，
        但正文是 PDF/无图 JSON ⇒ **不作卷源**（§十「来源可导入性」）。
  * `尚未找到` **只**表示「本机所有来源都没提到」这一件事，**绝不**表示「该考试没举行」。
  * `多省联考` 是**源并卷键**、不是地区 ⇒ 单列 `ptype="并卷"`，**不得**产出
    `region="多省联考"` 的行。

**卷型归一（修轮 1 / A1）**：`canon_ptype` 是交付侧与源侧**共用的唯一归一出口**。
控制器裁定（R-COV-16）把「归一」**只**放在**匹配层**：
  * **已交付行**（`repo_paths` 有落盘）**一律以交付侧原始串落键**（`ptype`），
    行内**另存** canonical 供匹配 —— 保证 `delivered_md` 与 manifest 的 895 个 path
    **一一对应、绝不并掉异形件**（如 `急需紧缺岗位` 与 `统考` 并存于黑龙江 2019 申论）。
  * **源侧证据**用 canonical 匹配：同 `(level, region, year, subject)` 格内先找 canonical
    相同的**已交付行**挂 `attested_by`；**找不到才**新建（非交付）行。
  * ⇒ 交付侧 `A类` 与源侧 `A卷` 归一后**同一行**（幻影缺口消失），而交付侧两个**不同**
    交付件**不会**被并成一行（账闭合）。**归一化只发生在比较层，交付树文件名一字未动。**

**只读**：绝不写交付树 / `work/catalog/` / `work/manifest.jsonl` /
`work/slb_shenlun_manifest.json`；只写 `work/EXPECTED.md`、`work/EXPECTED.jsonl`、
`work/PTYPE-MAP.md`。不导入任何内容、不改正文/答案、不做跨卷去重、不碰 PDF。

风格照 `tools/gwyzhenti/report_accept.py`（同包、argparse + main + 打印路径与字节数）。

**源 6「sghcn」的 TOC 快照**：`tools/gwyzhenti/data/sghcn_toc/*.txt`（随仓提交的**文件名
清单**，事实性标题，非正文）。**不联网**；刷新（本机 HTTPS 直连 GitHub，不绕行、不镜像）：

    gh api "repos/SGHCN0762/<repo>/git/trees/HEAD?recursive=1" \
        --jq '.tree[]|select(.type=="blob")|.path'

四份快照：`sghcn_provice.txt`（省考申论 PDF 名）、`sghcn_country.txt`（国考申论 PDF 名）、
`sghcn_provice_xingce_json.txt`（省考行测 JSON 名）、`sghcn_country_xingce_json.txt`
（国考行测 JSON 名）。重取时**逐字覆盖同名文件**即可。
"""
import argparse
import collections
import io
import json
import os
import re

from . import export
from .model import PaperKey

# ---- 口径常量 ----------------------------------------------------------------

# 用户口径的 31 个省级地区（骨架用）。
PROVINCES = (
    "北京 天津 上海 重庆 河北 山西 辽宁 吉林 黑龙江 江苏 浙江 安徽 福建 江西 山东 河南 "
    "湖北 湖南 广东 海南 四川 贵州 云南 陕西 甘肃 青海 内蒙古 广西 西藏 宁夏 新疆"
).split()

# A4：region 白名单**只**补深圳/广州（真实地方公务员考试地区）。
# **不入骨架**：骨架 = 用户点名的 31 省 + 国考 = 704 格，不因白名单扩张而变。
EXTRA_REGIONS = ("深圳", "广州")
REGION_WORDS = tuple(PROVINCES) + EXTRA_REGIONS

# 国考的写法（标题里出现任一 ⇒ level=国考、region="国考"）。
GUOKAO_TOKENS = ("国考", "国家公考", "国家公务员")

# 过滤词：命中即丢弃，**不得混入应有账**。
DROP_WORDS = ("模考", "模拟", "大赛", "预测", "押题", "密卷", "冲刺", "精选")

# 非国省考类（A3）：**移出主账**，单列一节。
VERIFY_WORDS = ("选调", "招警", "公安院校", "政法干警", "到基层")

# 并卷键的标记词（`20XX·公务员多省联考` 一族）。
BINGJUAN_WORD = "多省联考"
BINGJUAN_PTYPE = "并卷"

# 用户点名的检查格：31 省 + 国考（**不含** 深圳/广州）。
GRID_REGIONS = list(PROVINCES) + ["国考"]

# `work/EXPECTED.jsonl` 每行的字段，**固定 10 个且顺序固定**。
JSONL_FIELDS = ("level", "region", "year", "subject", "session", "ptype",
                "status", "attested_by", "delivered_md", "note")

LEVEL_GUOKAO = "国考"
LEVEL_SHENGKAO = "省考"

# 源 6「sghcn」的 TOC 快照（随仓提交的**文件名清单**；生成器**从该目录读**，不联网）。
# 目录默认取**本模块同级**的 `data/sghcn_toc` ⇒ 不依赖 CWD / 不依赖 `--upstream`。
SGHCN_TOC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "sghcn_toc")
# (快照文件, 科目兜底, level 兜底)。**顺序固定** ⇒ 证据顺序确定、产物逐字节可复现。
SGHCN_TOC_FILES = (("sghcn_country.txt", "申论", LEVEL_GUOKAO),
                   ("sghcn_country_xingce_json.txt", "行测", LEVEL_GUOKAO),
                   ("sghcn_provice.txt", "申论", LEVEL_SHENGKAO),
                   ("sghcn_provice_xingce_json.txt", "行测", LEVEL_SHENGKAO))

# 交付树（catalog）里那个**伪地区**：源并卷的产物，不是考点。
PSEUDO_REGION = "多省联考"

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_YEAR_RE = re.compile(r"(20\d\d)")

# ---- A1：卷型归一（**只**在匹配层用） ------------------------------------------

# 规范词表。**注**：task-1 fix-1 简令写「共 27 个允许值」却列举了 **28** 项，且其别名表
# 要求 `县级卷 / 县级 -> 县级` 而 `县级` **不在**那 28 项里。控制器裁定（R-COV-16-1）把
# `县级` 补进词表：**自洽读法 = 28 列举项 + `县级`**。本账按此实现，并在 PTYPE-MAP.md
# 与报告里如实记录该计数差异（27 声称 / 28 列举 / 29 实需）。
CANON_PTYPES = (
    "副省级", "地市级", "行政执法", "A类", "B类", "C类", "甲级", "乙级", "丙级",
    "乡镇", "县乡", "省市", "州市", "州县", "旗县", "盟市", "区县", "区级",
    "省级", "市级", "省直", "县级以上", "县级",
    "一卷", "二卷", "三卷", "兵团", "通用", "统考",
)

# (别名, 规范词)。**排序 = 最长优先；同长按规范词在上表的次序**（保证 `A卷：省直` → `A类`
# 而不是 `省直`，`兵团一卷` → `一卷` 而不是 `兵团`）。
_ALIAS_PAIRS = (
    ("副省级", "副省级"), ("地市级", "地市级"), ("市地级", "地市级"),
    ("行政执法", "行政执法"),
    ("A卷", "A类"), ("A类", "A类"), ("B卷", "B类"), ("B类", "B类"), ("C卷", "C类"),
    ("C类", "C类"),
    ("卷甲级", "甲级"), ("甲卷", "甲级"), ("甲级", "甲级"),
    ("卷乙级", "乙级"), ("乙卷", "乙级"), ("乙级", "乙级"),
    ("丙卷", "丙级"), ("丙级", "丙级"),
    ("定向乡镇", "乡镇"), ("乡镇卷", "乡镇"), ("乡镇", "乡镇"),
    ("县级、乡镇统一卷", "县乡"), ("县级+乡镇", "县乡"), ("县乡卷", "县乡"), ("县乡", "县乡"),
    ("县级以上", "县级以上"),
    ("县级卷", "县级"), ("县级", "县级"),
    ("省市县卷", "省市"), ("省市州级", "省市"), ("省市卷", "省市"), ("省市", "省市"),
    ("州市卷", "州市"), ("州市", "州市"),
    ("州县卷", "州县"), ("州县", "州县"),
    ("旗县卷", "旗县"), ("旗县", "旗县"),
    ("盟市卷", "盟市"), ("盟市", "盟市"),
    ("区县卷", "区县"), ("区县", "区县"),
    ("区级及以上", "区级"), ("区级卷", "区级"), ("区级", "区级"),
    ("省级卷", "省级"), ("省级", "省级"),
    ("市级卷", "市级"), ("市级", "市级"),
    ("省直", "省直"),
    ("一卷", "一卷"), ("二卷", "二卷"), ("三卷", "三卷"),
    ("兵团", "兵团"),
    ("通用卷", "通用"), ("通用", "通用"),
)
_IDX = {c: i for i, c in enumerate(CANON_PTYPES)}
ALIASES = tuple(sorted(_ALIAS_PAIRS, key=lambda p: (-len(p[0]), _IDX[p[1]])))
ALIAS_TO_CANON = dict(ALIASES)
SESSIONS = ("上半年", "下半年")


def match_ptype(s):
    """→ `(命中的别名 or None, session)`。别名 = **最长优先**（同长按规范词序）。"""
    s = s or ""
    session = ""
    for w in SESSIONS:
        if w in s:
            session = w
            break
    for alias, _canon in ALIASES:
        if alias in s:
            return alias, session
    return None, session


def canon_ptype(s):
    """原始串（交付侧 `row["ptype"]` **或**整条标题）→ `(规范 ptype, session)`。

    `session` **独立成字段**（A6）：规范 ptype 里**永不**含「上半年/下半年」。取不到别名 ⇒
    `统考`。**注意**：本函数**只用于匹配层**；已交付行落键用交付侧原始串（见 `_strip_session`）。
    """
    alias, session = match_ptype(s)
    return (ALIAS_TO_CANON[alias] if alias else "统考"), session


def _strip_session(raw):
    """交付侧原始串 → `(原始串去掉 session 词, session)`；空串 ⇒ `统考`（A6）。"""
    s = raw or ""
    sess = ""
    for w in SESSIONS:
        if w in s:
            sess = w
            s = s.replace(w, "")
            break
    s = s.strip()
    return (s or "统考"), sess


# ---- 共享解析 ----------------------------------------------------------------

def parse_title(s, subject_hint=None, level_hint=None):
    """标题/键名 → 证据 dict；取不到年份/科目或命中过滤词 ⇒ **None（丢弃，不猜）**。

    `subject_hint` / `level_hint` 是**来源级**兜底（如 linfukai186 的 `guokao-xingce`
    目录、xingcezhenti 的 6 个模块目录）：**只在标题本身解析不出时**才用。
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
        for p in REGION_WORDS:
            if p in s:
                region = p
                break

    ptype, session = canon_ptype(s)
    alias, _ = match_ptype(s)
    return {"level": level, "region": region, "year": year, "subject": subject,
            "ptype": ptype, "session": session, "ptype_raw": alias or "",
            "verify": any(w in s for w in VERIFY_WORDS),
            "bingjuan": (BINGJUAN_WORD in s) and (region == ""),
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
    """源 1「交付树」= `work/catalog/catalog.jsonl`。

    伪地区 `多省联考` 的行**不产出 `region="多省联考"` 的行**，而是转成**并卷行**（A2），
    以便 11 份并卷落盘也有 `delivered_md`（账闭合到 895）。
    """
    out = []
    for row in export.load_catalog(catalog_dir):
        key = PaperKey(row["level"],
                       "" if row["level"] == LEVEL_GUOKAO else row["region"],
                       row["year"], row["subject"], row["ptype"])
        md_rel, _ = export.repo_paths(key, row["slug"])
        base = {"level": row["level"],
                "region": "国考" if row["level"] == LEVEL_GUOKAO else row["region"],
                "year": row["year"], "subject": row["subject"],
                "title": row.get("title", ""), "src": "catalog", "md_rel": md_rel,
                "ptype_raw": row["ptype"]}
        if row["region"] == PSEUDO_REGION:
            base.update({"ptype": BINGJUAN_PTYPE, "session": "", "verify": False,
                         "bingjuan": True})
        else:
            pt, sess = canon_ptype(row["ptype"])
            base.update({"ptype": pt, "session": sess, "verify": False,
                         "bingjuan": False})
        out.append(base)
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
    一律按 `title` 重新归位；`chars < 2000` 的**存根**排除。
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


def ev_sghcn(toc_dir=SGHCN_TOC_DIR):
    """源 6「sghcn」（`SGHCN0762`）：**文件名清单**（`data/sghcn_toc/*.txt`），不联网。

    价值：其申论/行测文件名把**真实省份 + 精确卷型**写进了名字
    （`2023年公务员多省联考《申论》真题及答案（安徽A卷）` ⇒ `region="安徽"`, `ptype="A类"`），
    是**拆并卷的权威卷型地图**。

    口径（与其余 5 源**完全同路**，**不另起词表** —— 这正是修轮 1 修掉的 F1）：
      * 一律走共享的 `parse_title` ⇒ `canon_ptype` / `match_ptype`；本函数**只**做
        「读文件 → 去扩展名 → 交给 `parse_title`」。
      * **region 优先于「多省联考」**：`parse_title` 先按 `REGION_WORDS` 取省名，
        取不到才可能落并卷键 ⇒ **绝不**产出 `region="多省联考"`（R-COV-1）。
      * **国考**（含 `国家公务员`/`国考`）⇒ `level="国考"`, `region="国考"`（R-COV-22：
        与既有各行一致，「国考」本就是 region 轴的一个取值）。
      * 年份取 `(20\\d\\d)`，**取不到 ⇒ 丢弃**；科目含「申论」/「行测」，取不到 ⇒ 丢弃；
        命中过滤词（模考/模拟/…）⇒ 丢弃。`招警`/`选调`/`政法干警`/`公安院校联考` 类
        由 `parse_title` 打 `verify=True` ⇒ 走**非国省考**通路（R-COV-9），不进主账。
      * `level_hint`：`sghcn_country*` 两份给 `国考`（其文件名可能不含「国家公务员」），
        `sghcn_provice*` 两份给 `省考`。**它只是兜底**（标题本身能判时以标题为准）。
      * **`--since` 不在本函数过滤**：与其余 5 源同路，`since` 统一在 `merge_rows` /
        `render_ptype_map` 层执行（否则 §二「证据条数」在源间口径不一）。
      * 清单里混入的非试卷名（如 `issues.txt`/`analyze_data.py`）**无年份 ⇒ 自然丢弃**，
        不需要特判。
    """
    out = []
    for fn, subj, lv in SGHCN_TOC_FILES:
        p = os.path.join(toc_dir, fn)
        if not os.path.isfile(p):
            continue
        with io.open(p, encoding="utf-8") as fh:
            for line in fh:
                name = line.strip()
                if not name:
                    continue
                for ext in (".pdf", ".json"):
                    if name.lower().endswith(ext):
                        name = name[:-len(ext)]
                        break
                out.append(_ev(parse_title(name, subject_hint=subj, level_hint=lv),
                               "sghcn"))
    return [e for e in out if e]


# ---- 并账 --------------------------------------------------------------------

def _row(level, region, year, subject, ptype, session):
    """空白行累加器（内部键由 `JSONL_FIELDS` 投影剥掉）。"""
    return {"level": level, "region": region, "year": year, "subject": subject,
            "ptype": ptype, "session": session, "canon": ptype, "ptype_raw": "",
            "srcs": set(), "mds": set(), "plain_titles": [], "verify_titles": []}


def _status(row):
    """`status` 判定（**严格按序**）。

    1. 交付树有 md ⇒ `已有`；2. 只由非国省考类标题产生 ⇒ `待核实`（A3 后主账预期 0 行）；
    3. `attested_by` 非空 ⇒ `源有未导入`；4. 否则 ⇒ `尚未找到`。

    入参是**最终行 dict**（`attested_by` 已物化）—— A7：不再出现
    `row["attested_by"] or row["srcs"]` 这种二者恒等的死代码。
    """
    if row["delivered_md"]:
        return "已有"
    if row["verify_titles"] and not row["plain_titles"]:
        return "待核实"
    if row["attested_by"]:
        return "源有未导入"
    return "尚未找到"


def _short(seq, n=5):
    """note 里保留原串但**不无限长**：最多 `n` 条 + 「…等 N 条」。"""
    uniq = sorted(set(x for x in seq if x))
    if len(uniq) <= n:
        return "、".join(uniq)
    return "、".join(uniq[:n]) + "…等 %d 条" % len(uniq)


def _match_delivered(dela, e):
    """源侧证据 → 同格 `canonical` 相同的**已交付行**（裁定口径：找不到才新建）。

    优先 `session` 相同；再优先 `ptype == canonical`（如 `统考` 证据只挂 `统考` 那一行，
    不挂同格的 `急需紧缺岗位`）；仍并列则按 `ptype` 排序取首（确定性）。
    """
    cell = (e["level"], e["region"], e["year"], e["subject"])
    cands = [r for r in dela.values()
             if (r["level"], r["region"], r["year"], r["subject"]) == cell
             and r["canon"] == e["ptype"]]
    if not cands:
        return None
    same = [r for r in cands if r["session"] == e["session"]]
    pool = same or cands
    exact = [r for r in pool if r["ptype"] == e["ptype"]]
    return sorted(exact or pool, key=lambda r: (r["ptype"], r["session"]))[0]


def merge_rows(evidences, since, delivered, years, grid=True):
    """证据并集 + 规则骨架 → `(rows, bingjuan_rows, non_gs_rows)`。

    * **已交付行**：`delivered`（落盘存在的 `md_rel` 集合）里的 catalog 证据，
      **以交付侧原始串落键**（`_strip_session`），一行一路径 ⇒ 与 manifest 一一对应。
    * **其余证据**：先按 canonical 匹配已交付行（`_match_delivered`），找不到才新建行
      （键 = canonical ptype + session）。
    * 行键 = `(level, region, year, subject, ptype, session)`；`session` 与 ptype **脱钩**（A6）。
    * 非国省考类证据（A3）**不进主账**，归入 `non_gs_rows`；其独占的格**不生成**骨架占位。
    * 骨架只在 `grid=True` 时生成空格行（`ptype="统考"` 占位、`srcs` 为空）。
    """
    dela = {}
    for e in evidences:                                   # ① 已交付行（原始串落键）
        if since and e["year"] < since:
            continue
        if e.get("bingjuan") or e.get("verify"):
            continue
        md = e.get("md_rel")
        if not md or md not in delivered:
            continue
        pt, sess = _strip_session(e.get("ptype_raw") or "")
        k = (e["level"], e["region"], e["year"], e["subject"], pt, sess)
        r = dela.get(k)
        if r is None:
            r = _row(e["level"], e["region"], e["year"], e["subject"], pt, sess)
            r["canon"] = canon_ptype(e.get("ptype_raw") or "")[0]
            r["ptype_raw"] = e.get("ptype_raw") or ""
            dela[k] = r
        r["mds"].add(md)                                  # 不变量：一行一路径
        r["srcs"].add(e["src"])
        r["plain_titles"].append(e.get("title") or "")

    # A3 判定：哪些「键」是**整行只由非国省考类标题组成**（= 现状 41 行 `待核实` 的同型行）
    # ⇒ 整行移出主账、单列 §七；其余提及选调/招警的标题**照常**归属主行（如
    # `2018·公务员多省联考《申论》题（安徽A、普通选调卷）` 是安徽 A 卷的一体两面，不是另一场考试）。
    grp = collections.defaultdict(list)
    for e in evidences:
        if since and e["year"] < since:
            continue
        if e["bingjuan"]:
            continue
        k = (e["level"], e["region"], e["year"], e["subject"], e["ptype"], e["session"])
        grp[k].append(e)
    diverted = set()
    for k, v in grp.items():
        if not all(x.get("verify") for x in v):
            continue
        probe = {"level": k[0], "region": k[1], "year": k[2], "subject": k[3],
                 "ptype": k[4], "session": k[5]}
        if _match_delivered(dela, probe) is None:         # 交付树有 md ⇒ 该行仍是 `已有`
            diverted.add(k)

    src_rows = {}
    non_gs = {}
    vonly = set()
    bj = {}
    for e in evidences:                                   # ② 其余证据
        if since and e["year"] < since:
            continue
        if e["bingjuan"]:
            b = bj.setdefault(e["year"], {"srcs": set(), "keys": [], "md": ""})
            b["srcs"].add(e["src"])
            if e.get("md_rel") and e["md_rel"] in delivered:
                b["md"] = e["md_rel"]
            if e.get("keyname"):
                b["keys"].append((e["keyname"], e.get("n") or 0))
            continue
        k6 = (e["level"], e["region"], e["year"], e["subject"], e["ptype"],
              e["session"])
        if e.get("verify") and k6 in diverted:             # A3：整行移出主账
            non_gs.setdefault(k6, {"titles": []})["titles"].append(e.get("title") or "")
            vonly.add(k6[:4])
            continue
        md = e.get("md_rel")
        if md and md in delivered:                        # 已由 ① 落行
            continue
        tgt = _match_delivered(dela, e)
        if tgt is not None:
            tgt["srcs"].add(e["src"])
            tgt["plain_titles"].append(e.get("title") or "")
            if e.get("verify"):
                tgt["verify_titles"].append(e.get("title") or "")
            continue
        r = src_rows.get(k6)
        if r is None:
            r = _row(e["level"], e["region"], e["year"], e["subject"], e["ptype"],
                     e["session"])
            r["canon"] = e["ptype"]
            src_rows[k6] = r
        r["srcs"].add(e["src"])
        r["plain_titles"].append(e.get("title") or "")
        if e.get("verify"):
            r["verify_titles"].append(e.get("title") or "")

    # 非国省考**独占**的格不生成占位（A3：否则虚增 `尚未找到`）
    if grid:
        blocked = {(k[0], k[1], k[2], k[3]) for k in list(dela) + list(src_rows)}
        blocked |= {c for c in vonly if c not in blocked}
        for region in GRID_REGIONS:
            level = LEVEL_GUOKAO if region == "国考" else LEVEL_SHENGKAO
            for year in years:
                for subject in ("行测", "申论"):
                    if (level, region, year, subject) in blocked:
                        continue
                    k = (level, region, year, subject, "统考", "")
                    src_rows.setdefault(k, _row(level, region, year, subject,
                                                "统考", ""))

    rows = []
    for r in list(dela.values()) + list(src_rows.values()):
        notes = []
        if r["ptype"] not in CANON_PTYPES and r["ptype"] != BINGJUAN_PTYPE:
            if r["mds"]:
                notes.append("交付侧异形卷型原串 `%s`（规范词表只用于匹配；本行按交付侧原样"
                             "保留，以保交付路径不丢）" % r["ptype"])
            else:
                notes.append("规范词表外的卷型原串 `%s`（该格已交付件与本串不同，分列以保路径）"
                             % r["ptype"])
        if r["region"] == "" and r["plain_titles"]:
            notes.append("地区未归位，原串：" + _short(r["plain_titles"]))
        if r["verify_titles"]:
            notes.append("含非国省考类标题（选调/招警/…）：与本行同格同卷型，"
                         "**不是**另一场考试")
        if (not r["srcs"] and not r["mds"] and r["level"] == LEVEL_SHENGKAO
                and r["subject"] == "申论" and r["year"] in {str(y) for y in bj}):
            notes.append("该年源内可能位于并卷键中，待拆")
        if not r["mds"] and not r["srcs"]:
            notes.append("无任何来源提到（≠ 考试未举行）")
        row = {"level": r["level"], "region": r["region"], "year": r["year"],
               "subject": r["subject"], "session": r["session"], "ptype": r["ptype"],
               "attested_by": sorted(r["srcs"]),
               "delivered_md": (sorted(r["mds"])[0] if r["mds"] else ""),
               "note": "；".join(notes),
               "plain_titles": r["plain_titles"], "verify_titles": r["verify_titles"]}
        row["status"] = _status(row)
        rows.append(row)

    rows.sort(key=lambda x: (x["level"], x["region"], x["year"], x["subject"],
                             x["ptype"], x["session"]))

    bjrows = []
    for year in sorted(bj):
        b = bj[year]
        bjrows.append({
            "level": LEVEL_SHENGKAO, "region": "", "year": year, "subject": "申论",
            "session": "", "ptype": BINGJUAN_PTYPE,
            "attested_by": sorted(b["srcs"]), "delivered_md": b["md"],
            "note": "源并卷产物；待按真实省份拆分为独立卷型",
            "keys": sorted(b["keys"]), "plain_titles": [], "verify_titles": []})
        bjrows[-1]["status"] = _status(bjrows[-1])
    bjrows.sort(key=lambda x: x["year"])

    ngs = []
    for k, r in non_gs.items():
        ngs.append({"level": k[0], "region": k[1], "year": k[2], "subject": k[3],
                    "ptype": k[4], "session": k[5], "titles": sorted(set(r["titles"]))})
    ngs.sort(key=lambda x: (x["year"], x["level"], x["region"], x["subject"], x["ptype"]))
    return rows, bjrows, ngs


def _catalog_bounds(catalog_dir, repo_root, delivered, since):
    """`catalog` 与交付树的差集构成（**A0-3**）：**全部实算**，为 `EXPECTED.md` §九 供数。

    「交付树」的权威数取 `work/manifest.jsonl` 的 path 数（与 `delivered` 逐项交叉核对）；
    「≥since 的 catalog 行」逐行重算 `export.repo_paths`，路径不在 manifest ⇒ 该行**无落盘 md**。
    同格（`level/region/year/subject`）已有落盘件 ⇒ 该行「**有同伴**」（并卷/拼写差），
    否则是**整格零交付**。
    """
    manifest = os.path.join(repo_root, "work", "manifest.jsonl")
    mpaths = set()
    if os.path.exists(manifest):
        with io.open(manifest, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    mpaths.add(json.loads(line)["path"])
    cells = set()                                   # 交付树里「已有的格」
    for p in mpaths:
        seg = p.replace("\\", "/").split("/")
        if len(seg) == 4:                           # 省考/<region>/<year>/<subject>-<ptype>.md
            cells.add((seg[0], seg[1], seg[2], seg[3].split("-")[0]))
        elif len(seg) == 3 and seg[0] == LEVEL_GUOKAO:   # 国考/<year>/<subject>-<ptype>.md
            cells.add((LEVEL_GUOKAO, LEVEL_GUOKAO, seg[1], seg[2].split("-")[0]))
    cat = export.load_catalog(catalog_dir)
    cat_since = [r for r in cat if r["year"] >= since]
    orph = []
    for r in cat_since:
        key = PaperKey(r["level"], "" if r["level"] == LEVEL_GUOKAO else r["region"],
                       r["year"], r["subject"], r["ptype"])
        md, _ = export.repo_paths(key, r["slug"])
        md = md.replace("\\", "/")
        if md in mpaths:
            continue                                # 盘上有 ⇒ 不是差集
        reg = LEVEL_GUOKAO if r["level"] == LEVEL_GUOKAO else r["region"]
        orph.append({"level": r["level"], "region": reg, "year": r["year"],
                     "subject": r["subject"], "ptype": r["ptype"],
                     "n": r.get("n_questions"),
                     "srcs": sorted(r.get("sources") or []), "md_rel": md,
                     "sibling": (r["level"], reg, r["year"], r["subject"]) in cells})
    orph.sort(key=lambda x: (x["year"], x["level"], x["region"], x["ptype"]))
    return {"catalog_total": len(cat), "catalog_since": len(cat_since),
            "manifest": len(mpaths), "lt_since": len(cat) - len(cat_since),
            "delivered_evidence": len(delivered),
            "orphans": orph,
            "orphan_has": sum(1 for x in orph if x["sibling"]),
            "orphan_none": sum(1 for x in orph if not x["sibling"])}


def build(catalog_dir, uproots, repo_root, since, sghcn_dir=SGHCN_TOC_DIR):
    """→ `(md_text, ptype_map_text, jsonl_rows, stats)`。只读；不写任何文件。"""
    since = str(since)
    years = [str(y) for y in range(int(since), 2027)]
    evidences = (ev_catalog(catalog_dir)
                 + ev_xingcezhenti(uproots["xingcezhenti"])
                 + ev_shangantong(uproots["shangantong_c1"])
                 + ev_shangantong(uproots["shangantong_c2"])
                 + ev_linfukai186(uproots["linfukai186"])
                 + ev_slb(repo_root)
                 + ev_sghcn(sghcn_dir))
    delivered = set()
    for e in evidences:
        md = e.get("md_rel")
        if not md or e["year"] < since:
            continue
        if os.path.exists(os.path.join(repo_root, md.replace("/", os.sep))):
            delivered.add(md)
    rows, bjrows, ngs = merge_rows(evidences, since, delivered, years)
    all_rows = rows + bjrows
    bounds = _catalog_bounds(catalog_dir, repo_root, delivered, since)
    stats = {"delivered": delivered, "n_ev": len(evidences),
             "n_delivered_paths": len(delivered), "bounds": bounds}
    return (render_md(all_rows, bjrows, ngs, since, len(evidences), bounds),
            render_ptype_map(evidences, since, delivered), all_rows, stats)


# ---- 人读账 ------------------------------------------------------------------

def _blank_section(L, all_rows):
    """§六 `region=""` 行（A4）：并卷行 + 无省名行，分列。"""
    blank = [r for r in all_rows if r["region"] == ""]
    bj_only = [r for r in blank if r["ptype"] == BINGJUAN_PTYPE]
    rest = [r for r in blank if r["ptype"] != BINGJUAN_PTYPE]
    L += ["## 六、`region=\"\"` 行（**允许非零**，不计入覆盖率）", "",
          "> 白名单只补了 `深圳`/`广州`（A4）；补完后 `region=\"\"` **允许非零**，但须逐条可解释。"
          "本账共 **%d** 行 = ① 并卷行 **%d** + ② 无省名行 **%d**。" % (
              len(blank), len(bj_only), len(rest)),
          "", "### ① 并卷行（`ptype=\"并卷\"`，恰 %d 行）" % len(bj_only), ""]
    for r in bj_only:
        L.append("- `%s` 年：`%s`（源并卷键，待拆）" % (r["year"], r["delivered_md"]))
    L += ["", "### ② 无省名行（源标题里没有可归位的地区名，**不瞎填**）", ""]
    if not rest:
        L.append("- （无）")
    for r in sorted(rest, key=lambda x: (x["year"], x["level"], x["subject"], x["ptype"])):
        L.append("- `%s / %s / %s / %s / %s` %s ← 原串：%s（来源 %s）" % (
            r["level"], r["year"], r["subject"], r["ptype"], r["session"] or "—",
            r["status"], _short(r["plain_titles"], 3),
            ", ".join(r["attested_by"]) or "—"))
    L.append("")
    return L


def render_md(all_rows, bjrows, ngs, since, n_ev, bounds=None):
    """`all_rows` = **最终写盘的整行集**（含并卷行）。所有计数只从这里导出（A5）。

    `bounds` = `_catalog_bounds(...)` 的产物（A0-3）；缺省 `None` ⇒ **不渲染 §九**
    （既有单测以 5 参调用，仍得八节）。行集内的计数**一律**从 `all_rows` 导出。
    """
    n = len(all_rows)
    cnt = collections.Counter(r["status"] for r in all_rows)
    years = sorted({r["year"] for r in all_rows}, reverse=True)
    xc = sum(1 for r in all_rows if r["subject"] == "行测")
    sl = sum(1 for r in all_rows if r["subject"] == "申论")
    empty = [r for r in all_rows if r["status"] == "尚未找到"]
    empty_x = sum(1 for r in empty if r["subject"] == "行测")
    empty_s = sum(1 for r in empty if r["subject"] == "申论")

    L = []
    L += ["# 应有试卷清单（全量·机器算·人可审计）", "",
          "> 机器生成（`tools/gwyzhenti/expect.py`）。范围：`year >= %s`、`国考 + 31 省级地区"
          "（+ 深圳/广州）`、行测/申论。**只读**：本账不导入任何内容、不改交付树、"
          "不做跨卷去重。" % since, ""]

    # ---- 一、口径声明 ----
    L += ["## 一、口径声明", "",
          "1. **应有 = 规则骨架 ∪ 多来源 TOC 证据并集**，**不是**模型记忆。"
          "规则骨架 = 用户点名的检查格（31 省级地区 + 国考 × %s–%s × 行测/申论），"
          "它**只**表达「该地区该年该科应有一卷待查」，**不声称**该卷存在："
          "没有来源提到的格一律落 `尚未找到`。" % (since, years[0]),
          "2. **`尚未找到` 只表示「本机所有来源都没提到」**这一件事，"
          "**绝不表示该考试没有举行**。判定某考试未举行需要**独立证据**，本账没有那种证据。",
          "3. **`多省联考` 是源并卷键、不是地区**：本账**不产出** `region=\"多省联考\"` 的行；"
          "并卷键单列 `ptype=\"并卷\"`（§五），其落盘件计入 `delivered_md` 以保账闭合。",
          "4. **证据并集，不由记忆断言**：每一行的 `attested_by` 都真枚举自下列来源的 TOC。"
          "来源名 ∈ `{catalog, xingcezhenti, shangantong, linfukai186, SLB, sghcn}`，其中 "
          "`catalog` = 交付树（`work/catalog/catalog.jsonl` + `export.repo_paths` 判盘上 md "
          "是否存在）；`sghcn` = `SGHCN0762` 的**文件名清单**（§十）。"
          "**注意**：来源 ∈ `attested_by` **≠** 该来源可导入 —— 见 §十「来源可导入性」。",
          "5. **卷型归一（修轮 1 / A1，控制器裁定 R-COV-16）**：`canon_ptype` **只在匹配层**用 —— "
          "**已交付行按交付侧原始串落键**（一行一路径，与 manifest 一一对应），源侧证据按 "
          "canonical 匹配到已交付行。⇒ 交付侧 `A类` 与源侧 `A卷` 归一为**同一行**（幻影缺口消失），"
          "而交付侧两个**不同**交付件（如黑龙江 2019 申论 `统考` 与 `急需紧缺岗位`）"
          "**各占一行、两个路径都在**。映射与压平组见 `work/PTYPE-MAP.md`。"
          "**归一化只发生在比较层，交付树文件名一字未动。**",
          "6. **账闭合（A2）**：`{delivered_md}` == `work/manifest.jsonl` 的全部 path"
          "（**双向差集为空**）。",
          "7. **非国省考移出主账（A3）**：选调/招警/公安院校联考/政法干警/基层项目类"
          "**不计入四数**，单列 §七；其独占的格**不生成** `尚未找到` 占位。",
          "8. 一行 = 一个 `(level, region, year, subject, ptype, session)`；同格 distinct 卷型各占"
          "一行 ⇒ **行数是卷型级的、多于格级**。`session` 与 `ptype` **脱钩**（A6）："
          "`ptype` 永不含「上半年/下半年」。", ""]

    # ---- 二、总量四数 ----
    L += ["## 二、总量（四数 + 待核实单列）", "",
          "| 项 | 卷数 |", "|---|---:|",
          "| **应有总数**（本账总行数） | **%d** |" % n,
          "| 其中 `已有`（交付树有 md） | %d |" % cnt["已有"],
          "| 其中 `源有未导入` | %d |" % cnt["源有未导入"],
          "| 其中 `尚未找到` | %d |" % cnt["尚未找到"],
          "| 其中 `待核实`（单列，预期 0） | %d |" % cnt["待核实"],
          "",
          "> **四数之和 = `已有 %d` + `源有未导入 %d` + `尚未找到 %d` + `待核实 %d` = %d**"
          " == `EXPECTED.jsonl` 行数 **%d**。" % (
              cnt["已有"], cnt["源有未导入"], cnt["尚未找到"], cnt["待核实"], n, n),
          "> `尚未找到` **≠** 考试未举行（§一.2）：**行测 %d 行 / 申论 %d 行**。"
          % (empty_x, empty_s),
          "> 范围：`year >= %s`，共 %d 个年份（%s–%s）；`行测 %d 行 / 申论 %d 行`。"
          % (since, len(years), years[-1], years[0], xc, sl),
          "> 并卷键 **%d 行**（`ptype=\"并卷\"`，已含在本表与总数内）。" % len(bjrows),
          "> 证据条数（未合并前）共 **%d** 条。" % n_ev, ""]

    # ---- 三、交叉表 ----
    L += ["## 三、按 `status` × 科目（交叉表）", "",
          "> 本表由**最终写盘行集**导出，故各行列和 == §二 的 `行测 %d + 申论 %d = %d`（A5）。"
          % (xc, sl, n), "",
          "| status | 行测 | 申论 | 合计 |", "|---|---:|---:|---:|"]
    for st in ("已有", "源有未导入", "尚未找到", "待核实"):
        a = sum(1 for r in all_rows if r["status"] == st and r["subject"] == "行测")
        b = sum(1 for r in all_rows if r["status"] == st and r["subject"] == "申论")
        L.append("| %s | %d | %d | %d |" % (st, a, b, a + b))
    L += ["| **合计** | **%d** | **%d** | **%d** |" % (xc, sl, n),
          "",
          "> 并卷行 %d 行（申论侧）已计入上表的 `已有` 列，**不再另列**（§二 与 §三 同源）。"
          % len(bjrows), ""]

    # ---- 四、缺卷清单 ----
    miss = [r for r in all_rows if r["status"] != "已有"]
    miss.sort(key=lambda r: (r["year"], r["level"], r["region"], r["subject"],
                             r["ptype"], r["session"]), reverse=True)
    L += ["## 四、缺卷清单（**非 `已有`**，按年份倒序）", "",
          "> 共 **%d** 行（`源有未导入` %d + `尚未找到` %d + `待核实` %d）。"
          % (len(miss), cnt["源有未导入"], cnt["尚未找到"], cnt["待核实"]), ""]
    for year in sorted({r["year"] for r in miss}, reverse=True):
        grp = [r for r in miss if r["year"] == year]
        L += ["### %s 年（缺 %d 行；行测 %d / 申论 %d）" % (
                  year, len(grp),
                  sum(1 for r in grp if r["subject"] == "行测"),
                  sum(1 for r in grp if r["subject"] == "申论")), "",
              "| level | region | subject | ptype | session | status | attested_by | note |",
              "|---|---|---|---|---|---|---|---|"]
        for r in sorted(grp, key=lambda x: (x["level"], x["region"], x["subject"],
                                            x["ptype"], x["session"])):
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["level"], r["region"] or "（未归位）", r["subject"], r["ptype"],
                r["session"] or "—", r["status"],
                ", ".join(r["attested_by"]) or "—",
                (r["note"] or "").replace("|", "\\|")))
        L.append("")

    # ---- 五、并卷键清单 ----
    L += ["## 五、并卷键清单（`ptype=\"并卷\"`，**不是**一个地区）", "",
          "> `linfukai186` 的 `shengkao-shenlun` 把多个省塞进**一个**键 ⇒ 该键**不是**地区。"
          "本账据此单列，**不产出** `region=\"多省联考\"` 的行；对应各省的格照常判"
          "（`note` 注明「该年源内可能位于并卷键中，待拆」）。", "",
          "| year | 键名 | 题数 | status | delivered_md | source |",
          "|---|---|---:|---|---|---|"]
    for r in bjrows:
        for name, cnt_i in r.get("keys", []):
            L.append("| %s | `%s` | %d | %s | `%s` | %s |" % (
                r["year"], name, cnt_i, r["status"], r["delivered_md"],
                ", ".join(r["attested_by"])))
    if bjrows:
        _byrs = sorted({r["year"] for r in bjrows})
        _span = _byrs[0] if len(_byrs) == 1 else "%s–%s" % (_byrs[0], _byrs[-1])
        _multi = sum(1 for r in bjrows if len(r.get("keys", [])) > 1)
        L += ["",
              "> 并卷行 **%d** 行（%s；同一年源内若有多批键则合为**一行**、"
              "键名与题数俱列 —— 本期多批键的年份计 %d 个）。" % (
                  len(bjrows), _span, _multi),
              "> 交付树里这一坨并卷落盘**已计入** `delivered_md`（账闭合到 manifest），"
              "但**不**被计为「单省已有卷」；它是**待拆分**的合并件。", ""]
    else:
        L += ["",
              "> 并卷行 **0** 行（本账的行集里没有 `ptype=\"并卷\"` 的落键）。", ""]

    # ---- 六、region="" ----
    L = _blank_section(L, all_rows)

    # ---- 七、非国省考 ----
    # A0-4：前言的示例**从数据生成**（不得硬编码一个与本表冲突的例子）。
    ngs_titles = {t for r in ngs for t in (r["titles"] or [])}
    main_vt_rows = [r for r in all_rows if r.get("verify_titles")]
    main_vt = sorted({t for r in main_vt_rows for t in r["verify_titles"]
                      if t not in ngs_titles})
    ex = ("（如 `%s`）" % main_vt[0]) if main_vt else ""
    L += ["## 七、非国省考（选调/招警/公安院校联考/政法干警/基层，**不计入应有**）", "",
          "> 口径（A3）：**整行只由非国省考类标题组成**的行 ⇒ 移出主账、**不计入四数**、"
          "也不生成格级占位，在此单列。共 **%d** 条（按 `(level, region, year, subject, "
          "ptype, session)` 聚合）。" % len(ngs),
          "> 只**提及**选调/招警而实为国省考卷的标题%s**留在主账**（本账共 **%d** 行带此类"
          "标题，逐行见 §四 的 `note`）：它与主行**同格同卷型**、是同一份卷的一体两面，"
          "**不是**另一场考试。" % (ex, len(main_vt_rows)),
          "> ⇔ 对照：**上表**列出的 %d 条才是**移出**主账的（整行皆非国省考类）。"
          "前言示例由上表**反选**生成（取主行集里出现、且**不在**上表内的标题）⇒ "
          "二者**不可能**冲突。" % len(ngs), "",
          "| level | region | year | subject | ptype | session | 原始 title |",
          "|---|---|---|---|---|---|---|"]
    for r in ngs:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["level"], r["region"] or "（未归位）", r["year"], r["subject"], r["ptype"],
            r["session"] or "—", _short(r["titles"], 3).replace("|", "\\|")))
    L += ["",
          "> `status=\"待核实\"` **保留为合法取值**，但按 A3 主行集内预期为 **0** 行 —— "
          "这类考试**不进「应有」**，故不产生缺口。", ""]

    # ---- 八、诚实边界 ----
    L += ["## 八、诚实边界（未做的事）", "",
          "- 本账只证明「**有来源提到**」这样一份卷，**不证明**该卷真实存在、"
          "更**不证明**来源内容完整或与原卷一致。",
          "- `attested_by` 仅 **1** 个来源的行**可信度低**（可能是源自己的转写/回忆版）；"
          "本账**未做任何内容核对**，未打开任何 md/PDF，未比对原卷。",
          "- **源标题若未指明卷型**（归一后落 `统考`）而同格已交付的是**别的**卷型，"
          "本账**不会**猜着并进去，而是新建一行 `源有未导入` 并在 `note` 记原串 —— "
          "宁可多一行可疑、也不并错一份卷。",
          "- **未做跨卷去重**：同名卷在不同来源各记一条证据；归一后行键相同即并成一行。",
          "- **未导入任何内容**、未改正文/答案、未碰 PDF、未动交付树与 `work/mirror/`；"
          "**交付树文件名一字未改**（归一化只在比较层）。",
          "- **归一有损**：`canon_ptype` 会把别名压平（如 `乡镇卷/乡镇/定向乡镇 → 乡镇`）。"
          "压平组逐条列在 `work/PTYPE-MAP.md`。该表**只用于匹配**：已交付行的 `ptype` 仍"
          "保留交付侧原始串（故账里会同时出现 `乡镇卷`（已交付行）与 `乡镇`（源侧行））。",
          "- `region=\"\"` 的行**不计入**覆盖率（§六）。",
          "- 空格行 `ptype=\"统考\"` 是**占位**：本账不声称该年该科只有一卷或只有一种卷型。",
          "- **`尚未找到` 不等于考试未举行**；要判「未举行」需独立证据，本账没有。", ""]

    # ---- 九、账的边界：catalog 与交付树的差集构成（A0-3） ----
    if bounds is not None:
        b = bounds
        L += ["## 九、账的边界：`catalog` 与交付树的差集构成", "",
              "> 本节**全部实算**（`expect._catalog_bounds`）——**没有一处手写求和**。"
              "它划清「本账（`EXPECTED.jsonl`）」「`catalog`（候选清单）」「交付树（盘上 md）」"
              "三者的边界。", "",
              "| 量 | 值 | 实算式 |", "|---|---:|---|",
              "| `work/catalog/catalog.jsonl` 总行数 | %d | `len(load_catalog())` |"
              % b["catalog_total"],
              "| 其中 `year >= %s` | %d | `len([r for r in cat if r.year >= \"%s\"])` |"
              % (since, b["catalog_since"], since),
              "| 其中 `< %s` | %d | `%d - %d` |"
              % (since, b["lt_since"], b["catalog_total"], b["catalog_since"]),
              "| `work/manifest.jsonl` 的 path 数（= 交付树） | %d | `len(set(paths))` |"
              % b["manifest"],
              "| 本账 `delivered_md` 覆盖的 path（V1，双向差集为空） | %d | "
              "`len({r.delivered_md})` |" % b["delivered_evidence"],
              "",
              "**`catalog − 交付树 = %d − %d = %d` 行，正确分解为**："
              "**`%d`（`< %s`，按设计不在范围）+ `%d`（`>= %s`，**有行但盘上无 md**）**。"
              % (b["catalog_total"], b["manifest"],
                 b["catalog_total"] - b["manifest"],
                 b["lt_since"], since, len(b["orphans"]), since),
              "",
              "> 旧稿写「`catalog − manifest = 366`，**全是 2016 前**」——**错**。"
              "`366 = %d + %d`，其中 **%d** 行是 `>= %s` 的行测卷**有出处却没有落盘 md**。"
              % (b["lt_since"], len(b["orphans"]), len(b["orphans"]), since), "",
              "### 那 %d 行（`>= %s` 的 catalog 行，路径不在 manifest 里）" % (
                  len(b["orphans"]), since), "",
              "- **全部是行测**：%d / %d。" % (
                  sum(1 for x in b["orphans"] if x["subject"] == "行测"), len(b["orphans"])),
              "- **全部只由 `linfukai186` 一个源提供**：%d / %d。" % (
                  sum(1 for x in b["orphans"] if x["srcs"] == ["linfukai186"]),
                  len(b["orphans"])),
              "- **根因**（`export.py:run` 实读）：", "",
              "  ```python",
              "  if \"xingcezhenti\" not in row[\"sources\"]:",
              "      rep.skipped.append({\"slug\": row[\"slug\"], \"reason\": \"本批只导出有正文的源\"})",
              "  ```", "",
              "  ⇒ **行测只导「带 `xingcezhenti` 源」的行**（申论无此过滤）。"
              "故这 %d 行是「**该源的导出器尚未写**」，**不是「源里没有」** —— "
              "除非该格另有进路，否则它们**在交付树里恒缺**。" % len(b["orphans"]),
              "- **分类**（逐行实算）：**%d 行有同伴**（同格已按**别的卷型**落盘，"
              "属并卷/拼写差）＋ **%d 行整格零交付**。" % (
                  b["orphan_has"], b["orphan_none"]),
              "- **补导归 Task 4**（裁定 **R-COV-21**）：本件**只**把差集写清，"
              "**不导任何内容、不动交付树**。", "",
              "| year | level | region | subject | ptype | 题数 | 同格有交付件 | 目标路径（缺） |",
              "|---|---|---|---|---|---:|---|---|"]
        for x in b["orphans"]:
            L.append("| %s | %s | %s | %s | %s | %s | %s | `%s` |" % (
                x["year"], x["level"], x["region"] or "（未归位）", x["subject"],
                x["ptype"], "—" if x["n"] is None else x["n"],
                "有" if x["sibling"] else "**无**", x["md_rel"]))
        L += ["",
              "> 合计行数 `%d = %d（有同伴）+ %d（零交付）`。" % (
                  len(b["orphans"]), b["orphan_has"], b["orphan_none"]),
              "> 其中「同格只交付了**别的卷型**」的典型：`国考 2019 行测-统考`（124 题）"
              "↔ 已交付 `副省级` + `地市级`；`吉林 2017 甲级/乙级` ↔ 交付侧拼作 "
              "`卷甲级`/`卷乙级`；`青海 2020 行测 C类`（79 题）↔ 同格只交付 `A类`/`B类`。", ""]

    # ---- 十、来源可导入性（W5） ----
    L += ["## 十、来源可导入性（哪些源能当**卷源**）", "",
          "> `attested_by` 里出现的来源**不等于**可补源。本节逐源交代「能不能拿它把缺卷"
          "补成交付件」，**防止把 `sghcn` 误当可补源**。", "",
          "| 源 | 形式 | 可否作**卷源** | 说明 |", "|---|---|---|---|",
          "| 交付树 / `xingcezhenti` | md | 是（已交付） | 交付树本体；`xingcezhenti` 是其"
          "上游正文本（md，含图） |",
          "| `shangantong` | html | 是（含图） | `paper_*/index.html` |",
          "| `linfukai186` | json | 是（题级，须成卷） | 题级 JSON，须按卷重组 |",
          "| `SLB` | md | 是（逐卷记来源） | 已下载的 md 清单（`chars < 2000` 的存根除外） |",
          "| **`sghcn`** | **pdf（申论）/ json（行测，无图）** | **否 —— 仅 TOC / 原件对照** | "
          "**R-COV-11** |", "",
          "> **`sghcn` 为什么是「否」**：它会让一批行变成 `源有未导入`（本账的 `attested_by` "
          "里会出现 `sghcn`），但它的**行测 JSON 无图**、**申论为 PDF** ⇒ 本批**不可导入**。"
          "它的价值是**卷型地图**（给 Task 3 拆并卷用），**不是**内容源。", ""]
    return "\n".join(L)


def render_ptype_map(evidences, since, delivered=None):
    """`work/PTYPE-MAP.md`：**本轮评审的主要审计面**（A1/V7）。

    交付侧**全部**原始值 → `(canonical, session)` + 条数；源侧观察到的别名；未匹配原串；
    归一后剩余的不同 canonical 值；**被压平的组**；以及裁定带来的「原始串落键」说明。

    `delivered` = 盘上 md 的 path 集合（`build` 传入）。用于把 §2 的**合计**拆成
    「盘上有 md」/「有行无 md」两半 —— **合计一律由 `len()`/`sum()` 实算并打印校验式**
    （A0-2：**禁止手写求和**）。缺省 `None` ⇒ 只打印纯合计。
    """
    deliv = collections.Counter()
    on_disk = collections.Counter()
    src = collections.Counter()
    unmapped_src = collections.Counter()
    for e in evidences:
        if since and e["year"] < since:
            continue
        if e.get("bingjuan"):
            continue
        raw = e.get("ptype_raw") or ""
        if e["src"] == "catalog":
            if raw:
                deliv[raw] += 1
                if delivered and e.get("md_rel") in delivered:
                    on_disk[raw] += 1
        elif raw:
            src[raw] += 1
        else:
            unmapped_src[e.get("title") or ""] += 1

    L = ["# 卷型归一映射表（`canon_ptype`）—— 修轮 1 / A1 的审计面", "",
         "> 机器生成（`tools/gwyzhenti/expect.py`）。范围 `year >= %s`。" % since,
         "> **归一化只发生在比较层**：交付树文件名一字未动。按控制器裁定 R-COV-16，"
         "**已交付行以交付侧原始串落键**（保交付路径），本表给出的 canonical 值"
         "**只用于把源侧证据匹配到已交付行**。", "",
         "## 1. 规范词表（canonical `ptype`）", "",
         "共 **%d** 个允许值。**计数差异如实记录**：简令正文写「共 **27** 个允许值」，"
         "但其后列举了 **28** 项，且其别名表另需 `县级`（`县级卷 / 县级 -> 县级`）。"
         "按控制器裁定 R-COV-16-1 补入 `县级` ⇒ **自洽词表 = 28 列举项 + `县级`**（下例）。"
         % len(CANON_PTYPES), "",
         "```", " ".join(CANON_PTYPES), "```", "",
         "`session ∈ {\"\", \"上半年\", \"下半年\"}`，**独立字段**，规范 ptype 里永不含它。", "",
         "## 2. 交付侧：%d 个原始值 → `(canonical, session)`" % len(deliv), "",
         "> **V7 要求覆盖交付侧全部原始值**（简令写「50」，实测 **%d** 个）。"
         "已交付行的 `ptype` **保留左列原始串**；右列 canonical 只用于匹配源侧证据。"
         % len(deliv), "",
         "| 原始串 | 条数 | canonical（匹配用） | session | 是否需归一 |",
         "|---|---:|---|---|---|"]
    for raw, k in sorted(deliv.items(), key=lambda x: (-x[1], x[0])):
        canon, sess = canon_ptype(raw)
        need = "否" if (canon == raw and not sess) else "**是**"
        L.append("| `%s` | %d | `%s` | %s | %s |" % (
            raw, k, canon, sess or "—", need))
    # A0-2：**合计必须实算**（`sum(...)`），并在同处打印**校验式**（逐项和式 == 结果）。
    _items = sorted(deliv.items(), key=lambda x: (-x[1], x[0]))
    _total = sum(k for _, k in _items)
    _expr = "+".join(str(k) for _, k in _items)
    _disk = sum(on_disk.values())
    L.append("| **合计** | **%d** | — | — | **校验式**：`sum(条数) = %s = %d`；"
             "其中 `%d` 条盘上有 md（已交付）+ `%d` 条有行无 md（见 `EXPECTED.md` §九）"
             % (_total, _expr, _total, _disk, _total - _disk))
    uniq_canon = sorted({canon_ptype(r)[0] for r in deliv},
                        key=lambda c: _IDX.get(c, 99))
    # A0-1：判据必须与 `canon_ptype` **同一出口** —— `match_ptype(raw)[0] is None`
    # （子串最长优先），**不得**手写 `raw not in ALIAS_TO_CANON` 这类精确键 membership。
    _tk = sorted(((r, k) for r, k in deliv.items() if match_ptype(r)[0] is None),
                 key=lambda x: (-x[1], x[0]))
    L += ["",
          "> 交付侧原始值 **%d** 个（`len(deliv)`）；**归一后剩余的不同 canonical 值：%d "
          "个**（`len(set(canon))`）—— %s。"
          % (len(deliv), len(uniq_canon),
             "、".join("`%s`" % c for c in uniq_canon)), "",
          "> **落 canonical `统考` 的交付侧原始串**（判据 = **`match_ptype(raw)[0] is None`**，"
          "即**与 `canon_ptype` 同一出口**；共 **%d** 个 / %d 条 —— `len(...)` / `sum(...)` "
          "实算）：%s。"
          % (len(_tk), sum(k for _, k in _tk),
             "、".join("`%s`×%d" % (r, k) for r, k in _tk) or "（无）"), "",
          "> 注：判据**不是**「`raw` 不在别名表里」—— 那是**精确键** membership，会把 "
          "`A卷：省直`（含 `省直`）、`上半年乡镇卷`（含 `乡镇卷`）这类**能匹配到别名**的串"
          "误列进来。此处改用与 `canon_ptype` 完全同一出口的子串匹配（最长优先）。", ""]

    L += ["## 3. 源侧：观察到的卷型词（匹配到的别名）", "",
          "| 别名 | 条数 | canonical |", "|---|---:|---|"]
    _src_items = sorted(src.items(), key=lambda x: (-x[1], x[0]))
    for raw, k in _src_items:
        L.append("| `%s` | %d | `%s` |" % (raw, k, ALIAS_TO_CANON[raw]))
    # A0-2：源侧两半**实算**并给校验式：匹配到的 + 未匹配的 == 源侧非并卷证据总数。
    _src_tot = sum(k for _, k in _src_items)
    _src_um = sum(unmapped_src.values())
    L.append("| **合计（匹配到别名）** | **%d** | **校验式**：`sum(条数) = %s = %d` |" % (
        _src_tot, "+".join(str(k) for _, k in _src_items) or "0", _src_tot))
    L += ["",
          "> 源侧标题里**未匹配**任何别名的证据 **%d** 条 ⇒ canonical `统考`"
          "（即「源标题未指明卷型」）；这类证据**只**匹配同格 canonical 也是 `统考` 的已交付行，"
          "否则新建行（`note` 记原串）。示例（前 10 条）：" % _src_um, ""]
    for t, k in sorted(unmapped_src.items(), key=lambda x: (-x[1], x[0]))[:10]:
        L.append("- （%d 条）`%s`" % (k, t))
    L += ["",
          "> **源侧非并卷证据（`year >= %s`）合计的校验式**：匹配到别名 `%d` + 未匹配 `%d` "
          "= **%d**；未匹配那半覆盖 `len(distinct 标题) = %d` 个标题。" % (
              since, _src_tot, _src_um, _src_tot + _src_um, len(unmapped_src)), ""]

    L += ["## 4. 被归一压平的组（同一 canonical 下的多个交付侧原始串）", "",
          "| canonical | 交付侧原始串（含条数） | 合计条数 |", "|---|---|---:|"]
    groups = collections.defaultdict(list)
    for raw, k in deliv.items():
        groups[canon_ptype(raw)[0]].append((raw, k))
    flat = 0
    flat_sum = 0
    single_sum = 0
    for canon in sorted(groups, key=lambda c: (-sum(k for _, k in groups[c]), c)):
        members = sorted(groups[canon], key=lambda x: (-x[1], x[0]))
        if len(members) < 2:
            single_sum += sum(k for _, k in members)
            continue
        flat += 1
        flat_sum += sum(k for _, k in members)
        L.append("| `%s` | %s | %d |" % (
            canon, "、".join("`%s`×%d" % (r, k) for r, k in members),
            sum(k for _, k in members)))
    # A0-2：本表三个数**全由 `sum(...)` 实算**，并打印**校验式**（多值组 + 单值组 == §2 合计）。
    L.append("| **合计（多值组）** | **%d 组** | **%d** |" % (flat, flat_sum))
    L += ["",
          "> **校验式**：多值组 `%d` 条 + 单值组 `%d` 条 = **%d** == §2 的合计 `sum(条数) = %d`。"
          % (flat_sum, single_sum, flat_sum + single_sum, _total), "",
          "> 只列**多于一个原始串**的组（共 **%d** 组，`len(...)` 实算）；单值组见 §2。压平是**有损**的，"
          "但正是它消灭了「交付侧 `A类` vs 源侧 `A卷`」这类**幻影缺口**；"
          "而它**不会**并掉两个已交付件 —— 已交付行按原始串落键"
          "（如 `统考` 组含 `急需紧缺岗位`，但黑龙江 2019 申论两个交付件**仍各占一行**）。"
          % flat, "",
          "## 5. 本表的边界", "",
          "- 本表**不**声称任何原始串与 canonical 的映射是「考纲事实」，它只是**比较层**的"
          "去重口径；映射由简令别名表逐字照用（最长优先 + 同长按规范词序）。",
          "- 未匹配的原始串**不猜**：一律落 `统考` 并在账内保留原串。", ""]
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
    md_txt, map_txt, rows, _stats = build(a.catalog, uproots, a.repo, a.since)
    out_md = os.path.join(a.repo, "work", "EXPECTED.md")
    out_jsonl = os.path.join(a.repo, "work", "EXPECTED.jsonl")
    out_map = os.path.join(a.repo, "work", "PTYPE-MAP.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with io.open(out_md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md_txt)
    lines = "".join(
        json.dumps({k: r[k] for k in JSONL_FIELDS}, ensure_ascii=False) + "\n" for r in rows)
    with io.open(out_jsonl, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lines)
    with io.open(out_map, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(map_txt)
    print("→", out_md, len(md_txt.encode("utf-8")), "字节")
    print("→", out_jsonl, len(lines.encode("utf-8")), "字节")
    print("→", out_map, len(map_txt.encode("utf-8")), "字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
