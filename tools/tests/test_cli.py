# -*- coding: utf-8 -*-
"""CLI 接线回归：`cli.main` 的 `export` 子命令。

覆盖两件在 `cli.py` 里**只有一行**、但行为语义很重的事（裁定 R-T8-1）：
  * `--limit` 缺省（`type=int, default=0`）在 `export.run` / `gates.run_all` 里都等价于**不限**
    （`if limit:` 判真值）⇒ 不传 `--limit` 时**不得**截断；
  * 撞 slug（`collided`）与跳过（`skipped`）是**两种不同的事故** ⇒ 必须**分行**打印，
    混在一行会让人以为只是上游缺文件。

全程用临时目录 + `tests/fixtures` 下的**小 y 上游**，不碰真上游、不跑全量。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import cli  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# fixtures 里真实存在的两个卷（见 tools/tests/fixtures/xingcezhenti/）
_SICHUAN_TITLES = ["2016年423联考《行测》题（四川卷）"]
_JIANGSU_TITLES = ["2020年江苏省公务员录用考试《行测》题（A类）"]
# fixtures 里**不存在**的卷名，只用来制造「同一键两个卷名」
_GHOST_TITLE = "2017年天津滨海新区公务员考试《行测》题（网友回忆版）"


def _row(slug, *, level, region, year, subject, ptype, modules, sources, titles,
         nature="正式真题", form="单独命题"):
    return {
        "slug": slug, "level": level, "region": region, "year": year,
        "subject": subject, "ptype": ptype, "modules": modules, "sources": sources,
        "titles": titles, "nature": nature, "form": form,
        "title": (titles.get("linfukai186") or titles.get("xingcezhenti"))[0],
        "n_questions": sum(modules.values()), "declared_questions": sum(modules.values()),
        "dubious": [],
    }


class _CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwycli-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write_catalog(self, rows, name="catalog"):
        d = os.path.join(self.tmp, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "catalog.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return d

    def _run_export(self, catalog_dir, repo, *extra):
        argv = ["export", "--catalog", catalog_dir, "--upstream", FIX, "--repo", repo]
        argv += list(extra)
        # `cmd_export` 把报告写进 stdout；捕获它以便逐行断言
        s = io.StringIO()
        with redirect_stdout(s):
            code = cli.main(argv)
        return code, s.getvalue()


class TestExportLimitSemantics(_CliCase):
    """`--limit` 缺省 = **不限**（`default=0` 且 `if limit:` 判真值）。"""

    def _three_row_catalog(self):
        # 3 行小 catalog：2 行可导出（有 xingcezhenti 正文）+ 1 行纯 linfukai186（必跳过）
        return self._write_catalog([
            _row("省考-四川-2016-行测-统考", level="省考", region="四川", year="2016",
                 subject="行测", ptype="统考", modules={"常识判断": 1, "资料分析": 1},
                 sources=["linfukai186", "xingcezhenti"], titles={"xingcezhenti": _SICHUAN_TITLES}),
            _row("省考-江苏-2020-行测-A类", level="省考", region="江苏", year="2020",
                 subject="行测", ptype="A类", modules={"资料分析": 1},
                 sources=["xingcezhenti"], titles={"xingcezhenti": _JIANGSU_TITLES}),
            _row("国考-2016-申论-统考", level="国考", region="", year="2016",
                 subject="申论", ptype="统考", modules={"公文写作题": 1},
                 sources=["linfukai186"], titles={"linfukai186": ["2016·国家公务员考试"]}),
        ])

    def test_default_limit_is_unlimited_not_zero_rows(self):
        cat = self._three_row_catalog()
        repo = os.path.join(self.tmp, "repo-default")
        code, out = self._run_export(cat, repo)          # 不传 --limit
        self.assertEqual(code, 0)
        # **不截断**：3 行里 2 行可导出 ⇒ 全部导出（若 0 被当成「取前 0 行」这里会是 0）
        self.assertIn("卷 2 |", out)
        self.assertTrue(os.path.exists(os.path.join(repo, "省考/四川/2016/行测-统考.md")))
        self.assertTrue(os.path.exists(os.path.join(repo, "省考/江苏/2020/行测-A类.md")))
        # 第 3 行（纯 linfukai186）如实进 skipped，而不是被静默丢
        self.assertIn("跳过 1 项", out)

    def test_explicit_limit_does_truncate(self):
        cat = self._three_row_catalog()
        repo = os.path.join(self.tmp, "repo-limit1")
        code, out = self._run_export(cat, repo, "--limit", "1")   # 显式截断到第 1 行
        self.assertEqual(code, 0)
        self.assertIn("卷 1 |", out)
        self.assertTrue(os.path.exists(os.path.join(repo, "省考/四川/2016/行测-统考.md")))
        self.assertFalse(os.path.exists(os.path.join(repo, "省考/江苏/2020/行测-A类.md")))


class TestCollidedAndSkippedAreSeparateLines(_CliCase):
    """裁定 R-T8-1：撞 slug（`collided`）与跳过（`skipped`）**必须分行**，不得混成一句。"""

    def test_collided_printed_on_its_own_line_with_count(self):
        # 同一键在 xingcezhenti 侧有**两个**卷名 ⇒ 只导第一个，第二个进 collided；
        # 另有一行纯 linfukai186 ⇒ 进 skipped。两份事故必须各占一行。
        cat = self._write_catalog([
            _row("省考-四川-2016-行测-统考", level="省考", region="四川", year="2016",
                 subject="行测", ptype="统考", modules={"常识判断": 1, "资料分析": 1},
                 sources=["linfukai186", "xingcezhenti"],
                 titles={"xingcezhenti": _SICHUAN_TITLES + [_GHOST_TITLE]}),
            _row("国考-2016-申论-统考", level="国考", region="", year="2016",
                 subject="申论", ptype="统考", modules={"公文写作题": 1},
                 sources=["linfukai186"], titles={"linfukai186": ["2016·国家公务员考试"]}),
        ])
        repo = os.path.join(self.tmp, "repo-collide")
        code, out = self._run_export(cat, repo)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        collided = [l for l in lines if "撞 slug" in l]
        skipped = [l for l in lines if "跳过" in l]
        # 两行都在，且各只一次
        self.assertEqual(len(collided), 1, out)
        self.assertEqual(len(skipped), 1, out)
        # collided 的计数为 1（只有 1 条卷名被撞掉）
        self.assertIn("1", collided[0])
        # **分行**：两句互不为对方的一部分
        self.assertNotIn("跳过", collided[0])
        self.assertNotIn("撞 slug", skipped[0])
        # 只导了排序后第一个卷名，第二卷名未被导出
        self.assertTrue(os.path.exists(os.path.join(repo, "省考/四川/2016/行测-统考.md")))


if __name__ == "__main__":
    unittest.main()
