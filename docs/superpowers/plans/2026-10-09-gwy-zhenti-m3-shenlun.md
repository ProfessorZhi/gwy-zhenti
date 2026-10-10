# gwy-zhenti M3（申论导出）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把段一已 catalog 的 **576 份申论卷**（2016 年及以后 **468 份**）从 `linfukai186` 的题级 JSON 导出为成卷 Markdown，落进既有交付树 `省考/<省>/<年>/申论-<卷型>.md` 与 `国考/<年>/申论-<卷型>.md`，并通过 G1–G6 闸门。

**Architecture:** 复用 M1 两段式。**段一完全不动**（申论行已在 `catalog.jsonl` 里，见下方「为什么 M3 只做段二」）。M3 只新增一条**段二渲染路径**：`shenlun.py` 读题级 JSON → 渲染成卷 → 复用 `export`/`gates` 的写盘、图片、frontmatter 契约。**不改 `render.render_paper`**（它对 `zip(parts, modules)` 的依赖使申论无法复用，见「为什么不复用 `render_paper`」）。

**Tech Stack:** Python 3.12 标准库（`io`/`json`/`os`/`re`/`hashlib`/`shutil`/`unittest`）。

**Spec:** `docs/superpowers/specs/2026-10-09-gwy-zhenti-merge-design.md`（本计划从它论证；冲突以 spec 为准）

## Global Constraints

以下**逐条**约束每个任务（取自 spec 与本仓既有纪律，值照抄）：

- **零改写**：除 spec §6 五项机械变换（合并 / 题号重建 / 答案去泄露 / 图片重写 / frontmatter）外，**题干、材料、答案、解析一字不动**。spec §34。
- **不做 OCR / 不猜错字 / 不补知识内容 / 不答案投票**。spec §32、§35。
- **不从 PDF 重转**；历史 PDF 仅作争议题原件对照。spec §33。
- **不并入非国省考**（选调 / 法检 / 司法所 / 事业编 / 职测 / 综应 / 模考 / 公开课）。spec §36。
- **2016 年及以后**为本次导出范围（spec §19 与 M1 同界）。
- **不改 `work/mirror/`；不覆盖 `knowledge/`；不自动推送**。
- **分支 `feat/m1-merge`，本计划全程 local commit，绝不 push**（用户已批准此分支的本地提交）。
- **D 盘纪律**：不做 `find` / 递归 `grep` / `Glob`；不做 `du -sh`；长 Python 一律**写进文件**再跑（禁 heredoc）；一律 `PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8`。
- **测试命令**：`cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest discover -s tests`
- **出口命令**：`cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m gwyzhenti.cli export --catalog ../work/catalog --upstream D:/projects/_gwy-upstream --repo .. --since 2016`
- **交付树 `国考/ 省考/ 图片/` 被 `.gitignore`**：`git status` 里看不到它们是**预期**（M1 的 I4 修复），不是缺陷。
- 提交信息以 `Co-Authored-By: Claude Code <noreply@anthropic.com>` 结尾。

---

## 为什么 M3 只做段二（已实测，非推测）

| 事实 | 证据 |
|---|---|
| `work/catalog/catalog.jsonl` 已有 **576 行 `subject="申论"`**，全来自 `linfukai186` | `Counter(r['subject'])` = `{'行测': 685, '申论': 576}` |
| 申论行的 `模块` 字段装的**就是题型计数**（`{"公文写作题":1,"单一题":1}`） | 段一已把 `t`（题型）当 module 归一 |
| 汇总键已按 `ptype="统考"` 归一：`2010·国家公考` → slug `国考-2010-申论-统考` | catalog 实读 |
| 27 行的 `titles["linfukai186"]` **有 2 个卷名**（汇总键与分卷键撞 slug 已合并） | 例 `省考-北京-2015-申论-统考` = `['2015·北京市公考','2015·北京市公考《申论》题']` |
| **合并行的 `n_questions` == 各标题题数之和**，576/576 全对 | 实算 |
| 所有 576 行的每个标题都能在源里定位 | 实算 |
| 申论 **2016+ = 468 行 / 2299 题**；`<2016 = 108 行` | 实算 |
| `unparsed.jsonl` / `unmapped.jsonl` 均 **0 行** | 段一无遗漏 |

⇒ **M3 不新增 adapter、不改 `catalog.py`、不重跑段一**（spec §115 亦如此要求）。

## 源的真实形态（实测，决定渲染设计）

- 源 = `D:\projects\_gwy-upstream\gongkao-tiku\data\{shengkao,guokao}-shenlun\{index.json, y<年>.json}`。
- `y<年>.json` 是 **`{卷标识: [题, ...]}`**；`index.json` 是 `[{key, count}]`，`count` == 该卷题数（637 卷**全对**）。
- 每题的字段**恒为** `{t, s, q, a, e, source}`；`t` = **题型**（`单一题`/`综合题`/`公文写作题`/`文章写作题`），不是行测模块。
- **`a` 恒为空串**；申论范文/解析在 **`e`**。
- **`s` 是「该题相关的材料子集」**（实例：同一卷内 `[0] 材料1-8 / 6000 字`、`[2] 只有材料1 / 1733 字`），**不是**一份共享的整卷给定资料。
- **`s` 在 6000 字处被源硬截断**：613/2703 题恰为 6000 字，最大就是 6000（23% 的题受影响）——**必须如实标注**。
- **0 / 2703 题含图片标记** ⇒ 此源无图可丢，`图片/` 树不新增申论图。
- `guokao-shenlun` 实为 **0 真卷**（59 键全含「模考」），但国考申论键（`2010·国家公考《申论》题（副省级）` 等 46 行）**存放在 `shengkao-shenlun`** ⇒ 读取器需**同时**扫两个类目。

## 为什么不复用 `render.render_paper`

`render.py:82` 是 `for part, module in zip(parts, modules)`。申论无「模块」概念 ⇒ `modules=[]` 时 **zip 零轮、正文为空**。改它的循环会牵动行测已验收的 427 卷输出（G5 逐行比对会红）。故 M3 **另写** `shenlun.render_paper`，只**复用**它的三个无状态部件：

- `render._frontmatter(key, nature, form, sources, numbering)` —— frontmatter 契约（含 `题号口径`/`校验状态`）
- `render.key_label(key)` —— H1 标题
- `render.RenderedPaper` —— 返回值形状

## 关键裁定（Rulings，随计划生效）

| # | 裁定 | 理由 | 若错的代价 |
|---|---|---|---|
| **R-M3-1** | 申论答案板块沿用**同一串** `## 答案与解析`，不另起名 | `gates._g3` 硬要这一串；沿用 ⇒ G3 **零分支**、行测不扰动 | 板块名略不贴「范文」语义；改一行即可 |
| **R-M3-2** | **不做材料去重**（同一卷内 `s` 相同也不合并） | spec §34 零改写；「材料去重」是 spec §6 **没有**的第 6 项变换，不得擅自加 | 部分 md 偏长（仅 98/637 卷的 `s` 全同，影响面小） |
| **R-M3-3** | 交付 **2016+**；`--since 2016` **统一**作用于行测与申论 | 行测 427 行**全部 ≥2016（零例外）** ⇒ 对行测输出**逐字节无扰动**（可证） | 108 份 2010–2015 申论暂不导出；`--since 2010` 一条命令即补 |
| **R-M3-4** | G1/G3 **复用**；G2 反向在无图卷上**自然空过**；**G5/G6 必须加申论分支** | G5 现走 `_parts_for`（md 模块）⇒ 申论恒红；G6 用 `_parts_for` 判「可导出」⇒ 申论会被算成 0 卷而**假红** | 若不做分支：G5 **假红**、G6 **假红**，把真缺陷埋掉 |
| **R-M3-5** | 材料截断事实写进 **frontmatter 的 `校验状态`**，**不往正文加任何提示行** | 正文加行 = 第 6 项变换（违 §34）；frontmatter 本就是机器生成的**第 5 项变换** | 读者需读 frontmatter 才知道截断；报告里另有汇总 |
| **R-M3-7**（**控制器扩容**） | `source_lines` 与 `strip_structure` **共用同一个过滤谓词** —— 抽出 `shenlun._keep_line(ln)`，两侧都过它。谓词剔除：**① 空白行**（`not ln.strip()`）、② 我们声明的结构行（`STRUCT`）、③ `# ` / `> ` 开头的行 | **不是理论风险，是实测假红面。** 控制器全量扫 468 卷：现状下**有差异的卷 = 460/468**（源行 220,470），差异行**全部**是空白行（例 `''`、`'\r\r'`），`缺 N 行 / 多 0 行` —— 根因是 `strip_structure` 剔空白行而 `source_lines` 不剔 ⇒ **不对称** ⇒ G5 一跑就假红 460 卷。**控制器证伪实验**：两侧都剔空白行后，**468/468 卷零差异**（源里空白行共 6,763 行，非空 213,707 行）。三处谓词在源侧的命中数分别实测为：空白 6,763 / `# `·`> `·`STRUCT` **0**（373,956 行中 0 条） | 空白行不承载内容 ⇒ 谓词对空白行是**安全的**；对 `# `/`> `/`STRUCT` 行源侧命中 0 ⇒ 无实际盲区。若错，代价是 G5 少判一类行 —— 而这类行在源里根本不存在 |

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `tools/gwyzhenti/shenlun.py` | **新建** | 申论源读取（跨两类目）+ 成卷渲染 + 保真用的行提取/结构剔除 |
| `tools/gwyzhenti/export.py` | 修改 | `run()` 加申论分支；新增 `exportable_map()`；`--since` 过滤；`_shenlun_titles()` |
| `tools/gwyzhenti/cli.py` | 修改 | `export`/`gate` 加 `--since`；打印申论计数 |
| `tools/gwyzhenti/gates.py` | 修改 | G5/G6 加申论分支（G1/G2/G3/G4 不动） |
| `tools/tests/test_shenlun.py` | **新建** | `shenlun.py` 单测（合成 + 真源冒烟） |
| `tools/tests/test_export_shenlun.py` | **新建** | 导出申论分支 + manifest + 幂等（在临时小仓上跑） |
| `tools/tests/test_gates.py` | 修改 | 加「G5/G6 申论分支**能红**」的回归 |
| `tools/gwyzhenti/report_m3.py` | **新建** | 只读：catalog + 交付树 → `work/M3-REPORT.md` |

---

### Task 1: `shenlun.py` —— 源读取 + 成卷渲染

**Files:**
- Create: `tools/gwyzhenti/shenlun.py`
- Test: `tools/tests/test_shenlun.py`

**Interfaces:**
- Consumes: `render._frontmatter(key, nature, form, sources, numbering)`、`render.key_label(key)`、`render.RenderedPaper(body, images_used, n_questions, numbering)`、`model.PaperKey`
- Produces（Task 2/3 依赖，签名与返回类型即契约）：
  - `CATS: tuple[str, ...]`
  - `NUMBERING: str`
  - `load_source(uproot: str) -> dict[str, list[dict]]`
  - `titles_of(row: dict) -> list[str]`
  - `questions_for_titles(src: dict, titles: list[str]) -> list[dict]`
  - `render_paper(questions: list[dict], key: PaperKey, *, nature: str, form: str, sources: list[str]) -> render.RenderedPaper`
  - `source_lines(questions: list[dict]) -> list[str]`
  - `_keep_line(ln: str) -> bool`（两侧共用的过滤谓词，裁定 R-M3-7）
  - `STRUCT: re.Pattern`、`strip_structure(text: str) -> list[str]`

- [ ] **Step 1: 写失败测试**

创建 `tools/tests/test_shenlun.py`：

```python
# -*- coding: utf-8 -*-
import io
import json
import os
import tempfile
import unittest

from gwyzhenti import shenlun
from gwyzhenti.model import PaperKey


def _q(t, s, q, e, a="", source="公开资料整理"):
    return {"t": t, "s": s, "q": q, "a": a, "e": e, "source": source}


class TestLoadSource(unittest.TestCase):
    def test_merges_both_categories_and_keeps_source_order(self):
        with tempfile.TemporaryDirectory() as d:
            data = os.path.join(d, "data")
            for cat in shenlun.CATS:
                os.makedirs(os.path.join(data, cat))
            with io.open(os.path.join(data, "shengkao-shenlun", "y2019.json"),
                         "w", encoding="utf-8") as fh:
                json.dump({"2019·甲省《申论》题": [_q("单一题", "材料甲", "题干甲", "范文甲")]},
                          fh, ensure_ascii=False)
            with io.open(os.path.join(data, "guokao-shenlun", "y2019.json"),
                         "w", encoding="utf-8") as fh:
                json.dump({"2019·国家公考《申论》题（副省级）":
                           [_q("综合题", "材料乙", "题干乙", "范文乙")]}, fh, ensure_ascii=False)
            src = shenlun.load_source(d)
        self.assertEqual(set(src), {"2019·甲省《申论》题", "2019·国家公考《申论》题（副省级）"})
        self.assertEqual(len(src["2019·甲省《申论》题"]), 1)

    def test_missing_dir_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "data", "shengkao-shenlun"))
            src = shenlun.load_source(d)
        self.assertEqual(src, {})


class TestQuestionsForTitles(unittest.TestCase):
    def test_concatenates_in_title_order(self):
        src = {"A": [_q("单一题", "sA", "qA", "eA")], "B": [_q("综合题", "sB", "qB", "eB")]}
        got = shenlun.questions_for_titles(src, ["A", "B"])
        self.assertEqual([q["q"] for q in got], ["qA", "qB"])

    def test_missing_title_is_skipped_not_fatal(self):
        src = {"A": [_q("单一题", "sA", "qA", "eA")]}
        self.assertEqual(len(shenlun.questions_for_titles(src, ["A", "NOPE"])), 1)

    def test_titles_of_reads_linfukai186_key(self):
        row = {"titles": {"linfukai186": ["X", "Y"]}}
        self.assertEqual(shenlun.titles_of(row), ["X", "Y"])


class TestRenderPaper(unittest.TestCase):
    def _render(self, qs):
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        return shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                    sources=["linfukai186"])

    def test_body_layout_and_answer_folding(self):
        out = self._render([_q("单一题", "材料一\n第二行", "请概括。\n要求：准确。", "参考要点：\n一、……")])
        b = out.body
        self.assertIn("# 2019 山东省公务员录用考试 申论（统考）", b)
        self.assertIn("> 申论 · 1 题 · 山东 2019", b)
        self.assertIn("## 第 1 题（单一题）", b)
        self.assertIn("### 给定材料", b)
        self.assertIn("材料一\n第二行", b)
        self.assertIn("### 作答要求", b)
        self.assertIn("## 答案与解析", b)
        self.assertIn("<details>", b)
        self.assertIn("<summary>第 1 题</summary>", b)
        self.assertIn("参考要点：\n一、……", b)
        self.assertEqual(out.n_questions, 1)

    def test_empty_material_section_is_omitted(self):
        out = self._render([_q("单一题", "", "只有题干", "范文")])
        self.assertNotIn("### 给定材料", out.body)
        self.assertIn("### 作答要求", out.body)

    def test_numbering_is_declared_honestly(self):
        out = self._render([_q("单一题", "s", "q", "e")])
        self.assertEqual(out.numbering, shenlun.NUMBERING)
        self.assertIn('题号口径: "源无卷内题号，按源序编号"', out.body)

    def test_no_images(self):
        out = self._render([_q("单一题", "s", "q", "e")])
        self.assertEqual(out.images_used, [])

    def test_question_count_matches(self):
        out = self._render([_q("单一题", "s", "q", "e")] * 3)
        self.assertEqual(out.n_questions, 3)
        self.assertEqual(out.body.count("## 第 "), 3)

    def test_truncation_is_declared_in_frontmatter_only(self):
        long_s = "字" * 6000
        out = self._render([_q("单一题", long_s, "q", "e")])
        self.assertIn("材料截断 1 题", out.body.split("---")[1])
        # 正文里不得新增任何提示行
        self.assertNotIn("截断", out.body.split("---")[2])


class TestSourceLinesRoundTrip(unittest.TestCase):
    def test_strip_structure_leaves_only_source_lines(self):
        qs = [_q("单一题", "材料一\n第二行", "请概括。", "范文行")]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        out = shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                   sources=["linfukai186"])
        got = shenlun.strip_structure(out.body)
        want = shenlun.source_lines(qs)
        self.assertEqual(sorted(got), sorted(want))
        self.assertEqual(sorted(want), sorted(["材料一", "第二行", "请概括。", "范文行"]))

    def test_blank_and_cr_lines_do_not_break_the_pair(self):
        """R-M3-7 回归：源里的空白行 / `\\r` 行 / 尾随换行不得让两侧不等。

        真数据背景（控制器全量扫 468 卷）：现状下 **460/468 卷**两侧不等，
        差异行**全是**空白行（例 `''`、`'\\r\\r'`）；两侧共用谓词后 **468/468 卷零差异**。
        """
        qs = [_q("单一题", "材料一\n\n\n材料二", "请概括。", "范文一\n"),
              _q("单一题", "材料三\r\r\n\r\r\n材料四", "q2", "e2")]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        out = shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                   sources=["linfukai186"])
        self.assertEqual(sorted(shenlun.strip_structure(out.body)),
                         sorted(shenlun.source_lines(qs)))
        self.assertNotIn("", shenlun.source_lines(qs))
        self.assertNotIn("\r\r", shenlun.source_lines(qs))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest tests.test_shenlun`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.shenlun'`

- [ ] **Step 3: 实现 `shenlun.py`**

创建 `tools/gwyzhenti/shenlun.py`：

```python
# -*- coding: utf-8 -*-
"""申论源（linfukai186 题级 JSON）读取 + 成卷渲染。

与行测的差别（实测，见 M3 计划「源的真实形态」）：
  * 无「模块」概念 ⇒ 不能走 `render.render_paper`（它按 `zip(parts, modules)` 驱动，申论会零轮空转）。
  * 每题自带 `s`（该题相关材料子集），**不是**整卷共享的给定资料 ⇒ **按题原样排**，不做合并（裁定 R-M3-2）。
  * `a` 恒为空串，范文/解析在 `e`。
  * `s` 在源内被硬截断于 6000 字 ⇒ 事实写进 frontmatter 的 `校验状态`，**不往正文加提示行**（裁定 R-M3-5）。
  * 源无卷内题号 ⇒ 按源序编号，口径如实声明。
本模块**只读源、只造字符串**，不写盘。
"""
import io
import json
import os
import re

from . import render
from .model import PaperKey

CATS = ("shengkao-shenlun", "guokao-shenlun")
NUMBERING = "源无卷内题号，按源序编号"
TRUNCATED_LEN = 6000
# 我们**声明过**要新增的结构行 —— 保真判据（G5）在两侧都剔除它们。
STRUCT = re.compile(
    r"^\s*(?:---|#{2,4}\s*第\s*\d+\s*题.*|###\s*(?:给定材料|作答要求)"
    r"|##\s*答案与解析|<details>|</details>|<summary>.*</summary>)\s*$")
FM_BLOCK = re.compile(r"\A(?:---\n.*?\n---\n)", re.S)


def load_source(uproot):
    """→ {卷标识: [题, ...]}，同时扫 `shengkao-shenlun` 与 `guokao-shenlun`。

    目录不存在 ⇒ 跳过（不抛）。同一年两文件不冲突（题在各自类目的 `y<年>.json` 里）。
    """
    out = {}
    for cat in CATS:
        d = os.path.join(uproot, "data", cat)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not (fn.startswith("y") and fn.endswith(".json")):
                continue
            with io.open(os.path.join(d, fn), encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for title, qs in data.items():
                    if isinstance(qs, list):
                        out[title] = qs
    return out


def titles_of(row):
    """该卷在 linfukai186 源里的卷名（保序）。空 = 该源没有此卷。"""
    return list(row.get("titles", {}).get("linfukai186", []))


def questions_for_titles(src, titles):
    """按 titles 顺序拼接各卷名的题；标题在源里找不到 ⇒ 跳过该标题（不抛）。"""
    out = []
    for t in titles:
        qs = src.get(t)
        if isinstance(qs, list):
            out.extend(qs)
    return out


def _lines(v):
    return (v or "").split("\n")


def render_paper(questions, key, *, nature, form, sources):
    """把题列表渲染成一卷 Markdown。逐字节保真的只有材料的文本行本身（§6 五项之外零改写）。"""
    n_trunc = sum(1 for q in questions if len(q.get("s") or "") >= TRUNCATED_LEN)
    status = ("机器校验（并卷/题号/去泄露/G1–G5）；未人工通读"
              "；材料截断 %d 题（源内硬截断于 %d 字）" % (n_trunc, TRUNCATED_LEN))
    head = render._frontmatter(key, nature, form, sources, NUMBERING)
    head = [ln if not ln.startswith('校验状态:') else '校验状态: "%s"' % status for ln in head]

    body = head + [""]
    body += ["# %s" % render.key_label(key), ""]
    body += ["> %s · %d 题 · %s %s" % (key.subject, len(questions),
                                     key.region or key.level, key.year), ""]
    for i, q in enumerate(questions, 1):
        t = (q.get("t") or "").strip()
        body += ["## 第 %d 题%s" % (i, "（%s）" % t if t else ""), ""]
        s = q.get("s") or ""
        if s:
            body += ["### 给定材料", ""] + _lines(s) + [""]
        body += ["### 作答要求", ""] + _lines(q.get("q")) + [""]
    body += ["## 答案与解析", ""]
    for i, q in enumerate(questions, 1):
        body += ["<details>", "<summary>第 %d 题</summary>" % i, ""]
        for f in ("a", "e"):
            v = q.get(f) or ""
            if v:
                body += _lines(v) + [""]
        body += ["</details>", ""]
    text = "\n".join(body)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    return render.RenderedPaper(text, [], len(questions), NUMBERING)


def _keep_line(ln):
    """保真判据**两侧共用**的过滤谓词：空白行与结构行都不算「内容行」。

    为什么必须共用（裁定 R-M3-7）：`strip_structure` 原本剔空白行而 `source_lines` 不剔
    ⇒ 不对称。控制器全量实测：不对称让 G5 在 **460/468 卷**上假红（差异行全是
    `''` / `'\\r\\r'`）；两侧都过本谓词后 **468/468 卷零差异**。
    谓词对空白行安全（不承载内容）；对 `# `/`> `/`STRUCT` 行在源侧命中数为 **0**
    （373,956 行中 0 条）。
    """
    if not ln.strip():
        return False
    if ln.startswith("# ") or ln.startswith("> "):
        return False
    return not STRUCT.match(ln)


def source_lines(questions):
    """保真判据的**源侧**行：只有 s/q/a/e 的文本行（空字段不计），过了共用谓词。"""
    out = []
    for q in questions:
        for f in ("s", "q", "a", "e"):
            v = q.get(f) or ""
            if v:
                out += [ln for ln in _lines(v) if _keep_line(ln)]
    return out


def strip_structure(text):
    """保真判据的**导出侧**行：先剔 frontmatter 块，其余过共用谓词。"""
    text = FM_BLOCK.sub("", text)
    return [ln for ln in text.split("\n") if _keep_line(ln)]
```

> 注意 `render._frontmatter` 的第 9 行格式是 `'校验状态: "%s"' % ...`，故 Step 3 的替换按 `startswith('校验状态:')` 定位；若实测该串不符，以 `render.py:68` 的真实行为为准并在报告里写明。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest tests.test_shenlun -v`
Expected: PASS（全部）

- [ ] **Step 5: 真源冒烟（只读，不写盘）**

把下面脚本写进 `tools/tests/smoke_m3_shenlun.py` 并跑：

```python
# -*- coding: utf-8 -*-
"""真源只读冒烟：抽 3 卷渲染，断言题数与源一致、且源行全在导出里。"""
import json
import os

from gwyzhenti import shenlun
from gwyzhenti.model import PaperKey

UP = r"D:\projects\_gwy-upstream\gongkao-tiku"
CAT = r"D:\projects\gwy-zhenti\work\catalog\catalog.jsonl"

src = shenlun.load_source(UP)
rows = [json.loads(l) for l in open(CAT, encoding="utf-8") if l.strip()]
sl = [r for r in rows if r["subject"] == "申论" and r["year"] >= "2016"]
print("源卷数", len(src), "| 2016+ 申论行", len(sl))
for r in sl[:3]:
    qs = shenlun.questions_for_titles(src, shenlun.titles_of(r))
    key = PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"])
    out = shenlun.render_paper(qs, key, nature=r["nature"], form=r["form"], sources=r["sources"])
    missing = [x for x in shenlun.source_lines(qs) if x not in out.body]
    print(" %-34s 题 %2d/%2d | 源行缺失 %d | md %d 字节"
          % (r["slug"], out.n_questions, r["n_questions"], len(missing), len(out.body.encode("utf-8"))))
```

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 tests/smoke_m3_shenlun.py`
Expected: 源卷数 ≥ 637；三卷 `题 N/N` 相等、`源行缺失 0`。

- [ ] **Step 6: Commit**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/shenlun.py tools/tests/test_shenlun.py tools/tests/smoke_m3_shenlun.py
git commit -m "feat(m3): 申论源读取与成卷渲染（shenlun.py）

为何：M1 只导出有 xingcezhenti 正文的行，申论 576 卷（2016+ 468 卷）整片 0 交付。
改了什么：新增 tools/gwyzhenti/shenlun.py（跨两类目读题级 JSON、按源序成卷渲染、
截断事实入 frontmatter 校验状态）+ 单测 + 真源只读冒烟。
核实：unittest tests.test_shenlun 全绿；真源冒烟三卷题数与源一致、源行零缺失。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 段二导出申论分支 + `--since`

**Files:**
- Modify: `tools/gwyzhenti/export.py`
- Modify: `tools/gwyzhenti/cli.py`
- Test: `tools/tests/test_export_shenlun.py`

**Interfaces:**
- Consumes: Task 1 的 `shenlun.load_source` / `titles_of` / `questions_for_titles` / `render_paper`
- Produces:
  - `export._shenlun_titles(row) -> list[str]`
  - `export.exportable_map(rows, uproots) -> dict[str, bool]`（键 = `row["slug"]`；申论源**只加载一次**）
  - `export.run(catalog_dir, uproots, repo_root, limit=None, since=None)`
  - `cli` 的 **`export`** 子命令新增 `--since`（默认 `""` = 不过滤）。
    ⚠️ **本任务不动 `gate` 子命令** —— 裁定 R-M3-6：`gate --since` 与 `cmd_gate` 接线**同批挪进 Task 3 Step 3c**，
    否则本任务的提交里 `TestGateSubcommand` 会因 `gates.run_all` 尚不接受 `since` 而 TypeError 红。

- [ ] **Step 1: 写失败测试**

创建 `tools/tests/test_export_shenlun.py`：

```python
# -*- coding: utf-8 -*-
import io
import json
import os
import tempfile
import unittest

from gwyzhenti import export


def _mk(up, rows, body='{"t":"单一题","s":"材料","q":"题干","a":"","e":"范文","source":"x"}'):
    """建一个最小上游：gongkao-tiku/data/shengkao-shenlun/y2019.json + xingcezhenti/。

    注意 `body` 必须是 **str**。写成 `b'...'` 会在 Python 3 里直接 **SyntaxError**
    （bytes 字面量只能放 ASCII，这里的「单一题/材料/题干/范文」都是中文）。
    """
    d = os.path.join(up, "gongkao-tiku", "data", "shengkao-shenlun")
    os.makedirs(d)
    q = json.loads(body)
    with io.open(os.path.join(d, "y2019.json"), "w", encoding="utf-8") as fh:
        json.dump({r["titles"]["linfukai186"][0]: [q] if r["n_questions"] else [] for r in rows},
                  fh, ensure_ascii=False)
    os.makedirs(os.path.join(up, "xingcezhenti"))
    cat = os.path.join(up, "catalog")
    os.makedirs(cat)
    with io.open(os.path.join(cat, "catalog.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return cat


def _row(year="2019", n=1, slug="省考-山东-2019-申论-统考", title="2019·山东省公考《申论》题"):
    return {"slug": slug, "level": "省考", "region": "山东", "year": year, "subject": "申论",
            "ptype": "统考", "nature": "正式真题", "form": "单独命题",
            "sources": ["linfukai186"], "n_questions": n,
            "titles": {"linfukai186": [title]}}


class TestExportShenlun(unittest.TestCase):
    def test_writes_md_and_manifest(self):
        with tempfile.TemporaryDirectory() as up, tempfile.TemporaryDirectory() as repo:
            cat = _mk(up, [_row()])
            uproots = {"linfukai186": os.path.join(up, "gongkao-tiku"),
                       "xingcezhenti": os.path.join(up, "xingcezhenti")}
            rep = export.run(cat, uproots, repo, since="2016")
            md = os.path.join(repo, "省考", "山东", "2019", "申论-统考.md")
            self.assertTrue(os.path.exists(md))
            self.assertEqual(rep.files, 1)
            text = io.open(md, encoding="utf-8").read()
            self.assertIn("## 第 1 题（单一题）", text)
            man = os.path.join(repo, "work", "manifest.jsonl")
            self.assertTrue(os.path.exists(man))
            self.assertEqual(len([l for l in io.open(man, encoding="utf-8") if l.strip()]), 1)

    def test_since_filters_old_shenlun(self):
        with tempfile.TemporaryDirectory() as up, tempfile.TemporaryDirectory() as repo:
            cat = _mk(up, [_row(year="2015", slug="省考-北京-2015-申论-统考",
                                title="2015·北京市公考")])
            uproots = {"linfukai186": os.path.join(up, "gongkao-tiku"),
                       "xingcezhenti": os.path.join(up, "xingcezhenti")}
            rep = export.run(cat, uproots, repo, since="2016")
            self.assertEqual(rep.files, 0)
            self.assertTrue(any("since" in s.get("reason", "") for s in rep.skipped))

    def test_exportable_map_counts_shenlun(self):
        with tempfile.TemporaryDirectory() as up:
            cat = _mk(up, [_row(), _row(year="2015", slug="省考-北京-2015-申论-统考",
                                        title="2015·北京市公考")])
            uproots = {"linfukai186": os.path.join(up, "gongkao-tiku"),
                       "xingcezhenti": os.path.join(up, "xingcezhenti")}
            m = export.exportable_map(export.load_catalog(cat), uproots)
            self.assertEqual(m["省考-山东-2019-申论-统考"], True)
            self.assertEqual(len(m), 2)

    def test_idempotent_sha(self):
        with tempfile.TemporaryDirectory() as up, tempfile.TemporaryDirectory() as repo:
            cat = _mk(up, [_row()])
            uproots = {"linfukai186": os.path.join(up, "gongkao-tiku"),
                       "xingcezhenti": os.path.join(up, "xingcezhenti")}
            export.run(cat, uproots, repo, since="2016")
            md = os.path.join(repo, "省考", "山东", "2019", "申论-统考.md")
            a = open(md, "rb").read()
            export.run(cat, uproots, repo, since="2016")
            self.assertEqual(a, open(md, "rb").read())


if __name__ == "__main__":
    unittest.main()
```

> 注：`_mk` 的 `uproots` 里键名以 `cli._uproots` 为准（`xingcezhenti` + `linfukai186`）。写实现时若发现冗余键（上面样例中重复的 `"gongkao-tiku"`/`"xingcezhenti"`），**删掉多余键**，只留 `cli._uproots` 产出的两个。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest tests.test_export_shenlun`
Expected: FAIL —— `TypeError: run() got an unexpected keyword argument 'since'`

- [ ] **Step 3: 改 `export.py`**

在 `export.py` 顶部 import 区加 `from . import mdread, render, shenlun`（替换原 `from . import mdread, render`）。

在 `_parts_for` 之后新增：

```python
def _shenlun_titles(row):
    """该卷在 **linfukai186 源**里的卷名（保序）。空 = 该源没有此卷。

    不能拿 `row["title"]` 当源键：与 `_xingce_titles` 同理（R-T8-1）。
    合并行会有**多个**卷名（汇总键 + 分卷键撞 slug），必须**全部**取，否则丢题。
    """
    return shenlun.titles_of(row)


def _shenlun_questions(row, src):
    return shenlun.questions_for_titles(src, _shenlun_titles(row))


def exportable_map(rows, uproots):
    """→ {slug: 该卷在源里是否取得到正文}。**申论源只加载一次**（否则 O(卷×年文件)）。

    行测沿用 `_parts_for`（与 M1 完全一致）；申论用 `shenlun.load_source`。

    键用 `.get(..., "")` 而**不是** `uproots["linfukai186"]`：`export.run` 的调用方不保证给这个键
    （`test_export.py` / `test_gates.py` 里 22 条既有测试故意只传 `xingcezhenti`），硬下标会 KeyError。
    `.get` 缺键 → `""` → `load_source` 找不到目录 → `{}` → 申论卷判为不可导出（**不会**误判成可导出）。
    """
    src = shenlun.load_source(uproots.get("linfukai186", ""))
    out = {}
    for row in rows:
        if row["subject"] == "申论":
            out[row["slug"]] = bool(_shenlun_questions(row, src))
        else:
            parts, _ = _parts_for(row, uproots["xingcezhenti"])
            out[row["slug"]] = bool(parts)
    return out
```

改 `run` 签名为 `def run(catalog_dir, uproots, repo_root, limit=None, since=None):`，并在 `rows = load_catalog(...)` 之后加申论源加载与 `--since` 归一：

```python
    rows = load_catalog(catalog_dir)
    if limit:
        rows = rows[:limit]
    shenlun_src = shenlun.load_source(uproots.get("linfukai186", ""))
    entries = []
```

把原循环体开头（`for row in rows:` 之后第一句）改为申论先行分支 —— **在** `if "xingcezhenti" not in row["sources"]` **之前**插入：

```python
    for row in rows:
        if since and row["year"] < since:
            rep.skipped.append({"slug": row["slug"], "reason": "早于 since=%s" % since})
            continue
        if row["subject"] == "申论":
            qs = _shenlun_questions(row, shenlun_src)
            if not qs:
                rep.skipped.append({"slug": row["slug"], "reason": "申论上游题缺失"})
                continue
            key = PaperKey(row["level"], row["region"], row["year"], row["subject"], row["ptype"])
            md_rel, _ = repo_paths(key, row["slug"])
            out = shenlun.render_paper(qs, key, nature=row["nature"], form=row["form"],
                                       sources=row["sources"])
            data = out.body.encode("utf-8")
            _write(os.path.join(repo_root, md_rel), data)
            rep.files += 1
            entries.append({"path": md_rel.replace("\\", "/"), "sha256": _sha256_bytes(data)})
            rep.papers += 1
            continue
        if "xingcezhenti" not in row["sources"]:
            rep.skipped.append({"slug": row["slug"], "reason": "本批只导出有正文的源"})
            continue
```

> **行测路径逐字节不变**：`--since 2016` 下，行测 427 行全部 `year >= 2016`（catalog 实测 `<2016 = 0`），故对行测**零扰动**；其余代码未动。这不靠「看起来对」，而由 Task 2 Step 5 的 sha 对账证明。

- [ ] **Step 4: 改 `cli.py`**

`cmd_export` 改成把 `since` 传下去并打印申论计数：

```python
def cmd_export(args):
    from . import export
    rep = export.run(args.catalog, _uproots(args), args.repo,
                     limit=args.limit, since=(args.since or None))
    print("段二完成 →", args.repo)
    print("  卷 %d | md %d | 图片 %d" % (rep.papers, rep.files, rep.images))
    if rep.skipped:
        print("  跳过 %d 项（详见报告）" % len(rep.skipped))
    if rep.collided:
        print("  撞 slug 未导的卷名 %d 条（详见报告）" % len(rep.collided))
    return 0
```

`export` 子命令加一个参数（放在 `--limit` 之后）：

```python
    e.add_argument("--since", default="", help="只导出该年及以后（如 2016）；空 = 不过滤")
```

> **`cmd_gate` 与 `gate` 子命令的 `--since` 本任务**不动 —— `gates.run_all` 的 `since` 参数由 **Task 3** 一并加（否则本提交里 `cmd_gate` 会传一个尚不存在的参数而 `TypeError`，`tests/test_cli.py::TestGateSubcommand` 立刻红。裁定 **R-M3-6**：接线两侧同任务落地）。

- [ ] **Step 5: 先跑单测，再对**真库**做行测 sha 对账**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest tests.test_export_shenlun -v`
Expected: PASS

**对账（先存 427 卷的 sha，再重跑，再比）**：

```bash
cd D:/projects/gwy-zhenti
PYTHONIOENCODING=utf-8 python -X utf8 -c "
import io,os,hashlib,json
h={}
for dp,_,fns in os.walk('省考'):
    for f in fns:
        if f.endswith('.md'):
            p=os.path.join(dp,f); h[p.replace(os.sep,'/')]=hashlib.sha256(open(p,'rb').read()).hexdigest()
for dp,_,fns in os.walk('国考'):
    for f in fns:
        if f.endswith('.md'):
            p=os.path.join(dp,f); h[p.replace(os.sep,'/')]=hashlib.sha256(open(p,'rb').read()).hexdigest()
json.dump(h, open('work/_pre_m3_sha.json','w'), ensure_ascii=False, indent=0)
print('行测基线 md 数', len(h))
"
```
再跑导出：
```bash
cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m gwyzhenti.cli export --catalog ../work/catalog --upstream D:/projects/_gwy-upstream --repo .. --since 2016
```
再比对：
```bash
cd D:/projects/gwy-zhenti && PYTHONIOENCODING=utf-8 python -X utf8 -c "
import json,hashlib,os
pre=json.load(open('work/_pre_m3_sha.json'))
bad=[p for p,s in pre.items() if hashlib.sha256(open(p,'rb').read()).hexdigest()!=s]
print('行测 md 数变化后仍逐字节相同?', not bad, '| 变化', bad[:5])
n=0
for dp,_,fns in os.walk('省考'):
    n+=sum(1 for f in fns if f.endswith('.md'))
for dp,_,fns in os.walk('国考'):
    n+=sum(1 for f in fns if f.endswith('.md'))
print('交付树 md 总数', n)
print('manifest 行数', sum(1 for l in open('work/manifest.jsonl',encoding='utf-8') if l.strip()))
"
```
Expected: 行测 427 卷**逐字节不变**；md 总数 **427 + 468 = 895**；manifest **895** 行。

- [ ] **Step 6: Commit**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/export.py tools/gwyzhenti/cli.py tools/tests/test_export_shenlun.py
git commit -m "feat(m3): 段二加申论分支与 --since，导出 2016+ 申论 468 卷

为何：段二原只认 xingcezhenti 源，申论行被整片跳过。
改了什么：export.run 加申论分支（渲染→写盘→manifest）、新增 exportable_map
（申论源只加载一次）、--since 统一过滤（行测 <2016 = 0 ⇒ 零扰动）。
核实：unittest tests.test_export_shenlun 全绿；真库重跑后行测 427 卷 sha 逐字节不变、
交付树 895 md、manifest 895 行。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 闸门 G5/G6 的申论分支

**Files:**
- Modify: `tools/gwyzhenti/gates.py`
- Modify: `tools/gwyzhenti/cli.py`（`gate` 子命令接线 `--since`，裁定 R-M3-6）
- Test: `tools/tests/test_gates.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `shenlun.load_source` / `questions_for_titles` / `titles_of` / `source_lines` / `strip_structure`；Task 2 的 `export.exportable_map`
- Produces: `gates._g5_shenlun(md_path, row, shenlun_src, repo_root) -> (bool, str)`；`gates.run_all(..., since=None)`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_gates.py`）**

```python
class TestG5ShenlunBranch(unittest.TestCase):
    """申论保真：源 JSON 的 s/q/a/e 行必须逐行出现在导出里（多重集相等）。"""

    def _pair(self):
        from gwyzhenti import shenlun
        from gwyzhenti.model import PaperKey
        qs = [{"t": "单一题", "s": "材料甲\n材料乙", "q": "请概括", "a": "", "e": "范文一",
               "source": "x"}]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        return qs, shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                        sources=["linfukai186"]).body

    def test_clean_render_has_no_diff(self):
        from gwyzhenti import shenlun
        qs, body = self._pair()
        self.assertEqual(shenlun.strip_structure(body), shenlun.source_lines(qs))

    def test_dropped_source_line_is_caught(self):
        from gwyzhenti import shenlun
        qs, body = self._pair()
        broken = body.replace("材料乙", "")
        self.assertNotEqual(sorted(shenlun.strip_structure(broken)),
                            sorted(shenlun.source_lines(qs)))

    def test_injected_line_is_caught(self):
        from gwyzhenti import shenlun
        qs, body = self._pair()
        broken = body.replace("范文一", "范文一\n凭空多出来的一行")
        self.assertNotEqual(shenlun.strip_structure(broken), shenlun.source_lines(qs))

    def test_blank_line_asymmetry_is_not_a_diff(self):
        """R-M3-7 扩容回归：源里带空白行 / 渲染器折叠空行，都不得判成差异。

        实测背景：控制器全量扫 468 卷，现状下 460/468 卷报差异，差异行全是空白行。
        这条测试把它钉死 —— 谓词必须两侧共用（含剔空白行）。
        """
        from gwyzhenti import shenlun
        from gwyzhenti.model import PaperKey
        qs = [{"t": "单一题", "s": "材料甲\n\n\n材料乙", "q": "请概括", "a": "",
               "e": "范文一\n", "source": "x"}]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        body = shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                    sources=["linfukai186"]).body
        self.assertEqual(sorted(shenlun.strip_structure(body)),
                         sorted(shenlun.source_lines(qs)))

    def test_gate_reads_the_delivered_file_verbatim(self):
        """R-M3-11 回归：源侧是**内存字符串**（不经 I/O 翻译），导出侧读盘也必须**原样**。

        源行尾带 `\\r\\r`（上游硬换行残留，实测真库 56,776 行）时，闸门若用默认读法读盘，
        `X\\r\\r\\n` 被折成 `X\\n\\n` ⇒ 两侧不对称 ⇒ 真库 **372/468 卷**假红。
        这条**能红**：把 `_g5_shenlun` 的 `newline=""` 去掉，它立刻失败。
        """
        from gwyzhenti import gates, shenlun
        from gwyzhenti.model import PaperKey
        qs = [{"t": "单一题", "s": "材料甲\r\r\n材料乙", "q": "请概括", "a": "",
               "e": "范文一\r\r", "source": "x"}]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        body = shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                    sources=["linfukai186"]).body
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "wb") as fh:
                fh.write(body.encode("utf-8"))
            good, detail = gates._g5_shenlun(p, {"titles": {"linfukai186": ["卷T"]}},
                                             {"卷T": qs}, d)
        self.assertTrue(good, detail)
```

> 先在 `tests/test_gates.py` 顶部确认 import 区含 `from gwyzhenti import export, gates`、`import os`、`import tempfile`；缺哪个按该文件既有风格补。

- [ ] **Step 2: 跑测试确认失败/通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest tests.test_gates`
Expected: 若 Task 1 已完成，这三条**应直接通过**（它们测的是 `shenlun` 的两个函数，不含 `gates` 分支）。**通过后仍须写 Step 3 的 `gates` 分支** —— 单测证明判据本身能红，Step 5 证明它真的接进了 G5。

- [ ] **Step 3a: 确认共用谓词已就位（裁定 R-M3-7）**

**这一步在 Task 1 的 fix round 1 里已经做完**（`shenlun._keep_line`，两侧共用）。此处只做确认：

```bash
cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -c "import gwyzhenti.shenlun as s; print(s._keep_line(''), s._keep_line('  '), s._keep_line('材料'), s._keep_line('# 材料'))"
```

Expected: `False False True False`。

若这条命令报 `AttributeError`（说明 Task 1 的 fix round 没落地），**停下来** —— 不要在这里补，
`_g5_shenlun` 会在 460 卷上假红。回 Task 1 补完再继续。

- [ ] **Step 3b: 改 `gates.py`**

在 `gates.py` 顶部 import 加 `shenlun`：`from . import export, mdread, render, shenlun`。

新增函数（放在 `_g5` 之后）：

```python
def _g5_shenlun(md_path, row, shenlun_src, repo_root):
    """申论保真：源 JSON 的 s/q/a/e 行 vs 导出正文行，逐行**多重集**相等。

    源不是 md 文件，故不能走 `_g5`（它读 `_parts_for` 的模块 md）。
    两侧的过滤**共用** `shenlun._keep_line`（Step 3a）—— 与行测 `_strip_declared` 同口径。
    """
    if row is None:
        return False, "catalog 里找不到该卷: %s" % os.path.relpath(md_path, repo_root).replace(os.sep, "/")
    qs = shenlun.questions_for_titles(shenlun_src, shenlun.titles_of(row))
    if not qs:
        return False, "申论源题缺失"
    # 读盘必须**原样**（`newline=""`，裁定 R-M3-11）：源侧是**内存 JSON**，从不经 I/O 的通用换行
    # 翻译；导出侧若用默认读法，源行尾的 `\r\r`（上游硬换行残留）会被折掉 ⇒ 两侧不对称。
    # 实测：盘上字节 == 新渲染字节 **0 卷有差异**、按原样读 **0 卷有差异**，而按默认读法
    # **372/468 卷**假红（那些卷的源侧有 56,776 行内容行行尾带 `\r`）。
    with io.open(md_path, encoding="utf-8", newline="") as fh:
        out_text = fh.read()
    cs = collections.Counter(shenlun.source_lines(qs))
    co = collections.Counter(shenlun.strip_structure(out_text))
    removed, added = sorted((cs - co).elements()), sorted((co - cs).elements())
    if removed or added:
        return False, "源有导出无 %d 行 / 导出有源无 %d 行；例：%s" % (
            len(removed), len(added), (removed or added)[:2])
    return True, "零内容增删"
```

顶部加 `import collections`。

改 `_g6` 签名与「可导出」判定：

```python
def _g6(catalog_dir, uproots, repo_root, mds, limit, failed, since=None):
```
把其中的 `for r in scope:` 循环改用一次性建好的可导出表：

```python
    exp = export.exportable_map(rows, uproots)
    exportable, absent = 0, []
    for r in scope:
        if since and r["year"] < since:
            continue
        if not exp.get(r["slug"]):
            continue
        exportable += 1
        md_rel, _ = export.repo_paths(
            PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
        if not os.path.exists(os.path.join(repo_root, md_rel.replace("/", os.sep))):
            absent.append(md_rel)
```

改 `run_all` 签名并加申论源：

```python
def run_all(catalog_dir, uproots, repo_root, limit=None, since=None):
    rep = GatesReport()
    mds = _md_files(repo_root)
    if limit:
        mds = mds[:limit]
    xingce = uproots["xingcezhenti"]
    shenlun_src = shenlun.load_source(uproots.get("linfukai186", ""))
    index = _index(catalog_dir)
    failed = set()
```
G5 段按科目分派：

```python
    for md in mds:
        row = index.get(os.path.relpath(md, repo_root))
        if row is not None and row["subject"] == "申论":
            good, d = _g5_shenlun(md, row, shenlun_src, repo_root)
        else:
            good, d = _g5(md, row, xingce, repo_root)
        if not good:
            ok = False
            failed.add(md)
            detail.append(_tag(md, repo_root, d))
```
G6 调用改为 `_g6(catalog_dir, uproots, repo_root, mds, limit, failed, since=since)`。

> **G6 说明行必须自报口径（评审判定 F4/F5）**：`_g6` 的 detail 里「本次对账 %d」必须是**过完 `since` 之后**
> 真正参与对账的卷数（不是 `len(scope)`）；`since` 为空时须补一句「未限定年份（`--since` 为空）—— catalog 里
> 早于本次范围的卷不落盘属预期」。**判据（红/绿）一律不变** —— 只让打印出来的口径与实算一致。
> 另：`_g6` 只在**给定 `since`** 时才有意义（不带时 `可导出 1003` vs `落盘 895` 会误报缺卷），这是**已知限制**，
> 记录在案、不改判据（裁定 R-M3-13）。

> **G1/G2/G3/G4 不动**：G1 的 `QHEAD`/`DECL` 与 `render`/`shenlun` 产出的 `## 第 N 题`、`> 申论 · N 题 · …` 同构；G2 在 0 图卷上「双向闭合 0 张」自然通过；G3 因裁定 R-M3-1 沿用 `## 答案与解析` 直接通过；G4 只看 manifest↔磁盘 sha。

- [ ] **Step 3c: 接线 `cli` 的 `gate` 子命令（裁定 R-M3-6）**

`cmd_gate` 改成把 `since` 传下去：

```python
def cmd_gate(args):
    from . import gates
    rep = gates.run_all(args.catalog, _uproots(args), args.repo,
                        limit=args.limit, since=(args.since or None))
    for name, ok, detail in rep.results:
        print("  [%s] %s —— %s" % ("OK" if ok else "FAIL", name, detail))
    return 0 if rep.ok else 1
```

`gate` 子命令加参数（放在它的 `--limit` 之后）：

```python
    g.add_argument("--since", default="", help="只对账该年及以后（如 2016）；空 = 不过滤")
```

> 本步与 Step 3 **必须同一个提交** —— `cmd_gate` 传 `since` 而 `run_all` 不收，`TestGateSubcommand` 立红。

- [ ] **Step 4: 跑全量单测**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest discover -s tests`
Expected: OK（146 + Task1 新增 + Task2 新增 + 本轮 5 条）

- [ ] **Step 5: 在真交付树上跑闸门**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m gwyzhenti.cli gate --catalog ../work/catalog --upstream D:/projects/_gwy-upstream --repo .. --since 2016`
Expected: G1–G6 **全 OK**；G6 说明里 `落盘 md` 应为 **895**、`可导出` 应为 **895**。
若 G5 报某卷「源有导出无」，**不要改源、不要改判据** —— 先定位是渲染丢了行还是源里有异常行，把原始输出贴进报告。

- [ ] **Step 6: Commit**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/gates.py tools/gwyzhenti/cli.py tools/tests/test_gates.py
git commit -m "feat(m3): 闸门 G5/G6 加申论分支（R-M3-4）

为何：G5 原走 _parts_for（行测模块 md）⇒ 申论恒红；G6 用 _parts_for 判可导出 ⇒ 申论被算成 0 卷。
改了什么：新增 _g5_shenlun（源 JSON 的 s/q/a/e 行 vs 导出行的多重集比较，结构行两侧同剔）；
_g6 改用 exportable_map、支持 since；run_all 按科目分派 G5。G1–G4 未动。
核实：unittest discover 全绿（含 4 条判据能红回归）；真树 G1–G6 全 OK，G6 报落盘 895 / 可导出 895。

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: M3 覆盖账与报告

**Files:**
- Create: `tools/gwyzhenti/report_m3.py`
- Create（产物）: `work/M3-REPORT.md`

**Interfaces:**
- Consumes: `export.load_catalog`、`export.exportable_map`、`export.repo_paths`、`shenlun.load_source`、`shenlun.titles_of`
- Produces: `work/M3-REPORT.md`（含：申论 逐年×地区覆盖表、题数账、截断账、诚实边界）

- [ ] **Step 1: 写 `report_m3.py`**

```python
# -*- coding: utf-8 -*-
"""M3 覆盖账与报告（只读 catalog + 交付树 + 源；写 work/M3-REPORT.md）。"""
import argparse
import collections
import io
import os

from . import export, shenlun


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
                __import__("gwyzhenti.model", fromlist=["PaperKey"]).PaperKey(
                    r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
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
            __import__("gwyzhenti.model", fromlist=["PaperKey"]).PaperKey(
                r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
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
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(txt)
    print("→", out, len(txt.encode("utf-8")), "字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> `__import__("gwyzhenti.model", fromlist=["PaperKey"])` 是避免在函数内写顶层 import 的笨办法 —— **实现时直接在该文件顶部写 `from .model import PaperKey`**，并把那三处 `__import__(...)` 换成 `PaperKey`。计划里保留该写法只为标明**必须用 `PaperKey` 而非字符串**。

- [ ] **Step 2: 跑真库出报告**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m gwyzhenti.report_m3 --catalog ../work/catalog --upstream D:/projects/_gwy-upstream --repo .. --since 2016`
Expected: 写出 `work/M3-REPORT.md`；「2016+ 落盘」逐年合计 = **468**。

- [ ] **Step 3: 人工核对报告的三个数**

用只读命令独立复算，与报告对照（**不符就改报告，不改数**）：
- 申论 2016+ 行数 = 468
- 交付树里 `申论-*.md` 的文件数 = 468
- 截断题数：2016+ = **484**、全量 = **599**（控制器独立预取。若脚本得数与此不同，**先查口径再改报告，不改数**）

> 注意 `catalog.jsonl` 的 `year` 是**字符串**（`"2016"`），`n_questions` 是 **int**。`--since` 全程当字符串用
> （`"2016"`），四位年份的字典序与数值序一致 —— 与 `export.run` / `_g6` 的既有口径相同，**不要**改成 int。

```bash
cd D:/projects/gwy-zhenti && PYTHONIOENCODING=utf-8 python -X utf8 -c "
import os
n=sum(1 for dp,_,fs in os.walk('.') for f in fs if f.startswith('申论-') and f.endswith('.md'))
print('交付树 申论-*.md =', n)
"
```

- [ ] **Step 4: Commit**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/report_m3.py
git commit -m "feat(m3): M3 覆盖账与报告生成器（只读）

为何：申论导出后需要一份对全量成立的覆盖账与诚实边界，供复核。
改了什么：新增 tools/gwyzhenti/report_m3.py → work/M3-REPORT.md
（总量/逐年×落盘/地区覆盖/截断账/诚实边界）。
核实：真库跑出报告；2016+ 落盘合计 468，与独立复算一致。
（work/ 被 gitignore，报告本体不入库。）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review（写计划时自查过）

1. **Spec 覆盖**：§19 2016+ → R-M3-3；§27/§183 申论单列 → 本计划即 M3；§34 零改写 → R-M3-2/R-M3-5 + Task1 渲染只搬运；§36 排除非国省考 → 段一已做（632 excluded 含申论 264）；§115 不重做段一 → 「为什么 M3 只做段二」；§7 G1–G6 → Task3。**无缺口。**
2. **占位符**：无 TBD/TODO；每个 Step 有实际代码或实际命令。
3. **类型一致**：`shenlun.render_paper(questions, key, *, nature, form, sources)` 在 Task1 定义，Task2/3/4 调用一致；`exportable_map(rows, uproots) -> dict[slug,bool]` 在 Task2 定义、Task3/4 使用一致；`run_all(..., since=None)` 在 Task3 定义、cli 已是该形状。
4. **已知风险（写进报告，不隐藏）**：
   - ~~源材料若出现形如 `## 第 N 题` 的行 → G1 题数会多算~~ → **已实测为 0**（探针 `work/probe_m3_hazards.py`：2016+ 468 卷 / 2299 题里，题内 `## 第 N 题` 形行 **0**、独立 `---` 行 **0**、`## 答案与解析` 行 **0**）⇒ G1/结构/G3 均不受源文本干扰。
   - `省考-多省联考-2020-申论-统考` 是 catalog `dubious` 行（合并了 `2020·0725` 与 `2020·0822` 两次联考）——**段一已定，M3 不动**，只在报告里点名。
   - **保真判据两侧不对称 → G5 假红面（已在 Task 1 fix round 1 修掉，R-M3-7）**：控制器全量扫 468 卷实测
     **460/468 卷**两侧不等（差异行全是空白行 `''` / `'\r\r'`，形态一律 `缺 N 行 / 多 0 行`）；
     两侧共用 `shenlun._keep_line` 后 **468/468 卷零差异**（源里空白行 6,763、非空行 213,707）。
     报告里必须写这条 —— 它说明「导出侧忠实、判据侧不健全」曾经真实存在过。
   - **闸门读法不对称（已在 Task 3 fix round 1 修掉，R-M3-11）**：`_g5_shenlun` 源侧是**内存 JSON**、
     导出侧却走默认通用换行读法 ⇒ 真库 **372/468 卷**假红；改 `newline=""` 后 0 卷差异。交付物
     自始至终逐字节忠实（盘上字节 == 新渲染字节，0 卷差异）。**`\r` 残留不归一化**（见 Task 4 诚实边界）。
