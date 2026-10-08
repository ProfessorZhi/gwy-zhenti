# -*- coding: utf-8 -*-
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import catalog, export, gates      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class TestGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwygate-")
        self.cat = os.path.join(self.tmp, "catalog")
        self.repo = os.path.join(self.tmp, "repo")
        up = {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}
        catalog.build({**up, "linfukai186": os.path.join(FIX, "linfukai186")}, self.cat)
        export.run(self.cat, up, self.repo)
        self.rep = gates.run_all(self.cat, up, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _up(self):
        return {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}

    def test_all_six_gates_reported(self):
        names = [n for n, _, _ in self.rep.results]
        for g in ("G1", "G2", "G3", "G4", "G5", "G6"):
            self.assertTrue(any(x.startswith(g) for x in names), names)

    def test_all_pass_on_fixture(self):
        self.assertTrue(self.rep.ok, [(n, d) for n, ok, d in self.rep.results if not ok])

    def test_g2_detects_dangling_image(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("154428b1a538147.png", "missing-zzz.png")
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        rep = gates.run_all(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G2") and not ok for n, ok, _ in rep.results))

    def test_g2_known_source_gap_is_named_not_silent(self):
        """清单内的已知缺图 ⇒ G2 **不判负**，但必须**点名**（区别于清单外的缺失 = 缺陷）。"""
        os.remove(os.path.join(
            self.repo, "图片/省考-四川-2016-行测-统考/题目图/154428b1a538147.png"))
        with mock.patch.object(gates, "KNOWN_SOURCE_GAPS",
                               frozenset({"154428b1a538147.png"})):
            rep = gates.run_all(self.cat, self._up(), self.repo)
        name, ok, detail = [r for r in rep.results if r[0].startswith("G2")][0]
        self.assertTrue(ok, detail)
        self.assertIn("154428b1a538147.png", detail)

    def test_g6_detects_missing_paper(self):
        """G6 是 catalog→落盘的反向对账：整卷丢失必须红（G5 只从 md 出发，看不见这一面）。"""
        os.remove(os.path.join(self.repo, "省考/江苏/2020/行测-A类.md"))
        rep = gates.run_all(self.cat, self._up(), self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G6") and not ok for n, ok, _ in rep.results))

    def test_g5_detects_content_change(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        perturbed = re.sub(r"(?m)^(- \*\*A\*\*\. )(\d+)", r"\g<1>999999", text, count=1)
        self.assertNotEqual(perturbed, text, "fixture 里没有可扰动的 A 选项行")
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(perturbed)
        rep = gates.run_all(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G5") and not ok for n, ok, _ in rep.results))
