# 申论本地档案 publish-preflight

离线、只读的验收矩阵，用来回答两个**不同**的问题：

1. **technical**：这份本地档案在结构、材料、答案、图片字节和哈希上是否自洽、可用？
2. **publication**：它是否已经拿到第三方版权许可、可以进入 GitHub 发布？

两者不能互相替代。用户授权访问/私有保存不是版权方许可；技术 PASS 也不会自动变成可发布。

## 不变式

- 不访问网络、不启动浏览器、不读取登录态。
- 不写档案目录；默认只在显式 `--out` / `--markdown` / `--snapshot-out` 时写派生元数据。
- 报告只含计数、哈希、相对路径、issue code；不含题干、材料、答案、解析、标题正文或图片字节。
- 不修改 `rightsStatus`、`cloudStorageBlocked`、`githubPublicationAllowed`。
- 发现 `rightsStatus=cleared` 或 `cloudStorageBlocked=false` 时记为 `POLICY_VIOLATION`，而不是接受它。
- 缺图但没有本地 SHA 元数据时，**不按顺序或尺寸猜图**，只报告 `unresolved`。

## 命令

```bash
# 只读扫描 + metadata-only 报告
node tools/fenbi/src/archive-preflight-cli.mjs \
  --archive /path/to/shenlun-archive \
  --main-manifest catalog/manifest.jsonl \
  --inventory /path/to/inventory.json \
  --asset-store /path/to/local-images-1 \
  --asset-store /path/to/local-images-2 \
  --out reports/PREFLIGHT.json \
  --markdown reports/PREFLIGHT.md

# 额外生成派生元数据快照（不含正文）
node tools/fenbi/src/archive-preflight-cli.mjs ... --snapshot-out /tmp/preflight-snapshot

# 生成图片修复计划（dry-run）；--apply-repairs 才真正复制字节
node tools/fenbi/src/archive-preflight-cli.mjs ... --repair-plan /tmp/repair-plan.json
node tools/fenbi/src/archive-preflight-cli.mjs ... --repair-plan /tmp/repair-plan.json --apply-repairs
```

退出码：`0` 正常；`1` 配合 `--strict` 且存在 FAIL/SKIP；`2` 参数错误；`3` 检测到 ELIGIBLE（不应出现在当前 rights 状态下）。

## 门禁语义

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `technicalStatus` | `PASS` | 结构/材料/答案/图片哈希自洽；允许 `explanation-empty`、`answer-above-word-maximum` 等 warning |
| | `FAIL` | 有 fatal issue（缺文件、哈希不符、材料页签缺口、未解析引用、缺图字节、身份/计数不一致等） |
| | `SKIP` | 卷目录缺失或扫描期间文件变化，不能下结论 |
| `publicationStatus` | `BLOCKED` | rights 未 cleared 或 cloudStorageBlocked=true（本档案的正常状态） |
| | `ELIGIBLE` | 只有 rights 真正 cleared 且未 blocked；当前应为 0 |
| | `POLICY_VIOLATION` | 检测到 cleared/未 blocked/允许发布，需要人工处置 |

## 图片映射核验

对每个 `assets[]` 条目：

- 文件存在、位于 `assets/` 内、SHA256 与声明一致、字节数一致；
- 文件名 stem 等于内容 SHA（内容寻址）；
- PNG/JPEG 头部尺寸与声明一致；
- `paper.md` 与 `paper.json` 的图片引用顺序一致，且与 `assets[]` 顺序一致；
- 无孤儿文件、无越界引用、无外部 URL 残留。

只有“缺失/哈希不符且本地 store 有同 SHA 字节”的图片才会生成 `copy` 修复；其余为 `unresolved`。

## main catalog 重叠匹配

档案没有 main 的行号或标题主键，因此按“地区 + 年份 + 卷型 + 题数”给出候选：

- `exact`：唯一候选；
- `ambiguous`：多个候选；
- `none`：无候选。

`priorAnswerOverlap` 只在 `exact` 且命中 #110/#112/#113 的 14 条路径时为 true；`priorAnswerCandidate` 表示仅候选命中，不能当成“已补答案”。

## manifest 行级增量更新

不要全量重写 `catalog/manifest.jsonl`。用 patch 工具只替换命中 key 的单行，其余行逐字节保留：

```bash
node tools/fenbi/src/manifest-patch-cli.mjs \
  --manifest catalog/manifest.jsonl \
  --updates /tmp/updates.json \
  --check          # 默认；--apply 才写盘

# updates.json
# { "updates": [
#   { "path": "省考/…/申论-….md", "expectSha256": "…", "set": { "notes": ["…"] } }
# ] }
```

冲突（key 不存在、重复 key、`expectSha256` 不符、试图改 key、任一 update 冲突）时整批拒绝，不写盘。

## 测试

```bash
cd tools/fenbi
node --test test/archive-preflight.test.mjs test/manifest-patch.test.mjs
```

测试全部使用合成文本和合成 PNG 头，并专门断言报告里不出现答案/材料/题干标记。

## 2026-10-22 首次运行

见 `reports/SHENLUN-LOCAL-ARCHIVE-PREFLIGHT-20261022.md`。摘要：56 卷全部 `PARTIAL`，technical `PASS 30 / FAIL 26 / SKIP 0`，publication 全部 `BLOCKED`；131 张已落地图片 SHA 全部核验通过，40 张缺字节且无本地 SHA，无法离线修复。
