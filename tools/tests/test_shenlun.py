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


if __name__ == "__main__":
    unittest.main()
