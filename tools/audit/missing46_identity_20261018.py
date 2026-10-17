#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""申论原卷完整性来源 Lane：浙江/上海/天津 37 槽位的身份判定账本（只读生成）。

数据来源：
  reports/MISSING48-RECOVERY-20261016.json  —— 槽位真相（48 目标，2 已收，余 46）
  reports/MISSING48-PUBLIC-SOURCE-CHECKS-20261016.json —— 已尝试且被阻断的来源（不得重试）

本工具不读正文、不写正式卷，只把已核实的身份证据整理成机器可核对的账本。
"""
from __future__ import annotations
import json, os, sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")

# ── 证据常量（本轮实际检索所得；URL 仅作元数据出处，不复制正文） ──────────────
E_ZJ_VILLAGE_16_18 = {
    "tier": "public_secondary",
    "finding": "浙江省考优秀村干部类笔试为《行政职业能力测验》(C卷)+《综合应用能力》，不含《申论》",
    "urls": [
        "https://m.huatu.com/zhaojing/news/zhejiang/2017/1117/1605742.html",
        "http://www.offcn.com/zjgwy/2017/0905/19442_2.html",
        "https://news.koolearn.com/20171116/1139970_3.html",
    ],
}
E_ZJ_VILLAGE_SINCE_21 = {
    "tier": "public_secondary",
    "finding": "自2021年起浙江行测分A/B/C/D卷，D卷对应优秀村干部类；主观题为《综合应用能力》，不含《申论》",
    "urls": [
        "https://www.huatu.com/2022/1208/2598681.html",
        "http://www.haining.gov.cn/art/2022/2/23/art_1688835_161814.html",
    ],
}
E_ZJ_2022_RESTART = {
    "tier": "official_announcement",
    "finding": "2022年浙江省考笔试2022-07-09；《申论》按职位分A/B/C三卷（综合类/基层类/行政执法类）",
    "urls": [
        "https://www.zj.gov.cn/art/2022/6/12/art_9614088_59711702.html",
        "https://www.hangzhou.gov.cn/art/2022/6/22/art_1229063420_4054783.html",
    ],
}
E_ZJ_2022_A_THEMES = {
    "tier": "public_secondary",
    "finding": "2022浙江申论A的主题（充电桩问题与建议、小微企业座谈发言提纲、民生服务作文）见机构分析，但无完整给定材料与逐字作答要求",
    "urls": [
        "https://www.eoffcn.com/kszx/detail/1029502.html",
        "https://yuantuedu.com/list_19/10686.html",
    ],
}
E_SH_ESSAY_AB = {
    "tier": "public_secondary",
    "finding": "上海市考《申论》按职位分A卷/B卷两类，4题、150分钟、满分100分；A/B之外无第三种市考申论卷",
    "urls": [
        "https://m.huatu.com/2023/0717/2668510.html",
        "https://www.huazhi.cn/view-35684-1.html",
        "https://gwy.gkzhenti.cn/paper?cls=%E7%94%B3%E8%AE%BA&province=%E4%B8%8A%E6%B5%B7",
    ],
}
E_SH_ZHIFA_EXAM = {
    "tier": "public_secondary",
    "finding": "上海行政执法类公务员为独立招录考试（2016年起，城管+市场监管），9月笔试，一张卷=行测+《申论(行政执法类)》；申论3题、120分钟，与市考4题不同卷",
    "urls": [
        "https://www.sohu.com/a/484531334_139324",
        "https://zhuanlan.zhihu.com/p/398071724",
        "https://m.huatu.com/2025/0811/2828448.html",
    ],
}
E_SH_2021_QUOTA = {
    "tier": "public_secondary",
    "finding": "2021年上海行政执法类公务员招录480名，笔试上午申论(行政执法类)、下午行测，申论三题",
    "urls": ["https://www.sohu.com/a/484531334_139324"],
}
E_TJ_2024_2026 = {
    "tier": "public_secondary",
    "finding": "天津申论分级分类：综合市区卷/综合街镇卷/行政执法卷三类并行（2024、2026 均如此），150分钟满分100分",
    "urls": [
        "https://m.tj.bendibao.com/job/162361.shtm",
        "http://m.offcn.com/tjgwy/2025/1105/30544.html",
        "https://m.huatu.com/2025/1210/2842909.html",
    ],
}


def slots():
    """37 槽位判定表。status 取值见 STATUS_VALUES。"""
    S = []
    def add(area, year, subject, variant, existence, identity, status, evid, note=""):
        S.append(dict(area=area, year=year, subject=subject, variant=variant,
                      paper_existence=existence, paper_identity=identity,
                      completeness_status=status, evidence=evid, note=note))

    # ── 浙江 15 ────────────────────────────────────────────────────────────
    for y in (2016, 2017, 2018, 2019, 2020):
        if y in (2016, 2018):
            ex, ev = "confirmed_public_secondary", [E_ZJ_VILLAGE_16_18]
        else:
            ex, ev = "not_confirmed_this_run", [E_ZJ_VILLAGE_16_18]
        add("浙江", y, "行测", "C（优秀村干部）", ex, "independent_paper",
            "source_missing" if ex != "not_confirmed_this_run" else "unknown", ev,
            "该卷为行测C卷；同场主观题是《综合应用能力》而非《申论》，不得计入申论完整率")
    for y in range(2021, 2027):
        add("浙江", y, "行测", "D（优秀村干部）", "confirmed_public_secondary",
            "independent_paper", "source_missing", [E_ZJ_VILLAGE_SINCE_21],
            "该卷为行测D卷；同场主观题是《综合应用能力》而非《申论》，不得计入申论完整率")
    add("浙江", 2022, "行测", "B", "not_confirmed_this_run", "independent_paper", "unknown",
        [{"tier": "prior_repo_report", "finding": "已尝试来源中 kkgwy 只列 2022 行测 A/C、无 B；该清单为空不证明 B 不存在",
          "urls": ["https://www.kkgwy.com/stk/zj/14922.html"]}],
        "浙江2022职位分综合类/基层类/行政执法类/优秀村干部类，理论上应有B类；本轮未取得直接卷证")
    add("浙江", 2022, "申论", "A", "confirmed_official", "independent_paper",
        "partly_observed", [E_ZJ_2022_RESTART, E_ZJ_2022_A_THEMES],
        "已证开考与卷型；仅取得主题级信息，无完整材料与逐字作答要求")
    add("浙江", 2022, "申论", "B", "confirmed_official", "independent_paper",
        "source_missing", [E_ZJ_2022_RESTART], "已证开考与卷型；未取得任何正文")
    add("浙江", 2022, "申论", "C", "confirmed_official", "independent_paper",
        "source_missing", [E_ZJ_2022_RESTART], "已证开考与卷型；未取得任何正文")

    # ── 上海 16（9 行测 + 7 申论） ─────────────────────────────────────────
    sh_apt = [(2017, "A"), (2017, "B"), (2022, "A"), (2022, "行政执法专项"),
              (2023, "B"), (2024, "A"), (2024, "B"), (2024, "行政执法专项"),
              (2025, "行政执法专项")]
    for y, v in sh_apt:
        if v == "行政执法专项":
            add("上海", y, "行测", v, "confirmed_public_secondary",
                "separate_recruitment_exam", "source_missing", [E_SH_ZHIFA_EXAM],
                "属上海行政执法类公务员独立招录（非上海市考）；同一考试另含《申论(行政执法类)》")
        else:
            add("上海", y, "行测", v, "not_confirmed_this_run", "independent_paper",
                "unknown", [E_SH_ESSAY_AB], "市考A/B类为真实分类；本轮未取得该年行测卷证")
    sh_essay = [(2016, "行政执法专项"), (2021, "行政执法专项"), (2022, "行政执法专项"),
                (2022, "A"), (2023, "B"), (2024, "行政执法专项"), (2025, "行政执法专项")]
    for y, v in sh_essay:
        if v == "行政执法专项":
            ev = [E_SH_ZHIFA_EXAM]
            if y == 2021:
                ev = [E_SH_ZHIFA_EXAM, E_SH_2021_QUOTA]
                ex, st = "confirmed_public_secondary", "source_missing"
            elif y in (2016, 2025):
                ex, st = "confirmed_public_secondary", "source_missing"
            else:
                ex, st = "not_confirmed_this_run", "unknown"
            add("上海", y, "申论", v, ex, "separate_recruitment_exam", st, ev,
                "上海行政执法考试为独立招录；申论3题/120分钟，与市考A/B卷(4题/150分钟)不同卷")
        else:
            add("上海", y, "申论", v, "inferred_from_sibling", "independent_paper",
                "unknown", [E_SH_ESSAY_AB],
                "市考申论按A/B两类分卷；本年库内仅见另一类，故本类存在性由同类推断，未单独取卷证")

    # ── 天津 6 ────────────────────────────────────────────────────────────
    add("天津", 2022, "申论", "行政执法", "not_confirmed_this_run", "independent_paper",
        "unknown", [E_TJ_2024_2026], "2022年天津申论的分类面貌本轮未取得直接证据；库内仅有市级/县级")
    add("天津", 2024, "申论", "综合街镇", "confirmed_public_secondary", "independent_paper",
        "source_missing", [E_TJ_2024_2026], "2024年天津申论分综合市区/综合街镇/行政执法三类")
    add("天津", 2024, "申论", "行政执法", "confirmed_public_secondary", "independent_paper",
        "source_missing", [E_TJ_2024_2026], "同上")
    add("天津", 2025, "申论", "行政执法", "not_confirmed_this_run", "independent_paper",
        "unknown", [E_TJ_2024_2026], "2025年分类面貌本轮未取得直接证据")
    add("天津", 2026, "申论", "综合市区", "confirmed_public_secondary", "independent_paper",
        "source_missing", [E_TJ_2024_2026], "2026年天津申论分综合市区/综合街镇/行政执法三类")
    add("天津", 2026, "申论", "综合街镇", "confirmed_public_secondary", "independent_paper",
        "source_missing", [E_TJ_2024_2026], "同上")
    return S


def build(root: str) -> dict:
    with open(os.path.join(root, "reports/MISSING48-RECOVERY-20261016.json"), encoding="utf-8") as fh:
        reg = json.load(fh)
    remaining = {(t["area"], t["year"], t["subject"], t["variant"])
                 for t in reg["targets"] if not t["counted_as_recovered_this_round"]}
    mine = {k for k in remaining if k[0] in ("浙江", "上海", "天津")}
    S = slots()
    got = {(s["area"], s["year"], s["subject"], s["variant"]) for s in S}

    assert len(got) == len(S), "槽位重复"
    assert got == mine, ("槽位与登记不符", sorted(mine - got), sorted(got - mine))

    # 仓库现状：该 (地区,年份) 下是否存在对应科目文件
    for s in S:
        d = os.path.join(root, "省考", s["area"], str(s["year"]))
        files = sorted(os.listdir(d)) if os.path.isdir(d) else []
        s["repo_cell_files"] = files
        s["slot_has_dedicated_file"] = any(
            f.startswith(s["subject"]) and s["variant"].split("（")[0].rstrip("专项") in f
            for f in files
        ) if s["variant"] != "行政执法专项" else any(
            f.startswith(s["subject"]) and "行政执法" in f for f in files)

    from collections import Counter
    return {
        "generated": "2026-10-18",
        "baseline_pr": 20,
        "baseline_head": "e1feb5187ec3544cde62a1a128a6269a8d63011b",
        "registry": "reports/MISSING48-RECOVERY-20261016.json",
        "registry_remaining": len(remaining),
        "lane_slots": len(S),
        "lane_by_area": dict(Counter(s["area"] for s in S)),
        "lane_by_subject": dict(Counter(s["subject"] for s in S)),
        "status_counts": dict(Counter(s["completeness_status"] for s in S)),
        "existence_counts": dict(Counter(s["paper_existence"] for s in S)),
        "identity_counts": dict(Counter(s["paper_identity"] for s in S)),
        "recovered_complete_papers_this_round": 0,
        "blocked_sources_not_retried": "reports/MISSING48-PUBLIC-SOURCE-CHECKS-20261016.json 的 10 个来源",
        "source_policy": "只登记可访问证据与公开元数据；不复制第三方受限正文；不可得即记 source_missing/unknown",
        "slots": sorted(S, key=lambda x: (x["area"], x["year"], x["subject"], x["variant"])),
    }


if __name__ == "__main__":
    d = build(ROOT)
    out = os.path.join(ROOT, "reports/MISSING46-ZJ-SH-TJ-IDENTITY-20261018.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps({k: d[k] for k in ("lane_slots", "lane_by_area", "lane_by_subject",
                                        "status_counts", "existence_counts",
                                        "identity_counts", "recovered_complete_papers_this_round")},
                     ensure_ascii=False, indent=1))
