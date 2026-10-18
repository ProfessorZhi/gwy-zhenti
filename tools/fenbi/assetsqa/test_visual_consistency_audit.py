#!/usr/bin/env python3
"""Unit tests for the visual-consistency audit helpers.

Run with unittest (this host has no pytest):
    python3 -m unittest discover -s tools/fenbi/assetsqa -v

Tests that need the read-only handoff or a full image tree are skipped when the
path is absent, so the suite still passes on a sparse or partial checkout.
"""
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import visual_consistency_audit as V  # noqa: E402

HANDOFF = os.environ.get("ASSETSQA_HANDOFF", "")
REPO = os.environ.get("ASSETSQA_REPO", "")


class TestClassifiers(unittest.TestCase):
    """The three-way content classification must not confuse look-alike shapes."""

    def _classify(self, stem, option_texts, labels=("A", "B", "C", "D")):
        if not stem.strip():
            return "M"
        if option_texts and all(t.strip() == "缺失" for t in option_texts):
            return "P"
        if option_texts and all(t.strip() == l for t, l in zip(option_texts, labels)):
            return "G"
        return "T"

    def test_placeholder_is_P_not_G(self):
        # placeholder options are all 缺失; that must not be mistaken for graphic
        self.assertEqual(self._classify("征集", ["缺失"] * 4), "P")

    def test_graphic_label_options_is_G(self):
        self.assertEqual(self._classify("图形规律", ["A", "B", "C", "D"]), "G")

    def test_real_text_is_T(self):
        self.assertEqual(self._classify("题干", ["甲", "乙", "丙", "丁"]), "T")

    def test_blank_stem_is_M_even_with_options(self):
        self.assertEqual(self._classify("   ", ["甲", "乙", "丙", "丁"]), "M")

    def test_missing_stem_beats_placeholder_options(self):
        # no stem at all is the stronger signal
        self.assertEqual(self._classify("", ["缺失"] * 4), "M")


class TestSourceUrlPolicy(unittest.TestCase):
    def test_allowed_hosts_and_params(self):
        self.assertTrue(V.HOST_OK.search("fb.fbstatic.cn"))
        self.assertTrue(V.HOST_OK.search("fb.fenbike.cn"))
        self.assertTrue(V.HOST_OK.search("fb.fenbi.com"))
        self.assertFalse(V.HOST_OK.search("evil.example.com"))
        # a look-alike suffix must not pass
        self.assertFalse(V.HOST_OK.search("notfbstatic.cn"))

    def test_param_allowlist(self):
        self.assertEqual(V.PARAM_OK, {"width", "fontSize"})


class TestMaterialBlockAttribution(unittest.TestCase):
    """Regression: images inside a 材料 block belong to the material.

    Attributing by nearest preceding *question* header silently reassigns every
    material figure to the previous question, which produced a false
    "donor figures dropped" finding during the audit.
    """

    MD = (
        "# t\n\n"
        "## 第 1 题\n\n<img src=\"../../图片/省考-江苏-2025-行测-C类/题目图/aaa.png\">\n\n"
        "## 材料 1（第2—3题共用）\n\n<img src=\"../../图片/省考-江苏-2025-行测-C类/公式图/bbb.png\">\n\n"
        "## 第 2 题\n\ntext\n\n"
        "## 第 3 题\n\n<img src=\"../../图片/省考-江苏-2025-行测-C类/题目图/ccc.png\">\n"
    )

    def test_material_image_not_attributed_to_previous_question(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.md")
            open(p, "w", encoding="utf8").write(self.MD)
            _, refs, by_q, by_mat, unattributed = V.parse_md(p)
        self.assertEqual(by_q[1], ["aaa.png"])
        self.assertEqual(by_q[3], ["ccc.png"])
        self.assertNotIn("bbb.png", by_q.get(1, []))
        self.assertEqual(by_mat[1], ["bbb.png"])
        self.assertEqual(unattributed, [])

    def test_owning_tree_key_extracted(self):
        # the audit infers the owning paper tree from the path; make sure the
        # third-from-last segment is what we think it is
        raw = "../../图片/省考-江苏-2025-行测-A类/题目图/x.png"
        self.assertEqual(raw.split("/")[-3], "省考-江苏-2025-行测-A类")


class TestDeclaredDimensionParsing(unittest.TestCase):
    def test_px_suffix_optional(self):
        tag = '<img width="700px" height="201" src="a.png">'
        self.assertEqual(int(V.WIDTH.search(tag).group(1)), 700)
        self.assertEqual(int(V.HEIGHT.search(tag).group(1)), 201)


@unittest.skipUnless(REPO and os.path.isdir(REPO), "ASSETSQA_REPO not set")
class TestBackfillReportIntegrity(unittest.TestCase):
    def test_report_added_numbers_and_no_new_image_paths(self):
        p = os.path.join(REPO, "reports/FREE-TOOLS-JS2025C-20261016.json")
        if not os.path.isfile(p):
            self.skipTest("backfill report absent")
        d = json.load(open(p, encoding="utf8"))
        self.assertEqual(d["new_image_paths"], 0)
        self.assertEqual(d["reused_new_question_image_reference_count"], 2)
        self.assertEqual(sorted(d["added_original_numbers"]),
                         [27, 29, 35, 36, 37, 42, 75, 77, 78, 80, 81, 85])
        # the structured "missing" field claims completeness; the added list is
        # the real provenance record. Keep both visible.
        self.assertEqual(d["missing_original_numbers"], [])

    def test_borrowed_images_live_in_sibling_tree(self):
        p = os.path.join(REPO, "reports/FREE-TOOLS-JS2025C-20261016.json")
        if not os.path.isfile(p):
            self.skipTest("backfill report absent")
        d = json.load(open(p, encoding="utf8"))
        borrowed = {}
        for rec in d["questions"]:
            for img in rec.get("existing_image_reuse") or []:
                borrowed[rec["number"]] = img["path"]
        self.assertEqual(sorted(borrowed), [81, 85])
        for path in borrowed.values():
            self.assertIn("行测-A类", path)
            self.assertNotIn("行测-C类", path)


@unittest.skipUnless(HANDOFF and os.path.isdir(HANDOFF), "ASSETSQA_HANDOFF not set")
class TestHandoffFacts(unittest.TestCase):
    def _canon(self, key):
        p = os.path.join(HANDOFF, "papers", key, "canonical.json")
        if not os.path.isfile(p):
            self.skipTest("handoff paper absent")
        return json.load(open(p, encoding="utf8"))

    def test_handoff_ships_no_asset_bytes(self):
        root = os.path.join(HANDOFF, "papers")
        idx = os.path.join(root, "js-2025-xingce-c-4189916", "assets-index.json")
        if not os.path.isfile(idx):
            self.skipTest("handoff paper absent")
        assets = json.load(open(idx, encoding="utf8"))["assets"]
        present = [a for a in assets if os.path.isfile(os.path.join(HANDOFF, a["relativePath"]))]
        self.assertEqual(present, [], "handoff unexpectedly ships image bytes")

    def test_js2025c_placeholder_numbers_match_repo_backfill_list(self):
        c = self._canon("js-2025-xingce-c-4189916")
        unm = sorted(c["reconciliation"]["unmatchedSourceNumbers"])
        self.assertEqual(unm, [27, 29, 35, 36, 37, 42, 75, 77, 78, 80, 81, 85])

    def test_q81_q85_are_placeholders_in_the_capture(self):
        """In the handoff, Q81/Q85 are crowdsourcing placeholders -- NOT graphic
        questions. The repository turns them into graphic questions by reusing
        the A-class donor, which is exactly the divergence under audit."""
        c = self._canon("js-2025-xingce-c-4189916")
        by = {q["sourceNumber"]: q for q in c["questions"]}
        for n in (81, 85):
            opts = by[n]["options"]
            self.assertTrue(all((o.get("text") or "").strip() == "缺失" for o in opts),
                            f"Q{n} should be a placeholder in the capture")
        self.assertIn(81, c["reconciliation"]["unmatchedSourceNumbers"])
        self.assertIn(85, c["reconciliation"]["unmatchedSourceNumbers"])

    def test_graphic_questions_have_label_only_options(self):
        c = self._canon("js-2025-xingce-c-4189916")
        g = [q["sourceNumber"] for q in c["questions"]
             if q["options"] and all((o.get("text") or "").strip() == o.get("label")
                                     for o in q["options"])]
        self.assertEqual(g, [82, 83, 84, 87, 88, 89, 90])
        # none of the label-only graphic questions may be placeholder-flagged
        for n in g:
            self.assertNotIn(n, c["reconciliation"]["unmatchedSourceNumbers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
