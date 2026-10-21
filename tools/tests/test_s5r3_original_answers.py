"""S5R3：五卷八处原创答案、六处原创解析的回归测试。"""
import json
import unittest
from pathlib import Path

from verify_s5r3_original_answers import EXPL, LABEL, RECEIPT, verify

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "catalog/manifest.jsonl"


class S5R3OriginalContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = verify(ROOT)
        cls.receipts = [json.loads(line) for line in (ROOT / RECEIPT).read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_five_papers(self):
        self.assertEqual("passed", self.summary["status"])
        self.assertEqual(5, self.summary["modified_papers"])
        self.assertEqual(8, self.summary["new_authored_answers"])
        self.assertEqual(6, self.summary["new_original_explanations"])
        self.assertEqual(12, self.summary["preserved_existing_answers"])

    def test_labels_and_boundaries(self):
        for row in self.receipts:
            text = (ROOT / row["path"]).read_text(encoding="utf-8")
            for item in row["added_answers"]:
                block = text.split('<summary>第 %d 题</summary>' % item["number"], 1)[1].split("</details>", 1)[0]
                self.assertIn(LABEL, block)
                self.assertIn("**作答思路与得分要点**", block)
                self.assertIn("写作依据：本卷给定材料", block)
                self.assertNotIn("https://", block)
            for item in row["added_explanations"]:
                block = text.split('<summary>第 %d 题</summary>' % item["number"], 1)[1].split("</details>", 1)[0]
                self.assertIn(EXPL, block)
                self.assertIn("不是原答案附带的机构解析", block)

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
            self.assertEqual([], row["missing_answer_numbers"])

    def test_no_new_paper_files(self):
        self.assertEqual(1572, len([p for top in ("国考", "省考") for p in (ROOT / top).rglob("*.md")]))


if __name__ == "__main__":
    unittest.main()
