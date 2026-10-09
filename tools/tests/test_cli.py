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
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import cli, export  # noqa: E402

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
        # **整行断言**（原为 `assertIn("1", ...)` —— 计数误成 10 / 21 仍会过，太弱）：
        # 串取自 `cli.cmd_export` 的实际 `print`（`"  撞 slug 未导的卷名 %d 条（详见报告）"`）。
        self.assertEqual(collided[0], "  撞 slug 未导的卷名 1 条（详见报告）")
        self.assertEqual(skipped[0], "  跳过 1 项（详见报告）")
        # **分行**：两句互不为对方的一部分
        self.assertNotIn("跳过", collided[0])
        self.assertNotIn("撞 slug", skipped[0])
        # 只导了排序后第一个卷名，第二卷名未被导出
        self.assertTrue(os.path.exists(os.path.join(repo, "省考/四川/2016/行测-统考.md")))


class TestGateSubcommand(_CliCase):
    """整改 F2·G：`cli.py` 的 `gate` 子命令此前**没有**回归（Task 11 复审 Minor）。

    覆盖三件事：干净夹具仓 ⇒ 返回 0；弄坏一卷 ⇒ 返回 1（接线到 `gates.run_all` 且**退出码**可判）；
    `--limit` 语义（缺省 `0` = 不限、`--limit 1` = 截断）**不改判据**，两者都返回 0。
    """

    def _exportable_catalog(self):
        # 2 行**都可导出**（都有 xingcezhenti 正文），避免「跳过」干扰闸门对账
        return self._write_catalog([
            _row("省考-四川-2016-行测-统考", level="省考", region="四川", year="2016",
                 subject="行测", ptype="统考", modules={"常识判断": 1, "资料分析": 1},
                 sources=["linfukai186", "xingcezhenti"], titles={"xingcezhenti": _SICHUAN_TITLES}),
            _row("省考-江苏-2020-行测-A类", level="省考", region="江苏", year="2020",
                 subject="行测", ptype="A类", modules={"资料分析": 1},
                 sources=["xingcezhenti"], titles={"xingcezhenti": _JIANGSU_TITLES}),
        ])

    def _clean_repo(self):
        cat = self._exportable_catalog()
        repo = os.path.join(self.tmp, "repo-gate")
        code, _ = self._run_export(cat, repo)
        self.assertEqual(code, 0)
        return cat, repo

    def _run_gate(self, catalog_dir, repo, *extra):
        argv = ["gate", "--catalog", catalog_dir, "--upstream", FIX, "--repo", repo]
        argv += list(extra)
        s = io.StringIO()
        with redirect_stdout(s):
            code = cli.main(argv)
        return code, s.getvalue()

    def test_gate_returns_zero_on_clean_fixture_repo(self):
        cat, repo = self._clean_repo()
        code, out = self._run_gate(cat, repo)
        self.assertEqual(code, 0, out)
        self.assertIn("[OK] G1", out)
        self.assertIn("[OK] G6", out)

    def test_gate_returns_one_when_a_paper_is_broken(self):
        # 破坏 A1 那种：把第 1 题题号改成第 8 题 ⇒ G1 判负 ⇒ 退出码 1
        cat, repo = self._clean_repo()
        md = os.path.join(repo, "省考", "四川", "2016", "行测-统考.md")
        with io.open(md, encoding="utf-8") as fh:
            text = fh.read()
        with io.open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace("## 第 1 题", "## 第 8 题", 1))
        code, out = self._run_gate(cat, repo)
        self.assertEqual(code, 1, out)
        self.assertIn("[FAIL] G1", out)

    def test_gate_limit_defaults_to_unlimited_and_limit_one_still_passes(self):
        # `--limit` 缺省（0）= 不限；`--limit 1` = 截断（只对账 catalog 第 1 行 / 前 1 个 md）。
        # **它不改判据**，只改**对账范围** ⇒ 干净仓上两者都必须返回 0。
        cat, repo = self._clean_repo()
        code0, out0 = self._run_gate(cat, repo)                       # 不传 --limit ⇒ 0
        self.assertEqual(code0, 0, out0)
        code0b, out0b = self._run_gate(cat, repo, "--limit", "0")      # 显式 0 ⇒ 同「不限」
        self.assertEqual(code0b, 0, out0b)
        self.assertIn("本次对账 2", out0b)                              # 0 ⇒ 全量对账
        code1, out1 = self._run_gate(cat, repo, "--limit", "1")
        self.assertEqual(code1, 0, out1)
        self.assertIn("本次对账 1", out1)                              # 1 ⇒ 截断
        self.assertIn("limit 生效", out1)


class TestCliExportSinceDefault(_CliCase):
    """R-M3-18 回归：**裸** `export`（不传 `--since`）的 `since` 必须落到交付下限 2016。

    与 `TestCliGateForwardsSince`（`gate` 侧）同款：`--since` 缺省若为空串 ⇒ `cmd_export`
    的 `or None` ⇒ 不过滤 ⇒ catalog 可导出 1003 vs 落盘 895 ⇒ 误报「未落盘」。这条钉死缺省 =
    `export.SCOPE_SINCE`；`--since ""` 仍折成 `None`（不过滤的逃生门）。
    """

    class _Rep:
        papers = 0
        files = 0
        images = 0
        skipped = []
        collided = []

    def _call(self, *extra):
        s = io.StringIO()
        with mock.patch.object(export, "run", return_value=self._Rep()) as m:
            with redirect_stdout(s):
                code = cli.main(["export", "--catalog", "cat", "--upstream", "up",
                                 "--repo", "repo"] + list(extra))
        self.assertEqual(code, 0, s.getvalue())
        return m

    def test_cli_export_since_defaults_to_the_scope_floor(self):
        m = self._call()                    # 不传 --since ⇒ 交付下限
        self.assertEqual(m.call_args.kwargs.get("since"), "2016",
                         "裸 export 的 since 必须是交付下限 2016，否则会误报未落盘")
        m = self._call("--since", "2016")   # 显式传值照旧
        self.assertEqual(m.call_args.kwargs.get("since"), "2016")
        m = self._call("--since", "")       # 显式空串 = 不过滤（原意保留）
        self.assertIsNone(m.call_args.kwargs.get("since"))


if __name__ == "__main__":
    unittest.main()
