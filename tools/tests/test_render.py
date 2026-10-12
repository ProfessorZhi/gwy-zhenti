# -*- coding: utf-8 -*-
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import render        # noqa: E402
from gwyzhenti.model import PaperKey    # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "xingcezhenti")
# 源里的写法 → 导出后应有的写法（测试与 image_map 共用同一常量，避免两处各写一遍写岔）
SRC_IMG = "../90-图片/题目图/154428b1a538147.png"
IMG_OUT = "../../../图片/省考-四川-2016-行测-统考/题目图/154428b1a538147.png"


def load(*p):
    with open(os.path.join(FIX, *p), encoding="utf-8") as fh:
        return fh.read()


class TestRender(unittest.TestCase):
    def setUp(self):
        self.key = PaperKey("省考", "四川", "2016", "行测", "统考")
        self.parts = [
            load("02-常识判断", "2016年423联考《行测》题（四川卷）.md"),
            load("06-资料分析", "2016年423联考《行测》题（四川卷）.md"),
        ]
        self.out = render.render_paper(
            self.parts, self.key, nature="正式真题", form="联考",
            sources=["xingcezhenti"], modules=["常识判断", "资料分析"],
            image_map={SRC_IMG: IMG_OUT},
        )

    def test_no_checkmark_anywhere(self):
        self.assertNotIn("✅", self.out.body)

    def test_answers_moved_to_own_section(self):
        self.assertIn("## 答案与解析", self.out.body)
        self.assertIn("<details>", self.out.body)
        # 答案区必须位于最后一道题之后
        self.assertLess(self.out.body.index("## 答案与解析"),
                        self.out.body.rindex("<details>"))

    def test_question_count_across_modules(self):
        self.assertEqual(self.out.n_questions, 3)
        self.assertEqual(self.out.numbering, "模块拼接序号（未核对原卷）")

    def test_numbering_is_rebuilt_contiguously(self):
        nums = [int(m) for m in re.findall(r"^#{2,4}\s*第\s*(\d+)\s*题", self.out.body, re.M)]
        self.assertEqual(nums, [1, 2, 3])

    def test_images_rewritten_and_collected(self):
        self.assertIn(IMG_OUT, self.out.body)
        self.assertNotIn("../90-图片/", self.out.body)
        self.assertEqual(self.out.images_used, [IMG_OUT])

    def test_frontmatter_contract(self):
        head = self.out.body.split("---")[1]
        for k in ("考试", "地区", "年份", "科目", "卷型", "真题性质", "来源", "校验状态", "题号口径"):
            self.assertIn(k, head)

    def test_g5_diff_is_empty_against_source(self):
        # 导出 vs 源：除声明过的结构性差异外，逐行多重集必须相等（零内容增删）
        removed, added = render.diff_report(self.out.body, self.parts)
        self.assertEqual(removed, [], "源里有、导出里没有的行")
        self.assertEqual(added, [], "导出里多出来、源里没有的行")

    def test_g5_diff_catches_a_perturbation(self):
        # 把正文里**第一处 A 选项行**的数字改掉 ⇒ 必须被判为「源里有、导出没有」
        bad = re.sub(r"(?m)^(- \*\*A\*\*\. )(\d+)", r"\g<1>999999", self.out.body, count=1)
        self.assertNotEqual(bad, self.out.body, "fixture 里没有可扰动的 A 选项行")
        removed, _ = render.diff_report(bad, self.parts)
        self.assertTrue(removed, "扰动后 diff 必须非空")
