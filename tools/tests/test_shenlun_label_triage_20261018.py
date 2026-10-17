# -*- coding: utf-8 -*-
"""申论「正式真题」标签分级校勘的门禁测试（只读）。

把 2026-10-18 的裁决结果钉成常量：468 份已改、39 份保留待人工复核。
任何一侧数量变化即报警，防止后续静默扩大或回退。
"""
import glob
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "reports" / "FULL-REPAIR-SHENLUN-ZHENTI-LABEL-20261018.jsonl"
NEW_LABEL = "第三方整理真题，非官方原件"
EXPECT_CHANGED = 468
EXPECT_REMAIN_BARE = 39


def _fm(t):
    if not t.startswith("---"):
        return ""
    p = t.split("---", 2)
    return p[1] if len(p) > 2 else ""


def _field(f, k):
    m = re.search(r"^%s:\s*(.*)$" % re.escape(k), f, flags=re.M)
    return m.group(1).strip() if m else ""


def _shenlun():
    return sorted(glob.glob("国考/*/申论-*.md", root_dir=ROOT) +
                  glob.glob("省考/*/*/申论-*.md", root_dir=ROOT))


class ShenlunLabelTriage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [json.loads(l) for l in RECEIPT.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_receipt_has_expected_record_count(self):
        self.assertEqual(len(self.rows), EXPECT_CHANGED)

    def test_every_changed_file_now_carries_new_label(self):
        for r in self.rows:
            t = (ROOT / r["path"]).read_text(encoding="utf-8")
            self.assertEqual(_field(_fm(t), "真题性质").strip('"'), NEW_LABEL, r["path"])

    def test_every_changed_file_matches_receipt_hash(self):
        for r in self.rows:
            cur = hashlib.sha256((ROOT / r["path"]).read_bytes()).hexdigest()
            self.assertEqual(cur, r["after_sha256"], r["path"])

    def test_remaining_bare_labels_are_exactly_the_review_set(self):
        bare = []
        for p in _shenlun():
            t = (ROOT / p).read_text(encoding="utf-8")
            if _field(_fm(t), "真题性质").strip('"') == "正式真题":
                bare.append(p)
        self.assertEqual(len(bare), EXPECT_REMAIN_BARE)
        changed = {r["path"] for r in self.rows}
        self.assertEqual(sorted(set(bare) & changed), [], "同一份不能既改又保留")

    def test_no_changed_file_still_claims_bare_officialness(self):
        for r in self.rows:
            t = (ROOT / r["path"]).read_text(encoding="utf-8")
            self.assertNotIn('真题性质: "正式真题"', t, r["path"])

    def test_receipts_are_append_only_distinct_files(self):
        paths = [r["path"] for r in self.rows]
        self.assertEqual(len(paths), len(set(paths)), "receipt 不得重复记录同一文件")


if __name__ == "__main__":
    unittest.main()
