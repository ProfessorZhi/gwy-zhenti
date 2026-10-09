# -*- coding: utf-8 -*-
"""SLB 申论源接入（**候选区**）：把 `mkih76/SLB` 的 `data/shenlun_zhenti`（393 份全卷 md）
解析、过滤、归位，产出**可审**的索引与**交付格式候选** md。

为什么有这一件（Task 2 / 覆盖优先）：用户第一阶段头号优先级是「2023–2026 缺失的申论」。
SLB 是本轮验真的**唯一成规模 md 申论源**（裁定 R-COV-4）。本件把它**接入候选区**并产出
可追溯的身份账，**不动交付树**（R-COV-6）。

口径（**身份与归位一律从 `title` 重新解析**，**不信** frontmatter 的 `province`/`exam_type`）：

  实测 `exam_type` **不可信**：`2017年深圳市公务员考试《申论》试题` / `2016年广州市公务员考试
  《申论》试题` 的 `exam_type` 都写作 **`国考`**；深圳/广州是**真实的市考**（裁定 R-COV-22A），
  必须按 `title` 归位为 `region="深圳"/"广州"`。

  排除类（`reason` 取值，**按序判定，先中先出**）：
    * `国考_0素材` —— 文件名以 `国考_0_` 开头的**素材文章**（非试卷），必须排除。
    * `存根<2000` —— `chars < 2000` 的存根。
    * `无年份` —— 标题取不到 `(20\\d\\d)`。
    * `无科目` —— 标题不含「申论」且无科目兜底。
    * `模考` —— 命中过滤词（模考/模拟/大赛/预测/押题/密卷/冲刺/精选）。
    * `年<2016` —— 年份 `(20\\d\\d)` 早于 2016（交付下限）。
    * `非国省考:选调` / `:招警` / `:政法干警` / `:公安院校联考` / `:基层项目` —— R-COV-9。
    * `联考多省并列无法归位` —— `level="省考"` 但 `title` 定不出**唯一**省（多省并列联考）。

  采用行的 `level/region/ptype/session` **复用主包共享解析**（`expect.parse_title` /
  `canon_ptype` / `match_ptype`）——**不另起第二套词表**。国考 ⇒ `level="国考"`,
  **`region="国考"`**（R-COV-22；与 `EXPECTED.jsonl` 国考行一致，**绝不**用 `region=""` 冒充）。
  `region="多省联考"` **恒为 0**。

**只读** `data/shenlun_zhenti`、`work/EXPECTED.jsonl`；**只写** `work/slb-INDEX.jsonl`、
`work/slb-GAP.md`、`work/slb-cand/**`。
**不**动交付树、`work/catalog/`、`work/manifest.jsonl`、`work/EXPECTED.*`、`work/PTYPE-MAP.md`、
`work/slb_shenlun_manifest.json`；**不**下载 PDF、**不**导入交付、**不**改正文、**不**跨卷去重。

**S4 缺口对账**（`build_gap` / `render_gap`）：读 `work/EXPECTED.jsonl` 取
`subject=="申论"` 且 `status!="已有"` 的行，与采用候选按 `(level, region, year, ptype)` 对键，
**逐条给证据**（候选路径 ↔ EXPECTED 键）。**「有候选」≠「已补齐交付」**。

风格照 `tools/gwyzhenti/expect.py`（同包、argparse + main + 打印路径与条数）。
"""
import argparse
import io
import json
import os
import re

from . import expect

# ---- 口径常量 ----------------------------------------------------------------

# 源目录（**相对上游克隆根**）：`<SLB>/data/shenlun_zhenti`。
SRC_SUBDIR = os.path.join("data", "shenlun_zhenti")
# 本机默认上游克隆路径（S1 sparse clone 的目标）。
DEFAULT_SRC = os.path.join("D:" + os.sep, "projects", "_gwy-upstream", "SLB", SRC_SUBDIR)

# 素材文章的文件名前缀（**非试卷**，必须排除）。
MATERIAL_PREFIX = "国考_0_"
# 存根门槛（与 `ev_slb` / `slb_shenlun_manifest.json` 一致）。
MIN_CHARS = 2000
# 交付下限（与 `expect` 的 `--since` 一致）。
MIN_YEAR = "2016"

# 非国省考类 → `reason` 细分标签（**按序**，先中先出）。
VERIFY_REASONS = (("选调", "选调"), ("招警", "招警"), ("政法干警", "政法干警"),
                  ("公安院校", "公安院校联考"), ("到基层", "基层项目"))

# `work/slb-INDEX.jsonl` 每行的字段，**固定 15 个且顺序固定**（简令 S2）。
INDEX_FIELDS = ("tid", "file", "title", "province_raw", "exam_type_raw", "year", "chars",
                "level", "region", "subject", "ptype", "session", "verdict", "reason",
                "chars_ok")

# 校验状态底盘（**含明确未核验标注**，简令 S3）。
VERIFY_BASE = "机器校验（身份/来源/字数）；未人工通读；第三方源，再分发条件未核实"

_FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.S)
_YEAR_RE = re.compile(r"(20\d\d)")
_Q1_RE = re.compile(r"问题[一二三四五六七八九十]+")
_Q2_RE = re.compile(r"第[一二三四五六七八九十]+题")
_SCORE_RE = re.compile(r"[（(]\s*\d+\s*分\s*[）)]")


# ---- 解析 --------------------------------------------------------------------

def read_index(src_dir):
    """读 `_manifest.json` → `list[dict]`（原始记录，字段照抄）。"""
    with io.open(os.path.join(src_dir, "_manifest.json"), encoding="utf-8") as fh:
        obj = json.load(fh)
    return list(obj)


def count_md(src_dir):
    """目录内 `.md` 数（S1 断言用；**显式 `os.listdir`**，不用 Glob）。"""
    return len([f for f in os.listdir(src_dir) if f.endswith(".md")])


def split_fm(text):
    """源 md → `(frontmatter dict, 去 fm 后的文本)`。无 fm ⇒ `({}, 原文)`。"""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def extract_body(rest):
    """去 fm 后的文本 → `(H1 标题, 正文)`；去掉**首个**一级标题行与其前导空行。

    正文**逐字保留**（仅统一换行为 LF —— 不改任何内容字符）。
    """
    lines = rest.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    h1 = ""
    if i < len(lines) and lines[i].startswith("# "):
        h1 = lines[i][2:].strip()
        i += 1
    body = "\n".join(lines[i:])
    return h1, body.lstrip("\n")


def multi_ptypes(title):
    """标题里命中的**全部** distinct 规范卷型（`>=2` ⇒ **合卷**，需在 `校验状态` 标注）。

    **别名按最长优先**（`expect.ALIASES` 已排序）：被更长命中**包含**的短语**丢弃**
    （否则 `副省级` 里的 `省级` 会被误判成第二个卷型）。
    """
    present = [a for a, _c in expect.ALIASES if a in title]
    kept = []
    for a in present:
        if any(a != b and a in b for b in kept):
            continue
        kept.append(a)
    return sorted({expect.ALIAS_TO_CANON[a] for a in kept})


def count_questions(body):
    """正文题数（**启发式**：`问题N` 与 `第N题` 的 distinct 数取大；都为 0 ⇒ 用分值标记数）。

    返回 `(n, method)`：`method ∈ {"问题N", "第N题", "分值标记", "未检出"}`。
    """
    q1 = len(set(_Q1_RE.findall(body)))
    q2 = len(set(_Q2_RE.findall(body)))
    if q1 or q2:
        if q1 >= q2:
            return q1, "问题N"
        return q2, "第N题"
    sc = len(_SCORE_RE.findall(body))
    if sc:
        return sc, "分值标记"
    return 0, "未检出"


def classify(rec):
    """一条源记录 → 索引行（**固定 15 字段**）。身份/归位一律从 `title` 解析。"""
    tid = str(rec.get("tid") or "")
    fn = rec.get("file") or ""
    title = rec.get("title") or ""
    chars = int(rec.get("chars") or 0)
    row = {"tid": tid, "file": fn, "title": title,
           "province_raw": rec.get("province") or "",
           "exam_type_raw": rec.get("exam_type") or "",
           "year": "", "chars": chars, "level": "", "region": "", "subject": "",
           "ptype": "", "session": "", "verdict": "", "reason": "",
           "chars_ok": chars >= MIN_CHARS}

    m = _YEAR_RE.search(title)
    if m:
        row["year"] = m.group(1)

    # 1) 素材文章（非试卷）
    if fn.startswith(MATERIAL_PREFIX):
        row["verdict"], row["reason"] = "排除", "国考_0素材"
        return row
    # 2) 存根
    if chars < MIN_CHARS:
        row["verdict"], row["reason"] = "排除", "存根<2000"
        return row
    # 3) 无年份
    if not row["year"]:
        row["verdict"], row["reason"] = "排除", "无年份"
        return row
    # 4) 科目
    if "申论" in title:
        row["subject"] = "申论"
    else:
        row["verdict"], row["reason"] = "排除", "无科目"
        return row
    # 5) 过滤词
    for w in expect.DROP_WORDS:
        if w in title:
            row["verdict"], row["reason"] = "排除", "模考"
            return row
    # 6) 共享解析（归位）
    p = expect.parse_title(title, subject_hint="申论")
    if p is None:
        row["verdict"], row["reason"] = "排除", "无科目"
        return row
    row["level"], row["region"] = p["level"], p["region"]
    row["ptype"], row["session"] = p["ptype"], p["session"]
    # 7) 交付下限
    if row["year"] < MIN_YEAR:
        row["verdict"], row["reason"] = "排除", "年<2016"
        return row
    # 8) 非国省考
    if p["verify"]:
        for w, tag in VERIFY_REASONS:
            if w in title:
                row["verdict"], row["reason"] = "排除", "非国省考:" + tag
                return row
        row["verdict"], row["reason"] = "排除", "非国省考:其他"
        return row
    # 9) 多省并列、定不出唯一省（**绝不**臆造某一省，**绝不**用 region="" 冒充国考）
    if row["level"] == expect.LEVEL_SHENGKAO and row["region"] == "":
        row["verdict"], row["reason"] = "排除", "联考多省并列无法归位"
        return row
    row["verdict"], row["reason"] = "采用", "ok"
    return row


def _tid_key(row):
    """稳定排序键（数值 tid 优先）。"""
    t = row["tid"]
    return (0, int(t)) if t.isdigit() else (1, 0), t


def build_index(records):
    """全部记录 → 索引行（**按 tid 数值稳定排序**，产物逐字节可复现）。"""
    rows = [classify(r) for r in records]
    rows.sort(key=_tid_key)
    return rows


# ---- 候选 md ----------------------------------------------------------------

def cand_relpath(row):
    """采用行 → 相对 `work/slb-cand/` 的路径（**不含**重名后缀）。

    国考：`国考/<年份>/申论-<卷型>.md`（无地区层）；省考：`省考/<地区>/<年份>/申论-<卷型>.md`。
    """
    if row["level"] == expect.LEVEL_GUOKAO:
        return os.path.join("国考", row["year"], "申论-%s.md" % row["ptype"])
    return os.path.join("省考", row["region"], row["year"], "申论-%s.md" % row["ptype"])


def plan_paths(rows):
    """采用行 → `(row, relpath)`；**同路径冲突不覆盖** ⇒ 后续件加 `__t<tid>`。

    处理顺序 = `build_index` 的排序顺序（确定性）。
    """
    out, used = [], set()
    for row in rows:
        if row["verdict"] != "采用":
            continue
        rel = cand_relpath(row)
        if rel in used:
            base, ext = os.path.splitext(rel)
            rel = "%s__t%s%s" % (base, row["tid"], ext)
        used.add(rel)
        out.append((row, rel))
    return out


def render_candidate(row, body, notes=()):
    """索引行 + 正文 → 候选 md 全文（frontmatter 照交付树键名/取值域）。

    `notes`：如实标注的缺损/机制性说明（**不删件**；全部并入 `校验状态`）。
    """
    exam = "国考" if row["level"] == expect.LEVEL_GUOKAO else "省考"
    region = row["region"]
    n, _method = count_questions(body)
    truth = "网友回忆版" if "回忆" in row["title"] else "正式真题"
    form = "联考" if "联考" in row["title"] else "单独命题"
    verify = VERIFY_BASE + ("".join("；" + x for x in notes))
    fm = [
        "---",
        u'考试: "%s"' % exam,
        u'地区: "%s"' % region,
        u'年份: "%s"' % row["year"],
        u'科目: "申论"',
        u'卷型: "%s"' % row["ptype"],
        u'真题性质: "%s"' % truth,
        u'命题形式: "%s"' % form,
        u'来源: ["slb"]',
        u'来源明细: "shenlunhome.com tid=%s crawled_at=%s"' % (row["tid"], row["_crawled"]),
        u'题号口径: "源无卷内题号，按源序编号"',
        u'校验状态: "%s"' % verify,
        "---",
    ]
    head = u"\n".join(fm) + u"\n\n# %s\n\n> 申论 · %d 题 · %s %s\n\n" % (
        row["title"], n, region, row["year"])
    return head + body


def write_candidates(src_dir, work_dir, rows):
    """按 `plan_paths` 写 `work/slb-cand/**`；返回 `(list[(row, relpath, abspath)], 重名列表)`。"""
    root = os.path.join(work_dir, "slb-cand")
    planned = plan_paths(rows)
    out, collided = [], []
    for row, rel in planned:
        base = cand_relpath(row)
        notes = []
        if base != rel:
            collided.append((row["tid"], base, rel))
            notes.append(u"同格重名，文件名加 tid 后缀（不覆盖）")
        mp = multi_ptypes(row["title"])
        if len(mp) >= 2:
            notes.append(u"源标题含合卷标记（%s 同卷）" % u"/".join(mp))
        fm, body, crawled = _load_body(src_dir, row)
        n, method = count_questions(body)
        if n == 0:
            notes.append(u"题号标记未检出")
        if "作答要求" not in body:
            notes.append(u"正文未见「作答要求」标记")
        row = dict(row)
        row["_crawled"] = crawled
        text = render_candidate(row, body, notes)
        abspath = os.path.join(root, rel)
        d = os.path.dirname(abspath)
        if not os.path.isdir(d):
            os.makedirs(d)
        with io.open(abspath, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        out.append((row, rel, abspath))
    return out, collided


def _load_body(src_dir, row):
    """源 md → `(fm, body, crawled_at)`。"""
    p = os.path.join(src_dir, row["file"])
    text = io.open(p, encoding="utf-8", newline="").read()
    fm, rest = split_fm(text)
    _h1, body = extract_body(rest)
    return fm, body, fm.get("crawled_at", "")


# ---- 汇总 --------------------------------------------------------------------

def summarize(rows):
    """`(verdict 计数, reason 计数, 采用数)`。"""
    vc, rc = {}, {}
    for r in rows:
        vc[r["verdict"]] = vc.get(r["verdict"], 0) + 1
        key = r["reason"]
        rc[key] = rc.get(key, 0) + 1
    return vc, rc, vc.get("采用", 0)


def write_index(path, rows):
    """写 `slb-INDEX.jsonl`（固定 15 字段，行序 = 索引序）。"""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            proj = {k: r[k] for k in INDEX_FIELDS}
            fh.write(json.dumps(proj, ensure_ascii=False) + u"\n")


# ---- S4 缺口对账 -------------------------------------------------------------

def load_expected(work_dir):
    """读 `work/EXPECTED.jsonl`（**只读**，Task 1b 后版本）→ `list[dict]`。"""
    p = os.path.join(work_dir, "EXPECTED.jsonl")
    with io.open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def build_gap(work_dir, rows):
    """缺口对账数据（**不落盘**）。返回 dict。

    * `exp_n` / `exp_status`：EXPECTED 总行数与 status 计数。
    * `shen_n` / `gap_n`：申论行数 / 申论非「已有」行数（= S4 的缺口集）。
    * `filled`：缺口行里**有候选**的 —— `(key, exp_status, [(tid, rel), ...])`。
    * `still`：缺口行里**无候选**的 —— `(key, exp_status, attested_by)`。
    * `new`：候选键在 EXPECTED 申论行里**根本不存在**（新增卷型）—— `(key, [(tid, rel)])`。
    * `dup`：候选命中的是 EXPECTED **已有**行（重复源）。
    """
    exp = load_expected(work_dir)
    shen = [r for r in exp if r["subject"] == "申论"]
    gaps = [r for r in shen if r["status"] != "已有"]
    exp_shen_keys = {(r["level"], r["region"], r["year"], r["ptype"]) for r in shen}
    status_all = {}
    for r in exp:
        status_all[r["status"]] = status_all.get(r["status"], 0) + 1

    cand = {}
    for row, rel in plan_paths(rows):
        k = (row["level"], row["region"], row["year"], row["ptype"])
        cand.setdefault(k, []).append((row["tid"], rel.replace(os.sep, "/")))

    filled, still, new, dup = [], [], [], []
    for r in gaps:
        k = (r["level"], r["region"], r["year"], r["ptype"])
        if k in cand:
            filled.append((k, r["status"], cand[k]))
        else:
            still.append((k, r["status"], r.get("attested_by") or []))
    for k in sorted(cand, key=lambda x: (x[2], x[0], x[1], x[3])):
        if k not in exp_shen_keys:
            new.append((k, cand[k]))
    # dup：候选键存在且该申论行 status == 已有（重复源）
    for r in shen:
        k = (r["level"], r["region"], r["year"], r["ptype"])
        if r["status"] == "已有" and k in cand:
            dup.append((k, cand[k]))
    return {"exp_n": len(exp), "exp_status": status_all, "shen_n": len(shen),
            "gap_n": len(gaps), "filled": filled, "still": still, "new": new, "dup": dup,
            "adopted_n": sum(1 for r in rows if r["verdict"] == "采用")}


def _kstr(k):
    return u"%s/%s/%s/%s" % (k[0], k[1] or u"—", k[2], k[3])


def render_gap(g):
    """缺口对账数据 → `work/slb-GAP.md` 全文。"""
    L = []
    A = L.append
    A(u"# SLB 申论源 → 缺口对账（Task 2 · S4）")
    A(u"")
    A(u"**口径**：读 `work/EXPECTED.jsonl`（Task 1b 后版本），取 `subject==\"申论\"` 且 "
      u"`status!=\"已有\"` 的行，与 `work/slb-INDEX.jsonl` 里 `verdict==\"采用\"` 的候选"
      u"按 `(level, region, year, ptype)` 逐条对键。")
    A(u"")
    A(u"**重要**：本节只证「**候选区里有这份正文**」；候选在 `work/slb-cand/`，"
      u"**尚未导入交付树**，故「有候选」**≠**「已补齐交付」。")
    A(u"")
    A(u"## 计数")
    A(u"")
    A(u"| 项 | 数 |")
    A(u"|---|---|")
    A(u"| EXPECTED 总行 | %d |" % g["exp_n"])
    for k in ("已有", "源有未导入", "尚未找到"):
        A(u"| EXPECTED `%s` | %d |" % (k, g["exp_status"].get(k, 0)))
    A(u"| EXPECTED 申论行 | %d |" % g["shen_n"])
    A(u"| **EXPECTED 申论缺口行（非「已有」）** | **%d** |" % g["gap_n"])
    A(u"| 本批采用候选（`slb-INDEX` verdict=采用） | %d |" % g["adopted_n"])
    A(u"| **补上的缺口行（候选键命中缺口）** | **%d** |" % len(g["filled"]))
    A(u"| 仍缺（缺口行无候选） | %d |" % len(g["still"]))
    A(u"| 候选新增卷型（EXPECTED 原无此申论键） | %d |" % len(g["new"]))
    A(u"| 候选命中「已有」行（重复源，不影响交付） | %d |" % len(g["dup"]))
    A(u"")
    A(u"## 一、补上的缺口（候选证据 ↔ EXPECTED 键）")
    A(u"")
    A(u"> 一个缺口键可能对应**多份**候选（同年同省多卷，如江苏 2019 A/B/C）⇒ 下表数据行数 "
      u"> **≥** 键数。")
    A(u"")
    A(u"| EXPECTED 键 | 原 status | 候选 tid | 候选路径 |")
    A(u"|---|---|---|---|")
    for k, st, cands in sorted(g["filled"], key=lambda x: (x[0][2], x[0][0], x[0][1], x[0][3])):
        for tid, rel in cands:
            A(u"| `%s` | %s | %s | `work/slb-cand/%s` |" % (_kstr(k), st, tid, rel))
    A(u"")
    A(u"## 二、仍缺（缺口行，本批**无**候选）")
    A(u"")
    A(u"| EXPECTED 键 | status | attested_by（其它源） |")
    A(u"|---|---|---|")
    for k, st, ab in sorted(g["still"], key=lambda x: (x[0][2], x[0][0], x[0][1], x[0][3])):
        A(u"| `%s` | %s | %s |" % (_kstr(k), st, u", ".join(ab) or u"—"))
    A(u"")
    A(u"## 三、候选新增卷型（EXPECTED 申论行里原来没有的键）")
    A(u"")
    A(u"| 候选键 | tid | 候选路径 |")
    A(u"|---|---|---|")
    for k, cands in g["new"]:
        for tid, rel in cands:
            A(u"| `%s` | %s | `work/slb-cand/%s` |" % (_kstr(k), tid, rel))
    A(u"")
    A(u"## 四、候选命中「已有」行（重复源）")
    A(u"")
    A(u"| EXPECTED 键 | 候选 tid | 候选路径 |")
    A(u"|---|---|---|")
    for k, cands in g["dup"]:
        for tid, rel in cands:
            A(u"| `%s` | %s | `work/slb-cand/%s` |" % (_kstr(k), tid, rel))
    A(u"")
    return u"\n".join(L)


def write_gap(work_dir, rows):
    """写 `work/slb-GAP.md`；返回对账数据。"""
    g = build_gap(work_dir, rows)
    p = os.path.join(work_dir, "slb-GAP.md")
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_gap(g))
    return g


# ---- CLI --------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="SLB 申论源 → 候选区索引 + 候选 md")
    ap.add_argument("--src", default=DEFAULT_SRC, help="SLB data/shenlun_zhenti 目录")
    ap.add_argument("--work", default=os.path.join(".", "work"), help="work 目录")
    ap.add_argument("--no-md", action="store_true", help="只写索引，不写候选 md")
    ap.add_argument("--gap", action="store_true", help="另写 work/slb-GAP.md（S4 缺口对账）")
    args = ap.parse_args(argv)

    src, work = args.src, args.work
    n_md = count_md(src)
    records = read_index(src)
    print(u"源目录: %s" % src)
    print(u"  _manifest.json 条数: %d ; 目录内 .md 数: %d ; 一致: %s"
          % (len(records), n_md, len(records) == n_md))

    rows = build_index(records)
    vc, rc, n_adopt = summarize(rows)
    idx = os.path.join(work, "slb-INDEX.jsonl")
    write_index(idx, rows)
    print(u"索引: %s（%d 行）" % (idx, len(rows)))
    print(u"  verdict: %s" % vc)
    print(u"  reason :")
    for k in sorted(rc, key=lambda x: (-rc[x], x)):
        print(u"    %-24s %d" % (k, rc[k]))

    if not args.no_md:
        out, collided = write_candidates(src, work, rows)
        print(u"候选 md: %s（%d 份）" % (os.path.join(work, "slb-cand"), len(out)))
        if collided:
            print(u"  同格重名（已加 tid 后缀，未覆盖）: %d 处" % len(collided))

    if args.gap:
        g = write_gap(work, rows)
        print(u"缺口对账: %s" % os.path.join(work, "slb-GAP.md"))
        print(u"  EXPECTED 总行 %d ; 申论缺口行 %d ; 补上 %d ; 仍缺 %d ; 新增卷型 %d ; 重复源 %d"
              % (g["exp_n"], g["gap_n"], len(g["filled"]), len(g["still"]),
                 len(g["new"]), len(g["dup"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
