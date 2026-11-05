# 试卷归档：三个步骤

目标：保存缺口相关卷的题目、选项、材料、平台参考答案、文字解析和图片。只存到 `work/`，不修改试卷、不判定补题成功。

## 1. 准备任务清单

首次在 `tools/fenbi` 执行 `npm ci`，确认 `opencli doctor` 已连接用户指定的 Chrome 登录态。

agent 根据缺口清单在粉笔、华图找到卷子，进入解析页，把**实际看到的标题和解析链接**填入 `work/archive-jobs.json`：

```json
[
  {
    "provider": "huatu",
    "session": "gwy-huatu",
    "key": "shanghai-2021-b",
    "expectedCount": 127,
    "title": "页面上实际的完整试卷标题",
    "url": "https://v.huatu.com/tiku/analysis/已观察到的记录ID"
  }
]
```

粉笔填 `provider: fenbi`、独立 session 和实际 `/ti/exam/solution/...` 地址。`key` 是本地目录名，不是平台编号。每份卷一行；同卷两家来源两行。**不要猜链接，不要在清单里填写 Cookie、令牌或密码。**

`expectedCount` 必须是源站该版本的目录题量，不是本库题量。程序会等到题目节点数达到这个数，并要求答案块覆盖题目节点；只渲染了前10题时不能报整卷成功。等待后仍不完整会保存为 `questions_incomplete` / `answers_incomplete`，退出码2。

已有解析页直接复用。需要交白卷时遵守用户授权，每份练习只提交一次；会留下练习记录。未登录、验证码、无法进入解析页时记录原因并跳过该卷，不把它写成“平台没有”。

粉笔后台交卷的固定备用步骤：若 OpenCLI 返回点击成功但确认框没有出现，用 Playwright MCP 的 `browser_run_code_unsafe`，`filename` 指向 `tools/fenbi/driver/fenbi-enter-solution.playwright.js`。它验证当前页面和交卷确认框，使用后台点击方式，并等待解析页出现；不会重新登录或自行换卷。不要反复运行未生效的数字索引点击，也不要仅凭点击成功就开始归档。这个备用步骤已在甘肃2026练习验证能进入解析页，但尚未覆盖全部站点流程。

## 2. 跑一条命令

在仓库根目录：

```powershell
node tools/fenbi/driver/archive-jobs.mjs work/archive-jobs.json --concurrency 2
```

程序自动使用后台标签，核对标题和来源域、等待题目加载、整卷提取、保存图片及 SHA-256，并检查是否有答案块。Windows 下直接通过 Node 启动 OpenCLI，不把 JavaScript 拼进 shell。

默认两路浏览器会话并发；同一 session 的任务严格串行，避免相互覆盖页面。每卷图片四路下载，因此两卷最多八路图片下载。`--concurrency 1` 可降低负载，允许范围为 1–4；增加并发不保证更快。不要让另一个进程同时操纵队列中的 session。

2026-11-05 实测：北京2023粉笔解析页（135题位、135答案块、72图）与上海2021B华图解析页（127题位、127答案块、262图）两路运行总计约15.4秒，图片失败0。只计已知解析链接的导航及归档，不含找卷/登录；这不是全站吞吐保证，也不说明占位答案有效。

不要让模型逐题复制、重新写爬虫或推算答案。华图有的页面把内容直接放在 HTML 中，所以本工具保存题目区 DOM，明确标识为 DOM 采集，不伪称接口 JSON。

## 3. 只看结果，交接文件

文件在 `work/source-papers-v1/<来源>/<归档键>/<时间戳>/`：

- `content.html`：题目、材料、已有答案解析。去掉脚本、视频、个人笔记等非题目区内容。
- `images/`：原图。
- `manifest.json`：来源、题目节点数、答案块数、占位数、图片映射、哈希、限制和状态。

汇总：`work/source-papers-v1/runs.jsonl`；队列失败：`queue-failures.jsonl`。

| 结果 | 如何报告 |
| --- | --- |
| `archived` | 题目已存，有答案块，图片下载无失败；仍不代表原卷完整或每个答案有效 |
| `answers_missing` | 题目已存，答案未取得，不能算完整归档 |
| `images_incomplete` | 保留已存内容，图片待补，见 manifest |
| `needs_attention` | 需检查登录、标题、页面或连接，不能报成功 |

源侧占位和默认答案仍保留，后面清洗时处理；不要将默认 A 当真实答案。HTML 的图片地址仍为原 URL，离线清洗时按 manifest 映射替换。每次使用新时间戳目录，不覆盖旧包。归档包数与不同试卷数分别统计。

**分工固定：模型找卷和处理登录；程序采集和验收。** 从解析链接开始的归档可重复执行；找卷及交卷仍需要 agent 根据当前页面操作，尚未承诺完全无人值守。用户指定的其他窗口不参与操作。不要并行让多个 agent 操作同一个 session/tab。

## 给其他模型的交接指令

> 按 docs/workflow/SOURCE-ARCHIVE.md 执行。读取缺口清单和已有 runs.jsonl，把找到的解析页加入 work/archive-jobs.json，运行一条归档命令。仅回报成功包、答案/图片缺失包和失败原因。不要改试卷、不要临时改爬虫、不要提交 work/。标题或登录检查失败时保留失败记录，不猜测成功。

即使换 Terra/Luna，也使用相同程序和验收状态。网站结构或内容变化时可能需维护程序，不能保证未验证页面得到相同结果。

开发者测试：在 `tools/fenbi` 执行 `node --test test/archive-loaded.test.mjs test/archive-queue.test.mjs test/huatu-capture.test.mjs`。
