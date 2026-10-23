"""Regression: no AI-authored answers, analyses or labels are left in the corpus.

This module was rebuilt on 2026-10-23 from two near-identical files
(``test_remove_ai_content.py`` / ``test_remove_legacy_ai.py``). The old versions pinned the
byte-level snapshot of the two 2026-10-22 receipts (``after_sha256`` / ``body_sha256`` /
``preserved_answer_sha256``) plus absolute corpus sizes (1,291 papers, 130 fenbi essays).
Commit 04e756aa ("全仓排版, 1,422 卷, 答案随题折叠") reformatted every paper and grew the
corpus, so those assertions could only ever pass on their own commit — a permanent red in
main CI that reported the same defect twice.

The split is now:

* This module (main CI, must stay green forever) keeps the invariants that do not depend on
  when the tree was taken:
    - no AI label anywhere under 国考/省考 (the real safety net);
    - the AI receipt/verifier artefacts stay deleted;
    - catalog/manifest.jsonl, the paper files on disk and the two receipts agree:
      one manifest row per paper file, unique paths, and every row's sha256/bytes equal to
      the bytes actually on disk, with receipt-covered papers a subset of the manifest.
  There are deliberately **no absolute corpus counts**: the corpus grew 1,243 -> 1,422 in
  one day, so a hard-coded number is a timer, not a test. What must not drift is the
  relation between the three sources, so that is what is asserted.
* ``tools/verify_ai_removal_receipts.py`` (opt-in, time-pinned) keeps the byte-level
  receipt snapshot. It passes only on the tree of commit de8832f57; run it by hand with
  ``python tools/verify_ai_removal_receipts.py`` or from the ``ai_receipt_audit``
  workflow_dispatch input.
"""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPTS = (ROOT / "reports/REMOVED-AI-CONTENT-20261022.json",
            ROOT / "reports/REMOVED-AI-CONTENT-LEGACY-20261022.json")
MANIFEST = ROOT / "catalog/manifest.jsonl"
CORPUS_ROOTS = ("国考", "省考")
# Union of both former label lists. "原创学习解析" also covers the longer
# "原创学习解析，非原参考答案说明" variant, and the S5R2/S5R3 round tags covered the
# 2026-10-21 answer batches.
AI_LABELS = ("原创学习参考作答", "原创学习解析", "原创示范作答", "AI辅助编写",
             "模型生成", "AI辅助整理", "S5R2", "S5R3")
# Receipts, drafts, verifiers and tests of the three AI-answer rounds. All of them were
# deleted together with the content they described; their reappearance is a regression.
REMOVED_ARTIFACTS = (
    "reports/S5-ORIGINAL-ANSWERS-20261021.jsonl",
    "reports/S5R2-ORIGINAL-ANSWERS-20261021.jsonl",
    "reports/S5R3-ORIGINAL-ANSWERS-20261021.jsonl",
    "reports/ROUND8-ORIGINAL-ANSWERS-20261013.jsonl",
    "reports/ROUND9-ORIGINAL-ANSWERS-20261013.jsonl",
    "reports/ROUND10-ORIGINAL-ANSWERS-20261013.jsonl",
    "tools/verify_s5_original_answers.py",
    "tools/verify_s5r2_original_answers.py",
    "tools/verify_s5r3_original_answers.py",
    "tools/verify_round8_reference.py",
    "tools/verify_round9_reference.py",
    "tools/verify_round10_reference.py",
    "tools/tests/test_s5_original_answers.py",
    "tools/tests/test_s5r2_original_answers.py",
    "tools/tests/test_s5r3_original_answers.py",
    "tools/tests/test_round10_shenzhen.py",
)


def sha(b):
    return hashlib.sha256(b).hexdigest()


class RemovedAIContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [row for receipt in RECEIPTS
                    for row in json.loads(receipt.read_text(encoding="utf-8"))]
        cls.manifest = {}
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                cls.manifest[row["path"]] = row
        cls.disk = {p.relative_to(ROOT).as_posix()
                    for top in CORPUS_ROOTS for p in (ROOT / top).rglob("*.md")}

    def test_no_ai_labels_remain_in_corpus(self):
        found = []
        for rel in sorted(self.disk):
            text = (ROOT / rel).read_text(encoding="utf-8")
            if any(label in text for label in AI_LABELS):
                found.append(rel)
        self.assertEqual([], found)

    def test_no_ai_artifacts_left(self):
        self.assertEqual([], [rel for rel in REMOVED_ARTIFACTS if (ROOT / rel).exists()])

    def test_delivered_files_carry_no_ai_labels(self):
        # Both receipts claim these papers were reverted to their pre-AI bytes. A label
        # coming back would mean an AI block was re-applied after the revert.
        for rel in sorted({row["path"] for row in self.rows}):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for label in AI_LABELS:
                self.assertNotIn(label, text, rel)

    def test_manifest_matches_disk_and_receipt_coverage(self):
        # Three sources, one relation: manifest rows == paper files on disk, and every
        # receipt paper is still shipped. Counts are taken from the tree, never hard-coded.
        manifest_paths = [row["path"] for row in self.manifest.values()]
        self.assertEqual(len(manifest_paths), len(set(manifest_paths)),
                         "duplicate path in catalog/manifest.jsonl")
        self.assertEqual(self.disk, set(manifest_paths),
                         "manifest and the .md files under 国考/省考 disagree")
        receipt_paths = {row["path"] for row in self.rows}
        self.assertLessEqual(receipt_paths, set(manifest_paths),
                             "a receipt paper is missing from the manifest")
        for rel in sorted(self.disk):
            entry = self.manifest[rel]
            raw = (ROOT / rel).read_bytes()
            self.assertEqual(entry["sha256"], sha(raw), rel)
            self.assertEqual(entry["bytes"], len(raw), rel)


if __name__ == "__main__":
    unittest.main()
