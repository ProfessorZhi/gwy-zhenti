# -*- coding: utf-8 -*-
"""申论证据审计工具的门禁测试（只读）。

这些断言把**当前已知缺陷**钉成常量：不是宣称缺陷已修，而是让缺陷数目
一旦变化就报警，避免静默增多或假装已解决。
"""
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "audit" / "shenlun_evidence_audit_20261017.py"

_spec = importlib.util.spec_from_file_location("shenlun_evidence_audit", TOOL)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

# 2026-10-15 报告登记 21 份；2026-10-16 commit 1d1379c3 补入江苏2026 A/C
REGISTERED = 21
RECONCILED_PRESENT = {("江苏", "2026", "A"), ("江苏", "2026", "C")}
# 2026-10-17 已把 9 处悬空指针降级为「源不可考」标记（PR 见 reports/
# FULL-REPAIR-SHENLUN-SOURCE-PROVENANCE-20261017.jsonl）。此后不应再有悬空指针。
DOWNGRADED = {
    "国考/2024/申论-副省级.md", "国考/2024/申论-地市级.md", "国考/2024/申论-行政执法.md",
    "国考/2025/申论-副省级.md", "国考/2025/申论-地市级.md", "国考/2025/申论-行政执法.md",
    "国考/2026/申论-副省级.md", "国考/2026/申论-地市级.md", "国考/2026/申论-行政执法.md",
}


class ShenlunEvidenceAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        cls.data = audit.build(str(ROOT))
        os.chdir(cls.cwd)

    def test_registered_missing_count_is_the_report_number(self):
        m = self.data["missing_whole_papers"]
        self.assertEqual(m["registered_in_report"], REGISTERED)

    def test_every_registered_paper_is_classified_present_or_absent(self):
        m = self.data["missing_whole_papers"]
        self.assertEqual(len(m["entries"]), REGISTERED)
        for e in m["entries"]:
            self.assertIn(e["status"], ("present", "absent"), e)
            if e["status"] == "present":
                self.assertTrue(e["matched_file"], e)

    def test_only_jiangsu_2026_AC_reconciled_by_later_commit(self):
        got = {(r["region"], r["year"], r["paper_type"])
               for r in self.data["missing_whole_papers"]["reconciled_present"]}
        self.assertEqual(got, RECONCILED_PRESENT)
        self.assertEqual(self.data["missing_whole_papers"]["confirmed_still_missing"],
                         REGISTERED - len(RECONCILED_PRESENT))

    def test_zhejiang_2022_shenlun_still_absent(self):
        """浙江2022申论A/B/C：公开公告证实开考且独立分卷，但库内仍无正文。"""
        entries = {(e["region"], e["year"], e["paper_type"]): e
                   for e in self.data["missing_whole_papers"]["entries"]}
        for t in ("A", "B", "C"):
            self.assertEqual(entries[("浙江", "2022", t)]["status"], "absent")

    def test_no_dangling_answer_source_pointers_remain(self):
        """悬空指针必须为 0；指针目标若存在则放行。"""
        bad = {x["path"] for x in self.data["dangling_answer_source_pointers"]
               if not x["target_exists"]}
        self.assertEqual(bad, set(), "仍有悬空答案来源指针：%s" % sorted(bad))

    def test_nine_files_carry_source_unverifiable_marker(self):
        got = {m["path"] for m in self.data["source_unverifiable_markers"]}
        self.assertEqual(got, DOWNGRADED)

    def test_every_shenlun_file_hash_is_recorded_in_some_receipt(self):
        c = self.data["receipt_coverage"]
        self.assertEqual(c["unrecorded"], [])
        self.assertEqual(c["current_hash_recorded"], c["files"])

    def test_audit_is_read_only(self):
        """build() 前后正式卷逐字节不变：证明工具确实只读。"""
        import hashlib

        def snapshot():
            snap = {}
            for top in ("国考", "省考"):
                for p in sorted((ROOT / top).rglob("*.md")):
                    snap[p.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
            return snap

        before = snapshot()
        cwd = os.getcwd()
        try:
            audit.build(str(ROOT))
        finally:
            os.chdir(cwd)
        self.assertEqual(snapshot(), before, "审计不得改动正式卷")


if __name__ == "__main__":
    unittest.main()
