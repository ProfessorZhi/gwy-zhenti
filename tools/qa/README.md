# 质量覆盖 QA（只读）

`tools/qa/` 提供跨 lane 的统一质量台账，供任何 lane 的产出并入同一坐标系。

```bash
python3 -I tools/qa/coverage_matrix.py --repo . --out coverage-matrix.jsonl
```

只读：不写正式卷、不改缺口数字、不合并任何分支、不访问网络。

## 数据契约

### 连接键

**`path`** —— 仓库相对路径，正斜杠，含中文，不带引号，例 `省考/浙江/2026/行测-C类.md`。

- 唯一性：`catalog/manifest.jsonl` 1169 行，path 无重复。
- **不要用 `sha256` 做连接键**——同一卷多轮修复会变；`sha256` 只用于校验当前树。
- **不要用题号做跨卷键**——同年 A/B/C 卷题号不通用。

### 质量标签（每维度独立）

词表出自 `tools/fenbi/ANSWER-EVIDENCE-SOP.md`：
`verified` / `partial` / `conflicting` / `unknown` / `not_applicable`。

**赋值铁律：只有真的做过来源比对且通过，才可写 `verified`。**
"从没比过"一律 `unknown`——不是 `verified`，也不是 `partial`。

| 维度 | 当前可达最好状态 | 理由 |
|---|---|---|
| `stem` `options` `number` `materials` | 仅浙江2026C `verified`，其余 1168 卷 `unknown` | 只有该卷做过逐题严格比对 |
| `images` | 浙江2026C `partial` | 21 同 / 3 字节不同但内容等价 / 85 未比 |
| `answer` | 全部 `unknown` | 实站练习页不暴露答案 |
| `explanation` | 全部 `unknown` | 仓库内不存在逐卷解析计数 |
| `paper_binding` | 全部 `unverified` | 目录响应无 paperId |

`not_applicable` 必须与结论同时出现，不得省略成"全部通过"。
例：行测 DOM 命名空间与库内数字 qid 不同，逐题 ID 比对本就无从进行——记为
`not_applicable`，既不算通过也不算缺口。

### 来源分级（不得升级）

| `source_class` | 含义 |
|---|---|
| `real_exam_provenance_unstated` | 标"正式真题"，**未声明官方发布** |
| `third_party_recall` | 明确"网友回忆版" |
| `unstated` | "源未标注" |
| `third_party_compiled` | 明确"机构整理…非官方原件" |

**没有任何一卷声明官方原卷。** 未声明 ≠ 已证实，报表中不得简写成"官方真题"。

答案署名须与"是否核对过来源"**分开**报告：
**(a)** 有没有答文；**(b)** 谁写的；**(c)** 有没有和来源核对过。
禁止把 AI 编写/校算答文写成官方参考答案。

### 图片证据粒度

仓库只有**聚合**证据（`FREE-TOOLS-INDEX-IMAGE-PIXELS-20261016.json`：96433 帧、0 失败）。
**逐卷**证据只有 2 卷（`MISSING50-PEER-REVIEW-20261016.json`）。
故 `decode_verified` 对 1167 卷为 `null` 且 `decode_scope = "aggregate-only"`。
**聚合 `passed` ≠ 每卷图片已核。**

### 冲突消解优先级

同一个量有多个来源时按序取信，并**保留**被覆盖的值：

1. 现场重算（对锚点 SHA 的树跑脚本）
2. 该卷自身 frontmatter
3. `catalog/manifest.jsonl`
4. 轮次凭据（`FULL-REPAIR-*`）—— 记录**当轮之前**的状态，视为历史

实测 44 处答案计数冲突中，manifest 与 frontmatter 一致而轮次凭据偏低者 37 处。
**不得**让轮次凭据覆盖前两者。

## 每小时 handoff

每个 lane 每小时落一份 `handoff/HANDOFF-<YYYYMMDDTHH>.json`，并在 `LATEST.json` 留指针。
必填字段与填写细则见交付说明；硬规则：

- 只写可复验的东西：命令 + exit code + 文件路径 + 哈希。不写叙事。
- `gap_totals` **每小时重算**，不许复制上一小时的值。
- `pinned_sha` 必须写死——历史报告过时问题全部源于没有锚点。
- `tasks.done[].result` 只允许 `closed` / `no_change` / `refuted`。
- 没做的事写进 `not_done`，不得留给读者推断。

## 边界

- 不修改正式卷、正式图片、缺口数字。
- 不合并任何分支（合并计划另见交付说明）。
- 不访问网络、不使用任何账号凭据。
- 本仓库 GitHub Actions **不执行**（账单限制，`steps: 0`）。
  **不得以检查项颜色判断任何 PR 的可用性**；唯一有效证据是本机重跑等效命令并附 exit code。
