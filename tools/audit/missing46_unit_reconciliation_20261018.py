#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""46 专项缺口与 47 资料缺档的单位对账（只读）。

本工具只做三件事：
  1. 用 MISSING48-RECOVERY 的**实际字段**重算缺卷单位（不手抄数字）；
  2. 把 46 目标与 资料缺失/INDEX.jsonl 的 47 格按 (地区,年份,科目) 去重；
  3. 输出各单位的独立计数与**不可相加**声明。

不读正文、不写正式卷、不复制第三方文本。
"""
from __future__ import annotations
import json, os, sys, collections

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")

# ── 9 个非本 Lane 目标的身份判定（本轮 4 条有界检索所得） ─────────────────────
E_ZJ_C = {  # 江苏 2023 行测 C
    "tier": "official_outline",
    "finding": "江苏 2023 分级分类 A/B/C 三类；C 类适用乡镇(街道)机关, 行测 130 题",
    "urls": ["http://jshrss.jiangsu.gov.cn/art/2022/11/4/art_87130_10651727.html",
             "https://www.huatu.com/2022/1103/2585043.html"],
}
E_BJ_2024 = {
    "tier": "official_announcement",
    "finding": "北京 2024 年度京考公共科目笔试 2023-12-03 举行（上午行测/下午申论）；公告未使用『统一卷』一词",
    "urls": ["https://www.beijing.gov.cn/gongkai/rsxx/gwyzk/202311/t20231110_3299396.html",
             "https://www.bjdj.gov.cn/article/3000193824.html"],
}
E_FJ_2026 = {
    "tier": "official_guide",
    "finding": "福建 2026 申论为双卷：A类(省市综合管理卷) 与 A类(通用卷)；往年县乡/执法并入通用卷",
    "urls": ["https://jyw.fjpsc.edu.cn/index.php/home/article/35775",
             "https://m.qz.bendibao.com/job/37206.shtm"],
    "disagreement": "另有易考吧解读仍称三卷（省市/县乡/执法），与官方报考指南的双卷表述冲突；以官方指南为准",
}
E_SZ_2024 = {
    "tier": "official_syllabus",
    "finding": "深圳 2024 申论按职位设 Ⅰ类/Ⅱ类 两套（民间称一卷/二卷），150 分钟 100 分",
    "urls": ["http://www.offcn.com/gdgwy/2023/1206/32682.html",
             "http://ww.chinagwyw.org/guangdong/656924.html"],
}

NINE = {
    ("江苏", 2023, "行测", "C"): ("confirmed_missing", E_ZJ_C, "库内江苏2023仅有行测A/B，C类缺"),
    ("江苏", 2026, "行测", "A"): ("partial_existing",
                                 {"tier": "registry", "finding": "登记状态 partial_source_recovered_not_a_complete_paper", "urls": []},
                                 "库内文件存在但登记为残卷，非完整卷"),
    ("江苏", 2026, "行测", "B"): ("plausible_unconfirmed",
                                 {"tier": "inference", "finding": "江苏实行 A/B/C 分级分类（2023 大纲证实）；2026 专项证据本轮未取得", "urls": []},
                                 "存在性由同类分类体系推断，未取得 2026 直接卷证"),
    ("江苏", 2026, "行测", "C"): ("plausible_unconfirmed",
                                 {"tier": "inference", "finding": "同上", "urls": []},
                                 "存在性由同类分类体系推断，未取得 2026 直接卷证"),
    ("北京", 2024, "行测", "统一卷"): ("confirmed_missing", E_BJ_2024,
                                     "京考 2024 确已举行；『统一卷』是本库内部标签，不是官方卷型名"),
    ("北京", 2026, "行测", "统一卷"): ("partial_existing",
                                     {"tier": "registry", "finding": "登记状态 partial_source_recovered_not_a_complete_paper", "urls": []},
                                     "库内文件存在但登记为残卷"),
    ("福建", 2026, "申论", "省市综合管理"): ("confirmed_missing", E_FJ_2026,
                                         "2026 福建申论双卷；库内仅通用卷"),
    ("深圳", 2024, "申论", "Ⅰ"): ("confirmed_missing", E_SZ_2024,
                                 "深圳申论 Ⅰ/Ⅱ 两类；库内仅二卷"),
    ("北京", 2026, "申论", "统一卷"): ("partial_existing",
                                     {"tier": "registry", "finding": "登记状态 source_has_only_material1_and_four_tasks_materials2_to10_missing", "urls": []},
                                     "仅有材料1与四道题，材料2–10 缺失"),
}


def build(root: str) -> dict:
    with open(os.path.join(root, "reports/MISSING48-RECOVERY-20261016.json"), encoding="utf-8") as fh:
        reg = json.load(fh)
    T = reg["targets"]
    rec = [t for t in T if t["counted_as_recovered_this_round"]]
    rem = [t for t in T if not t["counted_as_recovered_this_round"]]

    def key(t): return (t["area"], int(t["year"]), t["subject"], t["variant"])
    mine = [t for t in rem if t["area"] in ("浙江", "上海", "天津")]
    other = [t for t in rem if t["area"] not in ("浙江", "上海", "天津")]

    # 单位 A：缺完整参考卷（paper slot）
    unitA = {
        "unit": "paper_slot（地区×年份×科目×卷型）",
        "targets_total": len(T),
        "recovered_this_round": len(rec),
        "recovered_list": [dict(area=t["area"], year=t["year"], subject=t["subject"], variant=t["variant"]) for t in rec],
        "remaining": len(rem),
        "declared_remaining": reg["remaining_targets_without_complete_reference_version"],
        "remaining_by_subject": dict(collections.Counter(t["subject"] for t in rem)),
        "remaining_by_area": dict(collections.Counter(t["area"] for t in rem)),
        "all48_by_subject": dict(collections.Counter(t["subject"] for t in T)),
        "lane_37": {"count": len(mine), "by_subject": dict(collections.Counter(t["subject"] for t in mine))},
        "other_9": {"count": len(other), "by_subject": dict(collections.Counter(t["subject"] for t in other))},
    }
    assert unitA["remaining"] == unitA["declared_remaining"] == 46
    assert unitA["lane_37"]["count"] + unitA["other_9"]["count"] == 46

    slots9 = []
    for t in sorted(other, key=key):
        k = (t["area"], int(t["year"]), t["subject"], t["variant"])
        verdict, ev, note = NINE[k]
        slots9.append({
            "area": t["area"], "year": int(t["year"]), "subject": t["subject"],
            "variant": t["variant"], "registry_status": t["status"],
            "classification": verdict, "evidence": ev, "note": note,
        })
    assert len(slots9) == 9, len(slots9)

    # 单位 B：资料缺档/待核（cell）
    with open(os.path.join(root, "资料缺失/INDEX.jsonl"), encoding="utf-8") as fh:
        idx = [json.loads(l) for l in fh if l.strip()]
    cells = []
    for r in idx:
        p = r["path"].split("/")
        cells.append({"area": p[2], "year": int(p[3]), "subject": p[4].replace(".md", ""),
                      "state": r["state"], "evidence": r.get("evidence", "")})
    unitB = {
        "unit": "cell（地区×年份×科目；无卷型维度）",
        "total": len(cells),
        "by_state": dict(collections.Counter(c["state"] for c in cells)),
        "by_area": dict(collections.Counter(c["area"] for c in cells)),
        "cells": sorted(cells, key=lambda c: (c["area"], c["year"], c["subject"])),
    }
    assert unitB["total"] == 47

    # 去重：(地区,年份,科目) 是否同时出现在两个单位
    a_keys = {(t["area"], int(t["year"]), t["subject"]) for t in rem}
    b_keys = {(c["area"], c["year"], c["subject"]) for c in cells}
    overlap = sorted(a_keys & b_keys)
    return {
        "generated": "2026-10-18",
        "baseline_pr": 20,
        "baseline_head": "e1feb5187ec3544cde62a1a128a6269a8d63011b",
        "unit_a_missing_papers": unitA,
        "unit_b_material_cells": unitB,
        "dedupe": {
            "overlap_cells": overlap,
            "overlap_count": len(overlap),
            "distinct_rows_across_units": unitA["remaining"] + unitB["total"],
            "note": "两单位粒度不同且本轮实测零重叠；其和 93 只能称『两条独立账的合计行数』，不得称为『93 份缺卷』",
        },
        "non_additivity_rules": [
            "整卷缺口（unit A）与资料缺档格（unit B）是不同粒度，禁止相加成单一缺口数",
            "『缺原题 106 道』是题级计数，禁止与 46 整卷相加或互替",
            "残卷（partial_existing）既不算已恢复，也不并入完全缺失",
            "待核实 18 格不得并入资料缺失 29 格",
        ],
        "pr74_reconciliation": {
            "pr74_claim": "46 = 21 申论整卷 + 25 行测缺原题（自述『单位不同』仍相加）",
            "registry_recomputed": "46 = 19 申论 + 27 行测（皆为 paper_slot）",
            "explanation": "登记的 2 个已恢复目标（江苏2026 申论A、申论C）都是申论；"
                           "21 是 48 个目标的申论总数，减 2 后应为 19。"
                           "PR#74 把 21 留在申论、却从行测 27 里减了 2，且把行测项写成『缺原题』这一题级单位。",
            "correction": {"essay": 19, "aptitude": 27},
        },
        "classification_counts_9": dict(collections.Counter(s["classification"] for s in slots9)),
        "slots_9": slots9,
        "new_complete_licensed_papers_this_round": 0,
        "new_external_source_receipts_this_round": 0,
    }


if __name__ == "__main__":
    d = build(ROOT)
    out = os.path.join(ROOT, "reports/MISSING46-UNIT-RECONCILIATION-20261018.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps({
        "unitA_remaining": d["unit_a_missing_papers"]["remaining"],
        "unitA_by_subject": d["unit_a_missing_papers"]["remaining_by_subject"],
        "unitB_total": d["unit_b_material_cells"]["total"],
        "unitB_by_state": d["unit_b_material_cells"]["by_state"],
        "overlap_count": d["dedupe"]["overlap_count"],
        "class9": d["classification_counts_9"],
        "new_complete_papers": d["new_complete_licensed_papers_this_round"],
    }, ensure_ascii=False, indent=1))
