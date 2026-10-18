# 一次批量重算：10 卷 / 1210 题位 → 4 个离线 lane 分片（2026-10-18）

**metadata-only**：不含题目正文、选项、图片字节、Cookie、账号资料或练习 URL。
`main` = `34439ace3ad6c0b93b0671b1f76ca4afd6cce06d`（**未改动**）。

## 0. 前置与纪律

| 项 | 值 |
| --- | --- |
| MemAvailable | **7.55 GB** |
| PSI cpu/memory/io | **全 0.00** |
| IO / load | nvme ≈1% / 0.37（另有 12 个 claude 进程） |
| Chrome / profile 锁 | **无 / 无** |
| **本轮浏览器** | **未启动**（AMBER，只跑轻量本机脚本） |
| **本轮新初始化** | **0**（ledger 仍 8 卷） |

## 1. 一次批量 CLI

| 项 | 值 |
| --- | --- |
| 命令 | `node driver/batch-recompute.mjs` |
| **退出码** | **0** |
| **执行时间** | **1152 ms**（wall ≈1.23 s） |
| 峰值 RSS | **114 MB**（远低于 256–384 MiB 预算） |
| 输入 | 10 卷既有本机采集物 + 仓库 MD/图片 |
| 网络 / 浏览器 | **零** |

**所有数字均由代码实际重算**，未照抄 PR #66/#72。

## 2. 逐题唯一类别（每卷闭合）

类别优先级（互斥，每题恰一类）：
`source_stub > ambiguous > image_* > normalized_equal > near > weak > different > repo_missing`

| 卷 | sourceId | stub | img同字节 | img切分不可比 | img unknown | norm_equal | near | weak | ambiguous | different | repo_missing | 合计 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 国考2026 地市级 | `5823068` | 0 | 11 | 2 | 2 | 88 | 19 | 3 | 4 | 1 | 0 | 130 |
| 国考2026 行政执法 | `5823067` | 0 | 9 | 1 | 4 | 91 | 18 | 3 | 4 | 0 | 0 | 130 |
| 天津2026 统考 | `8399759` | 0 | 3 | 4 | 1 | 94 | 15 | 1 | 2 | 0 | 0 | 120 |
| 上海2026 统考 | `8472470` | 1 | 8 | 4 | 2 | 65 | 28 | 6 | 9 | 6 | 1 | 130 |
| 广东2026 统考 | `8399765` | 0 | 8 | 0 | 2 | 56 | 7 | 6 | 3 | 7 | 1 | 90 |
| 国考2026 副省级 | `5823069` | 0 | 11 | 4 | 2 | 96 | 13 | 1 | 4 | 4 | 0 | 135 |
| 浙江2026 C类 | `8399763` | 0 | 8 | 2 | 1 | 78 | 13 | 1 | 3 | 4 | 0 | 110 |
| 江苏2025 C类 | `4189916` | 12 | 10 | 3 | 2 | 86 | 7 | 4 | 3 | 3 | 0 | 130 |
| 江苏2024 A类 | `4162243` | 4 | 8 | 5 | 2 | 90 | 11 | 2 | 8 | 5 | 0 | 135 |
| 广东2020 县级 | `96785` | 7 | 15 | 2 | 1 | 48 | 10 | 8 | 5 | 4 | 0 | 100 |
| **合计** | | **24** | **91** | **27** | **19** | **792** | **141** | **35** | **45** | **34** | **2** | **1210** |

**闭合校验**：每卷 `counts 之和 == 题位`，且全局 `24+91+27+19+792+141+35+45+34+2 = 1210` ✓
每题另有 `answerStatus = unverified_answer`（源页面从不展示答案）。

## 3. 与 PR #72 的差异及原因（必须解释）

| 项 | PR #72 | 本轮 | 原因 |
| --- | --- | --- | --- |
| 含图题 | **6**（只统计「短题干且有图」） | **137**（统计**所有**含 `<img>` 的题） | 分母不同：72 只看了短题干子集 |
| 图片字节已核 | 9（仅抽查 3 卷） | **91**（全 10 卷统一按字节 SHA 比） | 本轮对所有含图题做了源/库图字节比对 |
| 文本已核 | 1050（`normalized_equal`+`near`） | **933**（792+141） | 本轮把 `ambiguous`(45) 与 `different`(34) **单独拆出**，不再混入已核 |
| weak | 40 | 35 | 同上，口径统一后有 5 个落进 `ambiguous`/`different` |
| 缺口 | 90（54图+36文） | 见下 | 图片缺口大部分被字节比对消化 |

**净效果**：91 道含图题从「无法判定」变为**有字节证据**；同时把 45 处歧义与 34 处同号异文**显式列出**，不再藏在「已核」里。

## 4. 离线分片（给 4 个 lane）

10 个分片 + 1 个索引，均 **0600**，本地 gitignored：

```
/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi/batch-shards-20261018/
  shard-<sourceId>.json   ×10
  shard-manifest.json
/home/fjd/workspaces/gwy-zhenti-safe-observations/digest/
  shard-index-20261018.json   sha256 063e1cc40cd66db91f8e327b8b256901c94576f9cf7da34947a1a9319032d59e
```

**lane 分配**（每 lane 只读自己的分片）：

| lane | 卷 | 题位 |
| --- | --- | --- |
| lane1 | `5823068`, `8399765`, `4162243` | 355 |
| lane2 | `5823067`, `5823069`, `96785` | 365 |
| lane3 | `8399759`, `8399763` | 230 |
| lane4 | `8472470`, `4189916` | 260 |

单分片 < 1 MB，**N=2..4 均可**在 7.5 GB 可用内存内运行；重跑 `batch-recompute.mjs` 结果确定性一致，可缓存。

分片字段：`sourceNumber / repositoryNumber / category / image{sourceImages,repoImages} / imageSha / contentHash / optionHash / optionCount / score / answerStatus`。
**已核验**：分片内无 `contentHtml`/`answerHtml`/`<img` 标记、无 URL、无 cookie/token 字样。

## 5. 需要浏览器再次核对的最小名单

**空** —— 本轮无需浏览器复核。依据：

1. 上一轮实测 **27/27 实时图片字节与本地一致、0 新字节**，源内容未变；
2. 全库**没有**「无文本、无图、无选项」的空题（实测 0 条）；
3. 剩余未决类别（`ambiguous` 45、`different` 34、`image_chunking` 27、`image_unknown` 19、`repo_missing` 2）**都是仓库侧或映射侧问题**，浏览器重看同一页不会改变结论。

→ 后续工作应集中在**离线映射/仓库侧**，不建议再开浏览器。

## 6. 证据等级

| 级别 | 内容 |
| --- | --- |
| 字节级 | **91** 道含图题（源/库图内容 SHA 相同）+ 上一轮 27 个实时字节 |
| 单源文本 | `normalized_equal` 792、`near` 141 —— **非字节相等、非官方认证** |
| 独立第三方 QA | **无** |

`officialVerification = false`。`normalized_equal` 是**规范化后相等**，不是原文字节相等。

## 7. 复跑

```bash
cd /home/fjd/workspaces/gwy-zhenti-fenbi
node driver/batch-recompute.mjs    # 退出 0，约 1.2 s，峰值 ~114 MB
node driver/verify-shards.mjs      # 闭合 + 分片哈希 + 内容扫描，退出 0
cd repo/tools/fenbi && node --test test/model.test.mjs test/browser.test.mjs \
  test/pipeline.test.mjs test/dom.test.mjs test/align.test.mjs
```

## 8. 边界

未启动浏览器、未创建第 6 份练习、未答题/交卷/购买、未联网。
未改 `main`、未改他人分支/工作区/生产。受限原文仅在本机 0700/0600 gitignored 目录。
**本轮为一次有界批量，不是守护进程，也未创建定时任务。**
