# -*- coding: utf-8 -*-
"""Synthetic-fixture tests for tools/qa/fingerprint_shard_qa.py.

No real question text, image bytes or Owner data is used.  The fixture is
invented solely to exercise normalization, one-to-one mapping, image-SHA
resolution and the Q44 override.
"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "qa"))
import fingerprint_shard_qa as qa  # noqa: E402

IMG3 = b"synthetic-image-3"
IMG8A = b"synthetic-image-8a"
IMG8B = b"synthetic-image-8b"
SHA = lambda b: hashlib.sha256(b).hexdigest()

MD = """# synthetic

## 第 1 题
甲乙丙丁戊己庚辛
- **A**. 甲
- **B**. 乙
- **C**. 丙
- **D**. 丁

## 第 2 题
另一个题目内容
- **A**. 甲
- **B**. 乙
- **C**. 丙
- **D**. 丁

## 第 3 题
<img src="图片/测试/q3.png">

## 第 4 题
弱匹配题
- **A**. 甲
- **B**. 乙
- **C**. 丙
- **D**. 丁

## 第 7 题
切分不同题
- **A**. 甲
- **B**. 乙
- **C**. 丙
- **D**. 丁

## 第 8 题
图像冲突题
<img src="图片/测试/q8.png">

## 第 44 题
争议题
- **A**. 甲
- **B**. 乙
- **C**. 丙
- **D**. 丁
"""

IMAGES = {"图片/测试/q3.png": IMG3, "图片/测试/q8.png": IMG8A}


def loader(rel):
    return IMAGES.get(rel)


def repo():
    return qa.parse_repo_markdown(MD, loader)


def slot(n, cat, repo_n=None, image=None, score=None, content="x", option="y"):
    return {
        "sourceNumber": n,
        "repositoryNumber": repo_n,
        "category": cat,
        "imageSha": image or [],
        "contentHash": content,
        "optionHash": option,
        "optionCount": 4,
        "score": score,
        "answerStatus": "unverified_answer",
    }


def make_shard():
    r = repo()
    q1 = r[1]
    q44 = r[44]
    return {
        "sourceId": "synthetic",
        "label": "synthetic",
        "repoPaper": "synthetic.md",
        "questions": [
            slot(1, "normalized_equal", 1, content=q1["contentHash"], option=q1["optionHash"]),
            slot(2, "near", 2, score=0.9),
            slot(3, "ambiguous", None, image=[SHA(IMG3)]),
            slot(4, "weak", 4),
            slot(5, "source_stub"),
            slot(6, "repo_missing"),
            slot(7, "image_chunking_not_comparable", 7),
            slot(8, "image_unknown", 8, image=[SHA(IMG8B)]),
            slot(44, "normalized_equal", 44, content=q44["contentHash"], option=q44["optionHash"]),
        ],
    }


class TestFingerprintShardQA(unittest.TestCase):
    def test_normalization_and_fingerprint(self):
        self.assertEqual(qa.normalize_text("Ａ　Ｂ，C！"), "ABC")
        fp = qa.fingerprint("甲乙丙丁戊己庚辛", ["甲", "乙", "丙", "丁"])
        self.assertEqual(len(fp["contentHash"]), 64)
        self.assertEqual(len(fp["optionHash"]), 64)

    def test_parse_repo_image_sha(self):
        r = repo()
        self.assertEqual(r[3]["imageShas"], [SHA(IMG3)])
        self.assertEqual(r[8]["imageShas"], [SHA(IMG8A)])

    def test_unique_image_resolution(self):
        shard = make_shard()
        got = qa.resolve_by_image(shard["questions"], repo())
        self.assertEqual(got, {3: 3})

    def test_unique_image_requires_multiplicity_one(self):
        r = repo()
        r[9] = dict(r[3])  # duplicate image SHA on the repository side
        shard = make_shard()
        got = qa.resolve_by_image(shard["questions"], r)
        self.assertNotIn(3, got)

    def test_audit_statuses_and_q44(self):
        result = qa.audit(make_shard(), repo(), pr_mode=True)
        self.assertEqual(result["counts"], {"matched": 3, "needs_review": 4, "unknown": 2})
        by = {x["sourceNumber"]: x for x in result["rows"]}
        self.assertEqual(by[1]["status"], "matched")
        self.assertEqual(by[2]["basis"], "near_text")
        self.assertEqual(by[3]["status"], "matched")
        self.assertEqual(by[3]["basis"], "image_sha_unique")
        self.assertEqual(by[4]["status"], "needs_review")
        self.assertEqual(by[7]["status"], "needs_review")
        self.assertEqual(by[8]["basis"], "image_conflict")
        self.assertEqual(by[44]["basis"], "q44_source_dispute")
        self.assertTrue(result["oneToOne"])

    def test_duplicate_repository_number_breaks_one_to_one(self):
        shard = make_shard()
        shard["questions"][1]["repositoryNumber"] = 1  # duplicate target 1
        result = qa.audit(shard, repo(), pr_mode=True)
        self.assertFalse(result["oneToOne"])

    def test_report_has_no_question_text_or_image_bytes(self):
        result = qa.audit(make_shard(), repo(), pr_mode=True)
        text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("甲乙丙丁戊己庚辛", text)
        self.assertNotIn("synthetic-image", text)
        self.assertNotIn("base64", text)
        self.assertNotIn(".png", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
