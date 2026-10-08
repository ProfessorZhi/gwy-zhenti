# -*- coding: utf-8 -*-
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import catalog, export        # noqa: E402
from gwyzhenti.model import PaperKey         # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class TestExportPaths(unittest.TestCase):
    def test_shengkao_three_levels(self):
        p, img = export.repo_paths(PaperKey("省考", "四川", "2016", "行测", "统考"), "省考-四川-2016-行测-统考")
        self.assertEqual(p, "省考/四川/2016/行测-统考.md")
        self.assertEqual(img, "图片/省考-四川-2016-行测-统考")

    def test_guokao_two_levels(self):
        p, img = export.repo_paths(PaperKey("国考", "", "2026", "行测", "副省级"), "国考-2026-行测-副省级")
        self.assertEqual(p, "国考/2026/行测-副省级.md")
        self.assertEqual(img, "图片/国考-2026-行测-副省级")


class TestExportRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwyexp-")
        self.cat = os.path.join(self.tmp, "catalog")
        self.repo = os.path.join(self.tmp, "repo")
        catalog.build({
            "xingcezhenti": os.path.join(FIX, "xingcezhenti"),
            "linfukai186": os.path.join(FIX, "linfukai186"),
        }, self.cat)
        self.rep = export.run(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_papers_written(self):
        self.assertEqual(self.rep.papers, 2)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "省考/四川/2016/行测-统考.md")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, "省考/江苏/2020/行测-A类.md")))

    def test_images_copied_to_paper_dir(self):
        d = os.path.join(self.repo, "图片/省考-四川-2016-行测-统考/题目图")
        self.assertEqual(os.listdir(d), ["154428b1a538147.png"])

    def test_md_refs_image_actually_exists(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("../../../图片/省考-四川-2016-行测-统考/题目图/154428b1a538147.png", text)

    def test_manifest_written_with_sha(self):
        with open(self.rep.manifest_path, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]["sha256"]), 64)

    def test_rerun_is_idempotent(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        before = open(md, "rb").read()
        export.run(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertEqual(open(md, "rb").read(), before)


class TestFilenameUsesXingceSourceTitle(unittest.TestCase):
    """裁定 R-T8-1：文件名**必须**取 `titles["xingcezhenti"][0]`，**不得**取 `row["title"]`。

    真库聚合按 `sorted(uproots.items())` 走，`linfukai186` 排在 `xingcezhenti` 之前 ⇒
    两源同键的卷（实测 286 个）其 `row["title"]` 是 **linfukai186** 的卷名。拿它去
    xingcezhenti 根下拼路径会**全数落空**（286/286），整卷被错判成「上游文件缺失」而静默丢弃。
    测试造一条 `title ≠ titles["xingcezhenti"][0]` 的 row：若实现拿 `row["title"]` 拼路径，
    `_parts_for` 会 0 命中 ⇒ `modules` 为空 ⇒ 本测试**变红**。
    """

    def test_parts_use_xingcezhenti_name_not_row_title(self):
        row = {
            # title = 首个被聚合进来的源（linfukai186）的卷名，与 xingcezhenti 的**不同**
            "title": "2016·423四川公务员考试《行测》题",
            "titles": {
                "linfukai186": ["2016·423四川公务员考试《行测》题"],
                "xingcezhenti": ["2016年423联考《行测》题（四川卷）"],
            },
            "modules": {"常识判断": 1},
            "sources": ["linfukai186", "xingcezhenti"],
            "slug": "省考-四川-2016-行测-统考",
        }
        # 前提：两串确实不同（真库两源同键的形态）
        self.assertNotEqual(row["title"], row["titles"]["xingcezhenti"][0])
        # 取的是 xingcezhenti 源自己的卷名
        self.assertEqual(export._xingce_titles(row), ["2016年423联考《行测》题（四川卷）"])
        # 按该名拼路径能命中；按 row["title"] 拼会 0 命中（见 _parts_for docstring）
        parts, modules = export._parts_for(row, os.path.join(FIX, "xingcezhenti"))
        self.assertEqual(modules, ["常识判断"])
        self.assertEqual(len(parts), 1)
        self.assertIn("下列说法正确的是", parts[0])
