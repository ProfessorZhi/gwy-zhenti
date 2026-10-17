# -*- coding: utf-8 -*-
"""北京2026行测51缺号的跨版本/重复/异序复核与P0/P1台账自检。

只校验结构、集合、状态与“零正文/零图片”边界；不把第三方题面当夹具。
"""
import hashlib
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MD = os.path.join(ROOT, "省考", "北京", "2026", "行测-统考.md")
REPORT = os.path.join(ROOT, "reports", "BEIJING2026-CROSSCHECK-P0P1-20261018.json")
BLOB = "1e67c838d565873f10b0b32b956e654b55b8cb65"
EXPECTED_MISSING = [
    2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 22, 31,
    34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 89, 90, 96, 97, 98, 99,
    100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 112, 114,
    115, 117,
]
EXPECTED_P0 = set(range(96, 111)) | {89, 90, 112, 114, 115}
EXPECTED_P1 = set(EXPECTED_MISSING) - EXPECTED_P0


def load():
    with open(REPORT, encoding="utf-8") as fh:
        return json.load(fh)


class TestBeijing2026CrosscheckP0P1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load()
        with open(MD, encoding="utf-8") as fh:
            cls.md = fh.read()

    def test_missing_is_still_51_and_unchanged(self):
        present = sorted(int(n) for n in re.findall(r"^#{2,3} 第 (\d+) 题", self.md, re.M))
        self.assertEqual(len(present), 67)
        self.assertEqual(sorted(set(range(1, 119)) - set(present)), EXPECTED_MISSING)
        self.assertEqual(self.report["crosscheck"]["numbering"]["missing_count"], 51)

    def test_p0_p1_sets_are_exact_and_disjoint(self):
        rows = self.report["p0_p1"]["rows"]
        p0 = {r["number"] for r in rows if r["priority"] == "P0"}
        p1 = {r["number"] for r in rows if r["priority"] == "P1"}
        self.assertEqual(p0, EXPECTED_P0)
        self.assertEqual(p1, EXPECTED_P1)
        self.assertFalse(p0 & p1)
        self.assertEqual(p0 | p1, set(EXPECTED_MISSING))
        self.assertEqual(len(p0), 20)
        self.assertEqual(len(p1), 31)
        self.assertEqual(self.report["p0_p1"]["p0_count"], 20)
        self.assertEqual(self.report["p0_p1"]["p1_count"], 31)

    def test_every_row_is_blocked_without_candidate_text(self):
        rows = self.report["p0_p1"]["rows"]
        self.assertEqual(len(rows), 51)
        self.assertEqual(len({r["number"] for r in rows}), 51)
        for r in rows:
            self.assertEqual(r["status"], "blocked_no_verified_source")
            self.assertIsNone(r["candidate_source"])
            self.assertEqual(set(r["evidence"]), {"E1", "E2", "E3", "E4", "E5", "E6"})
            self.assertIn(r["priority"], {"P0", "P1"})

    def test_crosscheck_concludes_zero_reduction(self):
        c = self.report["crosscheck"]
        self.assertEqual(c["repo_versions"]["alternate_versions_found"], 0)
        self.assertEqual(c["repo_versions"]["blob_all_refs"], BLOB)
        self.assertEqual(c["inventory"]["answers_for_missing_numbers"], 0)
        self.assertEqual(c["inventory"]["images_for_missing_numbers"], 0)
        self.assertEqual(c["within_2026_duplicates"]["substantive_duplicates"], 0)
        self.assertEqual(c["cross_year_duplicates"]["substantive_duplicates"], 0)
        self.assertEqual(c["conclusion"]["explained_by_duplicate_or_order"], 0)
        self.assertEqual(c["conclusion"]["recovered_numbers"], 0)
        self.assertEqual(c["conclusion"]["still_missing"], 51)

    def test_current_blob_matches_declared_single_version(self):
        out = subprocess.check_output(
            ["git", "-C", ROOT, "rev-parse", "HEAD:省考/北京/2026/行测-统考.md"],
            text=True,
        ).strip()
        self.assertEqual(out, BLOB)
        with open(MD, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(sha, self.report["baseline"]["paper_sha256"])

    def test_two_whole_papers_are_blocked_not_fabricated(self):
        c = self.report["completeness"]
        x = c["beijing_2024_xingce"]
        s = c["beijing_2026_shenlun"]
        self.assertEqual(x["status"], "blocked")
        self.assertTrue(x["official_exam_confirmed"])
        self.assertEqual(x["exam_date"], "2023-12-03")
        self.assertIsNone(x["repo_file"])
        self.assertEqual(x["new_content_added"], 0)
        self.assertIn("C03", x["candidates"])
        self.assertEqual(s["status"], "blocked")
        self.assertTrue(s["official_exam_confirmed"])
        self.assertEqual(s["exam_date"], "2025-12-07")
        self.assertFalse(s["full_materials_obtained"])
        self.assertIsNone(s["repo_file"])
        self.assertEqual(s["new_content_added"], 0)

    def test_no_third_party_bodies_or_images(self):
        with open(REPORT, encoding="utf-8") as fh:
            text = fh.read()
        for token in (".png", ".jpg", ".jpeg", "base64", "<img"):
            self.assertNotIn(token, text, token)

        def keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield k
                    yield from keys(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from keys(v)

        forbidden = {"stem", "options", "answer_text", "analysis_text", "content_html", "materials_text"}
        self.assertFalse(set(keys(self.report)) & forbidden)
        self.assertEqual(self.report["summary"]["new_legal_content"], 0)
        self.assertEqual(self.report["summary"]["questions_added"], 0)
        self.assertEqual(self.report["summary"]["images_added"], 0)

    def test_source_ledger_matches_summary(self):
        self.assertEqual(len(self.report["sources"]), self.report["summary"]["new_sources_checked"])
        ids = {s["id"] for s in self.report["sources"]}
        for ref in ("C01", "C02", "C03", "C07", "C08", "C09", "C10"):
            self.assertIn(ref, ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
