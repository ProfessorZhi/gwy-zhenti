# 独立 QA：PR #62 映射统计 + PR #63 advisory matcher（2026-10-18）

**lane**：gwy-zhenti 独立 QA（非登录）· **性质：metadata / algorithm QA，不是 source truth verification**
**被审对象**（精确 SHA）

| PR | HEAD | 基础 | 状态 |
| --- | --- | --- | --- |
| #62 | `2cb719a4fb36bf85392f871e08e1d356a79b2b58` | `codex/shenlun-full-repair-20261015` | OPEN |
| #63 | `ea91bb55d3ad6f327f42352fd398976f2f6d6452` | 同上 | **Draft** |

**环境**：load 0.33 → 0.30，available RAM **9 GiB**，swap 2/7 GiB 已用，IO pressure 0，CPU pressure 0，20 核。
→ 允许静态审计 + 隔离 worktree 合成 fixture；**未做**任何重图像运算。
**隔离**：两个 `git worktree`（`wt/pr62`、`wt/pr63`）建在**本 lane 自己的 workspace** 下；离线 `npm ci --offline` 成功。
**未接触**：Owner 0700/0600 目录、fenbi profile、浏览器、真实题文、任何他人 worktree。

---

## 0. 总判定

| 对象 | 判定 | 一句话 |
| --- | --- | --- |
| **PR #63**（advisory matcher） | **PASS（带 1 项语义保留）** | 契约自洽、门禁齐全、测试全绿；唯一问题是 `imageSignal` 比的是**引用字符串**而非图片字节 |
| **PR #62**（reorder 报告） | **FAIL（报告层）** | 算法本身可用，但**报告里的数字与它自己的 JSON 对不上**，且「逐字相同」「近乎单调」「覆盖率」三处表述超出算法实际证明力 |
| **#62 + #63 组合** | **可合并（无文件冲突）** | 文件集不相交；但**两套 matcher 的定义不能互相换算**，数字不可混用 |

---

## 1. 测试实跑（exit 记录）

| 命令（各自隔离 worktree 的 `tools/fenbi/` 下） | 结果 | exit |
| --- | --- | --- |
| `node --test test/reorder.test.mjs`（#62） | **9 pass**, 0 fail | **0** |
| `node --test test/model.test.mjs test/browser.test.mjs test/pipeline.test.mjs test/dom.test.mjs test/align.test.mjs test/reorder.test.mjs`（#62 全套） | **75 pass**, 0 fail | **0** |
| `node --test test/mapping.test.mjs`（#63） | **17 pass**, 0 fail | **0** |
| `node --test test/model.test.mjs test/browser.test.mjs test/pipeline.test.mjs test/dom.test.mjs test/align.test.mjs test/mapping.test.mjs`（#63 CI 行） | **83 pass**, 0 fail | **0** |
| `node tools/fenbi/assetsqa/crosscheck_matchers.mjs --reorder … --mapping …`（本报告新增，纯合成） | 产出结果 | **0** |

安装：`npm ci --offline --ignore-scripts --no-audit --no-fund` → 27 packages，离线完成。

---

## 2. PR #62 核验

### 2.1 PASS

| # | 项 | 证据 |
| --- | --- | --- |
| P1 | **coverage 分母正确** | 上海 `112/(130−0)=0.8615`→0.862；广东 `77/(90−1)=0.8652`→0.865。分母=源题数−image_only，与 `coverage()` 实现一致 |
| P2 | **一对一约束成立** | 上海 mapping 113 条、广东 79 条；source/repo 号码**各自无重复**、全部在范围内、无重复 (src,rep) 对 |
| P3 | **分类闭合且互斥（计数层）** | 上海 源 130 = 0+68+35+9+9+9+0；库 129 = 113+16。广东 源 90 = 11+53+7+6+3+9+1；库 86 = 79+7 |
| P4 | **metadata-only 无泄漏** | 4 个新增文件：**0 个 URL、0 凭据、0 题干正文**；长 CJK 串全部是文档/注释散文 |
| P5 | **exactPairs 与 mapping 自洽** | 上海 mapping 内 exact 69 = 报告 `exactPairs` 69；广东 66 = 66 |

### 2.2 FAIL

**F1 · `mapping` 里**含有 **ambiguous 的绑定**（与文档表述矛盾）**
- 文档 §1.3：「内容雷同的题……落入 `ambiguous_multi_candidate`，**交由人工，不强行绑定**」。
- 实际：`mapping` 113 条里含 **1 条** ambiguous（上海）；79 条里含 **2 条**（广东）。差额即 `mapping − 分类已映射 = 113−112 = 1`、`79−77 = 2`。
- 后果：任何读 `mapping` 的下游都会**自动采纳**这些对。合成 fixture 复现：`ambiguousButBound: [[4,4]]`。

**F2 · 报告数字与自己的 JSON 不一致**

| 文档 §4 | JSON 实际 | 差 |
| --- | --- | --- |
| 上海「已建立一对一映射 **112**」 | mapping **113**（分类已映射 112） | 1 |
| 广东「已建立一对一映射 **69**」 | mapping **79**（分类已映射 **77**） | **8–10** |
| 上海「**112 对**」/ 广东「**78 对**」 | 113 / 79 | 1 / 1 |

广东 69 既不等于 mapping 79，也不等于分类已映射 77；且「exact 64，其余为近似」推不出 69（64+13=77）。

**F3 · coverage 把 `weak_candidate_review` 计入分子，与「不建议直接采用」冲突**

| 卷 | 报头 coverage | 含 weak | 剔除 weak | 仅 exact |
| --- | --- | --- | --- | --- |
| 上海 | 0.862 | 112/130 | **103/130 = 0.792** | 68/130 = 0.523 |
| 广东 | 0.865 | 77/89 | **71/89 = 0.798** | 64/89 = 0.719 |

mapping 内有 **9**（上海）/ **6**（广东）条 score < 0.85，正是 `weak_candidate_review`。报头引用 0.862/0.865 时未说明含弱候选。

**F4 · 「仅 4 处逆序 / 112 对」「1 处逆序 / 78 对」误导**

那是**相邻下降点**（descent points），不是逆序对：

| 卷 | 相邻下降点 | 逆序对 | 逆序占比 | 总对数 |
| --- | --- | --- | --- | --- |
| 上海 | **4**（30→1, 75→51, 109→86, 86→31） | **1249** | **19.7%** | 6328 |
| 广东 | **1**（65→16） | **215** | **7.0%** | 3081 |

→ 「块状重排」成立；「**近乎单调**」不成立（上海约五分之一的对是逆序）。

**F5 · 偏移枚举不完整**：上海只列 `+15/+28/−50/−15/−25`，实际还有 `−1`(16)、`+31`(15)、`+3`(7)；广东只列 `+1/+5/−4`，实际还有 `0`(15)、`−50`(5)。

**F6 · 「逐字相同」是高估**：`exact` 只要求规范化后相等——`normalizeText` 会折叠标点/空白/全角。
合成复现：`'甲，乙。丙！丁？'` 与 `'甲 乙 丙 丁'` 规范化后**完全相同**，判为 `exact`。
→ 应写「规范化后相等」，不能写「逐字相同」；由此推出的「不同卷子不可能共享 68 道逐字相同的题」也**强于**算法实际证明。

**F7 · #62 没把 `reorder.test.mjs` 接进 CI**：`.github/workflows/fenbi-framework.yml` 用的是**显式文件列表**，#63 加了 `mapping.test.mjs`，#62 **没加** `reorder.test.mjs`。两 PR 合并后，#62 的测试仍不会在 CI 跑。

### 2.3 UNKNOWN

- **U1 · 「前序严格同号 12/90」vs 本审计 11/90**：算术上完全吻合「**1 道 image-only 题本来是同号对，被排除**」（12−1=11，90−1=89）。但我看不到该题号（JSON 只有计数），**不能确认身份** → 记为算术支持、未核实。
- **U2**：JSON 只给分类**计数**与 `mapping`，不给逐题分类列表，故我只能验证「计数求和闭合」，**不能**验证每个源题号恰好出现一次。

---

## 3. PR #63 核验

### 3.1 PASS

| # | 项 | 证据 |
| --- | --- | --- |
| P6 | **advisory-only 契约** | `advisoryOnly: true` 恒定；`validateMappingReport` 强制该字段 |
| P7 | **autoAccept 边界** | 仅 `grade === 'exact'` 才 `autoAcceptable: true`；`validateMappingReport` 把「非 exact 却可自动接受」列为 problem。合成 fixture：3 条 exact 全 true，其余 false |
| P8 | **rights gate 硬否决** | `sourceRights: 'restricted'` → `blocked='source-rights-not-cleared'`，`assignments` 长度 **0**，6 条源题全进 `unmatchedSource` with reason=blocked |
| P9 | **isEligible 必填** | 不传函数直接 `throw`；合成 fixture 中剔除 image-only 后 `rejected=[{number:5,...}]`，不再进入候选池 |
| P10 | **重复题号** | 两侧各自记录 `duplicateNumbers` 与 `conflicts`（合成：`[1]` / `[1]` / 2 条 conflict） |
| P11 | **选项标签顺序冲突** | A/B/D/C → `score:0, grade:'weak', contradictory:true`，不可映射 |
| P12 | **题号不参与评分** | `sameNumber` 只作观察值报出；`scorePair` 不使用 number |
| P13 | **测试全绿** | 17 / 83，exit 0 |

### 3.2 语义保留（不阻断，但必须写进使用约定）

**F8 · `imageSignal` 比的是「图片引用字符串」的 sha256，不是图片字节**

合成复现：

| 情形 | imageSignal |
| --- | --- |
| 两侧 src 字符串**完全相同** | `score 1` |
| 同一文件、**不同 host/path** | `score 0` |
| 同一目录、**不同文件** | `score 0` |

推论：跨语料（采集侧是 URL、仓库侧是相对路径）该信号**几乎恒为 0**；而两侧都有图时它仍算 "available"，会**稀释**加权分。它既不能证明图片相同，也不能发现「同路径不同内容」。

---

## 4. #62 与 #63 的定义兼容性

**结论：不能互相换算，数字不可混用。**

| 维度 | #62 `reorder.mjs` | #63 `mapping.mjs` |
| --- | --- | --- |
| 相似度 | 题干+选项 bigram **Jaccard** | stem/options/materials/images **加权 Dice**（0.55/0.25/0.12/0.08） |
| 阈值 | `low 0.45` / `suggest 0.85` | `candidateFloor 0.72` / `ambiguityMargin 0.08` |
| 约束 | **双向互最佳** + 一对一 | 逐源贪心 + 已占则 `repository-row-already-claimed` |
| ambiguous 是否绑定 | **绑定进 `mapping`**（F1） | **不绑定** |
| image-only | 内建 `image_only_not_comparable`，**排除出 coverage 分母** | **无此类别**，交给调用方 `isEligible` |
| repo 未映射 | `repo_only_absent_in_source` = 2（fixture） | `unmatchedRepository` = **3**（fixture，多出被 ambiguous 消费的那条） |
| exact 定义 | 规范化后 `combined` 全等 | `stem.score===1 && (options 不可用 或 options.score===1)` |

同一 fixture 上：#62 出 4 个 pair（含 ambiguous 的 4→4），coverage 0.6；#63 出 3 个 assignment、1 个 ambiguous、2 unmatchedSource、3 unmatchedRepository。

---

## 5. 组合 / CI / 契约检查

| 项 | 结果 |
| --- | --- |
| #62 与 #63 文件集 | **不相交**（#62：reports×2 + reorder.mjs + test；#63：workflow + README + mapping.mjs + test）→ 可干净合并 |
| 与 **#42** 的契约 | #63 `import { normalizeComparisonText } from './align.mjs'`；#42 改的是 `compareText`/`comparePaper`，**`normalizeComparisonText` 逐字节未变**（已 diff 比对）→ **PASS** |
| 与 **#54 / #58 / #61** | 三者只动 `browser/config/cli/plan/pipeline/*`，**均不触碰 workflow** → #63 的单行 CI 改动**无冲突** |
| CI 一行冲突 | 无。但见 **F7**：#62 未接入 CI |

---

## 6. 门禁阻断清单

| 级别 | 项 | 说明 |
| --- | --- | --- |
| **BLOCK** | F2 | 报告数字与自身 JSON 不一致（广东 69 vs 77/79）→ 不得按现文引用 |
| **BLOCK** | F6 | 「逐字相同」实为「规范化后相等」→ 「同一卷」结论需降级表述 |
| **BLOCK** | F3 | 0.862/0.865 含 weak 候选 → 引用时必须注明；建议同时给出 0.792/0.798 |
| **BLOCK（若下游读 `mapping`）** | F1 | `mapping` 含 ambiguous 绑定 |
| 建议修 | F4/F5 | 措辞与枚举 |
| 建议修 | F7 | 把 `reorder.test.mjs` 接进 workflow |
| 使用约定 | F8 | `imageSignal` 不代表图片内容一致 |

---

## 7. 明确不做的事

- **没有**独立可读的真实原题数据 → 本报告**不是**来源真伪验证；#62 的「同一卷」结论我**不能**独立证实，只能指出其**证明力被高估**。
- **没有**修改 #62/#63 的任何文件、任何 head、`main`。
- **没有**依赖相似度或正文相等去宣称「来源独立验真」——恰恰相反，本轮指出 #62 的 exact 只是规范化相等。

---

## 8. 复现

```bash
# 1) 两个隔离 worktree（各自的 src 路径）
node tools/fenbi/assetsqa/crosscheck_matchers.mjs \
  --reorder <wt-pr62>/tools/fenbi/src/reorder.mjs \
  --mapping <wt-pr63>/tools/fenbi/src/mapping.mjs \
  --out /tmp/cross.json

# 2) 各自测试
cd <wt-pr62>/tools/fenbi && npm ci --offline --ignore-scripts --no-audit --no-fund && \
  node --test test/reorder.test.mjs
cd <wt-pr63>/tools/fenbi && npm ci --offline --ignore-scripts --no-audit --no-fund && \
  node --test test/mapping.test.mjs
```
