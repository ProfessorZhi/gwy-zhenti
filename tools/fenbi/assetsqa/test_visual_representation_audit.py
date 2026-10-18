#!/usr/bin/env python3
"""Unit tests for the round-2 visual-representation audit.

    python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v

Repo/handoff-dependent checks skip when the paths are absent.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import visual_representation_audit as R  # noqa: E402

REPO = os.environ.get("ASSETSQA_REPO", "")
HANDOFF = os.environ.get("ASSETSQA_HANDOFF", "")


class TestPlaceholderDetection(unittest.TestCase):
    """The stub sentinel is NOT uniform. A single-string check under-detects."""

    @staticmethod
    def q(stem, texts):
        return {"stemText": stem,
                "options": [{"label": l, "text": t} for l, t in zip("ABCD", texts)]}

    def test_missing_sentinel(self):
        self.assertTrue(R.is_placeholder_stub(self.q("随便", ["缺失"] * 4)))

    def test_zhanque_sentinel(self):
        # real capture used 暂缺 in 江苏2024A Q76
        self.assertTrue(R.is_placeholder_stub(self.q("随便", ["暂缺"] * 4)))

    def test_mixed_sentinels(self):
        self.assertTrue(R.is_placeholder_stub(self.q("随便", ["缺失", "暂缺", "缺失", "暂缺"])))

    def test_stem_marker_only(self):
        self.assertTrue(R.is_placeholder_stub(
            self.q("题目正在全力以赴征集，将会第一时间上传", ["甲", "乙", "丙", "丁"])))

    def test_real_question_is_not_placeholder(self):
        self.assertFalse(R.is_placeholder_stub(self.q("下列说法正确的是", ["甲", "乙", "丙", "丁"])))

    def test_graphic_label_options_are_not_placeholder(self):
        self.assertFalse(R.is_placeholder_stub(self.q("图形规律", ["A", "B", "C", "D"])))


class TestNormalisation(unittest.TestCase):
    """Regression: round 1's normaliser deleted the image token because the tag
    stripper ran after the substitution and ate '<IMG>'."""

    def test_image_token_survives_tag_stripping(self):
        s = '<p>前<img src="a.png" />后</p>'
        out = R.norm(s)
        self.assertIn(R.IMG_TOKEN, out)
        self.assertNotIn("<", out.replace(R.IMG_TOKEN, ""))

    def test_fullwidth_folding(self):
        self.assertEqual(R.norm("（１％）".replace("１", "1")), R.norm("(1%)"))


class TestSplitBlock(unittest.TestCase):
    def test_image_only_option_is_not_lost(self):
        blk = ('### 第 1 题\n\n题干\n\n'
               '- **A**. <p><img src="x.png" /></p>\n'
               '- **B**. <p><img src="y.png" /></p>\n'
               '- **C**. <p>丙</p>\n'
               '- **D**. <p>丁</p>\n')
        stem, opts = R.split_block(blk)
        self.assertEqual([l for l, _ in opts], ["A", "B", "C", "D"])
        self.assertIn("x.png", opts[0][1])
        self.assertEqual(R.norm(opts[0][1]), R.IMG_TOKEN)


class TestClassifyPair(unittest.TestCase):
    def test_same(self):
        self.assertEqual(R.classify_pair("甲乙", "甲乙")[0], "same")

    def test_text_vs_image_stem(self):
        cls, _ = R.classify_pair("增长率为16.6%", '增长率为<img src="f.png" />')
        self.assertEqual(cls, "text-vs-image")

    def test_text_vs_image_option(self):
        cls, _ = R.classify_pair("4", '<p><img src="f.png" /></p>')
        self.assertEqual(cls, "text-vs-image")

    def test_numeric_token_difference(self):
        cls, _ = R.classify_pair("占比为20%", "占比为30%")
        self.assertEqual(cls, "numeric-token")

    def test_genuine_content_difference(self):
        cls, _ = R.classify_pair("甲的说法正确", "乙的说法错误")
        self.assertEqual(cls, "content-diff")


class TestXYCut(unittest.TestCase):
    def _ink(self, w, h, blocks):
        """blocks: list of (x0,x1) vertical bars with full-height ink."""
        return [[any(x0 <= x < x1 for x0, x1 in blocks) for x in range(w)]
                for _ in range(h)]

    def test_five_tiles_are_separated(self):
        # five 20px bars separated by 10px gutters
        blocks = [(i * 30, i * 30 + 20) for i in range(5)]
        ink = self._ink(150, 40, blocks)
        boxes = R.xy_cut(ink, 0, 0, 150, 40)
        self.assertEqual(len(boxes), 5)

    def test_uniform_ink_is_one_box(self):
        ink = self._ink(100, 40, [(0, 100)])
        self.assertEqual(len(R.xy_cut(ink, 0, 0, 100, 40)), 1)

    def test_empty_region_terminates(self):
        ink = self._ink(100, 40, [])
        boxes = R.xy_cut(ink, 0, 0, 100, 40)
        self.assertEqual(len(boxes), 1)


@unittest.skipUnless(REPO and os.path.isdir(REPO), "ASSETSQA_REPO not set")
class TestRepositoryInvariants(unittest.TestCase):
    def test_gd_declared_dimension_errors_are_capped_width_rounding(self):
        if not os.path.isdir(os.path.join(REPO, "图片/省考-广东-2020-行测-县级卷")):
            self.skipTest("image tree absent")
        res = R.audit_declared_dimensions(REPO, "gd-2020-xingce-county-96785")
        c = res["counts"]
        # width exact everywhere; every error is a small height-only delta
        self.assertEqual(c.get("size-disagreement", 0), 0)
        for row in res["rows"]:
            self.assertEqual(row["declared"][0], row["true"][0])
            self.assertLessEqual(abs(row["delta"][1]), 2)
            self.assertTrue(row["cappedWidth"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
