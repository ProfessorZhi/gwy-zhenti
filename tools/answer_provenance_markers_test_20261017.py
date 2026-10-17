#!/usr/bin/env python3
"""Tests for tools/answer_provenance_markers_20261017.py.

Run from the tools directory:
    python -m unittest answer_provenance_markers_test_20261017 -v
"""
import json
import tempfile
import unittest
from pathlib import Path

import answer_provenance_markers_20261017 as m


def block(qno: int, body: str) -> str:
    return (f"<details>\n<summary>第 {qno} 题</summary>\n\n{body}\n\n---\n\n</details>\n")


def paper(*blocks: str) -> str:
    return ('---\n考试: "省考"\n地区: "测试"\n年份: "2020"\n科目: "行测"\n卷型: "A类"\n---\n'
            "# 测试卷\n\n## 第 1 题\n\n题干\n\n- **A**. 甲\n- **B**. 乙\n\n"
            "## 答案与解析\n\n" + "\n".join(blocks))


class BlockSplittingTests(unittest.TestCase):
    def test_finds_each_block_with_its_printed_number(self):
        text = paper(block(1, "**答案**：A"), block(2, "**答案**：B"))
        self.assertEqual([n for n, _b, _s, _e in m.iter_answer_blocks(text)], [1, 2])

    def test_block_boundaries_do_not_bleed_into_the_next_block(self):
        text = paper(block(1, "**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n解析一。"),
                     block(2, "**答案**：B\n\n**答案性质**：独立校算参考答案（非官方）。"))
        blocks = list(m.iter_answer_blocks(text))
        self.assertNotIn("答案性质", blocks[0][1])
        self.assertIn("答案性质", blocks[1][1])

    def test_unterminated_block_still_yields_a_record(self):
        text = "## 答案与解析\n\n<details>\n<summary>第 1 题</summary>\n\n**答案**：A\n"
        self.assertEqual(len(list(m.iter_answer_blocks(text))), 1)

    def test_non_answer_details_are_ignored(self):
        text = "<details>\n<summary>不是题目</summary>\n正文\n</details>\n"
        self.assertEqual(list(m.iter_answer_blocks(text)), [])


class ClassificationTests(unittest.TestCase):
    def test_canonical_sourced_marker_is_canonical(self):
        info = m.classify_block("**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n解析。")
        self.assertTrue(info["declared"])
        self.assertTrue(info["canonical_marker"])
        self.assertEqual(info["authority_class"], "institution_reference")

    def test_disclaimer_outside_the_bold_span_is_a_variant_not_a_gap(self):
        # This is the real spelling used by 省考/浙江/2020/行测-A类.md. The disclaimer
        # is present and correct -- only its placement differs. Reporting it as
        # undeclared would be a false accusation.
        info = m.classify_block("**答案**：A\n\n**来源参考解析**（不是官方公布答案）\n\n解析。")
        self.assertTrue(info["declared"])
        self.assertFalse(info["canonical_marker"])

    def test_abbreviated_variant_is_declared(self):
        info = m.classify_block("**答案**：A\n\n**来源参考解析（非官方）**\n\n解析。")
        self.assertTrue(info["declared"])
        self.assertFalse(info["canonical_marker"])

    def test_alternative_field_name_is_declared_but_variant(self):
        info = m.classify_block("**答案**：B\n\n**答案性质**：独立校算参考答案（非官方，非来源原答案）。")
        self.assertTrue(info["declared"])
        self.assertFalse(info["canonical_marker"])

    def test_ai_assisted_marker_is_classified_ai_derived(self):
        info = m.classify_block(
            "**答案**：B\n\n**AI辅助独立校核解析（非官方答案，非王智公考原解析，未经实考评分）**\n\n解析。")
        self.assertTrue(info["declared"])
        self.assertTrue(info["canonical_marker"])
        self.assertEqual(info["authority_class"], "ai_derived")

    def test_plain_answer_with_no_declaration_is_a_gap(self):
        info = m.classify_block("**答案**：A\n\n因为甲最合适，所以选A。")
        self.assertFalse(info["declared"])
        self.assertIsNone(info["marker"])

    def test_disputed_source_is_classified_solver_dispute(self):
        info = m.classify_block("**答案**：C\n\n**来源参考解析（非官方标准答案）**\n\n> 校核提示：原件笔误。")
        self.assertEqual(info["authority_class"], "solver_dispute")

    def test_official_source_is_recognised(self):
        info = m.classify_block("**答案**：A\n\n本题答案依据官方公布答案。")
        self.assertTrue(info["declared"])
        self.assertEqual(info["authority_class"], "official_published")

    # -- negation regressions -------------------------------------------------
    # Misreading "NOT an official answer" as "an official answer" is the single
    # most damaging error this checker could make, so each real phrasing the
    # library uses gets its own case.

    def test_negated_official_inline_is_not_official(self):
        info = m.classify_block("**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n解析。")
        self.assertNotEqual(info["authority_class"], "official_published")

    def test_negated_official_with_words_between_is_not_official(self):
        # Real text: 省考/上海/2024/申论-A卷.md, 省考/内蒙古/2021/申论-乡镇.md, ...
        info = m.classify_block(
            "> 来源说明：从本库固定版本的同年、同地区同题记录补入。"
            "原记录卷型标记为“统考”，并非本卷的独立官方答案。")
        self.assertNotEqual(info["authority_class"], "official_published")

    def test_negated_official_with_bushi_is_not_official(self):
        info = m.classify_block("> 来源说明：不是官方标准答案，仅供参照。")
        self.assertNotEqual(info["authority_class"], "official_published")

    def test_distant_negation_does_not_suppress_a_real_official_claim(self):
        info = m.classify_block(
            "> 说明：本条与上一题不同，并非臆测。" + "补充说明若干。" +
            "本题答案依据官方公布答案。")
        self.assertEqual(info["authority_class"], "official_published")

    def test_bare_bu_negation_is_not_official(self):
        # Real text: 省考/天津/2016/申论-统考.md -- '不将其改称原创或官方答案'
        info = m.classify_block("> 来源说明：见恢复凭据，不将其改称原创或官方答案。不是来源作者原稿。")
        self.assertNotEqual(info["authority_class"], "official_published")

    def test_ye_bu_cheng_wei_negation_is_not_official(self):
        # Real text: 省考/江苏/2016/申论-B类.md -- '，不将C类答案移用，也不称为官方答案'
        info = m.classify_block("> 来源说明：不将C类答案移用，也不称为官方答案。")
        self.assertNotEqual(info["authority_class"], "official_published")

    def test_original_ai_collation_marker_is_ai_derived(self):
        # Real text: 省考/黑龙江/2019/行测-边境县.md
        info = m.classify_block("**答案**：B\n\n**原创校核解析（AI辅助整理，非官方标准答案）**\n\n解析。")
        self.assertEqual(info["authority_class"], "ai_derived")

    def test_inline_authorship_ai_note_is_ai_derived(self):
        # Real text: 省考/上海/2017/行测-统考.md
        info = m.classify_block(
            "> 来源说明：根据本卷原题独立重算；作者／整理性质为AI辅助修订，"
            "不是原机构作者原稿，不是官方答案，未经实考评分。")
        self.assertEqual(info["authority_class"], "ai_derived")


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "省考" / "甲").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, text: str):
        (self.root / "省考" / "甲" / name).write_text(text, encoding="utf-8")

    def test_scan_counts_declared_and_undeclared_separately(self):
        self.write("a.md", paper(block(1, "**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n解析。"),
                                 block(2, "**答案**：B\n\n没有声明的解析。")))
        r = m.scan(self.root)
        self.assertEqual(r["answerBlocks"], 2)
        self.assertEqual(r["undeclared"], 1)
        self.assertEqual(r["declared"], 1)

    def test_check_gate_fails_only_on_undeclared(self):
        self.write("variant_only.md", paper(
            block(1, "**答案**：A\n\n**来源参考解析**（不是官方公布答案）\n\n解析。")))
        r = m.scan(self.root)
        self.assertEqual(r["undeclared"], 0)
        self.assertEqual(r["formatVariants"], 1)

    def test_scan_is_deterministic(self):
        self.write("a.md", paper(block(1, "**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n解析。")))
        self.assertEqual(m.scan(self.root)["answerBlocks"], m.scan(self.root)["answerBlocks"])

    def test_paths_limit_restricts_the_scan(self):
        self.write("a.md", paper(block(1, "**答案**：A\n\n无声明。")))
        (self.root / "国考").mkdir()
        (self.root / "国考" / "b.md").write_text(paper(block(1, "**答案**：A\n\n无声明。")), encoding="utf-8")
        self.assertEqual(m.scan(self.root)["answerBlocks"], 2)
        self.assertEqual(m.scan(self.root, ["省考"])["answerBlocks"], 1)


class RealLibraryTests(unittest.TestCase):
    """The four papers this audit covers, checked against the real files."""

    ROOT = Path(__file__).resolve().parents[1]

    def test_the_twelve_ai_backfills_are_classified_ai_derived(self):
        text = (self.ROOT / "省考/江苏/2025/行测-C类.md").read_text(encoding="utf-8")
        ai = {n for n, b, _s, _e in m.iter_answer_blocks(text)
              if m.classify_block(b)["authority_class"] == "ai_derived"}
        self.assertEqual(ai, {27, 29, 35, 36, 37, 42, 75, 77, 78, 80, 81, 85})

    def test_the_audited_papers_have_no_undeclared_answer_blocks(self):
        for rel in ("省考/江苏/2025/行测-C类.md", "省考/江苏/2024/行测-A类.md",
                    "省考/广东/2020/行测-县级卷.md", "省考/浙江/2026/行测-C类.md"):
            with self.subTest(paper=rel):
                text = (self.ROOT / rel).read_text(encoding="utf-8")
                undeclared = [n for n, b, _s, _e in m.iter_answer_blocks(text)
                              if not m.classify_block(b)["declared"]]
                self.assertEqual(undeclared, [])

    def test_every_answer_block_in_the_audited_papers_carries_an_answer_letter(self):
        for rel in ("省考/江苏/2025/行测-C类.md", "省考/江苏/2024/行测-A类.md",
                    "省考/广东/2020/行测-县级卷.md", "省考/浙江/2026/行测-C类.md"):
            with self.subTest(paper=rel):
                text = (self.ROOT / rel).read_text(encoding="utf-8")
                blocks = list(m.iter_answer_blocks(text))
                self.assertTrue(blocks)
                for n, b, _s, _e in blocks:
                    self.assertRegex(b, r"\*\*答案\*\*\s*[：:]\s*\**\s*[A-D]\b",
                                     f"{rel} 第{n}题 has no answer letter")


class JsonOutputTests(unittest.TestCase):
    def test_report_is_json_serialisable(self):
        r = m.scan(Path(__file__).resolve().parents[1], ["省考/江苏/2025"])
        s = json.dumps(r, ensure_ascii=False)
        self.assertIn("undeclared", json.loads(s))


if __name__ == "__main__":
    unittest.main()


class FileLevelProvenanceTests(unittest.TestCase):
    """Provenance declared in frontmatter, which an earlier revision of this checker ignored."""

    HASH = "a" * 64

    def fp(self, fm, receipts=None):
        return m.file_provenance(fm, set(receipts or ()))

    def test_explicit_answer_source_field_is_recognised(self):
        # Real text: 省考/内蒙古/2020/行测-统考.md
        p = self.fp({"答案来源": "同上《参考答案及解析》PDF"})
        self.assertEqual(p["state"], "explicit_answer_source")
        self.assertFalse(p["declared_absent"])

    def test_answer_source_declaring_absence_is_not_a_declaration(self):
        # Real text: 省考/黑龙江/2019/行测-边境县.md. Counting the mere presence of the
        # key as a declaration would invert its meaning.
        p = self.fp({"答案来源": "缺（两源均无此卷答案）"})
        self.assertEqual(p["state"], "declared_absent")
        self.assertTrue(p["declared_absent"])

    def test_detail_keys_naming_answers_count_as_declared(self):
        for key in ("来源明细", "来源整卷", "来源补录凭据", "第六轮原始资料补答案凭据",
                    "补全来源", "补全证据", "完整题本固定来源"):
            with self.subTest(key=key):
                p = self.fp({key: "某来源 PDF"})
                self.assertEqual(p["state"], "detail_names_answers")

    def test_source_list_alone_is_the_weakest_declaration(self):
        p = self.fp({"来源": '["xingcezhenti"]'})
        self.assertEqual(p["state"], "source_list_only")

    def test_no_fields_means_none(self):
        self.assertEqual(self.fp({})["state"], "none")

    def test_backed_requires_the_identifier_to_be_retained(self):
        fm = {"答案来源": f"某 PDF，SHA-256：{self.HASH}"}
        self.assertFalse(self.fp(fm)["backed"])
        self.assertTrue(self.fp(fm, {self.HASH})["backed"])

    def test_quote_stripped_values_still_yield_hashes(self):
        fm = {"来源明细": f'题面 PDF(sha256={self.HASH})'}
        self.assertEqual(self.fp(fm)["cited_hashes"], [self.HASH])


class OfficialDisclaimerTests(unittest.TestCase):
    """Negative cases: an official *disclaimer* must never read as an official claim.

    Misreading `非官方标准答案` as an official key is the inversion this whole tool
    exists to prevent, so every phrasing the library uses gets a case.
    """

    def test_block_level_negations(self):
        cases = [
            "**来源参考解析（非官方标准答案）**\n解析。",
            "**来源参考答案（非官方）**\n解析。",
            "> 来源说明：原记录卷型标记为“统考”，并非本卷的独立官方答案。",
            "> 来源说明：见恢复凭据，不将其改称原创或官方答案。",
            "> 来源说明：不将C类答案移用，也不称为官方答案。",
            "资料性质为机构/个人整理参考解析，不是官方公布答案。",
            "作者／整理性质为AI辅助修订，不是原机构作者原稿，不是官方答案。",
        ]
        for c in cases:
            with self.subTest(case=c[:26]):
                self.assertFalse(m.claims_official(c))

    def test_frontmatter_negations(self):
        cases = [
            "非官方逐字验真",
            "第三方参考答案不等于官方标准答案",
            "不是官方公布答案",
        ]
        for c in cases:
            with self.subTest(case=c):
                self.assertFalse(m.claims_official_broad(c))

    def test_real_official_claim_is_detected(self):
        # Positive control, so the negations above are not passing trivially.
        self.assertTrue(m.claims_official("本题答案依据官方公布答案。"))
        self.assertTrue(m.claims_official_broad("答案 同批官方《行政职业能力测验解析》PDF"))

    def test_ordinary_question_text_containing_guanfang_is_not_a_claim(self):
        # 省考/黑龙江/2019/行测-边境县.md has `官方` inside a question stem about
        # litigation. The block-level detector must stay strict so this does not fire.
        body = "中国民间一直存在以争讼为耻的传统思想，且官方也存在无讼和恶讼思维。"
        self.assertFalse(m.claims_official(body))

    def test_institution_labelled_official_is_flagged(self):
        fm = {"来源": '["huatu-zhenti", "huatu-zhenti-ans"]',
              "来源明细": "答案 同批官方《行政职业能力测验解析》PDF"}
        p = m.file_provenance(fm, set())
        self.assertTrue(p["claims_official"])
        self.assertTrue(p["sources_institutional_only"])
        self.assertTrue(p["official_claim_with_only_institutional_sources"])

    def test_genuine_official_source_list_is_not_flagged(self):
        fm = {"来源": '["某省人事考试院"]', "来源明细": "官方公布答案"}
        p = m.file_provenance(fm, set())
        self.assertFalse(p["official_claim_with_only_institutional_sources"])


class CoverageStateTests(unittest.TestCase):
    """The three-state coverage model, including the stale-frontmatter contradiction."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "省考").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        p = self.root / "省考" / "a.md"
        p.write_text(text, encoding="utf-8")
        return p

    def test_declared_block_without_identifier_is_source_present(self):
        self.write(paper(block(1, "**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n解析若干字。")))
        r = m.scan(self.root, receipt_index=set())
        self.assertEqual(r["coverage"]["source-present"], 1)
        self.assertEqual(r["coverage"]["verified"], 0)

    def test_declared_block_with_backed_identifier_is_verified(self):
        h = "b" * 64
        self.write(paper(block(1, f"**答案**：A\n\n**参考解析（用户提供资料）**\n\n"
                                f"**来源**：用户提供 PDF，SHA-256：{h}\n")))
        r = m.scan(self.root, receipt_index={h})
        self.assertEqual(r["coverage"]["verified"], 1)

    def test_file_level_declaration_covers_its_blocks(self):
        text = paper(block(1, "**答案**：A\n\n解析没有来源行。"))
        text = text.replace('卷型: "A类"', '卷型: "A类"\n来源明细: "答案 PDF(sha256=' + "c" * 64 + ')"')
        self.write(text)
        r = m.scan(self.root, receipt_index=set())
        self.assertEqual(r["coverage"]["unsupported"], 0)
        self.assertGreaterEqual(r["coverage"]["source-present"], 1)

    def test_stale_declared_absent_frontmatter_is_flagged_not_fatal(self):
        text = paper(block(1, "**答案**：A\n\n**参考解析（用户提供资料）**\n\n有来源行。"))
        text = text.replace('卷型: "A类"', '卷型: "A类"\n答案来源: "缺（两源均无此卷答案）"')
        self.write(text)
        r = m.scan(self.root, receipt_index=set())
        self.assertEqual(r["coverage"]["unsupported"], 0)
        self.assertEqual(r["staleFileProvenanceBlocks"], 1)

    def test_declared_absent_without_block_declaration_is_unsupported(self):
        text = paper(block(1, "**答案**：A\n\n解析没有来源行。"))
        text = text.replace('卷型: "A类"', '卷型: "A类"\n答案来源: "缺（两源均无此卷答案）"')
        self.write(text)
        r = m.scan(self.root, receipt_index=set())
        self.assertEqual(r["coverage"]["unsupported"], 1)

    def test_receipt_index_ignores_this_tools_own_report(self):
        reports = self.root / "reports"
        reports.mkdir()
        h = "d" * 64
        (reports / "ANSWER-PROVENANCE-MARKERS-20261017.json").write_text(h, encoding="utf-8")
        (reports / "OTHER-RECEIPT.json").write_text(h, encoding="utf-8")
        idx = m.build_receipt_index(self.root)
        self.assertIn(h, idx)  # from OTHER-RECEIPT
        (reports / "OTHER-RECEIPT.json").unlink()
        self.assertNotIn(h, m.build_receipt_index(self.root))  # own output excluded
