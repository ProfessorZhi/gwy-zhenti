# 单 persistent context · 双 Page 并发读取验证（2026-10-17）

本文件只记录**身份、数量、状态与校验结果**，不含题目正文、答案、解析、Cookie 或账号资料。

## 0. 执行前置（实测）

| 项 | 值 |
| --- | --- |
| profile / work / Singleton 锁 | **均无** |
| Chrome / CLI 进程 | **0** |
| CPU | 20 核，load **0.54** |
| RAM | 31.3 GB 总 / **13.7 GB 可用** |
| 磁盘 | 282 GB 可用（37% 已用） |

→ **GREEN**，可安全执行 2 页并发。

## 1. 隔离组合树（未触碰任何他人 worktree）

在自有工作区新建 worktree `combo/`，基线 = **PR #31 head `6e38f30`**（含 `schedule.mjs` 与
`--concurrency N`），再合入 **PR #36 head `4372e8a`**（collection-stub 闸门）。

合并冲突 3 处（`align.mjs` / `validate.mjs` / `model.test.mjs`）：两侧均为**互补闸门**，
按"两者共存"解决。`model.test.mjs` 因直接拼接导致花括号失衡，改为**以 HEAD 有效版本为底、
追加 #36 自包含测试块**重建；最终 `node --check` 通过、括号平衡 depth=0。

组合树离线测试：**102 tests / 102 pass / 0 fail / 0 skip**。

## 2. 两处实测发现（组合树的真实缺陷）

### 2.1 PR #36 的占位闸门**不认识真实措辞**

用组合树的 `isCollectionStub` 跑三卷真实文档：

| 卷 | 期望占位号 | 实际检出 | validator 状态 |
| --- | --- | --- | --- |
| 江苏2025C | 12（27,29,…） | **0** | partial |
| 江苏2024A | 4（76,96,110,111） | **0** | partial |
| 广东2020 | 7（69–75） | **0** | partial |

原因：粉笔真实文案是
`题目正在全力以赴征集，将会第一时间上传` / `…，将会在征集到后第一时间上传`，
而 #36 的正则只允许尾巴 `请稍后再试|请稍后|敬请期待|感谢您的关注|谢谢|稍后重试`，
**不含"将会…第一时间上传"**。裸前缀 `题目正在全力以赴征集` 可命中，真实整句**不能**。

后果：**不会误判为 complete**（因其它维度仍 partial，`matchedButStub` 为 0），
但 `question-body-placeholder` 这条 issue **不会产生**，闸门对该文案**不生效**。
→ 建议 #36 增补该尾巴（属他人分支，我未改动）。

### 2.2 PR #31 **未**修复 `routecs`，但新增了落地核对

`publicUrl()` 仍剥离 `routecs`：练习 URL `…/exercise/1_1_3u2bp59?routecs=xingce`
→ 被剥成无查询串 → 实测落地 `about:blank`、0 题。

但 #31 新增 `landingMismatch` / `page-route-mismatch` 闸门，会**判 blocked 而不是静默读错页**
（`validateDocument` 返回 `blocked`）。因此 CLI 的 `capture --concurrency N` 目前**到不了**练习页，
但**不会**产生错误的 complete 结果。

## 3. 双 Page 并发实测（唯一一次有界实站只读）

- 方式：**单 persistent context**、`context.newPage()` 开第二页、`Promise.allSettled` **同时导航**
- 目标：两份**已存在**练习（浙江2026C `1_1_3u2bp59`、江苏2025C `1_1_3u32di3`）
- 全程只读 GET；**未**修改 requestPolicy；**未**初始化、作答、交卷、购买

### 结果：**通过**

| 检查项 | Page A | Page B |
| --- | --- | --- |
| 卷 / sourceId | 浙江2026C / `8399763` | 江苏2025C / `4189916` |
| 落地 URL 与期望一致 | **true** | **true** |
| 页面标题含本卷标识 | **true** | **true** |
| 是否混入对方标题 | **false** | **false** |
| 题目数 `app-ti` | **110** | **130** |
| 材料数 | **4** | **6** |
| `.tis-container` | 1 | 1 |
| 前 3 个题目标题键 | `3_1_beq2d…` | `3_1_cmf0j…` |
| 这些键是否见于既往采集 | **3/3 是** | **3/3 是** |
| 图片抽样 | 3 张（sha256 已记录） | 3 张（sha256 已记录） |
| 抽样图是否见于既往 assets | **3/3 是** | **3/3 是** |

**总体**：`ok = true`；并发导航 **295 ms**，两页均 fulfilled；
**跨卷污染 = false**；两页图片抽样 **重叠 0 张**（各自 sha256 互不相同，且各自与既往采集一致）。

### 安全面

- 非 GET 请求：**0 条**（`writes: []`）→ **没有发生任何练习初始化**，与"仅复用已有练习"一致
- `guard = { blockedWrites: 0, blockedNavigation: 0, blockedHost: 4, blockedUrl: 0 }`
- 结束后：**锁已释放**、无 `SingletonLock`、Chrome 进程 **0**
- `auth` 记录为 `unknown`：本次直接进入练习页，未触发 `users/info`，故未复证登录态
  （**不代表登录失效**；两页均成功渲染 110/130 题即为有效访问的证据）

## 4. 占位题在本次并发读数中的表现

Page B（江苏2025C）读到 **130** 个题目标题，其中含 **12 个占位存根**。
本次仅核对"每页独立性与身份"，**未**在并发路径上重跑 align；
占位题是否被计入 matched 的验证见 §2.1（离线，结论：闸门对该措辞不生效，但未产出 complete）。

## 5. 已知未解决 / 留给下一小时

1. **#36 措辞缺口**（§2.1）——需其 lane 补 `将会…第一时间上传` 尾巴；补后应重跑离线闸门验证。
2. **#31 未修 `routecs`**（§2.2）——CLI 并发路径仍到不了练习页；目前只能由 lane 内 driver
   以完整观察 URL 导航验证能力（本次即如此）。要让 `capture --concurrency` 真正可用，需修
   `publicUrl` 或在 job 中保留原始查询串。
3. 本次只验证 **2 页**；3 页并发、以及并发下的 checkpoint/material/sha 落盘比对尚未做。
4. 并发下的**逐页 checkpoint 写入**未验证（本次只读核对，未触发落盘）。

## 6. 产物

- 并发证据：`work/fenbi/concurrency-20261017/concurrency-2page.json`（0600，含 sha256，无正文/凭据）
- 占位闸门验证：`work/fenbi/audit-20261017/stub-gate-verification.json`
- 组合树：`/home/fjd/workspaces/gwy-zhenti-fenbi/combo`（本机隔离 worktree，未推送）

## 7. 边界

未改 `main`、未合并任何 PR、未写他人分支或 worktree；未上传第三方全文/图片/账号数据；
未重复初始化、未作答、未交卷、未购买、未猜 API 或试卷 ID。
