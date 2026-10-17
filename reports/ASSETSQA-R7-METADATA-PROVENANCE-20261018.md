# 独立 QA：缺口口径 / 版权状态标签 / 版本身份（PR #67 · #69 · #70 · #71）

**2026-10-18** · lane：gwy-zhenti 独立 QA（非登录）· **性质：metadata-only 审核，不做法务判定**

## 0. 精确 SHA 与资源

| PR | HEAD | 本轮核验对象 |
| --- | --- | --- |
| #67 | `c544c1f31085965dc33c11b1d7b4f2ea96501cb7` | 自身仅 1 个提交（其余 20 个是 PR20 栈） |
| #69 | `31ca946d192a24229591d30ca11e7e7dce85ed52` | 55 缺号可回溯性 + 福建合规提示 |
| #70 | `32e9deeadd5f6fc00edcdd660bca33123ebc30a1` | 北京 51 缺号 0 恢复 |
| #71 | `266fa08a6873b7d45f624f461fd4c8f84b32820d` | 有界增量校验器（仅合成 fixture） |

**资源（开工实测）**：load 1.00 · MemAvailable **9 GiB** · swap 4/7 已用 · PSI io `avg60=0.11` · 20 核 · 无 Chrome 进程。
→ **AMBER**：只做静态/Node/Python 轻量；未开浏览器、未做 OCR、未碰私有 raw。

**未访问**：Fenbi login/profile/Cookie/token、Owner 0700/0600、他人 worktree、main。

---

## 1. 新增：metadata fail-closed 规则（可执行）

`tools/fenbi/assetsqa/metadata_provenance_gate.py` —— 只读**声明元数据**（front matter / 来源标签 / 槽位描述 / 回执旗标），
不读题干、选项、图片字节、凭据；**不做法律最终判决**，只拒绝「声明跑在证据前面」。

| 规则 | 内容 | 判定 |
| --- | --- | --- |
| **R1** 受限来源标签 | 自称 `正式真题/官方原题`，但来源明细或校验状态含 `粉笔会员` / `会员采` / `再分发条件未核实`，且**无**再分发许可记录 | **`provenance_uncertain`**，`verified=False`，附 `requiredAction`（取来源确认证据或降级声明） |
| **R2** 身份混同 | ① 通用卷 vs 综合卷被当成同一份 ② 优秀村干部（行测 C/D +《综合应用能力》）被计入申论 ③ 行政执法专项招录被当作市考 A/B 的第三类 ④ 卷型=行政执法 却以「市考《申论》」名义记载 | `identity_conflict` |
| **R3** 计数边界 | 剩余缺口数下降必须有等量 recovery；**重新归类不等于恢复** | `PASS` / `FAIL` |
| **R4** 图片证据提升 | 已验图片**内容 SHA 冲突**是「确实不同」的正面证据，绝不可被提升为 exact/auto-acceptable | `PASS` / `FAIL` |

> R1 刻意**不**说「侵权」：它只说「这份文件自己的声明与其自述来源不匹配，不能标 verified」。
> 也**不**修改、不删除任何正文。

---

## 2. PR #67 — 37 槽位身份判定：**PASS**，但有一个口径护栏要写明

**已核实的事实**

- `registry_remaining = 46` **未变**；`recovered_complete_papers_this_round = 0`。
- 浙江 11 个优秀村干部槽位在 **JSON 里已按 `subject: 行测` + `variant: C（优秀村干部）/D（优秀村干部）`** 记录，
  不在申论分母内：`lane_by_subject = {行测: 21, 申论: 16}`，11 个正是行测侧。
  → 结构化台账**没有**把 11 个算作申论，MD §三.1 与 JSON 一致。
- 上海 8 个行政执法专项槽位 `paper_identity = separate_recruitment_exam`，**没有**被并入市考 A/B。
- 天津 2024/2026 三类并行（综合市区/综合街镇/行政执法）登记为独立卷。

**R3 复算**：`before 46 → after 46, recovered 0, reclassified 11` → **PASS**。

**⚠️ 需写进口径说明（非缺陷，但是误读风险）**
> 46 是**总缺口**；`16 申论` 是**子集视图**。把 11 个槽位移出申论口径**不得**让 46 变成 35。
> 任何引用都必须同时给出「总 46」与「申论 16」两个数，且注明后者是子集。

**附带发现（PR67 自己已提示、未修改）**：库内 `省考/上海/2017/申论-行政执法卷.md` 的
`来源明细` 写作「2017年上海市公考《申论》题（行政执法卷）」，而卷型是「行政执法卷」而无「专项/招录」字样
→ 我的 R2 把它判为 **`enforcement-special-labelled-as-municipal`（needs_review）**。
该文件同时 `真题性质: 网友回忆版`（**非**正式真题）、`校验状态` 含「粉笔系上游，**再分发条件未核实**」。
→ 现状：**未被标 verified**（R1 `verified=False`），但身份需一次卷型裁定。

---

## 3. PR #69 — 55 缺号可回溯性 + 福建合规：**逻辑 PASS**，福建项 **provenance_uncertain**

**55 缺号逻辑（PASS）**

- 同号跨卷替代的量化：广东县级 vs 乡镇 **90 个同号重叠、0 个正文相同（0.0%）**；
  江苏2024A vs B **35.1%**、vs C **20.6%**；浙江2020A vs B **15.3%**。
- 阈值 0.95 下**全部 5 卷、55 个缺号 `substitution_justified=false`，`gap_numbers_recovered=0`**。
- `lead ≠ recovery` 写得明确，且未据此补齐任何一题 → 与 R3 一致。

**福建 2026 申论-通用卷（R1 = `provenance_uncertain`）**

PR69 §3 引用该文件 front matter：

| 字段 | 引述值 |
| --- | --- |
| `真题性质` | `正式真题` |
| `来源明细` | `shiwuooo/qiushi-shenlun SK_福建_2026_福建通用卷 · 粉笔会员采(v6)` |
| `校验状态` | `…粉笔系上游，再分发条件未核实…` |

→ 三条同时成立：**自称正式真题** + **自述来源是受限会员采集** + **自述再分发条件未核实**，且无许可记录 → 命中 R1。

**⚠️ 我无法独立复核该文件的当前内容**：`省考/福建/2026/申论-通用卷.md` **不在任何我可读的 ref 中**
（52 个 remote ref + main + 四个被审 PR 的树里都没有）。因此：
- 上述字段是**单源引述**（来自 PR69），我只核验「PR69 的处置逻辑是否正确」，**不声称核验了文件本身**；
- 文件当前是否仍为 `正式真题` → **unknown**，需持有该文件的分支负责人确认。

**PR69 的处置是恰当的**：只记录、不修改（文件所有权不在该 lane），并把该卷型等同问题
（`通用卷` 是否等于用户说的「综合卷」）明确**不作断言**。

---

## 4. PR #70 — 北京 51：**PASS**

- 「**51 个缺号没有因重复/顺序/同卷不同回忆版而减少：恢复 0，仍缺 51**」——这正是 R3 要求的形态。
- 证据可复核：全 ref 指向同一 blob `1e67c838…`（无第二版本）；67 题/67 答案/173 图严格 1:1，缺号无隐藏答案或图；
  卷内仅图形题通用占位选项；跨年仅数值选项巧合（2026 Q60/Q72）且题干不同。
- 2024 行测 / 2026 申论：官方开考已证、库内无文件、候选因**时间不可能/卷型冲突/主题冲突/非申论**被拒 → blocked。
- 我的 R1/R3 对其元数据判 **no_conflict / PASS**。

---

## 5. PR #71 — 有界增量校验器：**自身测试 PASS，但图片提升有缺口（high）**

**测试**：`node --test model browser pipeline dom align mapping incremental-validator` → **102 pass, exit 0**。

**设计已具备的正确点**
- `advisoryOnly: true` 恒定；`validateReceipt` 拒绝含 `contentHtml/options/imageBytes/text` 等字段的回执
- 版本标签不同 → 整卷 `version_wording_differs`、`autoAcceptable=false`
- 「图片证据**不可用**」→ `image_evidence_unverified` → 分类降为 `material_or_image_not_compared`

**缺口：把「已验但冲突」当成了「已验且相同」**

合成 fixture（`<p>图<img></p>` + 两侧 `imageBytes.verified=true`）：

| 情形 | category | grade | autoAcceptable | requiresHumanReview | flags |
| --- | --- | --- | --- | --- | --- |
| 已验 **相同** SHA | ordered_same_number | exact | **true** | false | `[]` |
| **已验 冲突** SHA | **ordered_same_number** | **exact** | **true** | **false** | **`[]`** |
| 两侧都无 manifest | material_or_image_not_compared | exact | false | true | `image_evidence_unverified` |
| `verified:false` | material_or_image_not_compared | exact | false | true | `image_evidence_unverified` |
| 单侧无 manifest | material_or_image_not_compared | exact | false | true | `image_evidence_unverified` |
| 版本标签不同 | ordered_same_number | — | false | true | `version_wording_differs` |

**「已验冲突」与「已验相同」结果完全一致，而「未验证」反被降级** —— 顺序是反的：
正面证据（内容不同）比证据缺失更强，却更宽松。`validateReceipt` 也返回 `ok:true`。

**根因分层（不重叠 #63 的 F8）**
- 直接原因在 #63 的 `scorePair`：`stemExact = stem.available ? stem.score===1 : (images...)`，
  题干残留任一字（如「图」）就走文本分支，图片分歧不参与 `exact`。此点已在 PR #68 报为 F8-residual，**不重复修**。
- **#71 自己的缺口**：`assessPair` 只在 `images.available === false` 时加旗标，
  **没有**覆盖 `images.available === true && images.similarity === 0`。这是 #71 文件内的防御缺口。

**#71 侧最小修复（属本 PR 范围，不与 #63 重叠）**
```js
if (images?.available === true && images.similarity === 0 && !images.contradictory) {
  flags.push('image_content_conflict');
}
```
并在 `requiresHumanReview` 中纳入该旗标、在 `categorize` 中禁止其返回 `ordered_same_number`。
优点：#71 不再依赖上游 `grade` 是否正确；即便 #63 未修，回执也不会把冲突对提升为 exact。

> 按派工要求：**本轮只做合成 fixture 检查，等 #71 出新 SHA 后再正式复审**。

---

## 6. PASS / FAIL / BLOCKED 矩阵

| 项 | PR | 判定 |
| --- | --- | --- |
| 46 总缺口未被重归类消掉 | #67 | **PASS**（R3：46→46，recovered 0，reclassified 11） |
| 浙江优秀村干部不计入申论 | #67 | **PASS**（JSON `subject:行测`，申论 16） |
| 上海行政执法专项 = 独立招录 | #67 | **PASS** |
| 上海2017 行政执法卷身份需裁定 | （仓库文件） | **needs_review**（R2 `enforcement-special-labelled-as-municipal`） |
| 55 缺号无同号替代 | #69 | **PASS**（0.0%–35.1%，阈值 0.95，0 恢复） |
| 福建2026 通用卷「正式真题」标签 | #69 引述 | **provenance_uncertain**（R1），文件本身 **unknown** |
| 通用 vs 综合 等同断言 | #69 | **PASS**（明确不断言） |
| 北京 51 全 blocked、0 恢复 | #70 | **PASS** |
| 增量校验器自身契约与测试 | #71 | **PASS**（102 pass） |
| **已验图片冲突被提为 exact/auto** | #71 | **FAIL（high）** |
| 来源真实性总体 | 全部 | **BLOCKED** —— 无独立可读真实原题；不判任何题「真实性通过」 |

---

## 7. 需人工处理的 copyright / metadata 明细

| # | 对象 | 问题 | 需谁处理 |
| --- | --- | --- | --- |
| M1 | `福建2026 申论-通用卷`（PR69 引述） | `正式真题` + 自述来源「粉笔会员采」+「再分发条件未核实」→ 不得标 verified | **持有该文件的分支负责人**（不在本 lane、不在我可读 ref 内） |
| M2 | `福建2026 通用卷` vs 用户口径「综合卷」 | 是否同一卷未定；不得按同义处理 | 福建卷型口径确认 |
| M3 | `省考/上海/2017/申论-行政执法卷.md` | 以「市考《申论》」记载，但卷型为行政执法；可能是专项招录卷 | 上海卷型裁定；当前**已未标 verified** |
| M4 | 浙江 11 个优秀村干部槽位 | 已正确记为行测；但引用时必须同时给「总 46 / 申论 16」，**不得**把 46 减成 35 | 报告作者/下游消费方 |
| M5 | #71 回执 `image_content_conflict` | 已验图片冲突未加旗标 | #71 作者（本 lane 只报，不改） |

---

## 8. 测试与 exit（真）

| 命令 | 结果 | exit |
| --- | --- | --- |
| `python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa` | **138 pass, 0 fail** | **0** |
| 其中 `test_metadata_provenance_gate.py` | **25 pass** | **0** |
| `node --test model browser pipeline dom align mapping incremental-validator`（#71 worktree） | **102 pass** | **0** |
| `metadata_provenance_gate.py <meta> --out ledger` | 6 records | **0** |

## 9. 复现

```bash
python3 -I tools/fenbi/assetsqa/metadata_provenance_gate.py <metadata.json> --out ledger.json
ASSETSQA_REPO=$PWD python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v
```

## 10. 边界

- **未**修改 #67/#69/#70/#71 任何文件或 HEAD；**未**合并、未 force；**未**碰 main（`34439ace3ad6c0b93b0671b1f76ca4afd6cce06d`）。
- **未**读取 Fenbi profile/Cookie/token；**未**打开浏览器；**未**创建练习；**未**访问站点。
- **未**删除或改写任何正式试卷正文；**未**对版权做法律结论。
- 未把任何第三方题文/图片字节/带凭据 URL 写入仓库。
