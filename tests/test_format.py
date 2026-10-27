"""Synthetic negative/positive tests for the layout checker.

Run: python3 -I -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gwy_format.checker import SEV_ERROR, SEV_REVIEW, SEV_WARN, check_paper  # noqa: E402

IMG = "assets-fenbi-1/" + "a" * 64 + ".png"
TREE = {f"省考/测试/2020/{IMG}"}

CLEAN = f"""---
考试: "省考"
地区: "测试"
年份: 2020
科目: "行测"
卷型: "统考"
真题性质: "测试卷"
来源: "https://spa.fenbi.com/ti/exam/exercise/1_1_x"
源试卷ID: "1"
---

# 2020年测试《行测》题

<!-- gwy:overview:start -->
> **测试 · 2020 · 行测 · 统考** ｜ 1 题 · 图片 1 处 · 答案随题折叠

导航：[题目](#题目)
<!-- gwy:overview:end -->

> 候选采集稿。

## 题目

### 第 1 题

题干一，下列哪项正确？

A. 甲

B. 乙

C. 丙

D. 丁

![]({IMG})

<details><summary>第 1 题 · 答案与解析</summary>

**参考答案（粉笔题库参考内容）**

B

**解析**

略。

</details>
"""


def run(text: str, tree: set[str] | None = None):
    return check_paper("省考/测试/2020/行测-统考.md", text.encode("utf-8"), TREE if tree is None else tree)


def codes(rep) -> set[str]:
    return {f.code for f in rep.findings}


def sev(rep, level) -> list:
    return [f for f in rep.findings if f.severity == level]


class CleanBaseline(unittest.TestCase):
    def test_clean_paper_has_no_errors_or_warnings(self):
        rep = run(CLEAN)
        self.assertEqual(sev(rep, SEV_ERROR), [], [f.to_dict() for f in sev(rep, SEV_ERROR)])
        self.assertEqual(sev(rep, SEV_WARN), [], [f.to_dict() for f in sev(rep, SEV_WARN)])
        self.assertEqual(rep.template, "fenbi")


class FrontmatterRules(unittest.TestCase):
    def test_missing_frontmatter(self):
        rep = run(CLEAN.split("---", 2)[2])
        self.assertIn("FM001", codes(rep))

    def test_unclosed_frontmatter(self):
        rep = run(CLEAN.replace("校验状态", "校验状态").replace("\n---\n\n# 2020", "\n\n# 2020", 1))
        self.assertIn("FM002", codes(rep))

    def test_missing_subject(self):
        rep = run(CLEAN.replace('科目: "行测"\n', ""))
        self.assertIn("FM004", codes(rep))

    def test_invalid_subject(self):
        rep = run(CLEAN.replace('科目: "行测"', '科目: "行策"'))
        self.assertIn("FM005", codes(rep))

    def test_fenbi_source_without_id(self):
        rep = run(CLEAN.replace('源试卷ID: "1"\n', ""))
        self.assertIn("FM009", codes(rep))


class HeadingRules(unittest.TestCase):
    def test_no_h1(self):
        rep = run(CLEAN.replace("# 2020年测试《行测》题\n", ""))
        self.assertIn("HD001", codes(rep))

    def test_two_h1(self):
        rep = run(CLEAN.replace("## 题目", "# 第二个一级标题\n\n## 题目"))
        self.assertIn("HD002", codes(rep))

    def test_level_jump(self):
        rep = run(CLEAN.replace("## 题目\n\n### 第 1 题", "## 题目\n\n#### 第 1 题"))
        self.assertIn("HD003", codes(rep))

    def test_duplicate_question_number(self):
        rep = run(CLEAN.replace("### 第 1 题", "### 第 1 题", 1) + "\n### 第 1 题\n\n重复\n")
        self.assertIn("HD004", codes(rep))

    def test_question_gap(self):
        extra = CLEAN.replace("### 第 1 题", "### 第 3 题").replace("第 1 题 · 答案与解析", "第 3 题 · 答案与解析")
        rep = run(extra)
        self.assertIn("HD005", codes(rep))

    def test_heading_trailing_colon(self):
        rep = run(CLEAN.replace("## 题目", "## 题目："))
        self.assertIn("HD010", codes(rep))


class DetailsRules(unittest.TestCase):
    def test_unbalanced_details(self):
        rep = run(CLEAN.replace("</details>", ""))
        self.assertIn("DT002", codes(rep))

    def test_summary_number_mismatch(self):
        rep = run(CLEAN.replace("<summary>第 1 题", "<summary>第 2 题"))
        self.assertIn("DT004", codes(rep))

    def test_duplicate_details(self):
        rep = run(CLEAN + "\n<details><summary>第 1 题 · 答案与解析</summary>\n\nB\n\n</details>\n")
        self.assertIn("DT005", codes(rep))

    def test_missing_details_for_question(self):
        rep = run(CLEAN.replace("<details><summary>第 1 题 · 答案与解析</summary>", "").replace("</details>", ""))
        self.assertIn("DT006", codes(rep))

    def test_empty_details(self):
        rep = run(CLEAN.replace("**参考答案（粉笔题库参考内容）**\n\nB\n\n**解析**\n\n略。\n", ""))
        self.assertIn("DT007", codes(rep))

    def test_duplicate_analysis_header(self):
        rep = run(CLEAN.replace("**解析**\n\n略。", "**解析**\n\n**解析**\n\n略。"))
        self.assertIn("DT008", codes(rep))


class OptionRules(unittest.TestCase):
    def test_two_options_one_line(self):
        rep = run(CLEAN.replace("A. 甲\n\nB. 乙", "A. 甲 B. 乙"))
        self.assertIn("OP001", codes(rep))

    def test_option_label_skip(self):
        rep = run(CLEAN.replace("C. 丙", "E. 丙"))
        self.assertIn("OP002", codes(rep))

    def test_duplicate_option_label(self):
        rep = run(CLEAN.replace("B. 乙", "A. 乙"))
        self.assertIn("OP003", codes(rep))

    def test_indented_options(self):
        rep = run(CLEAN.replace("A. 甲", "  A. 甲"))
        self.assertIn("OP004", codes(rep))

    def test_single_option(self):
        rep = run(CLEAN.replace("B. 乙\n\nC. 丙\n\nD. 丁\n", ""))
        self.assertIn("OP006", codes(rep))

    def test_stem_starting_with_A_dundun_is_not_an_option(self):
        rep = run(CLEAN.replace("题干一，下列哪项正确？", "A、B两地各有一批货物，问共有多少箱？"))
        self.assertNotIn("OP002", codes(rep))
        self.assertNotIn("OP003", codes(rep))

    def test_optionless_question_in_option_paper(self):
        extra = CLEAN.replace(
            "A. 甲\n\nB. 乙\n\nC. 丙\n\nD. 丁\n\n![]({})\n\n".format(IMG),
            "",
        ).replace("![]({})\n\n".format(IMG), "")
        extra = extra.replace("题干一，下列哪项正确？", "关于地球的说法，下列哪项正确？")
        rep = run(extra)
        self.assertIn("OP007", codes(rep))

    def test_options_inside_a_table_are_recognised(self):
        text = CLEAN.replace(
            "A. 甲\n\nB. 乙\n\nC. 丙\n\nD. 丁\n\n",
            "以下正确的一行是（　）。\n\n| 项目 | 2005 |\n| --- | ---: |\n| A. 甲 | 1 |\n| B. 乙 | 2 |\n| C. 丙 | 3 |\n| D. 丁 | 4 |\n\n",
        ).replace(f"![]({IMG})\n\n", "")
        rep = run(text)
        self.assertNotIn("OP007", codes(rep))

    def test_statement_question_is_not_optionless_error(self):
        extra = CLEAN.replace("A. 甲\n\nB. 乙\n\nC. 丙\n\nD. 丁\n\n", "").replace(f"![]({IMG})\n\n", "")
        extra = extra.replace("题干一，下列哪项正确？", "运动、变化和发展是同等程度的概念，它们彼此无实质区别。")
        rep = run(extra)
        self.assertNotIn("OP007", codes(rep))


class MaterialRules(unittest.TestCase):
    SHENLUN = CLEAN.replace('科目: "行测"', '科目: "申论"').replace("· 行测 ·", "· 申论 ·")

    def test_duplicate_material_heading(self):
        text = self.SHENLUN.replace("## 题目", "## 给定材料\n\n### 材料 1\n\n正文一\n\n### 材料 1\n\n正文二\n\n## 题目")
        rep = run(text)
        self.assertIn("MT001", codes(rep))

    def test_matref_to_missing_material(self):
        text = self.SHENLUN.replace("## 题目", "## 给定材料\n\n### 材料 1\n\n正文一\n\n## 题目").replace(
            "题干一，下列哪项正确？", "根据给定资料1，说明理由。\n\n关联材料：材料 1、材料 2"
        )
        rep = run(text)
        self.assertIn("MT003", codes(rep))

    def test_empty_material(self):
        text = self.SHENLUN.replace("## 题目", "## 给定材料\n\n### 材料 1\n\n### 材料 2\n\n正文\n\n## 题目")
        rep = run(text)
        self.assertIn("MT008", codes(rep))

    def test_matref_without_blank_line(self):
        text = self.SHENLUN.replace("## 题目", "## 给定材料\n\n### 材料 1\n\n正文一\n\n## 题目")
        text = text.replace("题干一，下列哪项正确？", "根据给定资料1作答。\n关联材料：材料 1")
        rep = run(text)
        self.assertIn("MT006", codes(rep))


class ListAndTableRules(unittest.TestCase):
    def test_tab_indentation(self):
        rep = run(CLEAN.replace("略。", "\t缩进。"))
        self.assertIn("LS001", codes(rep))

    def test_table_separator_mismatch(self):
        text = CLEAN.replace("**解析**\n\n略。", "**解析**\n\n| 甲 | 乙 |\n| --- |\n| 1 | 2 |\n")
        rep = run(text)
        self.assertIn("TB002", codes(rep))

    def test_table_row_mismatch(self):
        text = CLEAN.replace("**解析**\n\n略。", "**解析**\n\n| 甲 | 乙 |\n| --- | --- |\n| 1 |\n")
        rep = run(text)
        self.assertIn("TB003", codes(rep))

    def test_table_without_separator(self):
        text = CLEAN.replace("**解析**\n\n略。", "**解析**\n\n| 甲 | 乙 |\n| 1 | 2 |\n")
        rep = run(text)
        self.assertIn("TB001", codes(rep))

    def test_pipe_math_is_not_a_table(self):
        text = CLEAN.replace("**解析**\n\n略。", "**解析**\n\n|甲-乙|=|丙-丁|\n")
        rep = run(text)
        self.assertNotIn("TB001", codes(rep))


class EscapingRules(unittest.TestCase):
    def test_unclosed_bold(self):
        rep = run(CLEAN.replace("**解析**", "<b>解析"))
        self.assertIn("ES001", codes(rep))

    def test_less_than_b_is_not_a_tag(self):
        rep = run(CLEAN.replace("略。", "由 a（10.7%）<b（12.2%）可判断为下降。"))
        self.assertNotIn("ES001", codes(rep))
        self.assertIn("ES002", codes(rep))

    def test_broken_entity(self):
        rep = run(CLEAN.replace("略。", "A&amp B"))
        self.assertIn("ES003", codes(rep))

    def test_odd_code_fence(self):
        rep = run(CLEAN.replace("略。", "```\ncode\n"))
        self.assertIn("ES004", codes(rep))


class LineRules(unittest.TestCase):
    def test_overlong_line(self):
        rep = run(CLEAN.replace("略。", "字" * 2100))
        self.assertIn("LX001", codes(rep))

    def test_trailing_space(self):
        rep = run(CLEAN.replace("略。", "略。   "))
        self.assertIn("LX002", codes(rep))

    def test_three_blank_lines(self):
        rep = run(CLEAN.replace("\n\n## 题目", "\n\n\n\n## 题目"))
        self.assertIn("LX003", codes(rep))

    def test_missing_final_newline(self):
        rep = run(CLEAN.rstrip("\n"))
        self.assertIn("LX007", codes(rep))

    def test_crlf(self):
        rep = run(CLEAN.replace("\n", "\r\n"))
        self.assertIn("LX008", codes(rep))


class ImageRules(unittest.TestCase):
    def test_missing_image_file(self):
        rep = run(CLEAN.replace(IMG, "assets-fenbi-1/" + "b" * 64 + ".png"))
        self.assertIn("IM001", codes(rep))

    def test_remote_image(self):
        rep = run(CLEAN.replace(IMG, "https://example.com/a.png"))
        self.assertIn("IM002", codes(rep))

    def test_image_path_with_space(self):
        rep = run(CLEAN.replace(f"![]({IMG})", "![](assets-fenbi-1/a b.png)"))
        self.assertIn("IM003", codes(rep))

    def test_duplicate_image_reference(self):
        rep = run(CLEAN.replace("<details>", f"![]({IMG})\n\n<details>"))
        self.assertIn("IM004", codes(rep))

    def test_html_img_tag_is_checked(self):
        text = CLEAN.replace(f"![]({IMG})", f'<img src="{IMG}" />')
        rep = run(text)
        self.assertEqual(rep.images, 1)
        self.assertNotIn("IM001", codes(rep))
        bad = run(text.replace(IMG, "图片/缺失/a.png"))
        self.assertIn("IM001", codes(bad))


class NavigationRules(unittest.TestCase):
    def test_missing_overview(self):
        text = CLEAN.split("<!-- gwy:overview:start -->")[0] + CLEAN.split("<!-- gwy:overview:end -->")[1]
        rep = run(text)
        self.assertIn("NV001", codes(rep))

    def test_bad_anchor(self):
        rep = run(CLEAN.replace("[题目](#题目)", "[题目](#不存在)"))
        self.assertIn("NV003", codes(rep))

    def test_question_count_mismatch(self):
        rep = run(CLEAN.replace("｜ 1 题", "｜ 9 题"))
        self.assertIn("NV004", codes(rep))

    def test_image_count_mismatch(self):
        rep = run(CLEAN.replace("图片 1 处", "图片 7 处"))
        self.assertIn("NV005", codes(rep))


class PlaceholderRules(unittest.TestCase):
    def test_placeholder_is_info_not_defect(self):
        text = CLEAN.replace("题干一，下列哪项正确？", "粉笔暂未收录本题（来源缺题，题位保留）").replace(
            "A. 甲\n\nB. 乙\n\nC. 丙\n\nD. 丁\n\n", ""
        )
        rep = run(text)
        self.assertIn("PH001", codes(rep))
        self.assertNotIn("OP007", codes(rep))
        self.assertEqual(sev(rep, SEV_ERROR), [])
        self.assertTrue(all(f.severity != SEV_WARN for f in rep.findings if f.code == "PH001"))


class LayoutVariants(unittest.TestCase):
    def test_legacy_shenlun_without_details_is_not_an_error(self):
        text = (
            "---\n考试: \"省考\"\n地区: \"测试\"\n年份: 2020\n科目: \"申论\"\n卷型: \"统考\"\n真题性质: \"测试\"\n"
            "来源: \"shenlunhome\"\n---\n\n# 测试申论\n\n<!-- gwy:overview:start -->\n> **测试 · 2020 · 申论 · 统考** ｜ 1 题 · 图片 0 处\n\n"
            "导航：[题目](#题目)\n<!-- gwy:overview:end -->\n\n## 参考作答与范文导读\n\n说明。\n\n## 给定材料\n\n### 材料 1\n\n材料正文。\n\n"
            "## 题目\n\n### 第 1 题\n\n根据给定资料1作答。\n\n关联材料：材料 1\n"
        )
        rep = run(text)
        self.assertEqual(sev(rep, SEV_ERROR), [], [f.to_dict() for f in sev(rep, SEV_ERROR)])
        self.assertTrue(rep.legacy_answers)

    def test_mixed_question_levels_is_review(self):
        text = CLEAN.replace("## 题目", "## 题目\n\n## 材料 1\n\n材料正文\n\n## 第 2 题\n\n第二题\n\n<details><summary>第 2 题 · 答案与解析</summary>\n\nC\n\n</details>")
        rep = run(text)
        self.assertIn("HD008", codes(rep))
        self.assertEqual(rep.template, "mixed-level")


if __name__ == "__main__":
    unittest.main()
