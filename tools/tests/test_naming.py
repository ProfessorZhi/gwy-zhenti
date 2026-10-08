# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.naming import classify, Unparsed      # noqa: E402


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
