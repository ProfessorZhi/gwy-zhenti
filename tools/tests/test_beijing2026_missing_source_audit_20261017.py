# -*- coding: utf-8 -*-
"""北京 2026 行测（统考）缺原题 51 题：metadata-only 台账自检。

只校验结构、题号补集、模块分区、哈希与“零正文/零图片”边界；
不把任何第三方题干/选项当测试夹具。
"""
import hashlib
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MD = os.path.join(ROOT, "省考", "北京", "2026", "行测-统考.md")
MANIFEST = os.path.join(ROOT, "catalog", "manifest.jsonl")
REPORT = os.path.join(
    ROOT, "reports", "BEIJING2026-MISSING-SOURCE-AUDIT-20261017.json"
)

EXPECTED_MD_SHA256 = "012bcadc0301fc178f246827035298d8b0697da836df20a246c49f6c2ee98bf0"
EXPECTED_MISSING = [
    2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 22, 31,
    34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 89, 90, 96, 97, 98, 99,
    100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 112, 114,
    115, 117,
]
EXPECTED_MODULE_COUNTS = {
    "政治理论": 14,
    "常识判断": 7,
    "言语理解与表达": 9,
    "数量关系": 0,
    "判断推理·图形推理": 2,
    "判断推理·类比推理": 0,
    "判断推理·逻辑判断": 10,
    "判断推理·定义判断": 5,
    "判断推理·科学推理": 4,
    "资料分析": 0,
}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def present_anchors(text):
    return sorted(int(n) for n in re.findall(r"^#{2,3} 第 (\d+) 题", text, re.M))


def manifest_row():
    for line in read(MANIFEST).splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            row.get("area") == "北京"
            and row.get("year") == "2026"
            and row.get("subject") == "行测"
            and row.get("paper_type") == "统考"
        ):
            return row
    raise AssertionError("manifest 中找不到 北京/2026/行测/统考")


class TestBeijing2026MissingSourceAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(MD)
        cls.present = present_anchors(cls.text)
        cls.report = json.loads(read(REPORT))
        cls.manifest = manifest_row()

    def test_paper_sha256_unchanged(self):
        with open(MD, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(digest, EXPECTED_MD_SHA256)
        self.assertEqual(digest, self.manifest["sha256"])
        self.assertEqual(digest, self.report["baseline"]["paper_sha256"])

    def test_missing_is_exact_complement_within_118(self):
        self.assertEqual(len(self.present), 67)
        self.assertEqual(max(self.present), 118)
        complement = sorted(set(range(1, 119)) - set(self.present))
        self.assertEqual(complement, EXPECTED_MISSING)
        self.assertEqual(complement, sorted(self.report["missing_numbers"]))
        self.assertEqual(complement, sorted(self.manifest["missing_original_numbers"]))
        self.assertEqual(len(complement), 51)

    def test_frontmatter_missing_list_matches(self):
        m = re.search(r"^缺失原题号:\s*(\[[^\]]*\])", self.text, re.M)
        self.assertIsNotNone(m, "frontmatter 缺 缺失原题号")
        self.assertEqual(json.loads(m.group(1)), EXPECTED_MISSING)

    def test_module_partition_covers_each_missing_once(self):
        rows = self.report["missing_by_module"]
        counts = {r["module"]: r["count"] for r in rows}
        self.assertEqual(counts, EXPECTED_MODULE_COUNTS)
        seen = []
        for r in rows:
            self.assertEqual(r["count"], len(r["missing_numbers"]), r["module"])
            seen.extend(r["missing_numbers"])
        self.assertEqual(sorted(seen), EXPECTED_MISSING)
        self.assertEqual(len(seen), len(set(seen)), "缺号不得跨模块重复")
        self.assertEqual(sum(EXPECTED_MODULE_COUNTS.values()), 51)

    def test_boundary_is_not_overclaimed(self):
        scope = self.report["missing_scope"]
        self.assertEqual(scope["observed_max_number"], 118)
        self.assertEqual(scope["missing_count_within_118"], 51)
        self.assertFalse(scope["complete_paper"])
        self.assertTrue(scope["complement_verified"])
        # 118 以后只能是推定，不能混入已取证的 51
        extra = scope["inferred_full_paper"]["inferred_additional_missing"]
        self.assertEqual(extra[:2], [119, 120])
        self.assertFalse(set(extra) & set(EXPECTED_MISSING))

    def test_no_new_content_or_images(self):
        s = self.report["summary"]
        self.assertEqual(s["new_legal_content_items"], 0)
        self.assertEqual(s["questions_added"], 0)
        self.assertEqual(s["images_added"], 0)
        self.assertEqual(s["verified_new_question_text_sources"], 0)

    def test_report_carries_no_third_party_bodies(self):
        text = read(REPORT)
        for token in (".png", ".jpg", ".jpeg", "base64", "<img"):
            self.assertNotIn(token, text, token)

        def keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield k
                    yield from keys(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from keys(v)

        forbidden = {"stem", "options", "answer_text", "analysis_text", "content_html"}
        self.assertFalse(set(keys(self.report)) & forbidden)
        self.assertLess(len(text.encode("utf-8")), 100_000)

    def test_ledger_status_counts_are_consistent(self):
        rows = self.report["source_ledger"]
        status = [r["status"] for r in rows]
        s = self.report["summary"]
        self.assertEqual(len(rows), s["independent_urls_ledgered"])
        self.assertEqual(status.count("rejected_mismatch"), s["rejected_mismatch_documents"])
        self.assertEqual(status.count("partial_mirror"), s["partial_mirror_entries"])
        self.assertEqual(
            sum(1 for x in status if x.startswith("blocked_")),
            s["blocked_antibot_login_or_403"],
        )
        self.assertEqual(
            sum(1 for x in status if x.startswith("empty")),
            s["empty_no_2026_or_no_results"],
        )
        self.assertEqual(
            sum(1 for x in status if x == "verified_metadata"),
            s["verified_metadata_sources"],
        )
        self.assertEqual(
            sum(1 for x in status if x == "verified_no_paper_section"),
            s["verified_official_no_paper_section"],
        )
        self.assertEqual(
            sum(1 for x in status if x.startswith("verified_secondary")),
            s["verified_secondary_sources"],
        )
        self.assertEqual(
            sum(1 for x in status if x == "commercial_no_license"),
            s["commercial_books_no_license"],
        )

    def test_queries_are_substantive(self):
        self.assertGreaterEqual(len(self.report["queries"]), 40)
        self.assertEqual(len(set(self.report["queries"])), len(self.report["queries"]))

    def test_metadata_defect_is_reported_not_patched(self):
        # 原始 PDF 的 SHA-256 只有 51 位；本轮只报告，不猜补
        shas = re.findall(r"`([0-9a-f]{40,})`", self.text)
        lengths = sorted(len(x) for x in shas)
        self.assertEqual(lengths, [51, 64])
        defects = self.report["metadata_defects"]
        self.assertTrue(any("51" in d["observed"] for d in defects))


if __name__ == "__main__":
    unittest.main(verbosity=2)
