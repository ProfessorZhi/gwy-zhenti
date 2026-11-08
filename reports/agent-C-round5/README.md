# 144 道 import-ready 候选（0 写入）

## 结果

| 目标卷 | 完整候选 |
|---|---:|
| 兵团2023 行测 | 74 |
| 宁夏2022 行测 | 47 |
| 兵团2022 行测 | 18 |
| 内蒙古2024 行测 | 5 |
| **合计** | **144** |

- 144 条均含题干、A–D 四选项、答案、`answer_source`、前后锚点；见 `candidates.jsonl`。
- **0 条写入题卷**：四个目标卷在 main 均无正式题本；题量/缺段存在 103/104、121/125、115/102、72/未知 的冲突，建部分卷需先由维护者选定总数并同意新增占位。
- 20 条 `LOW_CONFIDENCE_MATCH`、117 条 `ANSWER_NOT_FOUND`，以及 53 缺选项/49 缺图/10 非原源/8 遮蔽/6 占位/3 答案冲突/2 选项损坏，全部不写。
- 缺口统计不变：本分支（基于 #194）缺卷 51、待核 15、行测缺题干 261。

## 文件

- `intake-audit.md`：规范审计、四个目标卷的题量/缺段/答案性质、0 写入理由。
- `candidates.jsonl`：144 条 import-ready 记录（`status=import_ready_not_written`；`plan_blocker` 说明缺目标卷）。
- `audit.csv`：412 行逐题审计（含 20 低置信、117 无答案、53 缺选项、49 缺图等）。
- `source-evidence.json`：四个题干页 URL/状态/字节数/SHA256。
- `README.md`：本文件。

## 下一步（需维护者决策）

1. 同意“部分卷入库”后，为四卷各选定一个总题量（兵团2023 103/104、宁夏2022 121/125、兵团2022 115、内蒙古2024 待定），建立带占位的卷骨架。
2. 用 `source_fill.py` 的 source_snapshot 门禁逐题写入；跨省答案必须在 `来源清单`/正文 `来源` 中写明“甘肃/陕西/四川同题答案 + 内容映射”，不得写成官方答案。
3. 部分卷的占位由 `gap_report.py` 真实计入缺题干，禁止手工调数。

## 边界

未改题卷、未改槽位、未改缺口统计；未合并任何 PR；未绕验证码/会员/403/429；未用 AI 生成题干/选项/答案。

## 2026-11-08 第六轮候选台账更新（B round5 / D 审计）

`candidates.jsonl` 由 144 更新为 **170 条**，按证据等级分层（**不都是可入库**）：

| 层级 | 数量 | 含义 |
|---|---:|---|
| `D_ACCEPT` | 139 | Agent D 逐条审计内容 accept；目标卷槽位仍阻塞 |
| `D_NEEDS_MORE_EVIDENCE` | 5 | 内蒙古2024；D 认为无 q±1 锚点，保留 needs-more |
| `B_RESOLVED_PENDING_D_AUDIT` | 20 | B round5 消除的旧低置信；**D 尚未逐条审计** |
| `B_NEW_PENDING_D_AUDIT` | 6 | B round5 从 unresolved 新增；**D 尚未审计** |
| **合计** | **170** | 139+5+20+6；不等于 170 可入库 |

- B 的 26 条与旧 144 条按 `(target_paper,target_q)` 和 `(target_paper,source_q,answer)` 均 **0 重叠**；已合并且不重复计数。
- **0 条写入 main**：兵团2022/2023 槽位仍待核，宁夏2022/内蒙古2024 仍缺卷；建卷/改槽位前 `source_fill.py` 无法写。
- B 报告的 111 条 unresolved 继续留缺；20 低置信由 B 解决 **不等于** D 已审计通过。
- 缺口不因候选抵扣：行测缺题干 261、缺选项 4、缺卷 51、待核 15（本分支基于 main）。
- 明细：`audit-status.csv`；逐条 `d_verdict`/`d_audited`/`d_write_verdict` 在 `candidates.jsonl`。
