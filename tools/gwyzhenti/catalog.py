# -*- coding: utf-8 -*-
"""段一：把各源 adapter 的清单汇总成 catalog.jsonl 与覆盖报告。

**本模块绝不读也不写 gwy-zhenti 的正文。**
"""
import io
import json
import os
from dataclasses import dataclass, field

from .model import PaperKey
from .naming import LEVEL_GUOKAO, LEVEL_SHENGKAO, PROVINCES as _PROVINCES_BY_LEN, Unparsed, classify
from .slug import paper_slug
from .sources import ADAPTERS

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
    by_region: dict = field(default_factory=dict)
    by_subject: dict = field(default_factory=dict)


def _dump_jsonl(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def build(uproots, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    all_records, all_unparsed, all_excluded = [], [], []
    for family, root in sorted(uproots.items()):
        adapter = ADAPTERS.get(family)
        if adapter is None:
            raise KeyError("未注册的源: %s" % family)
        res = adapter.scan(root)
        all_records.extend(res.records)
        all_unparsed.extend(res.unparsed)
        all_excluded.extend(res.excluded)

    # —— 按 (层级, 地区, 年份, 科目, 卷型) 聚合；原始卷名保真 ——
    papers = {}
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
        key = c.key
        p = papers.setdefault(key, {
            "title": r["title"], "nature": c.nature, "form": c.form,
            "modules": {}, "sources": set(), "titles": {}, "declared": 0,
        })
        p["modules"][r["module"]] = p["modules"].get(r["module"], 0) + r["n_questions"]
        p["sources"].add(r["family"])
        # **逐源保真**：同一卷键被多源提供时，各留各的原始卷名 —— 冲突页拿它当证据
        p["titles"][r["family"]] = r["title"]
        if r.get("declared_questions", -1) > 0:
            p["declared"] += r["declared_questions"]

    rows = []
    rep = Report(records=len(all_records),
                 unparsed=len(all_unparsed), excluded=len(all_excluded))
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
            "titles": {k: p["titles"][k] for k in sorted(p["titles"])},
        })
        rep.papers += 1
        rep.questions += n
        rep.by_region[key.region or "国考"] = rep.by_region.get(key.region or "国考", 0) + 1
        rep.by_subject[key.subject] = rep.by_subject.get(key.subject, 0) + 1

    _dump_jsonl(os.path.join(out_dir, "catalog.jsonl"), rows)
    _dump_jsonl(os.path.join(out_dir, "excluded.jsonl"), all_excluded)
    _dump_jsonl(os.path.join(out_dir, "unparsed.jsonl"), all_unparsed)
    _write_coverage(out_dir, rows, rep)
    _write_gaps(out_dir, rows, rep)
    _write_conflicts(out_dir, rows)
    return rep


def _region_rows(rows):
    """覆盖/缺口两表共用的地区行序列。

    固定行 = `国考` + 31 省；**再加** catalog 里实际出现的**非省份地区类**
    （实测有 `多省联考`）。不加这一项的话，这类卷存在于 `catalog.jsonl` 却在
    `coverage.md` / `gaps.md` 里**凭空消失** —— 恰好违背「地域齐全 > 时间齐全」的第一优先级。
    """
    seen = {r["region"] or "国考" for r in rows}
    extra = sorted(seen - {"国考"} - set(PROVINCES))
    return ["国考"] + list(PROVINCES) + extra


def _write_coverage(out_dir, rows, rep):
    have = {}
    for r in rows:
        have.setdefault((r["region"] or "国考", r["subject"]), []).append(r["year"])
    L = ["# 覆盖矩阵（地区 × 科目）", "",
         "> 由 catalog.jsonl 实算得出。**地域齐全 > 时间齐全**：先看地区行是否空白，再看年份纵深。", "",
         "| 地区 | 科目 | 卷数 | 年份跨度 | 年份数 |", "|---|---|---:|---|---:|"]
    for region in _region_rows(rows):
        for subject in SUBJECTS:
            ys = have.get((region, subject), [])
            if ys:
                L.append("| %s | %s | %d | %s–%s | %d |"
                         % (region, subject, len(ys), min(ys), max(ys), len(set(ys))))
            else:
                L.append("| %s | %s | 0 | — | 0 | **缺**" % (region, subject))
    L += ["", "**合计**：%d 卷 / %d 题。" % (rep.papers, rep.questions)]
    _w(os.path.join(out_dir, "coverage.md"), L)


def _write_gaps(out_dir, rows, rep):
    have = {(r["region"] or "国考", r["subject"]) for r in rows}
    L = ["# 缺口清单", "",
         "> 排序 = **地域优先**、年份次之、**新卷先于老卷**。", ""]
    L.append("## 一、地区级缺口（最高优先）")
    for region in _region_rows(rows):
        missing = [s for s in SUBJECTS if (region, s) not in have]
        if missing:
            L.append("- **%s**：缺 %s" % (region, "、".join(missing)))
    L.append("")
    L.append("## 二、年次级缺口（地区齐了再看）")
    for region in _region_rows(rows):
        ys = sorted({r["year"] for r in rows if (r["region"] or "国考") == region})
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
            L.append("    - `%s`：%s" % (fam, r["titles"].get(fam, "—")))
    _w(os.path.join(out_dir, "conflicts.md"), L)


def _w(path, lines):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
