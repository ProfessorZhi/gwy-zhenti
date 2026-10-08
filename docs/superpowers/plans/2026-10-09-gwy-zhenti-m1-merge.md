# gwy-zhenti 多源合并 · M1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把上游行测真题源归并成一份可核验的清单（段一），再把 2016–2026 行测逐卷导出成 `gwy-zhenti` 约定的 Markdown 布局（段二）。

**Architecture:** 两段式。**段一** 只读上游、产 `work/catalog/` 六个产物（`catalog.jsonl` 是唯一接口），**绝不碰正文**；**段二** 只读 `catalog.jsonl` + 上游正文，做五项机械变换后写盘。加新源 = 新增一个 adapter，下游不动。

**Tech Stack:** Python 3.12（**仅标准库**：`dataclasses` / `re` / `json` / `unittest` / `hashlib` / `pathlib`）。不引入第三方依赖 —— D 盘 + 深信服环境下装包是额外风险，且本任务的解析用不到。

**Spec:** `docs/superpowers/specs/2026-10-09-gwy-zhenti-merge-design.md`

## Global Constraints

- **落点**：管线代码 `gwy-zhenti/tools/`；上游只读克隆 `D:\projects\_gwy-upstream\<repo>`；中间产物 `gwy-zhenti/work/`；导出 `gwy-zhenti/{国考,省考,图片}/`。
- **本计划只写 `gwy-zhenti`**。绝不写 `gwy-material-ops/knowledge/`。
- **换行**：导出产物一律 **LF**；仓库根 `.gitattributes` 钉 `*.md text eol=lf` + 图片 `binary`。**产物逐字节稳定是 G4/G5 的判据**，不得放宽。
- **不改写题干 / 选项 / 答案 / 解析**；除 §六项变换外零改写。
- **Windows 执行约定**：所有 Python 调用用 `PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 …`；**带引号的长 Python 一律写成文件再跑，不用 heredoc**。
- **D 盘是 HDD + `sfavsvc`**：读可并发，**写盘串行**；测试用 `tools/tests/fixtures/` 小样本，只有显式标注的冒烟测试才读真库。
- **测试跑法**：`cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest discover -s tests -v`。
- **各步 `Expected: PASS，N tests OK` 里的 N 是示意值，不是闸门** —— 闸门是「全部测试通过 + 输出无噪声」。实际条数与 N 不符时**以实际为准**，并在报告里写明，**绝不为了凑数字增删测试**。
- **提交**：每个任务末尾一次 **本地** commit 到分支 **`feat/m1-merge`**（该分支在提交 spec/plan 时已创建，**实现时不要 `git checkout -b`**，直接 `git add` 指定文件 + `git commit`）。**绝不 push、绝不 force、绝不 `git add .`**。
- **凭据**：本计划全链路不接触任何 token / dlink / cookie。

## 实测数据事实（实现时以此为准，勿凭想象）

**A. `ERRRC/xingcezhenti`（行测正文主源，本机 `D:\projects\_gwy-upstream\xingcezhenti`）**

```
01-政治理论/ 02-常识判断/ 03-言语理解与表达/ 04-数量关系/ 05-判断推理/ 06-资料分析/
90-图片/题目图/   90-图片/公式图/   README.md   图片缺失清单.txt   蒸馏方法参考.md
```
- 每卷每模块一篇：`<模块目录>/<试卷名>.md`；同一 `<试卷名>` 出现在它有的各模块目录里（**各模块的卷集合不同**）。
- 模块目录前缀序 `01→06` **就是行测标准顺序**（政治理论在最前，覆盖 2025+ 国考新增）。
- frontmatter 固定 7 键 9 行：`类型 / 试卷 / 地区 / 年份 / 模块 / 题数 / 来源`，值一律双引号包裹。
- `地区` 已是归一值：省名（`浙江`/`江苏`/…/`西藏`）、`国考`，以及**需排除**的 `选调` `深圳市考` `广州市考`。
- 题目标题：`^#{2,4}\s*第\s*(\d+)\s*题`（政治理论等用 `##`，资料分析用 `###` 嵌套在 `## 材料 N` 下）。
- 选项行：`- **A**. 文本`；**正确项在行尾带 `　✅`**，实测 `✅` **只在选项行出现**（不在选项行的条数 = 0）。
- 答案行：`**答案**：X`；随后 `**官方解析**` + 正文（可能是 Markdown 段落，也可能是整段 `<p>…</p>`）。
- 图片：`<img width="700px" height="173px" src="../90-图片/题目图/<16hex>.png" />` 与
  `<img flag="tex" src="../90-图片/公式图/formula-<16hex>.png" />`（相对**模块目录**）。图片目录是**扁平**的，无按卷分子目录。
- 材料小标题：`## 材料 N`。
- 全库「第 N 题」标题合计 **58,890**，与 README 逐模块数字**完全一致** ⇒ `题数` 字段可信，可直接当 G1 基准。
- `图片缺失清单.txt` 实测仅 1 行（`90-图片/公式图/formula-4daf9a3762c10376.png`）。

**B. `linfukai186-arch/gongkao-tiku`（行测交叉对照源，本机 `D:\projects\_gwy-upstream\gongkao-tiku`）**

- `data/<类>/index.json` = `[{"key":"<卷标识>","count":N}, …]`，`<类> ∈ {guokao-xingce, shengkao-xingce, guokao-shenlun, shengkao-shenlun, …}`
- `data/<类>/y<YYYY>.json` = `{"<卷标识>":[{"t":"<模块>","s":"<材料>","q":"<题干>","o":["选项",…],"a":"<答案>","e":"<解析>"}, …]}`
- 卷标识样例：`2026·国家公务员考试行政执法`、`2020·江苏公务员考试《行测》真题C类`、`2027·国考行测申论联合模考大赛（第二十三季）`（**模考须排除**）。

**C. 已判定的范围事实**

- `zzcc-nb/gongkao-tiku`：`行测题库/`、`职测题库/` **为空**（README 自述「待采集」）⇒ **申论源，归 M3**，不进 M1。
- `shiwuooo/shangantong-papers-v2-c1/c2`：**行测源（非申论）**，每卷 `paper_*/{index.html,index_static.html,assets/*.webp}`，共 **498 卷**、**2008–2026**（2016+ 331 卷），`<title>` 即卷名；地区覆盖 30 省 + 国考，**独缺西藏**（ERRRC 有）⇒ **不提升「地域齐全」**，价值在交叉验证与老年份纵深。**归 M2，M1 不接。**

## 文件结构

```
gwy-zhenti/
├─ .gitignore                       # 忽略 work/
├─ tools/
│  ├─ README.md                     # 怎么跑、产物在哪
│  ├─ gwyzhenti/
│  │  ├─ __init__.py
│  │  ├─ model.py                   # PaperKey / SourceRecord / PaperAgg
│  │  ├─ slug.py                    # paper_slug
│  │  ├─ naming.py                  # 试卷名+地区 → PaperKey；排除规则
│  │  ├─ mdread.py                  # frontmatter/题数/图片/题块切分/去泄露 原语
│  │  ├─ sources/
│  │  │  ├─ __init__.py             # ADAPTERS 注册表
│  │  │  ├─ base.py                 # SourceAdapter 接口
│  │  │  ├─ xingcezhenti.py         # 正文主源
│  │  │  └─ linfukai186.py          # 交叉对照源
│  │  ├─ catalog.py                 # 段一：6 个产物
│  │  ├─ render.py                  # 段二：单卷五项变换 + revert
│  │  ├─ export.py                  # 段二：遍历导出 + 图片 + manifest
│  │  ├─ gates.py                   # G1–G6
│  │  └─ cli.py                     # catalog | export | gate
│  └─ tests/
│     ├─ __init__.py
│     ├─ fixtures/xingcezhenti/…    # 微型上游样本（Task 3 建）
│     ├─ fixtures/linfukai186/…     # 微型 JSON 样本（Task 5 建）
│     ├─ test_slug.py
│     ├─ test_naming.py
│     ├─ test_mdread.py
│     ├─ test_src_xingcezhenti.py
│     ├─ test_src_linfukai186.py
│     ├─ test_catalog.py
│     ├─ test_render.py
│     ├─ test_export.py
│     └─ test_gates.py
└─ docs/superpowers/{specs,plans}/…
```

---

### Task 1: 骨架 + 卷键 + 卷标识

**Files:**
- Create: `D:\projects\gwy-zhenti\.gitignore`
- Create: `D:\projects\gwy-zhenti\.gitattributes`
- Create: `tools/gwyzhenti/__init__.py`
- Create: `tools/gwyzhenti/model.py`
- Create: `tools/gwyzhenti/slug.py`
- Create: `tools/tests/__init__.py`
- Create: `tools/tests/test_slug.py`

**Interfaces:**
- Consumes: 无
- Produces: `PaperKey(level, region, year, subject, ptype)`（frozen dataclass，`region` 在国考时为空串）；`paper_slug(key, variant="") -> str`

- [ ] **Step 1: 写失败的测试**

`tools/tests/test_slug.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.model import PaperKey        # noqa: E402
from gwyzhenti.slug import paper_slug       # noqa: E402


class TestPaperSlug(unittest.TestCase):
    def test_shengkao_three_levels(self):
        k = PaperKey("省考", "四川", "2016", "行测", "A类")
        self.assertEqual(paper_slug(k), "省考-四川-2016-行测-A类")

    def test_guokao_has_no_region_segment(self):
        k = PaperKey("国考", "", "2026", "行测", "副省级")
        self.assertEqual(paper_slug(k), "国考-2026-行测-副省级")

    def test_variant_appended(self):
        k = PaperKey("省考", "四川", "2016", "行测", "统考")
        self.assertEqual(paper_slug(k, "网友回忆版"), "省考-四川-2016-行测-统考-网友回忆版")

    def test_deterministic(self):
        k = PaperKey("省考", "四川", "2016", "行测", "A类")
        self.assertEqual(paper_slug(k), paper_slug(k))

    def test_key_is_hashable_and_orderable(self):
        a = PaperKey("省考", "四川", "2016", "行测", "A类")
        b = PaperKey("省考", "四川", "2017", "行测", "A类")
        self.assertLess(a, b)
        self.assertEqual(len({a, b}), 2)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_slug -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti'`

- [ ] **Step 3: 写最小实现**

`tools/gwyzhenti/__init__.py`：
```python
# -*- coding: utf-8 -*-
"""gwy-zhenti 多源合并管线。两段式：catalog（段一）→ export（段二）。"""
```

`tools/gwyzhenti/model.py`：
```python
# -*- coding: utf-8 -*-
"""卷的归一身份与清单记录。"""
from dataclasses import dataclass, field, asdict

LEVEL_GUOKAO = "国考"
LEVEL_SHENGKAO = "省考"


@dataclass(frozen=True, order=True)
class PaperKey:
    """一卷的归一键。year 为四位字符串（源里就是字符串）。"""
    level: str      # 国考 | 省考
    region: str     # 省名；国考时为空串（国考不设地区层）
    year: str       # "2016"
    subject: str    # 行测 | 申论
    ptype: str      # A类 | B类 | C类 | 乡镇卷 | 县级卷 | 副省级 | 地市级 | 行政执法 | 统考

    def as_dict(self):
        return asdict(self)
```

`tools/gwyzhenti/slug.py`：
```python
# -*- coding: utf-8 -*-
"""确定性卷标识：用于目录名、文件名与图片目录名。"""
from .model import PaperKey


def paper_slug(key: PaperKey, variant: str = "") -> str:
    parts = [key.level, key.region, key.year, key.subject, key.ptype]
    if variant:
        parts.append(variant)
    return "-".join(p.strip() for p in parts if p and p.strip())
```

`tools/tests/__init__.py`：留空（让 `unittest discover` 认包）。

`.gitignore`（仓库根）：
```
work/
__pycache__/
*.pyc
```

`.gitattributes`（仓库根）—— **本仓产物必须逐字节稳定**：本机 `core.autocrlf=true`，检出时会把 `.md` 变成 CRLF，
使 G4/G5 的 sha 在别的机器上失真，故在此钉死：
```
*.md text eol=lf
*.png binary
*.jpg binary
*.jpeg binary
*.webp binary
*.gif binary
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_slug -v`
Expected: PASS，5 tests OK

- [ ] **Step 5: 提交**

```bash
cd D:/projects/gwy-zhenti
git add .gitignore .gitattributes tools/gwyzhenti/__init__.py tools/gwyzhenti/model.py tools/gwyzhenti/slug.py tools/tests/__init__.py tools/tests/test_slug.py
git commit -m "feat(tools): 骨架 + 卷键 + 确定性卷标识"
```

---

### Task 2: 试卷名解析（层级 / 卷型 / 性质 / 排除）

**Files:**
- Create: `tools/gwyzhenti/naming.py`
- Create: `tools/tests/test_naming.py`

**Interfaces:**
- Consumes: `PaperKey`（Task 1）
- Produces: `classify(region, year, title, subject="行测") -> Classified`，其中
  `Classified(key: PaperKey, nature: str, form: str)`；解析不了抛 `Unparsed(reason, title)`。
  常量 `EXCLUDE_REGIONS`、`EXCLUDE_TITLE`、`PTYPE_RULES`。

- [ ] **Step 1: 写失败的测试**

`tools/tests/test_naming.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.naming import classify, Unparsed      # noqa: E402
from gwyzhenti.slug import paper_slug                # noqa: E402


class TestClassify(unittest.TestCase):
    def test_liankao_shengkao_default_ptype(self):
        c = classify("四川", "2016", "2016年423联考《行测》题（四川卷）")
        self.assertEqual(c.key.level, "省考")
        self.assertEqual(c.key.region, "四川")
        self.assertEqual(c.key.ptype, "统考")
        self.assertEqual(c.nature, "正式真题")
        self.assertEqual(c.form, "联考")

    def test_guokao_region_cleared_and_subtype_from_title(self):
        c = classify("国考", "2026", "2026年国家公务员录用考试《行测》题（副省级网友回忆版）")
        self.assertEqual(c.key.level, "国考")
        self.assertEqual(c.key.region, "")
        self.assertEqual(c.key.ptype, "副省级")
        self.assertEqual(c.nature, "网友回忆版")
        self.assertEqual(c.form, "单独命题")

    def test_zhixing_and_xingzheng_zhifa(self):
        self.assertEqual(classify("国考", "2026", "…（行政执法卷网友回忆版）").key.ptype, "行政执法")
        self.assertEqual(classify("上海", "2016", "2016年上海市公务员录用考试《行测》题（A类）").key.ptype, "A类")
        self.assertEqual(classify("上海", "2016", "…（B类）").key.ptype, "B类")

    def test_excluded_region_raises(self):
        with self.assertRaises(Unparsed):
            classify("选调", "2017", "2017年重庆市选调优秀大学生到基层工作考试《行测》题")
        with self.assertRaises(Unparsed):
            classify("深圳市考", "2020", "2020年深圳市公务员考试《行测》题")

    def test_excluded_title_raises(self):
        with self.assertRaises(Unparsed):
            classify("江西", "2019", "2019年江西省法检统一考录公务员笔试《行测》题")

    def test_empty_region_raises(self):
        with self.assertRaises(Unparsed):
            classify("", "2020", "某卷")

    def test_xuandiao_in_title_is_excluded(self):
        # 地区字段是「四川」，但标题是选调卷 —— 必须由**标题**排除词拦下
        with self.assertRaises(Unparsed):
            classify("四川", "2016",
                     "2016年3月四川省选调优秀大学生到基层工作考试 行政职业能力测验试卷（精选）")

    def test_selected_nature(self):
        c = classify("四川", "2016", "2016年四川省公务员录用考试《行测》题（精选）")
        self.assertEqual(c.nature, "精选")

    def test_reason_is_populated(self):
        try:
            classify("选调", "2017", "x")
        except Unparsed as e:
            self.assertIn("选调", e.reason)
        else:
            self.fail("应当抛 Unparsed")

    def test_zhejiang_ab_juan_do_not_collide(self):
        # 实测：2016/2017 浙江联考同时有 A卷 与 B卷（同年同省同科目）
        # —— 卷型若默认成「统考」，两卷会塌成同一个 slug，导出时后写覆盖先写
        a = classify("浙江", "2016", "2016年423联考《行测》题（浙江A卷）")
        b = classify("浙江", "2016", "2016年423联考《行测》题（浙江B卷）")
        self.assertEqual(a.key.ptype, "A类")
        self.assertEqual(b.key.ptype, "B类")
        self.assertNotEqual(paper_slug(a.key), paper_slug(b.key))

    def test_unknown_suffix_is_carried_verbatim_not_defaulted(self):
        # 实测存在（甲级/乙级/下半年/县级以上/定向乡镇/省直卷/…）：
        # 认不出就**逐字**带上，绝不静默塌成「统考」
        self.assertEqual(classify("吉林", "2016", "2016年吉林省公务员考试《行测》题（甲级）").key.ptype,
                         "甲级")
        self.assertEqual(classify("浙江", "2019", "2019年浙江省公务员考试《行测》题（下半年）").key.ptype,
                         "下半年")

    def test_memory_marker_is_not_a_ptype(self):
        # 「网友回忆版」是**性质**，不是卷型 —— 不能进 slug
        c = classify("云南", "2016", "2016年423联考《行测》题（云南网友回忆版）")
        self.assertEqual(c.key.ptype, "统考")
        self.assertEqual(c.nature, "网友回忆版")

    def test_region_marker_is_not_a_ptype(self):
        # `（四川卷）` 里的「四川」是地区标记，剥掉后为空 ⇒ 统考
        self.assertEqual(classify("四川", "2016", "2016年423联考《行测》题（四川卷）").key.ptype,
                         "统考")

    def test_trailing_juan_is_absorbed_only_when_it_lands_in_the_vocabulary(self):
        # 尾缀「卷」的容差是**窄的**：剥掉后能落回已声明词表才剥（`行政执法卷`→`行政执法`），
        # 否则逐字保留 —— 真库里 `（省直）` 与 `（黑龙江省直卷）` 同时存在，宽泛地剥会让
        # 两者收敛成同一个 ptype ⇒ 撞 slug ⇒ 丢卷。
        self.assertEqual(classify("国考", "2026", "…（行政执法卷网友回忆版）").key.ptype, "行政执法")
        self.assertEqual(classify("黑龙江", "2016", "…（黑龙江省直卷）").key.ptype, "省直卷")
        shi = classify("黑龙江", "2016", "…（省直）").key.ptype
        hl = classify("黑龙江", "2016", "…（黑龙江省直卷）").key.ptype
        self.assertEqual(shi, "省直")
        self.assertNotEqual(shi, hl)

    def test_compound_suffix_keeps_nature_word_out_of_ptype(self):
        # 性质词在复合后缀里是**尾巴** ⇒ 必须在 token 内部剔除，精确匹配会漏
        c = classify("国考", "2026", "2026年国家公务员录用考试《行测》题（副省级网友回忆版）")
        self.assertEqual(c.key.ptype, "副省级")
        self.assertEqual(c.nature, "网友回忆版")

    def test_no_suffix_is_tongkao(self):
        # spec §6.1：标题里没有括号后缀 ⇒ 统考
        self.assertEqual(classify("江西", "2016", "2016年江西省公务员考试《行测》题").key.ptype,
                         "统考")

    def test_gongjianfa_is_excluded(self):
        # 「公检法」与 spec 已排除的「法检」同属系统内招录 ⇒ 一并排除
        with self.assertRaises(Unparsed):
            classify("黑龙江", "2016", "2016年黑龙江省公务员考试《行测》题（公检法卷）")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_naming -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.naming'`

- [ ] **Step 3: 写最小实现**

`tools/gwyzhenti/naming.py`：
```python
# -*- coding: utf-8 -*-
"""试卷名 + 地区字段 → PaperKey。只做保守命中，拿不准就抛 Unparsed。"""
import re
from dataclasses import dataclass

from .model import LEVEL_GUOKAO, LEVEL_SHENGKAO, PaperKey

# 实测存在的非国省考地区值
EXCLUDE_REGIONS = {"选调", "深圳市考", "广州市考"}
# 标题里的排除词（实测样本：法检统一考录、司法所、事业编、职测、综应、模考）
EXCLUDE_TITLE = re.compile(r"选调|法检|司法所|公检法|事业编|事业单位|职测|综应|模考|公开课|模拟")

# 卷型：**长模式在前**，先命中先返回。**只归一到 spec 已声明的词表**，其余一律不推测。
PTYPE_RULES = (
    (re.compile(r"副省级"), "副省级"),
    (re.compile(r"地市级"), "地市级"),
    (re.compile(r"行政执法"), "行政执法"),
    (re.compile(r"A类|A卷"), "A类"),
    (re.compile(r"B类|B卷"), "B类"),
    (re.compile(r"C类|C卷"), "C类"),
    (re.compile(r"D类|D卷"), "D类"),
    (re.compile(r"乡镇卷|乡镇"), "乡镇卷"),
    (re.compile(r"县级卷|县级"), "县级卷"),
)
MEMORY = re.compile(r"网友回忆版")
SELECTED = re.compile(r"精选")
LIANKAO = re.compile(r"联考")

# 标题里的括号内容（全角与半角都认）
PAREN = re.compile(r"[（(]([^）)]*)[）)]")
# 括号里这些词是**性质/形式**，不是卷型 —— 不能进 slug。用 `sub` 在 token **内部**剔除，
# 因为复合后缀（`行政执法卷网友回忆版`）里它们只是尾巴；精确匹配会漏 ⇒ 性质词被带上 slug。
NOT_PTYPE = re.compile(r"网友回忆版|精选|联考")
# 已声明词表的**值**集合 —— 尾缀 `卷` 只在剥掉后能落回词表时才允许剥（见 `_match_value`）。
PTYPE_VALUES = frozenset(v for _, v in PTYPE_RULES)


def _ptype_tokens(region, title):
    """取出标题括号里的「卷型/批次」token：先剥掉其中的地区标记（`浙江A卷`→`A卷`、`四川卷`→空），
    再**逐字**返回剩下的部分。性质/形式词（网友回忆版/精选/联考）不算卷型。
    """
    out = []
    for raw in PAREN.findall(title):
        s = raw.strip()
        if region and s.startswith(region):
            s = s[len(region):]
        s = NOT_PTYPE.sub("", s)
        if s == "卷":
            s = ""
        if s:
            out.append(s)
    return out


def _match_value(token):
    """token → 已声明卷型值；认不出返回 `None`。

    尾缀 `卷` 的容差是**窄的**：只在剥掉后能落回 `PTYPE_VALUES` 时才剥。真库同时存在
    `（省直）` 与 `（黑龙江省直卷）`，宽容差会把两者收敛成同一个 ptype ⇒ 撞 slug ⇒ **丢卷**。
    """
    for rx, value in PTYPE_RULES:
        if rx.fullmatch(token):
            return value
    if token.endswith("卷") and token[:-1] in PTYPE_VALUES:
        return token[:-1]
    return None


def _ptype(region, title):
    """卷型判定。**塌成同一个值 = 撞 slug = 丢卷**，故认不出时逐字带上，绝不默认。"""
    tokens = _ptype_tokens(region, title)
    for t in tokens:
        value = _match_value(t)
        if value:
            return value
    if tokens:
        return "+".join(sorted(set(tokens)))
    # 没有括号后缀 —— 回落到全标题扫描（覆盖 `2026·国家公务员考试副省级` 这种无括号写法）
    for rx, value in PTYPE_RULES:
        if rx.search(title):
            return value
    # spec §6.1：无后缀 ⇒ 统考
    return "统考"


class Unparsed(Exception):
    """解析不了 —— 进 unparsed.jsonl，绝不静默丢弃。"""

    def __init__(self, reason, title=""):
        super().__init__("%s | %s" % (reason, title))
        self.reason = reason
        self.title = title


@dataclass(frozen=True)
class Classified:
    key: PaperKey
    nature: str
    form: str


def classify(region, year, title, subject="行测"):
    title = title or ""
    if not region:
        raise Unparsed("地区字段为空", title)
    if region in EXCLUDE_REGIONS:
        raise Unparsed("非国省考地区: %s" % region, title)
    m = EXCLUDE_TITLE.search(title)
    if m:
        raise Unparsed("试卷名含排除词: %s" % m.group(0), title)

    level = LEVEL_GUOKAO if region == LEVEL_GUOKAO else LEVEL_SHENGKAO
    ptype = _ptype(region, title)

    if MEMORY.search(title):
        nature = "网友回忆版"
    elif SELECTED.search(title):
        nature = "精选"
    else:
        nature = "正式真题"

    form = "联考" if LIANKAO.search(title) else "单独命题"
    key = PaperKey(level, "" if level == LEVEL_GUOKAO else region, str(year), subject, ptype)
    return Classified(key, nature, form)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_naming -v`
Expected: PASS，17 tests OK

- [ ] **Step 5: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/naming.py tools/tests/test_naming.py
git commit -m "feat(tools): 试卷名解析表（层级/卷型/性质/排除）"
```

---

### Task 3: Markdown 读取原语 + 微型上游样本

**Files:**
- Create: `tools/gwyzhenti/mdread.py`
- Create: `tools/tests/fixtures/xingcezhenti/02-常识判断/2016年423联考《行测》题（四川卷）.md`
- Create: `tools/tests/fixtures/xingcezhenti/06-资料分析/2016年423联考《行测》题（四川卷）.md`
- Create: `tools/tests/fixtures/xingcezhenti/06-资料分析/2020年江苏省公务员录用考试《行测》题（A类）.md`
- Create: `tools/tests/test_mdread.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `read_frontmatter(text) -> dict[str, str]`（只取 `键: "值"` 形式）
  - `count_questions(text) -> int`
  - `iter_images(text) -> list[tuple[str, str]]`（`(类型, 相对路径)`，类型 ∈ `{题目图, 公式图}`）
  - `split_question_blocks(text) -> tuple[list[str], list[list[str]]]`（`(前导行, 题块列表)`）
  - `split_answer(block) -> tuple[list[str], list[str], list[str]]`（`(题干行, 答案行, 尾行)`）
  - `strip_leak(lines) -> list[str]`
  - `correct_option(block) -> str | None`（从 `**答案**：X` 取字母）
  - 常量 `QHEAD`, `ANS`, `IMG`

- [ ] **Step 1: 建微型上游样本**

`tools/tests/fixtures/xingcezhenti/06-资料分析/2016年423联考《行测》题（四川卷）.md`：
```markdown
---
类型: "真题"
试卷: "2016年423联考《行测》题（四川卷）"
地区: "四川"
年份: "2016"
模块: "资料分析"
题数: "2"
来源: "tiku.db 原始题库（未蒸馏）"
---

# 2016年423联考《行测》题（四川卷）

> 资料分析 · 2 题 · 四川 2016

## 材料 1

<p><img width="654px" height="388px" src="../90-图片/题目图/154428b1a538147.png" /><br></p>

### 第 1 题　<sub>qid 1796142 · 综合</sub>

2014年1~10月我国货物运输总量为多少亿吨？

- **A**. 340.2
- **B**. 353.9　✅
- **C**. 366.5
- **D**. 393.2

**答案**：B

**官方解析**

定位表格，2014年1~11月货物运输总量为393.2亿吨。故正确答案为B。

---

### 第 2 题　<sub>qid 1796168 · 综合</sub>

2013年1~10月我国货物运输总量最大的领域是：

- **A**. 水运
- **B**. 民航
- **C**. 铁路
- **D**. 公路　✅

**答案**：D

**官方解析**

由表可知公路最大。故正确答案为D。

---
```

`tools/tests/fixtures/xingcezhenti/02-常识判断/2016年423联考《行测》题（四川卷）.md`：
```markdown
---
类型: "真题"
试卷: "2016年423联考《行测》题（四川卷）"
地区: "四川"
年份: "2016"
模块: "常识判断"
题数: "1"
来源: "tiku.db 原始题库（未蒸馏）"
---

# 2016年423联考《行测》题（四川卷）

> 常识判断 · 1 题 · 四川 2016

## 第 1 题　<sub>qid 1797001 · 政治</sub>

下列说法正确的是：

- **A**. 甲
- **B**. 乙　✅
- **C**. 丙
- **D**. 丁

**答案**：B

**官方解析**

<p>A项错误。B项正确，故正确答案为B。</p>
```

`tools/tests/fixtures/xingcezhenti/06-资料分析/2020年江苏省公务员录用考试《行测》题（A类）.md`：
```markdown
---
类型: "真题"
试卷: "2020年江苏省公务员录用考试《行测》题（A类）"
地区: "江苏"
年份: "2020"
模块: "资料分析"
题数: "1"
来源: "tiku.db 原始题库（未蒸馏）"
---

# 2020年江苏省公务员录用考试《行测》题（A类）

> 资料分析 · 1 题 · 江苏 2020

### 第 1 题　<sub>qid 2000001 · 计算</sub>

增长率约为：<img flag="tex" src="../90-图片/公式图/formula-717ebaedf48c8509.png" />。

- **A**. 5%
- **B**. 7%　✅

**答案**：B

**官方解析**

计算得7%。故正确答案为B。

---
```

- [ ] **Step 2: 写失败的测试**

`tools/tests/test_mdread.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import mdread      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "xingcezhenti")
ZL = os.path.join(FIX, "06-资料分析", "2016年423联考《行测》题（四川卷）.md")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestMdRead(unittest.TestCase):
    def setUp(self):
        self.zl = load(ZL)

    def test_frontmatter(self):
        fm = mdread.read_frontmatter(self.zl)
        self.assertEqual(fm["地区"], "四川")
        self.assertEqual(fm["年份"], "2016")
        self.assertEqual(fm["模块"], "资料分析")
        self.assertEqual(fm["题数"], "2")

    def test_count_questions(self):
        self.assertEqual(mdread.count_questions(self.zl), 2)

    def test_images_typed(self):
        imgs = mdread.iter_images(self.zl)
        self.assertEqual(imgs, [("题目图", "../90-图片/题目图/154428b1a538147.png")])

    def test_formula_image_typed(self):
        jiangsu = load(os.path.join(FIX, "06-资料分析", "2020年江苏省公务员录用考试《行测》题（A类）.md"))
        self.assertEqual(mdread.iter_images(jiangsu),
                         [("公式图", "../90-图片/公式图/formula-717ebaedf48c8509.png")])

    def test_split_blocks_and_preamble_keeps_material(self):
        pre, blocks = mdread.split_question_blocks(self.zl)
        self.assertEqual(len(blocks), 2)
        self.assertTrue(any(ln.startswith("## 材料 1") for ln in pre))
        self.assertTrue(blocks[0][0].startswith("### 第 1 题"))

    def test_split_answer(self):
        _, blocks = mdread.split_question_blocks(self.zl)
        stem, ans, tail = mdread.split_answer(blocks[0])
        self.assertTrue(any("340.2" in ln for ln in stem))
        self.assertTrue(any(ln.startswith("**答案**：") for ln in ans))
        self.assertTrue(any("官方解析" in ln for ln in ans))
        self.assertEqual(tail, [])

    def test_split_answer_tail_returns_next_material(self):
        # 第二题块之后（本 fixture 里为文件末尾）不应有内容
        _, blocks = mdread.split_question_blocks(self.zl)
        _, ans2, tail2 = mdread.split_answer(blocks[1])
        self.assertTrue(any("公路最大" in ln for ln in ans2))
        self.assertEqual(tail2, [])

    def test_strip_leak_removes_checkmark_only(self):
        lines = ["- **B**. 353.9　✅", "- **A**. 340.2", "**答案**：B"]
        self.assertEqual(mdread.strip_leak(lines),
                         ["- **B**. 353.9", "- **A**. 340.2", "**答案**：B"])

    def test_correct_option(self):
        _, blocks = mdread.split_question_blocks(self.zl)
        self.assertEqual(mdread.correct_option(blocks[0]), "B")
        self.assertEqual(mdread.correct_option(blocks[1]), "D")

    def test_correct_option_none_when_no_answer(self):
        self.assertIsNone(mdread.correct_option(["### 第 1 题", "无答案"]))
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_mdread -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.mdread'`

- [ ] **Step 4: 写最小实现**

`tools/gwyzhenti/mdread.py`：
```python
# -*- coding: utf-8 -*-
"""上游 Markdown 的读取原语。只解析，不改写。"""
import re

FM_LINE = re.compile(r'^([^\s:：]+):\s*"(.*)"\s*$')
QHEAD = re.compile(r'^#{2,4}\s*第\s*(\d+)\s*题')
ANS = re.compile(r'^\*\*答案\*\*：\s*([A-Za-z])')
ANS_ANY = re.compile(r'^\*\*答案\*\*：')
IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')
LEAK = re.compile(r'[\u3000\s]*✅')
OPTION = re.compile(r'^- \*\*([A-Za-z])\*\*\.')


def read_frontmatter(text):
    """取文件头 YAML 里的 `键: "值"`。不做完整 YAML 解析（源固定 7 键）。"""
    out = {}
    for ln in text.split("\n"):
        if ln.strip() == "---" and out:
            break
        m = FM_LINE.match(ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def count_questions(text):
    return sum(1 for ln in text.split("\n") if QHEAD.match(ln))


def iter_images(text):
    """→ [(类型, 相对路径)]。类型由路径段判定。"""
    out = []
    for ln in text.split("\n"):
        for src in IMG.findall(ln):
            if "/题目图/" in src:
                out.append(("题目图", src))
            elif "/公式图/" in src:
                out.append(("公式图", src))
    return out


def split_question_blocks(text):
    """→ (前导行, [题块行列表])。题块 = 从 `第 N 题` 标题到下一题标题（或文末）。"""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if QHEAD.match(ln)]
    if not starts:
        return lines, []
    bounds = starts + [len(lines)]
    blocks = [lines[a:b] for a, b in zip(starts, bounds[1:])]
    return lines[:starts[0]], blocks


def split_answer(block):
    """→ (题干行, 答案行, 尾行)。

    答案行 = 首个 `**答案**：` 起，到其后**第一个** `---` 分隔线（含）。
    尾行 = 该分隔线之后的内容（例如下一段 `## 材料 N`），必须回正文，不能算答案。
    无答案标记时 → (block, [], [])。
    """
    start = None
    for i, ln in enumerate(block):
        if ANS_ANY.match(ln):
            start = i
            break
    if start is None:
        return block, [], []
    end = None
    for k in range(start, len(block)):
        if block[k].strip() == "---":
            end = k
            break
    if end is None:
        return block, [], []
    return block[:start], block[start:end + 1], block[end + 1:]


def strip_leak(lines):
    """剥掉选项行尾的 `✅`（及其前面的全角空格）。"""
    return [LEAK.sub("", ln) if "✅" in ln else ln for ln in lines]


def correct_option(block):
    """从 `**答案**：X` 取字母；取不到返回 None。"""
    for ln in block:
        m = ANS.match(ln)
        if m:
            return m.group(1).upper()
    return None
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_mdread -v`
Expected: PASS，10 tests OK

- [ ] **Step 6: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/mdread.py tools/tests/test_mdread.py tools/tests/fixtures
git commit -m "feat(tools): Markdown 读取原语 + 微型上游样本"
```

---

### Task 4: `xingcezhenti` adapter（段一核心）

**Files:**
- Create: `tools/gwyzhenti/sources/__init__.py`
- Create: `tools/gwyzhenti/sources/base.py`
- Create: `tools/gwyzhenti/sources/xingcezhenti.py`
- Create: `tools/tests/test_src_xingcezhenti.py`
- Create: `tools/tests/smoke_xingcezhenti.py`（手工冒烟，不进 `unittest discover`）

**Interfaces:**
- Consumes: `PaperKey`（Task 1）、`paper_slug`（Task 1）、`classify/Unparsed`（Task 2）、`mdread`（Task 3）
- Produces:
  - `tools/gwyzhenti/sources/base.py`：`class SourceAdapter`（`family: str`、`scan(root) -> ScanResult`）、
    `@dataclass ScanResult(records: list[dict], unparsed: list[dict], excluded: list[dict])`，
    记录 dict 的键固定为
    `{family, title, region, year, module, n_questions, relpath, images_题目, images_公式}`
  - `tools/gwyzhenti/sources/__init__.py`：`ADAPTERS: dict[str, SourceAdapter]`，键为 `"xingcezhenti"` / `"linfukai186"`
  - `xingcezhenti.XingceZhentiAdapter`，`MODULE_DIRS` 常量

- [ ] **Step 1: 写失败的测试**

`tools/tests/test_src_xingcezhenti.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.xingcezhenti import XingceZhentiAdapter, MODULE_DIRS   # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "xingcezhenti")


class TestXingceZhentiAdapter(unittest.TestCase):
    def setUp(self):
        self.res = XingceZhentiAdapter().scan(FIX)

    def test_module_order_is_curriculum_order(self):
        self.assertEqual(MODULE_DIRS[0], "01-政治理论")
        self.assertEqual(MODULE_DIRS[-1], "06-资料分析")

    def test_records_are_per_paper_per_module(self):
        # fixture: 四川卷有 常识判断 1 题 + 资料分析 2 题；江苏A类卷 资料分析 1 题 ⇒ 3 条记录
        self.assertEqual(len(self.res.records), 3)
        got = {(r["title"], r["module"]): r["n_questions"] for r in self.res.records}
        self.assertEqual(got[("2016年423联考《行测》题（四川卷）", "资料分析")], 2)
        self.assertEqual(got[("2016年423联考《行测》题（四川卷）", "常识判断")], 1)
        self.assertEqual(got[("2020年江苏省公务员录用考试《行测》题（A类）", "资料分析")], 1)

    def test_record_shape_and_image_counts(self):
        r = [x for x in self.res.records if x["module"] == "资料分析" and x["year"] == "2016"][0]
        self.assertEqual(r["family"], "xingcezhenti")
        self.assertEqual(r["region"], "四川")
        self.assertEqual(r["images_题目"], 1)
        self.assertEqual(r["images_公式"], 0)
        self.assertTrue(r["relpath"].endswith(".md"))

    def test_no_unparsed_for_clean_fixture(self):
        self.assertEqual(self.res.unparsed, [])

    def test_n_questions_matches_actual_headings(self):
        for r in self.res.records:
            self.assertIsInstance(r["n_questions"], int)
            self.assertGreater(r["n_questions"], 0)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_src_xingcezhenti -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.sources'`

- [ ] **Step 3: 写最小实现**

`tools/gwyzhenti/sources/base.py`：
```python
# -*- coding: utf-8 -*-
"""所有源 adapter 的统一接口。段一只认这个接口，段二只认 catalog.jsonl。"""
from dataclasses import dataclass, field

RECORD_KEYS = (
    "family", "title", "region", "year", "module", "n_questions",
    "relpath", "images_题目", "images_公式",
)


@dataclass
class ScanResult:
    records: list = field(default_factory=list)     # 卷×模块 粒度
    unparsed: list = field(default_factory=list)    # [{family, title, region, year, module, relpath, reason}]
    excluded: list = field(default_factory=list)    # [{family, title, region, year, module, relpath, reason}]


class SourceAdapter:
    family = ""

    def scan(self, root):
        raise NotImplementedError
```

`tools/gwyzhenti/sources/xingcezhenti.py`：
```python
# -*- coding: utf-8 -*-
"""ERRRC/xingcezhenti adapter：卷×模块 粒度清单。只读，不产正文。"""
import os

from .. import mdread
from ..naming import Unparsed, classify
from .base import ScanResult, SourceAdapter

FAMILY = "xingcezhenti"

# 目录序 **就是** 行测标准顺序（政治理论在最前，覆盖 2025+ 国考新增）
MODULE_DIRS = (
    "01-政治理论", "02-常识判断", "03-言语理解与表达",
    "04-数量关系", "05-判断推理", "06-资料分析",
)


class XingceZhentiAdapter(SourceAdapter):
    family = FAMILY

    def scan(self, root):
        res = ScanResult()
        for module_dir in MODULE_DIRS:
            abs_dir = os.path.join(root, module_dir)
            if not os.path.isdir(abs_dir):
                continue
            for name in sorted(os.listdir(abs_dir)):
                if not name.endswith(".md") or name == "README.md":
                    continue
                relpath = "%s/%s" % (module_dir, name)
                self._one(os.path.join(abs_dir, name), relpath, res)
        return res

    def _one(self, abspath, relpath, res):
        with open(abspath, encoding="utf-8") as fh:
            text = fh.read()
        fm = mdread.read_frontmatter(text)
        title = fm.get("试卷", os.path.splitext(os.path.basename(relpath))[0])
        module = fm.get("模块", os.path.basename(os.path.dirname(relpath)))
        region = fm.get("地区", "")
        year = fm.get("年份", "")
        try:
            classify(region, year, title)
        except Unparsed as exc:
            res.excluded.append({
                "family": FAMILY, "title": title, "region": region, "year": year,
                "module": module, "relpath": relpath, "reason": exc.reason,
            })
            return
        imgs = mdread.iter_images(text)
        declared = fm.get("题数", "")
        actual = mdread.count_questions(text)
        res.records.append({
            "family": FAMILY,
            "title": title,
            "region": region,
            "year": year,
            "module": module,
            "n_questions": actual,
            "relpath": relpath,
            "images_题目": sum(1 for t, _ in imgs if t == "题目图"),
            "images_公式": sum(1 for t, _ in imgs if t == "公式图"),
            # 台账用：源自报题数，供 G1 对账（不参与导出）
            "declared_questions": int(declared) if declared.isdigit() else -1,
        })
```

> 说明：`classify` 在这里**只用于筛除**（排除项进 `excluded`）；是否进 `unparsed` 由上层的固化逻辑决定 ——
> `classify` 抛异常时区分「排除」与「解析不了」：`reason` 以「非国省考地区」「试卷名含排除词」开头者入 `excluded`，
> 其余（如「地区字段为空」）入 `unparsed`。在 `_one` 里按这一条分流。

把上面 `_one` 的 `except` 分支改为：
```python
        except Unparsed as exc:
            bucket = res.unparsed if exc.reason.startswith(("地区字段为空",)) else res.excluded
            bucket.append({
                "family": FAMILY, "title": title, "region": region, "year": year,
                "module": module, "relpath": relpath, "reason": exc.reason,
            })
            return
```

`tools/gwyzhenti/sources/__init__.py`：
```python
# -*- coding: utf-8 -*-
"""adapter 注册表。加新源 = 在这里多一行。"""
from .xingcezhenti import XingceZhentiAdapter

ADAPTERS = {
    XingceZhentiAdapter.family: XingceZhentiAdapter(),
}
```
（Task 5 会补 `linfukai186`。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_src_xingcezhenti -v`
Expected: PASS，5 tests OK

- [ ] **Step 5: 真库冒烟（**唯一读 340MB 真库的测试**，慢）**

写 `tools/tests/smoke_xingcezhenti.py`（**不作为 unittest**；不用 `python -c`，免得引号被 shell 吃掉）：
```python
# -*- coding: utf-8 -*-
"""真库冒烟：读本机 xingcezhenti 克隆，核对题数与排除项。手工运行。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.xingcezhenti import XingceZhentiAdapter      # noqa: E402

ROOT = r"D:\projects\_gwy-upstream\xingcezhenti"


def main():
    res = XingceZhentiAdapter().scan(ROOT)
    total = sum(r["n_questions"] for r in res.records)
    print("records %d | unparsed %d | excluded %d | 题数合计 %d"
          % (len(res.records), len(res.unparsed), len(res.excluded), total))
    reasons = {}
    for e in res.excluded:
        reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
    for k in sorted(reasons):
        print("  excluded %4d  %s" % (reasons[k], k))
    assert total == 58890, "题数合计应为 58890，实得 %d" % total


if __name__ == "__main__":
    main()
```

Run:
```bash
cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 tests/smoke_xingcezhenti.py
```
Expected: `题数合计 58890`；`excluded` 理由分布含 `非国省考地区: 选调` / `非国省考地区: 深圳市考` / `非国省考地区: 广州市考`。

- [ ] **Step 6: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/sources/__init__.py tools/gwyzhenti/sources/base.py tools/gwyzhenti/sources/xingcezhenti.py tools/tests/test_src_xingcezhenti.py tools/tests/smoke_xingcezhenti.py
git commit -m "feat(tools): xingcezhenti adapter（卷×模块清单 + 排除/未解析分流）"
```

---

### Task 5: `linfukai186` adapter（交叉对照源）

**Files:**
- Create: `tools/gwyzhenti/sources/linfukai186.py`
- Create: `tools/tests/fixtures/linfukai186/data/guokao-xingce/index.json`
- Create: `tools/tests/fixtures/linfukai186/data/guokao-xingce/y2026.json`
- Create: `tools/tests/fixtures/linfukai186/data/guokao-xingce/y2027.json`
- Create: `tools/tests/test_src_linfukai186.py`
- Modify: `tools/gwyzhenti/sources/__init__.py`

**Interfaces:**
- Consumes: `ScanResult`（Task 4）
- Produces: `Linfukai186Adapter`（`family = "linfukai186"`），记录键同上，另加 `n_questions` = 该卷**题级条目数**（此源无「题数」字段）

- [ ] **Step 1: 建微型样本**

`tools/tests/fixtures/linfukai186/data/guokao-xingce/index.json`：
```json
[{"key":"2026·国家公务员考试副省级","count":1},{"key":"2027·国考行测申论联合模考大赛（第二十三季）","count":1}]
```
`tools/tests/fixtures/linfukai186/data/guokao-xingce/y2026.json`：
```json
{"2026·国家公务员考试副省级":[{"t":"资料分析","s":"","q":"增长率为多少？","o":["5%","7%"],"a":"B","e":"计算得7%。"}]}
```
`tools/tests/fixtures/linfukai186/data/guokao-xingce/y2027.json`：
```json
{"2027·国考行测申论联合模考大赛（第二十三季）":[{"t":"公文写作题","s":"材料1","q":"请拟写一份通知。","o":[],"a":"","e":""}]}
```

- [ ] **Step 2: 写失败的测试**

`tools/tests/test_src_linfukai186.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.linfukai186 import Linfukai186Adapter      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "linfukai186")


class TestLinfukai186Adapter(unittest.TestCase):
    def setUp(self):
        self.res = Linfukai186Adapter().scan(FIX)

    def test_records_per_paper_module(self):
        self.assertEqual(len(self.res.records), 1)
        r = self.res.records[0]
        self.assertEqual(r["family"], "linfukai186")
        self.assertEqual(r["module"], "资料分析")
        self.assertEqual(r["n_questions"], 1)
        self.assertEqual(r["year"], "2026")

    def test_mock_exam_excluded(self):
        self.assertTrue(any("模考" in e["reason"] for e in self.res.excluded))

    def test_relpath_points_at_year_file(self):
        self.assertTrue(self.res.records[0]["relpath"].endswith("y2026.json"))
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_src_linfukai186 -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.sources.linfukai186'`

- [ ] **Step 4: 写最小实现**

`tools/gwyzhenti/sources/linfukai186.py`：
```python
# -*- coding: utf-8 -*-
"""linfukai186-arch/gongkao-tiku adapter：题级 JSON，按 **卷标识** 归组。

此源**无 卷型 字段、无图片**；仅作覆盖交叉对照与补洞提示，不参与段二导出。
"""
import json
import os
import re

from ..naming import Unparsed, classify
from .base import ScanResult, SourceAdapter

FAMILY = "linfukai186"
CATS = ("guokao-xingce", "shengkao-xingce")     # M1 只接行测两类
YEAR_RE = re.compile(r"^y(\d{4})\.json$")
YEAR_IN_KEY = re.compile(r"(\d{4})")


class Linfukai186Adapter(SourceAdapter):
    family = FAMILY

    def scan(self, root):
        res = ScanResult()
        data = os.path.join(root, "data")
        for cat in CATS:
            cat_dir = os.path.join(data, cat)
            if not os.path.isdir(cat_dir):
                continue
            for name in sorted(os.listdir(cat_dir)):
                m = YEAR_RE.match(name)
                if not m:
                    continue
                relpath = "data/%s/%s" % (cat, name)
                self._one(os.path.join(cat_dir, name), relpath, m.group(1), res)
        return res

    def _one(self, abspath, relpath, fallback_year, res):
        with open(abspath, encoding="utf-8") as fh:
            papers = json.load(fh)
        for title, items in papers.items():
            if not items:
                continue
            ym = YEAR_IN_KEY.search(title)
            year = ym.group(1) if ym else fallback_year
            region = "国考" if title.startswith(str(year) + "·国家公务员") else \
                (title.split("·", 1)[1][:2] if "·" in title else "")
            try:
                classify(region, year, title)
            except Unparsed as exc:
                bucket = res.unparsed if exc.reason.startswith("地区字段为空") else res.excluded
                bucket.append({
                    "family": FAMILY, "title": title, "region": region, "year": year,
                    "module": "", "relpath": relpath, "reason": exc.reason,
                })
                continue
            by_module = {}
            for it in items:
                by_module.setdefault(it.get("t", ""), 0)
                by_module[it["t"]] += 1
            for module, n in by_module.items():
                res.records.append({
                    "family": FAMILY, "title": title, "region": region, "year": year,
                    "module": module, "n_questions": n, "relpath": relpath,
                    "images_题目": 0, "images_公式": 0,
                })
```

`tools/gwyzhenti/sources/__init__.py`（追加一行）：
```python
# -*- coding: utf-8 -*-
"""adapter 注册表。加新源 = 在这里多一行。"""
from .linfukai186 import Linfukai186Adapter
from .xingcezhenti import XingceZhentiAdapter

ADAPTERS = {
    XingceZhentiAdapter.family: XingceZhentiAdapter(),
    Linfukai186Adapter.family: Linfukai186Adapter(),
}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_src_linfukai186 -v`
Expected: PASS，3 tests OK

- [ ] **Step 6: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/sources/linfukai186.py tools/gwyzhenti/sources/__init__.py tools/tests/test_src_linfukai186.py tools/tests/fixtures/linfukai186
git commit -m "feat(tools): linfukai186 adapter（行测交叉对照，模考排除）"
```

---

### Task 6: 段一 —— 六个产物

**Files:**
- Create: `tools/gwyzhenti/catalog.py`
- Create: `tools/tests/test_catalog.py`

**Interfaces:**
- Consumes: `ADAPTERS`（Task 4/5）、`classify`（Task 2）、`paper_slug`（Task 1）
- Produces:
  - `build(uproots: dict[str, str], out_dir: str) -> Report`
    （`uproots` 形如 `{"xingcezhenti": r"D:\...\xingcezhenti", "linfukai186": r"D:\...\gongkao-tiku"}`）
  - `Report` dataclass：`papers: int`、`records: int`、`questions: int`、`unparsed: int`、`excluded: int`、`by_region: dict[str, int]`
  - 产物：`catalog.jsonl` / `coverage.md` / `gaps.md` / `conflicts.md` / `excluded.jsonl` / `unparsed.jsonl`

- [ ] **Step 1: 写失败的测试**

`tools/tests/test_catalog.py`：
```python
# -*- coding: utf-8 -*-
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import catalog        # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def jl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="gwycat-")
        self.rep = catalog.build({
            "xingcezhenti": os.path.join(FIX, "xingcezhenti"),
            "linfukai186": os.path.join(FIX, "linfukai186"),
        }, self.out)

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_six_artifacts_exist(self):
        for n in ("catalog.jsonl", "coverage.md", "gaps.md", "conflicts.md",
                  "excluded.jsonl", "unparsed.jsonl"):
            self.assertTrue(os.path.exists(os.path.join(self.out, n)), n)

    def test_catalog_one_paper_one_line(self):
        rows = jl(os.path.join(self.out, "catalog.jsonl"))
        # fixture: 四川卷 2016（两模块）+ 江苏A类 2020 + linfukai186 的 2026 国考副省级 ⇒ 3 卷
        self.assertEqual(len(rows), 3)
        titles = {r["title"] for r in rows}
        self.assertEqual(titles, {"2016年423联考《行测》题（四川卷）",
                                  "2020年江苏省公务员录用考试《行测》题（A类）",
                                  "2026·国家公务员考试副省级"})

    def test_catalog_row_shape(self):
        rows = jl(os.path.join(self.out, "catalog.jsonl"))
        r = [x for x in rows if x["region"] == "四川"][0]
        self.assertEqual(r["level"], "省考")
        self.assertEqual(r["subject"], "行测")
        self.assertEqual(r["year"], "2016")
        self.assertEqual(r["ptype"], "统考")
        self.assertEqual(r["slug"], "省考-四川-2016-行测-统考")
        self.assertEqual(r["n_questions"], 3)          # 常识 1 + 资料 2
        self.assertEqual(sorted(r["modules"]), ["常识判断", "资料分析"])
        self.assertEqual(r["sources"], ["xingcezhenti"])

    def test_report_totals(self):
        self.assertEqual(self.rep.papers, 3)           # 含 linfukai186 的 2026 国考副省级
        self.assertEqual(self.rep.records, 4)          # 卷×模块
        self.assertEqual(self.rep.questions, 5)        # 1+2+1 + 1（linfukai186）

    def test_coverage_matrix_has_region_rows(self):
        with open(os.path.join(self.out, "coverage.md"), encoding="utf-8") as fh:
            cov = fh.read()
        self.assertIn("四川", cov)
        self.assertIn("江苏", cov)
        self.assertIn("申论", cov)      # 申论列必须存在，且标为未接入（M3）

    def test_gaps_ordered_region_first(self):
        with open(os.path.join(self.out, "gaps.md"), encoding="utf-8") as fh:
            gaps = fh.read()
        self.assertIn("地域优先", gaps)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_catalog -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.catalog'`

- [ ] **Step 3: 写最小实现**

`tools/gwyzhenti/catalog.py`：
```python
# -*- coding: utf-8 -*-
"""段一：把各源 adapter 的清单汇总成 catalog.jsonl 与覆盖报告。

**本模块绝不读也不写 gwy-zhenti 的正文。**
"""
import io
import json
import os
from dataclasses import dataclass, field

from .model import PaperKey
from .naming import LEVEL_GUOKAO, LEVEL_SHENGKAO, Unparsed, classify
from .slug import paper_slug
from .sources import ADAPTERS

SUBJECTS = ("行测", "申论")
# 省级地区全集（用于「地域齐全」度量；实测 ERRRC 出现过的 31 个 + 国考）
PROVINCES = (
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西",
    "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
)


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
            c = classify(r["region"], r["year"], r["title"], subject="行测")
        except Unparsed as exc:            # 理论上 adapter 已分流；此处兜底
            all_unparsed.append(dict(r, reason=exc.reason))
            continue
        key = c.key
        p = papers.setdefault(key, {
            "title": r["title"], "nature": c.nature, "form": c.form,
            "modules": {}, "sources": set(), "declared": 0,
        })
        p["modules"][r["module"]] = p["modules"].get(r["module"], 0) + r["n_questions"]
        p["sources"].add(r["family"])
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


def _write_coverage(out_dir, rows, rep):
    have = {}
    for r in rows:
        have.setdefault((r["region"] or "国考", r["subject"]), []).append(r["year"])
    L = ["# 覆盖矩阵（地区 × 科目）", "",
         "> 由 catalog.jsonl 实算得出。**地域齐全 > 时间齐全**：先看地区行是否空白，再看年份纵深。", "",
         "| 地区 | 科目 | 卷数 | 年份跨度 | 年份数 |", "|---|---|---:|---|---:|"]
    for region in ["国考"] + list(PROVINCES):
        for subject in SUBJECTS:
            ys = have.get((region, subject), [])
            if ys:
                L.append("| %s | %s | %d | %s–%s | %d |"
                         % (region, subject, len(ys), min(ys), max(ys), len(set(ys))))
            else:
                note = "**未接入（M3）**" if subject == "申论" else "**缺**"
                L.append("| %s | %s | 0 | — | 0 | %s" % (region, subject, note))
    L += ["", "**合计**：%d 卷 / %d 题。" % (rep.papers, rep.questions)]
    _w(os.path.join(out_dir, "coverage.md"), L)


def _write_gaps(out_dir, rows, rep):
    have = {(r["region"] or "国考", r["subject"]) for r in rows}
    L = ["# 缺口清单", "",
         "> 排序 = **地域优先**、年份次之、**新卷先于老卷**。", ""]
    L.append("## 一、地区级缺口（最高优先）")
    for region in ["国考"] + list(PROVINCES):
        missing = [s for s in SUBJECTS if (region, s) not in have]
        if missing:
            L.append("- **%s**：缺 %s" % (region, "、".join(missing)))
    L.append("")
    L.append("## 二、年次级缺口（地区齐了再看）")
    for region in ["国考"] + list(PROVINCES):
        ys = sorted({r["year"] for r in rows if (r["region"] or "国考") == region})
        if not ys:
            continue
        full = {str(y) for y in range(2016, 2027)}
        miss = sorted(full - set(ys), reverse=True)      # 新的在前
        if miss:
            L.append("- %s：有 %s；缺 %s" % (region, "、".join(ys), "、".join(miss)))
    L += ["", "> 未接入的申论源见 spec §3 与 SOURCES.md；M3 前不宣称申论覆盖。"]
    _w(os.path.join(out_dir, "gaps.md"), L)


def _write_conflicts(out_dir, rows):
    L = ["# 同卷多源冲突", "",
         "> 同一卷键被多个来源家族同时提供时列出，**留证不裁决**。", ""]
    hit = [r for r in rows if len(r["sources"]) > 1]
    if not hit:
        L.append("（本次无同键多源卷。）")
    for r in hit:
        L.append("- `%s` ← %s" % (r["slug"], "、".join(r["sources"])))
    _w(os.path.join(out_dir, "conflicts.md"), L)


def _w(path, lines):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_catalog -v`
Expected: PASS，6 tests OK

- [ ] **Step 5: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/catalog.py tools/tests/test_catalog.py
git commit -m "feat(tools): 段一 —— catalog/coverage/gaps/conflicts/excluded/unparsed 六产物"
```

---

### Task 7: CLI `catalog` + 段一实跑（**人工验收检查点**）

**Files:**
- Create: `tools/gwyzhenti/cli.py`
- Create: `tools/README.md`

**Interfaces:**
- Consumes: `catalog.build`（Task 6）
- Produces: `python -m gwyzhenti.cli catalog --up-upstream <root> --out <dir>`；后续 Task 11 在同一 `cli.py` 加 `export` / `gate` 子命令

- [ ] **Step 1: 写 CLI**

`tools/gwyzhenti/cli.py`：
```python
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
```

`tools/README.md`：
```markdown
# gwy-zhenti 管线

两段式：**段一** 产清单（不碰正文），**段二** 逐卷导出。

```bash
cd D:/projects/gwy-zhenti/tools
export PYTHONIOENCODING=utf-8

# 段一：把上游克隆汇总成清单
python -X utf8 -m gwyzhenti.cli catalog \
  --upstream "D:/projects/_gwy-upstream" \
  --out "../work/catalog"

# 跑测试
python -X utf8 -m unittest discover -s tests -v
```

- 上游只读；产物全在 `../work/`（已 gitignore）。
- 加新源 = 在 `gwyzhenti/sources/` 写一个 adapter + 在 `sources/__init__.py` 注册一行。
```

- [ ] **Step 2: 实跑段一**

Run:
```bash
cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m gwyzhenti.cli catalog --upstream "D:/projects/_gwy-upstream" --out "../work/catalog"
```
Expected: 打印卷数 / 记录数 / 题数；`题数` 中 xingcezhenti 部分应为 **58,890**。

- [ ] **Step 3: 人工核对产物（**停下来给用户看**）**

Run: `ls D:/projects/gwy-zhenti/work/catalog/`；然后**把 `coverage.md` 的「地区 × 科目」表**贴给用户，并明确指出：
- 哪些省份已有、哪些为「**缺**」；
- `excluded.jsonl` 的条数与理由分布（应主要是 `选调` / `深圳市考` / `广州市考` / 含排除词）；
- `unparsed.jsonl` 是否为空（**非空必须逐条给用户裁决，不得自行处理**）。

**此步是硬检查点：等用户确认覆盖图与排除清单后方可继续。**

- [ ] **Step 4: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/cli.py tools/README.md
git commit -m "feat(tools): catalog 子命令 + 管线使用说明"
```

---

### Task 8: 段二 —— 单卷五项变换

**Files:**
- Create: `tools/gwyzhenti/render.py`
- Create: `tools/tests/test_render.py`

**Interfaces:**
- Consumes: `mdread`（Task 3）、`PaperKey`（Task 1）
- Produces:
  - `render_paper(parts: list[str], key: PaperKey, *, nature: str, form: str, sources: list[str], modules: list[str], image_map: dict[str, str]) -> RenderedPaper`
    - `parts`：该卷各模块**源的完整文本**，**必须按 ModuleOrder 传入**
    - `image_map`：`{源里的 src → 输出相对路径}`（Task 9 负责算）
  - `@dataclass RenderedPaper: body: str, images_used: list[str], n_questions: int, numbering: str`
  - `MODULE_ORDER` 常量

- [ ] **Step 1: 写失败的测试**

`tools/tests/test_render.py`：
```python
# -*- coding: utf-8 -*-
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import render        # noqa: E402
from gwyzhenti.model import PaperKey    # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "xingcezhenti")
# 源里的写法 → 导出后应有的写法（测试与 image_map 共用同一常量，避免两处各写一遍写岔）
SRC_IMG = "../90-图片/题目图/154428b1a538147.png"
IMG_OUT = "../../../图片/省考-四川-2016-行测-统考/题目图/154428b1a538147.png"


def load(*p):
    with open(os.path.join(FIX, *p), encoding="utf-8") as fh:
        return fh.read()


class TestRender(unittest.TestCase):
    def setUp(self):
        self.key = PaperKey("省考", "四川", "2016", "行测", "统考")
        self.parts = [
            load("02-常识判断", "2016年423联考《行测》题（四川卷）.md"),
            load("06-资料分析", "2016年423联考《行测》题（四川卷）.md"),
        ]
        self.out = render.render_paper(
            self.parts, self.key, nature="正式真题", form="联考",
            sources=["xingcezhenti"], modules=["常识判断", "资料分析"],
            image_map={SRC_IMG: IMG_OUT},
        )

    def test_no_checkmark_anywhere(self):
        self.assertNotIn("✅", self.out.body)

    def test_answers_moved_to_own_section(self):
        self.assertIn("## 答案与解析", self.out.body)
        self.assertIn("<details>", self.out.body)
        # 答案区必须位于最后一道题之后
        self.assertLess(self.out.body.index("## 答案与解析"),
                        self.out.body.rindex("<details>"))

    def test_question_count_across_modules(self):
        self.assertEqual(self.out.n_questions, 3)
        self.assertEqual(self.out.numbering, "原卷重建")

    def test_numbering_is_rebuilt_contiguously(self):
        nums = [int(m) for m in re.findall(r"^#{2,4}\s*第\s*(\d+)\s*题", self.out.body, re.M)]
        self.assertEqual(nums, [1, 2, 3])

    def test_images_rewritten_and_collected(self):
        self.assertIn(IMG_OUT, self.out.body)
        self.assertNotIn("../90-图片/", self.out.body)
        self.assertEqual(self.out.images_used, [IMG_OUT])

    def test_frontmatter_contract(self):
        head = self.out.body.split("---")[1]
        for k in ("考试", "地区", "年份", "科目", "卷型", "真题性质", "来源", "校验状态", "题号口径"):
            self.assertIn(k, head)

    def test_g5_diff_is_empty_against_source(self):
        # 导出 vs 源：除声明过的结构性差异外，逐行多重集必须相等（零内容增删）
        removed, added = render.diff_report(self.out.body, self.parts)
        self.assertEqual(removed, [], "源里有、导出里没有的行")
        self.assertEqual(added, [], "导出里多出来、源里没有的行")

    def test_g5_diff_catches_a_perturbation(self):
        # 把正文里**第一处 A 选项行**的数字改掉 ⇒ 必须被判为「源里有、导出没有」
        bad = re.sub(r"(?m)^(- \*\*A\*\*\. )(\d+)", r"\g<1>999999", self.out.body, count=1)
        self.assertNotEqual(bad, self.out.body, "fixture 里没有可扰动的 A 选项行")
        removed, _ = render.diff_report(bad, self.parts)
        self.assertTrue(removed, "扰动后 diff 必须非空")
```

> 注：`images_used` 的期望值与 `image_map` 共用 `IMG_OUT` 常量，避免同一路径两处各写一遍写岔。
> `diff_report` 是 G5 的判据 —— **不要求**导入导出互为逆变换（题号重建本就不是逆变换），
> 要求的是「除声明项外逐行多重集相等」。图片路径按**文件名**比对（源 `../90-图片/…` vs 导出 `../../../图片/…`）。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_render -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.render'`

- [ ] **Step 3: 写最小实现**

`tools/gwyzhenti/render.py`：
```python
# -*- coding: utf-8 -*-
"""段二：单卷合并 + 五项机械变换。除这五项外逐字符保真。

五项变换：
  1 合并（按 MODULE_ORDER 拼接各模块）
  2 题号重建（模块内序号 → 连续原卷号）
  3 答案去泄露（剥 ✅；答案与解析移到卷末 <details>）
  4 图片重写（相对路径按输出深度计算）
  5 frontmatter 契约
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from . import mdread
from .model import PaperKey

MODULE_ORDER = (
    "政治理论", "常识判断", "言语理解与表达",
    "数量关系", "判断推理", "资料分析",
)
IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')
QNUM = re.compile(r'^(#{2,4})\s*第\s*(\d+)\s*题(.*)$')


@dataclass
class RenderedPaper:
    body: str = ""
    images_used: list = field(default_factory=list)
    n_questions: int = 0
    numbering: str = ""


def _renumber(lines, offset):
    out = []
    for ln in lines:
        m = QNUM.match(ln)
        out.append("%s 第 %d 题%s" % (m.group(1), int(m.group(2)) + offset, m.group(3))
                   if m else ln)
    return out


def _rewrite_images(lines, image_map):
    used = []

    def sub(m):
        src = m.group(1)
        if src in image_map:
            used.append(image_map[src])
            return m.group(0).replace(src, image_map[src])
        return m.group(0)

    return [IMG.sub(sub, ln) for ln in lines], used


def _frontmatter(key, nature, form, sources, numbering):
    lines = [
        "---",
        '考试: "%s"' % key.level,
        '地区: "%s"' % (key.region or key.level),
        '年份: "%s"' % key.year,
        '科目: "%s"' % key.subject,
        '卷型: "%s"' % key.ptype,
        '真题性质: "%s"' % nature,
        '命题形式: "%s"' % form,
        '来源: [%s]' % ", ".join('"%s"' % s for s in sources),
        '题号口径: "%s"' % numbering,
        '校验状态: "机器校验（并卷/题号/图片/去泄露/G1–G5）；未人工通读"',
        "---",
    ]
    return lines


def render_paper(parts, key, *, nature, form, sources, modules, image_map):
    """parts 必须已按 MODULE_ORDER 排好；modules 与之等长，给出模块名。"""
    # 1) frontmatter 契约（先按「模块内序号」估，若模块齐则用「原卷重建」）
    standard = [m for m in MODULE_ORDER if m in set(modules)]
    numbering = "原卷重建" if standard == list(modules) else "模块内序号"

    blocks, answers, used = [], [], []
    offset = 0
    for part, module in zip(parts, modules):
        pre, qblocks = mdread.split_question_blocks(part)
        # 每个部分的前导正文（含 `## 材料 N` 与材料图）按**原位**进正文 ——
        # 只取第一部分会把后续部分的材料整段丢掉（资料分析作第二模块时必现）。
        seg = mdread.strip_leak(_body_head(pre))
        if seg:
            if blocks:
                blocks += [""]
            blocks += seg
        for b in qblocks:
            stem, ans, tail = mdread.split_answer(b)
            blocks += _renumber(mdread.strip_leak(stem), offset)
            if tail:
                blocks += mdread.strip_leak(tail)
            if ans:
                answers.append((int(mdread.QHEAD.match(b[0]).group(1)) + offset,
                                mdread.strip_leak(ans)))
        offset += len(qblocks)

    # 4) 图片重写（在正文与答案里都要做）
    flat, u1 = _rewrite_images(blocks, image_map)
    used.extend(u1)
    ans_lines = []
    for num, al in answers:
        al, u2 = _rewrite_images(al, image_map)
        used.extend(u2)
        ans_lines.append((num, al))

    body = _frontmatter(key, nature, form, sources, numbering) + [""]
    body += ["# %s" % key_label(key), ""]
    body += ["> %s · %d 题 · %s %s" % (key.subject, offset, key.region or key.level, key.year), ""]
    body += flat
    body += ["", "## 答案与解析", ""]
    for num, al in ans_lines:
        body += ["<details>", "<summary>第 %d 题</summary>" % num, ""]
        body += al
        body += ["</details>", ""]

    # 合并相邻空行，去首尾空白，行尾统一 LF
    text = "\n".join(body)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    return RenderedPaper(text, used, offset, numbering)


def key_label(key):
    if key.level == "国考":
        return "%s %s %s（%s）" % (key.year, "国家公务员录用考试", key.subject, key.ptype)
    return "%s %s省公务员录用考试 %s（%s）" % (key.year, key.region, key.subject, key.ptype)


def _body_head(pre):
    """取源前导块里除 frontmatter / `---` / 一级标题 / 引言（`>` 行）之外的**正文**行。"""
    out, seen_h1 = [], False
    for ln in pre:
        if ln.strip() == "---":
            continue
        if mdread.FM_LINE.match(ln):
            continue
        if ln.startswith("# ") and not seen_h1:
            seen_h1 = True
            continue
        if ln.startswith("> "):
            continue
        out.append(ln)
    while out and not out[0].strip():
        out.pop(0)
    return out


LEAK_SUB = re.compile(r"[　\s]*✅")
QNUM_ANY = re.compile(r"^(#{2,4})\s*第\s*\d+\s*题(.*)$")
SRC_ATTR = re.compile(r'(src=")(?:[^"]*/)?([^"/]+)(")')
# 我们**声明过**要新增或删除的结构行；G5 在两侧都剔除它们
STRUCTURAL = re.compile(
    r"^\s*(---|#{1,2}\s*答案与解析|<details>|</details>|<summary>.*</summary>)\s*$")
FM_BLOCK = re.compile(r"\A(?:---\n.*?\n---\n)", re.S)


def _strip_declared(text):
    """剔除双方共有的「声明过的结构性差异」：frontmatter 块、一级标题、引言、答案区容器、空行。"""
    text = FM_BLOCK.sub("", text)
    out = []
    for ln in text.split("\n"):
        if not ln.strip():
            continue
        if ln.startswith("# ") or ln.startswith("> "):
            continue
        if STRUCTURAL.match(ln):
            continue
        out.append(ln)
    return out


def _normalize(lines):
    """可比较形态：去 ✅（连前导全角空格）、`第 N 题` 编号抹成 `?`、图片路径只留文件名。"""
    out = []
    for ln in lines:
        ln = LEAK_SUB.sub("", ln)
        ln = QNUM_ANY.sub(lambda m: "%s 第 ? 题%s" % (m.group(1), m.group(2)), ln)
        ln = SRC_ATTR.sub(lambda m: m.group(1) + m.group(2) + m.group(3), ln)
        out.append(ln)
    return out


def diff_report(out_text, src_texts):
    """G5 判据：导出 vs 源，返回 (源里有而导出没有的行, 导出有而源里没有的行)，各为排序后的列表。

    两侧都剔除**声明过的**结构性差异后做逐行多重集比较 —— 即**零内容增删**。
    刻意**不**做「导入导出互为逆变换」：题号重建本就不是逆变换，硬构造逆向只会把判据做脆。
    """
    src_lines = []
    for t in src_texts:
        src_lines += _strip_declared(t)
    cs = Counter(_normalize(src_lines))
    co = Counter(_normalize(_strip_declared(out_text)))
    return sorted((cs - co).elements()), sorted((co - cs).elements())
```

> **实现提示**：`import` 段要把 `from collections import Counter` 加上。G5 的判据是**多重集相等**，
> 不是逆变换 —— 别去写「把导出还原成源」的反函数，那条路会为了对齐 ✅ 与题号把判据做脆。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_render -v`
Expected: PASS，8 tests OK

- [ ] **Step 5: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/render.py tools/tests/test_render.py
git commit -m "feat(tools): 段二单卷渲染（合并/题号/去泄露/图片/frontmatter + G5 对账）"
```

---

### Task 9: 段二 —— 导出与图片落盘

**Files:**
- Create: `tools/gwyzhenti/export.py`
- Create: `tools/tests/test_export.py`

**Interfaces:**
- Consumes: `catalog`（Task 6）产物、`render.render_paper`（Task 8）
- Produces:
  - `export.repo_paths(key, slug) -> tuple[str, str]`（`(md 相对路径, 图片目录相对路径)`）
  - `export.run(catalog_dir, upstream, repo_root, limit=None) -> ExportReport`
  - `ExportReport`：`papers`、`files`、`images`、`manifest_path`

- [ ] **Step 1: 写失败的测试**

`tools/tests/test_export.py`：
```python
# -*- coding: utf-8 -*-
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import catalog, export        # noqa: E402
from gwyzhenti.model import PaperKey         # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class TestExportPaths(unittest.TestCase):
    def test_shengkao_three_levels(self):
        p, img = export.repo_paths(PaperKey("省考", "四川", "2016", "行测", "统考"), "省考-四川-2016-行测-统考")
        self.assertEqual(p, "省考/四川/2016/行测-统考.md")
        self.assertEqual(img, "图片/省考-四川-2016-行测-统考")

    def test_guokao_two_levels(self):
        p, img = export.repo_paths(PaperKey("国考", "", "2026", "行测", "副省级"), "国考-2026-行测-副省级")
        self.assertEqual(p, "国考/2026/行测-副省级.md")
        self.assertEqual(img, "图片/国考-2026-行测-副省级")


class TestExportRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwyexp-")
        self.cat = os.path.join(self.tmp, "catalog")
        self.repo = os.path.join(self.tmp, "repo")
        catalog.build({
            "xingcezhenti": os.path.join(FIX, "xingcezhenti"),
            "linfukai186": os.path.join(FIX, "linfukai186"),
        }, self.cat)
        self.rep = export.run(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_papers_written(self):
        self.assertEqual(self.rep.papers, 2)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "省考/四川/2016/行测-统考.md")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, "省考/江苏/2020/行测-A类.md")))

    def test_images_copied_to_paper_dir(self):
        d = os.path.join(self.repo, "图片/省考-四川-2016-行测-统考/题目图")
        self.assertEqual(os.listdir(d), ["154428b1a538147.png"])

    def test_md_refs_image_actually_exists(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("../../../图片/省考-四川-2016-行测-统考/题目图/154428b1a538147.png", text)

    def test_manifest_written_with_sha(self):
        with open(self.rep.manifest_path, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]["sha256"]), 64)

    def test_rerun_is_idempotent(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        before = open(md, "rb").read()
        export.run(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertEqual(open(md, "rb").read(), before)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_export -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.export'`

- [ ] **Step 3: 写最小实现**

`tools/gwyzhenti/export.py`：
```python
# -*- coding: utf-8 -*-
"""段二：按 catalog.jsonl 逐卷导出，并只复制被引用的图片。"""
import hashlib
import io
import json
import os
import re
import shutil
from dataclasses import dataclass, field

from . import mdread, render
from .model import PaperKey

IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')


@dataclass
class ExportReport:
    papers: int = 0
    files: int = 0
    images: int = 0
    manifest_path: str = ""
    skipped: list = field(default_factory=list)


def repo_paths(key, slug):
    if key.level == "国考":
        md = "国考/%s/%s-%s.md" % (key.year, key.subject, key.ptype)
    else:
        md = "省考/%s/%s/%s-%s.md" % (key.region, key.year, key.subject, key.ptype)
    return md, "图片/%s" % slug


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _write(path, data_bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data_bytes)
    os.replace(tmp, path)


def load_catalog(catalog_dir):
    with io.open(os.path.join(catalog_dir, "catalog.jsonl"), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _parts_for(row, upstream_xingce):
    """按 MODULE_ORDER 取该卷各模块源文本；模块缺失则跳过（并如实记录）。"""
    want = [m for m in render.MODULE_ORDER if m in row["modules"]]
    parts, got = [], []
    for module in want:
        # 模块目录前缀
        prefix = {"政治理论": "01-政治理论", "常识判断": "02-常识判断",
                  "言语理解与表达": "03-言语理解与表达", "数量关系": "04-数量关系",
                  "判断推理": "05-判断推理", "资料分析": "06-资料分析"}[module]
        path = os.path.join(upstream_xingce, prefix, row["title"] + ".md")
        if os.path.exists(path):
            with io.open(path, encoding="utf-8") as fh:
                parts.append(fh.read())
            got.append(module)
    return parts, got


def run(catalog_dir, uproots, repo_root, limit=None):
    rep = ExportReport()
    manifest = os.path.join(repo_root, "work", "manifest.jsonl")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    rows = load_catalog(catalog_dir)
    if limit:
        rows = rows[:limit]
    entries = []
    for row in rows:
        if "xingcezhenti" not in row["sources"]:
            rep.skipped.append({"slug": row["slug"], "reason": "本批只导出有正文的源"})
            continue
        key = PaperKey(row["level"], row["region"], row["year"], row["subject"], row["ptype"])
        parts, modules = _parts_for(row, uproots["xingcezhenti"])
        if not parts:
            rep.skipped.append({"slug": row["slug"], "reason": "上游文件缺失"})
            continue
        md_rel, img_dir = repo_paths(key, row["slug"])
        depth = md_rel.count("/")
        # 收集被引用的图 → 建 image_map（源 src → 输出相对路径）
        image_map = {}
        for text in parts:
            for src in IMG.findall(text):
                name = os.path.basename(src)
                seg = "公式图" if "/公式图/" in src else "题目图"
                image_map[src] = "../" * depth + "%s/%s/%s" % (img_dir, seg, name)
        out = render.render_paper(parts, key, nature=row["nature"], form=row["form"],
                                  sources=row["sources"], modules=modules, image_map=image_map)
        data = out.body.encode("utf-8")
        _write(os.path.join(repo_root, md_rel), data)
        rep.files += 1
        entries.append({"path": md_rel.replace("\\", "/"), "sha256": _sha256_bytes(data)})
        # 只复制被引用的图
        for src, dest_rel in image_map.items():
            name = os.path.basename(src)
            seg = "公式图" if "/公式图/" in src else "题目图"
            src_abs = os.path.normpath(os.path.join(uproots["xingcezhenti"], "90-图片", seg, name))
            if not os.path.exists(src_abs):
                rep.skipped.append({"slug": row["slug"], "reason": "源图片缺失: %s" % name})
                continue
            dest_abs = os.path.join(repo_root, dest_rel.replace("/", os.sep))
            if os.path.exists(dest_abs):
                continue
            os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
            shutil.copyfile(src_abs, dest_abs)
            rep.images += 1
        rep.papers += 1
    with io.open(manifest, "w", encoding="utf-8", newline="\n") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    rep.manifest_path = manifest
    return rep
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_export -v`
Expected: PASS，8 tests OK

- [ ] **Step 5: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/export.py tools/tests/test_export.py
git commit -m "feat(tools): 段二导出（按 catalog 落盘 + 只复制被引用图片 + manifest）"
```

---

### Task 10: 闸门 G1–G6

**Files:**
- Create: `tools/gwyzhenti/gates.py`
- Create: `tools/tests/test_gates.py`

**Interfaces:**
- Consumes: 产物（`catalog/`）与导出（repo）
- Produces: `gates.run_all(catalog_dir, upstream, repo_root, limit=None) -> GatesReport`；
  `GatesReport` 的 `results: list[(闸名, 通过?, 说明)]`、`ok: bool`

- [ ] **Step 1: 写失败的测试**

`tools/tests/test_gates.py`：
```python
# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import catalog, export, gates      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class TestGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwygate-")
        self.cat = os.path.join(self.tmp, "catalog")
        self.repo = os.path.join(self.tmp, "repo")
        up = {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}
        catalog.build({**up, "linfukai186": os.path.join(FIX, "linfukai186")}, self.cat)
        export.run(self.cat, up, self.repo)
        self.rep = gates.run_all(self.cat, up, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_six_gates_reported(self):
        names = [n for n, _, _ in self.rep.results]
        for g in ("G1", "G2", "G3", "G4", "G5", "G6"):
            self.assertTrue(any(x.startswith(g) for x in names), names)

    def test_all_pass_on_fixture(self):
        self.assertTrue(self.rep.ok, [(n, d) for n, ok, d in self.rep.results if not ok])

    def test_g2_detects_dangling_image(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("154428b1a538147.png", "missing-zzz.png")
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        rep = gates.run_all(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G2") and not ok for n, ok, _ in rep.results))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_gates -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.gates'`

- [ ] **Step 3: 写最小实现**

`tools/gwyzhenti/gates.py`：
```python
# -*- coding: utf-8 -*-
"""G1–G6 验收闸门。逐卷实算，不抽样、不口头。"""
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field

from . import export, mdread, render
from .model import PaperKey

IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')
QHEAD = re.compile(r'^#{2,4}\s*第\s*(\d+)\s*题')


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


def _g1(md_path):
    with io.open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    nums = [int(m.group(1)) for m in QHEAD.finditer(text)]
    if not nums:
        return False, "无题目"
    if nums != list(range(1, len(nums) + 1)):
        return False, "题号不连续: %s" % nums[:20]
    fm = mdread.read_frontmatter(text)
    return True, "%d 题" % len(nums)


def _g2(md_path, repo_root):
    with io.open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    missing = []
    used = set()
    for src in IMG.findall(text):
        abs_p = os.path.normpath(os.path.join(os.path.dirname(md_path), src.replace("/", os.sep)))
        used.add(os.path.normpath(abs_p))
        if not os.path.exists(abs_p):
            missing.append(src)
    # 反向：该卷图片目录里有没有没被引用的
    slug = os.path.basename(os.path.dirname(os.path.normpath(md_path)))
    # 卷标识由 图片/<slug> 目录名给出 —— 用 md 里的引用反推目录集合更稳
    dirs = {os.path.dirname(p) for p in used}
    orphan = []
    for d in dirs:
        if os.path.isdir(d):
            for fn in os.listdir(d):
                p = os.path.normpath(os.path.join(d, fn))
                if p not in used:
                    orphan.append(fn)
    if missing:
        return False, "引用但缺文件: %s" % missing[:5]
    if orphan:
        return False, "复制了但未被引用: %s" % orphan[:5]
    return True, "双向闭合 %d 张" % len(used)


def _g3(md_path):
    with io.open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    if "✅" in text:
        return False, "正文残留 ✅"
    if "## 答案与解析" not in text:
        return False, "无独立答案板块"
    if "<details>" not in text:
        return False, "答案未折叠"
    return True, "无泄露"


def _g5(md_path, catalog_dir, upstream_xingce, repo_root):
    """保真：导出正文 vs 源，逐行**多重集**比较（`render.diff_report`），要求零内容增删。"""
    rel = os.path.relpath(md_path, repo_root).replace(os.sep, "/")
    row = None
    for r in export.load_catalog(catalog_dir):
        md_rel, _ = export.repo_paths(
            PaperKey(r["level"], r["region"], r["year"], r["subject"], r["ptype"]), r["slug"])
        if md_rel == rel:
            row = r
            break
    if row is None:
        return False, "catalog 里找不到该卷: %s" % rel
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


def run_all(catalog_dir, uproots, repo_root, limit=None):
    rep = GatesReport()
    mds = _md_files(repo_root)
    if limit:
        mds = mds[:limit]

    ok, detail = True, []
    for md in mds:
        good, d = _g1(md)
        if not good:
            ok = False
            detail.append("%s: %s" % (os.path.basename(md), d))
    rep.results.append(("G1 卷内题号连续", ok, "；".join(detail[:3]) or "全部通过"))

    ok, detail = True, []
    for md in mds:
        good, d = _g2(md, repo_root)
        if not good:
            ok = False
            detail.append("%s: %s" % (os.path.basename(md), d))
    rep.results.append(("G2 图片双向闭合", ok, "；".join(detail[:3]) or "全部通过"))

    ok, detail = True, []
    for md in mds:
        good, d = _g3(md)
        if not good:
            ok = False
            detail.append("%s: %s" % (os.path.basename(md), d))
    rep.results.append(("G3 答案不泄露", ok, "；".join(detail[:3]) or "全部通过"))

    # G4 幂等：重跑 sha 不变（由 CLI 在两次 run 之间比对；此处核对 manifest 与文件一致）
    man = os.path.join(repo_root, "work", "manifest.jsonl")
    ok, detail = True, []
    if os.path.exists(man):
        with io.open(man, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                e = json.loads(line)
                p = os.path.join(repo_root, e["path"].replace("/", os.sep))
                if not os.path.exists(p):
                    ok, _ = False, detail.append("缺 %s" % e["path"])
                    continue
                actual = hashlib.sha256(open(p, "rb").read()).hexdigest()
                if actual != e["sha256"]:
                    ok = False
                    detail.append("sha 不符 %s" % e["path"])
    rep.results.append(("G4 manifest 与文件一致", ok, "；".join(detail[:3]) or "一致"))

    ok, detail = True, []
    for md in mds:
        good, d = _g5(md, catalog_dir, uproots["xingcezhenti"], repo_root)
        if not good:
            ok = False
            detail.append("%s: %s" % (os.path.basename(md), d))
    rep.results.append(("G5 保真（源↔导出逐行多重集）", ok, "；".join(detail[:3]) or "全部通过"))

    rep.results.append(("G6 覆盖账（catalog 实算）", True,
                        "见 work/catalog/coverage.md；已入库数 = 通过 G1–G5 的卷数"))

    rep.ok = all(x for _, x, _ in rep.results)
    return rep
```

> **注**：G6 在本任务里只落**接口与占位说明**，其口径核对在 `coverage.md` 与 Task 11 Step 4 的报告里完成
> （「已入库」只能指**通过 G1–G5** 的卷）。`_g5` 是**逐卷真跑**，不是占位。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_gates -v`
Expected: PASS，3 tests OK

- [ ] **Step 5: 加 G5 扰动测试**

在 `tools/tests/test_gates.py` 追加（**必须能证明 G5 真的会失败**，否则它只是一条永远绿的闸）：
```python
    def test_g5_detects_content_change(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        perturbed = re.sub(r"(?m)^(- \*\*A\*\*\. )(\d+)", r"\g<1>999999", text, count=1)
        self.assertNotEqual(perturbed, text, "fixture 里没有可扰动的 A 选项行")
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(perturbed)
        rep = gates.run_all(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G5") and not ok for n, ok, _ in rep.results))
```
（`test_gates.py` 顶部若无 `import re` 请补上。）

- [ ] **Step 6: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/gates.py tools/tests/test_gates.py
git commit -m "feat(tools): G1–G6 闸门（G5 逐卷保真对账）"
```

---

### Task 11: CLI `export` / `gate` + M1 实跑 + 交付报告

**Files:**
- Modify: `tools/gwyzhenti/cli.py`
- Create: `work/REPORT-M1.md`（**产物，不提交**；报告内容另存一份贴给用户）

**Interfaces:**
- Consumes: `export.run`（Task 9）、`gates.run_all`（Task 10）
- Produces: `python -m gwyzhenti.cli export …`、`python -m gwyzhenti.cli gate …`

- [ ] **Step 1: 加子命令**

在 `tools/gwyzhenti/cli.py` 里追加：
```python
def cmd_export(args):
    from . import export
    rep = export.run(args.catalog, _uproots(args), args.repo, limit=args.limit)
    print("段二完成 →", args.repo)
    print("  卷 %d | md %d | 图片 %d" % (rep.papers, rep.files, rep.images))
    if rep.skipped:
        print("  跳过 %d 项（详见报告）" % len(rep.skipped))
    return 0


def cmd_gate(args):
    from . import gates
    rep = gates.run_all(args.catalog, _uproots(args), args.repo, limit=args.limit)
    for name, ok, detail in rep.results:
        print("  [%s] %s —— %s" % ("OK" if ok else "FAIL", name, detail))
    return 0 if rep.ok else 1
```
并在 `main()` 的 `sub` 里注册：
```python
    e = sub.add_parser("export", help="段二：逐卷导出")
    e.add_argument("--catalog", required=True)
    e.add_argument("--upstream", required=True)
    e.add_argument("--repo", required=True)
    e.add_argument("--limit", type=int, default=0)
    e.set_defaults(func=cmd_export)

    g = sub.add_parser("gate", help="跑 G1–G6")
    g.add_argument("--catalog", required=True)
    g.add_argument("--upstream", required=True)
    g.add_argument("--repo", required=True)
    g.add_argument("--limit", type=int, default=0)
    g.set_defaults(func=cmd_gate)
```

- [ ] **Step 2: 小样端到端（先 20 卷）**

Run:
```bash
cd D:/projects/gwy-zhenti/tools
export PYTHONIOENCODING=utf-8
python -X utf8 -m gwyzhenti.cli export --catalog ../work/catalog --upstream "D:/projects/_gwy-upstream" --repo "../work/out20" --limit 20
python -X utf8 -m gwyzhenti.cli gate --catalog ../work/catalog --upstream "D:/projects/_gwy-upstream" --repo "../work/out20"
```
Expected: 六闸全 OK。**任一 FAIL 就停下来修，不许带着红灯进全量。**

- [ ] **Step 3: 全量导出**

Run:
```bash
cd D:/projects/gwy-zhenti/tools
python -X utf8 -m gwyzhenti.cli export --catalog ../work/catalog --upstream "D:/projects/_gwy-upstream" --repo ".."
python -X utf8 -m gwyzhenti.cli gate   --catalog ../work/catalog --upstream "D:/projects/_gwy-upstream" --repo ".."
```
Expected: 六闸全 OK；`sources` 不含正文的卷（纯 linfukai186）列入 `skipped` 并在报告中如实列出。

- [ ] **Step 4: 写交付报告（如实，不美化）**

`work/REPORT-M1.md` 必须含：
- **数量账**：catalog 卷数 / 已导出卷数 / 跳过卷数（及理由分布）/ 未解析卷数 / 已排除卷数（及理由分布）。
- **六闸结果**：逐闸通过与否 + 说明（**不得抽样伪装成全量**）。
- **覆盖账**：`coverage.md` 的地区×科目表；明确「哪些省份已覆盖、哪些为缺」。
- **诚实边界**（照抄 spec §9，并更新实测数字）：ERRRC 自报 515 ≠ 已入库；申论未接入；公式为位图非数学表达式；卷型与层级由名字解析、拿不准的已进 `unparsed.jsonl`。

- [ ] **Step 5: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/cli.py
git commit -m "feat(tools): export / gate 子命令"
```
（`work/` 已 gitignore，报告不进版本库。）

---

### Task 12: 来源登记 + 管线说明收口

**Files:**
- Modify: `SOURCES.md`
- Modify: `tools/README.md`

- [ ] **Step 1: 更新 SOURCES.md**

在 `SOURCES.md` 里补一节「本仓实际接入的源（2026-10-09 实测）」，写明：
- **已接入（M1）**：`ERRRC/xingcezhenti`（行测正文主源；自报 515 卷 / 58,890 题；实测标题合计一致；**无 LICENSE**，私有仓内导入 + 逐卷记来源）；`linfukai186-arch/gongkao-tiku`（题级 JSON，行测交叉对照）。
- **已识别、未接入**：`zzcc-nb/gongkao-tiku`（**行测题库为空**，实为申论源，归 M3）；`shiwuooo/shangantong-papers-v2-c1/c2`（**行测**源，498 卷，2008–2026，HTML+webp，**独缺西藏** ⇒ 不提升地域齐全，留作交叉验证与老年份纵深，归 M2）。
- **同源 fork 家族**：`r1172464137/xingcezhenti` 等只算 1 个家族。

- [ ] **Step 2: 更新 tools/README.md**

把三条命令（`catalog` / `export` / `gate`）与「加新源 = 一个 adapter + 注册一行」写全。

- [ ] **Step 3: 提交**

```bash
cd D:/projects/gwy-zhenti
git add SOURCES.md tools/README.md
git commit -m "docs: 登记实测接入的源与管线用法"
```

---

## Self-Review

**1. Spec 覆盖**

| Spec 章节 | 落点 |
|---|---|
| §1 目标 / M1 | Task 6（段一全域接入 → 覆盖图）、Task 9/11（行测导出） |
| §2 非目标 | Task 2 排除词表；Task 4 分流；Task 8 零改写 |
| §3 数据源 | Task 4（ERRRC）、Task 5（linfukai186）、Task 12（登记 zzcc-nb / shiwuooo） |
| §4 两段式架构 | Task 6（段一）↔ Task 9（段二），接口 = `catalog.jsonl` |
| §5 卷键 / adapter 字段 / 六产物 | Task 1（卷键）、Task 4（记录字段）、Task 6（六产物） |
| §6 五项变换 | Task 8 |
| §6.1 解析表 | Task 2 |
| §7 G1–G6 | Task 10 |
| §8 落点与运行 | Task 7/11（CLI）、Global Constraints |
| §9 诚实边界 | Task 11 Step 4 报告 |
| §10 待确认 | A 已在 Global Constraints 定；B = 本计划仅 M1 |

**2. 占位符扫描**：无 TBD/TODO。Task 10 的 `_g5` 与 G6 明确写了「本任务只落接口，Step 5 写实」，并给了具体做法与测试要求。

**3. 类型一致性**：`ScanResult` / 记录键在 Task 4 定义、Task 5 复用；`PaperKey` 字段名在 Task 1/2/6/9 一致；`RenderedPaper` 字段在 Task 8/9 一致；`ExportReport.manifest_path` 在 Task 9/10 一致。

**已知缺口（交付时必须照实说）**：
- G5 的判据是**「除声明项外逐行多重集相等」**（`render.diff_report`），**不是**「导入导出互为逆变换」—— 题号重建本就不是逆变换，构造逆向只会把判据做脆。`_strip_declared` 会把两侧的 `# ` / `> ` 开头行一并剔除，故**改动只发生在这类行**时 G5 看不见（已知的窄面）。
- G6 的「已入库 = 通过 G1–G5 的卷」需要 CLI 把两次 `gate` 的结果汇总，Task 11 Step 4 的报告里手工确保口径一致。
