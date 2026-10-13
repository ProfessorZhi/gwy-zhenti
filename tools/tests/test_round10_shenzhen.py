"""R10深圳2025两卷六题：来源题面保护、完整答案与全库覆盖回归。"""
import hashlib
import json
import re
import unittest
from pathlib import Path

import round5_bulk as parser
from r7_reference_audit import audit, assess

ROOT = Path(__file__).resolve().parents[2]
DRAFTS = ROOT / "reports/ROUND10-ORIGINAL-ANSWER-DRAFTS-20261013.json"
RECEIPT = ROOT / "reports/ROUND10-ORIGINAL-ANSWERS-20261013.jsonl"
MANIFEST = ROOT / "catalog/manifest.jsonl"
SUMMARY = ROOT / "reports/REPAIR-SUMMARY-20261013-R10.json"
DETAILS = re.compile(r"<summary>第\s*(\d+)\s*题</summary>(.*?)</details>", re.S)


def checksum(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def body_before_answers(s):
    start = s.index("材料一：")
    end = s.index("\n\n## 答案与解析", start)
    return s[start:end].rstrip()


class Round10ShenzhenReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.drafts = json.loads(DRAFTS.read_text(encoding="utf-8"))
        cls.receipts = [json.loads(line) for line in RECEIPT.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_six_authored_answers_and_exact_original_body(self):
        self.assertEqual(6, len(self.drafts))
        self.assertEqual(2, len(self.receipts))
        seen = set()
        papers = {}
        for r in self.receipts:
            relative = r["path"]
            self.assertNotIn(relative, seen)
            seen.add(relative)
            self.assertTrue(relative.startswith("省考/深圳/2025/申论-"))
            p = (ROOT / relative).resolve()
            self.assertTrue(p.is_relative_to(ROOT))
            text = p.read_text(encoding="utf-8")
            self.assertEqual(r["after_sha256"], checksum(text))
            original = body_before_answers(text)
            self.assertEqual(r["original_materials_and_task_body_sha256"], checksum(original))
            self.assertEqual(r["original_materials_and_task_body_length"], len(original))
            self.assertEqual(15, len(re.findall(r"^材料(?:[一二三四五六七八九十]|\d+)：", original, re.M)))
            self.assertIn("已收录参考答案题号: [1, 2, 3]", text)
            self.assertIn("缺参考答案题号: []", text)
            self.assertIn("其中 3 题已有可读取的参考版本", text)
            parsed = parser.parse(text, relative)
            self.assertEqual({1, 2, 3}, set(parsed["questions"]))
            self.assertEqual({1, 2, 3}, set(parsed["answers"]))
            self.assertEqual([], parsed["missing"])
            blocks = {int(n): block for n, block in DETAILS.findall(text)}
            self.assertEqual({1, 2, 3}, set(blocks))
            entries = [x for x in self.drafts if x["path"] == relative]
            self.assertEqual(3, len(entries))
            for entry in entries:
                n = entry["n"]
                self.assertIn(entry["answer"].strip(), blocks[n])
                self.assertIn("原创示范作答（AI辅助编写；非机构原文，未经实考评分）", blocks[n])
                self.assertIn(entry["source"], blocks[n])
                self.assertNotIn("实考高分证明", blocks[n])
                self.assertEqual(1, text.count('id="r7-reference-' + str(n) + '"'))
                size = len(re.sub(r"[\s*]", "", entry["answer"]))
                self.assertGreaterEqual(size, entry["min"])
                self.assertLessEqual(size, entry["max"])
                self.assertEqual("已收录", assess(parsed["questions"][n], parsed["answers"][n])["status"])
                self.assertEqual(size, next(a["chars"] for a in r["answers"] if a["number"] == n))
            papers[relative] = {"material": original.split("作答要求")[0], "questions": parsed["questions"], "answers": parsed["answers"]}
        a = papers["省考/深圳/2025/申论-一卷.md"]
        b = papers["省考/深圳/2025/申论-二卷.md"]
        self.assertEqual(a["material"], b["material"])
        self.assertEqual(parser.qkey(a["questions"][3]), parser.qkey(b["questions"][3]))
        self.assertEqual(a["answers"][3].split("> 写作依据：")[0], b["answers"][3].split("> 写作依据：")[0])

    def test_catalog_matches_both_updated_papers(self):
        expected = {r["path"]: r for r in self.receipts}
        hits = {}
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["path"] in expected:
                hits[row["path"]] = row
        self.assertEqual(expected.keys(), hits.keys())
        for path, r in expected.items():
            row = hits[path]
            self.assertEqual(r["after_sha256"], row["sha256"])
            self.assertEqual(3, row["answer_blocks"])
            self.assertTrue(row["has_answer_content"])
            self.assertEqual([], row["issues"])
            self.assertEqual([], row["missing_answer_numbers"])
            self.assertEqual(len((ROOT / path).read_bytes()), row["bytes"])

    def test_global_reference_coverage_is_actual(self):
        if (ROOT / "reports/SOURCED-SUPPLEMENT-20261013.jsonl").exists():
            import tempfile
            from unittest.mock import patch
            from verify_sourced_supplement_20261013 import historical_snapshot
            with tempfile.TemporaryDirectory(prefix="r10-before-source-") as tmp:
                historical_snapshot(ROOT, Path(tmp))
                with patch("r7_reference_audit.ROOT", Path(tmp)):
                    rows, bad, _, counts = audit()
        else:
            rows, bad, _, counts = audit()
        remaining = sum(n for key, n in counts.items() if key.endswith("/待补"))
        self.assertEqual(729, len(rows))
        self.assertEqual(9, len(bad))
        self.assertEqual(568, remaining)
        data = json.loads(SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(574, data["previous_missing_answers"])
        self.assertEqual(568, data["expected_missing_answers_after"])
        self.assertEqual(6, data["reference_positions_added"])


if __name__ == "__main__":
    unittest.main()
