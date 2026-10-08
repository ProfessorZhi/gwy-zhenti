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
        # 期望值是 `sorted()` 的**实际**结果（码点序：常 U+5E38 < 数 U+6570 < 资 U+8D44）。
        # 简报原文写的是 ["常识判断","资料分析","数量关系"]（「逻辑序」），`sorted()` 给不出它。
        self.assertEqual(sorted(r["modules"]), ["常识判断", "数量关系", "资料分析"])
        self.assertEqual(r["sources"], ["linfukai186", "xingcezhenti"])
        # **逐源保真**：两个源的原始卷名各自留存
        self.assertEqual(r["titles"], {
            "linfukai186": "2016·423四川公务员考试《行测》题",
            "xingcezhenti": "2016年423联考《行测》题（四川卷）",
        })

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
        # **3，不是简报写的 2**：fixture 按 R-T5-6 在 `shengkao-shenlun` 加过一条
        # 「无地区 + 含模考」键（真实数据 56 条的同形样本），故实际是
        # 深圳市考 + guokao-xingce 模考 + shengkao-shenlun 模考；plan 自身 Task 5 段
        # （`test_mock_and_shenzhen_are_excluded_not_unparsed`）已冻结为 3。
        self.assertEqual(self.rep.excluded, 3)      # 深圳市考卷 + 模考卷 ×2
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
