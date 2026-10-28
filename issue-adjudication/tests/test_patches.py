"""Tests for the adjudication patches.

Run:  python3 -I -m unittest discover -s tests -v
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN = "/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main"
PR140 = "/home/fjd/scratch/gwy-format-final-20261028/structure/reading-sample/repo-pr140"
WORK = os.path.join(ROOT, "work")
PATCHES = os.path.join(ROOT, "patches")

PATCH_OF = {
    "省考/上海/2017/行测-统考.md": "0001-shanghai2017-hr-and-dup-jiexi.patch",
    "省考/广东/2016/行测-广州市考.md": "0002-guangzhou2016xingce-drop-hr.patch",
    "省考/江苏/2024/行测-C类.md": "0003-jiangsu2024c-drop-hr.patch",
    "省考/北京/2026/申论-选调生.md": "0004-beijing2026-stray-u-close.patch",
    "省考/青海/2014/行测-统考.md": "0005-qinghai2014-pipe-math.patch",
}


def read(base, path):
    with open(os.path.join(base, path), "rb") as fh:
        return fh.read().decode("utf-8")


def split_details(text):
    out, blocks, pos = [], [], 0
    for m in re.finditer(r"<details\b[^>]*>(.*?)</details>", text, re.S):
        out.append(text[pos:m.start()]); blocks.append(m.group(1)); pos = m.end()
    out.append(text[pos:])
    return "".join(out), blocks


def answer_part(block):
    inner = re.sub(r"<summary\b[^>]*>.*?</summary>", "", block, flags=re.S)
    m = re.search(r"\*\*(?:官方)?解析\*\*", inner)
    return inner[: m.start()] if m else inner


class PatchApplies(unittest.TestCase):
    def test_each_patch_applies_to_main_and_matches_work(self):
        for path, name in PATCH_OF.items():
            with self.subTest(path=path):
                tmp = tempfile.mkdtemp()
                try:
                    dst = os.path.join(tmp, path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(os.path.join(MAIN, path), dst)
                    res = subprocess.run(
                        ["patch", "-p1", "-s", "-d", tmp, "-i", os.path.join(PATCHES, name)],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(res.returncode, 0, res.stderr)
                    self.assertEqual(open(dst, encoding="utf-8").read(), read(WORK, path))
                finally:
                    shutil.rmtree(tmp)


class TextInvariants(unittest.TestCase):
    def test_no_question_option_material_or_answer_text_changes(self):
        for path in PATCH_OF:
            with self.subTest(path=path):
                before = read(MAIN, path)
                after = read(WORK, path)
                ob, bb = split_details(before)
                oa, ba = split_details(after)
                self.assertEqual(ob, oa, "text outside <details> changed")
                self.assertEqual([answer_part(x) for x in bb], [answer_part(x) for x in ba], "answer changed")
                self.assertEqual(len(bb), len(ba))

    EXPECTED_RULES = {
        "省考/上海/2017/行测-统考.md": 136,
        "省考/广东/2016/行测-广州市考.md": 100,
        "省考/江苏/2024/行测-C类.md": 129,
        "省考/北京/2026/申论-选调生.md": 0,
        "省考/青海/2014/行测-统考.md": 0,
    }

    def test_only_thematic_rules_and_dup_label_removed(self):
        for path, expected in self.EXPECTED_RULES.items():
            before = read(MAIN, path)
            after = read(WORK, path)
            removed = len([l for l in before.split("\n") if l.strip() == "---"]) - len(
                [l for l in after.split("\n") if l.strip() == "---"]
            )
            self.assertEqual(removed, expected, path)

    def test_headings_and_frontmatter_untouched(self):
        for path in PATCH_OF:
            b = read(MAIN, path).split("\n")
            a = read(WORK, path).split("\n")
            hb = [l for l in b if l.startswith("#")]
            ha = [l for l in a if l.startswith("#")]
            self.assertEqual(hb, ha, path)
            fb = b.index("---", 1)
            self.assertEqual(b[: fb + 1], a[: fb + 1], path)


class Pr140Mirrors(unittest.TestCase):
    def test_mirror_files_equal_pr140(self):
        for path in ("省考/北京/2026/申论-选调生.md", "省考/青海/2014/行测-统考.md"):
            with self.subTest(path=path):
                self.assertEqual(read(WORK, path), read(PR140, path))

    def test_static_checker_drops_the_only_error(self):
        sys.path.insert(0, os.path.join(ROOT, "..", "src"))
        from gwy_format.checker import check_paper
        path = "省考/北京/2026/申论-选调生.md"
        with open(os.path.join(MAIN, path), "rb") as fh:
            before = check_paper(path, fh.read(), set())
        with open(os.path.join(WORK, path), "rb") as fh:
            after = check_paper(path, fh.read(), set())
        self.assertEqual(before.counts()["error"], 1)
        self.assertEqual(after.counts()["error"], 0)


class CaseFile(unittest.TestCase):
    def test_11_cases_with_known_verdicts(self):
        import json
        rows = [json.loads(l) for l in open(os.path.join(ROOT, "11-case.jsonl"), encoding="utf-8")]
        self.assertEqual(len(rows), 11)
        allowed = {"VERIFIED_FORMAT_ERROR", "VERIFIED_CONTENT_IDENTITY_ISSUE", "ALREADY_FIXED_IN_PR140",
                   "SOURCE_EXCEPTION", "FALSE_POSITIVE", "NEEDS_ORIGINAL_IMAGE"}
        for r in rows:
            self.assertIn(r["verdict"], allowed)
            self.assertTrue(r["md_sha256"])
            self.assertTrue(r["evidence"])
        by = {r["case"]: r for r in rows}
        self.assertEqual(by[18]["verdict"], "ALREADY_FIXED_IN_PR140")
        self.assertEqual(by[88]["verdict"], "ALREADY_FIXED_IN_PR140")
        self.assertEqual(by[60]["verdict"], "VERIFIED_CONTENT_IDENTITY_ISSUE")


if __name__ == "__main__":
    unittest.main()
