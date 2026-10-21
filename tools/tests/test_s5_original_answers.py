"""S5：三卷六处原创学习参考交付的回归测试。"""
import json
import unittest
from pathlib import Path

from verify_s5_original_answers import LABEL, RECEIPT, verify

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "catalog/manifest.jsonl"


class S5OriginalAnswers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = verify(ROOT)
        cls.receipts = [json.loads(line) for line in (ROOT / RECEIPT).read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_three_papers_six_answers(self):
        self.assertEqual("passed", self.summary["status"])
        self.assertEqual(3, self.summary["modified_papers"])
        self.assertEqual(6, self.summary["new_authored_answers"])
        self.assertEqual(2, self.summary["preserved_existing_answers"])

    def test_each_added_answer_is_labelled_and_grounded(self):
        for row in self.receipts:
            text = (ROOT / row["path"]).read_text(encoding="utf-8")
            for item in row["added_answers"]:
                block = text.split('<summary>第 %d 题</summary>' % item["number"], 1)[1].split("</details>", 1)[0]
                self.assertIn(LABEL, block)
                self.assertIn("**作答思路与得分要点**", block)
                self.assertIn("写作依据：本卷给定材料", block)
                self.assertNotIn("http://", block)
                self.assertNotIn("https://", block)
                self.assertNotIn("粉笔原解析", block.replace("非粉笔原解析", ""))

    def test_manifest_reflects_delivery(self):
        rows = {}
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["path"] in {r["path"] for r in self.receipts}:
                rows[row["path"]] = row
        self.assertEqual({r["path"] for r in self.receipts}, set(rows))
        for receipt in self.receipts:
            row = rows[receipt["path"]]
            self.assertEqual(receipt["after_sha256"], row["sha256"])
            self.assertEqual(len((ROOT / receipt["path"]).read_bytes()), row["bytes"])
            self.assertEqual(len(receipt["added_answers"]) + len(receipt["preserved_answers"]), row["answer_blocks"])
            self.assertTrue(row["has_answer_content"])
            self.assertEqual(receipt["remaining_answer_ids"], row["missing_answer_numbers"] or [])

    def test_no_new_paper_files(self):
        paper_files = [p for top in ("国考", "省考") for p in (ROOT / top).rglob("*.md")]
        self.assertEqual(1572, len(paper_files))


if __name__ == "__main__":
    unittest.main()
