"""E5NW：东北/西北十四卷十九处原创学习参考作答的回归测试。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from e5nw_manifest_patch import load_updates, run
from verify_e5nw_original_answers import LABEL, RECEIPT, UPDATES, verify

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "catalog/manifest.jsonl"


class E5NWOriginalContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = verify(ROOT)
        cls.receipts = [json.loads(line) for line in (ROOT / RECEIPT).read_text(encoding="utf-8").splitlines() if line.strip()]
        cls.updates = load_updates(ROOT / UPDATES)

    def test_fourteen_papers_nineteen_answers(self):
        self.assertEqual("passed", self.summary["status"])
        self.assertEqual(14, self.summary["modified_papers"])
        self.assertEqual(19, self.summary["new_authored_answers"])
        self.assertEqual(38, self.summary["preserved_existing_answers"])
        self.assertEqual(["内蒙古", "山西", "新疆", "甘肃", "陕西", "黑龙江"], self.summary["provinces"])

    def test_labels_and_boundaries(self):
        for row in self.receipts:
            text = (ROOT / row["path"]).read_text(encoding="utf-8")
            for item in row["added_answers"]:
                block = text.split('<summary>第 %d 题</summary>' % item["number"], 1)[1].split("</details>", 1)[0]
                self.assertIn(LABEL, block)
                self.assertIn("**作答思路与得分要点**", block)
                self.assertIn("写作依据：本卷给定材料", block)
                self.assertIn("非官方", block)
                self.assertIn("未经实考评分", block)
                self.assertNotIn("https://", block)
                self.assertNotIn("标准答案", block)
                self.assertNotIn("官方答案", block)
                self.assertNotIn("粉笔原解析", block.split(LABEL, 1)[1])

    def test_manifest_rows_reflect_delivery(self):
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
            self.assertIn("E5NW", row["source_validation"])
            self.assertIn("原创学习参考与解析不等同官方答案或粉笔原解析；未经实考评分", row["notes"])

    def test_manifest_patch_is_row_level_and_idempotent(self):
        u = self.updates[0]
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "manifest.jsonl"
            row = json.loads(next(l for l in MANIFEST.read_text(encoding="utf-8").splitlines()
                                  if json.loads(l)["path"] == u["path"]))
            row["sha256"] = u["expected_before_sha256"]
            row["bytes"] = 1
            row["missing_answer_numbers"] = [99]
            dummy1 = {"path": "省考/黑龙江/2016/申论-统考.md", "sha256": "a" * 64, "bytes": 1}
            dummy2 = {"path": "国考/2016/申论-地市级.md", "sha256": "b" * 64, "bytes": 2}
            before = [json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for x in (row, dummy1, dummy2)]
            tmp.write_text("\n".join(before) + "\n", encoding="utf-8")
            first = run(tmp, [u], True)
            during = tmp.read_text(encoding="utf-8").splitlines()
            second = run(tmp, [u], True)
            self.assertEqual(1, first["rows_to_update"])
            self.assertEqual(1, second["already_final"])
            self.assertEqual(0, second["rows_to_update"])
            self.assertNotEqual(before[0], during[0])
            self.assertEqual(before[1:], during[1:])
            merged = json.loads(during[0])
            for k, v in u["fields"].items():
                self.assertEqual(v, merged[k])

    def test_manifest_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "manifest.jsonl"
            lines = MANIFEST.read_text(encoding="utf-8").splitlines()
            target = self.updates[0]["path"]
            out = []
            for line in lines:
                row = json.loads(line)
                if row["path"] == target:
                    row["sha256"] = "0" * 64
                out.append(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                run(tmp, self.updates, False)


if __name__ == "__main__":
    unittest.main()
