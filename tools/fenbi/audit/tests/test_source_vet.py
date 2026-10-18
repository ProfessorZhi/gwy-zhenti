#!/usr/bin/env python3
"""Regression tests for the source-candidate pre-flight gate.

Run from the repository root:

    python3 -m unittest discover -s tools/fenbi/audit/tests -t .

Fixtures are synthetic and contain no real question text. They exist to prove
that a candidate source which merely *lists* a number — or lists it with a
collection stub — is never counted as recovering that question.
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.dirname(HERE)
sys.path.insert(0, AUDIT)

import source_candidate_vet as vet  # noqa: E402

PAPER = "省考/江苏/2026/行测-A类.md"

STUB = "题目正在全力以赴征集，将会第一时间上传"
STUB_LONG = "题目正在全力以赴征集，将会在征集到后第一时间上传"


def repo_root():
    return os.path.abspath(os.path.join(AUDIT, os.pardir, os.pardir, os.pardir))


class ManifestExtractionTests(unittest.TestCase):
    """The gap list must come from the manifest, never from a hardcoded list."""

    @classmethod
    def setUpClass(cls):
        cls.doc = vet.build(repo_root(), PAPER)

    def test_declared_gaps_are_forty_two(self):
        self.assertEqual(self.doc["paper"]["declared_missing_count"], 42)
        self.assertEqual(len(self.doc["items"]), 42)

    def test_declared_numbers_match_the_known_manifest(self):
        self.assertEqual(self.doc["paper"]["declared_missing"], [
            16, 17, 18, 19, 20, 21, 22, 23,
            32, 33, 34, 35, 36, 37, 38, 39, 40,
            86, 87, 88, 89, 90, 91, 92, 93,
            102, 103, 104, 105, 106, 107, 108,
            126, 127, 128, 129, 130, 131, 132, 133, 134, 135,
        ])

    def test_gap_runs_are_the_five_declared_blocks(self):
        self.assertEqual(self.doc["paper"]["gap_runs"], [
            {"from": 16, "to": 23, "count": 8},
            {"from": 32, "to": 40, "count": 9},
            {"from": 86, "to": 93, "count": 8},
            {"from": 102, "to": 108, "count": 7},
            {"from": 126, "to": 135, "count": 10},
        ])

    def test_all_declared_numbers_are_absent_from_the_library(self):
        for item in self.doc["items"]:
            self.assertEqual(item["library_state"], "absent-gap-preserved")

    def test_paper_is_a_recollection_fragment_not_official(self):
        self.assertEqual(self.doc["paper"]["provenance_nature"], "网友回忆残卷")

    def test_no_source_supplied_is_blocked(self):
        self.assertEqual(self.doc["summary"]["verdict"], "blocked-no-source-supplied")
        self.assertEqual(self.doc["summary"]["source_not_supplied"], 42)
        self.assertEqual(self.doc["summary"]["source_content"], 0)


class SourceClassificationTests(unittest.TestCase):
    """A listed number is not a recovery; a stub is not content."""

    def vet_text(self, text, source_format="text"):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(text)
            path = fh.name
        try:
            return vet.build(repo_root(), PAPER, source_path=path,
                             source_format=source_format)
        finally:
            os.unlink(path)

    def test_stub_source_yields_no_recoverable_content(self):
        doc = self.vet_text(f"2026年江苏省 行测\n16.{STUB}\nA.缺失 B.缺失\n"
                            f"17.{STUB_LONG}\nA.缺失 B.缺失\n")
        self.assertEqual(doc["summary"]["source_content"], 0)
        self.assertEqual(doc["summary"]["source_stub"], 2)
        self.assertEqual(doc["summary"]["verdict"], "no-recoverable-content-stub-present")

    def test_stub_is_never_counted_as_content(self):
        doc = self.vet_text(f"2026年江苏省 行测\n16.{STUB}\n")
        item = next(i for i in doc["items"] if i["number"] == 16)
        self.assertEqual(item["source"]["state"], "stub")
        self.assertIn("collection_pending", item["source"]["markers"])

    def test_source_without_the_numbers_lacks_the_gaps(self):
        doc = self.vet_text("2026年江苏省 行测\n1.合成占位题干。\nA.甲\n")
        self.assertEqual(doc["summary"]["source_content"], 0)
        self.assertEqual(doc["summary"]["verdict"], "candidate-lacks-the-gaps")

    def test_real_text_at_a_gap_number_is_counted(self):
        doc = self.vet_text("2026年江苏省 行测\n"
                            "16.合成占位题干：这是一道确有正文的题目。\nA.甲 B.乙\n")
        item = next(i for i in doc["items"] if i["number"] == 16)
        self.assertEqual(item["source"]["state"], "content")
        self.assertEqual(doc["summary"]["source_content"], 1)
        self.assertEqual(doc["summary"]["verdict"], "candidate-covers-some-gaps")

    def test_a_complete_synthetic_source_covers_all_gaps(self):
        declared = vet.build(repo_root(), PAPER)["paper"]["declared_missing"]
        body = "\n".join(f"{n}.合成占位题干第{n}题。\nA.甲 B.乙 C.丙 D.丁"
                         for n in declared)
        doc = self.vet_text("2026年江苏省公务员 行测 A类\n" + body)
        self.assertEqual(doc["summary"]["source_content"], 42)
        self.assertEqual(doc["summary"]["verdict"], "candidate-covers-all-gaps")

    def test_identity_tokens_are_checked(self):
        doc = self.vet_text("2026年江苏省公务员录用考试 行测 A类\n16.合成占位题干。\n")
        self.assertTrue(doc["candidate"]["identity_ok"])
        self.assertTrue(all(doc["candidate"]["identity_tokens"].values()))

    def test_wrong_paper_identity_is_flagged(self):
        doc = self.vet_text("2024年广东省公务员考试 申论 B类\n16.合成占位题干。\n")
        self.assertFalse(doc["candidate"]["identity_ok"])

    def test_html_source_is_accepted(self):
        doc = self.vet_text("<html><body><p>2026年江苏省 行测</p>"
                            f"<p>16.{STUB}</p></body></html>", source_format="html")
        self.assertTrue(doc["candidate"]["supplied"])
        # The html wrapper must not hide the stub classification.
        self.assertEqual(doc["summary"]["source_stub"], 1)


class ContextInferenceTests(unittest.TestCase):
    """Type hints must survive a run of consecutive gaps."""

    @classmethod
    def setUpClass(cls):
        cls.doc = vet.build(repo_root(), PAPER)

    def test_context_skips_over_neighbouring_gaps(self):
        item = next(i for i in self.doc["items"] if i["number"] == 16)
        # 15 exists, 17-23 do not: the previous context must still be found.
        self.assertIsNotNone(item["neighbour_context"]["previous_type"])

    def test_interior_gap_gets_a_type_from_the_nearest_survivor(self):
        item = next(i for i in self.doc["items"] if i["number"] == 23)
        self.assertIsNotNone(item["expected_type"])

    def test_tail_gap_has_no_next_context(self):
        item = next(i for i in self.doc["items"] if i["number"] == 135)
        self.assertIsNone(item["neighbour_context"]["next_type"])


class ToolHygieneTests(unittest.TestCase):
    def test_tool_emits_no_question_text(self):
        doc = vet.build(repo_root(), PAPER)
        blob = json.dumps(doc, ensure_ascii=False)
        for phrase in ("巍巍华山", "国家作物种质库", "数字游民", "压舱石"):
            self.assertNotIn(phrase, blob)

    def test_tool_has_no_absolute_host_paths(self):
        with open(os.path.join(AUDIT, "source_candidate_vet.py"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("/home/", text)
        self.assertNotIn("/Users/", text)

    def test_policy_states_stub_is_not_content(self):
        doc = vet.build(repo_root(), PAPER)
        joined = " ".join(doc["policy"])
        self.assertIn("stub is not content", joined)
        self.assertIn("front matter", joined)


if __name__ == "__main__":
    unittest.main()
