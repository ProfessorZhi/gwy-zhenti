# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import naming                                              # noqa: E402
from gwyzhenti.sources import xingcezhenti as xz_mod                      # noqa: E402
from gwyzhenti.sources.xingcezhenti import XingceZhentiAdapter, MODULE_DIRS   # noqa: E402

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
