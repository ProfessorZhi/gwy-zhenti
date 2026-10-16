# 全库质量覆盖矩阵（2026-10-17）

**锚点**: `e1feb5187ec3544cde62a1a128a6269a8d63011b`（PR#20 head）
**生成方式**: `python3 -I tools/qa/coverage_matrix.py --repo . --out coverage-matrix.jsonl`（只读）
**main 观测值**: `34439ace3ad6c0b93b0671b1f76ca4afd6cce06d`

本文件只报告身份、数量、标签与证据粒度。矩阵逐卷数据以脚本输出为准，不在此重复。

---

## 1. 为什么需要这份矩阵

`tools/fenbi/ANSWER-EVIDENCE-SOP.md` 定义了标签词表
（`verified` / `partial` / `conflicting` / `unknown` / `not_applicable`），
但**仓库内没有任何文件对任何一卷真正赋过这些标签**。

后果：`unknown`（从没看过）与 `verified`（看过且通过）在下游报告里无法区分。
本矩阵把标签物化，且采用保守赋值——**只有真的做过来源比对且通过才是 `verified`**。

## 2. 缺口复算（与 `QUALITY-SUMMARY.json` 七项逐字一致）

| 类别 | 总数 | 卷数 |
|---|---:|---:|
| `missing_original` | 106 | 5 |
| `missing_option` | 5 | 2 |
| `missing_shared_condition` | 10 | 2 |
| `missing_stem_condition` | 20 | 2 |
| `missing_stem_figure` | 2 | 2 |
| `material_gap` | 3 | 2 |
| `source_analysis_disagreement` | 7 | 5 |
| `missing_answer` | 6 | 2 |

**106 处的分布**：北京2026 统考 **51**、江苏2026A **42**、广东2020县级 7、江苏2024A 4、浙江2020A 2。
**2026 两卷占 93 处（88%）**——`FULL-REPAIR-20261015.md` 成文时这两卷尚未纳入，
其正文只记 25 处。对外沿用"缺 25 题"会严重低报。

## 3. 标签物化结果（覆盖率真实面貌）

截至本报告，**只有 4 卷做过来源比对**，其余 1165 卷从未比对：

| 卷 | `stem` | 依据 |
|---|---|---|
| 浙江2026C | `verified` | 109/110 严格一致 + 第54题表示等价（单列人工复核） |
| 江苏2024A | `partial` | 采集 135 / 匹配 131；源侧多出 4 题恰为缺号 76/96/110/111 |
| 江苏2025C | **`conflicting`** | 采集 130 / 匹配 **118**；12 处**同号不同内容** |
| 广东2020县级 | **`conflicting`** | 采集 100 / 匹配 **79**；69–75 存在，另有 14 处同号内容差异 |
| 其余 1165 卷 | `unknown` | 从未与来源比对 |

| 维度 | verified | 说明 |
|---|---:|---|
| `answer` | **0 / 1169** | 实站练习页不暴露答案 |
| `explanation` | **0 / 1169** | **仓库内不存在逐卷解析计数** |
| `paper_binding` | 0（全 `unverified`） | 目录响应无 paperId |

- **逐卷图片解码证据只有 2 卷**（`MISSING50-PEER-REVIEW-20261016.json`）。
  其余 1167 卷只有聚合证据（96433 帧、0 失败）。故 `images.decode_verified` 记 `null`、
  `decode_scope` 记 `aggregate-only`——**聚合 passed ≠ 每卷都核过**。
- `whole_paper_acceptance` 1169 卷全为 `not_certified_by_this_audit`。
- `has_answer_content` 1169 卷全为 `true`，不含区分信息。

## 4. 已核实的 source ID（目录实观，非推断）

`省考/浙江/2026/行测-C类.md` = `8399763`（已采集）、
`省考/江苏/2025/行测-C类.md` = `4189916`、
`省考/江苏/2024/行测-A类.md` = `4162243`、
`省考/广东/2020/行测-县级卷.md` = `96785`、
`省考/浙江/2020/行测-A类.md` = `96454`、
`省考/浙江/2020/行测-B类.md` = `96455`。

后三卷目录已确认但**采集 blocked**：目录中无既有练习，点击即创建练习（写操作）。
其余 1163 卷**无源 ID**，不得推断。

## 5. 第三方回忆版与官方原卷

由 frontmatter `真题性质` 派生（**不得升级**）：

| 分级 | 卷数 |
|---|---:|
| `real_exam_provenance_unstated`（标"正式真题"，未声明官方发布） | 827 |
| `third_party_recall`（网友回忆版） | 195 |
| `unstated`（源未标注） | 87 |
| `third_party_compiled`（机构整理，明示非官方原件） | 52 |
| `other` | 8 |

**没有任何一卷声明官方原卷**；全库 421 处明确否认官方身份的措辞。
`real_exam_provenance_unstated` 是**未声明**而非**已证实**。

答案署名（`新增答案性质`，81 卷有值）须与"是否核对过来源"分开报告：
38 卷"独立校算参考答案（非官方，非来源原答案）"、2 卷"已核对同题来源参考答案"、
3 卷标明 AI 辅助且"非官方"。**不得把 AI 编写答文写成官方参考答案。**

## 6. 答案计数两套口径（44 卷冲突，已定消解规则）

manifest `answer_blocks` 与轮次凭据（`FULL-REPAIR-LAYOUT` / `APTITUDE-VERIFICATION`）
对同一卷给出不同"已答数"。实测 44 处冲突中，43 卷 manifest == declared、
39 卷 frontmatter == manifest，而轮次凭据在 37 处 / 6 处**偏低**——
轮次凭据记录的是**当轮之前**的状态。

> **规则：以该卷 frontmatter + 当前 manifest 为准；轮次凭据降为历史证据。冲突保留不删。**

反例（说明为何不能让轮次凭据说话）：
`省考/上海/2016/申论-A类.md` 被记为 `current_answered=[1,2,3]` 且 `current_missing=[]`，
4 题中有 1 题既不在"已答"也不在"缺"，该记录自身不自洽。

## 7. 采集落地后暴露的数据模型缺口（本轮最重要）

第三批实站采集（`reports/FENBI-LIVE-THIRD-BATCH-20261017.md`）取得三卷题面后，
一个 manifest 无法表达的缺口类型浮出水面：

> **`省考/江苏/2025/行测-C类.md` 的 manifest 记 `missing_original_numbers: []`、`issues: []`，
> 即"完整"；但实站 C 类原卷显示，130 题中有 12 题（27、29、35、36、37、42、75、77、78、80、81、85）
> 与库内正文不同——且是**同号不同内容**，不是题号错位。**

manifest 的缺口词表只有"缺号/缺选项/缺材料"这类**缺失**状态，**没有"存在但与来源不符"**这一状态。
因此该卷在机读口径下显示为"已补齐、无问题"，而实际结论应为 `conflicting`。

同类未登记项：**广东2020县级**除 7 个缺号外，实站还显示 14 处同号内容差异
（18,22,64,66,67,79,87,91,92,94,96,98,99,100）并伴随 7 处材料差异与 7 处配图差异，
manifest 完全未记录。

**建议**：给 manifest 增加一个"已比对但与来源不一致"的维度（或把
`FENBI-THREE-PAPER-MATRIX` / 本矩阵的 `labels.*=conflicting` 纳入 QUALITY-SUMMARY 统计），
否则"补录完成"会被读成"内容正确"。本报告不改 manifest，只记录该缺口。

同时提示两处跨 lane 口径需要对齐：

1. `reports/FENBI-THREE-PAPER-MATRIX-20261017.md`（PR#30）以"三卷在官网均无既有练习、
   采集端尚未取得任何题面数据"为前提，把全部面向来源的维度记为 `unknown`。
   该前提已被第三批采集取代——**两份报告同时在库会自相矛盾**。
2. PR#30 的矩阵在**卷级**使用 `same/different/unknown/not_compared`（对齐器原语），
   而 `tools/fenbi/ANSWER-EVIDENCE-SOP.md` 与 `align.mjs` 的**卷级结论**是
   `verified/partial/conflicting/unknown/not_applicable`。两套词表需明确映射关系，
   否则并排阅读时会误判。

## 8. 边界

未修改任何正式卷、缺口数字或图片。未编造题目内容、source ID 或来源结论。
聚合图片证据不得表述为逐卷已验证。详见 `tools/qa/README.md` 的数据契约。
