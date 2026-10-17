# 独立 QA 复测：PR #62 / #63 / #65（2026-10-18）

**lane**：gwy-zhenti 独立 QA（非登录）· **性质：metadata / algorithm QA，不是 source truth verification**

## 0. 精确 SHA 与资源

| PR | HEAD（本轮实测） | base | 本轮判定 |
| --- | --- | --- | --- |
| #62 | `be45c9afb38d37f2bb74867d9eaa5261cdb42140` | `codex/shenlun-full-repair-20261015` | **PASS（F1–F7 全部修复）+ 1 项新 FAIL（F9）** |
| #63 | `ff00657c00b291e268da749215851587866ee3d3` | 同上 | **PARTIAL**：F8 修复了「纯 token」路径，**残留 caption 路径** |
| #65 | `30318fb88600a182d4d0c65a6a1dd3e34ced96b1` | `fix/fenbi-duplicate-route-guard-20261018` | **PASS + 1 项诊断建议（F10）** |
| #64（本 lane 上轮） | `0fe6128bb49043cc636aeaab9bb9a468f2c594e1` | 本 lane R4 | 本轮未改 |

**资源（开工实测）**：load 0.64 · **MemAvailable 8.0 GiB** · swap 3/7 GiB 已用 · PSI cpu/io/mem 全 0 · 20 核 · 无 Chrome 进程（仅残留 singleton 锁）。
→ 按「异常降载」执行**轻量离线**：静态审计 + 小合成 fixture；**未**启动浏览器、**未**并发重装依赖、**未**做图像解码。

**隔离**：三个 `git worktree`（`wt/pr62`、`wt/pr63`、`wt/pr65`）建在本 lane 自己的 workspace；`npm ci --offline` 各 27 packages。
**未接触**：Fenbi profile / Cookie / token / Owner 0700-0600 目录 / 他人 worktree / main。

---

## 1. 测试实跑（真 exit，非引用作者报告）

| 命令（各自 worktree 的 `tools/fenbi/` 下） | 结果 | exit |
| --- | --- | --- |
| `node --test test/reorder.test.mjs`（#62） | **14 pass** | **0** |
| #62 CI 行（model/browser/pipeline/dom/align/reorder） | **80 pass** | **0** |
| `node --test test/mapping.test.mjs`（#63） | **22 pass** | **0** |
| #63 CI 行（…/align/mapping） | **88 pass** | **0** |
| `node --test pipeline/test/*.test.mjs`（#65） | **71 pass** | **0** |
| `python3 -m unittest discover -s tools/fenbi/assetsqa`（本 lane） | **113 pass, 0 skip** | **0** |

安装：`npm ci --offline --ignore-scripts --no-audit --no-fund`。

---

## 2. PR #62 — F1–F7 复测

| 项 | 上轮缺陷 | 本轮实测 | 判定 |
| --- | --- | --- | --- |
| **F1** 歧义被绑定进 `mapping` | mapping 含 ambiguous | `mapping` 112/77；`reviewCandidates` 单列 9/3；**交集 = ∅**（脚本断言） | **PASS** |
| **F2** 报告数字与 JSON 不一致 | 广东「69」vs JSON 79 | MD §3 与 JSON `tiers` 完全一致；`approvedMappingCount` 112/77 = `len(mapping)` | **PASS** |
| **F3** coverage 含 weak | 0.862/0.865 当可用覆盖 | 三档分开：**exact 0.523/0.719 · high-confidence 0.792/0.798 · candidates 0.862/0.865**，并注明 candidates 不可当可用覆盖 | **PASS** |
| **F4** 「4 处逆序」误导 | 只报下降点 | `order` 同时给 `adjacentDescents 4/1` 与 `inversions 1219/205`、`rate 19.6%/7.0%`；「近乎单调」已撤回 | **PASS** |
| **F5** 偏移枚举不全 | 漏 −1/+31/+3、0/−50 | JSON `offsets` 9 种 / 5 种，与 mapping 重算一致 | **PASS** |
| **F6** 「逐字相同」 | 实为规范化相等 | `semantics` 明确 `normalized_equal … NOT byte identity`；分类名改为 `normalized_equal_*`；正文撤回「逐字/byte-identical」 | **PASS** |
| **F7** CI 未接 reorder | — | `fenbi-framework.yml` 测试命令已加 `test/reorder.test.mjs` | **PASS** |

**独立重算（`verify_pr62_stats.py`，18 PASS / 2 INFO）**

| 检查 | 上海 | 广东 |
| --- | --- | --- |
| closure-source | 130 = 130 ✓ | 90 = 90 ✓ |
| closure-repository | 112 + 17 = 129 ✓ | 77 + 9 = 86 ✓ |
| one-to-one | 112 对无重复 ✓ | 77 对无重复 ✓ |
| tiers-arithmetic | 68+35+9 = 112 ✓ | 64+7+6 = 77 ✓ |
| tiers-vs-coverage | 0.523/0.792/0.862 ✓ | 0.719/0.798/0.865 ✓ |
| tier-counts-vs-json | 全部相等 ✓ | 全部相等 ✓ |
| mapping-review-disjoint | ∅ ✓ | ∅ ✓ |
| order-metrics 重算 | inversions 1219, descents 4, pairs 6216 ✓ | 205 / 1 / 2926 ✓ |

**合成 fixture 复核**：构造「S4 在库内有两个同文孪生」→ 正确落入 `reviewCandidates`，**未进入 `mapping`**（`ambiguous bound into mapping? []`）。

### F9（新，minor）· 报告引用了不在 PR 里的校验脚本

MD 开头写「**有 `verify-reorder-stats.mjs` 校验闭合**」，但该文件**不存在于 PR #62**：

```
git ls-tree -r --name-only be45c9a | grep verify-reorder   →  (空)
```

PR #62 只有 5 个文件：workflow、json、md、`reorder.mjs`、`reorder.test.mjs`。
→ 数字本身是对的（已独立复算通过），但**读者无法运行报告所称的校验器**。建议：把脚本一并提交，或删除该引用。

---

## 3. PR #63 — F8 复测：**PARTIAL**

### 3.1 已修复部分（PASS）

| 项 | 实测 |
| --- | --- |
| `⟦IMAGE⟧` 占位符不再当文本证据 | `textOnly()` 剥离 token；`stem.available=false`（纯图片题干） |
| 图片证据只认**内容 SHA-256 manifest** | `imageManifest()` 要求 `imageBytes[].sha256` 为 64-hex 且 `verified === true`，否则整份 manifest 作废 |
| 无 manifest → 信号**不可用**而非 0（不再稀释） | `reason: image-bytes-not-verified`，`available:false` |
| 纯图片题干（无 caption）不得仅凭 token 判 exact | 合成复现：`<img>` 无 caption → `grade weak`, `autoAcceptable false` |
| rights gate | `restricted` → `blocked: source-rights-not-cleared`，assignments **0** |

### 3.2 残留缺陷（**FAIL，高**）· caption + 已验图片内容不同 → 仍判 `exact` 且 `autoAcceptable: true`

合成 fixture（题干 `<p>图<img src="x.png"></p>`，两侧 `imageBytes` 均为 `verified:true` 但 **SHA 不同**）：

```
score 0.9091  grade exact
stem   {available:true, score:1, basis:"text"}          ← 残留 1 个字「图」
images {available:true, score:0, basis:"image-content-sha256"}  ← 内容明确不同
assignments: [{grade:"exact", autoAcceptable:true, score:0.9091, img:{similarity:0}}]
```

**根因**：`scorePair` 中

```js
const stemExact = stem.available ? stem.score === 1 : (images.available && images.score === 1);
```

只要题干**还剩任意非空文本**（哪怕一个字「图」），就走文本分支，**图片分歧完全不参与 `exact` 判定**。
上轮的修复只覆盖了 `stem.available === false`（纯图片）这一条路径。

**影响**：图片题在仓库里普遍带一句「图」「如下图」之类的短 caption → 该缺陷对真实数据**可达**。下游若按 `autoAcceptable` 自动采纳，会把**图片内容已验证不同**的两道题绑成一对。

**最小修复**：`exact` 还应要求「两侧都有已验 manifest 时，图片不相互矛盾」：

```js
const imagesAgree = !images.available || images.score === 1;
const exact = stemExact && imagesAgree && (!options.available || (options.score === 1 && !options.contradictory));
```

**测试缺口**：`mapping.test.mjs` 的图片用例全部用 `contentHtml: '<img src="...">'`（**无 caption**），因此没有覆盖这条路径。建议补一条带 caption 的负例。

---

## 4. PR #65 — PASS

| 用户关注点 | 实测 |
| --- | --- |
| **个人已有练习 route owner-only** | `capture_ready` manifest：`requiresBrowserOwner:true`、`readOnly:false`、`browserProfile:'owner-only'`；任务 `assignableToOfflineWorker:false`、`suggestedOwner:'browser-owner'` |
| **离线 collector 不可借 URL 无账号抓取** | `pipeline/src/**` **零** `fetch(`/`node:http(s)`/axios；README 明确 `observe-import` 不打开浏览器/不访问站点/不创建练习/不猜 URL；`/start`·`/finish`·`/save` 直接判 `needs_route_review` |
| **QA handoff 无 URL/凭据泄漏** | 见下表，全部 fail-closed |
| 其他阶段只读 | `normalized` manifest：`readOnly:true`、`browserProfile:false`、`assignable:true`；manifest 全文无 URL/HTML |

**独立探针（自造 fixture，13 例）**

| 注入 | 结果 |
| --- | --- |
| 合法基线 | **ACCEPTED** |
| 顶层 `url` / `route` | REJECTED `QA_HANDOFF_URL_NOT_ALLOWED` |
| **嵌套** `assets[].sourceUrl` / `identity.practiceUrl` | REJECTED `QA_HANDOFF_URL_NOT_ALLOWED` |
| 原始 HTML 文本 | REJECTED `QA_HANDOFF_SCHEMA` |
| `permissions.browserProfile=true` | REJECTED `QA_HANDOFF_RAW_CONTENT` |
| `permissions` 缺 `tokens` 键 | REJECTED `QA_HANDOFF_RAW_CONTENT` |
| `redistribution: public` | REJECTED `QA_HANDOFF_REDISTRIBUTION` |
| asset sha 非 hex / artifact sha 不匹配 | REJECTED `QA_HANDOFF_SCHEMA` / `QA_HANDOFF_HASH_MISMATCH` |
| `producer.cookie='SESSION=…'` | REJECTED `HANDOFF_CREDENTIAL_LEAK` |
| 文件 0644（组/他人可读） | REJECTED `QA_HANDOFF_INSECURE_PERMISSIONS` |
| asset ref = 绝对 URL / `…:https://…` | **REJECTED**（但错误码是 `QA_HANDOFF_HASH_MISMATCH`） |
| asset ref = `../../etc/passwd` | REJECTED `INVALID_INPUT` |
| manifest 全文含 URL/HTML | **否** |

### F10（INFO）· URL 形态 asset ref 靠「哈希不匹配」偶然拒掉

`assertArtifactRelative()` 只拦：非字符串/空/绝对路径/NUL/`..` 越界。
`https://…` 在 POSIX 下不算绝对路径，因此**能通过**；它最终被拒，是因为 `asset_manifest` 里的 `ref` 未做同样归一化，导致键对不上 → `HASH_MISMATCH`。

→ **净效果是 fail-closed（无泄漏）**，但：
1. 错误码误导（应为 `URL_NOT_ALLOWED`）；
2. 属**偶然**防护——若将来 manifest 侧也做归一化，URL ref 可能被接受。

**最小修复**：`assertArtifactRelative` 增加 scheme 检查，如 `/^[a-z][a-z0-9+.-]*:/i` 直接拒绝。

---

## 5. PASS / FAIL / BLOCKED 矩阵

| 项 | PR | 判定 |
| --- | --- | --- |
| F1 歧义不绑定 | #62 | **PASS** |
| F2 数字与 JSON 一致 | #62 | **PASS** |
| F3 三档 coverage | #62 | **PASS** |
| F4 逆序对 | #62 | **PASS** |
| F5 偏移完整 | #62 | **PASS** |
| F6 normalized_equal ≠ 字节/官方 | #62 | **PASS** |
| F7 CI 含 reorder | #62 | **PASS** |
| F9 校验脚本缺失 | #62 | **FAIL（minor，文档引用）** |
| F8 图片内容 SHA vs 引用字符串 | #63 | **PARTIAL** |
| F8-residual caption+不同已验图片 → exact+autoAccept | #63 | **FAIL（high）** |
| #65 route owner-only | #65 | **PASS** |
| #65 离线不可抓取 | #65 | **PASS** |
| #65 handoff 无 URL/凭据泄漏 | #65 | **PASS** |
| F10 URL ref 诊断 | #65 | **INFO（fail-closed）** |
| 来源真实性 | 全部 | **BLOCKED** — 无独立可读真实原题；本轮不判任何题「真实性通过」 |

---

## 6. 需作者修复的最小清单

1. **#63（必须）**：`exact` 增加 `imagesAgree` 条件；补一条「caption + 不同已验图片」的负例测试。
2. **#62（应修）**：提交 `verify-reorder-stats.mjs` 或删除 MD 中的引用。
3. **#65（建议）**：`assertArtifactRelative` 显式拒绝带 scheme 的 ref。

---

## 7. 明确未做的事

- 未修改 #62/#63/#65 的**任何文件或 HEAD**；未合并、未 force、未碰 `main`（正式 main 仍 `34439ace3ad6c0b93b0671b1f76ca4afd6cce06d`）。
- 未读取 Fenbi profile / Cookie / token；未打开浏览器；未创建练习；未答题/交卷/购买；未猜 sourceID 或 URL。
- 未把任何第三方原题正文、选项、图片字节或带凭据 URL 写入仓库 —— 本报告与台账**只含计数、比例、SHA、布尔与拒绝码**。
- **没有**把任何一道尚无独立来源的人审题判为真实性通过。

## 8. 复现

```bash
# #62 统计独立重算
python3 -I tools/fenbi/assetsqa/verify_pr62_stats.py <pr62-report.json> --out ledger.json

# 各 PR 测试（各自 worktree 的 tools/fenbi/）
node --test test/reorder.test.mjs                      # #62  → 14 pass
node --test test/mapping.test.mjs                      # #63  → 22 pass
node --test pipeline/test/*.test.mjs                   # #65  → 71 pass
```
