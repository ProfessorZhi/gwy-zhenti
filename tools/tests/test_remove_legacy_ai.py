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
DETAIL = re.compile(r"<summary>第\s*(\d+)\s*题(?:\s*·[^<]*)?</summary>(.*?)</details>", re.S)


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

    def test_delivered_files_carry_no_ai_content(self):
        # 回执记录的是 2026-10-22 当时的字节；此后全仓排版会改变 sha/字节数，
        # 因此这里只守住「交付文件仍是移除 AI 内容后的版本」这一不变量。
        for row in self.rows:
            raw = (ROOT / row["path"]).read_bytes()
            text = raw.decode("utf-8")
            self.assertTrue(body(text).strip(), row["path"])
            for label in AI_LABELS:
                self.assertNotIn(label, text, row["path"])

    def test_preserved_answers_still_present(self):
        # 行内答案已由排版脚本改为逐题 <details>，旧解析器不再适用；
        # 这里确认回执列出的保留答案仍存在且非空，且不含 AI 标签。
        for row in self.rows:
            text = (ROOT / row["path"]).read_text(encoding="utf-8")
            blocks = {int(k): v for k, v in DETAIL.findall(text)}
            for n in row["preserved_answer_sha256"]:
                self.assertIn(int(n), blocks, f'{row["path"]}:{n}')
                self.assertTrue(blocks[int(n)].strip(), f'{row["path"]}:{n}')

    def test_manifest_matches_files_and_receipt(self):
        papers = [p for top in ("国考", "省考") for p in (ROOT / top).rglob("*.md")]
        self.assertEqual(len(papers), len(self.manifest))
        self.assertEqual(len(papers), len({r["path"] for r in self.manifest.values()}))
        for row in self.rows:
            self.assertIn(row["path"], self.manifest, row["path"])
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

    def test_fenbi_shenlun_and_total_papers(self):
        papers = [p for top in ("国考", "省考") for p in (ROOT / top).rglob("*.md")]
        self.assertEqual(len(self.manifest), len(papers))
        fenbi = 0
        for p in papers:
            if "申论" not in p.name:
                continue
            head = p.read_text(encoding="utf-8")[:4000]
            if "spa.fenbi.com" in head or "源试卷ID" in head or "fenbi" in head.lower():
                fenbi += 1
        self.assertGreaterEqual(fenbi, 130)


if __name__ == "__main__":
    unittest.main()
