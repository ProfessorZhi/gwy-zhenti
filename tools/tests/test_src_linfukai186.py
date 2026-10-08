# -*- coding: utf-8 -*-
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.sources.linfukai186 import (                       # noqa: E402
    CATS, NON_CAT_DIRS, Linfukai186Adapter,
)

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
        # 本 fixture **有意只放能判出地区的键** ⇒ 零未解析。真实数据的账在冒烟里冻结成哨兵：
        # 四类目 1,475 键，其中 56 条是**无地区的模考卷**，落 `excluded` 而非 `unparsed`。
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
        self.assertEqual(reasons, sorted(["非国省考地区", "试卷名含排除词", "试卷名含排除词"]))
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


class TestUnmappedCatsLedger(unittest.TestCase):
    """整改 F2·C / 评审 I3（`linfukai186` 侧）：`data/` 下不在 `CATS` 白名单的目录不得静默跳过。

    真树 `data/` 实测另有三项 —— `practice` / `shiyebian-gongji` / `shiyebian-zongying`，
    它们是 **spec §2 有意排除**的非目标，故进 `NON_CAT_DIRS` 白名单（各带理由）；**白名单之外**
    的目录一律记 `unmapped` 台账（只报不收）。
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gwylfk-up-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _put_json(self, rel, obj):
        p = os.path.join(self.root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False))

    def test_off_whitelist_cat_dir_is_recorded_and_whitelisted_is_scanned(self):
        self._put_json("data/guokao-xingce/y2016.json",
                       {"2016·国家公务员考试": [{"t": "常识判断", "q": "题干"}]})
        self._put_json("data/03-新类目/y2016.json", {})
        for d in NON_CAT_DIRS:                       # 真树那三个：有意排除、白名单内 ⇒ 不留痕
            self._put_json("data/%s/y2016.json" % d, {})
        res = Linfukai186Adapter().scan(self.root)
        self.assertTrue(res.records, "白名单内的类目应照常收")
        self.assertEqual([u["dir"] for u in res.unmapped], ["03-新类目"])
        self.assertEqual(res.unmapped[0]["reason"], "类目目录不在白名单: 03-新类目")
        self.assertEqual(res.unmapped[0]["relpath"], "data/03-新类目")

    def test_declared_non_cat_dirs_are_the_three_excluded_ones(self):
        self.assertEqual(set(NON_CAT_DIRS),
                         {"practice", "shiyebian-gongji", "shiyebian-zongying"})

    def test_real_fixture_data_has_no_unmapped(self):
        self.assertEqual(Linfukai186Adapter().scan(FIX).unmapped, [])
        self.assertEqual({c for c, _ in CATS},
                         {"guokao-xingce", "shengkao-xingce", "guokao-shenlun", "shengkao-shenlun"})
