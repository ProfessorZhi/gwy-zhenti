# -*- coding: utf-8 -*-
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from gwyzhenti import export


def _mk(up, rows, body='{"t":"单一题","s":"材料","q":"题干","a":"","e":"范文","source":"x"}'):
    """建一个最小上游：gongkao-tiku/data/shengkao-shenlun/y2019.json + xingcezhenti/。

    注：`body` 默认值在原稿里写成 `b'...'`，但其中的非 ASCII 字面量在 Python 3 下是
    SyntaxError（`bytes can only contain ASCII literal characters`）。改为 str 默认值，
    `json.loads` 对 str/bytes 皆可，行为不变。
    """
    d = os.path.join(up, "gongkao-tiku", "data", "shengkao-shenlun")
    os.makedirs(d)
    q = json.loads(body)
    with io.open(os.path.join(d, "y2019.json"), "w", encoding="utf-8") as fh:
        json.dump({r["titles"]["linfukai186"][0]: [q] if r["n_questions"] else [] for r in rows},
                  fh, ensure_ascii=False)
    os.makedirs(os.path.join(up, "xingcezhenti"))
    cat = os.path.join(up, "catalog")
    os.makedirs(cat)
    with io.open(os.path.join(cat, "catalog.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return cat


def _row(year="2019", n=1, slug="省考-山东-2019-申论-统考", title="2019·山东省公考《申论》题"):
    return {"slug": slug, "level": "省考", "region": "山东", "year": year, "subject": "申论",
            "ptype": "统考", "nature": "正式真题", "form": "单独命题",
            "sources": ["linfukai186"], "n_questions": n,
            "titles": {"linfukai186": [title]}}


def _uproots(up):
    """与 `cli._uproots` 同形：只此两键。"""
    return {"xingcezhenti": os.path.join(up, "xingcezhenti"),
            "linfukai186": os.path.join(up, "gongkao-tiku")}


class TestExportShenlun(unittest.TestCase):
    def test_writes_md_and_manifest(self):
        with tempfile.TemporaryDirectory() as up, tempfile.TemporaryDirectory() as repo:
            cat = _mk(up, [_row()])
            rep = export.run(cat, _uproots(up), repo, since="2016")
            md = os.path.join(repo, "省考", "山东", "2019", "申论-统考.md")
            self.assertTrue(os.path.exists(md))
            self.assertEqual(rep.files, 1)
            text = io.open(md, encoding="utf-8").read()
            self.assertIn("## 第 1 题（单一题）", text)
            man = os.path.join(repo, "work", "manifest.jsonl")
            self.assertTrue(os.path.exists(man))
            self.assertEqual(len([l for l in io.open(man, encoding="utf-8") if l.strip()]), 1)

    def test_since_filters_old_shenlun(self):
        with tempfile.TemporaryDirectory() as up, tempfile.TemporaryDirectory() as repo:
            cat = _mk(up, [_row(year="2015", slug="省考-北京-2015-申论-统考",
                                title="2015·北京市公考")])
            rep = export.run(cat, _uproots(up), repo, since="2016")
            self.assertEqual(rep.files, 0)
            self.assertTrue(any("since" in s.get("reason", "") for s in rep.skipped))

    def test_exportable_map_counts_shenlun(self):
        with tempfile.TemporaryDirectory() as up:
            cat = _mk(up, [_row(), _row(year="2015", slug="省考-北京-2015-申论-统考",
                                        title="2015·北京市公考")])
            m = export.exportable_map(export.load_catalog(cat), _uproots(up))
            self.assertEqual(m["省考-山东-2019-申论-统考"], True)
            self.assertEqual(len(m), 2)

    def test_idempotent_sha(self):
        with tempfile.TemporaryDirectory() as up, tempfile.TemporaryDirectory() as repo:
            cat = _mk(up, [_row()])
            export.run(cat, _uproots(up), repo, since="2016")
            md = os.path.join(repo, "省考", "山东", "2019", "申论-统考.md")
            a = open(md, "rb").read()
            export.run(cat, _uproots(up), repo, since="2016")
            self.assertEqual(a, open(md, "rb").read())


class TestWritePermissionFallback(unittest.TestCase):
    """`_write` 的文件锁兜底（评审 Important）：它是本任务唯一的写路径，必须有覆盖。

    判据必须**能红**：把 `export.py` 里那句守卫的 `not (...)` 去掉，下面第 2、3 条就会失败。
    """

    def _call(self, path, data):
        with mock.patch("os.replace", side_effect=PermissionError):
            export._write(path, data)

    def test_identical_destination_skips_without_raising(self):
        """目标被占用、但盘上字节与新字节完全相同 ⇒ 跳过替换、不抛、不留 .tmp。"""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "wb") as fh:
                fh.write(b"same")
            self._call(p, b"same")
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), b"same")
            self.assertFalse(os.path.exists(p + ".tmp"))

    def test_differing_destination_reraises(self):
        """目标被占用、盘上字节不同 ⇒ **必须抛出**，绝不静默丢内容。"""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "wb") as fh:
                fh.write(b"old")
            with self.assertRaises(PermissionError):
                self._call(p, b"new")
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), b"old")

    def test_missing_destination_reraises(self):
        """目标根本不存在 ⇒ **必须抛出**（不能把「该写却没写成」吞掉）。"""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with self.assertRaises(PermissionError):
                self._call(p, b"new")


if __name__ == "__main__":
    unittest.main()
