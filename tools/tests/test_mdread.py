# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import mdread      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "xingcezhenti")
ZL = os.path.join(FIX, "06-资料分析", "2016年423联考《行测》题（四川卷）.md")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestMdRead(unittest.TestCase):
    def setUp(self):
        self.zl = load(ZL)

    def test_frontmatter(self):
        fm = mdread.read_frontmatter(self.zl)
        self.assertEqual(fm["地区"], "四川")
        self.assertEqual(fm["年份"], "2016")
        self.assertEqual(fm["模块"], "资料分析")
        self.assertEqual(fm["题数"], "2")

    def test_count_questions(self):
        self.assertEqual(mdread.count_questions(self.zl), 2)

    def test_images_typed(self):
        imgs = mdread.iter_images(self.zl)
        self.assertEqual(imgs, [("题目图", "../90-图片/题目图/154428b1a538147.png")])

    def test_formula_image_typed(self):
        jiangsu = load(os.path.join(FIX, "06-资料分析", "2020年江苏省公务员录用考试《行测》题（A类）.md"))
        self.assertEqual(mdread.iter_images(jiangsu),
                         [("公式图", "../90-图片/公式图/formula-717ebaedf48c8509.png")])

    def test_split_blocks_and_preamble_keeps_material(self):
        pre, blocks = mdread.split_question_blocks(self.zl)
        self.assertEqual(len(blocks), 2)
        self.assertTrue(any(ln.startswith("## 材料 1") for ln in pre))
        self.assertTrue(blocks[0][0].startswith("### 第 1 题"))

    def test_split_answer(self):
        _, blocks = mdread.split_question_blocks(self.zl)
        stem, ans, tail = mdread.split_answer(blocks[0])
        self.assertTrue(any("340.2" in ln for ln in stem))
        self.assertTrue(any(ln.startswith("**答案**：") for ln in ans))
        self.assertTrue(any("官方解析" in ln for ln in ans))
        self.assertEqual(tail, [])

    def test_split_answer_tail_returns_next_material(self):
        # 第二题块之后（本 fixture 里为文件末尾）不应有内容
        _, blocks = mdread.split_question_blocks(self.zl)
        _, ans2, tail2 = mdread.split_answer(blocks[1])
        self.assertTrue(any("公路最大" in ln for ln in ans2))
        self.assertEqual(tail2, [])

    def test_tail_drops_trailing_blanks_but_keeps_material(self):
        # 尾行是 Task 8 把 `## 材料 N` 及其图片**送回正文**的通道 —— 只丢尾随空行，
        # 行内空行与内容行必须原样保留（`split("\n")` 会为文件末尾换行多产一个 ""）
        block = ["### 第 1 题　<sub>qid 1 · 综合</sub>",
                 "- **A**. 340.2",
                 "**答案**：A",
                 "",
                 "---",
                 "",
                 "## 材料 2",
                 "",
                 '<img width="700px" height="173px" src="../90-图片/题目图/154428b1a538147.png" />',
                 "",
                 ""]
        stem, ans, tail = mdread.split_answer(block)
        self.assertEqual(stem[:2], ["### 第 1 题　<sub>qid 1 · 综合</sub>", "- **A**. 340.2"])
        self.assertEqual(ans, ["**答案**：A", "", "---"])
        self.assertEqual(tail, ["",
                                "## 材料 2",
                                "",
                                '<img width="700px" height="173px" src="../90-图片/题目图/154428b1a538147.png" />'])

    def test_strip_leak_removes_checkmark_only(self):
        lines = ["- **B**. 353.9　✅", "- **A**. 340.2", "**答案**：B"]
        self.assertEqual(mdread.strip_leak(lines),
                         ["- **B**. 353.9", "- **A**. 340.2", "**答案**：B"])

    def test_correct_option(self):
        _, blocks = mdread.split_question_blocks(self.zl)
        self.assertEqual(mdread.correct_option(blocks[0]), "B")
        self.assertEqual(mdread.correct_option(blocks[1]), "D")

    def test_correct_option_none_when_no_answer(self):
        self.assertIsNone(mdread.correct_option(["### 第 1 题", "无答案"]))
