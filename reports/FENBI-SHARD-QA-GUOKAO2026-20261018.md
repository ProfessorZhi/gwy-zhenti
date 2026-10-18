# 国考2026 三卷分片 QA（离线 · 元数据 only）

**范围**：`国考2026副省级 5823069`（135 题位）、`国考2026地市级 5823068`（130）、
`国考2026行政执法 5823067`（130）——**合计 395 题位**。本报告只覆盖这三卷，不涉及其他分片。

**输入**（全部为无凭据、只读元数据）：

- 唯一 Browser Owner 产出的 `gwy-zhenti-source-observation` handoff
  （`permissions: {browserProfile:false, cookies:false, tokens:false}`，10 卷；本报告只用其中 3 卷）；
- 仓库正式卷（PR #20 head `e1feb518…`）的 Markdown 结构；
- PR #75 的逐题位图片结论，作为**待复核主张**输入，**不作为已证事实**。

**本报告不含**题目正文、选项、图片字节、图片/正文哈希、练习 URL、账号资料。所有卷的
`rights.redistribution` 均为 `local_only`，因此只发布数字与状态。

## 1. 结构核验（可独立复现）

| 卷 | sourceId | 源声明题数 | 仓库标题数 | 1..N 编号 | 占位存根 | 身份对齐 |
|---|---|---:|---:|---|---:|---|
| 国考2026副省级 | 5823069 | 135 | **135** | 完整 | 0 | ✅ year/area/subject/variant/sourceId |
| 国考2026地市级 | 5823068 | 130 | **130** | 完整 | 0 | ✅ |
| 国考2026行政执法 | 5823067 | 130 | **130** | 完整 | 0 | ✅ |

- 三卷均可解析出唯一 `qid`，无重复标题、无缺号、无「题目正在全力以赴征集」类占位。
- 图片引用：副省级 265 处 / 地市级 241 处（仓库侧引用计数，**不是**内容哈希）。

## 2. PR #75 逐题位主张的复核结果

| 卷 | 题位 | 主张 | 仓库侧该题位图片引用数 | 本次判定 |
|---|---|---|---:|---|
| 5823069 | Q31 | `chunking_differs_not_comparable` | 3 | **needs_review**（切片不可比，维持待核） |
| 5823069 | Q81/82/84/85 | `image_bytes_identical` | 各 1 | **blocked**（见 §4） |
| 5823069 | Q125 | `image_bytes_partial` | 3 | **blocked** |
| 5823068 | Q76/77/78/79/125 | `image_bytes_identical` | 各 1 | **blocked** |
| 5823068 | Q115 | `image_bytes_partial` | 6 | **blocked** |
| 5823067 | — | 无主张 | — | 本次未抽查 |

**12 项主张：1 项 needs_review、11 项 blocked、0 项被本次核实为 identical。**

结构上**与主张相容**：仓库在这些题位确实各有图片，Q31 为多图（与"切片数不同"一致），
Q115 为 6 图、Q125 为 3 图（与"partial"一致）。但**相容 ≠ 证明**——字节是否相同，
本次无法离线判定。

## 3. 跨卷关系（真实、可复现）

三卷共享大量同源题，但**题号不一致**，因此逐题审计不能按题号硬比：

| 对比 | 共享 qid | 同号 | 跨号 |
|---|---:|---:|---:|
| 副省级 ∩ 地市级 | 71 | 23 | **48** |
| 副省级 ∩ 行政执法 | 52 | 22 | 30 |
| 地市级 ∩ 行政执法 | 79 | 62 | 17 |

→ 任何跨卷结论都必须走**一对一高置信重排**；按同号比较会得出错误差异。

## 4. BLOCKED — 需要 Owner 补充的交接内容

| 缺项 | 为什么需要 | 影响 |
|---|---|---|
| `per-question-source-fingerprints` | handoff 只有纸张级字段，没有逐题题干指纹 | 无法做任何逐题文本相等判定 |
| `question-image-binding` | handoff 的图片列表是扁平索引（`ref` + sha256），**没有题号绑定** | 无法把源图与仓库某题位的图配对，字节相等不可复核 |

在补齐之前：**逐题文本 `matched`、图片 `image_bytes_identical` 一律保持 blocked**，
不得由本分片或下游工具转写为已核。

## 5. 方法与复跑

```bash
# 只读：读 handoff JSON + git show 仓库卷；不联网、不读 profile
node tools/fenbi/src/shard-qa-cli.mjs \
  --handoff <handoff.json> --ref e1feb5187ec3544cde62a1a128a6269a8d63011b \
  --out <report.json> --claims <claims.json> \
  --paper 国考/2026/行测-副省级.md --paper 国考/2026/行测-地市级.md --paper 国考/2026/行测-行政执法.md
```

退出码：`0` 全部结构通过且无待核主张 · `2` 存在待核/阻塞项（本次为 **2**） · `1` 用法或解析错误。
报告写入用 `wx`，不会覆盖既有报告。

模块：`tools/fenbi/src/shard-qa.mjs`（纯函数）+ `src/shard-qa-cli.mjs`（只读 CLI）。
契约由 `validateShardReport()` 强制：`metadataOnly`/`advisoryOnly` 恒 `true`，
且**拒绝**任何含 `markdown`/`sha256`/`url`/`stemText` 等字段的报告。

## 6. 测试

| 命令 | 结果 |
|---|---|
| `node --test test/shard-qa.test.mjs` | **10 / 10 pass，exit=0** |
| `node --test test/shard-qa.test.mjs test/model.test.mjs test/browser.test.mjs test/pipeline.test.mjs test/dom.test.mjs test/align.test.mjs` | **76 / 76 pass，exit=0** |

夹具全部为合成 Markdown 与合成 handoff，不含任何真实题目文本。

## 7. 边界的明确声明

- **不是**独立 QA，**不是**正式验收；本分片只做结构与元数据核对。
- 未确认任何一题的官方原题身份或标准答案。
- 未接触 Fenbi 登录 Profile / Cookie / Token / 私有 raw 目录；未创建练习、未作答交卷购买。
- `main`（`34439ace…`）与 PR #20 head（`e1feb518…`）均未改动。
