#!/usr/bin/env python3
"""Render SAMPLE-PLAN.md from frame + sample (reproducible)."""
import json, collections

frame = [json.loads(l) for l in open("frame.jsonl", encoding="utf-8")]
sample = [json.loads(l) for l in open("sample.jsonl", encoding="utf-8")]
summ = json.load(open("sample-summary.json", encoding="utf-8"))

def vb(r):
    v = r["validation"]
    return "candidate" if v.startswith("候选") else ("machine" if v.startswith("机器校验") else "other")

def pct(a, b):
    return f"{a}/{b} ({a / b * 100:.1f}%)" if b else "-"

L = []
L.append("# 92 卷分层抽样计划（AI 辅助阅读，不是人工 L3 验收）")
L.append("")
L.append("## 口径")
L.append("")
L.append("- 抽样框：GitHub `main` = `efea30030300e7bebcff6fbc05802a2ba3893a43` 的 1850 份正式试卷 Markdown。")
L.append("- 固定种子 **20261028**，脚本 `select.py`（可复跑，结果 `sample.jsonl` 逐字节稳定）。")
L.append("- 分层：地区 × 科目为主层（70 层），层内按 **source_validation bucket** 配额、再按年份均匀取；"
         "每层优先取 1 份高风险卷（error×10 + warn×3 + review）。")
L.append("- 16 份为强制入样：8 份任务点名案例 + 8 份高风险模板/来源状态案例（下表 `mand`）。")
L.append("- 规模：**92 份**，等于目标 92（±10% 区间 83–101 内）。")
L.append("")
L.append("## 覆盖率（样本 vs 全库）")
L.append("")
L.append("| 维度 | 全库 | 样本 |")
L.append("|---|---:|---:|")
L.append(f"| 卷数 | {len(frame)} | {len(sample)} |")
L.append(f"| 地区 | {len({r['area'] for r in frame})} | {len({r['area'] for r in sample})} |")
L.append(f"| 年份 | {len({r['year'] for r in frame})} | {len({r['year'] for r in sample})} |")
L.append(f"| 地区×科目 层 | {len({(r['area'], r['subject']) for r in frame})} | {len({(r['area'], r['subject']) for r in sample})} |")
for k in ("行测", "申论"):
    L.append(f"| 科目 {k} | {sum(1 for r in frame if r['subject'] == k)} | {sum(1 for r in sample if r['subject'] == k)} |")
for b in ("candidate", "machine", "other"):
    L.append(f"| 校验 {b} | {sum(1 for r in frame if vb(r) == b)} | {sum(1 for r in sample if vb(r) == b)} |")
for c in ("SOURCE_COMPLETE", "PARTIAL", "MISSING", "CONFLICT", "(none)"):
    f = sum(1 for r in frame if (r["source_class"] or "(none)") == c)
    s = sum(1 for r in sample if (r["source_class"] or "(none)") == c)
    L.append(f"| 来源 {c} | {f} | {s} |")
L.append(f"| 有 review 的卷 | {sum(1 for r in frame if r['risk'].get('counts',{}).get('review',0))} | "
         f"{sum(1 for r in sample if r['risk'].get('counts',{}).get('review',0))} |")
L.append(f"| 含占位(PH001)的卷 | {sum(1 for r in frame if 'PH001' in r['risk'].get('codes',[]))} | "
         f"{sum(1 for r in sample if 'PH001' in r['risk'].get('codes',[]))} |")
L.append("")
L.append("年份覆盖：" + "、".join(sorted({r['year'] for r in sample})))
missing_years = sorted({r['year'] for r in frame} - {r['year'] for r in sample})
if missing_years:
    L.append("")
    L.append("未进入样本的年份：" + "、".join(missing_years) + "（92 份配额下按层内年份均匀取，未覆盖属配额限制，不代表这些年份不审）。")
L.append("")
L.append("## 强制入样（16）")
L.append("")
L.append("| # | 卷 | 理由 |")
L.append("|---:|---|---|")
for r in sample:
    if r["role"] == "mandatory":
        L.append(f"| {r['rank']} | `{r['path']}` | {r['why']} |")
L.append("")
L.append("## 全部 92 份（按路径排序）")
L.append("")
L.append("| # | 角色 | 地区 | 年份 | 科目 | 卷型 | 来源状态 | 路径 |")
L.append("|---:|---|---|---|---|---|---|---|")
for r in sample:
    L.append(f"| {r['rank']} | {r['role']} | {r['area']} | {r['year']} | {r['subject']} | {r['variant']} | "
             f"{r['source_class'] or '无源ID'} | `{r['path']}` |")
L.append("")
L.append("## 阅读强度分配")
L.append("")
L.append("- **完整 AI 辅助阅读评析**：40 份（16 份强制 + 24 份按层抽取），逐题读题干/选项/答案开头/解析开头、"
         "材料每节、表格、图片引用与折叠逻辑。")
L.append("- **结构 + 高风险节点深核**：其余 52 份，逐卷核结构、导航、答案折叠与基线标记行，抽 3 题读全文。")
L.append("- 无论哪种强度，**公式/图片内容一律标 NEEDS_VISUAL_IMAGE**，不臆测未载入的原图。")
L.append("")
open("SAMPLE-PLAN.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print("wrote SAMPLE-PLAN.md", len(L), "lines")
