# -*- coding: utf-8 -*-
"""缺口总账与 README 缺口区块必须与当前试卷、缺卷台账一致。"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from gap_report import MATERIAL_REF, collect, grades, summary, unregistered  # noqa: E402


class GapReport(unittest.TestCase):
    def test_generated_files_are_current(self):
        result = subprocess.run([sys.executable, "-I", str(ROOT / "tools/gap_report.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_missing_paper_ledger_is_well_formed_and_not_collected(self):
        rows = [json.loads(l) for l in (ROOT / "catalog/uncollected-slots.jsonl").read_text(encoding="utf-8").splitlines() if l]
        keys = [(r["area"], r["year"], r["subject"], r["variant"]) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        for r in rows:
            self.assertIn(r["status"], {"缺卷", "无独立考试"})
            self.assertIn(r["subject"], {"行测", "申论"})
            self.assertGreaterEqual(r["year"], 2016)
            self.assertTrue(r["basis"])
            if r["variant"]:
                path = ROOT / "省考" / r["area"] / str(r["year"]) / f"{r['subject']}-{r['variant']}.md"
                self.assertFalse(path.exists(), path)

    def test_slot_ledger_partitions_expected_papers(self):
        rows = [json.loads(l) for l in (ROOT / "catalog/exam-slots.jsonl").read_text(encoding="utf-8").splitlines() if l]
        for r in rows:
            self.assertIn(r["status"], {"已收录", "缺卷", "无独立考试"})
            self.assertEqual(r["status"] == "已收录", bool(r["papers"]), r)
            if r["status"] == "已收录":
                self.assertTrue(r["sources"], r)
                for p in r["papers"]:
                    self.assertTrue((ROOT / p).exists(), p)
            else:
                self.assertTrue(r["basis"], r)

    def test_every_recent_slot_is_registered(self):
        """2016–2026 每个地区×年份×科目要么已收录，要么在台账中登记为缺卷或无独立考试。"""
        rows, xingce, shenlun, papers = collect()
        self.assertEqual([], unregistered(rows, grades(rows, xingce, shenlun), papers))

    def test_xingce_levels_do_not_overlap(self):
        _, xingce, _, _ = collect()
        for path, v in xingce.items():
            sets = [set(v["stem"]), set(v["option"]), set(v["answer"])]
            self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2], path)

    def test_material_ranges_are_parsed(self):
        refs = MATERIAL_REF.findall("根据给定资料2\\-4，归纳问题；结合材料6作答；拨打12345热线")
        self.assertEqual([("2", "4"), ("6", "")], refs)


if __name__ == "__main__":
    unittest.main()
