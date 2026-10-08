# -*- coding: utf-8 -*-
"""段一：把各源 adapter 的清单汇总成 catalog.jsonl 与覆盖报告。

**本模块绝不读也不写 gwy-zhenti 的正文。**
"""
import io
import json
import os
from dataclasses import dataclass, field

from . import export   # 见下方 import 环论证
from .naming import LEVEL_GUOKAO, PROVINCES as _PROVINCES_BY_LEN, Unparsed, classify
from .slug import paper_slug
from .sources import ADAPTERS

# **导入环论证（整改 F2·D4，实查结论）**：`catalog` 需要 `export._parts_for` 来判「M1 有正文」。
# 实查依赖方向：`export` 只 import `mdread, render, model`（**不** import `catalog`），
# 而 `render` 只 import `mdread, model`，`model`/`mdread` 无内部依赖 ⇒ `catalog → export` 是**单向边，不成环**。
# 反向只有 `cli` 单向 import `catalog`（`gates` 也只 import `export, mdread, render, model`）。
# 故此处**模块级**导入安全；无需（也不必）在函数体内延迟导入。

SUBJECTS = ("行测", "申论")
# 省级地区全集（用于「地域齐全」度量）。**单一真源**：`naming.PROVINCES`（Task 5 引入，
# 那里按**长度倒序**是为了最长匹配）。这里 `sorted()` 重排成**码点序**，只为覆盖表的行序
# 稳定可复现 —— 两份硬编码的省份表迟早会漂移，故不另抄一份。
PROVINCES = tuple(sorted(_PROVINCES_BY_LEN))


@dataclass
class Report:
    papers: int = 0
    records: int = 0
    questions: int = 0
    unparsed: int = 0
    excluded: int = 0
    # 硬编码目录白名单**之外**、被显式记录的目录数（见 `sources/*` 的 `unmapped`；整改 F2·C）。
    # 真树应为 **0**（表外目录一个也没有）；非零即「有题被静默跳过」的告警。
    unmapped: int = 0
    by_region: dict = field(default_factory=dict)
    by_subject: dict = field(default_factory=dict)


def _dump_jsonl(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def build(uproots, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    all_records, all_unparsed, all_excluded, all_unmapped = [], [], [], []
    for family, root in sorted(uproots.items()):
        adapter = ADAPTERS.get(family)
        if adapter is None:
            raise KeyError("未注册的源: %s" % family)
        res = adapter.scan(root)
        all_records.extend(res.records)
        all_unparsed.extend(res.unparsed)
        all_excluded.extend(res.excluded)
        all_unmapped.extend(res.unmapped)

    # —— 按 (层级, 地区, 年份, 科目, 卷型) 聚合；原始卷名保真 ——
    # 每卷键的三种卷名视图（改动 B 的三件套）：
    #   `title`   = **首个**被聚合进来的原始卷名（顺序由 `sorted(uproots)` 决定）；
    #   `titles`  = 逐源家族保留的**全部不同**原始卷名（去重、排序后的列表），**不再后写覆盖**；
    #   `dubious` = 非空 ⇒ 同源多名里存在**互不为子串**者 ⇒ 该键**可能撞 slug**（见 `_dubious`）。
    papers = {}
    rep = Report()          # `records` 只在 classify **成功**时累加（评审 F3）
    for r in all_records:
        try:
            # 科目**取自记录**（各 adapter 已按目录/模块判定过）—— **不得在此写死**：
            # 写死 `行测` 会把 linfukai186 的 686 份申论卷全部错标成行测，
            # 而 classify 不校验科目 ⇒ 错标会**静默**进 coverage.md。
            c = classify(r["region"], r["year"], r["title"], subject=r["subject"])
        except Unparsed as exc:            # 理论上 adapter 已分流；此处兜底
            # 兜底也**必须按 `kind` 分流**（同 Task 4）：否则「有意排除」的卷会挤进 `unparsed`
            # ——那是 G1 盯的缺陷桶，长期非零会让它失去告警意义。
            bucket = all_unparsed if exc.kind == Unparsed.UNPARSED else all_excluded
            bucket.append(dict(r, reason=exc.reason))
            continue
        rep.records += 1                    # 只有**进了 catalog** 的记录才算（评审 F3）
        key = c.key
        p = papers.setdefault(key, {
            "title": r["title"], "nature": c.nature, "form": c.form,
            "modules": {}, "sources": set(), "titles": {}, "declared": 0,
        })
        p["modules"][r["module"]] = p["modules"].get(r["module"], 0) + r["n_questions"]
        p["sources"].add(r["family"])
        # **逐源保真**：同一卷键被多源提供时，各留各的原始卷名 —— 冲突页拿它当证据。
        # 同一个（家族 × 卷键）被**多个不同卷名**喂入时**全部保留**（曾经的覆盖写法会丢名，
        # 正是 F2 的最小复现），由 `_dubious` 再判这是命名变体还是疑似撞 slug。
        p["titles"].setdefault(r["family"], set()).add(r["title"])
        if r.get("declared_questions", -1) > 0:
            p["declared"] += r["declared_questions"]

    # 未入选的去向在**循环之后**才齐（兜底也会往桶里追加），此处按最终桶长回填。
    rep.unparsed = len(all_unparsed)
    rep.excluded = len(all_excluded)
    rep.unmapped = len(all_unmapped)

    rows = []
    for key in sorted(papers):
        p = papers[key]
        n = sum(p["modules"].values())
        rows.append({
            "level": key.level, "region": key.region, "year": key.year,
            "subject": key.subject, "ptype": key.ptype,
            "slug": paper_slug(key),
            "title": p["title"], "nature": p["nature"], "form": p["form"],
            "modules": p["modules"], "n_questions": n,
            "declared_questions": p["declared"],
            "sources": sorted(p["sources"]),
            "titles": {k: sorted(p["titles"][k]) for k in sorted(p["titles"])},
            "dubious": _dubious(p["titles"]),
        })
        rep.papers += 1
        rep.questions += n
        rep.by_region[key.region or LEVEL_GUOKAO] = rep.by_region.get(key.region or LEVEL_GUOKAO, 0) + 1
        rep.by_subject[key.subject] = rep.by_subject.get(key.subject, 0) + 1

    _dump_jsonl(os.path.join(out_dir, "catalog.jsonl"), rows)
    _dump_jsonl(os.path.join(out_dir, "excluded.jsonl"), all_excluded)
    _dump_jsonl(os.path.join(out_dir, "unparsed.jsonl"), all_unparsed)
    # **新开一个 `unmapped` 台账**（整改 F2·C 的二选一）：不塞进 `unparsed.jsonl`。
    # 理由：`unparsed` 是 G1 盯的**缺陷桶**、长期必须为 0，它的语义已在多份文档里冻结为
    # 「卷解析失败」；把「目录不在白名单」混进去会让 0/非 0 的含义变模糊。单列一个台账，
    # 事件类型一眼可辨，且真树应为 0 行（表外目录一个也没有）。
    xingce_root = uproots.get("xingcezhenti")
    _dump_jsonl(os.path.join(out_dir, "unmapped.jsonl"), all_unmapped)
    _write_coverage(out_dir, rows, rep, xingce_root)
    _write_gaps(out_dir, rows, xingce_root)
    _write_conflicts(out_dir, rows)
    return rep


def _region_rows(rows):
    """覆盖/缺口两表共用的地区行序列。

    固定行 = `国考` + 31 省；**再加** catalog 里实际出现的**非省份地区类**
    （实测有 `多省联考`）。不加这一项的话，这类卷存在于 `catalog.jsonl` 却在
    `coverage.md` / `gaps.md` 里**凭空消失** —— 恰好违背「地域齐全 > 时间齐全」的第一优先级。
    """
    seen = {r["region"] or LEVEL_GUOKAO for r in rows}
    extra = sorted(seen - {LEVEL_GUOKAO} - set(PROVINCES))
    return [LEVEL_GUOKAO] + list(PROVINCES) + extra


def _subject_rows(rows):
    """覆盖/缺口两表共用的科目行序列。

    固定行 = `SUBJECTS`；**再加** catalog 里实际出现但不在 `SUBJECTS` 的科目（排序）。
    同 `_region_rows` 的 `extra` 一个道理：不加这一项，第三科目等**非固定科目**的卷
    存在于 `catalog.jsonl` 却在 `coverage.md` / `gaps.md` 里**凭空消失**（评审 F6）。
    """
    seen = {r["subject"] for r in rows}
    extra = sorted(seen - set(SUBJECTS))
    return list(SUBJECTS) + extra


def _dubious(titles_by_family):
    """同源多名里，若**存在两个互不为子串**的卷名 ⇒ 说明这可能是**两份不同的卷**被算成了同一个键。

    只看「互不为子串」是为了把**命名变体**（`2015·北京市公考` ⊂ `2015·北京市公考《申论》题`）
    放过 —— 那是同一份卷的两种写法。返回**全部**卷名（排序、去重），供人核对；空则返回 `[]`。
    """
    for fam in sorted(titles_by_family):
        ts = sorted(titles_by_family[fam])
        for i, a in enumerate(ts):
            for b in ts[i + 1:]:
                if a not in b and b not in a:
                    return sorted({t for f in titles_by_family for t in titles_by_family[f]})
    return []


def _body_by_cell(rows, xingce_root):
    """`(地区, 科目)` → **M1 真能导出正文**的卷数（`export._parts_for` 非空）。

    `xingce_root` 为假值（本次未接入 `xingcezhenti` 源）⇒ 返回空 dict，该列全 0 并由脚注声明
    「不可判」——**绝不用「有目录行」冒充「有正文」**（整改 F2·D/I6）。
    """
    out = {}
    if not xingce_root:
        return out
    for r in rows:
        parts, _ = export._parts_for(r, xingce_root)
        if parts:
            cell = (r["region"] or LEVEL_GUOKAO, r["subject"])
            out[cell] = out.get(cell, 0) + 1
    return out


def _write_coverage(out_dir, rows, rep, xingce_root=None):
    have = {}
    for r in rows:
        have.setdefault((r["region"] or LEVEL_GUOKAO, r["subject"]), []).append(r["year"])
    body = _body_by_cell(rows, xingce_root)
    L = ["# 覆盖矩阵（地区 × 科目）", "",
         "> 由 catalog.jsonl 实算得出。**地域齐全 > 时间齐全**：先看地区行是否空白，再看年份纵深。", "",
         "| 地区 | 科目 | 卷数 | 正文(M1) | 年份跨度 | 年份数 |",
         "|---|---|---:|---:|---|---:|"]
    for region in _region_rows(rows):
        for subject in _subject_rows(rows):
            ys = have.get((region, subject), [])
            if ys:
                L.append("| %s | %s | %d | %d | %s–%s | %d |"
                         % (region, subject, len(ys), body.get((region, subject), 0),
                            min(ys), max(ys), len(set(ys))))
            else:
                L.append("| %s | %s | 0 | 0 | — | 0 | **缺**" % (region, subject))
    L += ["", "**合计**：%d 卷 / %d 题。" % (rep.papers, rep.questions)]
    # **两种口径必须并列写清**（整改 F2·D3/E，评审 I6/I1）：
    if xingce_root:
        L += ["", "> **口径**：`卷数` = `catalog.jsonl` 里该 (地区,科目) 的**目录行数**（有目录行）；"
                  "`正文(M1)` = 其中 M1 **能导出正文**的卷数（`export._parts_for` 非空）；"
                  "两者之差 = **有目录无正文**（申论整片在此列，见 `gaps.md` 专段）。"]
    else:
        L += ["", "> **口径**：`卷数` = `catalog.jsonl` 里该 (地区,科目) 的**目录行数**；"
                  "**本次未接入 xingcezhenti 源，`正文(M1)` 该列不可判**（一律记 0）。"]
    L += ["> `catalog` 侧的**题数**是按**源累加**（同一卷键被多源提供时，各源各报一份相加）；"
          "而本表的 `卷数` / `正文(M1)` 是**卷键数**（**不累加**）—— 两个口径不可互相换算。"]
    _w(os.path.join(out_dir, "coverage.md"), L)


def _write_gaps(out_dir, rows, xingce_root=None):
    have = {(r["region"] or LEVEL_GUOKAO, r["subject"]) for r in rows}
    L = ["# 缺口清单", "",
         "> 排序 = **地域优先**、年份次之、**新卷先于老卷**。", ""]
    L.append("## 一、地区级缺口（最高优先）")
    for region in _region_rows(rows):
        missing = [s for s in _subject_rows(rows) if (region, s) not in have]
        if missing:
            L.append("- **%s**：缺 %s" % (region, "、".join(missing)))
    L.append("")
    # 整改 F2·D5：在「一、地区级缺口」之后加一段 —— 「有目录行」但 M1 **不出正文**的组合。
    # 这一段的全部意义就是不让 `coverage.md` 的「已覆盖」冒充「可交付」。
    L.append("## 二、有目录行但 M1 无正文")
    if not xingce_root:
        L.append("（本次未接入 xingcezhenti 源，**该段不可判**。）")
    else:
        body = _body_by_cell(rows, xingce_root)
        nobody = []
        for region in _region_rows(rows):
            for subject in _subject_rows(rows):
                cell = (region, subject)
                if cell not in have or body.get(cell):
                    continue
                n = sum(1 for r in rows
                        if (r["region"] or LEVEL_GUOKAO) == region and r["subject"] == subject)
                nobody.append((region, subject, n))
        if not nobody:
            L.append("（无）")
        for region, subject, n in nobody:
            L.append("- **%s** %s：有 %d 卷目录行，M1 **0 卷**有正文" % (region, subject, n))
    L.append("")
    L.append("## 三、年次级缺口（地区齐了再看）")
    for region in _region_rows(rows):
        ys = sorted({r["year"] for r in rows if (r["region"] or LEVEL_GUOKAO) == region})
        if not ys:
            continue
        full = {str(y) for y in range(2016, 2027)}
        miss = sorted(full - set(ys), reverse=True)      # 新的在前
        if miss:
            L.append("- %s：有 %s；缺 %s" % (region, "、".join(ys), "、".join(miss)))
    L += ["", "> 本表只反映**已 catalog 的源**。申论正文的导出排在 M3（见 spec §3）；"
              "**「有目录行」不等于「有可交付正文」** —— 转 M3 前不宣称申论覆盖。"]
    _w(os.path.join(out_dir, "gaps.md"), L)


def _write_conflicts(out_dir, rows):
    L = ["# 同卷多源冲突", "",
         "> 同一卷键被多个来源家族同时提供时列出，**留证不裁决**。", ""]
    hit = [r for r in rows if len(r["sources"]) > 1]
    if not hit:
        L.append("（本次无同键多源卷。）")
    for r in hit:
        L.append("- `%s` ← %s（%d 题 / %d 模块）"
                 % (r["slug"], "、".join(r["sources"]), r["n_questions"], len(r["modules"])))
        for fam in r["sources"]:
            ts = r["titles"].get(fam)
            L.append("    - `%s`：%s" % (fam, "、".join(ts) if ts else "—"))
    L += ["", "## 同源多名（疑似撞 slug）", "",
          "> 同一「来源家族 × 卷键」下有**互不为子串**的几个卷名 ⇒ 可能是**两份不同的卷**塌到了同一个",
          "> `slug`。段二导出会因此把两份卷合进一个文件。**此处只列证，不裁决。**", ""]
    doubtful = [r for r in rows if r["dubious"]]
    if not doubtful:
        L.append("（本次无。）")
    for r in doubtful:
        L.append("- `%s` ← %s" % (r["slug"], "、".join(r["sources"])))
        for t in r["dubious"]:
            L.append("    - `%s`" % t)
    _w(os.path.join(out_dir, "conflicts.md"), L)


def _w(path, lines):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
