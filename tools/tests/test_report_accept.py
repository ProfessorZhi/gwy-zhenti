# -*- coding: utf-8 -*-
"""accept-1：验收 / 发布分级账的可红测试（最小库风格，参照 test_gates.py）。"""
import hashlib
import io
import json
import os
import tempfile
import unittest

from gwyzhenti import export, report_accept
from gwyzhenti.model import PaperKey

REQ_EMPTY = "请根据给定资料，谈谈你的看法。\n要求："
REQ_FULL = "请根据给定资料，谈谈你的看法。\n要求：不超过500字。"


def _row(subject="申论", level="省考", region="山东", year="2019", ptype="统考",
         slug="省考-山东-2019-申论-统考", title="2019·山东省公考《申论》题", n=1):
    return {"slug": slug, "level": level, "region": region, "year": year, "subject": subject,
            "ptype": ptype, "nature": "正式真题", "form": "单独命题",
            "sources": ["linfukai186"], "n_questions": n,
            "titles": {"linfukai186": [title]}}


def _q(q=REQ_FULL, s="材料"):
    return {"t": "单一题", "s": s, "q": q, "a": "", "e": "范文", "source": "x"}


def _src(title, qs):
    return {title: qs}


def _write_md(repo_root, md_rel, data):
    p = os.path.join(repo_root, md_rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data)
    return p


class TestEmptyRequirement(unittest.TestCase):
    def _grade(self, q_text):
        row = _row()
        src = _src(row["titles"]["linfukai186"][0], [_q(q=q_text)])
        with tempfile.TemporaryDirectory() as d:
            rec = report_accept.grade_row(row, src, {}, {}, set(), d)
        return rec

    def test_ends_with_yaoqiu_colon_is_empty(self):
        # q 止于「要求：」⇒ 空要求计 1
        self.assertEqual(self._grade(REQ_EMPTY)["empty_requirement"], 1)

    def test_ends_with_full_sentence_is_not_empty(self):
        # q 止于「要求：不超过500字。」⇒ 不是空要求
        self.assertEqual(self._grade(REQ_FULL)["empty_requirement"], 0)

    def test_halfwidth_colon_also_counts(self):
        self.assertEqual(self._grade("谈谈你的看法。\n要求:")["empty_requirement"], 1)


class TestT2Manifest(unittest.TestCase):
    def _grade(self, manifest):
        row = _row()
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        md_rel, _ = export.repo_paths(key, row["slug"])
        with tempfile.TemporaryDirectory() as d:
            _write_md(d, md_rel, "# 卷\n".encode("utf-8"))
            return report_accept.grade_row(row, {}, manifest, {}, set(), d)

    def test_missing_manifest_entry_is_false(self):
        self.assertFalse(self._grade({}) ["t2_幂等一致"])

    def test_sha_mismatch_is_false(self):
        row = _row()
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        md_rel, _ = export.repo_paths(key, row["slug"])
        self.assertFalse(self._grade({md_rel: "0" * 64})["t2_幂等一致"])

    def test_sha_match_is_true(self):
        row = _row()
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        md_rel, _ = export.repo_paths(key, row["slug"])
        sha = hashlib.sha256("# 卷\n".encode("utf-8")).hexdigest()
        self.assertTrue(self._grade({md_rel: sha})["t2_幂等一致"])

    def test_missing_md_is_false(self):
        # t1 不存在 ⇒ t2 恒 False（即便 manifest 有同名条目）
        row = _row()
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        md_rel, _ = export.repo_paths(key, row["slug"])
        with tempfile.TemporaryDirectory() as d:
            rec = report_accept.grade_row(row, {}, {md_rel: "0" * 64}, {}, set(), d)
        self.assertFalse(rec["t1_已转写"])
        self.assertFalse(rec["t2_幂等一致"])


class TestT4T5Verify(unittest.TestCase):
    def test_missing_records_file_is_all_false_and_does_not_raise(self):
        row = _row()
        with tempfile.TemporaryDirectory() as d:
            verify = report_accept.load_verify(d)      # 文件不存在 ⇒ {}（不抛）
            self.assertEqual(verify, {})
            rec = report_accept.grade_row(row, {}, {}, verify, set(), d)
        self.assertFalse(rec["t4_原卷核验"])
        self.assertFalse(rec["t5_人工通读"])

    def _with_records(self, records):
        row = _row()
        with tempfile.TemporaryDirectory() as d:
            vd = os.path.join(d, "work", "verify")
            os.makedirs(vd)
            with io.open(os.path.join(vd, "records.jsonl"), "w",
                         encoding="utf-8", newline="\n") as fh:
                for r in records:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            verify = report_accept.load_verify(d)
            return report_accept.grade_row(row, {}, {}, verify, set(), d)

    def test_verdict_ok_sets_t4(self):
        rec = self._with_records([{"slug": "省考-山东-2019-申论-统考", "verdict": "ok"}])
        self.assertTrue(rec["t4_原卷核验"])
        self.assertFalse(rec["t5_人工通读"])   # 未声明 human_read

    def test_human_read_true_sets_t5(self):
        rec = self._with_records([{"slug": "省考-山东-2019-申论-统考", "verdict": "ok",
                                   "human_read": True}])
        self.assertTrue(rec["t4_原卷核验"])
        self.assertTrue(rec["t5_人工通读"])

    def test_non_ok_verdict_is_false(self):
        rec = self._with_records([{"slug": "省考-山东-2019-申论-统考", "verdict": "bad"}])
        self.assertFalse(rec["t4_原卷核验"])


class TestFormSuspect(unittest.TestCase):
    def test_multi_xingce_single_shenlun_is_suspect(self):
        rows = [
            _row(subject="行测", ptype="A类", slug="s-行测-A", title="t-a"),
            _row(subject="行测", ptype="B类", slug="s-行测-B", title="t-b"),
            _row(subject="申论", ptype="统考", slug="s-申论", title="t-c"),
        ]
        s = report_accept.suspect_groups(rows)
        self.assertIn(("省考", "山东", "2019"), s)

    def test_two_shenlun_types_is_not_suspect(self):
        rows = [
            _row(subject="行测", ptype="A类", slug="s-行测-A", title="t-a"),
            _row(subject="行测", ptype="B类", slug="s-行测-B", title="t-b"),
            _row(subject="申论", ptype="A类", slug="s-申论-A", title="t-c"),
            _row(subject="申论", ptype="B类", slug="s-申论-B", title="t-d"),
        ]
        self.assertEqual(report_accept.suspect_groups(rows), {})

    def test_grade_row_marks_form_suspect(self):
        row = _row(subject="申论", ptype="统考", slug="s-申论", title="t-c")
        suspects = {("省考", "山东", "2019"): {"行测": ["A类", "B类"], "申论": ["统考"]}}
        with tempfile.TemporaryDirectory() as d:
            rec = report_accept.grade_row(row, {}, {}, {}, suspects, d)
        self.assertTrue(rec["form_suspect"])


class TestTruncated(unittest.TestCase):
    def test_material_len_ge_6000_counts(self):
        row = _row()
        src = _src(row["titles"]["linfukai186"][0], [_q(s="材" * 6000)])
        with tempfile.TemporaryDirectory() as d:
            rec = report_accept.grade_row(row, src, {}, {}, set(), d)
        self.assertEqual(rec["truncated"], 1)

    def test_short_material_does_not_count(self):
        row = _row()
        src = _src(row["titles"]["linfukai186"][0], [_q(s="材料")])
        with tempfile.TemporaryDirectory() as d:
            rec = report_accept.grade_row(row, src, {}, {}, set(), d)
        self.assertEqual(rec["truncated"], 0)


class TestEndToEnd(unittest.TestCase):
    """build() 全链路：只读产出 (md, recs)；jsonl 投影字段与 brief 固定清单一致。"""

    def test_build_projects_fixed_jsonl_fields(self):
        row = _row()
        with tempfile.TemporaryDirectory() as up, tempfile.TemporaryDirectory() as repo:
            sd = os.path.join(up, "gongkao-tiku", "data", "shengkao-shenlun")
            os.makedirs(sd)
            with io.open(os.path.join(sd, "y2019.json"), "w",
                         encoding="utf-8", newline="\n") as fh:
                json.dump({row["titles"]["linfukai186"][0]: [_q()]}, fh, ensure_ascii=False)
            os.makedirs(os.path.join(up, "xingcezhenti"))
            cat = os.path.join(up, "catalog")
            os.makedirs(cat)
            with io.open(os.path.join(cat, "catalog.jsonl"), "w",
                         encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            uproots = {"xingcezhenti": os.path.join(up, "xingcezhenti"),
                       "linfukai186": os.path.join(up, "gongkao-tiku")}
            md_text, recs = report_accept.build(cat, uproots, repo, "2016")
        self.assertEqual(len(recs), 1)
        self.assertIn("## 一、口径声明", md_text)
        for sec in ("## 二、分级表", "## 三、缺陷账", "## 四、验收样本建议", "## 五、未做的事"):
            self.assertIn(sec, md_text)
        projected = {k: recs[0][k] for k in report_accept.JSONL_FIELDS}
        self.assertEqual(sorted(projected), sorted(report_accept.JSONL_FIELDS))
        # `t4`/`t5` 是定义里的分级字段，但**不进** jsonl（见 brief「字段固定为」）
        self.assertNotIn("t4_原卷核验", report_accept.JSONL_FIELDS)
        self.assertNotIn("t5_人工通读", report_accept.JSONL_FIELDS)


if __name__ == "__main__":
    unittest.main()
