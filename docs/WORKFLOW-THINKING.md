# 工作流设计思路：让粉笔整理一直跑，而不是一直断

写给项目所有者和接手的 agent。前面几轮踩过的坑都总结在这里；新的做法以本文为准，
`docs/WORKFLOW-GPT-DISPATCH.md` 里与本文冲突的部分（定时巡检、按批派单）不再适用。

## 目标

粉笔网页上 2016–2026 年的行测、申论 → 整理成本库稳定的 Markdown 版本：
题干、选项、材料、插图、答案、解析齐全，并以粉笔为准逐卷对齐。
**唯一进度指标：粉笔目录卷数（分母）与已进入 `main` 的卷数（分子）。**

## 一、为什么以前总是断

| 现象 | 根因 |
|---|---|
| 采集一阵就停，要人去重启 | 非风控类失败（超时、找不到行、连续 3 卷失败）也写 `STOP`；单轮异常让整个服务退出 |
| 每小时只有 35 卷 | 每轮只处理 3 卷（`SERVICE_BATCH=3`），每轮都要付目录巡检、启动浏览器、轮间 60 秒等固定开销；每卷还有 13 秒的固定等待 |
| 修复合进 `main` 也不生效 | 同一套代码有三份：Dell 上 git 外的 `driver/`、仓库存档、集成分支上的发布代码，各不相同 |
| agent 一直在绕、PR 越开越多 | 每次派单都是一个新会话：不知道已定的规则，倾向于"调查 → 写新工具 → 交报告"；规则写在文档里，可以被反复讨论 |
| 入库数一直是 0 | 替换开关没开、PR 没人合、Draft 工具 PR 堆积 |

## 二、原则

1. **生产线是固定程序，一直跑**：采集服务和发布服务都是 systemd 常驻服务，`Restart=always`。不靠 GPT 定时任务驱动，也不按批次派单。
2. **只有风控信号才停**：验证码、登录失效、403/429，写 `STOP` 并停下等人。其他失败一律退避 15 分钟后继续，失败的卷下次重新入队。
3. **只有一份代码**：Dell 直接从仓库 `main` 的 checkout 运行。部署 = `git pull` + 重启服务。Dell 上不允许有仓库外的脚本。
4. **规则写进代码和配置，不靠 agent 判断**：粉笔优先替换（题数更少不替换）、粉笔也缺的题标注后照常发布、答案冲突用粉笔并注明、私有存储已授权、只收 2016–2026。
5. **GPT 按需查询，不定时巡检**：用户问的时候，GPT 去 Dell 读看板和日志、回答问题。没人问的时候，生产线自己跑。
6. **代码改动走 PR**：同一时间最多一个代码 PR；只在"进入 `main` 的卷数"停止增长时才改代码，并且只改造成停滞的那一处。

## 三、结构

```text
fenbi-collector（常驻，唯一使用浏览器和登录状态）
  目录巡检 → 建队列 → 抓题 → 交白卷读解析页 → 回填答案解析 → 下载图片 → 写 work/fenbi/papers/
  每轮 30 卷，轮间 10 秒；风控信号 → STOP；其他失败 → 退避 15 分钟后继续

fenbi-publisher（常驻，不碰浏览器）
  每 5 分钟：转换（增量）→ 发布 A 卷（粉笔优先替换）→ 提交推送集成分支 → 更新 BOARD.md

用户
  每天合并一次题目 PR（或授权纯内容 PR 自动合并）
  想知道进度时问 GPT

GPT（按需）
  读 BOARD.md 和日志 → 回答；遇到 STOP 或表外问题 → 告诉用户
```

服务配置模板：`deploy/systemd/fenbi-pipeline.service.example`（采集）、`deploy/systemd/fenbi-publisher.service.example`（发布）。

## 四、这一轮的代码改动

| 文件 | 改动 | 目的 |
|---|---|---|
| `driver/fenbi-service.mjs` | 默认每轮 30 卷、轮间 10 秒、重点区 2 小时重扫一次 | 摊薄每轮固定开销 |
| 同上 | 目录、重点区、抓题、交卷的连续失败改为退避后继续；单轮异常不再结束服务 | 不再动不动就停 |
| `driver/capture-new-generic.mjs` | 固定等待（2.5 / 4 / 13 秒）改为"等到页面元素出现就继续"，并等题目数稳定下来；超时上限不低于原来的固定等待 | 每卷省约 10–15 秒，题目不会少抓 |
| `driver/*.mjs` | 所有模块都读取 `FENBI_WORK_DIR` | 代码从仓库运行时，数据仍在原来的 work 目录 |
| `deploy/systemd/*.example` | 采集、发布两个模板改为 `Restart=always` | 进程退出自动拉起 |

**还没做、值得下一步做的**：抓题目前仍是一卷启动一次浏览器、串行执行，交卷那一步才用到 3 个标签页。把抓题并进交卷的同一个浏览器、3 个标签页一起跑，预计还能快 2–3 倍。这一步要改动和粉笔页面交互的流程，需要在 Dell 上实测，所以单独做。

## 五、部署步骤（在 Dell 上做一次）

模板在仓库根目录的 `deploy/systemd/`（说明见同目录 `README.md`），模板里的 `REPO_ABSOLUTE_PATH`、`NODE_ABSOLUTE_PATH` 要换成实际路径。

```bash
# 1. 建 main 的 checkout，作为采集代码的唯一来源
git clone <repo> /home/fjd/workspaces/gwy-zhenti-main && cd /home/fjd/workspaces/gwy-zhenti-main/tools/fenbi && npm ci
# 2. 环境变量放在仓库外的 ~/.config/gwy-zhenti/collector.env，并打开模板里的 EnvironmentFile 行：
#    FENBI_WORK_DIR=<原来的 work/fenbi 目录，登录 Profile 和缓存都在这里>
#    SERVICE_BATCH=30  SERVICE_INTERVAL=10  SERVICE_FOCUS_RESCAN=7200  SERVICE_BACKOFF=900（每行一个）
# 3. 用 deploy/systemd/fenbi-pipeline.service.example（采集）和 fenbi-publisher.service.example（发布）
#    替换路径后覆盖原来的服务文件，让 ExecStart 指向这个 checkout，不再指向 git 外的 driver/
systemctl --user daemon-reload
systemctl --user restart fenbi-pipeline fenbi-publisher
systemctl --user enable fenbi-pipeline fenbi-publisher
loginctl enable-linger fjd
```

以后更新采集代码：`cd /home/fjd/workspaces/gwy-zhenti-main && git pull && systemctl --user restart fenbi-pipeline`。
发布服务每轮会自己合入 `origin/main`，不需要单独更新。
