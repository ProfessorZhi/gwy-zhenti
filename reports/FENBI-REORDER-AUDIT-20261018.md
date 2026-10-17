# 异序映射审计（修订版 R2）：上海2026统考 / 广东2026统考

本文件**只含题号映射、分数与计数**，不含题目正文、答案、解析、图片字节、Cookie 或账号资料。
算法：`tools/fenbi/src/reorder.mjs` · 测试：`tools/fenbi/test/reorder.test.mjs`（已接入 CI）。
**本版按独立 QA（PR #64）的 F1–F7 修订；所有数字均由本文附带的 JSON 直接重算，并有 `verify-reorder-stats.mjs` 校验闭合。**

## 0. 口径更正（必须先读）

| 旧表述（错误/高估） | 本版正确表述 |
| --- | --- |
| 旧称「逐字相同 / byte-identical」——**本版已撤回该措辞** | **`normalized_equal`** —— 规范化后相等（NFKC、全角折叠、标点/空白剥离）。**不同原文也可能判等，故不能当作官方同卷认证。** |
| 「近乎单调」 | **不成立**。相邻下降点少 ≠ 单调；真实逆序对占比上海 **19.6%**、广东 **7.0%** |
| 「coverage 0.862 / 0.865」 | 那是**含 weak 的候选覆盖**，不可当可用覆盖。可用口径见 §2 |
| mapping 含歧义绑定 | 歧义项**已剔除**，单列 `reviewCandidates` |

## 1. F1：歧义不再绑定

- `mapping` **只含非歧义、双向互最佳、一对一**的绑定。
- 同分并列一律进 `reviewCandidates`，**不进 mapping**（校验器断言二者题号不相交）。
- 等级：`normalized_equal_same_number` / `normalized_equal_reordered` / `near` / `weak`；歧义为 `manual_review_ambiguous`，不参与任何覆盖分子。

| 卷 | approved mapping | reviewCandidates（不绑定） |
| --- | --- | --- |
| 上海2026 | **112** | **9** |
| 广东2026 | **77** | **3** |

## 2. F3：三种覆盖口径分开报告

| 口径 | 上海 | 广东 | 含义 |
| --- | --- | --- | --- |
| **exact**（仅 `normalized_equal`） | **0.523**（68/130） | **0.719**（64/89） | 最强证据 |
| **high-confidence**（exact+near，**不含 weak**） | **0.792**（103/130） | **0.798**（71/89） | 可表述为"已映射" |
| **candidates**（含 weak） | 0.862（112/130） | 0.865（77/89） | **仅表示有候选，不是可用覆盖** |

> 广东 eligible = 90 − 1 张图片题 = 89；上海无图片题，eligible = 130。

## 3. F2：所有数字与 JSON 一致

| 项 | 上海 | 广东 |
| --- | --- | --- |
| 源题 / 库题 | 130 / 129 | 90 / 86 |
| 可比较源题（eligible） | 130 | 89 |
| exact（normalized_equal） | 68 | 64 |
| near | 35 | 7 |
| weak | 9 | 6 |
| approved mapping | **112** | **77** |
| reviewCandidates | **9** | **3** |
| 未匹配（源） | 9 | 9 |
| 图片题不可比较 | 0 | 1 |
| 库侧独有 | 17 | 9 |

闭合校验（脚本实测，全部通过）：

- 上海：`112 + 9 + 9 + 0 + 0 = 130`（源）；`112 + 17 = 129`（库）
- 广东：`77 + 3 + 9 + 0 + 1 = 90`（源）；`77 + 9 = 86`（库）

## 4. F4：逆序必须用逆序对，不是相邻下降

| 卷 | 相邻下降点 | **真实逆序对 / 总对数** | 逆序率 |
| --- | --- | --- | --- |
| 上海2026 | 4 | **1219 / 6216** | **19.6%** |
| 广东2026 | 1 | **205 / 2926** | **7.0%** |

（总数按 approved mapping 计算：上海 112 对 → 6216；广东 77 对 → 2926。）

**「近乎单调」的说法撤回。**

## 5. F5：完整偏移分布（repN − srcN）

- **上海**：`−50:19, −25:10, −15:13, −1:16, +3:7, +7:1, +15:15, +28:17, +31:14`（9 种，合计 112）
- **广东**：`−50:5, −4:16, 0:15, +1:26, +5:15`（5 种，合计 77）

## 6. 结论（证据强度已下调）

在两卷上，**大多数可映射题的 `normalized_equal` 对呈块状位移**，与「同一卷被按区块重排/插入」一致；
上海同时存在 9 处歧义、广东 3 处歧义，均**未绑定**。

**但必须明确**：
- 这是 **`normalized_equal`** 层面的证据，**不是原文字节相等**；
- 因此**不能**据此宣称「官方确认两卷为同一份卷子」；
- 残余（上海 9 未匹配 + 17 库独有；广东 9 + 9 + 1 图片题）保持 **unknown**；
- **没有独立第三方来源 QA**，故两卷均**不得**标记为"原题已核真"。

## 7. 保留争议

1. **上海 Q44 源解析争议** —— 保留，未因异序映射而消解。
2. **广东不同回忆版的可能性** —— 保留；异序是主因，但不排除局部版本差异。
3. **国考2026副省级 Q31** —— 同号内容差异，`needs_review` 保持独立。

## 8. F7：测试已接入 CI

`.github/workflows/fenbi-framework.yml` 的测试命令已加入 `test/reorder.test.mjs`。

```bash
cd tools/fenbi
node --test test/reorder.test.mjs        # 14 tests, exit 0
node --test test/model.test.mjs test/browser.test.mjs test/pipeline.test.mjs \
  test/dom.test.mjs test/align.test.mjs test/reorder.test.mjs   # 80 tests, exit 0
node ../../driver/verify-reorder-stats.mjs                    # 一致性校验, exit 0
```

新增测试含**合成负例**：歧义不强绑、`normalized_equal` 与字节相等区分、coverage 三口径分离、
逆序对 vs 相邻下降、空签名不得自匹配、图片题不进 mapping。**全部无 Chrome 依赖。**

## 9. 复跑与产物

- 统计 JSON：`reports/FENBI-REORDER-AUDIT-20261018.json`（可复跑，题号/分数/计数，无正文）
- 含正文的明细：仅本机 `work/fenbi/reorder-audit-20261018/*-detail.json`（0700/0600，gitignored，未上传）
