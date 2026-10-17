# 异序映射审计：上海2026统考 / 广东2026统考（2026-10-18）

本文件**只含题号映射、分数与计数**，不含任何题目正文、答案、解析、图片字节、Cookie 或账号资料。
算法与测试见 `tools/fenbi/src/reorder.mjs`、`tools/fenbi/test/reorder.test.mjs`。

## 0. 前置

纯离线，未联网、未开 Chrome、未碰 profile、**未做任何初始化**（5 次额度已用尽，本轮为 0 次）。
机器 load 0.08，10.3 GB 可用 RAM，NVMe util <1% —— 资源充裕，**全量 130/90 题**处理，未降级为 30 题试点。

## 1. 方法（为什么不沿用"同号对齐"）

旧对齐器按**题号**匹配，故上海得 0/130。本审计改为：

1. **身份只由规范化正文完全相同（exact hash）确立**；相似度仅用于提出候选，**不单独定身份**。
2. **双向互最佳 + 一对一**：源题与库题各自的最佳必须是同一对，且一题不得多绑。
3. 内容雷同的题（如资料分析公共提示语）会落入 `ambiguous_multi_candidate`，**交由人工，不强行绑定**。
4. 图片题（正文 <8 字且含图）单列 `image_only_not_comparable`，**不计入覆盖率**。
5. 结构校验：匹配后比较选项数。

## 2. 结果

| 卷 | sourceId | 源题 | 库题 | 覆盖率 | 一对一 |
| --- | --- | --- | --- | --- | --- |
| 上海2026 统考 | `8472470` | 130 | 129 | **0.862** | **true** |
| 广东2026 统考 | `8399765` | 90 | 86 | **0.865** | **true** |

### 上海2026 分类

| 类别 | 数量 |
| --- | --- |
| `exact_same_number`（逐字相同且同号） | **0** |
| `exact_reordered`（**逐字相同、不同号**） | **68** |
| `near_reordered`（近似、不同号） | 35 |
| `weak_candidate_review`（弱候选，需人工） | 9 |
| `ambiguous_multi_candidate`（多候选，拒绝强绑） | 9 |
| `unmatched_no_candidate` | 9 |
| `repo_only_absent_in_source` | 16 |
| `image_only_not_comparable` | 0 |

### 广东2026 分类

| 类别 | 数量 |
| --- | --- |
| `exact_same_number` | **11** |
| `exact_reordered` | **53** |
| `near_reordered` | 7 |
| `weak_candidate_review` | 6 |
| `ambiguous_multi_candidate` | 3 |
| `unmatched_no_candidate` | 9 |
| `repo_only_absent_in_source` | 7 |
| `image_only_not_comparable` | 1 |

## 3. 结论：两卷均判为**同题异序**

这是本轮最重要的判定。证据链：

1. **逐字相同**的题对分别为 **68**（上海）与 **53**（广东）——两份**不同的卷子不可能共享 68 道逐字相同的题**，故排除「不同卷型」。
2. 映射近乎**单调**：上海沿源题序仅 **4 处逆序 / 112 对**，广东仅 **1 处逆序 / 78 对**。
3. 偏移呈**块状**而非随机：上海 `+15 / +28 / −50 / −15 / −25` 等整块位移；广东 `+1 / +5 / −4` 分块位移。
   → 典型「同一卷子被按区块重排 / 插入」。

**因此：上海2026 与广东2026 判定为「同一卷、题序不同」，而非内容版本差异，更非不同卷型。**

### 明确不成立的替代解释

| 假设 | 判定 | 理由 |
| --- | --- | --- |
| 不同卷型 | **排除** | 68 / 53 道逐字相同题，非同卷不可能 |
| 内容版本差异（不同回忆版） | **不是主因** | 主因是逐字相同；版本差异只可能解释残余部分 |
| 图片题不可比较 | **基本排除** | 上海 0 道；广东仅 1 道 |

## 4. 不确定性与覆盖必须分开看

| 项 | 数值 | 含义 |
| --- | --- | --- |
| 已建立一对一映射 | 上海 112 / 广东 69 | 其中 exact 68 / 64，其余为近似 |
| `weak_candidate_review` | 上海 9 / 广东 6 | 分数低于建议阈值，**不建议**直接采用 |
| `ambiguous_multi_candidate` | 上海 9 / 广东 3 | 正文雷同，**无法唯一确定**，需人工 |
| `unmatched_no_candidate` | 各 9 | 源侧在库中**找不到对应** |
| `repo_only_absent_in_source` | 上海 16 / 广东 7 | 库侧在源中**找不到对应** |

**残余部分（上海 16+9、广东 7+9）一律标 unknown / 待人工，不并入"已核真"。**
其中上海有 1 道为「未征集」占位存根，不构成真实题。

## 5. 顺带：国考2026副省级 Q31（只读摘要，无正文）

| 项 | 值 |
| --- | --- |
| 源题号 | 31 |
| 库对应号 | 31（同号） |
| 状态 | `unmatched / no-safe-unique-match` |
| 源侧 | 题干 32 字、4 个选项、0 图 |
| 库侧 | 文本 73 字 |
| 判定 | **同号内容差异**，独立待核标记保持，未并入本批结论 |

## 6. 证据级别（必须如实标注）

| 级别 | 内容 |
| --- | --- |
| **单源（粉笔 UI）** | 源侧题面、题号、图引用 |
| **单源（仓库 MD）** | 库侧题面、题号 |
| **独立第三方 QA** | **无** |

→ **本轮只能宣称"两卷为同题异序、映射覆盖率约 0.86"，不能宣称"原题已全部核真"**。
两卷均**没有**独立的第三方来源交叉验证，故不得标记为权威核真。

## 7. 待人工 / 保留争议

1. 上海 9 处 `ambiguous_multi_candidate` + 9 处 unmatched + 16 处 repo-only。
2. 广东 3 处 ambiguous + 9 处 unmatched + 7 处 repo-only + 1 处图片题。
3. **上海 Q44 的源解析争议保留**（本轮未处理，不因异序映射而消解）。
4. **广东仍保留"不同回忆版"的可能性**：异序是主因，但不排除局部版本差异。

## 8. 复跑命令

```bash
cd /home/fjd/workspaces/gwy-zhenti-fenbi/repo/tools/fenbi
node --test test/reorder.test.mjs          # 9 tests, exit 0
node --test test/model.test.mjs test/browser.test.mjs test/pipeline.test.mjs test/dom.test.mjs test/align.test.mjs test/reorder.test.mjs
# 75 tests, exit 0
```

含正文的中间结果与映射明细只留在本机 `work/fenbi/reorder-audit-20261018/`（0700/0600，gitignored），未上传。
