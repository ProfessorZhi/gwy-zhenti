#!/usr/bin/env python3
"""Offline tests for the per-question validator.

    python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v

Synthetic papers are written into temp dirs, so most tests need no handoff and
no repository tree. The integration checks skip unless ASSETSQA_REPO is set.
"""
import json
import os
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import paper_question_validator as P  # noqa: E402

REPO = os.environ.get("ASSETSQA_REPO", "")
HANDOFF = os.environ.get("ASSETSQA_HANDOFF", "")

FM = """---
考试: "国考"
地区: "国考"
年份: "2026"
科目: "行测"
卷型: "副省级"
对照题本题量: {n}
实有题数: {n}
缺失原题号: {missing}
---

# 测试卷

"""


def make_paper(root, questions, n=3, missing="[]", name="t.md"):
    """questions: list of (number, stem_html, [option_plain_texts])."""
    os.makedirs(root, exist_ok=True)
    parts = [FM.format(n=n, missing=missing)]
    for num, stem, opts in questions:
        parts.append(f"## 第 {num} 题　<sub>qid {num} · 测试</sub>\n\n{stem}\n\n")
        for lab, txt in zip("ABCD", opts):
            parts.append(f"- **{lab}**. {txt}\n")
        parts.append("\n")
    path = os.path.join(root, name)
    open(path, "w", encoding="utf8").write("".join(parts))
    return path


def png(root, rel="图片/t/a.png", size=(8, 8)):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.new("L", size, 0).save(p)
    return os.path.relpath(p, root)


class TestFrontmatter(unittest.TestCase):
    def test_parses_key_values(self):
        fm = P.frontmatter(FM.format(n=3, missing="[]"))
        self.assertEqual(fm["地区"], "国考")
        self.assertEqual(fm["卷型"], "副省级")

    def test_missing_frontmatter(self):
        self.assertEqual(P.frontmatter("# no frontmatter"), {})


class TestSplitOptions(unittest.TestCase):
    """Regression: the heading line used to be counted as stem text, inflating
    every stemChars figure (国考 Q31 read 63 instead of 32)."""

    BLK = ("## 第 31 题　<sub>qid 19526345 · 常识判断</sub>\n\n"
           "题干正文：\n\n"
           "- **A**. 甲\n- **B**. 乙\n- **C**. 丙\n- **D**. 丁\n")

    def test_heading_not_in_stem(self):
        stem, opts = P.split_options(self.BLK)
        self.assertNotIn("第 31 题", stem)
        self.assertNotIn("qid", stem)
        self.assertEqual(len(opts), 4)

    def test_stem_chars_is_real_stem_only(self):
        stem, _ = P.split_options(self.BLK)
        plain = P.R.TAG.sub("", P.V.IMG.sub("", stem)).strip()
        self.assertEqual(len(plain), len("题干正文："))


class TestPlaceholder(unittest.TestCase):
    def test_missing_sentinel(self):
        self.assertTrue(P.is_placeholder("略", ["缺失"] * 4))

    def test_zhanque_sentinel(self):
        self.assertTrue(P.is_placeholder("略", ["暂缺"] * 4))

    def test_stem_marker(self):
        self.assertTrue(P.is_placeholder("题目正在全力以赴征集，将会第一时间上传", ["甲"] * 4))

    def test_real_question(self):
        self.assertFalse(P.is_placeholder("下列说法正确的是", ["甲", "乙", "丙", "丁"]))

    def test_label_options_are_not_placeholder(self):
        self.assertFalse(P.is_placeholder("图形规律", ["A", "B", "C", "D"]))


class TestHasContent(unittest.TestCase):
    def test_text_is_content(self):
        self.assertTrue(P.has_content("甲", []))

    def test_image_is_content(self):
        self.assertTrue(P.has_content("", ["x.png"]))

    def test_label_only_is_not_content(self):
        self.assertFalse(P.has_content("A", []))

    def test_empty_is_not_content(self):
        self.assertFalse(P.has_content("   ", []))


class TestValidatePaper(unittest.TestCase):
    def _run(self, questions, n=3, missing="[]", handoff=None):
        with tempfile.TemporaryDirectory() as d:
            path = make_paper(d, questions, n=n, missing=missing)
            P.PAPERS["_tmp"] = (os.path.relpath(path, d), ("国考", "2026", "副省级"), None)
            try:
                return P.validate_paper(d, handoff, "_tmp")
            finally:
                P.PAPERS.pop("_tmp", None)

    def test_clean_paper_is_structurally_valid(self):
        doc = self._run([(1, "题干甲", ["甲", "乙", "丙", "丁"]),
                         (2, "题干乙", ["甲", "乙", "丙", "丁"]),
                         (3, "题干丙", ["甲", "乙", "丙", "丁"])])
        self.assertEqual(doc["summary"]["structurallyValid"], 3)
        self.assertEqual(doc["summary"]["invalid"], 0)

    def test_placeholder_is_invalid(self):
        doc = self._run([(1, "题目正在全力以赴征集，将会第一时间上传",
                          ["缺失", "缺失", "缺失", "缺失"])])
        self.assertEqual(doc["summary"]["invalid"], 1)
        self.assertIn("fenbi-placeholder-stub", doc["rows"][0]["reasons"])

    def test_label_only_options_are_incomplete_not_invalid(self):
        doc = self._run([(1, "图形规律", ["A", "B", "C", "D"])])
        self.assertEqual(doc["summary"]["incomplete"], 1)
        self.assertEqual(doc["summary"]["invalid"], 0)
        self.assertTrue(all("label-only" in r
                            for r in doc["rows"][0]["incompleteReasons"]))

    def test_missing_option_d_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.md")
            open(p, "w", encoding="utf8").write(
                FM.format(n=1, missing="[]") +
                "## 第 1 题\n\n题干\n\n- **A**. 甲\n- **B**. 乙\n- **C**. 丙\n")
            P.PAPERS["_tmp"] = ("t.md", ("国考", "2026", "副省级"), None)
            try:
                doc = P.validate_paper(d, None, "_tmp")
            finally:
                P.PAPERS.pop("_tmp", None)
        self.assertIn("options-not-abcd", doc["rows"][0]["reasons"])

    def test_empty_stem_is_invalid(self):
        doc = self._run([(1, "", ["甲", "乙", "丙", "丁"])])
        self.assertIn("empty-stem", doc["rows"][0]["reasons"])

    def test_broken_image_reference_is_invalid(self):
        doc = self._run([(1, '<p><img src="../../图片/nope/missing.png" /></p>',
                          ["甲", "乙", "丙", "丁"])])
        self.assertIn("unresolved-or-undecodable-image", doc["rows"][0]["reasons"])

    def test_resolvable_image_carries_content(self):
        with tempfile.TemporaryDirectory() as d:
            rel = png(d, "图片/t/题目图/a.png")
            path = make_paper(d, [(1, f'<p><img src="{rel}" /></p>',
                                   ["甲", "乙", "丙", "丁"])], n=1)
            P.PAPERS["_tmp"] = ("t.md", ("国考", "2026", "副省级"), None)
            try:
                doc = P.validate_paper(d, None, "_tmp")
            finally:
                P.PAPERS.pop("_tmp", None)
            row = doc["rows"][0]
            self.assertEqual(row["verdict"], "structurally_valid")
            self.assertEqual(row["stemImages"], 1)
            self.assertEqual(len(row["stemImageSha"][0]), 64)

    def test_gaps_must_match_declared_missing(self):
        with tempfile.TemporaryDirectory() as d:
            make_paper(d, [(1, "甲", ["甲", "乙", "丙", "丁"]),
                           (3, "丙", ["甲", "乙", "丙", "丁"])], n=3, missing="[2]")
            P.PAPERS["_tmp"] = ("t.md", ("国考", "2026", "副省级"), None)
            try:
                doc = P.validate_paper(d, None, "_tmp")
            finally:
                P.PAPERS.pop("_tmp", None)
        self.assertEqual(doc["questionCount"]["gaps"], [2])
        self.assertTrue(doc["questionCount"]["gapsMatchDeclaredMissing"])

    def test_identity_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.md")
            open(p, "w", encoding="utf8").write(
                FM.format(n=1, missing="[]").replace('地区: "国考"', '地区: "江苏"') +
                "## 第 1 题\n\n甲\n\n- **A**. 甲\n- **B**. 乙\n- **C**. 丙\n- **D**. 丁\n")
            P.PAPERS["_tmp"] = ("t.md", ("国考", "2026", "副省级"), None)
            try:
                doc = P.validate_paper(d, None, "_tmp")
            finally:
                P.PAPERS.pop("_tmp", None)
        self.assertFalse(doc["identity"]["matches"])

    def test_no_handoff_means_unknown_capture_and_sourceid(self):
        doc = self._run([(1, "题干", ["甲", "乙", "丙", "丁"])])
        self.assertIsNone(doc["sourceId"])
        self.assertEqual(doc["sourceIdStatus"], "unknown-no-authorized-handoff")
        self.assertEqual(doc["rows"][0]["capture"]["status"], "no-authorized-handoff")

    def test_answers_and_explanations_always_unknown(self):
        doc = self._run([(1, "题干", ["甲", "乙", "丙", "丁"])])
        self.assertEqual(doc["rows"][0]["answer"], "unknown")
        self.assertEqual(doc["rows"][0]["explanation"], "unknown")

    def test_duplicate_numbers_are_detected(self):
        doc = self._run([(1, "甲", ["甲", "乙", "丙", "丁"]),
                         (1, "乙", ["甲", "乙", "丙", "丁"])], n=1)
        self.assertEqual(doc["questionCount"]["duplicates"], [1])

    def test_focus_matrix_does_not_merge_papers(self):
        with tempfile.TemporaryDirectory() as d:
            make_paper(d, [(1, "甲", ["甲", "乙", "丙", "丁"])], n=1)
            P.PAPERS["_a"] = ("t.md", ("国考", "2026", "副省级"), None)
            try:
                doc = {"papers": {"_a": P.validate_paper(d, None, "_a")}}
                m = P.build_focus(doc, 1)
            finally:
                P.PAPERS.pop("_a", None)
        self.assertIn("_a", m["columns"])
        self.assertIn("not be conflated", m["note"])


@unittest.skipUnless(REPO and HANDOFF, "ASSETSQA_REPO / ASSETSQA_HANDOFF not set")
class TestRepositoryValidation(unittest.TestCase):
    def test_handoff_backed_paper_has_sourceid(self):
        doc = P.validate_paper(REPO, HANDOFF, "js-2025-c")
        self.assertEqual(doc["sourceId"], "4189916")
        self.assertEqual(doc["sourceIdStatus"], "from-authorized-handoff")
        self.assertEqual(doc["summary"]["invalid"], 0)

    def test_paper_without_handoff_keeps_sourceid_unknown(self):
        doc = P.validate_paper(REPO, HANDOFF, "gk-2026-fushengji")
        self.assertIsNone(doc["sourceId"])
        self.assertEqual(doc["rows"][0]["capture"]["status"], "no-authorized-handoff")

    def test_guokao_2026_q31_repo_side_facts(self):
        doc = P.validate_paper(REPO, HANDOFF, "gk-2026-fushengji")
        row = next(r for r in doc["rows"] if r["number"] == 31)
        # repo-side only: 32-char stem, 4 options, 3 formula images
        self.assertEqual(row["stemChars"], 32)
        self.assertEqual(row["optionCount"], 4)
        self.assertEqual(sum(row["optionImages"]), 3)
        self.assertEqual(row["answer"], "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
