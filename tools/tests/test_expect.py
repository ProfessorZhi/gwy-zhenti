# -*- coding: utf-8 -*-
"""task-1：应有试卷清单生成器（`gwyzhenti.expect`）的可红测试（最小库风格）。

覆盖 brief §测试 的五项：`parse_title` 年份/科目/地区/卷型；过滤；`status` 四级；
并卷键（**不得**产 `region="多省联考"`）；源并集 `attested_by`。
另加：规则骨架 704 格、交付树伪地区剔除、SLB 存根排除与按标题归位。
"""
import io
import json
import os
import tempfile
import unittest

from gwyzhenti import expect


def _ev(title, src, subject_hint=None, level_hint=None, **extra):
    """标题 → 证据记录（测试便捷包装；解析失败 ⇒ None）。"""
    return expect._ev(expect.parse_title(title, subject_hint=subject_hint,
                                         level_hint=level_hint), src, **extra)


class TestParseTitle(unittest.TestCase):
    def test_xinjiang_423_liankao(self):
        # brief 点名：2016年423联考《行测》题（新疆卷）
        p = expect.parse_title("2016年423联考《行测》题（新疆卷）")
        self.assertEqual(p["year"], "2016")
        self.assertEqual(p["subject"], "行测")
        self.assertEqual(p["region"], "新疆")
        self.assertEqual(p["ptype"], "统考")
        self.assertEqual(p["level"], "省考")
        self.assertEqual(p["session"], "")
        self.assertFalse(p["bingjuan"])

    def test_guokao_fushengji(self):
        # brief 点名：2025年国家公务员考试《申论》试题（副省级）
        p = expect.parse_title("2025年国家公务员考试《申论》试题（副省级）")
        self.assertEqual(p["level"], "国考")
        self.assertEqual(p["region"], "国考")
        self.assertEqual(p["ptype"], "副省级")
        self.assertEqual(p["subject"], "申论")
        self.assertEqual(p["year"], "2025")

    def test_zhejiang_c_juan(self):
        # brief 点名：2023·浙江省公考《申论》题（C卷）
        p = expect.parse_title("2023·浙江省公考《申论》题（C卷）")
        self.assertEqual(p["region"], "浙江")
        self.assertEqual(p["ptype"], "C卷")
        self.assertEqual(p["year"], "2023")
        self.assertEqual(p["level"], "省考")

    def test_no_year_is_dropped(self):
        self.assertIsNone(expect.parse_title("某省公务员考试《行测》题"))

    def test_no_subject_is_dropped_without_hint(self):
        self.assertIsNone(expect.parse_title("2023·浙江省公考"))

    def test_subject_hint_used_only_as_fallback(self):
        # 标题本身没写科目 ⇒ 用来源级兜底（如 linfukai186 的 guokao-xingce 目录）
        p = expect.parse_title("2016·国家公务员考试地市级", subject_hint="行测")
        self.assertEqual(p["subject"], "行测")
        self.assertEqual(p["ptype"], "地市级")
        self.assertEqual(p["level"], "国考")
        # 标题自己写了科目 ⇒ 提示不覆盖它
        q = expect.parse_title("2016·国家公务员考试《申论》地市级", subject_hint="行测")
        self.assertEqual(q["subject"], "申论")

    def test_half_year_fills_session(self):
        p = expect.parse_title("2016·公务员多省联考《申论》题（重庆上半年卷）")
        self.assertEqual(p["ptype"], "上半年")
        self.assertEqual(p["session"], "上半年")
        self.assertEqual(p["region"], "重庆")

    def test_ptype_longest_first(self):
        # 「行政执法」比「执法」长 ⇒ 取长的
        p = expect.parse_title("2021·公务员多省联考《申论》题（湖南行政执法卷）")
        self.assertEqual(p["ptype"], "行政执法")

    def test_unknown_region_kept_empty_with_note_source(self):
        p = expect.parse_title("2023年深圳市公务员考试《申论》试题")
        self.assertEqual(p["region"], "")
        self.assertEqual(p["title"], "2023年深圳市公务员考试《申论》试题")

    def test_xingzhengzhiyenenngli_is_xingce(self):
        p = expect.parse_title("2016年3月四川省选调优秀大学生到基层工作考试 行政职业能力测验试卷")
        self.assertEqual(p["subject"], "行测")
        self.assertEqual(p["region"], "四川")
        self.assertTrue(p["verify"])


class TestFilter(unittest.TestCase):
    def test_mokao_dropped(self):
        self.assertIsNone(expect.parse_title(
            "2023·国考行测申论联合终极模考大赛《申论》（行政执法卷"))

    def test_dasai_dropped(self):
        self.assertIsNone(expect.parse_title("2023·省考行测申论联合模考大赛（第四季）《申论》"))

    def test_jingxuan_dropped(self):
        self.assertIsNone(expect.parse_title(
            "2016年3月四川省选调优秀大学生到基层工作考试 行政职业能力测验试卷（精选）"))

    def test_yuce_and_yaoti_dropped(self):
        self.assertIsNone(expect.parse_title("2024年山东省考《申论》预测卷"))
        self.assertIsNone(expect.parse_title("2024年山东省考《行测》押题卷"))

    def test_normal_title_kept(self):
        self.assertIsNotNone(expect.parse_title("2019·安徽省公考《申论》题（A卷）"))


class TestStatus(unittest.TestCase):
    def _one(self, evidences, delivered=None, grid=False, years=("2019",)):
        rows, bj = expect.merge_rows(evidences, "", delivered or {}, list(years), grid=grid)
        return rows, bj

    def test_yiyou_when_delivered(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        k = (e["level"], e["region"], e["year"], e["subject"], e["ptype"])
        rows, _ = self._one([e], delivered={k: "省考/山东/2019/申论-统考.md"})
        self.assertEqual(rows[0]["status"], "已有")
        self.assertEqual(rows[0]["delivered_md"], "省考/山东/2019/申论-统考.md")

    def test_daiheshi_for_non_guoshengkao_only(self):
        e = _ev("2021年全国招警考试申论试题", "SLB")
        rows, _ = self._one([e])
        self.assertEqual(rows[0]["status"], "待核实")
        self.assertIn("待核实", rows[0]["note"])

    def test_delivered_beats_daiheshi(self):
        # 判定**严格按序**：交付树有 md ⇒ 已有，即使标题是选调/招警类
        e = _ev("2021年全国招警考试申论试题", "SLB")
        k = (e["level"], e["region"], e["year"], e["subject"], e["ptype"])
        rows, _ = self._one([e], delivered={k: "x/y.md"})
        self.assertEqual(rows[0]["status"], "已有")

    def test_yuanyou_weidaoru_when_attested_but_no_md(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, _ = self._one([e])
        self.assertEqual(rows[0]["status"], "源有未导入")
        self.assertEqual(rows[0]["attested_by"], ["linfukai186"])

    def test_shangwei_zhaodao_for_bare_grid_cell(self):
        rows, _ = expect.merge_rows([], "", {}, ["2019"], grid=True)
        self.assertEqual(len(rows), len(expect.GRID_REGIONS) * 2)
        self.assertTrue(all(r["status"] == "尚未找到" for r in rows))
        self.assertTrue(all(r["attested_by"] == [] for r in rows))
        self.assertTrue(all(r["ptype"] == "统考" for r in rows))

    def test_verify_does_not_hide_a_normal_attestation(self):
        # 同一行既有国省考标题又有选调类标题 ⇒ 不是「只由选调类产生」⇒ 不降级为待核实
        a = _ev("2018·公务员多省联考《申论》题（河北卷）", "linfukai186")
        b = _ev("2018·公务员多省联考《申论》题（河北、普通选调卷）", "linfukai186")
        rows, _ = self._one([a, b])
        self.assertEqual(rows[0]["status"], "源有未导入")
        self.assertNotIn("待核实", rows[0]["note"])


class TestBingjuan(unittest.TestCase):
    def test_bingjuan_row_has_no_region_and_is_bingjuan_ptype(self):
        e = _ev("2023·公务员多省联考", "linfukai186", subject_hint="申论",
                keyname="2023·公务员多省联考", n=203)
        self.assertTrue(e["bingjuan"])
        rows, bj = expect.merge_rows([e], "", {}, ["2023"], grid=False)
        self.assertEqual(rows, [])
        self.assertEqual(len(bj), 1)
        r = bj[0]
        self.assertEqual(r["ptype"], "并卷")
        self.assertEqual(r["region"], "")
        self.assertEqual(r["subject"], "申论")
        self.assertEqual(r["level"], "省考")
        self.assertEqual(r["year"], "2023")
        self.assertEqual(r["status"], "源有未导入")
        self.assertIn("203", r["note"])
        self.assertIn("须拆分到真实省份", r["note"])

    def test_no_row_ever_has_region_duoshengliankao(self):
        e = _ev("2023·公务员多省联考", "linfukai186", subject_hint="申论",
                keyname="2023·公务员多省联考", n=1)
        rows, bj = expect.merge_rows([e], "", {}, ["2023"], grid=True)
        regions = {r["region"] for r in rows} | {r["region"] for r in bj}
        self.assertNotIn("多省联考", regions)
        self.assertNotIn("多省联考", expect.GRID_REGIONS)

    def test_liankao_title_with_province_is_not_bingjuan(self):
        p = expect.parse_title("2016年423联考《行测》题（新疆卷）")
        self.assertFalse(p["bingjuan"])
        p2 = expect.parse_title("2021·公务员多省联考《申论》题（新疆兵团二卷）")
        self.assertFalse(p2["bingjuan"])
        self.assertEqual(p2["region"], "新疆")

    def test_missing_province_cells_get_bingjuan_note(self):
        e = _ev("2023·公务员多省联考", "linfukai186", subject_hint="申论",
                keyname="2023·公务员多省联考", n=203)
        rows, _ = expect.merge_rows([e], "", {}, ["2023"], grid=True)
        sl = [r for r in rows if r["level"] == "省考" and r["subject"] == "申论"
              and r["status"] == "尚未找到"]
        self.assertTrue(sl)
        self.assertTrue(all("并卷键" in r["note"] for r in sl))
        # 国考申论空格**不**带并卷提示（联考是省考侧的事）
        gk = [r for r in rows if r["level"] == "国考"]
        self.assertTrue(all("并卷键" not in r["note"] for r in gk))
        # 行测空格**不**该带并卷提示（并卷只发生在申论侧）
        xc = [r for r in rows if r["subject"] == "行测" and r["status"] == "尚未找到"]
        self.assertTrue(all("并卷键" not in r["note"] for r in xc))


class TestUnion(unittest.TestCase):
    def test_two_sources_give_two_attested_by(self):
        a = _ev("2019年安徽省公务员考试《申论》题", "shangantong")
        b = _ev("2019·安徽省公考《申论》题", "xingcezhenti")
        rows, _ = expect.merge_rows([a, b], "", {}, ["2019"], grid=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["attested_by"], ["shangantong", "xingcezhenti"])

    def test_same_source_twice_dedups(self):
        a = _ev("2019·安徽省公考《申论》题", "linfukai186")
        b = _ev("2019·安徽省公考《申论》题", "linfukai186")
        rows, _ = expect.merge_rows([a, b], "", {}, ["2019"], grid=False)
        self.assertEqual(rows[0]["attested_by"], ["linfukai186"])

    def test_distinct_ptype_in_one_cell_are_distinct_rows(self):
        a = _ev("2023·江苏省公考《申论》题（A卷）", "linfukai186")
        b = _ev("2023·江苏省公考《申论》题（B卷）", "linfukai186")
        rows, _ = expect.merge_rows([a, b], "", {}, ["2023"], grid=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["ptype"] for r in rows}, {"A卷", "B卷"})

    def test_attested_by_is_sorted(self):
        a = _ev("2019·安徽省公考《申论》题", "xingcezhenti")
        b = _ev("2019·安徽省公考《申论》题", "catalog")
        rows, _ = expect.merge_rows([a, b], "", {}, ["2019"], grid=False)
        self.assertEqual(rows[0]["attested_by"], ["catalog", "xingcezhenti"])


class TestGrid(unittest.TestCase):
    def test_skeleton_is_704_cells(self):
        years = [str(y) for y in range(2016, 2027)]
        rows, bj = expect.merge_rows([], "", {}, years, grid=True)
        self.assertEqual(len(rows), 32 * 11 * 2)
        self.assertEqual(len(rows), 704)
        self.assertEqual(bj, [])
        regions = {r["region"] for r in rows}
        self.assertEqual(len(regions), 32)
        self.assertIn("国考", regions)

    def test_cell_attested_with_other_ptype_gets_no_placeholder_row(self):
        # 回归：骨架判据是**格级**——该格已有 A卷 证据，就**不得**再补一行占位「统考」
        e = _ev("2023·江苏省公考《行测》题（A类）", "xingcezhenti")
        rows, _ = expect.merge_rows([e], "2016", {}, [str(y) for y in range(2016, 2027)],
                                    grid=True)
        cell = [r for r in rows if r["region"] == "江苏" and r["year"] == "2023"
                and r["subject"] == "行测"]
        self.assertEqual([r["ptype"] for r in cell], ["A类"])
        self.assertEqual(len(rows), 704)

    def test_since_filters_evidence(self):
        old = _ev("2015·山东省公考《申论》题", "linfukai186")
        rows, _ = expect.merge_rows([old], "2016", {}, ["2016"], grid=False)
        self.assertEqual(rows, [])


class TestCatalogSource(unittest.TestCase):
    def _catalog(self, rows):
        d = tempfile.mkdtemp()
        with io.open(os.path.join(d, "catalog.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return d

    def test_pseudo_region_duoshengliankao_is_not_an_evidence(self):
        d = self._catalog([
            {"slug": "省考-多省联考-2023-申论-统考", "level": "省考", "region": "多省联考",
             "year": "2023", "subject": "申论", "ptype": "统考", "title": "2023·公务员多省联考"},
            {"slug": "省考-山东-2019-申论-统考", "level": "省考", "region": "山东",
             "year": "2019", "subject": "申论", "ptype": "统考", "title": "2019·山东省公考"},
        ])
        evs = expect.ev_catalog(d)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["region"], "山东")
        self.assertEqual(evs[0]["md_rel"], "省考/山东/2019/申论-统考.md")

    def test_guokao_region_is_normalized_to_guokao(self):
        d = self._catalog([
            {"slug": "国考-2025-行测-副省级", "level": "国考", "region": "",
             "year": "2025", "subject": "行测", "ptype": "副省级", "title": "2025·国考"},
        ])
        evs = expect.ev_catalog(d)
        self.assertEqual(evs[0]["region"], "国考")
        # 交付树路径仍按 catalog 的 `region=""` 规则给（repo_paths 只看 level）
        self.assertEqual(evs[0]["md_rel"], "国考/2025/行测-副省级.md")


class TestSlbSource(unittest.TestCase):
    def _repo(self, entries):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "work"))
        with io.open(os.path.join(d, "work", "slb_shenlun_manifest.json"), "w",
                     encoding="utf-8") as fh:
            json.dump(entries, fh, ensure_ascii=False)
        return d

    def test_stub_under_2000_chars_excluded(self):
        d = self._repo([
            {"title": "2022年山东省公务员录用考试《申论》试题（A类）", "province": "山东",
             "year": 2022, "exam_type": "省考", "chars": 1200},
            {"title": "2022年山东省公务员录用考试《申论》试题（B类）", "province": "山东",
             "year": 2022, "exam_type": "省考", "chars": 7000},
        ])
        evs = expect.ev_slb(d)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["ptype"], "B类")

    def test_guokao_prefix_mislabel_is_rehomed_by_title(self):
        # recon §5.2：`国考_*` 前缀下混有深圳/招警卷 ⇒ 不信前缀，按 title 归位
        d = self._repo([
            {"title": "2022年深圳市公务员考试《申论》试题（一卷；二卷）", "province": "国考",
             "year": 2022, "exam_type": "国考", "chars": 6593},
            {"title": "2022年国家公务员考试《申论》试题（副省级）", "province": "国考",
             "year": 2022, "exam_type": "国考", "chars": 8000},
        ])
        evs = expect.ev_slb(d)
        by_title = {e["title"]: e for e in evs}
        shen = by_title["2022年深圳市公务员考试《申论》试题（一卷；二卷）"]
        self.assertEqual(shen["level"], "省考")
        self.assertEqual(shen["region"], "")
        gk = by_title["2022年国家公务员考试《申论》试题（副省级）"]
        self.assertEqual(gk["level"], "国考")
        self.assertEqual(gk["region"], "国考")
        self.assertEqual(gk["ptype"], "副省级")

    def test_missing_manifest_is_empty_not_error(self):
        self.assertEqual(expect.ev_slb(tempfile.mkdtemp()), [])


class TestJsonlContract(unittest.TestCase):
    def test_fields_are_exactly_the_fixed_ten_in_order(self):
        self.assertEqual(expect.JSONL_FIELDS,
                         ("level", "region", "year", "subject", "session", "ptype",
                          "status", "attested_by", "delivered_md", "note"))

    def test_projection_hides_internal_keys(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, _ = expect.merge_rows([e], "", {}, ["2019"], grid=False)
        proj = {k: rows[0][k] for k in expect.JSONL_FIELDS}
        self.assertNotIn("_verify", proj)
        self.assertEqual(set(proj), set(expect.JSONL_FIELDS))

    def test_year_is_str_and_status_in_enum(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, _ = expect.merge_rows([e], "", {}, ["2019"], grid=False)
        self.assertIsInstance(rows[0]["year"], str)
        self.assertIn(rows[0]["status"], ("已有", "源有未导入", "尚未找到", "待核实"))

    def test_render_md_has_the_six_required_sections(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, bj = expect.merge_rows([e], "2016", {}, ["2019"], grid=True)
        txt = expect.render_md(rows, bj, "2016", len(rows))
        for head in ("## 一、口径声明", "## 二、总量", "## 三、按 `status` × 科目",
                     "## 四、缺卷清单", "## 五、并卷键清单", "## 六、诚实边界"):
            self.assertIn(head, txt)
        self.assertIn("不等于", txt.replace("**", "").replace("`", ""))

    def test_render_md_states_the_two_disclaimers_verbatim(self):
        rows, bj = expect.merge_rows([], "2016", {}, ["2016"], grid=True)
        txt = expect.render_md(rows, bj, "2016", 0)
        self.assertIn("本机所有来源都没提到", txt)
        self.assertIn("绝不表示该考试没有举行", txt)
        self.assertIn("不是地区", txt)


if __name__ == "__main__":
    unittest.main()
