# -*- coding: utf-8 -*-
"""Conservative option/answer gap scanner regression tests."""
from pathlib import Path
import csv
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from gap_content_audit import (A1_STUB, answer_findings, frontmatter,
                               option_findings, question_blocks, scan)


class GapContentAuditTest(unittest.TestCase):
    def test_question_headers_and_placeholder(self):
        s = f"## 第 1 题　<sub>qid 42</sub>\n{A1_STUB}\n\n### 第 2 题\n实际题干\n"
        blocks = list(question_blocks(s))
        self.assertEqual([n for n, _ in blocks], [1, 2])
        self.assertIn(A1_STUB, blocks[0][1])

    def test_full_option_placeholder_is_confirmed(self):
        stem = "\n".join(["下列正确的是：", "A. 缺", "B. 缺",
                          "C. 缺", "D. 缺"])
        state, info = option_findings(stem)
        self.assertEqual(state, "a2_confirmed_option_placeholders")
        self.assertEqual(len(info["stub_labels"]), 4)

    def test_real_word_missing_is_not_confirmed(self):
        stem = "\n".join(["在家庭监管___的情况下", "A. 缺失",
                          "B. 薄弱", "C. 不力", "D. 缺乏"])
        state, _ = option_findings(stem)
        self.assertNotEqual(state, "a2_confirmed_option_placeholders")

    def test_option_shortfall_is_review_not_confirmed(self):
        state, _ = option_findings("A. 甲\nB. 乙\nC. 丙\n")
        self.assertEqual(state, "a2_review_option_format")

    def test_explicit_no_answer_beats_long_explanation(self):
        body = ("**同题参考作答**\n"
                "未收录同卷同题的完整参考答案；不以自动生成内容冒充来源答案。\n"
                "> 原答案映射是另一张卷，不能采用。" * 9)
        self.assertEqual(answer_findings(body, "申论", False),
                         "b2_confirmed_explicit_no_answer")

    def test_normal_answer_and_unknown_explanation_not_missing(self):
        body = "**参考答案（粉笔题库参考内容）**\n\nB\n\n**解析状态：unknown（来源未提供）**"
        self.assertEqual(answer_findings(body, "行测", False), "")

    def test_metadata_missing_numbers_parse(self):
        text = '---\n科目: "申论"\n缺参考答案题号: [1, 4]\n---\n'
        self.assertEqual(frontmatter(text)["缺参考答案题号"], [1, 4])


class LiveGapLedgerTest(unittest.TestCase):
    def test_current_confirmed_ledger_matches_current_papers(self):
        """Avoid publishing stale A2/B2 numbers after a future content change."""
        with (ROOT / "reports/GAP-CURRENT-CONFIRMED-20261030.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            documented = list(csv.DictReader(handle))
        self.assertEqual(293, len(documented))
        keys = [(r["paper_path"], int(r["question_number"])) for r in documented]
        self.assertEqual(len(keys), len(set(keys)), "issue keys must be unique")

        findings, summary = scan(ROOT)
        a2_types = {"a2_confirmed_option_placeholders",
                    "a2_confirmed_single_option_placeholder"}
        a2 = {(r["path"], r["question"]) for r in findings if r["type"] in a2_types}
        b2 = {(r["path"], r["question"]) for r in findings
              if r["type"] == "b2_confirmed_explicit_no_answer"}
        expected_a2 = {(r["paper_path"], int(r["question_number"]))
                       for r in documented if r["issue_type"] == "A2"}
        expected_b2 = {(r["paper_path"], int(r["question_number"]))
                       for r in documented if r["issue_type"] == "B2"}
        self.assertEqual(expected_a2, a2)
        self.assertEqual(expected_b2, b2)
        self.assertEqual(280, summary["a1_open_body_placeholder"])
        self.assertEqual(3, len([r for r in findings
                                 if r["type"] == "a2_confirmed_single_option_placeholder"]))
        self.assertEqual(13, summary["a2_excluded_valid_literal"])
        self.assertEqual(7, len(b2))
        self.assertEqual(6, len(a2))
        self.assertEqual(90_123, summary["question_blocks"])
        self.assertEqual(1_683, summary["inventory_papers"])


if __name__ == "__main__":
    unittest.main()
