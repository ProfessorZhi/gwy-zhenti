# -*- coding: utf-8 -*-
"""验收 / 发布分级全量账（只读 catalog + 交付树 + manifest + verify；写
work/ACCEPTANCE.md + work/ACCEPTANCE.jsonl）。

为什么有这一件（accept-1）：M3 之后 895 份 md 已交付、G1–G6 全绿，但 G1–G6 **全是**
「源 ↔ 导出」一致性判据，**没有一条**是「源 ↔ 原卷」。故本账把「已交付」与「可与真实
原卷相称」**严格分开**，给发布一道门槛可依的机器账。

风格照 `tools/gwyzhenti/report_m3.py`（同包、同 argparse + main + 直接打印路径与字节数）。
**只读**：绝不写交付树 / `work/manifest.jsonl` / `work/catalog/` / `work/verify/`；
只写 `work/ACCEPTANCE.md` 与 `work/ACCEPTANCE.jsonl`。

口径（裁定，逐字）：
  * `t1_已转写`  = 交付 md 存在（路径由 `export.repo_paths` 给出）。
  * `t2_幂等一致` = `t1` 且 manifest 同 path 的 sha256 == 盘上实际 sha256。
  * `t3_源内一致` = **corpus 级**，= `gate` 的 G1–G5 实跑通过。**本生成器不重算 G1–G5**
    （避免第二份可能漂移的保真实现），只在报告里引用其口径。**`t2` 不等于 `t3`。**
  * `t4_原卷核验` = 该 slug 在 `work/verify/records.jsonl` 有 ≥1 条 `verdict == "ok"`。
  * `t5_人工通读` = 同上且该记录 `human_read == True`。
  * `t4`/`t5` 依赖的 `records.jsonl` **不存在 ⇒ 全 0，绝不抛异常**（`os.path.exists` 先判）。
"""
import argparse
import collections
import hashlib
import io
import json
import os

from . import export, shenlun
from .model import PaperKey

# `work/ACCEPTANCE.jsonl` 每行一卷、字段固定为这些（brief 逐字）。
# `t4`/`t5` 是**定义里的分级字段**，其卷数在 md 分级表给出；逐卷布尔值不进 jsonl
# （jsonl 章节的「字段固定为」清单不含它们）。见报告里的口径说明。
JSONL_FIELDS = (
    "slug", "level", "region", "year", "subject", "md", "t1_已转写", "t2_幂等一致",
    "empty_requirement", "n_questions", "truncated", "has_cr", "form_suspect", "img_markers",
)


def _is_empty_requirement(q):
    """源 `q` 去掉 `\\r` 后 `.strip()` 止于「要求：」/「要求:」 ⇒ 该题作答要求为空（源缺）。"""
    t = (q or "").replace("\r", "").strip()
    return t.endswith("要求：") or t.endswith("要求:")


def load_manifest(repo_root):
    """→ {path: sha256}。文件不存在 ⇒ {}（不抛）。"""
    p = os.path.join(repo_root, "work", "manifest.jsonl")
    out = {}
    if not os.path.exists(p):
        return out
    with io.open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            out[e["path"]] = e["sha256"]
    return out


def load_verify(repo_root):
    """→ {slug: [记录, ...]}。`work/verify/records.jsonl` 不存在 ⇒ {}（不抛）。

    字段契约（供后续核验线写入，一行一卷一条）：`slug`(str)、`verdict`(str，`"ok"` 表示
    原卷核验通过)、`human_read`(bool)；若含外部来源内容，另加 `source_name`/`source_url`/
    `fetched_on`/`fields`（见 R-A1：逐条记来源，不得匿名并入）。
    """
    p = os.path.join(repo_root, "work", "verify", "records.jsonl")
    out = {}
    if not os.path.exists(p):
        return out
    with io.open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            out.setdefault(e.get("slug"), []).append(e)
    return out


def suspect_groups(rows):
    """`form_suspect`：同 `(level, region, year)` 下行测 distinct `ptype` ≥ 2 且申论 == 1。

    → {key: {"行测": [ptype...], "申论": [ptype...]}}，**只含命中组**；成员判据 = `key in 结果`。
    **指示不是证明**：行测多卷型不蕴含申论多卷型。
    """
    g = collections.defaultdict(lambda: {"行测": set(), "申论": set()})
    for r in rows:
        if r["subject"] in ("行测", "申论"):
            g[(r["level"], r["region"], r["year"])][r["subject"]].add(r["ptype"])
    out = {}
    for k, v in g.items():
        if len(v["行测"]) >= 2 and len(v["申论"]) == 1:
            out[k] = {"行测": sorted(v["行测"]), "申论": sorted(v["申论"])}
    return out


def grade_row(row, src, manifest, verify, suspects, repo_root):
    """逐 catalog 行算一条**分级记录**（含全部缺陷账字段）。

    返回字典含 `t4_原卷核验`/`t5_人工通读` 与内部用的 `cr_n`（`\\r` 出现次数）；写 jsonl 时
    由 `JSONL_FIELDS` 投影，只落固定字段。
    """
    key = PaperKey(row["level"], row["region"], row["year"], row["subject"], row["ptype"])
    md_rel, _ = export.repo_paths(key, row["slug"])
    p = os.path.join(repo_root, md_rel.replace("/", os.sep))
    exists = os.path.exists(p)
    sha = None
    has_cr = False
    cr_n = 0
    img = 0
    if exists:
        with open(p, "rb") as fh:
            raw = fh.read()
        sha = hashlib.sha256(raw).hexdigest()
        has_cr = b"\r" in raw
        cr_n = raw.count(b"\r")
        text = raw.decode("utf-8")
        img = text.count("<img") + text.count("![")
    t1 = bool(exists)
    t2 = bool(exists) and manifest.get(md_rel) == sha
    qs = export._shenlun_questions(row, src)
    empty = sum(1 for q in qs if _is_empty_requirement(q.get("q")))
    trunc = sum(1 for q in qs if len(q.get("s") or "") >= shenlun.TRUNCATED_LEN)
    vrecs = verify.get(row["slug"], [])
    t4 = any(x.get("verdict") == "ok" for x in vrecs)
    t5 = any(x.get("verdict") == "ok" and x.get("human_read") is True for x in vrecs)
    return {
        "slug": row["slug"], "level": row["level"], "region": row["region"],
        "year": row["year"], "subject": row["subject"], "md": md_rel,
        "t1_已转写": t1, "t2_幂等一致": t2,
        "t4_原卷核验": t4, "t5_人工通读": t5,
        "empty_requirement": empty, "n_questions": row["n_questions"],
        "truncated": trunc, "has_cr": has_cr, "cr_n": cr_n,
        "form_suspect": (row["level"], row["region"], row["year"]) in suspects,
        "img_markers": img,
    }


def _samples(recs, n=10):
    """缺陷密度最高抽样：按 `empty_requirement / n_questions` 降序（同比例按 `truncated` 降序）。"""
    ranked = sorted(
        (r for r in recs if r["n_questions"] > 0),
        key=lambda r: (-(r["empty_requirement"] / r["n_questions"]), -r["truncated"]))
    return ranked[:n]


def render_md(recs, suspects, since):
    n = len(recs)
    t1 = sum(1 for r in recs if r["t1_已转写"])
    t2 = sum(1 for r in recs if r["t2_幂等一致"])
    t4 = sum(1 for r in recs if r["t4_原卷核验"])
    t5 = sum(1 for r in recs if r["t5_人工通读"])
    sl = [r for r in recs if r["subject"] == "申论"]

    tot_q = sum(r["n_questions"] for r in sl)
    empty_q = sum(r["empty_requirement"] for r in sl)
    empty_aff = sorted((r for r in sl if r["empty_requirement"] > 0),
                       key=lambda r: (-r["empty_requirement"], r["slug"]))
    trunc_q = sum(r["truncated"] for r in recs)
    trunc_aff = sorted((r for r in recs if r["truncated"] > 0),
                       key=lambda r: (-r["truncated"], r["slug"]))
    cr_vol = [r for r in recs if r["has_cr"]]
    cr_top = sorted(cr_vol, key=lambda r: (-r["cr_n"], r["slug"]))[:10]
    img_sl = sum(r["img_markers"] for r in sl)
    img_all = sum(r["img_markers"] for r in recs)

    L = []
    L += ["# 验收 / 发布分级账（全量·机器算）", "",
          "> 机器生成（`tools/gwyzhenti/report_accept.py`）。逐 catalog 行、只算 `year >= %s` 的行；"
          "判据对**全量**成立，**不抽样**。" % since, ""]

    # ---- 一、口径声明 ----
    L += ["## 一、口径声明", "",
          "1. 本账为**机器校验**结果；全部判据对 `year >= %s` 的**全量** catalog 行成立。" % since,
          "2. **G1–G6 全部是「源 ↔ 导出」一致性判据，不证明与真实原卷一致**：G5 是源↔导出逐行多重集、"
          "G6 是 catalog↔落盘反向对账……六条里**没有一条**是「源 ↔ 原卷」。故 G1–G6 全绿"
          "**不等于**与真实原卷相称。",
          "3. **`t2` 不等于 `t3`**：`t2_幂等一致` 只证「交付 md 与 `work/manifest.jsonl` 幂等一致」"
          "（导出 ↔ 账本），**不**触及源、更**不**触及原卷；"
          "`t3_源内一致` = `gate` 的 G1–G5 实跑通过（**corpus 级**，非逐卷字段）。"
          "**本账不重算 G1–G5**，只引用其口径。", ""]

    # ---- 二、分级表 ----
    L += ["## 二、分级表（卷数）", "",
          "| 分级 | 卷数 | 口径 |", "|---|---:|---|",
          "| `t1_已转写` | %d | 交付 md 存在（路径由 `export.repo_paths` 给出） |" % t1,
          "| `t2_幂等一致` | %d | `t1` 且 manifest 同 path 的 sha256 == 盘上实际 sha256 |" % t2,
          "| `t3_源内一致` | — | **corpus 级，非逐卷**：见 `gate` 输出（G1–G5 实跑通过）。"
          "本账不重算。 |",
          "| `t4_原卷核验` | %d | 该 slug 在 `work/verify/records.jsonl` 有 ≥1 条 `verdict == \"ok\"` |" % t4,
          "| `t5_人工通读` | %d | 同上且记录 `human_read == True` |" % t5,
          "",
          "> 本账覆盖 `year >= %s` 的 catalog 行共 **%d**（其中申论 %d / 行测 %d）。" % (
              since, n, len(sl), n - len(sl)),
          "",
          "### `work/verify/records.jsonl` 字段契约（供后续核验线写入，一行一卷一条）", "",
          "```json",
          '{"slug": "国考-2025-申论-副省级", "verdict": "ok", "human_read": false,',
          ' "source_name": "<外部来源名；含外部内容时必填>", "source_url": "<URL>",',
          ' "fetched_on": "2026-10-09", "fields": "<被并入的字段/题号>"}',
          "```",
          "- `slug`：与 catalog 同名的卷标识（本账据此挂到具体卷）。",
          "- `verdict`：`\"ok\"` 表示该卷**原卷核验通过**；其余值视为未通过。",
          "- `human_read`：`true` 表示已**人工通读**。",
          "- 外部来源字段（`source_name`/`source_url`/`fetched_on`/`fields`）：仅当含外部来源内容时出现"
          "（R-A1：逐条记来源，不得匿名并入）。",
          "- `records.jsonl` **当前不存在** ⇒ `t4`/`t5` 现为 **0**（本账不新建该文件）。", ""]

    # ---- 三、缺陷账 ----
    L += ["## 三、缺陷账（全量）", "",
          "> 全部**实算**，不写死。", ""]

    pct = (100.0 * empty_q / tot_q) if tot_q else 0.0
    L += ["### 3.1 作答要求为空（**源缺**）", "",
          "- 全量：**%d 题 / %d 题**（占 %.1f%%），涉及 **%d 卷**。" % (
              empty_q, tot_q, pct, len(empty_aff)),
          "- 判据：源 `q` 去掉 `\\r` 后 `.strip()` 止于「要求：」或「要求:」 ⇒ 源本身止于"
          "「要求：」，**不是我方截断**。",
          "- 受影响卷清单（%d 卷，按空题数降序）：" % len(empty_aff), "",
          "| slug | 空题数/总题数 |", "|---|---:|"]
    for r in empty_aff:
        L.append("| %s | %d/%d |" % (r["slug"], r["empty_requirement"], r["n_questions"]))
    L.append("")

    L += ["### 3.2 材料截断（源内硬截断于 %d 字）" % shenlun.TRUNCATED_LEN, "",
          "- 全量：**%d 题**，涉及 **%d 卷**。" % (trunc_q, len(trunc_aff)),
          "- 判据：该卷里 `len(s) >= %d` 的题数。事实写在每卷 frontmatter 的「校验状态」里。" % (
              shenlun.TRUNCATED_LEN),
          "- 受影响卷前 15（按截断题数降序）：", "",
          "| slug | 截断题数/总题数 |", "|---|---:|"]
    for r in trunc_aff[:15]:
        L.append("| %s | %d/%d |" % (r["slug"], r["truncated"], r["n_questions"]))
    if len(trunc_aff) > 15:
        L.append("| … 其余 %d 卷（全量数见上） | — |" % (len(trunc_aff) - 15))
    L.append("")

    L += ["### 3.3 上游硬换行残留（`\\r` 未归一化，裁定 R-M3-11）", "",
          "- 含 `\\r` 的卷：**%d 卷**（判据：交付 md 字节里含 `\\r`）。" % len(cr_vol),
          "- **未归一化**：同一字节形态既出现在段界又出现在**词中间** ⇒ 任何按字节的规则都会同时判错一类 ⇒ "
          "归一化只能是猜。**本账不改任何 md 的 `\\r`。**",
          "- 受影响卷前 10（按 `\\r` 出现次数降序）：", "",
          "| slug | `\\r` 次数 |", "|---|---:|"]
    for r in cr_top:
        L.append("| %s | %d |" % (r["slug"], r["cr_n"]))
    L.append("")

    L += ["### 3.4 卷型不对称（`form_suspect`，**指示不是证明**）", "",
          "- 命中组：**%d 组**（同 `(level, region, year)` 下行测 distinct `ptype` ≥ 2 且申论 == 1）。"
          % len(suspects),
          "- **指示不是证明**：行测有三套**不蕴含**申论必然有三套；坐实须外部核对。",
          "- 命中组清单：", "",
          "| level | region | year | 行测卷型 | 申论卷型 |", "|---|---|---|---|---|"]
    for k in sorted(suspects):
        lv, rg, yr = k
        v = suspects[k]
        L.append("| %s | %s | %s | %s | %s |" % (
            lv, rg or "（国考）", yr, "、".join(v["行测"]), "、".join(v["申论"])))
    L.append("")

    L += ["### 3.5 图片标记（`<img` 与 `![` 次数之和）", "",
          "- 申论卷合计：**%d**（申论源无图 ⇒ 应为 0）。" % img_sl,
          "- 全卷合计（含行测，行测引用公式图/题目图）：**%d**。" % img_all, ""]

    # ---- 四、样本建议 ----
    L += ["## 四、验收样本建议（**缺陷密度最高**，非随机）", "",
          "> 按 `empty_requirement / n_questions` 降序（同比例按 `truncated` 降序）取前 10 卷。",
          "> **这是「缺陷密度最高」的抽样建议，不是随机抽样**；用于优先外部核对。", "",
          "| slug | 空题数/总题数 | 截断数 |", "|---|---:|---:|"]
    for r in _samples(recs, 10):
        L.append("| %s | %d/%d | %d |" % (
            r["slug"], r["empty_requirement"], r["n_questions"], r["truncated"]))
    L.append("")

    # ---- 五、诚实边界 ----
    L += ["## 五、未做的事（诚实边界）", "",
          "- **本账未做任何外部来源核对**：全部判据为机器对**本仓内**数据（catalog / 交付 md / "
          "manifest）的校验，**未**与真实原卷比对，**未**引入任何第三方来源。",
          "- **未人工通读**：`t5_人工通读` 现为 0；机器校验 ≠ 逐卷通读。",
          "- **未从 PDF 重转**：源为上游题级 JSON，非 PDF 重排。",
          "- **源本身把多卷型并成一键（源实证）**：如 `2025·国家公考` / `2025·浙江省公考` 在源 JSON 里"
          "各为一键（15 / 9 题）；行测源有卷型之分、申论源无 ⇒ `form_suspect` 的卷型不对称**在源里**，"
          "非我方导出时合并（零改写未破）。",
          "- **`form_suspect` 是「指示不是证明」**：同 `(level, region, year)` 下行测多卷型不蕴含申论多卷型"
          "（`新疆/兵团`、`四川/下半年`、`山西/县级` 这类很可能是误报）；坐实须外部核对。",
          "- `t4_原卷核验` / `t5_人工通读` 依赖 `work/verify/records.jsonl`，该文件**当前不存在** ⇒ 二者现为 0。",
          ""]
    return "\n".join(L)


def build(catalog_dir, uproots, repo_root, since):
    """→ (md_text, jsonl_records)。只读；不写任何文件。"""
    rows = export.load_catalog(catalog_dir)
    scope = [r for r in rows if r["year"] >= since]
    src = shenlun.load_source(uproots["linfukai186"])
    manifest = load_manifest(repo_root)
    verify = load_verify(repo_root)
    suspects = suspect_groups(scope)
    recs = [grade_row(r, src, manifest, verify, suspects, repo_root) for r in scope]
    return render_md(recs, suspects, since), recs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="report_accept")
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--since", default="2016")
    a = ap.parse_args(argv)
    uproots = {"xingcezhenti": os.path.join(a.upstream, "xingcezhenti"),
               "linfukai186": os.path.join(a.upstream, "gongkao-tiku")}
    md_txt, recs = build(a.catalog, uproots, a.repo, a.since)
    out_md = os.path.join(a.repo, "work", "ACCEPTANCE.md")
    out_jsonl = os.path.join(a.repo, "work", "ACCEPTANCE.jsonl")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with io.open(out_md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md_txt)
    lines = "".join(
        json.dumps({k: r[k] for k in JSONL_FIELDS}, ensure_ascii=False) + "\n" for r in recs)
    with io.open(out_jsonl, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lines)
    print("→", out_md, len(md_txt.encode("utf-8")), "字节")
    print("→", out_jsonl, len(lines.encode("utf-8")), "字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
