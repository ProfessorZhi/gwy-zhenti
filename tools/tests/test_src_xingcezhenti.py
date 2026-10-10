# -*- coding: utf-8 -*-
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import naming, render                                      # noqa: E402
from gwyzhenti.sources import xingcezhenti as xz_mod                      # noqa: E402
from gwyzhenti.sources.xingcezhenti import (                              # noqa: E402
    MODULE_DIRS, NON_MODULE_DIRS, XingceZhentiAdapter,
)

# 一张最小可解析的模块 md：只要 frontmatter 能判出 (地区, 年份, 试卷) 就算一条 record。
_OK_MD = """---
试卷: "2016年423联考《行测》题（四川卷）"
模块: "资料分析"
地区: "四川"
年份: "2016"
题数: "1"
---

#### 第 1 题

题干。

- **A**. 甲

**答案**：A

---
"""


FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "xingcezhenti")
ROUTING_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "xingcezhenti_routing")

RECORD_KEYS = {
    "family", "title", "region", "year", "subject", "module", "n_questions",
    "relpath", "images_题目", "images_公式", "declared_questions",
}
BUCKET_KEYS = {"family", "title", "region", "year", "subject", "module", "relpath", "reason"}


class TestXingceZhentiAdapter(unittest.TestCase):
    def setUp(self):
        self.res = XingceZhentiAdapter().scan(FIX)

    def test_module_order_is_curriculum_order(self):
        self.assertEqual(MODULE_DIRS, (
            "01-政治理论", "02-常识判断", "03-言语理解与表达",
            "04-数量关系", "05-判断推理", "06-资料分析",
        ))

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

    def test_record_keys_are_frozen(self):
        for r in self.res.records:
            self.assertEqual(set(r), RECORD_KEYS)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.res = XingceZhentiAdapter().scan(ROUTING_FIX)

    def test_three_buckets_split_by_kind_not_by_reason_prefix(self):
        self.assertEqual(len(self.res.records), 0)
        self.assertEqual(len(self.res.excluded), 2)
        self.assertEqual(len(self.res.unparsed), 1)

    def test_excluded_reasons(self):
        prefixes = sorted(e["reason"].split(":")[0].strip() for e in self.res.excluded)
        self.assertEqual(prefixes, ["试卷名含排除词", "非国省考地区"])

    def test_empty_region_is_unparsed_not_excluded(self):
        u = self.res.unparsed[0]
        self.assertTrue(u["reason"].startswith("地区字段为空"))
        self.assertEqual(u["relpath"], "02-常识判断/c-空地区.md")

    def test_bucket_keys_are_frozen(self):
        for b in self.res.unparsed + self.res.excluded:
            self.assertEqual(set(b), BUCKET_KEYS)


class TestRoutingFollowsKindNotReasonText(unittest.TestCase):
    """钉死分流判据是 `exc.kind`，**不是** `reason` 文本。

    旧写法 `reason.startswith("地区字段为空")` 会把「前缀不认识的新 reason」错分进
    `excluded` 桶（不被 G1 盯）。这组测试用**与任何既有 reason 都不同**的陌生 reason
    构造输入，故：**改回前缀分流 → 必红**。
    """

    def _route(self, exc):
        with mock.patch.object(xz_mod, "classify", side_effect=exc):
            return XingceZhentiAdapter().scan(FIX)

    def test_unfamiliar_reason_with_unparsed_kind_lands_in_unparsed(self):
        res = self._route(naming.Unparsed("年份缺失", "某卷",
                                          kind=naming.Unparsed.UNPARSED))
        self.assertEqual(len(res.records), 0)
        self.assertEqual(len(res.excluded), 0)
        self.assertEqual(len(res.unparsed), 3)      # FIX 下共有 3 个 md，全部命中

    def test_unfamiliar_reason_with_excluded_kind_lands_in_excluded(self):
        res = self._route(naming.Unparsed("某种新排除", "某卷",
                                          kind=naming.Unparsed.EXCLUDED))
        self.assertEqual(len(res.records), 0)
        self.assertEqual(len(res.unparsed), 0)
        self.assertEqual(len(res.excluded), 3)


class TestRegionAlias(unittest.TestCase):
    """Task 4A · S1：市考的 region 归一（`深圳市考`/`广州市考` → `深圳`/`广州`）。

    源 frontmatter 的「地区」写 `深圳市考`/`广州市考`，而交付树的 region 轴（以及
    `expect.EXTRA_REGIONS`）用 `深圳`/`广州`。不归一时 `PaperKey.region` 会是 `深圳市考`
    ⇒ 落成 `省考/深圳市考/…`，与 `EXPECTED` 对不上。归一**只在 adapter 内**做 ——
    `naming.EXCLUDE_REGIONS` 一字不动（`linfukai186` 侧的把市考卷混进省级源，仍要排除）。
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gwyxz-region-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _put(self, rel, text):
        p = os.path.join(self.root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    @staticmethod
    def _md(title, region, year):
        return ('---\n试卷: "%s"\n模块: "资料分析"\n地区: "%s"\n年份: "%s"\n题数: "1"\n---\n\n'
                "#### 第 1 题\n\n题干。\n\n- **A**. 甲\n\n**答案**：A\n\n---\n"
                % (title, region, year))

    def test_alias_table_is_exactly_the_two_city_exams(self):
        self.assertEqual(xz_mod.REGION_ALIAS, {"深圳市考": "深圳", "广州市考": "广州"})

    def test_shenzhen_and_guangzhou_regions_are_normalized(self):
        self._put("06-资料分析/sz.md",
                  self._md("2020年深圳市考公务员录用考试《行测1》试题（网友回忆版）", "深圳市考", "2020"))
        self._put("06-资料分析/gz.md",
                  self._md("2016年广州市公务员录用考试《行测》题", "广州市考", "2016"))
        res = XingceZhentiAdapter().scan(self.root)
        self.assertEqual(len(res.records), 2)
        self.assertEqual(res.excluded, [])          # 归一后**不再**落 excluded
        self.assertEqual(res.unparsed, [])
        got = {r["title"]: r["region"] for r in res.records}
        self.assertEqual(got["2020年深圳市考公务员录用考试《行测1》试题（网友回忆版）"], "深圳")
        self.assertEqual(got["2016年广州市公务员录用考试《行测》题"], "广州")

    def test_exclusions_are_not_opened_by_the_alias(self):
        # 归一**只**覆盖 深圳/广州：`选调`/`公安院校` 等仍走排除族（`EXCLUDE_REGIONS` 未动）
        self.assertIn("深圳市考", naming.EXCLUDE_REGIONS)
        self.assertIn("广州市考", naming.EXCLUDE_REGIONS)
        self._put("06-资料分析/xd.md",
                  self._md("2017年重庆市选调优秀大学生到基层工作考试《行测》题", "选调", "2017"))
        res = XingceZhentiAdapter().scan(self.root)
        self.assertEqual(res.records, [])
        self.assertEqual(len(res.excluded), 1)
        self.assertTrue(res.excluded[0]["reason"].startswith("非国省考地区"))

    def test_record_keys_unchanged_by_normalization(self):
        # 归一改的是**值**，不是**形状**：记录键集一字不变（无新增键）
        self._put("06-资料分析/sz.md",
                  self._md("2020年深圳市考公务员录用考试《行测1》试题（网友回忆版）", "深圳市考", "2020"))
        res = XingceZhentiAdapter().scan(self.root)
        self.assertEqual(set(res.records[0]), RECORD_KEYS)


class TestUnmappedDirsLedger(unittest.TestCase):
    """整改 F2·C / 评审 I3：模块目录白名单外的目录**不得静默跳过**（只报不收）。

    `MODULE_DIRS` 是硬编码 6 项、`scan()` 只遍历它 ⇒ 源根下任何别的目录此前被**静默**丢掉，
    丢了多少题无人知。现在表外目录（跳过显式列出的噪声白名单）**记进 `unmapped` 台账**，
    但它们的正文**不进** `records`（`catalog.jsonl` 的行数因此不变）。
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gwyxz-up-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _put(self, rel, text):
        p = os.path.join(self.root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def test_module_dirs_agree_with_render_module_order(self):
        """防两张硬编码表漂移：`MODULE_DIRS` 的目录后缀必须逐项等于 `render.MODULE_ORDER`。

        此前这两张表各写一份、无人对账 —— 哪天加了第 7 个模块却忘了同步任一张，
        段一与段二的模块口径就会分叉（导出漏模块 / 合并顺序错）。
        """
        self.assertEqual([d.split("-", 1)[1] for d in MODULE_DIRS],
                         list(render.MODULE_ORDER))

    def test_off_whitelist_dir_is_recorded_and_in_whitelist_is_scanned(self):
        self._put("06-资料分析/ok.md", _OK_MD)          # 白名单内 ⇒ 正常收
        self._put("07-新模块/x.md", "---\n试卷: \"某卷\"\n---\n")   # 表外 ⇒ 只报不收
        res = XingceZhentiAdapter().scan(self.root)
        # ① 白名单内的照旧进 records
        self.assertEqual([r["relpath"] for r in res.records], ["06-资料分析/ok.md"])
        # ② 表外目录**出现在台账里**（不再是静默跳过），计数非零
        self.assertEqual([u["dir"] for u in res.unmapped], ["07-新模块"])
        self.assertEqual(res.unmapped[0]["reason"], "模块目录不在白名单: 07-新模块")
        self.assertEqual(res.unmapped[0]["relpath"], "07-新模块")
        self.assertEqual(res.unmapped[0]["family"], "xingcezhenti")

    def test_declared_noise_dirs_are_not_recorded(self):
        # `.git` 与 `90-图片` 是**显式**列出的噪声白名单（各带理由）⇒ 不留痕；
        # 文件（README.md 等，非目录）也不进这条对账。
        for d in NON_MODULE_DIRS:
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        self._put("README.md", "# 说明\n")
        res = XingceZhentiAdapter().scan(self.root)
        self.assertEqual(res.unmapped, [])

    def test_real_fixture_root_has_no_unmapped(self):
        # 夹具根下只有 `02-常识判断`/`06-资料分析`（白名单内）与 `90-图片`（噪声白名单）
        self.assertEqual(XingceZhentiAdapter().scan(FIX).unmapped, [])
