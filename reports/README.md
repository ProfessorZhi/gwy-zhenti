# 报表索引（reports/）

> 快照：2026-10-27。本目录共 **32 份报表 .md**（根目录 31 份 + `fix-b1-8papers-20261022/RECEIPT.md`），其中 3 份未进下表（`SHENLUN-CAPTURE-INVENTORY-20261022.md`、`SHENLUN-LOCAL-ARCHIVE-PREFLIGHT-20261022.md`、`STRUCTURE-AUDIT-20261023.md`）；另有 27 份 `.json`、20 份 `.jsonl` 机读凭据（含子目录回执）。
> 当前库状态以 [README](../README.md)、[PROGRESS](../docs/PROGRESS.md)、[`catalog/manifest.jsonl`](../catalog/manifest.jsonl) 为准。本页只做入口和状态索引，**不改写、不移动任何报表**。

**状态口径**

- **现行**：结论仍适用，可作为当前依据。
- **历史**：某轮过程记录，数字和范围停留在当时。
- **已被 X 取代**：后续轮次已有同主题的新结论，旧数字不要再用。

**快速入口**

- 看当前规模与规则：[README](../README.md) · [PROGRESS](../docs/PROGRESS.md) · [质量报告](../docs/QUALITY.md)
- 看还没补齐的题：[PAPER-MISSING-SOURCE-CHECK-20261011.md](PAPER-MISSING-SOURCE-CHECK-20261011.md) · [ROUND3-XINGCE-SOURCE-CHECK-20261012.md](ROUND3-XINGCE-SOURCE-CHECK-20261012.md)
- 看最新质量告警与图片状态：[QUALITY-AUDIT.md](QUALITY-AUDIT.md) · [IMAGE-AUDIT-20261023.md](IMAGE-AUDIT-20261023.md)
- 看 AI 生成答案的清理结论：[REMOVED-AI-CONTENT-LEGACY-20261022.md](REMOVED-AI-CONTENT-LEGACY-20261022.md)

---

## 1. 题序、完整性与查源

| 报表 | 日期 | 一句话说明 | 状态 |
|---|---|---|---|
| [PAPER-INTEGRITY-20261011.md](PAPER-INTEGRITY-20261011.md) | 10-11 | 四卷按第三方题本恢复题序与漏题（国考2022、江苏2023B、广东2020县级、浙江2020A），补 9 题；广东 69–75、浙江 49–50 仍缺。 | **现行**（专项结论） |
| [PAPER-MISSING-SOURCE-CHECK-20261011.md](PAPER-MISSING-SOURCE-CHECK-20261011.md) | 10-11 | 上述 9 个缺号的查源记录；明确不拿“暂缺/默认 A”补答案，也不拿乡镇卷顶县级卷。 | **现行** |
| [ROUND3-XINGCE-SOURCE-CHECK-20261012.md](ROUND3-XINGCE-SOURCE-CHECK-20261012.md) | 10-12 | 第三轮 18 个行测缺号的公开候选核查（浙江 2、江苏2024A 4、江苏2025C 12），并记录当轮申论交付验收。 | **现行**（缺号结论）；全库计数已过期 |
| [ANSWER-GAP-AUDIT-20261026.md](ANSWER-GAP-AUDIT-20261026.md) | 10-26 | 全库行测 742 卷 / 86,867 题逐题判「有没有答案」：答案行缺失 0、空值 0；仅 64 卷 291 题在粉笔页面本身就是「全力以赴征集」占位，现场复核 7 卷题号逐一吻合。 | **现行** |
| [ANSWER-GAP-AUDIT-20261027.md](ANSWER-GAP-AUDIT-20261027.md) | 10-27 | 26 份「整卷无答案」逐卷核对：21 份粉笔同卷可整卷对应（11 份已补，10 份是从属佐证版不重复抄录）、1 份部分可补、4 份粉笔目录里根本没有该卷。 | **现行** |
| [MISSING-QUESTIONS-AUDIT-20261027.md](MISSING-QUESTIONS-AUDIT-20261027.md) | 10-27 | 291 个缺题题位（64 卷）全部是粉笔源侧「题目正在全力以赴征集」占位：`cache-has-it` 0、`off-by-index` 0、`source-absent` 291，无题可离线补。 | **现行** |
| [SLOT-AUDIT-20261027.md](SLOT-AUDIT-20261027.md) | 10-27 | 槽位与同槽复核：政策范围内空白槽位 **0**（旧「41」实为 34 个行测标签别名槽 + 7 条 2027 模考条目）；95 组同槽多文件判为重复 71 / 不同卷 23 / 混合 1 / 存疑 0；四川 2017 申论 `78982` 身份待现场核。 | **现行** |
| [fix-b1-8papers-20261022/RECEIPT.md](fix-b1-8papers-20261022/RECEIPT.md) | 10-22 | 八卷（四川2016–18、深圳2025、重庆2016–19）裸 `<` 转义、来源字段与 manifest 修复回执，含逐题指纹核验和深圳2025 q56↔q52 裁定。 | **现行**（已由 #122 合入）；§9 合并状态已过期 |
| [GAP-VS-VERIFY-20261027.md](GAP-VS-VERIFY-20261027.md) | 10-27 | 内容缺失（清单 A）与验证待办（清单 B）分开记：A1 答案缺 71 卷 402 题、A2 申论材料（19 卷 114 则已补，剩 2 卷残卷 + 河南 2018 无原件）、A3 未取得原件 23 卷；B1 人工验收 0/1,850。 | **现行** |
| [ACCEPTANCE-PROTOCOL-20261027.md](ACCEPTANCE-PROTOCOL-20261027.md) | 10-27 | 三层验收口径：L1 结构自洽全库跑完（1,758 过 + 92 卷全归因）、L2 来源一致全量跑完（1,257 卷 / 63,151 题，四类硬缺口 0）、L3 人工通读待做。 | **现行** |

## 2. 材料与排版

| 报表 | 日期 | 一句话说明 | 状态 |
|---|---|---|---|
| [QUALITY-REPAIR-20261012.md](QUALITY-REPAIR-20261012.md) | 10-12 | 第一轮总报告：修改/新增 133 份、补回 113 题、30 份申论导航、23 份申论整卷重整。 | **历史**（R2–R7 接续） |
| [QUALITY-REPAIR-20261012-R2.md](QUALITY-REPAIR-20261012-R2.md) | 10-12 | 第二轮：8 份早年申论残卷从 11 题恢复到 30 题（净补 19），另修江苏2019A 导航。 | **历史**（R3–R7 接续） |
| [QUALITY-REPAIR-20261012-R3.md](QUALITY-REPAIR-20261012-R3.md) | 10-12 | 第三轮：23 份申论（国考2016–2023、浙江2016、江苏答案）题序/分值/字数归位；附浙江2016A 排版复读修正。 | **历史**（R4–R7 接续） |

> 排版与空白类后续操作只有机读凭据：[`LAYOUT-FOLLOWUP-20261012.jsonl`](LAYOUT-FOLLOWUP-20261012.jsonl)（3 行）、[`ROUND3-LAYOUT-FOLLOWUP-20261012.jsonl`](ROUND3-LAYOUT-FOLLOWUP-20261012.jsonl)（1 行）、[`WHITESPACE-FOLLOWUP-20261012.jsonl`](WHITESPACE-FOLLOWUP-20261012.jsonl)（107 行），不单独设报表。

## 3. 申论修复与答案补录

| 报表 | 日期 | 一句话说明 | 状态 |
|---|---|---|---|
| [QUALITY-REPAIR-20261012-R4.md](QUALITY-REPAIR-20261012-R4.md) | 10-12 | 第四轮：31 份申论补 67 处库内同题答案；识别剩余缺答 676。 | **已被 R5 取代** |
| [QUALITY-REPAIR-20261013-R5.md](QUALITY-REPAIR-20261013-R5.md) | 10-13 | 第五轮：41 份补 102 处库内固定版本同题答案；剩余缺答 799。 | **已被 R6 取代** |
| [QUALITY-REPAIR-20261013-R6.md](QUALITY-REPAIR-20261013-R6.md) | 10-13 | 第六轮：80 份补 190 处用户资料原有答案；剩余缺答 609；明确 25 道行测缺题未动。 | **已被 R7 取代** |
| [QUALITY-REPAIR-20261013-R7.md](QUALITY-REPAIR-20261013-R7.md) | 10-13 | 第七轮：738 份申论逐卷验收，缺完整答案/范文 592，新增来源文本 15 段。 | **历史**（最新申论全库轮次；计数停在 10-13） |
| [SOURCED-SUPPLEMENT-20261013.md](SOURCED-SUPPLEMENT-20261013.md) | 10-13 | 来源补录：51 份补 117 处现成参考作答，新增 AI 答文 0；缺答位 451。 | **历史**（10-22 回退后为 475） |
| [SHENLUN-FANWEN-SOURCING-20261013.md](SHENLUN-FANWEN-SOURCING-20261013.md) | 10-13 | 申论参考作答/范文收录口径，以及 5 个同题候选（浙江2025A/2026A、江苏2026B）。 | **现行**（口径）；候选未全部落地 |
| [SHENLUN-SOURCE-AUDIT-20261027.md](SHENLUN-SOURCE-AUDIT-20261027.md) | 10-27 | 577 份新增申论 + 39 份复核逐题对源：真缺陷 8 题（已补）；解析三分类——134 卷 408 题中 49 题源端有文字解析且仓库 49/49 全覆盖、359 题源端本就只有答案与答案解析图；江苏 2026 申论B 与西藏 2019 第4题判粉笔未收录；全仓图片引用 19,907 处断图 0。 | **现行** |
| [NEW-EXTERNAL-SHENLUN-SOURCES-20261013.md](NEW-EXTERNAL-SHENLUN-SOURCES-20261013.md) | 10-13 | 2 篇署名作者同题原稿的外链登记，未复制成本库完整答案。 | **现行**（外链登记） |

## 4. 图片来源与图片完整性

| 报表 | 日期 | 一句话说明 | 状态 |
|---|---|---|---|
| [IMAGE-AUDIT-20261023.md](IMAGE-AUDIT-20261023.md) | 10-23 | 1,422 份 MD、86,858 处图片引用与两处图库交叉核对：断图 0；已删除 66,440 个有副本孤儿（514 MB）、归档 27,773 个唯一孤儿（33 MB），改后断链仍为 0。 | **现行** |
| [FORMULA-TRANSCRIPTION-20261023.md](FORMULA-TRANSCRIPTION-20261023.md) | 10-23 | 行内公式小图（宽 ≤60px）双盲 A/B 转写：4,699 张唯一图、4,398 张两遍一致，映射表按 sha256 全局替换。10-26 在 1,850 卷的 main 上重新套用，命中 24,191 处 / 733 卷。 | **现行** |

> 早期图片专项只有 JSONL 凭据：[`IMAGE-CROP-FOLLOWUP-20261012.jsonl`](IMAGE-CROP-FOLLOWUP-20261012.jsonl)（2 行，浙江2025 分数题裁图上边界）、[`PAPER-INTEGRITY-20261011.jsonl`](PAPER-INTEGRITY-20261011.jsonl)（4 行，含新增解析裁图哈希）。

## 5. 质量汇总、台账与 AI 清理

| 报表 | 日期 | 一句话说明 | 状态 |
|---|---|---|---|
| [QUALITY-AUDIT.md](QUALITY-AUDIT.md) | 10-23（#122 时点） | 规则生成的逐卷告警清单：250 份有告警，当前尾部截断 0；顶部“1291 份”是旧快照。 | **现行**（需按当前 1,422 份重算总数） |
| [PRIORITY-QUALITY-20261012.md](PRIORITY-QUALITY-20261012.md) | 10-12 | 国考/江苏/浙江逐卷质量台账，已接续到第五轮。 | **现行台账**（范围有限；未覆盖 R6/R7 与 AI 回退） |
| [REMOVED-AI-CONTENT-20261022.md](REMOVED-AI-CONTENT-20261022.md) | 10-22 | 第一阶段回退 14 卷 25 处 AI 答案 + 6 处解析；缺答位 426→451。 | **历史**（LEGACY 接续） |
| [REMOVED-AI-CONTENT-LEGACY-20261022.md](REMOVED-AI-CONTENT-LEGACY-20261022.md) | 10-22 | 第二阶段回退 9 卷 24 块早期 AI 作答；全库 AI 标签归零，缺答位 451→475。 | **现行**（AI 清理最终回执）；1243 计数已过期 |

> 机读汇总：[`QUALITY-SUMMARY.json`](QUALITY-SUMMARY.json)、[`DEFECTS.jsonl`](DEFECTS.jsonl)（250 行）、[`PRIORITY-MISSING.json`](PRIORITY-MISSING.json)（10 个重点年度科目格）。其中 `QUALITY-SUMMARY.json` 仍是 1291 份 / 85,360 处引用的旧快照。

---

## 与当前状态不符的历史表述

以下句子写在报表正文里，但按 2026-10-23 的仓库状态已经不成立。**本页只登记，不回改原报表**。

| # | 报表与位置 | 过期原文 | 当前事实 |
|---:|---|---|---|
| 1 | [QUALITY-REPAIR-20261012.md](QUALITY-REPAIR-20261012.md) 第 78 行 | “仓库维持私有，不修改Windows旧工作副本。” | 仓库现为**公开仓库（PUBLIC）**，见 [README](../README.md) 与 [PROGRESS](../docs/PROGRESS.md)。 |
| 2 | [QUALITY-REPAIR-20261012-R2.md](QUALITY-REPAIR-20261012-R2.md) 第 61 行 | “仓库保持私有。” | 同上，现为公开仓库。 |
| 3 | [QUALITY-REPAIR-20261012.md](QUALITY-REPAIR-20261012.md) 第 36 行 | “当前 1191份MD（行测453、申论738）” | 2026-10-23 为 **1,422 份**（行测 533 / 申论 889），图片引用 86,858 处。 |
| 4 | [QUALITY-REPAIR-20261012-R2.md](QUALITY-REPAIR-20261012-R2.md) 第 41 行 | “全库清单1191份” | 同上，现为 1,422 份。 |
| 5 | [ROUND3-XINGCE-SOURCE-CHECK-20261012.md](ROUND3-XINGCE-SOURCE-CHECK-20261012.md) 第 29 行 | “全库1191份MD、118521处图片引用” | 现为 1,422 份 MD、86,858 处图片引用。 |
| 6 | [QUALITY-REPAIR-20261013-R7.md](QUALITY-REPAIR-20261013-R7.md) 第 3 行（第 7、21 行同） | “当前仓库共738份申论MD” | 现为 **889 份申论**；R7 的逐卷表只覆盖 10-13 的 738 份。 |
| 7 | [REMOVED-AI-CONTENT-20261022.md](REMOVED-AI-CONTENT-20261022.md) 第 44、89 行 | “共 1243 卷（manifest 1243 行，申论 749…）”“合并后 1243 行 / 1243 卷” | 现为 **1,422 份**（申论 889）。 |
| 8 | [REMOVED-AI-CONTENT-LEGACY-20261022.md](REMOVED-AI-CONTENT-LEGACY-20261022.md) 第 48 行 | “当前 1243 行 / 1243 卷” | 同上，现为 1,422 份。 |
| 9 | [QUALITY-AUDIT.md](QUALITY-AUDIT.md) 第 4 行 | “正文文件 1291 份” | 现为 1,422 份；告警条目仍需按新清单重生成。 |
| 10 | [fix-b1-8papers-20261022/RECEIPT.md](fix-b1-8papers-20261022/RECEIPT.md) 第 5、9 行 | “基点：af24084a9（= 当前 main HEAD，未改动）”“合并状态：**未合并**” | 该修复已由 **#122（8ffafc8fa，2026-10-23）合入**，且 8ffafc8fa 是当前 HEAD 的祖先；`af24084a9` 已不是当前 main HEAD。 |
| 11 | [fix-b1-8papers-20261022/RECEIPT.md](fix-b1-8papers-20261022/RECEIPT.md) 第 97 行 | “行数不变（1291）” | 该回执写于 1291 行基线；当前清单为 1,422 行。 |
| 12 | [SOURCED-SUPPLEMENT-20261013.md](SOURCED-SUPPLEMENT-20261013.md) 第 11 行 | “仍缺已识别完整答文位置”一栏记的 451 | 10-22 第二阶段 AI 回退后该口径为 **475**；451 已不是最新值。 |

**口径说明**

- 本目录没有把“515 卷”当作本库统计：该数字只出现在 [SOURCES.md](../docs/SOURCES.md) 对上游 README 的转述里。
- “2016 年起收录”也不在 reports/ 内作为结论出现；仓库已在 2026-10-23 取消 2016 年份下限（提交 `2766a7a81`）。引用旧报表时不要把它当现行范围。
- 上述 12 处分布在 9 份报表；其余轮次数字（如 R4 的 676、R5 的 799、R6 的 609）是各轮“当时剩余”，已在分组状态中标为被下一轮取代，不再逐条列入本表。
