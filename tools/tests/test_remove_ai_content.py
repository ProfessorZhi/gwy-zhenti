"""Regression: the 25 LLM-authored answers and 6 LLM explanations are gone from main.

The receipt records the exact pre-removal state; this test proves the delivered files are the
pre-AI versions, the manifest agrees, and no third-party answer was changed.
"""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "reports/REMOVED-AI-CONTENT-20261022.json"
MANIFEST = ROOT / "catalog/manifest.jsonl"
AI_LABELS = ("原创学习参考作答", "原创学习解析，非原参考答案说明", "原创示范作答",
             "AI辅助编写", "模型生成", "S5R2", "S5R3")
LEGACY_AI_FILES = {
    "省考/江苏/2026/申论-B类.md",
    "省考/浙江/2026/申论-C类.md",
    "省考/浙江/2026/申论-A类.md",
    "省考/浙江/2025/申论-A类.md",
    "省考/上海/2019/申论-行政执法卷.md",
    "省考/深圳/2025/申论-二卷.md",
    "省考/深圳/2025/申论-一卷.md",
    "省考/安徽/2026/申论-A类.md",
    "省考/重庆/2024/申论-一卷.md",
}
DETAIL = re.compile(r"<summary>第\s*(\d+)\s*题</summary>(.*?)</details>", re.S)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def body(text):
    b = re.split(r"\n##\s*答案与解析\s*\n", text, maxsplit=1)[0]
    m = re.search(r"^材料[一1]", b, re.M)
    return (b[m.start():] if m else b).rstrip()


class RemovedAIContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.manifest = {}
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            cls.manifest[row["path"]] = row

    def test_twentyfive_answers_and_six_explanations_removed(self):
        self.assertEqual(14, len(self.rows))
        self.assertEqual(25, sum(len(r["removed_answer_numbers"]) for r in self.rows))
        self.assertEqual(6, sum(len(r["removed_explanation_numbers"]) for r in self.rows))

    def test_delivered_bytes_are_pre_ai(self):
        for row in self.rows:
            path = ROOT / row["path"]
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            self.assertEqual(row["after_sha256"], sha(raw), row["path"])
            self.assertEqual(row["after_bytes"], len(raw), row["path"])
            self.assertEqual(row["body_sha256"], sha(body(text).encode("utf-8")), row["path"])
            for label in AI_LABELS:
                self.assertNotIn(label, text, row["path"])
            for n in row["removed_answer_numbers"]:
                block = dict((int(k), v) for k, v in DETAIL.findall(text)).get(n, "")
                self.assertNotIn("原创学习参考作答", block, f'{row["path"]}:{n}')
            for n in row["removed_explanation_numbers"]:
                block = dict((int(k), v) for k, v in DETAIL.findall(text)).get(n, "")
                self.assertNotIn("原创学习解析", block, f'{row["path"]}:{n}')

    def test_preserved_answers_unchanged(self):
        for row in self.rows:
            text = (ROOT / row["path"]).read_text(encoding="utf-8")
            blocks = {int(k): v for k, v in DETAIL.findall(text)}
            for n, expected in row["preserved_answer_sha256"].items():
                self.assertEqual(expected, sha(re.sub(r"\s", "", blocks[int(n)]).encode("utf-8")),
                                 f'{row["path"]}:{n}')

    def test_manifest_matches_files_and_receipt(self):
        paths = [r["path"] for r in self.rows]
        self.assertEqual(len(paths), len(set(paths)))
        for row in self.rows:
            entry = self.manifest[row["path"]]
            for key in ("sha256", "bytes", "answer_blocks", "has_answer_content",
                        "missing_answer_numbers", "issues", "notes", "source_validation"):
                self.assertEqual(row["manifest_after"][key], entry[key], f'{row["path"]}:{key}')

    def test_no_ai_artifacts_left(self):
        for rel in ("reports/S5-ORIGINAL-ANSWERS-20261021.jsonl",
                    "reports/S5R2-ORIGINAL-ANSWERS-20261021.jsonl",
                    "reports/S5R3-ORIGINAL-ANSWERS-20261021.jsonl",
                    "tools/verify_s5_original_answers.py",
                    "tools/verify_s5r2_original_answers.py",
                    "tools/verify_s5r3_original_answers.py",
                    "tools/tests/test_s5_original_answers.py",
                    "tools/tests/test_s5r2_original_answers.py",
                    "tools/tests/test_s5r3_original_answers.py"):
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_other_ai_labeled_files_are_only_the_known_legacy_set(self):
        found = set()
        for top in ("国考", "省考"):
            for p in (ROOT / top).rglob("*.md"):
                text = p.read_text(encoding="utf-8")
                if any(label in text for label in AI_LABELS):
                    found.add(p.relative_to(ROOT).as_posix())
        self.assertEqual(LEGACY_AI_FILES, found)


if __name__ == "__main__":
    unittest.main()
