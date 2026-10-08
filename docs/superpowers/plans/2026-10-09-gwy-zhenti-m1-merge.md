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
- `图片缺失清单.txt` 实测 **2 行**（此前的「仅 1 行」是**误记**，Task 12 写的 2 行才对）：
  `90-图片/公式图/formula-4daf9a3762c10376.png` 与 `formula-2c7a9ff6774e3af2.png`。
  两行对应上游**引用得到、但 `90-图片/` 里没有**的两张图：前者只被 **2016 深圳市考**（**已排除**，
  不在 M1）引用 ⇒ **M1 实际只缺后者**；后者被 **2018 年 421 联考《行测》题（湖北卷）（网友回忆版）**
  引用 ⇒ **在 M1 交付范围内**。⇒ **交付报告必须写「M1 缺 1 张公式图」并点名**，不许声称「零缺失」。

**B. `linfukai186-arch/gongkao-tiku`（行测交叉对照 + 申论目录源，本机 `D:\projects\_gwy-upstream\gongkao-tiku`）**

- `data/<类>/index.json` = `[{"key":"<卷标识>","count":N}, …]`
- `data/<类>/y<YYYY>.json` = `{"<卷标识>":[{"t":"<模块>","s":"<材料>","q":"<题干>","o":["选项",…],"a":"<答案>","e":"<解析>"}, …]}`（申论类**无 `o`/`e`**，题形为 `{t,s,q,a}`）
- **四类实测**（逐一量过 `index.json`）：`guokao-xingce` 48 键 / 2000–2027；`shengkao-xingce` 560 键 / 2004–2025；
  `guokao-shenlun` 59 键但 **100% 含「模考」⇒ 真卷 0**；`shengkao-shenlun` 808 键、**真卷 686** / 2010–2026。
  ⇒ 它是 spec §9 所称「最大缺口」的**实际申论目录源**，**四个类目全部接入**（申论在 M1 只入 catalog）。
- 卷标识样例：`2026·国家公务员考试行政执法`、`2016·423四川公务员考试《行测》题`、`2026·国考行测申论联合模考大赛（第四十季）`（**模考须排除**）。
- **卷名里的地区不一定在开头**：实测有 `4月吉林公务员考试…`（月份前缀）、`公务员录用考试《行测》甘肃真题`（地区在中间）、
  `2020·度浙江省党政机关选调…`（`年度` 的残尾）。⇒ **禁止 `[:2]` 切片**（会把 `黑龙江` 切成 `黑龙`、把 `0822` 切成 `08`），
  一律走 `naming.region_from_text` 的**全串最长匹配**。

**C. 已判定的范围事实**

- `zzcc-nb/gongkao-tiku`：`行测题库/`、`职测题库/` **为空**（README 自述「待采集」）⇒ **申论源，归 M3**，不进 M1。
- `shiwuooo/shangantong-papers-v2-c1/c2`：**行测源（非申论）**，每卷 `paper_*/{index.html,index_static.html,assets/*.webp}`，共 **496 卷**（Task 12 本机实测：c1 310 + c2 186；原稿写 498 是**误记**）、**2008–2026**，`<title>` 即卷名；地区覆盖 30 省 + 国考，**独缺西藏**（ERRRC 有）⇒ **不提升「地域齐全」**，价值在交叉验证与老年份纵深。**归 M2，M1 不接。**
- `linfukai186` 的**申论侧在 M1 接入 catalog**：M1 的定义是「段一接入全部候选源（行测 + 申论）」，漏掉 `shengkao-shenlun`
  的 686 份真题，`coverage.md` 的申论列就会是假空白，M3 还得重做段一。**`zzcc-nb` 仍留 M3** —— 它的粒度是逐题、
  与 `linfukai186` 的逐卷不同层，适配器写法要等 M3 的导出设计定了再定；段一是**可增量重跑**的，后加 adapter 只是再跑一次扫描，不是"重做"。

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
│  │  │  └─ linfukai186.py          # 行测交叉对照 + 申论目录源
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
        # 否则**逐字保留**。
        # ⚠️ 本测试的原断言（`省直卷` ≠ `省直`）**已被裁定 R-T6-1 取代**：`省直` 现在**在**词表里，
        # 故 `（省直）` 与 `（黑龙江省直卷）` **归一为同一个值**。原断言的依据（「真库同时存在
        # 这两者」）**实测不成立** —— `（省直）` 只在 2018、`（黑龙江省直卷）` 只在 2019，
        # **从不同年** ⇒ 本就不同 `PaperKey`，归一零碰撞风险；且归一**反而消除了**一组撞键
        # （此前 linfukai 侧回落 `统考`，与 xingcezhenti 侧的 `省直` 撞上）。
        # 窄容差这条**原则**仍在：下面用一个**确实不在词表**的 token 证明它。
        self.assertEqual(classify("国考", "2026", "…（行政执法卷网友回忆版）").key.ptype, "行政执法")
        shi = classify("黑龙江", "2018", "…（省直）").key.ptype
        hl = classify("黑龙江", "2019", "…（黑龙江省直卷）").key.ptype
        self.assertEqual(shi, "省直")
        self.assertEqual(hl, "省直")          # 归一（R-T6-1）
        # 不落词表的 token ⇒ **逐字保留**，不剥「卷」
        self.assertEqual(classify("黑龙江", "2016", "…（县级、乡镇统一卷）").key.ptype,
                         "县级、乡镇统一卷")

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
# 词表 = spec §卷型归一表（`:137` 的第一张表 + `:141-144` **实测**的后缀词表）。
# ⚠️ **顺序有讲究**：`县级以上` 必须排在 `县级卷|县级` 之前，`定向乡镇` 必须排在 `乡镇卷|乡镇` 之前 ——
# 否则前者的 search 会被更短的后者抢先命中 ⇒ 卷型判错 ⇒ **可能撞 slug**（见下）。
# （裁定 R-T6-1：`:141-144` 那批后缀词原先没进代码，实测导致 **2016+ 行测 30 条真撞键** ——
# 两份不同的卷（甲卷/乙卷、县乡卷/省直卷、兵团/非兵团…）全部回落 `统考`，算出同一个 slug。）
PTYPE_RULES = (
    (re.compile(r"副省级"), "副省级"),
    (re.compile(r"地市级"), "地市级"),
    (re.compile(r"行政执法"), "行政执法"),
    (re.compile(r"A类|A卷"), "A类"),
    (re.compile(r"B类|B卷"), "B类"),
    (re.compile(r"C类|C卷"), "C类"),
    (re.compile(r"D类|D卷"), "D类"),
    # —— spec :141-144 实测的后缀词表（R-T6-1 补入）——
    (re.compile(r"甲级|甲卷"), "甲级"),
    (re.compile(r"乙级|乙卷"), "乙级"),
    (re.compile(r"上半年"), "上半年"),
    (re.compile(r"下半年"), "下半年"),
    (re.compile(r"县乡卷|县乡"), "县乡卷"),
    (re.compile(r"省直卷|省直"), "省直"),
    (re.compile(r"兵团"), "兵团"),
    (re.compile(r"县级以上"), "县级以上"),
    (re.compile(r"区级及以上"), "区级及以上"),
    (re.compile(r"定向乡镇"), "定向乡镇"),
    (re.compile(r"单考区卷"), "单考区卷"),
    # —— 原有的两级，必须排在「定向乡镇」「县级以上」之后 ——
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

    尾缀 `卷` 的容差是**窄的**：只在剥掉后能落回 `PTYPE_VALUES` 时才剥 ——
    真库里有 `（县级、乡镇统一卷）` 这种 token，其「剥掉卷」后的形态**不在**词表里 ⇒
    必须**逐字保留**，不得收敛。
    ⚠️ 本 docstring 原先举的例子是「`（省直）` 与 `（黑龙江省直卷）` 同时存在」，**该依据实测不成立**
    （两者分别在 2018 / 2019，从不同年 ⇒ 本就不同键）；`省直` 现已进词表，两者**归一**（裁定 R-T6-1）。
    窄容差这条**原则**不受影响，只是换了个真实例子。
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

    UNPARSED = "unparsed"    # 缺陷：必须被 G1 盯住
    EXCLUDED = "excluded"    # 有意排除：spec §2 非目标

    def __init__(self, reason, title="", kind=UNPARSED):
        super().__init__("%s | %s" % (reason, title))
        self.reason = reason
        self.title = title
        self.kind = kind


@dataclass(frozen=True)
class Classified:
    key: PaperKey
    nature: str
    form: str


def classify(region, year, title, subject="行测"):
    title = title or ""
    # **检查顺序是有意的**：排除族 → 标题排除词 → 地区为空。
    # 理由（Task 5 修复轮实测）：模考/选调这类卷是 spec §2 的**非目标**（有意排除），
    # 而它们常常**根本没有地区**（实测 `2021·省考行测申论联合终极模考大赛`，共 56 条）。
    # 若把「地区为空」放在最前，这些卷会在走到标题判断**之前**就抛错 ⇒ 落进
    # `unparsed`（**G1 盯的缺陷桶**），而 `unparsed` 长期非零会让人习惯性忽略它 ——
    # 缺陷桶就废了。`模考` 由 `EXCLUDE_TITLE` 判定，故必须让它**先**有机会命中。
    if region in EXCLUDE_REGIONS:
        raise Unparsed("非国省考地区: %s" % region, title, kind=Unparsed.EXCLUDED)
    m = EXCLUDE_TITLE.search(title)
    if m:
        raise Unparsed("试卷名含排除词: %s" % m.group(0), title, kind=Unparsed.EXCLUDED)
    if not region:
        raise Unparsed("地区字段为空", title)

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
  - `split_answer(block) -> tuple[list[str], list[str], list[str]]`（`(题干行, 答案行, 尾行)`；**尾行去掉尾随空行**，行内空行保留）
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

---
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
CS = os.path.join(FIX, "02-常识判断", "2016年423联考《行测》题（四川卷）.md")


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

    def test_tail_drops_trailing_blanks_but_keeps_material(self):
        # 尾行是 Task 8 把 `## 材料 N` 及其图片**送回正文**的通道 —— 只丢尾随空行，
        # 行内空行与内容行必须原样保留（`split("\n")` 会为文件末尾换行多产一个 ""）
        block = ["### 第 1 题　<sub>qid 1 · 综合</sub>",
                 "- **A**. 340.2",
                 "**答案**：A",
                 "",
                 "---",
                 "",
                 "## 材料 2",
                 "",
                 '<img width="700px" height="173px" src="../90-图片/题目图/154428b1a538147.png" />',
                 "",
                 ""]
        stem, ans, tail = mdread.split_answer(block)
        self.assertEqual(stem[:2], ["### 第 1 题　<sub>qid 1 · 综合</sub>", "- **A**. 340.2"])
        self.assertEqual(ans, ["**答案**：A", "", "---"])
        self.assertEqual(tail, ["",
                                "## 材料 2",
                                "",
                                '<img width="700px" height="173px" src="../90-图片/题目图/154428b1a538147.png" />'])

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

    def test_commonsense_fixture_uses_h2_and_terminating_separator(self):
        # 02-常识判断 真源用 `## 第 N 题`（两个井号）且**末块也以 `---` 收尾** —— 这是
        # `QHEAD` 的 `#{2,4}` 与 `split_answer` 的 `---` 切分在真实 02 文件上的形态；
        # 若 fixture 末块漏了 `---`，答案会整块落进题干、`ans` 为空（本测试正是为此而设）
        text = load(CS)
        self.assertEqual(mdread.count_questions(text), 1)
        _, blocks = mdread.split_question_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0][0].startswith("## 第 1 题"))
        stem, ans, tail = mdread.split_answer(blocks[0])
        self.assertTrue(any(ln.startswith("**答案**：B") for ln in ans))
        self.assertTrue(any("官方解析" in ln for ln in ans))
        self.assertEqual(tail, [])
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
    **尾随空行不计入尾行** —— 题块之间与文件末尾的空行是 `split("\\n")` 的排版噪声，不是内容
    （文件末尾的换行会多切出一个空串）；**行内空行保留**，`## 材料 N` 与其图片之间的空行属于正文结构。
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
    tail = block[end + 1:]
    while tail and not tail[-1].strip():
        tail.pop()
    return block[:start], block[start:end + 1], tail


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
Expected: PASS，12 tests OK

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

@dataclass
class ScanResult:
    # records 每条 = **卷×模块** 粒度，键固定为：
    #   family / title / region / year / module / n_questions / relpath /
    #   images_题目 / images_公式 / declared_questions
    # `declared_questions` = 源 frontmatter 自报题数（非数字则 -1），**只供 G1 对账，不参与导出**。
    records: list = field(default_factory=list)
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
            # 分流**只认 `exc.kind`，不认 `reason` 文本**（Task 4 修复轮 2 的结论，有回归测试护栏）：
            # **有意排除**（非国省考地区 / 试卷名含排除词）kind=EXCLUDED 进 excluded；
            # **解析不了**（如「地区字段为空」）kind=UNPARSED 是缺陷，必须进 unparsed 被 G1 盯住。
            # 若改回按 `reason.startswith(...)` 分流，将来新增的陌生 reason 会被**静默**错分进 excluded。
            bucket = res.unparsed if exc.kind == Unparsed.UNPARSED else res.excluded
            bucket.append({
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

> 说明：`classify` 在这里**只用于筛除**（排除项进 `excluded`）；是否进 `unparsed` 由 `classify` 抛出的
> `Unparsed.kind` 决定 —— `kind == Unparsed.EXCLUDED`（非国省考地区 / 试卷名含排除词）入 `excluded`，
> `kind == Unparsed.UNPARSED`（如「地区字段为空」）入 `unparsed`。**分流判据是 `kind`，不是 `reason` 文本**；
> 上面 `_one` 的写法即最终形态。

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

### Task 5: `linfukai186` adapter（行测交叉对照 + 申论目录）

> **本任务相对初稿已按实测重写**（见 spec §3「2026-10-09 二次实测」）。两处改动是**硬需求**，不是优化：
> ① 原稿只接行测两类，漏掉 `shengkao-shenlun` 的 **686 份省考申论真题** —— 而 M1 的定义就是
> 「段一接入全部候选源（行测 + 申论）」；② 原稿用 `title.split("·")[1][:2]` 取地区，是**切片**：
> 实测卷名里地区**不一定在开头**（`4月吉林公务员考试…`、`公务员录用考试《行测》甘肃真题`），
> 切片会把 `黑龙江` 变成 `黑龙`、把联考日期码 `0822` 变成 `08`；而 `classify` **不校验省份**
> ⇒ 脏地区会**静默写进 catalog**。本任务改用 `naming` 里的地区别名表 + **全串最长匹配**。

**Files:**
- Modify: `tools/gwyzhenti/naming.py`（新增地区别名表 + 两个纯函数）
- Create: `tools/gwyzhenti/sources/linfukai186.py`
- Create: `tools/tests/fixtures/linfukai186/data/guokao-xingce/index.json`
- Create: `tools/tests/fixtures/linfukai186/data/guokao-xingce/y2026.json`
- Create: `tools/tests/fixtures/linfukai186/data/shengkao-xingce/y2016.json`
- Create: `tools/tests/fixtures/linfukai186/data/shengkao-shenlun/y2016.json`
- Create: `tools/tests/test_src_linfukai186.py`
- Modify: `tools/tests/test_naming.py`（新增地区解析测试）
- Modify: `tools/gwyzhenti/sources/__init__.py`
- Create: `tools/tests/smoke_linfukai186.py`（手工冒烟，不进 `unittest discover`）

**Interfaces:**
- Consumes: `ScanResult`（Task 4）、`classify` / `Unparsed`（Task 2，`Unparsed.kind` 由 Task 4 的修复轮引入）
- Produces:
  - `naming.PROVINCES: tuple[str, ...]`（按长度倒序）
  - `naming.region_exclusion(text) -> str | None`（卷名 → 要排除的地区值）
  - `naming.region_from_text(text) -> str | None`（卷名 → 地区；认不出返回 `None`）
  - `Linfukai186Adapter`（`family = "linfukai186"`），记录键与 Task 4 **完全一致**（含 `subject`）；
    `n_questions` = 该**模块**的题级条目数（此源无「题数」字段，故 `declared_questions = -1`）

- [ ] **Step 1: `naming.py` 加地区别名表**

在 `naming.py` 里 `EXCLUDE_REGIONS` 之后追加（`EXCLUDE_REGIONS` 本身**加一个成员** `"公安院校"` —— 与 `公检法` 同族，见 Task 2 的裁定）：

```python
# 卷名里出现「地区」时的排除族。**值必须是 `EXCLUDE_REGIONS` 的成员** ——
# 这样 adapter 只需把 `region_exclusion()` 的结果交给 `classify`，排除逻辑只有一处。
REGION_EXCLUDE_RULES = (
    (re.compile(r"选调"), "选调"),
    (re.compile(r"深圳"), "深圳市考"),
    (re.compile(r"广州"), "广州市考"),
    (re.compile(r"公安院校"), "公安院校"),
)
# 23 省 + 5 自治区 + 4 直辖市。**按长度倒序**：保证 `黑龙江` 不被更短的别名先命中。
# 深圳/广州是**市**不是省 —— 它们只走上面的排除族，不进这张表。
PROVINCES = tuple(sorted((
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建",
    "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州",
    "云南", "陕西", "甘肃", "青海",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
), key=len, reverse=True))
GUOKAO_TEXT = re.compile(r"国家公务员|国家公考|国考")
LIANKAO_TEXT = re.compile(r"多省联考|联考")


def region_exclusion(text):
    """卷名文本 → 要排除的地区值；没有则 `None`。"""
    for rx, value in REGION_EXCLUDE_RULES:
        if rx.search(text):
            return value
    return None


def region_from_text(text):
    """卷名文本 → 地区。**全串最长匹配，绝不切片。**

    实测卷名里地区**不一定在开头**（`9月吉林公务员考试《行测》甲级`、
    `公务员录用考试《行测》甘肃真题`、`2020年度浙江省…`），切 `[:2]` 会把 `黑龙江` 截成
    `黑龙`、把联考日期码 `0822` 截成 `08`；而 `classify` **不校验省份**（只在 `EXCLUDE_REGIONS`
    三值上抛错）⇒ 脏地区会**静默写进 catalog**。故只认词表命中，认不出返回 `None`，
    由调用方抛 `Unparsed`。
    """
    if GUOKAO_TEXT.search(text):
        return LEVEL_GUOKAO
    for p in PROVINCES:
        if p in text:
            return p
    if LIANKAO_TEXT.search(text):
        # 无省份的多省联考卷（实测 `2016·公务员多省联考`）。**不猜省份** —— 填一个
        # 非省份的类别值，catalog 里一眼可辨。
        return "多省联考"
    return None
```

- [ ] **Step 2: 建微型样本（四类都要有）**

`tools/tests/fixtures/linfukai186/data/guokao-xingce/index.json`（**用来验证 `index.json` 被跳过**）：
```json
[{"key":"2026·国家公务员考试行政执法","count":2},{"key":"2026·国考行测申论联合模考大赛（第四十季）","count":1}]
```

`tools/tests/fixtures/linfukai186/data/guokao-xingce/y2026.json`：
```json
{
  "2026·国家公务员考试行政执法": [
    {"t":"政治理论","s":"","q":"下列说法正确的是：","o":["甲","乙","丙","丁"],"a":"B","e":"乙正确。"},
    {"t":"资料分析","s":"","q":"增长率约为：","o":["5%","7%"],"a":"B","e":"计算得7%。"}
  ],
  "2026·国考行测申论联合模考大赛（第四十季）": [
    {"t":"公文写作题","s":"材料1","q":"请拟写一份通知。","o":[],"a":"","e":""}
  ]
}
```

`tools/tests/fixtures/linfukai186/data/shengkao-xingce/y2016.json`（四个键各自钉一个危险点：
**3 字省名**、**地区在中间且前面有日期码**、**深圳市考须排除**、**无省份的多省联考**）：
```json
{
  "2016·黑龙江公务员考试《行测》题": [
    {"t":"常识判断","s":"","q":"下列属于……的是：","o":["甲","乙"],"a":"A","e":"甲正确。"}
  ],
  "2016·423四川公务员考试《行测》题": [
    {"t":"数量关系","s":"","q":"……是多少？","o":["1","2"],"a":"C","e":"略。"}
  ],
  "2016·深圳市公务员考试《行测》真题": [
    {"t":"言语理解与表达","s":"","q":"……","o":["甲"],"a":"A","e":"略。"}
  ],
  "2016·公务员多省联考《行测》题": [
    {"t":"判断推理","s":"","q":"……","o":["甲"],"a":"A","e":"略。"}
  ]
}
```

`tools/tests/fixtures/linfukai186/data/shengkao-shenlun/y2016.json`（钉三件事：**申论科目由目录决定**、
**申论目录里可以躺着国考卷**（实测 `shengkao-shenlun` 里有 46 个 `国家公考` 键）、
以及**无地区的模考卷进 `excluded` 而非 `unparsed`**（真实数据 56 条的同形样本））：
```json
{
  "2016·黑龙江公务员考试《申论》题": [
    {"t":"归纳概括题","s":"材料1\n……","q":"请概括……","a":"参考答案……"},
    {"t":"文章写作题","s":"材料2\n……","q":"请以……为题写一篇文章。","a":"范文……"}
  ],
  "2016·国家公考《申论》题（副省级）": [
    {"t":"综合分析题","s":"材料1\n……","q":"请分析……","a":"参考答案……"}
  ],
  "2016·省考行测申论联合模考大赛《申论》": [
    {"t":"归纳概括题","s":"材料1","q":"请概括……","a":"参考答案……"}
  ]
}
```

- [ ] **Step 3: 写失败的测试**

`tools/tests/test_src_linfukai186.py`：
```python
# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.linfukai186 import Linfukai186Adapter      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "linfukai186")

# 与 Task 4 的 `base.py` 契约**完全一致**（多一个 `subject` 就会在下游 KeyError）
RECORD_KEYS = {
    "family", "title", "region", "year", "subject", "module", "n_questions",
    "relpath", "images_题目", "images_公式", "declared_questions",
}
BUCKET_KEYS = {"family", "title", "region", "year", "subject", "module", "relpath", "reason"}


class TestLinfukai186Adapter(unittest.TestCase):
    def setUp(self):
        self.res = Linfukai186Adapter().scan(FIX)
        self.by = {(r["title"], r["module"]): r for r in self.res.records}

    def test_no_unparsed_for_clean_fixture(self):
        # 本 fixture **有意只放能判出地区的键** ⇒ 零未解析。真实数据的账另有断言（见 Step 7 哨兵）：
        # 四个类目共 1,475 个键，其中 56 条是**无地区的模考卷**，按 `classify` 的新检查顺序落
        # `excluded`（有意排除）而非 `unparsed` —— 所以**不是**「地区全部可判」。
        self.assertEqual(self.res.unparsed, [])

    def test_guokao_paper_has_two_modules(self):
        got = [r for r in self.res.records if r["title"] == "2026·国家公务员考试行政执法"]
        self.assertEqual(len(got), 2)
        self.assertEqual({r["module"] for r in got}, {"政治理论", "资料分析"})
        self.assertEqual({r["region"] for r in got}, {"国考"})
        self.assertEqual({r["subject"] for r in got}, {"行测"})

    def test_three_char_province_is_not_truncated(self):
        # `[:2]` 会把 `黑龙江` 切成 `黑龙` —— 这条测试就是钉死它
        r = self.by[("2016·黑龙江公务员考试《行测》题", "常识判断")]
        self.assertEqual(r["region"], "黑龙江")
        self.assertEqual(r["year"], "2016")

    def test_province_found_after_date_code(self):
        # 实测存在 `2016·423四川…` / `2016·0822…`：地区在日期码**之后**
        r = self.by[("2016·423四川公务员考试《行测》题", "数量关系")]
        self.assertEqual(r["region"], "四川")

    def test_shenlun_subject_comes_from_directory(self):
        a = self.by[("2016·黑龙江公务员考试《申论》题", "归纳概括题")]
        b = self.by[("2016·黑龙江公务员考试《申论》题", "文章写作题")]
        self.assertEqual(a["subject"], "申论")
        self.assertEqual(b["subject"], "申论")
        self.assertEqual(a["n_questions"], 1)

    def test_shenlun_dir_can_hold_a_guokao_paper(self):
        # 实测 `shengkao-shenlun` 里有 46 个 `国家公考` 键 ⇒ 地区取自**卷名**，不取自目录
        r = self.by[("2016·国家公考《申论》题（副省级）", "综合分析题")]
        self.assertEqual(r["region"], "国考")
        self.assertEqual(r["subject"], "申论")

    def test_multi_province_liankao_gets_its_own_region_value(self):
        r = self.by[("2016·公务员多省联考《行测》题", "判断推理")]
        self.assertEqual(r["region"], "多省联考")

    def test_mock_and_shenzhen_are_excluded_not_unparsed(self):
        reasons = sorted(e["reason"].split(":")[0].strip() for e in self.res.excluded)
        self.assertEqual(reasons, sorted(["试卷名含排除词", "试卷名含排除词", "非国省考地区"]))
        self.assertEqual(len(self.res.excluded), 3)

    def test_regionless_mock_paper_lands_in_excluded_not_unparsed(self):
        """无地区 + 含「模考」⇒ **有意排除**，不是缺陷。

        真实数据实测 56 条这类卷（100% 在 `shengkao-shenlun`，100% 含「模考」）。
        若 `classify` 把「地区为空」检查挪回**标题排除词之前**，本条会变红 —— 这就是它的用途。
        """
        titles = {e["title"] for e in self.res.excluded}
        self.assertIn("2016·省考行测申论联合模考大赛《申论》", titles)
        self.assertEqual(self.res.unparsed, [])

    def test_record_and_bucket_keys_are_frozen(self):
        for r in self.res.records:
            self.assertEqual(set(r), RECORD_KEYS)
        for e in self.res.excluded + self.res.unparsed:
            self.assertEqual(set(e), BUCKET_KEYS)

    def test_index_json_is_not_parsed_as_a_year_file(self):
        # index.json 是 list，若被当 `y<年>.json` 读取，`papers.items()` 会 AttributeError
        self.assertTrue(all(r["relpath"].endswith(".json") for r in self.res.records))
        self.assertFalse(any(r["relpath"].endswith("index.json") for r in self.res.records))
```

`tools/tests/test_naming.py` **追加**（放在已有测试类之后，import 行补 `region_exclusion, region_from_text`）：
```python
class TestRegionFromText(unittest.TestCase):
    def test_longest_match_beats_truncation(self):
        self.assertEqual(region_from_text("黑龙江公务员录用考试《行测》题"), "黑龙江")
        self.assertEqual(region_from_text("9月吉林公务员考试《行测》甲级"), "吉林")

    def test_region_may_sit_after_a_date_code(self):
        self.assertEqual(region_from_text("423四川公务员考试《行测》题"), "四川")
        self.assertEqual(region_from_text("0822河南公务员考试《行测》题"), "河南")

    def test_guokao_variants(self):
        self.assertEqual(region_from_text("国家公务员考试行政执法"), "国考")
        self.assertEqual(region_from_text("国家公考《申论》题（副省级）"), "国考")

    def test_liankao_without_province_is_its_own_value(self):
        self.assertEqual(region_from_text("公务员多省联考《行测》题"), "多省联考")

    def test_unknown_returns_none(self):
        self.assertIsNone(region_from_text("公安院校联考"))

    def test_exclusion_is_checked_before_region(self):
        self.assertEqual(region_exclusion("深圳市公务员考试《行测》题"), "深圳市考")
        self.assertEqual(region_exclusion("广州市公务员考试《行测》真题"), "广州市考")
        self.assertEqual(region_exclusion("2025·四川省考_选调公务员录用考试"), "选调")
        self.assertIsNone(region_exclusion("黑龙江省公务员考试"))
```

- [ ] **Step 4: 跑测试确认失败**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_src_linfukai186 tests.test_naming -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'gwyzhenti.sources.linfukai186'`

- [ ] **Step 5: 写最小实现**

`tools/gwyzhenti/sources/linfukai186.py`：
```python
# -*- coding: utf-8 -*-
"""linfukai186-arch/gongkao-tiku adapter：题级 JSON，按 **卷标识** 归组。

四个类目：`guokao-xingce` / `shengkao-xingce`（行测）、`guokao-shenlun` / `shengkao-shenlun`（申论）。
**科目由目录决定，地区由卷名决定** —— 实测 `shengkao-shenlun` 里有 46 个 `国家公考` 键，
反过来也会成立，故两者不可互相推导。此源**无卷型字段、无卷级图片**（图片按题级文本实测计数，
实测多为 0）。行测用于覆盖交叉对照；申论在 M1 只入 catalog，**不给正文**。
"""
import json
import os
import re

from ..naming import Unparsed, classify, region_exclusion, region_from_text
from .base import ScanResult, SourceAdapter

FAMILY = "linfukai186"

# (目录名, 科目) —— 实测四类都存在；`guokao-shenlun` 的键 100% 含「模考」，会全数进 excluded，
# 仍然接入：excluded 台账本身就是对账证据。
CATS = (
    ("guokao-xingce", "行测"),
    ("shengkao-xingce", "行测"),
    ("guokao-shenlun", "申论"),
    ("shengkao-shenlun", "申论"),
)
YEAR_RE = re.compile(r"^y(\d{4})\.json$")
YEAR_IN_KEY = re.compile(r"(\d{4})")
# 题级文本里出现即计一次（实测本机样本多为 0；不假设，按内容数）
IMGISH = re.compile(r"<img|\.png|\.jpg|\.jpeg|\.webp|/media/")


class Linfukai186Adapter(SourceAdapter):
    family = FAMILY

    def scan(self, root):
        res = ScanResult()
        for cat, subject in CATS:
            cat_dir = os.path.join(root, "data", cat)
            if not os.path.isdir(cat_dir):
                continue
            for name in sorted(os.listdir(cat_dir)):
                m = YEAR_RE.match(name)
                if not m:
                    continue                      # index.json 等非 `y<年>.json` 一律跳过
                self._one(os.path.join(cat_dir, name),
                          "data/%s/%s" % (cat, name), m.group(1), subject, res)
        return res

    def _one(self, abspath, relpath, fallback_year, subject, res):
        with open(abspath, encoding="utf-8") as fh:
            papers = json.load(fh)
        for title, items in papers.items():
            if not items:
                continue
            m = YEAR_IN_KEY.search(title)
            year = m.group(1) if m else fallback_year
            rest = title.split("·", 1)[1] if "·" in title else title
            # 排除族先于地区匹配：`2025·深圳行测申论联合终极模考大赛` 两个族都命中，
            # 报「非国省考地区」比报「模考」更贴近它的身份。
            region = region_exclusion(rest) or region_from_text(rest) or ""
            try:
                # **不要在此预判「地区为空」**（本任务初稿曾写 `if not region: raise ...`）：
                # 模考卷（实测 `2021·省考行测申论联合终极模考大赛`，56 条）**往往没有地区**，
                # 预判会让它们在 `classify` 之前就抛错、落进 `unparsed`（**G1 盯的缺陷桶**），
                # 而它们其实是 spec §2 的**有意排除**。一律交给 `classify`，由它的
                # **检查顺序**（排除族 → 标题排除词 → 地区为空）给出正确的 `kind`。
                classify(region, year, title, subject=subject)
            except Unparsed as exc:
                # 用**结构化判据** `exc.kind`，不比对 reason 前缀（前缀会在新增 reason 时错分）
                bucket = res.unparsed if exc.kind == Unparsed.UNPARSED else res.excluded
                bucket.append({
                    "family": FAMILY, "title": title, "region": region, "year": year,
                    "subject": subject, "module": "", "relpath": relpath,
                    "reason": exc.reason,
                })
                continue
            n_by_module, img_by_module = {}, {}
            for it in items:
                mod = it.get("t", "")
                n_by_module[mod] = n_by_module.get(mod, 0) + 1
                n_img = len(IMGISH.findall(json.dumps(it, ensure_ascii=False)))
                if n_img:
                    img_by_module[mod] = img_by_module.get(mod, 0) + n_img
            for module, n in n_by_module.items():
                res.records.append({
                    "family": FAMILY, "title": title, "region": region, "year": year,
                    "subject": subject, "module": module, "n_questions": n,
                    "relpath": relpath, "images_题目": img_by_module.get(module, 0),
                    "images_公式": 0, "declared_questions": -1,
                })
```

`tools/gwyzhenti/sources/__init__.py`（整体替换）：
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

- [ ] **Step 6: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8 -m unittest discover -s tests -v`
Expected: PASS，全部通过（`test_naming` 由 17 增至 23，`test_src_linfukai186` 新增 10 条；条数不符以实际为准，不许为凑数增删测试）

- [ ] **Step 7: 真库冒烟（冻结哨兵）**

写 `tools/tests/smoke_linfukai186.py`（**不作为 unittest**；不用 `python -c`，免得引号被 shell 吃掉）：
```python
# -*- coding: utf-8 -*-
"""真库冒烟：读本机 gongkao-tiku 克隆，核对四个类目的分桶。手工运行。

`unparsed == 0` 是**实测结论**（四个类目共 **1,475** 个键 —— 48+560+59+808；
`guokao-shenlun` 那 59 个初稿漏数过）。**若它不为 0**，先分辨两种成因：
- 键的地区**根本判不出**且标题也不含排除词 ⇒ 地区别名表**漏词**，**补表**，别放宽断言；
- 键是**模考/选调**这类非目标卷（实测 56 条，全在 `shengkao-shenlun`、全部含「模考」、
  **全部没有地区**）⇒ 它们应经 `classify` 的**标题排除词**判定落进 `excluded`。
  若它们出现在 `unparsed` 里，说明 `classify` 的检查顺序被改坏了，**修顺序**，不是补表。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.linfukai186 import Linfukai186Adapter      # noqa: E402

ROOT = r"D:\projects\_gwy-upstream\gongkao-tiku"


def main():
    res = Linfukai186Adapter().scan(ROOT)
    per = {}
    for r in res.records:
        k = (r["subject"], r["region"])
        per[k] = per.get(k, 0) + r["n_questions"]
    print("records %d | unparsed %d | excluded %d | 题数合计 %d"
          % (len(res.records), len(res.unparsed), len(res.excluded),
             sum(r["n_questions"] for r in res.records)))
    for subj in ("行测", "申论"):
        rows = [r for r in res.records if r["subject"] == subj]
        provs = sorted({r["region"] for r in rows})
        print("  %s: %d 卷·模块行 | %d 个地区 | 地区: %s"
              % (subj, len(rows), len(provs), " ".join(provs)))
    reasons = {}
    for e in res.excluded:
        reasons[e["reason"].split(":")[0].strip()] = \
            reasons.get(e["reason"].split(":")[0].strip(), 0) + 1
    for k in sorted(reasons):
        print("  excluded %4d  %s" % (reasons[k], k))

    assert res.unparsed == [], "地区别名表漏词：%s" % [u["title"] for u in res.unparsed[:5]]
    assert [r for r in res.records if r["subject"] == "行测"], "行测一条都没有："
    assert [r for r in res.records if r["subject"] == "申论"], "申论一条都没有："


if __name__ == "__main__":
    main()
```

Run:
```bash
cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 tests/smoke_linfukai186.py
```
Expected: `unparsed 0`；行测、申论两个科目**都有**非零记录；`excluded` 理由分布含
`非国省考地区` 与 `试卷名含排除词`（后者应含那 56 条无地区的模考卷）。
**把打印出的 `records` / `excluded` 实际数字回填成断言**（像 Task 4 的 `(2497, 0, 459)` 那样冻结成
哨兵，并在报告里写明数字来源是本机克隆实测），再跑一次确认通过。
⚠️ **同时必须在 `test_src_linfukai186.py` 里补一条回归测试**：造一个**没有地区但标题含「模考」**
的键（例如加进 `shengkao-shenlun/y2016.json` 的 fixture：`"2016·省考行测申论联合模考大赛《申论》"`），
断言它落进 **`excluded`**（reason 以 `试卷名含排除词` 开头）**而不是 `unparsed`**。
理由：这正是本任务实测踩到的坑（初稿会把它错分进缺陷桶），没有回归测试就会被无声改回去。

- [ ] **Step 8: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/naming.py tools/gwyzhenti/sources/linfukai186.py tools/gwyzhenti/sources/__init__.py tools/tests/test_naming.py tools/tests/test_src_linfukai186.py tools/tests/smoke_linfukai186.py tools/tests/fixtures/linfukai186
git commit -m "feat(tools): linfukai186 adapter（四类目，行测交叉对照 + 申论目录）"
```
（若冒烟哨兵是随后单独一次提交，可以，但每个 commit 必须语义完整。）

---

### Task 6: 段一 —— 六个产物

**Files:**
- Create: `tools/gwyzhenti/catalog.py`
- Create: `tools/tests/test_catalog.py`

**Interfaces:**
- Consumes: `ADAPTERS`（Task 4/5）、`classify`（Task 2）、`paper_slug`（Task 1）、`naming.PROVINCES`（Task 5）
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
        # 卷键去重后 = 7 卷：
        #   四川 2016 行测（**两源合并**）、江苏 2020 行测 A 类、国考 2026 行测 行政执法、
        #   黑龙江 2016 行测、多省联考 2016 行测、黑龙江 2016 申论、国考 2016 申论 副省级
        self.assertEqual(len(rows), 7)
        self.assertEqual(len({r["slug"] for r in rows}), 7, "slug 必须一一对应")
        titles = {r["title"] for r in rows}
        # `title` 取**首个遇到的源**（`sorted(uproots)` ⇒ linfukai186 在前），故四川卷存的是
        # linfukai186 的卷名；xingcezhenti 的原名在 `titles` 里逐源保留。
        self.assertIn("2016·423四川公务员考试《行测》题", titles)
        self.assertIn("2020年江苏省公务员录用考试《行测》题（A类）", titles)
        self.assertIn("2016·公务员多省联考《行测》题", titles)
        self.assertIn("2016·国家公考《申论》题（副省级）", titles)

    def test_catalog_row_shape(self):
        rows = jl(os.path.join(self.out, "catalog.jsonl"))
        r = [x for x in rows if x["region"] == "四川"][0]
        self.assertEqual(r["level"], "省考")
        self.assertEqual(r["subject"], "行测")
        self.assertEqual(r["year"], "2016")
        self.assertEqual(r["ptype"], "统考")
        self.assertEqual(r["slug"], "省考-四川-2016-行测-统考")
        # **跨源合并**：xingcezhenti 的 常识 1 + 资料 2，与 linfukai186 的 数量关系 1
        self.assertEqual(r["n_questions"], 4)
        # 码点序（常 U+5E38 < 数 U+6570 < 资 U+8D44）；**不是**逻辑序 —— 这里刻意用 sorted() 钉死可复现性
        self.assertEqual(sorted(r["modules"]), ["常识判断", "数量关系", "资料分析"])
        self.assertEqual(r["sources"], ["linfukai186", "xingcezhenti"])
        # **逐源保真**：两个源的原始卷名各自留存（R-T6-1 起值从**字符串**改为**排序去重列表**）
        self.assertEqual(r["titles"], {
            "linfukai186": ["2016·423四川公务员考试《行测》题"],
            "xingcezhenti": ["2016年423联考《行测》题（四川卷）"],
        })
        # 两源卷名互不为子串，但**跨源**不算撞键（跨源本来就是要合并的）⇒ `dubious` 只看**同源**
        self.assertEqual(r["dubious"], [])

    def test_gukao_rows_have_empty_region_field(self):
        # 国考卷在 `PaperKey.region` 里是**空串**（`classify` 的规定），报告里才折成 `国考`
        rows = jl(os.path.join(self.out, "catalog.jsonl"))
        gk = [x for x in rows if x["level"] == "国考"]
        self.assertEqual(len(gk), 2)                        # 2026 行测行政执法 + 2016 申论副省级
        self.assertEqual({x["region"] for x in gk}, {""})
        self.assertEqual(self.rep.by_region.get("国考"), 2)

    def test_report_totals(self):
        self.assertEqual(self.rep.papers, 7)
        self.assertEqual(self.rep.records, 11)      # xingcezhenti 3 + linfukai186 8（卷×模块）
        self.assertEqual(self.rep.questions, 12)    # xingcezhenti 4 + linfukai186 8
        self.assertEqual(self.rep.unparsed, 0)
        self.assertEqual(self.rep.excluded, 3)      # 深圳市考 1 + 模考 2（Task 5 fixture 另有一条无地区模考卷）
        self.assertEqual(dict(self.rep.by_subject), {"行测": 5, "申论": 2})

    def test_coverage_matrix_has_region_rows(self):
        with open(os.path.join(self.out, "coverage.md"), encoding="utf-8") as fh:
            cov = fh.read()
        self.assertIn("四川", cov)
        self.assertIn("江苏", cov)
        self.assertIn("申论", cov)      # 申论**已接入段一**（正文导出仍排 M3）
        # 非省份的地区类（多省联考）**不得从覆盖矩阵里消失** —— 否则 catalog 里有卷、
        # 报告里查不到，正好违背「地域齐全」的第一优先级。
        self.assertIn("多省联考", cov)
        self.assertNotIn("未接入（M3）", cov)

    def test_conflicts_lists_both_source_names(self):
        with open(os.path.join(self.out, "conflicts.md"), encoding="utf-8") as fh:
            con = fh.read()
        # 四川卷是同键多源的**唯一**例子；两个源的原始卷名都要出现（留证不裁决）
        self.assertIn("省考-四川-2016-行测-统考", con)
        self.assertIn("2016·423四川公务员考试《行测》题", con)
        self.assertIn("2016年423联考《行测》题（四川卷）", con)
        self.assertIn("xingcezhenti", con)
        self.assertIn("linfukai186", con)

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
    # 行里三个卷名字段的语义（裁定 R-T6-1）：
    #   `title`   = **首个**被聚合进来的原始卷名（稳定、但**不代表全部**）
    #   `titles`  = 逐源**全部**不同卷名（排序去重；**不是**覆盖式的单个值）
    #   `dubious` = 非空 ⇒ 该键下**存在互不为子串的两个卷名** ⇒ **疑似撞 slug**（两份不同的卷
    #               塌到了同一键）。段二导出会把它们合进一个文件 —— 故必须**摆到明面**，绝不静默。
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
        # **逐源保真**：同一卷键被多源提供时，各留各的原始卷名 —— 冲突页拿它当证据。
        # **用集合收**（R-T6-1）：先前是 `p["titles"][r["family"]] = r["title"]` 的**后写覆盖**，
        # 同源多名时只留最后一个，而 `title` 留的是第一个 ⇒ 两个字段指向两个不同卷名，且
        # 冲突页只列跨源 ⇒ **丢卷这件事一个字都不说**。
        p["titles"].setdefault(r["family"], set()).add(r["title"])
        if r.get("declared_questions", -1) > 0:
            p["declared"] += r["declared_questions"]

    rows = []
    rep = Report(unparsed=len(all_unparsed), excluded=len(all_excluded))
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
        # `records` 只数**真正进了 catalog 的**记录（R-T6-1 修评审 F3）：
        # 先前是 `records=len(all_records)` ⇒ 已被改判进 unparsed/excluded 的记录**重复计入**。
        rep.records += 1
        rep.papers += 1
        rep.questions += n
        rep.by_region[key.region or "国考"] = rep.by_region.get(key.region or "国考", 0) + 1
        rep.by_subject[key.subject] = rep.by_subject.get(key.subject, 0) + 1

    _dump_jsonl(os.path.join(out_dir, "catalog.jsonl"), rows)
    _dump_jsonl(os.path.join(out_dir, "excluded.jsonl"), all_excluded)
    _dump_jsonl(os.path.join(out_dir, "unparsed.jsonl"), all_unparsed)
    _write_coverage(out_dir, rows, rep)
    _write_gaps(out_dir, rows)
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
    """覆盖/缺口两表共用的**科目**行序列 —— 同 `_region_rows` 的道理，**只是换一维**：

    固定行 = `SUBJECTS`；再加 catalog 里实际出现但不在 `SUBJECTS` 的科目。
    不加这一项，第三科目（如将来引入的其它卷种）会**在覆盖表里凭空消失**。
    """
    extra = sorted({r["subject"] for r in rows} - set(SUBJECTS))
    return list(SUBJECTS) + extra


def _write_coverage(out_dir, rows, rep):
    have = {}
    for r in rows:
        have.setdefault((r["region"] or LEVEL_GUOKAO, r["subject"]), []).append(r["year"])
    L = ["# 覆盖矩阵（地区 × 科目）", "",
         "> 由 catalog.jsonl 实算得出。**地域齐全 > 时间齐全**：先看地区行是否空白，再看年份纵深。", "",
         "| 地区 | 科目 | 卷数 | 年份跨度 | 年份数 |", "|---|---|---:|---|---:|"]
    for region in _region_rows(rows):
        for subject in _subject_rows(rows):
            ys = have.get((region, subject), [])
            if ys:
                L.append("| %s | %s | %d | %s–%s | %d |"
                         % (region, subject, len(ys), min(ys), max(ys), len(set(ys))))
            else:
                L.append("| %s | %s | 0 | — | 0 | **缺**" % (region, subject))
    L += ["", "**合计**：%d 卷 / %d 题。" % (rep.papers, rep.questions)]
    _w(os.path.join(out_dir, "coverage.md"), L)


def _write_gaps(out_dir, rows):
    have = {(r["region"] or LEVEL_GUOKAO, r["subject"]) for r in rows}
    L = ["# 缺口清单", "",
         "> 排序 = **地域优先**、年份次之、**新卷先于老卷**。", ""]
    L.append("## 一、地区级缺口（最高优先）")
    for region in _region_rows(rows):
        missing = [s for s in _subject_rows(rows) if (region, s) not in have]
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


def _dubious(titles_by_family):
    """同源多名里，若**存在两个互不为子串**的卷名 ⇒ 这可能是**两份不同的卷**被算成了同一个键。

    只看「互不为子串」是为了放过**命名变体**（`2015·北京市公考` ⊂ `2015·北京市公考《申论》题`）。
    命中时返回**全部**卷名（排序去重），供人核对；否则 `[]`。
    **这是「不对劲就摆到明面」的兜底**，不是判定 —— 拆键要人来看（spec :88 留的 `[, 变体]` 那一维）。
    """
    for fam in sorted(titles_by_family):
        ts = sorted(titles_by_family[fam])
        for i, a in enumerate(ts):
            for b in ts[i + 1:]:
                if a not in b and b not in a:
                    return sorted({t for f in titles_by_family for t in titles_by_family[f]})
    return []


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
            L.append("    - `%s`：%s" % (fam, "；".join(r["titles"].get(fam, []))))
    L += ["", "## 同源多名（疑似撞 slug）", "",
          "> 同一「来源家族 × 卷键」下有**互不为子串**的几个卷名 ⇒ 可能是**两份不同的卷**塌到了同一个",
          "> `slug`。段二导出会因此把两份卷合进一个文件。**此处只列证，不裁决。**", ""]
    dub = [r for r in rows if r["dubious"]]
    if not dub:
        L.append("（本次无。）")
    for r in dub:
        L.append("- `%s` ← %s（%d 题 / %d 模块）"
                 % (r["slug"], "、".join(r["sources"]), r["n_questions"], len(r["modules"])))
        for t in r["dubious"]:
            L.append("    - `%s`" % t)
    _w(os.path.join(out_dir, "conflicts.md"), L)


def _w(path, lines):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd D:/projects/gwy-zhenti/tools && PYTHONIOENCODING=utf-8 python -X utf8 -m unittest tests.test_catalog -v`
Expected: PASS，8 tests OK

> **⚠️ 修复轮 1 的追加要求（裁定 R-T6-1，施行细节见
> `.superpowers/sdd/2026-10-09-gwy-zhenti-m1-merge/task-6-fix1-brief.md`）** ——
> 真实数据里**两份不同的卷会撞同一个 `slug`**（实测 2016+ 行测 30 条），故本任务追加：
> ① `naming.PTYPE_RULES` 补 spec `:141-144` 测出的后缀词表；
> ② `titles` 值改为**排序去重列表**、行内新增 `dubious`、`conflicts.md` 增「同源多名（疑似撞 slug）」一节；
> ③ 清掉未用 import 并把字面量 `"国考"` 换成 `LEVEL_GUOKAO`；
> ④ `records` 只数**真正进了 catalog 的**记录；
> ⑤ 给 `except Unparsed` 的 `kind` 兜底补**双向**护栏测试（评审实测：改成恒 `all_unparsed` 时全绿无人抓）；
> ⑥ `_write_gaps` 去掉死参数 `rep`；⑦ 新增 `_subject_rows`（第三科目不得静默消失）。
> 测试条数随之上升，**不许为凑数增删测试**。

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
- Produces: `python -m gwyzhenti.cli catalog --upstream <root> --out <dir>`；后续 Task 11 在同一 `cli.py` 加 `export` / `gate` 子命令

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
  - `ExportReport`：`papers`、`files`、`images`、`manifest_path`、`skipped`、`collided`
  - `export._xingce_titles(row) -> list[str]`（**取 xingcezhenti 源自己的卷名**，见 Step 3）

> ⚠️ **本任务最会静默吃掉交付量的一处（裁定 R-T8-1，已实测量化）**：
> 文件名**必须**用 `row["titles"]["xingcezhenti"]`，**绝不能**用 `row["title"]`。理由与实测数字见
> Step 3 里 `_xingce_titles` 的 docstring。**Step 1 必须有一条专门锁它的测试**：
> 造一条 `title` 与 `titles["xingcezhenti"][0]` **不同**的 row（模拟两源同键的真库形态），
> 断言取到的是 `titles["xingcezhenti"][0]` 那个文件 —— 拿 `row["title"]` 去拼会**落空**，
> 该测试必须因此**变红**。对照组：真库实测 `429` 个有 xingcezhenti 的卷里，
> 用 `row["title"]` **286 个落空**、用 `titles["xingcezhenti"][0]` **0 个落空**。

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
    # 撞 slug：同一键在 xingcezhenti 源里有**多个卷名** ⇒ 只导第一个，其余在此如实记下。
    # 与 `skipped` 分开，是因为「少导了一份卷」和「这份卷没导出」是**两种不同的事故**（裁定 R-T8-1）。
    collided: list = field(default_factory=list)


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


def _xingce_titles(row):
    """该卷在 **xingcezhenti 源**里的卷名（排序列表）。空 = 该源根本没有此卷。

    **绝不能用 `row["title"]` 当文件名**（裁定 R-T8-1）。`title` 是**首个被聚合进来的原始卷名**，
    而聚合按 `sorted(uproots.items())` 走、`linfukai186` 排在 `xingcezhenti` 之前 ⇒
    凡是**两源都有的键**，`title` 就是 **linfukai186** 的卷名。实测这种键 **286** 个，
    且 **286/286** 两侧卷名**完全不是同一串**：

        2016·国家公务员考试副省级            （linfukai186）
        2016年国家公务员录用考试《行测》题（副省级）  （xingcezhenti）

    拿前者去 xingcezhenti 根下拼路径 ⇒ **全数落空** ⇒ 整卷被错判成「上游文件缺失」而丢。
    这是本任务**最会静默吃掉交付量**的一处，故单独成函数、单独可测。
    """
    return sorted(row.get("titles", {}).get("xingcezhenti", []))


def _parts_for(row, upstream_xingce):
    """按 MODULE_ORDER 取该卷各模块源文本；模块缺失则跳过（并如实记录）。

    文件名用 **xingcezhenti 源自己的卷名**（见 `_xingce_titles`）。同名多值（`len > 1`）
    = 该键疑似撞 slug ⇒ 只取第一个，**多出来的**卷名由调用方记进 `rep.collided`（不静默丢）。
    """
    names = _xingce_titles(row)
    if not names:
        return [], []
    want = [m for m in render.MODULE_ORDER if m in row["modules"]]
    parts, got = [], []
    for module in want:
        # 模块目录前缀
        prefix = {"政治理论": "01-政治理论", "常识判断": "02-常识判断",
                  "言语理解与表达": "03-言语理解与表达", "数量关系": "04-数量关系",
                  "判断推理": "05-判断推理", "资料分析": "06-资料分析"}[module]
        path = os.path.join(upstream_xingce, prefix, names[0] + ".md")
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
        # xingcezhenti 侧同名多值 ⇒ 该键疑似撞 slug，只导第一个，**其余如实记进 `collided`**
        # （不是静默丢；见裁定 R-T8-1）。
        extra = _xingce_titles(row)[1:]
        if extra:
            rep.collided.append({"slug": row["slug"], "titles": extra})
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
            # ⚠️ `dest_rel` 是**相对 md 文件**的链接（`../../../图片/…`，写进正文的就是它）；
            # 落盘必须把它**锚在 md 所在目录**再归一化。**原稿直接 `join(repo_root, dest_rel)`
            # 是错的** —— 那串 `../` 会从 `repo_root` 再往上跳，图片落到**仓库外**
            # （Task 9 实现者实测：fixture 下落到 `…\AppData\Local\图片\`，真库会落到 `D:\图片`，
            # 既污染盘符根、又让 `图片/` 目录根本没建）。此处为已实测的最小修复。
            dest_abs = os.path.normpath(os.path.join(
                repo_root, os.path.dirname(md_rel), dest_rel.replace("/", os.sep)))
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
    if rep.collided:
        # 撞 slug：同一键在 xingcezhenti 侧有多名 ⇒ 只导了第一个，其余记在此。**必须显式打印** ——
        # 它与「没导出」是两种事故，混在 skipped 里会让人以为只是上游缺文件（裁定 R-T8-1）。
        print("  撞 slug 未导的卷名 %d 条（详见报告）" % len(rep.collided))
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
Expected: 六闸全 OK；`sources` 不含正文的卷（纯 linfukai186）列入 `skipped` 并在报告中如实列出；
`collided` 非空时（撞 slug 的卷）**另行列出**，不得并入 `skipped` 一句带过（裁定 R-T8-1）。

- [ ] **Step 4: 写交付报告（如实，不美化）**

`work/REPORT-M1.md` 必须含：
- **数量账**：catalog 卷数 / 已导出卷数 / 跳过卷数（及理由分布）/ **撞 slug 未导卷数** / 未解析卷数 /
  已排除卷数（及理由分布）。
- **⚠️ 题数口径必须写清（裁定 R-T7-2，Task 7 评审 F2 实测）**：`catalog.jsonl` 的 `n_questions`
  是**各源按模块名相加**，而一个卷常**两源都有**（实测 286 个键；281/286 存在同名模块）
  ⇒ **跨源相加会高估**（评审按「同卷同模块取 max」复算，合计 79639 **偏高约 5,901**）。
  故交付报告里的 **「本次交付题数」= 导出侧口径**（xingcezhenti 正文侧，实测约 **51,010**），
  并在同一行注明 `79639` 是**跨源相加**的 catalog 口径。**两个数都不许裸写、都必须带口径**。
  （口径不同的两个数都是对的；错的是**不写口径**让人以为它们可比。）
- **六闸结果**：逐闸通过与否 + 说明（**不得抽样伪装成全量**）。
- **图片账（含缺图，必须点名）**：落盘图数 / 总体积 / 引用出现次数；**被引用但源缺失的图**逐张列出。
  上游 `图片缺失清单.txt` 有 2 行，但**只有 `formula-2c7a9ff6774e3af2.png`（2018 湖北 421联考 行测）
  落在 M1 范围内**（另一张属已排除的 2016 深圳市考）⇒ 报告写「**M1 缺 1 张公式图**」并点名该文件名，
  **不许声称「零缺失」**。
- **CLI 三条命令必须实跑证成（Task 12 评审提）**：Task 12 已把 `catalog` / `export` / `gate` 三条命令
  写进 `tools/README.md`，但当时 `cli.py` **只注册了 `catalog`**（`export`/`gate` 由你本任务落地）。
  ⇒ 你**必须实跑三条命令**（贴输出），并**逐字核对** README 里那三条命令行与 `cli.py` 的真实签名一致。
  若不一致，**改 README**（这是 Task 12 故意提前写、由你负责证成的部分）。
- **产出入库状态**：明写「`国考/`、`省考/`、`图片/` 已落本地工作区、**未入库**」，
  并给出体积（实测约 **32,640 张 / 217.0 MB**）与「入库方式待用户决定」（裁定 R-T11-1）。
- **排版一致性坏例计数（Task 8 评审提，裁定 R-T8-2）**：`render` 的答案切分依赖题块尾部的 `---`
  分隔线；若真库存在「题块内有 `**答案**：` 但**尾部没有 `---`**」的形态，答案会**留在正文里、
  答案区缺项** —— 内容不丢（G1/G5 不会报），但**排版会不齐**，而用户明令「排版整齐」。
  **故在**全量跑完的 md 树上**逐卷**数一遍：题块内出现 `**答案**：` 但该块尾无 `---` 的**题数**；
  **数字如实写进报告**（是 0 也写 0，并写明「已逐卷数过，非抽样」）。**真库 fixture 无此形态**，
  所以这条**只能在全量跑里验**。
- **覆盖账**：`coverage.md` 的地区×科目表；明确「哪些省份已覆盖、哪些为缺」。
- **诚实边界**（照抄 spec §9，并更新实测数字）：ERRRC 自报 515 ≠ 已入库；**申论「有目录行」但 M1 不出正文**
  （686 份省考申论真题只在 `catalog.jsonl` 里，`coverage.md` 的申论行**不代表可交付**）；公式为位图非数学表达式；
  卷型与层级由名字解析、拿不准的已进 `unparsed.jsonl`；`linfukai186` 的行测卷**无正文**，只作交叉对照与补洞提示。

- [ ] **Step 5: 提交**

```bash
cd D:/projects/gwy-zhenti
git add tools/gwyzhenti/cli.py
git commit -m "feat(tools): export / gate 子命令"
```
（`work/` 已 gitignore，报告不进版本库。）

> ⚠️ **段二产出（`国考/`、`省考/`、`图片/`）本任务一律不 commit（裁定 R-T11-1）。**
> 实测 M1 段二会落 **32,640 张图 / 217.0 MB**（引用出现 114,318 次；题目图 5,222 + 公式图 27,417）。
> 把 217 MB 灌进 git 是**难撤销**的动作（历史里的 blob 甩不掉）⇒ 按「难撤销/对外可见先确认」的准则，
> **先不提交**。M1 的交付物 = **本地工作区里完整的 md 树 + 报告**（用户可打开、可复核）；
> **「产出如何入库」（直接提交 / Git LFS / 分仓 / 单独仓）是一个显式决策点，留给用户**。
> **代价（若裁定错）**：若用户本就要 M1 直接提交，补一条 `git add 图片/ …` 即可，**零返工**；
> 反向（先提交再想撤）**不可逆** —— 这个不对称就是取谨慎一边的全部理由。

---

### Task 12: 来源登记 + 管线说明收口

**Files:**
- Modify: `SOURCES.md`
- Modify: `tools/README.md`

- [ ] **Step 1: 更新 SOURCES.md**

> ⚠️ **顺手改掉 `tools/README.md` 里一句不实的话（Task 7 评审 F4）**：README 末行说
> 「加新源 = 写 adapter + 注册一行」，但 `cli._uproots` 是**硬编码**的那两个源目录
> （上游实有 4 个目录），**新注册的源不会自动进 catalog**。改成如实说法：
> 「加新源 = 写 adapter + 注册到 `sources.ADAPTERS` + **在 `cli._uproots` 里补一条源根**」。
> （这是**简报原文**带进来的，非 Task 7 实现者的错；Task 12 本来就要动这个文件，故在此收口。）

在 `SOURCES.md` 里补一节「本仓实际接入的源（2026-10-09 实测）」，写明：
- **已接入（M1）**：
  - `ERRRC/xingcezhenti` —— **行测正文主源**；自报 515 卷 / 58,890 题；实测标题合计一致；
    **无 LICENSE**，私有仓内导入 + 逐卷记来源。
  - `linfukai186-arch/gongkao-tiku` —— 题级 JSON 四类目：`guokao-xingce` / `shengkao-xingce`
    （行测，**交叉对照**）、`guokao-shenlun`（59 键 **100% 模考 ⇒ 0 真卷**，全数进 excluded）、
    `shengkao-shenlun`（808 键，**686 份省考申论真题**，2010–2026）。
    **它是 spec §9 所称「最大缺口」（申论）的实际目录源** ⇒ M1 段一**四类目全接入**；
    申论**正文**的导出仍排 M3。此源**无卷型字段、无卷级图片**。
- **已识别、未接入**：
  - `ERRRC/kaogong-shuati`（47★，**已入库 750 MB**）—— 考公刷题 App，**本地 SQLite 题库**，
    走 `node tools/reassemble-tiku.mjs` 从 `tiku.db.part-00..03`（94+94+94+34 MB）重组。**实测 schema**：
    `materials.db` = `materials(paperId, pdf, title, idx, text)` **申论材料正文**；
    `tiku.db` 的 `papers(id, subject, subjectName, category, name, …)` 中 `subject ∈ {xingce, shenlun, sydw}`、
    `category` 是**归一化的地区/类别**（注释示例 `国考 / 山东省考 / 四川 …`），
    `questions(id, questionId, paperId, …)` 的 `questionId` 是**粉笔原题 id**。
    README 注明题库版权属粉笔等来源方、已获授权随仓分发、**请勿商用或二次分发**。
    ⇒ **归 M3**（它的价值在申论材料 + 独立地区归一可做交叉验证）；M1 不接（749 MB 下载 + 分片重组 +
    SQLite adapter 会拉长关键路径，且不改变 M1 任何交付物）。
  - `ERRRC/kaogongzhentizhengliu`（725★）—— 同作者**按考点重组**的 判断推理 + 资料分析 部分：
    22,380 md + 21,829 png，`10-真题/<模块>/<子类>/<qid> <考点>.md`（**文件名带 qid**，与
    `xingcezhenti` 的 `<sub>qid NNNN · 考点</sub>` 同源）。**实测两仓 `90-图片/` 文件名：
    交集 21,591 / 仅本仓 17,870 / 仅 zhengliu 有 238** ⇒ 有 238 张图是主源没有的。
    ⇒ **归 M2**（两项价值：① 补图候选 ② 细粒度考点标签）。⚠️ 238 张是**两仓平行渲染**的差集，
    **不等于「主源丢了 238 张」**，M2 必须逐题比对再定，不得直接宣称。
  - `zzcc-nb/gongkao-tiku`（**行测题库为空**，实为申论源，归 M3）。
  - `shiwuooo/shangantong-papers-v2-c1/c2`（**行测**源，**496 卷**（本机实测 c1 310 + c2 186），2008–2026，HTML+webp，**独缺西藏**
    ⇒ 不提升地域齐全，留作交叉验证与老年份纵深，归 M2）。
- **主源的图片来源底账（正面结论，须进交付报告）**：`xingcezhenti` 自带的 `图片缺失清单.txt`
  **2 行**（`90-图片/公式图/formula-4daf9a3762c10376.png` 与 `formula-2c7a9ff6774e3af2.png`）。
  全仓图片 **实测现有 39,461 张**（题目图 6,152 + 公式图 33,309；`os.listdir` 点数），
  而 README 自报 **39,463** ⇒ **差 2，正是缺失清单那 2 行**（39,461 + 2 = 39,463）
  ⇒ 两条独立线索**互相印证**，缺失清单可信。
  **交付报告必须照实写缺图、不许声称「零缺失」**；且要**分清**：
  第 1 张只被 **2016 深圳市考**引用（**已排除**，不在 M1）⇒ **M1 实际只缺第 2 张**
  （**2018 年 421 联考《行测》题（湖北卷）（网友回忆版）**）⇒ **M1 的缺图数 = 1，可点名**。
- **同源 fork 家族**：`r1172464137/xingcezhenti` 等只算 1 个家族；
  `jangviktor-web/GongkaoNaoku` 是 `xingcezhenti` 的**衍生物**（无新地区），不另接入。
- **PDF-only（按用户口径「PDF 只作补充」，不作为 md 源）**：`SGHCN0762/civil-country-exam-xingce`、
  `SGHCN0762/civil-provice-exam-xingce`（1,294 份 PDF、**0 个 md**、1.09 GB，**2003 年起**，
  含云南/广东/广州/浙江 ⇒ 老年份纵深）、`Yaoyuan-Zhang319/AdministrativeAptitudeTest`。
- **实测判为不接入**（避免以后重复搜）：`zhangxiangliang/civil-service-exam`（984★，专业大类**攻略**）、
  `kuriv/civil-service-exam`（1005★，知识**思维导图**）、`dfds2989-source/kaogong-materials`（推广落地页）、
  `andesiwangzhiyi-alt/gongkao-shangantong`（应用，90 道**原创**题）、`gesu14/xingce-practice`、
  `steven-xjx/fenbi-xingce`、`Gnotes/gwy`、`TaiMaBenJi/knowledge-commons`（`exam/` 仅 59 项）。

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
| §3 数据源 | Task 4（ERRRC 行测正文主源）、Task 5（linfukai186 **四类目**：行测交叉对照 + 申论**目录**）、Task 12（登记 zzcc-nb / shiwuooo 与 PDF-only 源） |
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
