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
