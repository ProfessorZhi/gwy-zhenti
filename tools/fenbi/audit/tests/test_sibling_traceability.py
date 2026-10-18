#!/usr/bin/env python3
"""Regression tests for sibling-paper traceability.

Run from the repository root:

    python3 -m unittest discover -s tools/fenbi/audit/tests -t .

The unit tests use synthetic fingerprints. The repo tests assert measured
properties of the current catalog, which is what justifies refusing to
substitute a sibling paper's same-numbered question.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.dirname(HERE)
sys.path.insert(0, AUDIT)

import sibling_traceability as st  # noqa: E402


def repo_root():
    return os.path.abspath(os.path.join(AUDIT, os.pardir, os.pardir, os.pardir))


class ComparePairUnitTests(unittest.TestCase):
    """The metric itself, on synthetic data."""

    def test_identical_papers_measure_one(self):
        a = {1: "AAA", 2: "BBB", 3: "CCC"}
        pair = st.compare_pair(a, dict(a))
        self.assertEqual(pair["identical_rate"], 1.0)
        self.assertEqual(pair["text_identical"], 3)

    def test_disjoint_content_measures_zero(self):
        a = {1: "AAA", 2: "BBB"}
        b = {1: "XXX", 2: "YYY"}
        pair = st.compare_pair(a, b)
        self.assertEqual(pair["identical_rate"], 0.0)
        self.assertEqual(pair["text_identical"], 0)

    def test_no_overlap_gives_none_rate(self):
        pair = st.compare_pair({1: "AAA"}, {2: "BBB"})
        self.assertEqual(pair["same_number_overlap"], 0)
        self.assertIsNone(pair["identical_rate"])

    def test_empty_stems_never_count_as_identical(self):
        pair = st.compare_pair({1: "", 2: "AAA"}, {1: "", 2: "AAA"})
        self.assertEqual(pair["text_identical"], 1)  # only number 2

    def test_partial_overlap_is_reported_not_extrapolated(self):
        a = {n: f"Q{n}" for n in range(1, 11)}
        b = {n: (f"Q{n}" if n <= 3 else f"R{n}") for n in range(1, 11)}
        pair = st.compare_pair(a, b)
        self.assertEqual(pair["same_number_overlap"], 10)
        self.assertEqual(pair["text_identical"], 3)
        self.assertEqual(pair["identical_rate"], 0.3)

    def test_threshold_is_strict(self):
        self.assertGreaterEqual(st.SUBSTITUTION_RATE_THRESHOLD, 0.95)


class GapPaperSurveyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = st.build_all(repo_root()) if hasattr(st, "build_all") else None
        records = st.load_records(repo_root())
        targets = [r for r in records if r.get("missing_original_numbers")]
        fps = {}
        for record in records:
            try:
                fps[record["path"]] = st.fingerprint(record["path"], repo_root())
            except FileNotFoundError:
                continue
        cls.results = {r["path"]: st.analyse(repo_root(), r, records, fps)
                       for r in targets}

    def test_every_gap_paper_is_covered(self):
        self.assertEqual(len(self.results), 5)
        for path in ("省考/北京/2026/行测-统考.md", "省考/江苏/2026/行测-A类.md",
                     "省考/广东/2020/行测-县级卷.md", "省考/江苏/2024/行测-A类.md",
                     "省考/浙江/2020/行测-A类.md"):
            self.assertIn(path, self.results)

    def test_no_substitution_is_ever_justified(self):
        for path, result in self.results.items():
            self.assertEqual(result["summary"]["siblings_justified_as_source"], 0, path)
            for item in result["items"]:
                self.assertFalse(item["substitution_justified"], path)
                self.assertEqual(item["evidence_level"], "unconfirmed", path)

    def test_no_gap_number_is_counted_as_recovered(self):
        for path, result in self.results.items():
            self.assertEqual(result["summary"]["gap_numbers_recovered"], 0, path)

    def test_guangdong_county_and_township_share_nothing(self):
        """The clearest case: zero identical questions at shared numbers."""
        result = self.results["省考/广东/2020/行测-县级卷.md"]
        self.assertEqual(len(result["siblings"]), 1)
        sib = result["siblings"][0]
        self.assertEqual(sib["paper_type"], "乡镇卷")
        self.assertEqual(sib["text_identical"], 0)
        self.assertEqual(sib["identical_rate"], 0.0)
        # All seven gap numbers exist in the sibling, yet none is evidence.
        self.assertEqual(result["summary"]["gap_numbers_with_any_lead"], 7)

    def test_jiangsu_2024_rates_are_far_below_threshold(self):
        result = self.results["省考/江苏/2024/行测-A类.md"]
        rates = {s["paper_type"]: s["identical_rate"] for s in result["siblings"]}
        self.assertIn("B类", rates)
        self.assertIn("C类", rates)
        self.assertLess(rates["B类"], st.SUBSTITUTION_RATE_THRESHOLD)
        self.assertLess(rates["C类"], st.SUBSTITUTION_RATE_THRESHOLD)
        # Measured base rate: same number implies same question only ~1/3 of the time.
        self.assertAlmostEqual(rates["B类"], 0.3511, places=3)

    def test_zhejiang_2020_rate_is_low(self):
        result = self.results["省考/浙江/2020/行测-A类.md"]
        self.assertEqual(len(result["siblings"]), 1)
        self.assertLess(result["siblings"][0]["identical_rate"], 0.2)
        self.assertFalse(result["siblings"][0]["substitution_justified"])

    def test_papers_without_siblings_get_no_leads(self):
        for path in ("省考/北京/2026/行测-统考.md", "省考/江苏/2026/行测-A类.md"):
            result = self.results[path]
            self.assertEqual(result["summary"]["siblings_examined"], 0, path)
            self.assertEqual(result["summary"]["gap_numbers_with_any_lead"], 0, path)

    def test_blocked_reason_is_stated_for_every_item(self):
        for path, result in self.results.items():
            for item in result["items"]:
                self.assertIn("lead", item["blocked_reason"], path)
                self.assertIn("cannot be assumed", item["blocked_reason"], path)


class HygieneTests(unittest.TestCase):
    def test_tool_emits_no_question_text(self):
        records = st.load_records(repo_root())
        target = next(r for r in records
                      if r["path"] == "省考/广东/2020/行测-县级卷.md")
        fps = {r["path"]: st.fingerprint(r["path"], repo_root()) for r in records
               if os.path.exists(os.path.join(repo_root(), r["path"]))}
        blob = json.dumps(st.analyse(repo_root(), target, records, fps),
                          ensure_ascii=False)
        for phrase in ("巍巍华山", "国家作物种质库", "压舱石", "苍鹰", "极简婚礼"):
            self.assertNotIn(phrase, blob)

    def test_tool_has_no_absolute_paths_or_network(self):
        with open(os.path.join(AUDIT, "sibling_traceability.py"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("/home/", text)
        self.assertNotIn("urllib", text)
        self.assertNotIn("requests", text)


if __name__ == "__main__":
    unittest.main()
