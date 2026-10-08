# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti.model import PaperKey        # noqa: E402
from gwyzhenti.slug import paper_slug       # noqa: E402


class TestPaperSlug(unittest.TestCase):
    def test_shengkao_three_levels(self):
        k = PaperKey("省考", "四川", "2016", "行测", "A类")
        self.assertEqual(paper_slug(k), "省考-四川-2016-行测-A类")

    def test_guokao_has_no_region_segment(self):
        k = PaperKey("国考", "", "2026", "行测", "副省级")
        self.assertEqual(paper_slug(k), "国考-2026-行测-副省级")

    def test_variant_appended(self):
        k = PaperKey("省考", "四川", "2016", "行测", "统考")
        self.assertEqual(paper_slug(k, "网友回忆版"), "省考-四川-2016-行测-统考-网友回忆版")

    def test_deterministic(self):
        k = PaperKey("省考", "四川", "2016", "行测", "A类")
        self.assertEqual(paper_slug(k), paper_slug(k))

    def test_key_is_hashable_and_orderable(self):
        a = PaperKey("省考", "四川", "2016", "行测", "A类")
        b = PaperKey("省考", "四川", "2017", "行测", "A类")
        self.assertLess(a, b)
        self.assertEqual(len({a, b}), 2)
