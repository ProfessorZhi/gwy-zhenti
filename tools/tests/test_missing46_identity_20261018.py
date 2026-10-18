# -*- coding: utf-8 -*-
"""37 槽位身份账本的门禁测试（只读）。

钉住三件事：槽位集合必须与 MISSING48 登记的真实剩余槽位完全一致；
不得声称本轮恢复了任何完整卷；三条身份判定不得被静默改写。
"""
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "audit" / "missing46_identity_20261018.py"
LEDGER = ROOT / "reports" / "MISSING46-ZJ-SH-TJ-IDENTITY-20261018.json"

STATUSES = {"source_missing", "available_but_restricted", "partly_observed", "unknown"}
EXISTENCE = {"confirmed_official", "confirmed_public_secondary",
             "not_confirmed_this_run", "inferred_from_sibling"}
IDENTITY = {"independent_paper", "separate_recruitment_exam"}

_spec = importlib.util.spec_from_file_location("m46", TOOL)
m46 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m46)


class Missing46Identity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        cls.d = m46.build(str(ROOT))
        os.chdir(cls.cwd)
        cls.slots = cls.d["slots"]

    def test_slot_set_matches_registry_remaining(self):
        import json
        reg = json.loads((ROOT / "reports/MISSING48-RECOVERY-20261016.json").read_text(encoding="utf-8"))
        want = {(t["area"], t["year"], t["subject"], t["variant"])
                for t in reg["targets"] if not t["counted_as_recovered_this_round"]}
        want = {k for k in want if k[0] in ("浙江", "上海", "天津")}
        got = {(s["area"], s["year"], s["subject"], s["variant"]) for s in self.slots}
        self.assertEqual(got, want)
        self.assertEqual(len(got), 37)

    def test_area_split_is_15_16_6(self):
        import collections
        c = collections.Counter(s["area"] for s in self.slots)
        self.assertEqual(dict(c), {"浙江": 15, "上海": 16, "天津": 6})

    def test_no_claim_of_recovered_complete_papers(self):
        self.assertEqual(self.d["recovered_complete_papers_this_round"], 0)

    def test_vocabularies_are_closed(self):
        for s in self.slots:
            self.assertIn(s["completeness_status"], STATUSES, s["slot_id"] if "slot_id" in s else s)
            self.assertIn(s["paper_existence"], EXISTENCE, s)
            self.assertIn(s["paper_identity"], IDENTITY, s)

    def test_youxiu_cun_ganbu_slots_are_aptitude_not_essay(self):
        """优秀村干部类的同场主观题是《综合应用能力》，不得记成申论。"""
        vip = [s for s in self.slots if "优秀村干部" in s["variant"]]
        self.assertEqual(len(vip), 11)
        for s in vip:
            self.assertEqual(s["subject"], "行测")
            self.assertIn("综合应用能力", s["note"])

    def test_shanghai_zhifa_slots_are_separate_recruitment(self):
        """上海行政执法专项＝独立招录考试，不是上海市考的第三种申论卷。"""
        zf = [s for s in self.slots if s["variant"] == "行政执法专项"]
        self.assertEqual(len(zf), 8)
        for s in zf:
            self.assertEqual(s["paper_identity"], "separate_recruitment_exam")

    def test_unconfirmed_slots_are_not_marked_missing_nor_confirmed(self):
        """未取到卷证的槽位既不得写成 confirmed，也不得写成不存在。"""
        nc = [s for s in self.slots if s["paper_existence"] == "not_confirmed_this_run"]
        self.assertGreater(len(nc), 0)
        for s in nc:
            self.assertEqual(s["completeness_status"], "unknown", s)

    def test_tianjin_2024_and_2026_three_types_confirmed(self):
        want = {("天津", 2024, "综合街镇"), ("天津", 2024, "行政执法"),
                ("天津", 2026, "综合市区"), ("天津", 2026, "综合街镇")}
        got = {(s["area"], s["year"], s["variant"]) for s in self.slots
               if s["area"] == "天津" and s["paper_existence"] == "confirmed_public_secondary"}
        self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
