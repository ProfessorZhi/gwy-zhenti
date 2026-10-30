# -*- coding: utf-8 -*-
"""A1 machine summary must count real source placeholders, not just frontmatter."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cloud_quality  # noqa: E402
import gap_content_audit  # noqa: E402


class MachineGapSummaryConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.machine = cloud_quality.scan(ROOT)
        cls.findings, cls.content = gap_content_audit.scan(ROOT)
        cls.saved = json.loads(
            (ROOT / "reports/QUALITY-SUMMARY.json").read_text(encoding="utf-8"))

    def test_live_source_placeholders_match_question_audit(self):
        self.assertEqual(
            self.content["a1_open_body_placeholder"],
            self.machine["source_placeholder_question_positions"],
        )
        self.assertEqual(
            self.machine["confirmed_missing_original_questions"],
            self.machine["source_placeholder_question_positions"]
            + self.machine["missing_original_numbers_declared"],
            "The current corpus has no overlap/other metadata-only numbers.",
        )
        self.assertEqual(280, self.machine["confirmed_missing_original_questions"])
        self.assertEqual(1683, self.machine["paper_files"])

    def test_published_quality_summary_matches_live_scan(self):
        for key in (
            "confirmed_missing_original_questions",
            "source_placeholder_question_positions",
            "missing_original_numbers_declared",
            "image_references",
            "paper_files",
            "inventory_sha256",
        ):
            self.assertEqual(self.machine[key], self.saved[key], key)


if __name__ == "__main__":
    unittest.main()
