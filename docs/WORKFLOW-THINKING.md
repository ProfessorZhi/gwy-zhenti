# 工作流设计思路：让粉笔整理一直跑，而不是一直断

写给项目所有者和接手的 agent。前面几轮踩过的坑都总结在这里；新的做法以本文为准，
`docs/WORKFLOW-GPT-DISPATCH.md` 里与本文冲突的部分（定时巡检、按批派单）不再适用。

## 目标

粉笔网页上 2008–2026 年的行测、申论（现行不设年份下限）→ 整理成本库稳定的 Markdown 版本：
题干、选项、材料、插图、答案、解析齐全，并以粉笔为准逐卷对齐。
**唯一进度指标：粉笔目录卷数（分母）与已进入 `main` 的卷数（分子）。**
上线顺序：先保证风控正确、发布链路正确、内容质量不下降，再提速。

## 一、为什么以前总是断

| 现象 | 根因 |
|---|---|
| 采集一阵就停，要人去重启 | 非风控类失败（超时、找不到行、连续 3 卷失败）也写 `STOP`；单轮异常让整个服务退出 |
| 每小时只有 35 卷 | 每轮只处理 3 卷（`SERVICE_BATCH=3`），每轮都要付目录巡检、启动浏览器、轮间 60 秒等固定开销；每卷还有 13 秒的固定等待 |
| 风控信号可能漏判 | 主服务只看 `summary.risk.http403/429`，而交卷子进程把风险放在 `metrics.risk`、图片子进程用 `s401_403/s429_503`；连续失败判断读错了 `stopReason` 的位置 |
| 修复合进 `main` 也不生效 | 同一套代码有三份：Dell 上 git 外的 `driver/`、仓库存档、集成分支上的发布代码，各不相同 |
| agent 一直在绕、PR 越开越多 | 每次派单都是一个新会话：不知道已定的规则，倾向于"调查 → 写新工具 → 交报告"；规则写在文档里，可以被反复讨论 |
| 入库数一直是 0 | 替换开关没开、PR 没人合、Draft 工具 PR 堆积 |

## 二、原则

1. **生产线是固定程序，一直跑**：采集服务和发布服务都是 systemd 常驻服务。不靠 GPT 定时任务驱动，也不按批次派单。
2. **故障分三类处理**：
   - **风控信号**（验证码、登录失效、未授权；或一小时内累计 3 次 403/429）：写 `STOP`，正常退出（退出码 0），**不会被自动拉起**，等人处理。
   - **普通失败**（超时、网络、找不到行、单次 403/429、一轮异常）：退避 15 分钟后继续；退避期间每 30 秒检查一次 `STOP`，人工暂停立即生效。连续退避 4 次（约 1 小时）写 `work/fenbi/ALERT` 提醒人看，但不停止重试；一轮正常走完就清掉 `ALERT`。
   - **进程意外崩溃**：以非 0 退出，由 systemd `Restart=on-failure` 拉起；`STOP` 存在时服务一启动就退出，不会绕过。
3. **只有一份代码，但发布写在独立的集成工作树**：采集服务直接从 `main` 的 checkout 运行；发布服务的代码与 `main` 同步，但在**非 main 的集成分支工作树**里运行（`batch-promote` 拒绝在 main 上发布），题目通过纯内容 PR 进入 `main`。Dell 上不允许有仓库外的脚本。
4. **规则写进代码和配置，不靠 agent 判断**：粉笔优先替换（题数更少不替换）、粉笔也缺的题标注后照常发布、答案冲突用粉笔并注明、仓库公开且用户已同意收录（第三方内容授权未逐一核实）、只收 2008–2026（不设历史下限）。
5. **GPT 按需查询，不定时巡检**：用户问的时候，GPT 去 Dell 读看板和日志、回答问题，默认只读。遇到 `STOP`、`ALERT`、服务停止，告诉用户，由用户决定。
6. **代码改动走 PR**：同一时间最多一个代码 PR；只在"进入 `main` 的卷数"停止增长时才改代码，并且只改造成停滞的那一处。
7. **自动合并要有完整的闸门**：`tools/fenbi/src/content-gate.mjs` 只检查路径、清单和图片是否存在，是初步的结构检查，**不能单独作为自动合并 main 的依据**。在补齐逐卷 sourceId/SHA、QA 回执、授权边界、题数不倒退等检查之前，题目 PR 由用户合并。

## 三、结构

```text
fenbi-pipeline（采集，常驻，唯一使用浏览器和登录状态；从 main checkout 运行）
  目录巡检 → 建队列 → 抓题 → 交白卷读解析页 → 回填答案解析 → 下载图片 → 写 work/fenbi/papers/
  每轮 SERVICE_BATCH 卷（默认 10，逐级放量），轮间 10 秒
  每个子进程结束先过风控（driver/service-risk.mjs），再判断普通失败

fenbi-publisher（发布，常驻，不碰浏览器；在集成分支工作树运行）
  每 INTERVAL 秒：转换（增量）→ 发布 A 卷（粉笔优先替换）→ 提交推送集成分支 → 更新 BOARD.md

用户
  合并题目 PR；想知道进度时问 GPT

GPT（按需）
  读 BOARD.md、ALERT、STOP 和日志 → 回答；需要动作时请用户决定
```

服务配置模板：`deploy/systemd/fenbi-pipeline.service.example`（采集）、`deploy/systemd/fenbi-publisher.service.example`（发布），都是 `Restart=on-failure`。

## 四、本 PR 的代码改动

| 文件 | 改动 | 目的 |
|---|---|---|
| `driver/service-risk.mjs`（新） | 统一读取三种子进程回执里的风控字段；硬风控立即停，403/429 一小时内累计 3 次才停 | 风控信号不再漏判 |
| `driver/fenbi-service.mjs` | 每个子进程后先过风控再处理失败；读对 `stopReason` 位置；普通失败退避、可被 STOP 打断、长时间退避写 ALERT；单轮异常不结束服务；崩溃以非 0 退出 | 不再动不动就停，也不会无声地无限重试 |
| 同上 | 默认每轮 10 卷（原 3）、轮间 10 秒（原 60）、重点区 2 小时重扫（原 30 分钟） | 摊薄固定开销；30 卷要实测后再开 |
| `driver/capture-new-generic.mjs` | 切换地区后等**目标卷那一行**出现（不是任意一行）；题目数连续 3 秒不变且点开后至少 6 秒才截取；若少于页面标明的题数，再等 8 秒重截一次；记录 `waitMs`、`renderRetry` | 缩短原来固定 13 秒的等待，同时不放松完整性；不完整的卷仍由 validateDocument 判为不完整 |
| `driver/*.mjs` | 所有模块读取 `FENBI_WORK_DIR`（与 #102 一致） | 代码从仓库运行时，数据仍在原来的 work 目录 |
| `deploy/systemd/*.example` | `Restart=on-failure` | 崩溃自动恢复，STOP 不被绕过 |

**还没做、值得下一步做的**：抓题目前仍是一卷启动一次浏览器、串行执行，交卷那一步才用到 3 个标签页。把抓题并进交卷的同一个浏览器、3 个标签页一起跑，预计还能快 2–3 倍。这一步改动和粉笔页面交互的流程，需要先在 Dell 上把本 PR 跑稳，再单独做。

## 五、部署与放量（在 Dell 上）

模板在仓库根目录的 `deploy/systemd/`（说明见同目录 `README.md`），模板里的 `REPO_ABSOLUTE_PATH`、`NODE_ABSOLUTE_PATH` 要换成实际路径。

```bash
# 1. 采集代码的唯一来源：main 的 checkout
git clone <repo> /home/fjd/workspaces/gwy-zhenti-main
cd /home/fjd/workspaces/gwy-zhenti-main/tools/fenbi && npm ci

# 2. 采集环境变量放在仓库外 ~/.config/gwy-zhenti/collector.env，并打开模板里的 EnvironmentFile 行：
#    FENBI_WORK_DIR=<原来的 work/fenbi 目录，登录 Profile 和缓存都在这里>
#    SERVICE_BATCH=10
#    SERVICE_INTERVAL=10
#    SERVICE_FOCUS_RESCAN=7200
#    SERVICE_BACKOFF=900

# 3. 发布服务：在集成分支工作树里同步 main 的代码（不在 main 上运行）
cd /home/fjd/workspaces/gwy-zhenti-fenbi/integ && git fetch origin && git merge origin/main

# 4. 用两个模板替换路径后覆盖原服务文件：采集 ExecStart 指向 main checkout，不再指向 git 外的 driver/
systemctl --user daemon-reload
systemctl --user restart fenbi-pipeline fenbi-publisher
loginctl enable-linger fjd
```

**放量**：先用 `SERVICE_BATCH=10` 跑 1–2 小时，确认四件事——每小时卷数、来源题数是否与页面标明的一致（看 `renderRetry` 是否频繁）、答案解析和图片完整率、没有风控信号。都正常再改成 30 并重启。

**回滚**：采集 = 把服务的 ExecStart 改回原来的 `driver/` 并重启；发布 = 集成工作树 `git reset --hard <切换前的提交>` 并重启。切换前记下两边的提交号。

以后更新：采集 `cd gwy-zhenti-main && git pull && systemctl --user restart fenbi-pipeline`；发布在集成工作树 `git merge origin/main && systemctl --user restart fenbi-publisher`。

## 六、单卷流水线（`SERVICE_MODE=worker`）

用户已决定：重构抓取链路、交卷前停留 15 秒、闸门通过后自动合入 main。

### 为什么旧链路慢

旧链路把一卷拆成 5 个独立步骤（抓题 → 交卷 → JSON 回填 → 图片 → 发布），每步是一个子进程、各自启动浏览器、各自扫一遍全部缓存；
抓题每卷还要单独启动一次浏览器并从目录入口重新进入；最后还要等人合并 PR。每卷的真实工作只有十几秒，其余全是固定开销和等待。

### 新链路：一卷一条流，一个浏览器多个标签页

```text
worker/worker.mjs（fenbi-service 的一步，一次跑到 WORKER_MAX_PAPERS 卷或 WORKER_MAX_MS）
  一个浏览器 × WORKER_TABS(3) 个标签页，每个标签页循环：
    目录找行（该标签页已在同一地区就不重新进入）→ 点开练习（互斥锁内，init 预算 1，已有练习则 0）
    → 解析题目页 → 停留 15 秒 → 登记"交卷中" → 交白卷 → 解析页 DOM + solution JSON → 图片 → 校验 → 写缓存
    → 立即转换（单卷 ingest）并发布进集成工作树（粉笔优先替换、题数更少不替换、同路径取最完整来源）
  每 10 卷或 10 分钟：提交 → 合入 origin/main → 完整闸门 → 推送集成分支 → 闸门通过且 AUTO_MERGE=1 时快进推送 main
```

| 文件 | 作用 |
|---|---|
| `worker/flow.mjs` | 单卷浏览器流程；导航闸门（≥2.5 秒）和"打开练习"互斥锁由所有标签页共用 |
| `worker/analysis-merge.mjs` | 解析页 DOM 与 solution JSON 合并（纯函数，规则与旧 t2-collector/t2-backfill-json 相同） |
| `worker/queue.mjs` | 队列：先续交已抓未交的卷，再抓新卷；沿用旧链路的两本台账，新旧链路可互相接续 |
| `worker/gate.mjs` | 自动合入 main 的完整闸门 |
| `worker/publish.mjs` | 单卷落地、批量提交与推送 |
| `src/batch-ingest.mjs` | 抽出 `ingestFolder`（单卷转换），`runBatch` 行为不变 |

**不变的约束**：每卷至多 1 次 init、至多交 1 次白卷且不作答（交卷前先写台账 `submitting`，之后任何中断都不会再交第二次，旧链路也认这个状态）；
登录 Profile 和 Cookie 只在本机；任何风控信号（验证码、登录失效、403/429，含图片接口的 401/403）让所有标签页停下、本次运行结束，由 fenbi-service 按原规则 STOP 或退避。

**完整闸门**（`worker/gate.mjs`，任何一项不过就不动 main，写 `work/fenbi/ALERT-merge-gate`，集成分支照常推送）：
content-gate 的结构检查（只改内容路径、不删卷、清单齐全、图片存在）之外，逐卷核对回执 SHA 与文件一致且为 A 级、授权覆盖 sourceId、
题数等于回执且连续、不少于 main 上同一路径的题数、没有"征集中"残留、清单 sha256 与文件一致、新增图片按内容哈希命名且哈希一致、已有图片不被改写。

**速度**：打开练习一步串行（含 2.5 秒导航间隔），停留、交卷、解析、图片三个标签页并行。离线假站点只验证流程正确，不代表真实速度；
真实卷数/小时以 Dell 上 3 卷、10 卷试跑的 `worker.log` 为准，不做预测。

**图片与风控**：单卷流程里图片遇到 401/403/429/503 立即停止本卷剩余图片（留作 pending），并计入风控（401 视同登录失效硬停）。
worker 模式下每轮 worker 之后再跑一次只读补图（t2-asset-pass），下一轮 worker 开头把补齐图片的已交卷卷补落地。

### 部署（在 Dell 上）

```bash
# 1. 采集代码：main checkout 更新到含本改动的 main
cd /home/fjd/workspaces/gwy-zhenti-main && git pull && (cd tools/fenbi && npm ci)

# 2. 集成工作树：从 origin/main 新建一个干净的集成分支（只允许内容改动，否则闸门永远不过）
cd /home/fjd/workspaces/gwy-zhenti-fenbi/integ && git fetch origin && git switch -C fenbi-integ origin/main

# 3. ~/.config/gwy-zhenti/collector.env 追加：
#    SERVICE_MODE=worker
#    INTEG_REPO=/home/fjd/workspaces/gwy-zhenti-fenbi/integ
#    RIGHTS_FILE=<rights.json 的绝对路径>
#    PUSH=1
#    AUTO_MERGE=1
#    WORKER_TABS=3
#    WORKER_DWELL_MS=15000
#    WORKER_MAX_PAPERS=3        # 先 3 卷试跑，再 10，再 60
# 4. 发布服务不再需要（worker 自己落地），并且两者不能同时写集成工作树：
systemctl --user stop fenbi-publisher && systemctl --user disable fenbi-publisher
systemctl --user restart fenbi-pipeline
```

试跑看 `work/fenbi/worker.log`：每卷一行 `paper`（status、题数/应有题数、答案数、init 次数、耗时），`land`、`publish`（闸门结果、是否推送 main）。
3 卷正常（init=1、题数与应有一致、答案齐、main 有新提交）→ `WORKER_MAX_PAPERS=10` → 正常再调到 60。

**回滚**：collector.env 去掉 `SERVICE_MODE=worker`（回到分步链路），重新启用 fenbi-publisher；main 上的内容提交可以 `git revert`。
