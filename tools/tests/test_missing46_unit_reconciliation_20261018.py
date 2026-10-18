# -*- coding: utf-8 -*-
"""46 专项缺口 × 47 资料缺档 单位对账的门禁测试（只读）。

钉住：单位 A 必须由 registry 字段重算而非手抄；两单位零重叠；
PR#74 的「21+25」错位拆分数不得回流；九槽裁定计数固定。
"""
import collections
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "audit" / "missing46_unit_reconciliation_20261018.py"

_spec = importlib.util.spec_from_file_location("rec46", TOOL)
rec46 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rec46)

CLASSES = {"confirmed_missing", "plausible_unconfirmed", "partial_existing", "ruled_out"}


class UnitReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        cls.d = rec46.build(str(ROOT))
        os.chdir(cls.cwd)

    def test_unit_a_is_recomputed_to_46(self):
        a = self.d["unit_a_missing_papers"]
        self.assertEqual(a["targets_total"], 48)
        self.assertEqual(a["recovered_this_round"], 2)
        self.assertEqual(a["remaining"], 46)
        self.assertEqual(a["remaining"], a["declared_remaining"])

    def test_unit_a_subject_split_is_19_essay_27_aptitude(self):
        """PR#74 的 21+25 是错位拆分；registry 重算必须是 19+27。"""
        got = self.d["unit_a_missing_papers"]["remaining_by_subject"]
        self.assertEqual(got, {"申论": 19, "行测": 27})
        self.assertNotEqual(got, {"申论": 21, "行测": 25})

    def test_recovered_two_are_both_essay(self):
        rec = self.d["unit_a_missing_papers"]["recovered_list"]
        self.assertEqual(len(rec), 2)
        self.assertTrue(all(r["subject"] == "申论" for r in rec), rec)

    def test_lane37_plus_other9_partitions_46(self):
        a = self.d["unit_a_missing_papers"]
        self.assertEqual(a["lane_37"]["count"], 37)
        self.assertEqual(a["other_9"]["count"], 9)
        self.assertEqual(a["lane_37"]["count"] + a["other_9"]["count"], 46)
        self.assertEqual(a["lane_37"]["by_subject"], {"申论": 16, "行测": 21})
        self.assertEqual(a["other_9"]["by_subject"], {"申论": 3, "行测": 6})

    def test_unit_b_is_47_cells_with_29_18(self):
        b = self.d["unit_b_material_cells"]
        self.assertEqual(b["total"], 47)
        self.assertEqual(b["by_state"], {"资料缺失": 29, "待核实": 18})

    def test_units_do_not_overlap(self):
        self.assertEqual(self.d["dedupe"]["overlap_count"], 0)
        self.assertEqual(self.d["dedupe"]["overlap_cells"], [])

    def test_classification_counts_are_pinned(self):
        self.assertEqual(self.d["classification_counts_9"],
                         {"confirmed_missing": 4, "partial_existing": 3, "plausible_unconfirmed": 2})

    def test_every_slot_uses_closed_vocabulary(self):
        for s in self.d["slots_9"]:
            self.assertIn(s["classification"], CLASSES, s)
            self.assertTrue(s["evidence"]["finding"], s)

    def test_no_new_content_claimed(self):
        self.assertEqual(self.d["new_complete_licensed_papers_this_round"], 0)
        self.assertEqual(self.d["new_external_source_receipts_this_round"], 0)

    def test_non_additivity_rules_present(self):
        rules = " ".join(self.d["non_additivity_rules"])
        self.assertIn("106", rules)
        self.assertIn("相加", rules)

    def test_read_only(self):
        import hashlib
        def snap():
            out = {}
            for top in ("国考", "省考", "资料缺失"):
                for p in sorted((ROOT / top).rglob("*")):
                    if p.is_file():
                        out[p.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
            return out
        before = snap()
        cwd = os.getcwd()
        try:
            rec46.build(str(ROOT))
        finally:
            os.chdir(cwd)
        self.assertEqual(snap(), before, "审计不得改动正式卷或资料缺失索引")


if __name__ == "__main__":
    unittest.main()
