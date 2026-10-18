# Fingerprint-only shard QA (广东组)

只读、离线、metadata-only 的逐题指纹核对器。输入只允许 identity、一一映射和
SHA-256 指纹，**不允许题文/选项/答案/图片字节/URL**。它不打开浏览器、不读 Profile，
也不把 `normalized_equal` 元数据当成独立官方验真。

## 输入 shard

```json
{
  "schemaVersion": 1,
  "kind": "gwy-zhenti-fingerprint-shard",
  "paper": { "paperSourceId": "9000001", "year": 2026, "area": "广东",
    "subject": "xingce", "variant": "统考" },
  "rights": { "redistribution": "local_only" },
  "source": { "questionCount": 2, "questions": [
    { "number": 1, "textSha256": "<64hex>", "imageShas": ["<64hex>"] },
    { "number": 2, "status": "placeholder" }
  ] },
  "repository": { "questionCount": 2, "questions": [
    { "number": 1, "textSha256": "<64hex>", "imageShas": ["<64hex>"] },
    { "number": 2, "textSha256": "<64hex>" }
  ] },
  "mapping": [
    { "sourceNumber": 1, "repositoryNumber": 1, "grade": "exact" }
  ],
  "reviewCandidates": [
    { "sourceNumber": 2, "candidateRepositoryNumbers": [2], "reason": "ambiguous" }
  ]
}
```

- `mapping` 必须一一对应；重复 source/repo、跨 paper 编号、未知编号直接拒绝。
- `rights.redistribution` 必须是 `local_only`。
- `status`: `present` / `placeholder` / `unknown` / `image_only`；后三者不是有效内容。
- `grade`: `exact` / `near` / `weak` / `ambiguous`；near/weak/ambiguous 只能进 needs_review。
- 只有 source 与 repository 的 **text SHA 相等且 image SHA 集合也相等** 才记
  `fingerprint_exact`；这仍不是 official verification。
- 只有 text SHA 相等、无图片时记 `normalized_equal`；图片一侧缺失或冲突记
  `image_conflict`，绝不 same/exact。
- `normalizedEqual: true` 但没有本地 SHA（例如 PR#62 的 advisory mapping）只记
  `normalized_equal_mapping_only`，不是 verified。

## 运行

```bash
cd tools/fenbi/shard-qa

# 合成测试（真实 exit）
node --test test/checker.test.mjs
# 3 tests, 3 pass, exit 0

# 广东2026：把 PR#62 的 advisory mapping 转成 shard（无正文/图片/URL）
PR62_HEAD=be45c9afb38d37f2bb74867d9eaa5261cdb42140
git -C ../../.. show $PR62_HEAD:reports/FENBI-REORDER-AUDIT-20261018.json > /tmp/pr62-audit.json
node adapters/pr62-to-shard.mjs /tmp/pr62-audit.json 8399765 fixtures/gd-2026-pr62-shard.json
node checker.mjs --shard fixtures/gd-2026-pr62-shard.json \
  --out reports/gd-2026-shard-qa-20261018.json
```

## 本次结果（metadata-only）

### 广东2026统考 `8399765` — 90 题位

来源：PR#62 一对一 reorder audit（只有编号/grade/normalizedEqual，**没有** text/image SHA）。

| 状态 | 数量 | 含义 |
| --- | ---: | --- |
| `normalized_equal_mapping_only` | **64** | PR#62 归一化文本相等（11 same-number + 53 reordered），本地无 SHA，**不是独立验证** |
| `needs_review` | **13** | 7 near + 6 weak |
| `ambiguous` | **3** | source 46/47/49 的 tie 未绑定 |
| `unmatched` | **9** | 31/32/33/34/65/75/80/85/90 无一一映射 |
| `image_only_not_comparable` | **1** | Q35 源 1 图 / 库 0 图（PR#72），不可比 |
| `fingerprint_exact` | **0** | 没有合法 text+image SHA 分片 |

`officialVerification: false`。同号并非 12/90：PR#62 的 64 条归一化相等由 11 条同号 +
53 条重排组成；其余 26 条仍需人工/指纹复核。

### 广东2020县级 `96785` — 100 题位

**`BLOCKED_HOFF_OWNERS`**：没有合法 fingerprint-only 分片（逐题 text SHA + image SHA +
一一映射）。已知：

- 7 处粉笔征集占位（编号未在可读 handoff 中列出），占位正文不算题；
- Q30 的 1 张图与库图 byte-identical（PR#72），但这只是单图字节证据，不是文本/映射验证；
- PR#69：乡镇卷同号 90 题文本相等 **0**，不得用乡镇卷替补缺题；
- text fingerprint verified = 0，mapping verified = 0，blocked = 100。

详见 `reports/gd-2020-blocked-20261018.json`。

## 边界

- 不包含题文、选项、答案、图片字节、练习 URL、Cookie/Profile。
- 真实图片只认独立验证的 **image content sha256**；引用路径或 `⟦IMAGE⟧` 不算同图证据。
- 本工具只做指纹/映射核对，不产生 official verification，也不改写正式题库。
