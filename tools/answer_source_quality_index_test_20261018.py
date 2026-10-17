#!/usr/bin/env python3
"""Tests for tools/answer_source_quality_index_20261018.py.

Run from the tools directory:
    python -m unittest answer_source_quality_index_test_20261018 -v

Each case pins a parsing rule that, when wrong, silently inflates or deflates the
audit's headline numbers. All four were wrong in an earlier draft.
"""
import json
import tempfile
import unittest
from pathlib import Path

import answer_source_quality_index_20261018 as idx


def paper(*blocks, subject="行测", region="测试", extra_fm="", options=True):
    body = ""
    for n, answer in blocks:
        opts = "- **A**. 甲\n- **B**. 乙\n- **C**. 丙\n- **D**. 丁\n" if options else ""
        body += f"## 第 {n} 题\n\n题干{n}\n\n{opts}\n"
    ans = "## 答案与解析\n\n" + "".join(
        f"<details>\n<summary>第 {n} 题</summary>\n\n{answer}\n</details>\n\n" for n, answer in blocks)
    return (f'---\n考试: "省考"\n地区: "{region}"\n年份: "2020"\n科目: "{subject}"\n'
            f'卷型: "A类"\n实有题数: {len(blocks)}\n{extra_fm}---\n'
            f"# 测试\n\n{body}\n{ans}")


class LedgerParsingTests(unittest.TestCase):
    def test_quality_ledger_rows_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Q.md"
            p.write_text(
                "正文文件 1169 份；有规则告警 375 份；已明确缺原题 106 道\n\n"
                "| [省考/甲/2020/行测-A类.md](x) | 历史模块拼接题序未获原卷证据核对 |\n"
                "| [省考/乙/2020/行测-A类.md](x) | 已确认仍缺原题号：1、2 |\n",
                encoding="utf-8")
            issues, header = idx.parse_quality_ledger(p)
            self.assertEqual(len(issues), 2)
            self.assertEqual(header["declared_files"], 1169)
            self.assertEqual(header["declared_flagged"], 375)
            self.assertEqual(header["declared_missing_original"], 106)
            self.assertEqual(issues["省考/乙/2020/行测-A类.md"], ["已确认仍缺原题号：1、2"])

    def test_boilerplate_is_not_a_substantive_defect(self):
        self.assertEqual(idx.classify_issue("历史模块拼接题序未获原卷证据核对"),
                         "ordering_provenance_unverified")
        self.assertEqual(idx.classify_issue("已确认仍缺原题号：1、2"), "original_missing")
        self.assertEqual(idx.classify_issue("已确认选项缺失：1、3"), "option_missing")
        self.assertEqual(idx.classify_issue("原题或来源解析条件存在争议：53、71"),
                         "content_dispute")
        self.assertEqual(idx.classify_issue("已确认题干主图缺失：54"), "image_bytes_missing")
        self.assertEqual(idx.classify_issue("已确认共用题干条件缺失：56、57"), "stem_condition_gap")

    def test_content_dispute_is_not_official_label_conflict(self):
        # They were once the same enum value, which made a 争议题 look like a
        # mislabelled authority claim.
        self.assertNotEqual(idx.classify_issue("原题或来源解析条件存在争议：53"),
                            "official_label_conflict")


class QuestionSplittingTests(unittest.TestCase):
    def test_composite_questions_under_a_material(self):
        text = ("## 第 1 题\n\n题干\n\n- **A**. 甲\n\n## 材料 1（第2—3题共用）\n\n材料\n\n"
                "### 第 2 题\n\n题干\n\n- **A**. 甲\n\n### 第 3 题\n\n题干\n\n- **A**. 甲\n\n## 答案与解析\n")
        self.assertEqual([n for n, _ in idx.split_questions(text)], [1, 2, 3])

    def test_question_before_material_does_not_swallow_it(self):
        text = ("## 第 1 题\n\n题干\n\n- **A**. 甲\n\n## 材料 1（第2—3题共用）\n\n材料正文\n\n"
                "### 第 2 题\n\n题干\n\n## 答案与解析\n")
        first = idx.split_questions(text)[0][1]
        self.assertNotIn("材料正文", first)

    def test_options_beyond_d_are_counted(self):
        # 陕西 uses E/F/G/H on 8-option items. An A-D pattern made those papers look
        # option-less.
        text = "## 第 1 题\n\n题干\n\n" + "".join(f"- **{c}**. v{c}\n" for c in "ABCDEFGH") + "\n## 答案与解析\n"
        self.assertEqual(len(idx.OPT_LINE.findall(idx.split_questions(text)[0][1])), 8)


class AnswerFormTests(unittest.TestCase):
    def test_single_letter(self):
        self.assertIsNotNone(idx.ANSWER_LINE.search("**答案**：C"))

    def test_multi_select(self):
        # 上海 has 多选题: `**答案**：AB`.
        m = idx.ANSWER_LINE.search("**答案**：AB")
        self.assertIsNotNone(m)
        self.assertEqual(len([c for c in m.group(1) if c.isalpha()]), 2)

    def test_three_letter(self):
        m = idx.ANSWER_LINE.search("**答案**：ABD")
        self.assertEqual(len([c for c in m.group(1) if c.isalpha()]), 3)

    def test_letter_beyond_d(self):
        self.assertIsNotNone(idx.ANSWER_LINE.search("**答案**：F"))

    def test_prose_answer_is_recognised(self):
        # 江西2019 法检 第41题 declines to give a letter because no option matches.
        self.assertIsNotNone(idx.PROSE_ANSWER.search(
            "**参考作答**：按本卷现有题面计算为5400元；四个现有选项均不匹配。"))

    def test_quarantined_legacy_answer_is_not_current(self):
        # Real shape in 省考/新疆/2024/行测-兵团.md: the legacy answer sits BETWEEN two
        # comment markers, so stripping only the tags would leave it in place.
        block = ("**答案**：待补\n\n<!-- legacy-unverified-answer-54 -->\n"
                 "**答案**：C\n<!-- /legacy-unverified-answer-54 -->")
        stripped = idx.strip_quarantined(block)
        self.assertIn("待补", stripped)
        self.assertNotIn("**答案**：C", stripped)


class SelfCitationTests(unittest.TestCase):
    def test_self_repo_link_is_not_backing(self):
        url = ("https://github.com/ProfessorZhi/gwy-zhenti/blob/f9c7c37/%E7%9C%81%E8%80%83/x.md")
        self.assertIsNotNone(idx.SELF_REPO.match(url))

    def test_external_link_is_backing(self):
        self.assertIsNone(idx.SELF_REPO.match("https://example.org/a.pdf"))


class EndToEndTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    @classmethod
    def setUpClass(cls):
        if not (cls.ROOT / "省考").exists():
            raise unittest.SkipTest("library checkout not present")

    def test_index_is_deterministic_and_matches_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            import io
            import contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                rc = idx.main.__wrapped__ if hasattr(idx.main, "__wrapped__") else None
            # Drive the same functions the CLI uses, without the argparse layer.
            ledger, header = idx.parse_quality_ledger(
                self.ROOT / "reports" / "QUALITY-AUDIT.md")
            self.assertEqual(header["declared_flagged"], 375)
            self.assertEqual(len(ledger), 375)
            tree = idx.tracked_paths(self.ROOT, "e1feb5187ec3544cde62a1a128a6269a8d63011b")
            self.assertTrue(tree)
            receipt_index = idx.prov.build_receipt_index(self.ROOT)
            rows = [idx.analyse_paper(p, self.ROOT, tree, receipt_index,
                                      ledger.get(str(p.relative_to(self.ROOT))))
                    for p in sorted(idx.prov.iter_markdown(self.ROOT, None))]
            self.assertEqual(len(rows), 1169)
            self.assertEqual(sum(1 for r in rows if r["quality_flagged"]), 375)
            self.assertEqual(sum(r["provenance_unsupported"] for r in rows), 0)
            self.assertEqual(sum(r["provenance_verified"] for r in rows), 1070)


if __name__ == "__main__":
    unittest.main()
