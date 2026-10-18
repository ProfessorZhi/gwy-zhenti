# 粉笔答案解析核验能力与框架测试（2026-10-17）

独立 lane。基准为 PR #20 head `e1feb5187ec3544cde62a1a128a6269a8d63011b`，工作区 `gwy-zhenti-answerqa`，
不写 `main`、不写 PR #20 工作树。**本轮未接触真实粉笔账号、未启动浏览器、未新增正式试卷、未减少缺口。**
方法、字段与判定口径见 [tools/fenbi/README.md](../tools/fenbi/README.md) 与
[实站答案解析取证 SOP](../tools/fenbi/ANSWER-EVIDENCE-SOP.md)。

## 问题级别

### P1 — 访问提示被当成解析，整卷误判 `complete` 并可导出

`validate.mjs` 对解析槽只做"非空 + 不是占位符"检查。练习页的付费/会员/权限提示是正常文字，
因此**整卷被判 `complete`、退出码 0、可导出候选稿**；更严重的是 `checkpoint.status = complete`
会让后续 `resumeBundle` 把这一卷**当作已验证跳过，永不重采**（`store.mjs` 只认 `complete`）。

实测（离线合成夹具，`test/answerqa.test.mjs`）：

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 行测：答案正确、解析槽为"开通会员后方可查看" | `complete`，0 issues | `partial`，`explanation-access-gate` |
| 申论：答案槽为 41 字会员提示 | `complete`，0 issues | `partial`，`answer-access-gate` |
| 申论：答案槽为权限提示 | `complete`，0 issues | `partial`，`answer-access-gate` |

申论解析槽此前**没有任何实质检查**，短提示只被"参考答案<30字"这条偶然规则拦下。

### P1 — 对齐报告的结论面里根本没有答案解析

`comparePaper` 的头部 `paper` 块只有 questionCount/qidSet/order/orderById/materialCount，
逐题维度只出现在 `summary.dimensionCounts`；`summary.allQualityPassed` 是**硬编码 `false` 常量**，
不携带任何信息；`align` 命令**任何情况都返回 0**。

实测：DOM 采集的浙江式文档（题面/选项/材料齐全、答案与解析永远为空）对齐后得到
`paper.questionCount = same`、`paper.order = same`，答案与解析 109/109 `unknown`，
而退出码为 **0**。只看头部或退出码的读者会得到"对齐通过"。

### P2 — 零匹配时维度聚合为空对象，任何"无差异"检查都空过

`matched === 0` 时 `summary.dimensionCounts` 为 `{}`，`Object.values(...).every(d => d.different === 0)`
返回 `true`。整卷一道题都没对上，反而"没有差异"。

### P2 — 未声明 ID 命名空间时被默认当作与库内同命名空间

`comparePaper` 对未设置 `identity.questionIdNamespace` 的文档按库内数字 qid 处理。
DOM 复合键不会与数字 qid 相等，因此不会误配，但会产生**虚假的 `qidSet: different`**，
与 README"不把ID格式不同判作错题"相矛盾。本轮只做**披露**（`identity.questionIdNamespaceAssumed`），
不改默认值，避免影响既有对齐行为。

## 本轮代码修复

1. `src/validate.mjs`：新增访问提示检测，答案/解析槽为提示时分别记 `answer-access-gate` /
   `explanation-access-gate`，维度保持 `partial`。双阈值（正文≤120字**且**提示几乎占满正文）避免
   误伤真实答案中出现的"会员/权限/续费"表述；有图片的槽位按字节判定，不触发。
2. `src/align.mjs`：新增 `verification` 块——8 个逐题维度 + 5 个卷级检查**永远全部出现**（未观察填零），
   统一 `verified/partial/conflicting/unknown/not_applicable` 四态加不可比态，给出 `verdict`、
   `unverified`（点名 answer/explanation 等）、`notApplicable` 与判定定义；`dimensionCounts` 同样零填。
3. `src/align.mjs`：人工证据字段 `document.manualEvidence`。严格绑定（唯一落到**已被自动匹配**的采到题目），
   单独出现在 `dimension.manual`，**不并入自动计数、不能单独把整卷变为通过**；报告只保留 SHA256 与长度，
   凭据URL按 `publicUrl` 剥离。
4. `src/align.mjs` + `src/cli.mjs`：`allQualityPassed` 改为按 `verdict` 计算；新增
   `alignmentExitCode`，`align` 只有 `verified` 返回 0，其余返回 2（验收不完整），并把
   `verdict/unverified/notApplicable` 打到命令行摘要。
5. `src/align.mjs`：`identity.questionIdNamespaceAssumed` 披露默认命名空间假设（见 P2）。
6. `test/answerqa.test.mjs`：16 项离线合成夹具测试；`.github/workflows/fenbi-framework.yml` 与 README
   的测试命令同步加入该文件。

## 测试

`node --test test/model.test.mjs test/browser.test.mjs test/pipeline.test.mjs test/dom.test.mjs test/align.test.mjs test/answerqa.test.mjs`

- 修复前基线：**66 项通过，0 失败**。
- 本轮：**82 项通过，0 失败**（66 既有 + 16 新增），其中新增测试全部为离线合成夹具，
  不使用账号、网络或浏览器。
- `test/browser-smoke.test.mjs` **本机未运行**：该主机无 Chrome/Edge，此测试按设计明确失败，
  不计入通过。浏览器安装与登录属于另一 lane。

端到端复核（本机实跑 CLI，输入为离线合成文档与合成卷）：

```text
node src/cli.mjs align --document work/fenbi/normalized-synthetic.json --paper "省考/.../行测-合成.md"
退出码 2；verdict = partial；unverified = ["answer","explanation"]
```

## 未解决与登录依赖

- **答案解析仍未在实站取证。** 现有行测 DOM 适配器不读答案；粉笔复合题目 key 与库内数字 qid
  不同命名空间，JSON 答案无法按源题ID绑到 DOM 采到的题目上（会保留为 `unmatched-answer`）。
  这需要实站登录后确认答案解析的真实只读接口与字段映射，本 lane 无登录配置，未做。
- **实站步骤全部依赖另一 lane 的专用浏览器配置与登录**；本 lane 不使用其他 lane 的登录 profile，
  也未安装浏览器。
- **CI 未验证。** 新增测试文件已加入 `.github/workflows/fenbi-framework.yml` 的离线任务，
  但本 lane 未确认该仓库 Actions 是否有可用 runner，因此**不声明 CI 通过**。
- 访问提示检测是**复核触发条件**，不是"已确认被付费墙拦住"的结论；阈值（120字/几乎占满）为保守取值，
  真实长提示仍可能漏判，需实站样本回归。
- 原有 P2（默认命名空间假设）只做披露；是否改为 fail-closed 需另开变更并回归既有对齐语义。
