# 上海2026 / 天津2026 行测：fingerprint-only 分片逐题 QA（2026-10-18）

**metadata-only**：本报告只含题号、状态、来源等级、SHA-256 指纹与计数；**不含**题干、选项、材料、答案、图片字节、练习 URL、Cookie、Token 或账号资料。未启动浏览器，未创建第 6 份练习，未答题/交卷/购买。

## 0. 范围与输入

| 卷 | sourceId | 题位 | 仓库文件 | 分片 SHA-256 |
|---|---|---:|---|---|
| 上海2026 行测统考 | `8472470` | 130 | `省考/上海/2026/行测-统考.md` | `6fc353d8ef04e5f997492d6e6a54036c84b7f7e1eb9c8d91dbe250ddf35add3b` |
| 天津2026 行测统考 | `8399759` | 120 | `省考/天津/2026/行测-统考.md` | `c8718e011b60d62536479bb90f7dd1ddf1b88e510c740509d0aaf4952d4365fe` |

- 分片索引 SHA-256：`063e1cc40cd66db91f8e327b8b256901c94576f9cf7da34947a1a9319032d59e`。
- 两个分片均声明 `containsQuestionText=false`、`containsImageBytes=false`，rights=`observed_ui/local_only`。
- 资源：MemAvailable 6.9 GiB、PSI cpu/memory/io 全 0、load 0.20；未开浏览器。

## 1. 方法

1. **上海**只使用 PR #62 的双向互最佳、一对一、并列不绑定的 mapping；原同号 0 不当任何“错题”依据。
2. 用与 `batch-recompute.mjs` 相同的解析/规范化复算**仓库侧** `contentHash`/`optionHash`：
   - `normalize = NFKC + 全角折叠 + 去空括号 + 去空白/标点，仅留中日韩/字母/数字`；
   - `contentHash = sha256(normalize(stem) + "||" + "|".join(normalize(options)))`。
3. 图片只认**实际文件字节 SHA-256**：仓库 `图片/...` 文件实算；源侧取分片 `imageSha`。路径、`formula-<hex>` 文件名、`⟦IMAGE⟧` 一律不作同图证据。
4. `ambiguous`/`weak` 只有在**源/库两侧该 SHA 出现次数均为 1 且恰好一个候选**时才绑定；否则保留待核。
5. 上海 Q44 的源解析争议**强制保留**，不因文本或图片匹配而消解。

## 2. 结果（250 题位）

| 卷 | 槽位 | matched | needs_review | unknown | 1:1 | 仓库题号范围 |
|---|---:|---:|---:|---:|---|---|
| 上海2026 | 130 | **109** | **12** | **9** | ✅ | 1—128（仓库 129 题） |
| 天津2026 | 120 | **114** | **5** | **1** | ✅ | 1—119（仓库 120 题） |
| **合计** | **250** | **223** | **17** | **10** | ✅ | — |

### 上海 109 matched 的构成

| 依据 | 数量 |
|---|---:|
| 文本 exact（`normalized_equal`） | 64 |
| 文本 near（≥0.85） | 28 |
| 文本 exact + 图像 SHA 相同 | 2 |
| 文本 near + 图像 SHA 相同 | 4 |
| 图像 SHA 唯一一对一（9 个原 ambiguous + 2 个 weak 图题） | 11 |
| **合计** | **109** |

needs_review 12：Q44 源解析争议 1、图像字节冲突 1（源 89）、图像切分不可比 4、无图 weak 6。
unknown 9：内容不同 6、来源占位 1（源 80）、仓库缺题 1（源 130）、图像无对应 1（源 120）。

### 天津 114 matched 的构成

| 依据 | 数量 |
|---|---:|
| 文本 exact（`normalized_equal`） | 94 |
| 文本 near（≥0.85） | 15 |
| 文本 exact + 图像 SHA 相同 | 3 |
| 图像 SHA 唯一一对一（原 ambiguous 66/67） | 2 |
| **合计** | **114** |

needs_review 5：图像切分不可比 4、无图 weak 1。
unknown 1：源 120 无对应仓库题/图。

## 3. 关键发现：图像 SHA-256 解开 11 + 2 个待核槽

### 3.1 上海 9 个 ambiguous → 唯一镜像重排

源题位与仓库候选的图片字节 SHA-256 一一唯一匹配，且目标 87—98 均未被 PR62 的 112 条 mapping 使用（无冲突）：

| 源 | 仓库 | 源/库图数 | 结论 |
|---:|---:|---|---|
| 56 | 87 | 1/1 | `image_sha_unique` |
| 57 | 88 | 1/1 | `image_sha_unique` |
| 59 | 90 | 1/1 | `image_sha_unique` |
| 60 | 91 | 1/1 | `image_sha_unique` |
| 61 | 92 | 1/1 | `image_sha_unique` |
| 62 | 93 | 1/1 | `image_sha_unique` |
| 63 | 94 | 1/1 | `image_sha_unique` |
| 66 | 97 | 1/1 | `image_sha_unique` |
| 67 | 98 | 1/1 | `image_sha_unique` |

- 9 个源图 SHA 与 9 个仓库图 SHA 在两侧的出现次数均为 **1**；无一对多、多对一。
- 其中 56/57/59/63/66/67 的文本 `contentHash` 也与目标相同（exact）；60/61/62 仅图像唯一，文本未 exact → **只按图像证据记 matched**，不冒充文本 exact。
- 这 9 个题位原为 PR62 的 `reviewCandidates`（同分并列，未绑定）；本轮**只读指纹**把它们变成图像字节级一对一候选，仍不是官方验真。

### 3.2 上海 2 个 weak 图题

源 65→96、源 112→111：文本 weak，但源/库图 SHA 集合完全相同且每张图两侧唯一（112→111 为 4/4 图全同）。按“图片只认字节 SHA”记 matched，basis=`image_sha_unique`；**不把 weak 文本改写成 exact**。

### 3.3 天津 66/67

源 66→66、源 67→67：文本 ambiguous，但源/库各 1 张图的 SHA-256 相同且两侧唯一 → 图像字节级同号确认。

### 3.4 不能升级的图片项

- 上海源 89→39：文本 exact，但源/库各 2 张图 SHA **完全不交** → `needs_review/image_conflict`；不因文本 exact 自动接受。
- 两侧图数/切分不同（上海 4、天津 4）→ `needs_review/image_chunking_not_comparable`。
- 源 120（上海/天津）图无仓库对应 → `unknown/image_unknown_no_repo`。

## 4. 口径对账（禁止混用）

### 上海

- PR #62：approved mapping **112**（exact 68 + near 35 + weak 9），high-confidence **103**，reviewCandidates 9，unmatched 9。
- 本审计：**109 matched** = 103 high-confidence − Q44(1) − 图像冲突 89(1) − near 图像切分 3 + 9 ambiguous 图像唯一 + 2 weak 图像唯一。
- 因此 109 不是“比 PR62 多 6 个文本匹配”，而是**文本口径 + 图像字节口径**的合并结果；Q44 仍待核。

### 天津

- PR #72（文本内容口径）：已核 **114**，仍缺 3（1 weak + 2 ambiguous，未做图像解析）。
- 本审计（内容+图像）：matched **114**；2 个 ambiguous 由唯一图像 SHA 解析后，剩余 needs_review 5（4 图像切分 + 1 weak）、unknown 1（源 120）。
- Owner number-based：verified **119** / remaining 1；它按题号对齐并把 66/67 计入，不能与内容口径直接相加或相减。

**三个数字（103/114/119、109/114、5+1）各自口径不同，不得混成一个“已核总数”。**

## 5. 逐题台账

- 250 行逐题记录在 `reports/FENBI-SHARD-QA-SH-TJ-20261018.json` 的 `papers[].rows`。
- 每行字段：`sourceNumber / repositoryNumber / category / pr62Grade / textFingerprint / imageMatch / status / basis / resolvedByImage / contentHash12 / optionHash12 / repoContentHash12 / imageSha12 / repoImageSha12`。
- 不含任何题干/选项/材料/答案/图片字节/URL。

## 6. 可复跑与测试

```text
$ python3 -I tools/qa/fingerprint_shard_qa.py \
    --shard .../shard-8472470.json --paper /tmp/上海-行测-统考.md \
    --image-root .../gwy-zhenti-fenbi/repo --pr62 /tmp/pr62-reorder.json \
    --label '上海2026 统考' --out /tmp/qa-sh.json
8472470 slots=130 matched=109 needs_review=12 unknown=9 1:1=True
EXIT=0

$ python3 -I tools/qa/fingerprint_shard_qa.py \
    --shard .../shard-8399759.json --paper /tmp/天津-行测-统考.md \
    --image-root .../gwy-zhenti-fenbi/repo --label '天津2026 统考' --out /tmp/qa-tj.json
8399759 slots=120 matched=114 needs_review=5 unknown=1 1:1=True
EXIT=0

$ python3 -I tools/tests/test_fingerprint_shard_qa_20261018.py -v
Ran 7 tests ... OK
EXIT=0

$ cd tools && python3 -m unittest tests.test_fingerprint_shard_qa_20261018
Ran 7 tests ... OK
EXIT=0
```

合成测试覆盖：规范化/哈希复现、图片 SHA 唯一解析、两侧重复图不绑定、Q44 强制待核、重复 repoNumber 破坏 1:1、输出不含题干/图片字节。

## 7. 证据等级与边界

| 级别 | 内容 |
|---|---|
| 字节级 | 22 个题位的源/库图 SHA-256 相同（上海 8+9、天津 3+2）；其中 11 个是 `image_sha_identical`，11 个是图像唯一解析 |
| 文本单源 | 201 个题位的 exact/near 文本指纹；`normalized_equal` 不是字节相等 |
| 独立第三方 QA | **无** |
| 官方验真 | **无**（`officialVerification=false`） |

- 所有匹配仍是单源（粉笔 UI / Owner 分片）+ 仓库存量；`normalized_equal` 不等于官方原题/标准答案。
- 未修改 main、PR #62/#72/#75、其他 Owner 分支或工作区；未读取 Fenbi 登录 Profile/Cookie/Token/私有 raw 目录。
- 未创建新练习、未答题/交卷/购买、未绕验证码/403/429/频控。
- 图片只算 SHA-256，未复制、未上传、未在报告中保存字节。
- 未解决：Q44 解析争议、8 处图像切分不可比、1 处图像冲突、7 处 weak、6 处 different、2 处来源占位/仓库缺题、2 处源 120 无对应。
