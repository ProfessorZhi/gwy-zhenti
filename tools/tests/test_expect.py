# -*- coding: utf-8 -*-
"""task-1 / 修轮 1：应有试卷清单生成器（`gwyzhenti.expect`）的可红测试（最小库风格）。

覆盖 brief §测试 的五项：`parse_title` 年份/科目/地区/卷型；过滤；`status` 四级；
并卷键（**不得**产 `region="多省联考"`）；源并集 `attested_by`。
另加：规则骨架 704 格、交付树伪地区剔除、SLB 存根排除与按标题归位。

修轮 1 新增（A1–A7）：`canon_ptype` 归一映射、**反幻影缺口**、**账闭合**
（已交付行按原始串落键、两件并存不丢路径）、region 白名单、非国省考移出主账、
`session` 与 `ptype` 脱钩。
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


def _catalog_dir(rows):
    """临时 catalog 目录（`catalog.jsonl`）。"""
    d = tempfile.mkdtemp()
    with io.open(os.path.join(d, "catalog.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return d


def _cat(slug, level, region, year, subject, ptype, title=""):
    return {"slug": slug, "level": level, "region": region, "year": year,
            "subject": subject, "ptype": ptype, "title": title}


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
        # 修轮 1（A1）：源侧一律出**规范词** ⇒ `C卷` 归一为 `C类`
        p = expect.parse_title("2023·浙江省公考《申论》题（C卷）")
        self.assertEqual(p["region"], "浙江")
        self.assertEqual(p["ptype"], "C类")
        self.assertEqual(p["ptype_raw"], "C卷")
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
        # A6：`上半年/下半年` **剥进 session**，不再留在 ptype 里
        p = expect.parse_title("2016·公务员多省联考《申论》题（重庆上半年卷）")
        self.assertEqual(p["ptype"], "统考")
        self.assertEqual(p["session"], "上半年")
        self.assertEqual(p["region"], "重庆")

    def test_ptype_longest_first(self):
        # 「行政执法」比「执法」长 ⇒ 取长的
        p = expect.parse_title("2021·公务员多省联考《申论》题（湖南行政执法卷）")
        self.assertEqual(p["ptype"], "行政执法")

    def test_unknown_region_kept_empty_with_note_source(self):
        # A4：白名单只补深圳/广州；台州这类非考点城市仍归位到省，江苏/浙江外的陌生名留空
        p = expect.parse_title("2023年某某市公务员考试《申论》试题")
        self.assertEqual(p["region"], "")
        self.assertEqual(p["title"], "2023年某某市公务员考试《申论》试题")

    def test_xingzhengzhiyenenngli_is_xingce(self):
        p = expect.parse_title("2016年3月四川省选调优秀大学生到基层工作考试 行政职业能力测验试卷")
        self.assertEqual(p["subject"], "行测")
        self.assertEqual(p["region"], "四川")
        self.assertTrue(p["verify"])


class TestCanonPtype(unittest.TestCase):
    """A1：`canon_ptype` 的简令点名映射（逐条照抄简令 §归一规则 的示例）。"""

    def test_brief_named_mappings(self):
        for raw, want in (("A卷", ("A类", "")), ("A类", ("A类", "")),
                          ("乡镇卷", ("乡镇", "")), ("乡镇", ("乡镇", "")),
                          ("定向乡镇", ("乡镇", "")),
                          ("县级、乡镇统一卷", ("县乡", "")),
                          ("上半年行政执法卷", ("行政执法", "上半年")),
                          ("卷乙级", ("乙级", "")),
                          ("A卷：省直", ("A类", "")),
                          ("急需紧缺岗位", ("统考", ""))):
            self.assertEqual(expect.canon_ptype(raw), want, raw)

    def test_other_alias_groups(self):
        for raw, want in (("B卷", ("B类", "")), ("C卷", ("C类", "")),
                          ("卷甲级", ("甲级", "")), ("县级卷", ("县级", "")),
                          ("县级", ("县级", "")), ("区级及以上", ("区级", "")),
                          ("区级卷", ("区级", "")), ("县乡卷", ("县乡", "")),
                          ("县级+乡镇", ("县乡", "")), ("省市县卷", ("省市", "")),
                          ("省市州级", ("省市", "")), ("兵团一卷", ("一卷", "")),
                          ("兵团二卷", ("二卷", "")), ("通用卷", ("通用", "")),
                          ("市地级", ("地市级", "")), ("下半年", ("统考", "下半年")),
                          ("市县卷", ("统考", ""))):
            self.assertEqual(expect.canon_ptype(raw), want, raw)

    def test_alias_table_is_self_consistent(self):
        # 别名表的每个 canonical 都必须在规范词表里（`县级` 曾漏列 —— R-COV-16-1）
        for alias, canon in expect.ALIASES:
            self.assertIn(canon, expect.CANON_PTYPES, canon)
        self.assertIn("县级", expect.CANON_PTYPES)
        self.assertIn("县乡", expect.CANON_PTYPES)

    def test_longest_first_and_index_tiebreak(self):
        # 同长度按规范词表次序：`兵团一卷` 取 `一卷` 而非 `兵团`
        self.assertEqual(expect.canon_ptype("兵团一卷")[0], "一卷")
        self.assertEqual(expect.match_ptype("2016·新疆兵团二卷")[0], "二卷")

    def test_strip_session_keeps_raw_ptype(self):
        # A2/裁定：**已交付行**按交付侧原始串落键（只剥 session）
        self.assertEqual(expect._strip_session("下半年"), ("统考", "下半年"))
        self.assertEqual(expect._strip_session("上半年行政执法卷"),
                         ("行政执法卷", "上半年"))
        self.assertEqual(expect._strip_session("乡镇卷"), ("乡镇卷", ""))
        self.assertEqual(expect._strip_session(""), ("统考", ""))


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
        """`delivered` = **已落盘的 md_rel 集合**（修轮 1 口径）。"""
        rows, bj, ngs = expect.merge_rows(evidences, "", set(delivered or ()),
                                          list(years), grid=grid)
        return rows, bj, ngs

    def test_yiyou_when_delivered(self):
        d = _catalog_dir([_cat("省考-山东-2019-申论-统考", "省考", "山东", "2019", "申论",
                               "统考", "2019·山东省公考")])
        e = expect.ev_catalog(d)[0]
        rows, _, _ = self._one([e], delivered={e["md_rel"]})
        self.assertEqual(rows[0]["status"], "已有")
        self.assertEqual(rows[0]["delivered_md"], "省考/山东/2019/申论-统考.md")

    def test_non_guoshengkao_moves_out_of_main_account(self):
        # A3：**整行只由非国省考类标题组成** ⇒ 移出主账（不再落 `待核实`）
        e = _ev("2021年全国招警考试申论试题", "SLB")
        rows, _, ngs = self._one([e])
        self.assertEqual(rows, [])
        self.assertEqual(len(ngs), 1)
        self.assertEqual(ngs[0]["ptype"], "统考")
        self.assertIn("招警考试", ngs[0]["titles"][0])

    def test_non_guoshengkao_gets_no_grid_placeholder(self):
        # A3：这类格**不生成** `尚未找到` 占位（否则虚增空格）—— 该格直接出账
        e = _ev("2021·四川省选调生考试《申论》题", "linfukai186")
        self.assertTrue(e["verify"])
        rows, _, ngs = expect.merge_rows([e], "2016", set(), ["2021"], grid=True)
        sl = [r for r in rows if r["region"] == "四川" and r["subject"] == "申论"]
        self.assertEqual(sl, [])                                      # 被移出的一格无占位
        self.assertTrue([r for r in rows if r["region"] == "四川"
                         and r["subject"] == "行测"])                  # 同省另一科目照常占位
        self.assertEqual(len(rows), len(expect.GRID_REGIONS) * 2 - 1)  # 32*2 去掉被移出的一格
        self.assertEqual(len(ngs), 1)

    def test_delivered_beats_non_guoshengkao(self):
        # 判定**严格按序**：交付树有 md ⇒ 已有，即使标题是选调/招警类
        d = _catalog_dir([_cat("省考-山东-2019-申论-统考", "省考", "山东", "2019", "申论",
                               "统考", "2019·山东省公考")])
        e = expect.ev_catalog(d)[0]
        rows, _, _ = self._one([e], delivered={e["md_rel"]})
        self.assertEqual(rows[0]["status"], "已有")

    def test_yuanyou_weidaoru_when_attested_but_no_md(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, _, _ = self._one([e])
        self.assertEqual(rows[0]["status"], "源有未导入")
        self.assertEqual(rows[0]["attested_by"], ["linfukai186"])

    def test_shangwei_zhaodao_for_bare_grid_cell(self):
        rows, _, _ = expect.merge_rows([], "", set(), ["2019"], grid=True)
        self.assertEqual(len(rows), len(expect.GRID_REGIONS) * 2)
        self.assertTrue(all(r["status"] == "尚未找到" for r in rows))
        self.assertTrue(all(r["attested_by"] == [] for r in rows))
        self.assertTrue(all(r["ptype"] == "统考" for r in rows))

    def test_verify_does_not_hide_a_normal_attestation(self):
        # 同一行既有国省考标题又有选调类标题 ⇒ **不是**「整行只由选调类产生」⇒ 留在主账
        a = _ev("2018·公务员多省联考《申论》题（河北卷）", "linfukai186")
        b = _ev("2018·公务员多省联考《申论》题（河北、普通选调卷）", "linfukai186")
        rows, _, ngs = self._one([a, b])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "源有未导入")
        self.assertEqual(ngs, [])

    def test_status_is_never_daiheshi_in_main_account(self):
        # A3 验收：`待核实` 保留为合法取值，但主账预期 0 行
        for t in ("2019·山东省选调生考试", "2021·重庆市选调生考试",
                  "2022·公安院校联考"):
            rows, _, ngs = self._one([_ev(t, "linfukai186", subject_hint="申论")])
            self.assertEqual(rows, [], t)
            self.assertEqual(len(ngs), 1, t)


class TestAntiPhantom(unittest.TestCase):
    """A1 的核心验收：交付侧与源侧**同一份卷**不得既记 `已有` 又记 `源有未导入`。"""

    def test_catalog_a_lei_plus_source_a_juan_is_one_row(self):
        d = _catalog_dir([_cat("省考-上海-2016-申论-A类", "省考", "上海", "2016", "申论",
                               "A类", "2016·上海市公考《申论》题（A类）")])
        ce = expect.ev_catalog(d)[0]
        se = _ev("2016·上海市公考《申论》题（A卷）", "linfukai186")
        rows, _, _ = expect.merge_rows([ce, se], "", {ce["md_rel"]}, ["2016"], grid=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "已有")
        self.assertEqual(rows[0]["attested_by"], ["catalog", "linfukai186"])

    def test_catalog_xiangzhen_juan_plus_source_xiangzhen_is_one_row(self):
        d = _catalog_dir([_cat("省考-云南-2019-申论-乡镇卷", "省考", "云南", "2019", "申论",
                               "乡镇卷", "2019·公务员多省联考《申论》题（云南乡镇卷）")])
        ce = expect.ev_catalog(d)[0]
        se = _ev("2019·公务员多省联考《申论》题（云南乡镇）", "linfukai186")
        rows, _, _ = expect.merge_rows([ce, se], "", {ce["md_rel"]}, ["2019"], grid=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "已有")
        self.assertNotIn("源有未导入", [r["status"] for r in rows])

    def test_delivered_row_keeps_raw_ptype_but_matches_by_canon(self):
        # 裁定 R-COV-16：已交付行 `ptype` = 交付侧原始串；匹配用 canonical
        d = _catalog_dir([_cat("省考-内蒙古-2022-申论-旗县卷", "省考", "内蒙古", "2022",
                               "申论", "旗县卷", "2022·公务员多省联考《申论》题（内蒙古旗县卷）")])
        ce = expect.ev_catalog(d)[0]
        rows, _, _ = expect.merge_rows([ce], "", {ce["md_rel"]}, ["2022"], grid=False)
        self.assertEqual(rows[0]["ptype"], "旗县卷")          # 交付侧原样
        self.assertEqual(expect.canon_ptype(rows[0]["ptype"])[0], "旗县")  # 匹配用

    def test_underspecified_source_title_does_not_merge_into_other_ptype(self):
        # 宁多一行可疑，不并错一份卷：源标题未指明卷型（canon 统考）而同格交付的是乡镇卷
        d = _catalog_dir([_cat("省考-云南-2019-申论-乡镇卷", "省考", "云南", "2019", "申论",
                               "乡镇卷", "2019·公务员多省联考《申论》题（云南乡镇卷）")])
        ce = expect.ev_catalog(d)[0]
        se = _ev("2019年云南公务员考试《申论》试题（联考版）", "SLB")
        rows, _, _ = expect.merge_rows([ce, se], "", {ce["md_rel"]}, ["2019"], grid=False)
        self.assertEqual(len(rows), 2)
        st = {r["ptype"]: r["status"] for r in rows}
        self.assertEqual(st["乡镇卷"], "已有")
        self.assertEqual(st["统考"], "源有未导入")


class TestPathClosure(unittest.TestCase):
    """A2：`{delivered_md}` 必须逐路径与 manifest 对齐 —— 两个不同交付件不得被并掉。"""

    def test_two_delivered_files_in_one_cell_stay_two_rows(self):
        d = _catalog_dir([
            _cat("省考-黑龙江-2019-申论-统考", "省考", "黑龙江", "2019", "申论", "统考",
                 "2019·黑龙江省公考《申论》题"),
            _cat("省考-黑龙江-2019-申论-急需紧缺岗位", "省考", "黑龙江", "2019", "申论",
                 "急需紧缺岗位", "2019·黑龙江省公考《申论》题（急需紧缺岗位）"),
        ])
        evs = expect.ev_catalog(d)
        delivered = {e["md_rel"] for e in evs}
        self.assertEqual(len(delivered), 2)
        rows, _, _ = expect.merge_rows(evs, "", delivered, ["2019"], grid=False)
        self.assertEqual({r["delivered_md"] for r in rows}, delivered)
        self.assertEqual(len(rows), 2)

    def test_source_title_attaches_only_to_the_canonical_named_row(self):
        # 源侧 `统考` 证据只挂 `统考` 那一行，**不得**挂到同格 `急需紧缺岗位` 行
        d = _catalog_dir([
            _cat("省考-黑龙江-2019-申论-统考", "省考", "黑龙江", "2019", "申论", "统考",
                 "2019·黑龙江省公考《申论》题"),
            _cat("省考-黑龙江-2019-申论-急需紧缺岗位", "省考", "黑龙江", "2019", "申论",
                 "急需紧缺岗位", "2019·黑龙江省公考《申论》题（急需紧缺岗位）"),
        ])
        evs = expect.ev_catalog(d)
        delivered = {e["md_rel"] for e in evs}
        se = _ev("2019·黑龙江省公考《申论》题", "linfukai186")
        rows, _, _ = expect.merge_rows(evs + [se], "", delivered, ["2019"], grid=False)
        by = {r["ptype"]: r for r in rows}
        self.assertEqual(by["统考"]["attested_by"], ["catalog", "linfukai186"])
        self.assertEqual(by["急需紧缺岗位"]["attested_by"], ["catalog"])

    def test_delivered_paths_are_unique(self):
        d = _catalog_dir([
            _cat("省考-黑龙江-2019-申论-统考", "省考", "黑龙江", "2019", "申论", "统考"),
            _cat("省考-黑龙江-2019-申论-急需紧缺岗位", "省考", "黑龙江", "2019", "申论",
                 "急需紧缺岗位"),
            _cat("国考-2019-行测-统考", "国考", "", "2019", "行测", "统考"),
        ])
        evs = expect.ev_catalog(d)
        delivered = {e["md_rel"] for e in evs}
        rows, _, _ = expect.merge_rows(evs, "", delivered, ["2019"], grid=False)
        got = [r["delivered_md"] for r in rows if r["delivered_md"]]
        self.assertEqual(len(got), len(set(got)))
        self.assertEqual(set(got), delivered)


class TestBingjuan(unittest.TestCase):
    def test_bingjuan_row_has_no_region_and_is_bingjuan_ptype(self):
        e = _ev("2023·公务员多省联考", "linfukai186", subject_hint="申论",
                keyname="2023·公务员多省联考", n=203)
        self.assertTrue(e["bingjuan"])
        rows, bj, _ = expect.merge_rows([e], "", set(), ["2023"], grid=False)
        self.assertEqual(rows, [])
        self.assertEqual(len(bj), 1)
        r = bj[0]
        self.assertEqual(r["ptype"], "并卷")
        self.assertEqual(r["region"], "")
        self.assertEqual(r["subject"], "申论")
        self.assertEqual(r["level"], "省考")
        self.assertEqual(r["year"], "2023")
        self.assertEqual(r["status"], "源有未导入")
        self.assertIn("并卷", r["note"])
        self.assertEqual(r["keys"], [("2023·公务员多省联考", 203)])

    def test_catalog_bingjuan_row_gets_delivered_md(self):
        # A2：交付树里的并卷落盘要**计入** `delivered_md`（账闭合），且 `status=已有`
        d = _catalog_dir([_cat("省考-多省联考-2023-申论-统考", "省考", "多省联考", "2023",
                               "申论", "统考", "2023·公务员多省联考")])
        evs = expect.ev_catalog(d)
        self.assertTrue(evs[0]["bingjuan"])
        delivered = {e["md_rel"] for e in evs}
        rows, bj, _ = expect.merge_rows(evs, "", delivered, ["2023"], grid=False)
        self.assertEqual(rows, [])
        self.assertEqual(len(bj), 1)
        self.assertEqual(bj[0]["ptype"], "并卷")
        self.assertEqual(bj[0]["status"], "已有")
        self.assertEqual(bj[0]["delivered_md"], "省考/多省联考/2023/申论-统考.md")

    def test_no_row_ever_has_region_duoshengliankao(self):
        e = _ev("2023·公务员多省联考", "linfukai186", subject_hint="申论",
                keyname="2023·公务员多省联考", n=1)
        rows, bj, _ = expect.merge_rows([e], "", set(), ["2023"], grid=True)
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
        rows, _, _ = expect.merge_rows([e], "", set(), ["2023"], grid=True)
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
        rows, _, _ = expect.merge_rows([a, b], "", set(), ["2019"], grid=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["attested_by"], ["shangantong", "xingcezhenti"])

    def test_same_source_twice_dedups(self):
        a = _ev("2019·安徽省公考《申论》题", "linfukai186")
        b = _ev("2019·安徽省公考《申论》题", "linfukai186")
        rows, _, _ = expect.merge_rows([a, b], "", set(), ["2019"], grid=False)
        self.assertEqual(rows[0]["attested_by"], ["linfukai186"])

    def test_distinct_ptype_in_one_cell_are_distinct_rows(self):
        a = _ev("2023·江苏省公考《申论》题（A卷）", "linfukai186")
        b = _ev("2023·江苏省公考《申论》题（B卷）", "linfukai186")
        rows, _, _ = expect.merge_rows([a, b], "", set(), ["2023"], grid=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["ptype"] for r in rows}, {"A类", "B类"})

    def test_attested_by_is_sorted(self):
        a = _ev("2019·安徽省公考《申论》题", "xingcezhenti")
        b = _ev("2019·安徽省公考《申论》题", "catalog")
        rows, _, _ = expect.merge_rows([a, b], "", set(), ["2019"], grid=False)
        self.assertEqual(rows[0]["attested_by"], ["catalog", "xingcezhenti"])


class TestWhitelist(unittest.TestCase):
    """A4：region 白名单只补 `深圳`/`广州`；`region=""` 允许非零。"""

    def test_shenzhen_and_guangzhou_are_whitelisted(self):
        self.assertIn("深圳", expect.REGION_WORDS)
        self.assertIn("广州", expect.REGION_WORDS)

    def test_shenzhen_title_gets_region(self):
        p = expect.parse_title("2022年深圳市公务员考试《申论》试题（一卷）")
        self.assertEqual(p["region"], "深圳")
        self.assertEqual(p["level"], "省考")

    def test_guangzhou_title_gets_region(self):
        p = expect.parse_title("2018年广州市公务员考试《行测》题")
        self.assertEqual(p["region"], "广州")

    def test_whitelist_does_not_expand_the_skeleton(self):
        # 骨架仍是 31 省 + 国考 = 704 格（白名单不入骨架）
        self.assertEqual(len(expect.GRID_REGIONS), 32)
        self.assertNotIn("深圳", expect.GRID_REGIONS)
        self.assertNotIn("广州", expect.GRID_REGIONS)
        years = [str(y) for y in range(2016, 2027)]
        rows, _, _ = expect.merge_rows([], "", set(), years, grid=True)
        self.assertEqual(len(rows), 704)

    def test_blank_region_rows_are_allowed_and_explainable(self):
        p = expect.parse_title("2016年423联考《行测》题（网友回忆整理版）")
        self.assertEqual(p["region"], "")
        e = expect._ev(p, "xingcezhenti")
        rows, _, _ = expect.merge_rows([e], "", set(), ["2016"], grid=False)
        self.assertIn("地区未归位", rows[0]["note"])


class TestGrid(unittest.TestCase):
    def test_skeleton_is_704_cells(self):
        years = [str(y) for y in range(2016, 2027)]
        rows, bj, _ = expect.merge_rows([], "", set(), years, grid=True)
        self.assertEqual(len(rows), 32 * 11 * 2)
        self.assertEqual(len(rows), 704)
        self.assertEqual(bj, [])
        regions = {r["region"] for r in rows}
        self.assertEqual(len(regions), 32)
        self.assertIn("国考", regions)

    def test_cell_attested_with_other_ptype_gets_no_placeholder_row(self):
        # 回归：骨架判据是**格级**——该格已有 A类 证据，就**不得**再补一行占位「统考」
        e = _ev("2023·江苏省公考《行测》题（A类）", "xingcezhenti")
        rows, _, _ = expect.merge_rows([e], "2016", set(),
                                       [str(y) for y in range(2016, 2027)], grid=True)
        cell = [r for r in rows if r["region"] == "江苏" and r["year"] == "2023"
                and r["subject"] == "行测"]
        self.assertEqual([r["ptype"] for r in cell], ["A类"])
        self.assertEqual(len(rows), 704)

    def test_since_filters_evidence(self):
        old = _ev("2015·山东省公考《申论》题", "linfukai186")
        rows, _, _ = expect.merge_rows([old], "2016", set(), ["2016"], grid=False)
        self.assertEqual(rows, [])


class TestCatalogSource(unittest.TestCase):
    def test_pseudo_region_duoshengliankao_becomes_bingjuan_evidence(self):
        # A2：伪地区行**不再**被丢，转成并卷证据（供交付路径闭合）
        d = _catalog_dir([
            _cat("省考-多省联考-2023-申论-统考", "省考", "多省联考", "2023", "申论",
                 "统考", "2023·公务员多省联考"),
            _cat("省考-山东-2019-申论-统考", "省考", "山东", "2019", "申论", "统考",
                 "2019·山东省公考"),
        ])
        evs = expect.ev_catalog(d)
        self.assertEqual(len(evs), 2)
        bj = [e for e in evs if e["bingjuan"]]
        self.assertEqual(len(bj), 1)
        self.assertEqual(bj[0]["ptype"], "并卷")
        sd = [e for e in evs if not e["bingjuan"]][0]
        self.assertEqual(sd["region"], "山东")
        self.assertEqual(sd["md_rel"], "省考/山东/2019/申论-统考.md")

    def test_guokao_region_is_normalized_to_guokao(self):
        d = _catalog_dir([
            _cat("国考-2025-行测-副省级", "国考", "", "2025", "行测", "副省级", "2025·国考"),
        ])
        evs = expect.ev_catalog(d)
        self.assertEqual(evs[0]["region"], "国考")
        # 交付树路径仍按 catalog 的 `region=""` 规则给（repo_paths 只看 level）
        self.assertEqual(evs[0]["md_rel"], "国考/2025/行测-副省级.md")

    def test_catalog_raw_ptype_is_preserved_for_audit(self):
        d = _catalog_dir([_cat("省考-山东-2019-申论-乡镇卷", "省考", "山东", "2019",
                               "申论", "乡镇卷")])
        e = expect.ev_catalog(d)[0]
        self.assertEqual(e["ptype_raw"], "乡镇卷")
        self.assertEqual(e["ptype"], "乡镇")     # 匹配用 canonical
        self.assertFalse(e["verify"])            # A3：交付树行**不**按标题降级


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
        self.assertEqual(shen["region"], "深圳")      # A4：深圳已进白名单
        self.assertEqual(shen["ptype"], "一卷")        # A1：源侧出规范词
        gk = by_title["2022年国家公务员考试《申论》试题（副省级）"]
        self.assertEqual(gk["level"], "国考")
        self.assertEqual(gk["region"], "国考")
        self.assertEqual(gk["ptype"], "副省级")

    def test_missing_manifest_is_empty_not_error(self):
        self.assertEqual(expect.ev_slb(tempfile.mkdtemp()), [])


class TestSessionDecoupled(unittest.TestCase):
    """A6：`ptype` 与 `session` **脱钩**，`ptype` 永不含 上半年/下半年。"""

    def test_parse_never_puts_session_into_ptype(self):
        rows, bj, _ = expect.merge_rows(
            [_ev("2019·公务员多省联考《申论》题（重庆上半年卷）", "linfukai186"),
             _ev("2019·公务员多省联考《申论》题（重庆下半年卷）", "linfukai186")],
            "", set(), ["2019"], grid=False)
        self.assertEqual(len(rows), 2)
        for r in rows:
            for w in expect.SESSIONS:
                self.assertNotIn(w, r["ptype"], r)
        self.assertEqual({r["session"] for r in rows}, {"上半年", "下半年"})

    def test_canon_ptype_returns_session_separately(self):
        self.assertEqual(expect.canon_ptype("上半年行政执法卷"),
                         ("行政执法", "上半年"))
        self.assertNotIn("上半年", expect.canon_ptype("上半年行政执法卷")[0])

    def test_catalog_session_is_split_out_of_raw_ptype(self):
        d = _catalog_dir([_cat("省考-四川-2019-申论-下半年", "省考", "四川", "2019",
                               "申论", "下半年", "2019·四川省公考《申论》题（下半年）")])
        e = expect.ev_catalog(d)[0]
        self.assertEqual(e["session"], "下半年")
        self.assertNotIn("下半年", e["ptype"])


class TestJsonlContract(unittest.TestCase):
    def test_fields_are_exactly_the_fixed_ten_in_order(self):
        self.assertEqual(expect.JSONL_FIELDS,
                         ("level", "region", "year", "subject", "session", "ptype",
                          "status", "attested_by", "delivered_md", "note"))

    def test_projection_hides_internal_keys(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, _, _ = expect.merge_rows([e], "", set(), ["2019"], grid=False)
        proj = {k: rows[0][k] for k in expect.JSONL_FIELDS}
        self.assertNotIn("_verify", proj)
        self.assertEqual(set(proj), set(expect.JSONL_FIELDS))

    def test_year_is_str_and_status_in_enum(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, _, _ = expect.merge_rows([e], "", set(), ["2019"], grid=False)
        self.assertIsInstance(rows[0]["year"], str)
        self.assertIn(rows[0]["status"], ("已有", "源有未导入", "尚未找到", "待核实"))

    def test_render_md_has_the_eight_required_sections(self):
        e = _ev("2019·山东省公考《申论》题", "linfukai186")
        rows, bj, ngs = expect.merge_rows([e], "2016", set(), ["2019"], grid=True)
        txt = expect.render_md(rows + bj, bj, ngs, "2016", len(rows))
        for head in ("## 一、口径声明", "## 二、总量", "## 三、按 `status` × 科目",
                     "## 四、缺卷清单", "## 五、并卷键清单", "## 六、`region=\"\"` 行",
                     "## 七、非国省考", "## 八、诚实边界"):
            self.assertIn(head, txt)
        self.assertIn("不等于", txt.replace("**", "").replace("`", ""))

    def test_render_md_states_the_disclaimers_verbatim(self):
        rows, bj, ngs = expect.merge_rows([], "2016", set(), ["2016"], grid=True)
        txt = expect.render_md(rows + bj, bj, ngs, "2016", 0)
        self.assertIn("本机所有来源都没提到", txt)
        self.assertIn("绝不表示该考试没有举行", txt)
        self.assertIn("不是地区", txt)

    def test_render_md_totals_are_mutually_consistent(self):
        # A5：md 内所有合计**同源**（都从最终行集导出）
        evs = [_ev("2019·山东省公考《申论》题", "linfukai186"),
               _ev("2019·安徽省公考《行测》题", "xingcezhenti")]
        rows, bj, ngs = expect.merge_rows(evs, "2016", set(), ["2016", "2019"], grid=True)
        allr = rows + bj
        txt = expect.render_md(allr, bj, ngs, "2016", len(evs))
        self.assertIn("应有总数**（本账总行数） | **%d**" % len(allr), txt)
        self.assertIn("== `EXPECTED.jsonl` 行数 **%d**" % len(allr), txt)
        xc = sum(1 for r in allr if r["subject"] == "行测")
        sl = sum(1 for r in allr if r["subject"] == "申论")
        self.assertIn("| **合计** | **%d** | **%d** | **%d** |" % (xc, sl, len(allr)), txt)

    def test_render_ptype_map_lists_delivery_raw_values(self):
        d = _catalog_dir([_cat("省考-山东-2019-申论-乡镇卷", "省考", "山东", "2019",
                               "申论", "乡镇卷"),
                          _cat("省考-上海-2016-申论-A类", "省考", "上海", "2016",
                               "申论", "A类")])
        evs = expect.ev_catalog(d) + [_ev("2019·安徽省公考《申论》题（A卷）", "linfukai186")]
        txt = expect.render_ptype_map(evs, "2016")
        self.assertIn("| `乡镇卷` | 1 | `乡镇` |", txt)
        self.assertIn("| `A类` | 1 | `A类` |", txt)
        self.assertIn("| `A卷` | 1 | `A类` |", txt)
        self.assertIn("被归一压平的组", txt)


if __name__ == "__main__":
    unittest.main()
