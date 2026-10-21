"""Regression: the nine legacy AI answer sets (24 blocks) are gone from main.

The receipt records the exact pre-removal state; this test proves the delivered files are the
pre-AI versions, the manifest agrees, and no third-party answer was changed.
"""
import hashlib
import json
import re
import unittest
from pathlib import Path

import round5_bulk as parser
from round4_gap_repair import digest

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "reports/REMOVED-AI-CONTENT-LEGACY-20261022.json"
MANIFEST = ROOT / "catalog/manifest.jsonl"
AI_LABELS = ("原创示范作答", "AI辅助编写", "模型生成", "原创学习参考作答",
             "原创学习解析", "AI辅助整理")
DETAIL = re.compile(r"<summary>第\s*(\d+)\s*题</summary>(.*?)</details>", re.S)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def body(text):
    b = re.split(r"\n##\s*答案与解析\s*\n", text, maxsplit=1)[0]
    m = re.search(r"^(?:##\s*给定资料|材料[一1])", b, re.M)
    return (b[m.start():] if m else b).rstrip()


class RemovedLegacyAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.manifest = {}
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            cls.manifest[row["path"]] = row

    def test_nine_papers_twentyfour_blocks(self):
        self.assertEqual(9, len(self.rows))
        self.assertEqual(24, sum(len(r["removed_answer_numbers"]) for r in self.rows))

    def test_delivered_bytes_are_pre_ai(self):
        for row in self.rows:
            raw = (ROOT / row["path"]).read_bytes()
            text = raw.decode("utf-8")
            self.assertEqual(row["after_sha256"], sha(raw), row["path"])
            self.assertEqual(row["after_bytes"], len(raw), row["path"])
            self.assertEqual(row["body_sha256"], sha(body(text).encode("utf-8")), row["path"])
            for label in AI_LABELS:
                self.assertNotIn(label, text, row["path"])

    def test_preserved_answers_unchanged(self):
        for row in self.rows:
            text = (ROOT / row["path"]).read_text(encoding="utf-8")
            parsed = parser.parse(text, row["path"])
            for n, expected in row["preserved_answer_sha256"].items():
                self.assertEqual(expected, digest(parsed["answers"].get(int(n), "")),
                                 f'{row["path"]}:{n}')

    def test_manifest_matches_files_and_receipt(self):
        self.assertEqual(1243, len(self.manifest))
        self.assertEqual(1243, len({r["path"] for r in self.manifest.values()}))
        for row in self.rows:
            entry = self.manifest[row["path"]]
            for key in ("sha256", "bytes", "answer_blocks", "has_answer_content",
                        "missing_answer_numbers", "issues", "notes", "source_validation"):
                self.assertEqual(row["manifest_after"][key], entry[key], f'{row["path"]}:{key}')
        for row in self.manifest.values():
            raw = (ROOT / row["path"]).read_bytes()
            self.assertEqual(row["sha256"], sha(raw), row["path"])
            self.assertEqual(row["bytes"], len(raw), row["path"])

    def test_no_ai_artifacts_left(self):
        for rel in ("reports/ROUND8-ORIGINAL-ANSWERS-20261013.jsonl",
                    "reports/ROUND9-ORIGINAL-ANSWERS-20261013.jsonl",
                    "reports/ROUND10-ORIGINAL-ANSWERS-20261013.jsonl",
                    "tools/verify_round8_reference.py",
                    "tools/verify_round9_reference.py",
                    "tools/verify_round10_reference.py",
                    "tools/tests/test_round10_shenzhen.py"):
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_no_ai_labels_remain_in_corpus(self):
        found = []
        for top in ("国考", "省考"):
            for p in (ROOT / top).rglob("*.md"):
                text = p.read_text(encoding="utf-8")
                if any(label in text for label in AI_LABELS):
                    found.append(p.relative_to(ROOT).as_posix())
        self.assertEqual([], found)

    def test_fenbi_shenlun_38_and_total_1243(self):
        papers = [p for top in ("国考", "省考") for p in (ROOT / top).rglob("*.md")]
        self.assertEqual(1243, len(papers))
        fenbi = 0
        for p in papers:
            if "申论" not in p.name:
                continue
            head = p.read_text(encoding="utf-8")[:4000]
            if "spa.fenbi.com" in head or "源试卷ID" in head or "fenbi" in head.lower():
                fenbi += 1
        self.assertEqual(38, fenbi)


if __name__ == "__main__":
    unittest.main()
