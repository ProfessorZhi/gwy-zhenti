# QA 回执（R9）· 2026-10-18

精简核对，供 Integrating Owner 使用。**metadata / algorithm QA**，非来源真实性验真。
未新增报告 PR；本回执提交到本 lane 既有分支（PR #77）。

## 被测 SHA 与退出码

| 对象 | 精确 HEAD | 命令 | 结果 | exit |
| --- | --- | --- | --- | --- |
| #71 | `3f733da44a265a7615df8f053065b4b7d2912f1c` | `node --test model browser pipeline dom align mapping incremental-validator` | **117 pass** | **0** |
| #71 | 同上 | 合成负例矩阵（8 例） | **8/8** | **0** |
| #78 | `c9b143d19439471e5ec5ae24fa2825922dcf8eb6` | 表格算术重算（10 行 × 10 列） | 全闭合 | — |
| #80 | `e4b2d8b820544e6ef43777996e0e3e0a663d8cce` | `python3 -m unittest`（提取后） | **16 OK** | **0** |
| #81 | `55cc1fc90f372fd09faee28d266508247c4d0425` | `node --test test/checker.test.mjs`（提取后） | **3 pass** | **0** |
| #82 | `20b36556565a746ca3187fb6f9ea60c65e7a360a` | 报告证据级别核对 | 见下 | — |
| #83 | `a6e220d2f9a8f07528543073110adb4926ee523e` | `node --test test/shard-qa.test.mjs`（提取后） | **9/10**（第 10 项需 git 仓+国考 MD） | 1 |

## 10 条 pass / blocked 简表

| # | 项 | 结论 |
| --- | --- | --- |
| 1 | **#71 已验证图片内容冲突** → `image_content_conflict`、`autoAcceptable=false`、`requiresHumanReview=true` | **PASS** |
| 2 | **#71 未验证图片 + caption** → `material_or_image_not_compared`、不 auto | **PASS** |
| 3 | **#71 图像切片不同（1 vs 2 图，均已验）** → `image_content_conflict` | **PASS** |
| 4 | **#71 同号短文本（无图）** → `ordered_same_number`、auto（正确放行） | **PASS** |
| 5 | #71 仍依赖 #63 的 `grade`，但回执层独立降级：**#63 判 exact 时 #71 仍不 auto** | **PASS**（分层有效） |
| 6 | **#63 caption + 未验证图字节** → 仍 `exact` + `autoAcceptable`（无 #71 拦截时） | **FAIL**（属 #63，未修） |
| 7 | **#78 1210 类别闭合**：10 行逐行闭合、10 列逐列对上、总计 1210、lane 355+365+230+260=1210 | **PASS** |
| 8 | **#80 分片总量**：10 卷唯一、0 重复、每片 ≤3、年份仅 2020/2024/2025/2026（**无 2013–15**） | **PASS** |
| 9 | **#81 / #82 / #83 图像 SHA 证据级别**：均声明只认真实字节 SHA，路径/`formula-<hex>`/`⟦IMAGE⟧`/引用计数不作内容证据 | **PASS** |
| 10 | **#83 CLI 测试第 10 项**（需 git 仓 + `国考/2026/行测-地市级.md`） | **unknown**（环境受限，未复现；不作 PASS） |

**BLOCKED（无合法数据，不以合成测试当真相）**

- #74 `848` 与 `official_label_conflict` 词表（`cd161dd` 仍未修）—— 需作者改，我不重建。
- #83 逐题图片绑定：handoff 只有扁平 `ref`+sha256，**无题号绑定** → 字节相等不可复核。

## 经核真实问题数

| 类 | 数量 | 明细 |
| --- | --- | --- |
| **确认仍存在** | **3** | ① #63 caption+未验图仍 exact（#71 可拦）；② #74 「848」与产物不符（836/835）；③ #74 `official_label_conflict` 词表漏 826/827 |
| 本轮已由作者修复 | 3 | #74 的 1,020→1,070、1.8%→1.9%、叙述与产物一致（见 `cd161dd`） |
| 环境受限未判定 | 1 | #83 CLI 测试第 10 项 |

## 是否更正了答案/题干

**0**。本 lane 全程只读，未修改任何题目正文、选项、答案、图片字节；未改 `main` 或他人 PR。
未读 Owner 私有 raw / 登录 profile；未开浏览器；未做 OCR/GPU。本轮业务内存峰值 < 100 MB。
