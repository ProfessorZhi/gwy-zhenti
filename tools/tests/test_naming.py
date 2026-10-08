# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import naming                         # noqa: E402
from gwyzhenti.naming import (                       # noqa: E402
    EXCLUDE_TITLE, PTYPE_RULES, PTYPE_VALUES, classify, Unparsed,
    region_exclusion, region_from_text,
)
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
        # 尾缀「卷」的容差是**窄的**：剥掉后能落回已声明词表才剥（`行政执法卷`→`行政执法`、
        # `省直卷`→`省直` —— 二者的干都已在词表内），否则**逐字保留**（`县级、乡镇统一卷` 的干
        # `县级、乡镇统一` 不在词表 ⇒ 原样保留，免与别的卷塌成同一个 slug）。
        self.assertEqual(classify("国考", "2026", "…（行政执法卷网友回忆版）").key.ptype, "行政执法")
        self.assertEqual(classify("河南", "2016", "…（县级、乡镇统一卷）").key.ptype, "县级、乡镇统一卷")
        # **任务 6 修复轮改了这里的期望**：spec §卷型归一表 `:141-144` 实测列出的后缀词表**含 `省直`**
        # （不含「省直卷」），故 `省直` 现在**在词表内** ⇒ `省直卷` 窄容差剥「卷」后落回 `省直`，
        # 与 `（省直）` **归一为同一个值**。此前 ruling R-T2-2 靠「`省直` 不在词表」刻意让两者不同；
        # 本次实测真库 `（省直）` 只在 2018、`（黑龙江省直卷）` 只在 2019，**从不同年** ⇒ 归一不撞 slug；
        # 而归一前 linfukai 侧两者都回落 `统考`，反与 xingcezhenti 的 `省直`/`省直卷` **跨源撞键** ——
        # 归一**消除**了那处撞键（见 task-6-fix1-report）。
        self.assertEqual(classify("黑龙江", "2016", "…（黑龙江省直卷）").key.ptype, "省直")
        shi = classify("黑龙江", "2016", "…（省直）").key.ptype
        hl = classify("黑龙江", "2016", "…（黑龙江省直卷）").key.ptype
        self.assertEqual(shi, "省直")
        self.assertEqual(shi, hl)

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


class TestUnparsedKind(unittest.TestCase):
    """锁死 `classify` 抛错时的 `kind` —— 分流只认它，不认 `reason` 文本。"""

    def test_region_and_title_exclusions_are_excluded_kind(self):
        # 三组输入各自走一条排除路径（地区排除 / 标题排除词），都必须是 EXCLUDED
        for region, title in (
            ("选调", "2016年某省行测真题"),
            ("深圳市考", "2016年深圳市公务员考试《行测》题"),
            ("四川", "2016年四川省考行测模考大赛"),
        ):
            with self.assertRaises(Unparsed) as cm:
                classify(region, "2016", title)
            self.assertEqual(cm.exception.kind, Unparsed.EXCLUDED, title)

    def test_empty_region_is_unparsed_kind(self):
        with self.assertRaises(Unparsed) as cm:
            classify("", "2016", "2016年某省行测真题")
        self.assertEqual(cm.exception.kind, Unparsed.UNPARSED)
        self.assertTrue(cm.exception.reason.startswith("地区字段为空"))

    def test_kind_defaults_to_unparsed(self):
        # **默认值就是判据的一部分**：将来新增 reason（如「年份缺失」）若忘了标 kind，
        # 默认必须落在 UNPARSED（缺陷侧，被 G1 盯）；默认成 EXCLUDED 会让新缺陷
        # **静默**落进 excluded.jsonl。
        self.assertEqual(Unparsed("某个新理由", "某卷").kind, Unparsed.UNPARSED)


class TestPtypeTableGuards(unittest.TestCase):
    """整改 F2·F / 裁定 R-T6-2：卷型词表**表驱动**护栏 —— 新增/删除 `PTYPE_RULES` 条目都会被抓。

    旧测试只对约 7 个卷型值有断言 ⇒ **其余条目删掉也全绿**（`_match_value` 少一条分支无人知，
    后果是卷型判错 ⇒ 撞 slug ⇒ 丢卷）。这里改成遍历**全表**。
    """

    @staticmethod
    def _sample(rx):
        """给一条规则造一个 `rx.fullmatch` 能命中的 token（取**第一个**候选）。

        `PTYPE_RULES` 的每条模式都是「字面量 或 `|` 连接的字面量」，故第一个候选即合格 token。
        """
        return rx.pattern.split("|")[0]

    def test_every_rule_round_trips_through_match_value(self):
        for rx, value in PTYPE_RULES:
            token = self._sample(rx)
            self.assertTrue(rx.fullmatch(token), (rx.pattern, token))
            self.assertEqual(naming._match_value(token), value, (rx.pattern, token))

    def test_ptype_values_equals_the_rule_values(self):
        self.assertEqual(PTYPE_VALUES, frozenset(v for _, v in PTYPE_RULES))

    def test_no_dead_value_in_ptype_values(self):
        # 每个已声明值都必须**至少能被某个 token 命中**（否则是个永远判不出来的死值）
        reachable = {naming._match_value(self._sample(rx)) for rx, _ in PTYPE_RULES}
        self.assertNotIn(None, reachable)
        self.assertEqual(reachable, set(PTYPE_VALUES))

    def test_rules_are_ordered_so_longer_suffixes_win(self):
        # 顺序是判据的一部分（`县级以上` 必须早于 `县级`、`定向乡镇` 早于 `乡镇`）—— 钉住这两处
        order = [rx.pattern for rx, _ in PTYPE_RULES]
        self.assertLess(order.index("县级以上"), order.index("县级卷|县级"))
        self.assertLess(order.index("定向乡镇"), order.index("乡镇卷|乡镇"))
        self.assertLess(order.index("县乡卷|县乡"), order.index("县级卷|县级"))


class TestExclusionWordGuards(unittest.TestCase):
    """整改 F2·F·4：F1 新增排除词（`法院` / `检察院` / `招警`）的**单元行为**护栏。

    （真库零误伤由 F1 的实跑验证；此处锁住单元行为，防词表被误删/误改。）
    """

    def test_f1_exclusion_words_raise_excluded_kind(self):
        for region, year, title in (
            ("青海", "2019", "2019年青海省法院、检察院录用考试《行测》题"),
            ("江西", "2018", "江西省2018年市县两级法院、检察院统一考录公务员笔试《行测》题"),
            ("四川", "2007", "2007年9月四川省招警考试《行测》题"),
        ):
            with self.assertRaises(Unparsed) as cm:
                classify(region, year, title)
            self.assertEqual(cm.exception.kind, Unparsed.EXCLUDED, title)

    def test_gongan_juan_is_a_legit_shengkao_post_not_excluded(self):
        # **反面**：`公安卷` 是省考的**公安岗位**卷（正当省考），F1 刻意**不收**单字「公安」——
        # 收「公安」会把它误伤掉。词表若被改成含「公安」，本条立刻红。
        title = "2017·辽宁公务员考试《行测》真题公安卷"
        self.assertIsNone(EXCLUDE_TITLE.search(title), "「公安卷」不得命中排除词（会误伤正当省考）")
        c = classify("辽宁", "2017", title)
        self.assertEqual(c.key.level, "省考")
        self.assertEqual(c.key.region, "辽宁")


class TestMemoryZhengliVariant(unittest.TestCase):
    """整改 F2·F·5：F1 新增的 `网友回忆(整理)?版` 性质词 —— 走**性质**，不逐字回落成卷型。

    旧词表只认 `网友回忆版` ⇒ `网友回忆整理版` 既非性质也非卷型 ⇒ `_ptype` 逐字回落
    ⇒ 卷型真的成了 `网友回忆整理版` ⇒ 与 `统考` 分成两个键 ⇒ 同一份卷交付两遍（F1 的 C2）。
    """

    def test_zhengli_variant_is_a_nature_not_a_ptype_value(self):
        c = classify("广西", "2016", "2016年423联考《行测》题（广西网友回忆整理版）")
        self.assertEqual(c.nature, "网友回忆版")
        self.assertNotEqual(c.key.ptype, "网友回忆整理版")
        self.assertIn(c.key.ptype, PTYPE_VALUES | {"统考"})

    def test_zhengli_variant_collapses_into_the_same_key_as_the_plain_juan(self):
        # 与 `（广西卷）` 必须**归一到同一个键**（否则就是「同卷两交付」）
        a = classify("广西", "2016", "2016年423联考《行测》题（广西网友回忆整理版）")
        b = classify("广西", "2016", "2016年423联考《行测》题（广西卷）")
        self.assertEqual(a.key, b.key)
        self.assertEqual(a.key.ptype, "统考")


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
