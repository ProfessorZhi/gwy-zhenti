# -*- coding: utf-8 -*-
"""Task 2：SLB 申论源接入（`gwyzhenti.slb`）的可红测试（最小库风格）。

覆盖简令 S2 的**归位/过滤**、S3 的**候选 md 生成与重名不覆盖**、S4 的**缺口对账**。
**关键回归**：`深圳`/`广州` 是**市考**（R-COV-22A），**不得**判成国考；国考 `region="国考"`；
`region="多省联考"` 恒为 0。
"""
import io
import json
import os
import re
import tempfile
import unittest

from gwyzhenti import slb


def _rec(tid, title, file=None, province="", exam_type="", chars=8000, year=2020,
         crawled="2026-05-29T08:17:20"):
    return {"tid": str(tid), "title": title, "file": file or ("x_%s.md" % tid),
            "province": province, "exam_type": exam_type, "year": year, "chars": chars,
            "crawled_at": crawled}


def _src_dir(recs, bodies=None):
    """临时源目录：`_manifest.json` + 每条的 `.md`。"""
    d = tempfile.mkdtemp()
    bodies = bodies or {}
    with io.open(os.path.join(d, "_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(recs, fh, ensure_ascii=False)
    for r in recs:
        body = bodies.get(r["tid"], u"材料一：\n　　正文。\n作答要求\n问题一：做某事。（20分）\n")
        text = (u"---\nsource: shenlunhome.com\ntid: %s\ncrawled_at: %s\ntitle: %s\n---\n\n# %s\n\n%s"
                % (r["tid"], r.get("crawled_at", ""), r["title"], r["title"], body))
        with io.open(os.path.join(d, r["file"]), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return d


class TestClassify(unittest.TestCase):
    def test_adopt_normal(self):
        r = slb.classify(_rec(1, "2019年浙江公务员考试《申论》试题（A卷）"))
        self.assertEqual(r["verdict"], "采用")
        self.assertEqual(r["reason"], "ok")
        self.assertEqual(r["level"], "省考")
        self.assertEqual(r["region"], "浙江")
        self.assertEqual(r["ptype"], "A类")
        self.assertEqual(r["year"], "2019")
        self.assertEqual(r["subject"], "申论")

    def test_material_article_excluded(self):
        # 国考_0_* = 素材文章（非试卷）
        for t in (u"机关素养", u"习近平总书记强调的六大思维方法", u"机关工作素养必读系列：群众工作九法"):
            r = slb.classify(_rec(718, t, file="国考_0_%s.md" % t, province="国考"))
            self.assertEqual(r["verdict"], "排除")
            self.assertEqual(r["reason"], "国考_0素材")

    def test_stub_excluded(self):
        r = slb.classify(_rec(2, "2020年上海市公务员考试《申论》试题（B）", chars=148))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "存根<2000")
        self.assertFalse(r["chars_ok"])

    def test_no_year_excluded(self):
        r = slb.classify(_rec(3, "机关素养"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "无年份")

    def test_no_subject_excluded(self):
        # 标题无「申论」⇒ 科目取不到（不猜）
        r = slb.classify(_rec(4, "2019年新疆兵团公考试题（下半年）"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "无科目")

    def test_mock_excluded(self):
        r = slb.classify(_rec(5, "2021年浙江公务员考试《申论》模拟试题"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "模考")

    def test_before_2016_excluded(self):
        r = slb.classify(_rec(6, "2015年上海市公务员考试《申论》试题（B）"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "年<2016")

    def test_verify_xuandiao(self):
        r = slb.classify(_rec(7, "2024年浙江省选调生考试《申论》参考题本"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "非国省考:选调")

    def test_verify_zhaojing(self):
        r = slb.classify(_rec(8, "2022年全国招警考试申论试题（网友提供版，仅供参考）"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "非国省考:招警")

    def test_verify_zhengfa(self):
        r = slb.classify(_rec(9, "2019年政法干警考试《申论》试题（9.19）"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "非国省考:政法干警")

    def test_liankao_multi_province_excluded(self):
        r = slb.classify(_rec(10, "2019年联考《申论》（豫、云、贵、桂、闽）试题"))
        self.assertEqual(r["verdict"], "排除")
        self.assertEqual(r["reason"], "联考多省并列无法归位")


class TestRegionGuokaoAndMunicipal(unittest.TestCase):
    """R-COV-22 / R-COV-22A：国考 region 恒为「国考」；**深圳/广州是市考**。"""

    def test_guokao_region_is_guokao(self):
        r = slb.classify(_rec(11, "2025年国家公务员考试《申论》试题（副省级）"))
        self.assertEqual(r["verdict"], "采用")
        self.assertEqual(r["level"], "国考")
        self.assertEqual(r["region"], "国考")
        self.assertEqual(r["ptype"], "副省级")

    def test_shenzhen_not_guokao(self):
        # 源 frontmatter 谎称 exam_type=国考；必须按 title 归位为 省考/深圳
        r = slb.classify(_rec(12, "2017年深圳市公务员考试《申论》试题（A卷）",
                              province="国考", exam_type="国考"))
        self.assertEqual(r["level"], "省考")
        self.assertEqual(r["region"], "深圳")
        self.assertNotEqual(r["level"], "国考")

    def test_guangzhou_not_guokao(self):
        r = slb.classify(_rec(13, "2016年广州市公务员考试《申论》试题",
                              province="国考", exam_type="国考"))
        self.assertEqual(r["level"], "省考")
        self.assertEqual(r["region"], "广州")

    def test_never_liankao_region(self):
        rows = slb.build_index([_rec(14, "2019年联考《申论》（豫、云、贵、桂、闽）试题"),
                                _rec(15, "2019年联考《申论》（诚信）参考题本")])
        self.assertEqual([r for r in rows if r["region"] == "多省联考"], [])


class TestBody(unittest.TestCase):
    def test_split_fm_and_h1(self):
        text = u"---\ntid: 1\ntitle: T\ncrawled_at: X\n---\n\n# T\n\n材料一：\n正文\n"
        fm, rest = slb.split_fm(text)
        self.assertEqual(fm["tid"], "1")
        h1, body = slb.extract_body(rest)
        self.assertEqual(h1, "T")
        self.assertIn(u"材料一", body)
        self.assertNotIn(u"# T", body)

    def test_body_verbatim_crlf_to_lf_only(self):
        text = u"---\ntid: 1\n---\n# T\n材料一：\r\n　　甲\r\n"
        _fm, rest = slb.split_fm(text)
        _h1, body = slb.extract_body(rest)
        self.assertNotIn("\r", body)
        self.assertIn(u"　　甲", body)

    def test_count_questions(self):
        body = u"作答要求\n问题一：a\n问题二：b\n问题三：c\n"
        self.assertEqual(slb.count_questions(body)[0], 3)
        body2 = u"作答要求\n第一题：a\n第二题：b\n"
        self.assertEqual(slb.count_questions(body2)[0], 2)
        body3 = u"作答要求\n（20分）（30分）\n"
        self.assertEqual(slb.count_questions(body3)[0], 2)
        self.assertEqual(slb.count_questions(u"作答要求\n")[0], 0)

    def test_multi_ptypes_detects_hejuan(self):
        self.assertEqual(slb.multi_ptypes(u"2019年深圳市公务员考试《申论》试题（一卷；二卷）"),
                         ["一卷", "二卷"])
        self.assertEqual(slb.multi_ptypes(u"2020年浙江公务员考试《申论》试题（A卷）"), ["A类"])

    def test_multi_ptypes_no_substring_false_positive(self):
        # 别名**最长优先**：`省级` 被 `副省级` 包含 ⇒ 不得报成第二个卷型
        self.assertEqual(slb.multi_ptypes(u"2016年国家公务员考试《申论》（副省级）试题"), ["副省级"])
        self.assertEqual(slb.multi_ptypes(u"2022年内蒙古公务员考试《申论》试题（内蒙古盟市卷）"), ["盟市"])


class TestPaths(unittest.TestCase):
    def test_cand_relpath_shengkao(self):
        r = slb.classify(_rec(20, "2019年浙江公务员考试《申论》试题（A卷）"))
        self.assertEqual(slb.cand_relpath(r),
                         os.path.join("省考", "浙江", "2019", "申论-A类.md"))

    def test_cand_relpath_guokao_no_region_layer(self):
        r = slb.classify(_rec(21, "2025年国家公务员考试《申论》试题（副省级）"))
        self.assertEqual(slb.cand_relpath(r),
                         os.path.join("国考", "2025", "申论-副省级.md"))

    def test_plan_paths_collision_no_overwrite(self):
        # 构造**真**重名：A卷 与 A类 归一后同键 ⇒ 第二件必须加 `__t<tid>`（不覆盖）
        rows2 = slb.build_index([_rec(32, "2019年江苏公务员考试《申论》试题（A卷）"),
                                 _rec(33, "2019年江苏公务员考试《申论》试题（A类）")])
        plan = slb.plan_paths(rows2)
        self.assertEqual(len(plan), 2)
        rels = [rel for _r, rel in plan]
        self.assertEqual(len(set(rels)), 2)
        self.assertTrue(any(rel.endswith("__t33.md") for rel in rels))
        self.assertEqual(plan[0][1], os.path.join("省考", "江苏", "2019", "申论-A类.md"))


class TestRenderCandidate(unittest.TestCase):
    def _row(self, **kw):
        return slb.classify(_rec(**kw))

    def test_frontmatter_contract(self):
        row = self._row(tid=40, title=u"2025年浙江公务员考试《申论》试题（A卷）")
        body = u"材料一：\n　　正文。\n作答要求\n问题一：做某事。（20分）\n"
        rec = dict(row)
        rec["_crawled"] = "2026-05-29T08:17:20"
        text = slb.render_candidate(rec, body)
        fm, _rest = slb.split_fm(text)
        for k in (u"考试", u"地区", u"年份", u"科目", u"卷型", u"真题性质", u"命题形式",
                  u"来源", u"来源明细", u"题号口径", u"校验状态"):
            self.assertIn(k, fm)
        self.assertEqual(fm[u"考试"], u'"省考"')
        self.assertEqual(fm[u"地区"], u'"浙江"')
        self.assertEqual(fm[u"卷型"], u'"A类"')
        self.assertEqual(fm[u"来源"], u'["slb"]')
        self.assertIn("tid=40", fm[u"来源明细"])
        self.assertIn("crawled_at=2026-05-29T08:17:20", fm[u"来源明细"])
        self.assertIn(u"未人工通读", fm[u"校验状态"])
        self.assertIn(u"第三方源", fm[u"校验状态"])
        self.assertIn(u"# 2025年浙江公务员考试《申论》试题（A卷）", text)
        self.assertIn(u"> 申论 · 1 题 · 浙江 2025", text)
        self.assertIn(u"材料一", text)

    def test_guokao_region_in_frontmatter(self):
        row = self._row(tid=41, title=u"2025年国家公务员考试《申论》试题（副省级）")
        row = dict(row); row["_crawled"] = "X"
        text = slb.render_candidate(row, u"作答要求\n问题一：a\n")
        fm, _ = slb.split_fm(text)
        self.assertEqual(fm[u"考试"], u'"国考"')
        self.assertEqual(fm[u"地区"], u'"国考"')

    def test_notes_appended(self):
        row = self._row(tid=42, title=u"2025年浙江公务员考试《申论》试题（A卷）")
        row = dict(row); row["_crawled"] = "X"
        text = slb.render_candidate(row, u"作答要求\n", [u"正文未见「作答要求」标记"])
        fm, _ = slb.split_fm(text)
        self.assertIn(u"正文未见「作答要求」标记", fm[u"校验状态"])


class TestIndexContract(unittest.TestCase):
    def test_fields_exact_and_order(self):
        self.assertEqual(slb.INDEX_FIELDS,
                         ("tid", "file", "title", "province_raw", "exam_type_raw", "year",
                          "chars", "level", "region", "subject", "ptype", "session",
                          "verdict", "reason", "chars_ok"))

    def test_build_index_stable_and_sorted(self):
        recs = [_rec(3, "2019年浙江公务员考试《申论》试题"), _rec(1, "2018年浙江公务员考试《申论》试题"),
                _rec(2, "2020年浙江公务员考试《申论》试题")]
        rows = slb.build_index(recs)
        self.assertEqual([r["tid"] for r in rows], ["1", "2", "3"])

    def test_excluded_reason_nonempty(self):
        recs = [_rec(1, "2015年上海市公务员考试《申论》试题"), _rec(2, u"机关素养", file="国考_0_x.md"),
                _rec(3, "2020年浙江公务员考试《申论》试题", chars=10)]
        for r in slb.build_index(recs):
            self.assertEqual(r["verdict"], "排除")
            self.assertTrue(r["reason"])


class TestEndToEnd(unittest.TestCase):
    def test_write_index_and_candidates(self):
        recs = [
            _rec(100, u"2025年浙江公务员考试《申论》试题（A卷）", file="zj2025a.md"),
            _rec(101, u"2025年国家公务员考试《申论》试题（副省级）", file="gk2025f.md"),
            _rec(102, u"2019年联考《申论》（豫、云、贵、桂、闽）试题", file="lk2019.md"),
            _rec(103, u"2024年浙江省选调生考试《申论》参考题本", file="xd2024.md"),
        ]
        d = _src_dir(recs)
        work = tempfile.mkdtemp()
        records = slb.read_index(d)
        self.assertEqual(slb.count_md(d), 4)
        rows = slb.build_index(records)
        slb.write_index(os.path.join(work, "slb-INDEX.jsonl"), rows)
        # 索引行数 == 源记录数；采用行 == 已写候选数
        idx = [json.loads(l) for l in io.open(os.path.join(work, "slb-INDEX.jsonl"),
                                              encoding="utf-8")]
        self.assertEqual(len(idx), 4)
        adopted = [r for r in idx if r["verdict"] == "采用"]
        self.assertEqual(len(adopted), 2)
        out, _coll = slb.write_candidates(d, work, rows)
        self.assertEqual(len(out), len(adopted))
        for _row, rel, ap in out:
            self.assertTrue(os.path.exists(ap))
            fm, _rest = slb.split_fm(io.open(ap, encoding="utf-8").read())
            self.assertTrue(fm[u"来源"])
            self.assertIn(u"未人工通读", fm[u"校验状态"])

    def test_gap_report(self):
        recs = [
            _rec(200, u"2025年浙江公务员考试《申论》试题（A卷）", file="zj2025a.md"),
            _rec(201, u"2030年浙江公务员考试《申论》试题（A卷）", file="zj2030a.md"),
        ]
        d = _src_dir(recs)
        work = tempfile.mkdtemp()
        rows = slb.build_index(slb.read_index(d))
        exp = [
            {"level": "省考", "region": "浙江", "year": "2025", "subject": "申论",
             "session": "", "ptype": "A类", "status": "源有未导入", "attested_by": [],
             "delivered_md": [], "note": ""},
            {"level": "省考", "region": "浙江", "year": "2025", "subject": "申论",
             "session": "", "ptype": "C类", "status": "尚未找到", "attested_by": [],
             "delivered_md": [], "note": ""},
        ]
        with io.open(os.path.join(work, "EXPECTED.jsonl"), "w", encoding="utf-8") as fh:
            for r in exp:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        g = slb.build_gap(work, rows)
        self.assertEqual(g["exp_n"], 2)
        self.assertEqual(g["gap_n"], 2)
        filled = {k for k, _st, _c in g["filled"]}
        still = {k for k, _st, _ab in g["still"]}
        self.assertIn(("省考", "浙江", "2025", "A类"), filled)
        self.assertIn(("省考", "浙江", "2025", "C类"), still)
        # 2030 是 EXPECTED 里没有的键 ⇒ 新增卷型
        newkeys = {k for k, _c in g["new"]}
        self.assertIn(("省考", "浙江", "2030", "A类"), newkeys)
        md = slb.render_gap(g)
        self.assertIn(u"缺口对账", md)
        self.assertIn(u"省考/浙江/2025/A类", md)


if __name__ == "__main__":
    unittest.main()
