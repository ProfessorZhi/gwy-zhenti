# GPT 指挥手册：多 Claude Code 会话补齐整个题库

GPT 是总指挥，按本手册给 Dell A6000 上的 Claude Code 会话派任务。
抓取规则见 `docs/FENBI-FULL-CAPTURE-PLAN.md`；本手册只写**谁做什么、什么顺序、怎么判断该干什么**。

## 一、目标

1. **重点区**（国考、浙江、江苏、上海、北京、天津、广东、广州、深圳、福建）2016–2026：粉笔有的卷全部收录，带答案和解析，质量 A。
2. **其他地区**：粉笔有的卷全部收录（已有的以粉笔对齐，没有的补入）。
3. 粉笔没有的缺卷：用其他公开来源补。
4. 全部进入私有仓库，每周合一次 `main`。

## 二、速度设定（用户 2026-10-19 选定）

| 项 | 设定 |
|---|---|
| 标签页 | **3 个** |
| 交卷前停留 | **30 秒** |
| 预期速度 | 约 120 卷/小时 |
| 预期耗时 | 重点区约 2 小时，全部约 8 小时（不含开发） |

出现验证码、登录失效，或一小时内 3 次 403/429：立即全停，通知用户。不自行加标签页。

## 三、会话分工

| 会话 | 角色 | 负责 | 独占资源 |
|---|---|---|---|
| **S1** | 抓取 | T1 读解析页 → T2 常驻队列 → 一直抓 | 粉笔浏览器 Profile（全局唯一） |
| **S2** | 转换 | T3：答案/解析写入、占位题补齐、选项标签、跨卷图片 | `tools/fenbi/src/batch-ingest.mjs` |
| **S3** | 发布 | T4：A 卷 → 正式目录 + 清单 → 集成分支 → 每日 PR | 集成分支（只有它能推） |
| **S4** | 修 C 卷 | 按问题类型批量修，修完重跑转换 | 按卷认领 |
| **S5** | 非粉笔补缺 | 粉笔没有的缺卷，从公开题库 / PDF 补 | 按卷认领 |

- 同一时间最多 5 个会话，S4、S5 在第 3 阶段才开。
- 只有 S1 碰浏览器；只有 S3 推送 Git；其他会话只写本地文件。
- 一份卷同一时间只能被一个会话认领。

## 四、阶段与切换条件

| 阶段 | 内容 | 并行会话 | 进入下一阶段的条件 |
|---|---|---|---|
| **1 开发** | T1、T3、T4 同时开工；T2 由 S1 在 T1 之后做 | S1 S2 S3 | 深圳 2025 这一卷从抓取到出现在 PR 里，带 100/100 答案和解析 |
| **2 补答案** | 已缓存但缺答案的 31 卷：交白卷 → 读解析页 → 重新转换 → 发布 | S1 S2 S3 | 31 卷答案覆盖率 ≥ 95% |
| **3 重点区全量** | S1 连续抓重点区 2016–2026 全部粉笔卷 | S1–S5 | 重点区粉笔卷全部抓完，C 卷 ≤ 5% |
| **4 其他地区** | S1 先浏览其他 24 个地区的目录，再连续抓 | S1–S5 | 其他地区粉笔卷全部抓完 |
| **5 收尾** | S4 清 C 卷，S5 补非粉笔缺卷 | S4 S5 | 缺卷只剩"全网找不到"的 |

阶段 1 的三项开发要**同时派出**，不要串行。

## 五、GPT 的巡检循环（每 30–60 分钟一次）

读看板，按下表行动，**只做表里的动作**：

| 看到的情况 | 动作 |
|---|---|
| S1 抓取进程停了，队列不空 | 让 S1 从断点重启 |
| 队列空了，当前阶段还有没抓的地区 | 让 S1 把下一批目录放进队列 |
| 出现验证码 / 登录失效 / 限流停机 | 全停，通知用户，等用户处理 |
| 新增 C 卷 ≥ 5 卷 | 按问题类型派给 S4 |
| A 卷已生成但没进 PR | 让 S3 发布 |
| 某会话 1 小时内台账没有任何增长 | 看它卡在哪里：能改规则就改规则；不能就把该卷记为 `blocked`，换下一卷 |
| 一切正常 | 不派新任务，不要求任何会话写报告 |

GPT 不要做：要求补写分析报告、要求重新验证已到 A 的卷、开新的审计 PR、重新讨论第一节的目标和抓取计划里已定的决定。

## 六、任务卡

```text
T1｜S1｜读解析页
在采集代码里新增：交白卷后打开解析页，读出每题的答案和解析（DOM 为准，观察到的 JSON 作补充），
以稳定题目 ID 为键写进该卷缓存。只放行"交卷"这一个写操作。
完成：深圳 2025 行测 100/100 题有答案和解析；回执一行。限时 3 小时。
```

```text
T2｜S1｜常驻抓取（T1 之后）
队列放入当前阶段全部粉笔卷（年份 2016–2026，过滤更早的）。
每卷：开练习 → 停留 30 秒 → 交白卷 → 读解析页 → 下载图片 → 写缓存 → 立即接下一卷。
3 个标签页；卷间不留空等；遵守抓取计划第七节的自动停止条件；支持断点续抓。
完成：连续运行 1 小时不中断，回执报"本小时卷数、平均每卷秒数、风控信号次数"。限时 3 小时。
```

```text
T3｜S2｜转换升级
batch-ingest 增加：① 按题目 ID 写入答案和解析；② 粉笔占位题用本库原文补齐并标来源；
③ 修选项标签异常；④ 引用其他卷的图片时复制到本卷目录并改写路径。
完成：现有 31 卷重跑后，C 卷只剩真实缺内容的，每个 C 都写明原因。限时 3 小时。
```

```text
T4｜S3｜发布
用 batch-promote 把 A 卷写入正式目录（国考/、省考/、图片/）并更新 catalog/manifest.jsonl；
提交到集成分支，每天开一个 PR 到 main。不推 main，不开其他 PR。
完成：第一批 A 卷出现在 PR 里。限时 2 小时。
```

```text
T5｜S4｜修 C 卷（阶段 3 起）
领取一类 C 卷问题，改转换规则或补数据，重跑这些卷。
完成：这一类问题的卷变成 A，或逐卷写明"源头确实缺"。每张卡限时 40 分钟。
```

```text
T6｜S5｜非粉笔补缺（阶段 3 起）
从缺卷清单领取粉笔没有的卷，用公开题库 / PDF 补入；等级标 B。
完成：该卷入库，或写明"全网找不到"。每张卡限时 40 分钟。
```

## 七、看板（S3 每次发布时更新，GPT 只看这一张）

```text
阶段 | 队列剩余 | 本小时抓取 | 累计已抓 | A | C | 已进 PR | 缺卷 | 风控信号
地区 | 粉笔目录 | 已抓 | 有答案 | A | C | 缺卷
```

## 八、时间预期

| 时间 | 状态 |
|---|---|
| 开发半天 | 阶段 1 完成：一卷全链路跑通 |
| +1 小时 | 阶段 2 完成：31 卷补齐答案 |
| +2 小时 | 阶段 3 完成：重点区抓完 |
| +6 小时 | 阶段 4 完成：其他地区抓完 |
| 第二天 | 阶段 5 收尾；用户合 `main` |

## 九、不被权限和定时任务打断的运行方式

以前反复中断，原因有三个：
① Fleet 的 `allow_send_to` 没有列出会话，任务派不下去；
② Claude Code 每遇到一个没放行的命令就停下来等人批准；
③ 长任务放在 GPT 的定时任务里跑，定时任务有时长限制，到点就被切断。

对应的解决办法：

| 问题 | 解决 | 由谁做 |
|---|---|---|
| ① Fleet 派不下去 | 在 Dell 的 `~/.config/serveros-fleet-mcp/fleet-node.local.yaml` 里，把 S1–S5 五个会话的 ID **一次性**写进 `allow_send_to`，之后不再改 | 用户在 Dell 本地改一次 |
| ② 命令要人批准 | 仓库自带 `.claude/settings.json`：放行流水线要用的命令（node 采集/转换/发布、测试、git 提交、推送 `fenbi/*` 分支）；禁止推 main、强推、`rm -rf`、读写登录 Profile。会话在仓库目录里启动即生效，不需要 `--dangerously-skip-permissions` | 已在仓库里 |
| ③ 长任务被切断 | **抓取→转换→发布的循环不放在 GPT 里跑**，而是在 Dell 上作为常驻服务运行 `tools/fenbi/run-pipeline.sh`；GPT 的定时任务只做 5 分钟以内的巡检和派单 | S1 在 T2 完成后安装服务 |

常驻服务（S1 安装，Dell 本机，用户级 systemd）：

```ini
# ~/.config/systemd/user/fenbi-pipeline.service
[Unit]
Description=Fenbi capture-ingest-promote loop
[Service]
# 必须是集成工作树（非 main 分支），例如 integ/daily 分支的 git worktree
WorkingDirectory=/home/fjd/workspaces/gwy-zhenti-fenbi/integ
Environment=CONCURRENCY=3 INTERVAL=60 ALLOW_REPLACE=1 PUSH=1
Environment=RIGHTS_FILE=/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi/rights.json
ExecStart=/usr/bin/bash tools/fenbi/run-pipeline.sh
Restart=on-failure
RestartSec=120
[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now fenbi-pipeline
loginctl enable-linger fjd           # 退出登录后继续运行
touch work/fenbi/STOP                # 需要停时：写这个文件；删除后重新 start
```

**已有独立采集服务时（Dell 现状：`fenbi-service.mjs` 只负责采集）**：采集服务保持不动，另装一个**发布服务**，只做"转换 → 发布 → 提交推送 → 看板"，读取采集服务写出的缓存目录：

```ini
# ~/.config/systemd/user/fenbi-publisher.service
[Unit]
Description=Fenbi ingest-promote-push loop (no browser)
[Service]
WorkingDirectory=/home/fjd/workspaces/gwy-zhenti-fenbi/integ
Environment=CAPTURE=0 INTERVAL=300 ALLOW_REPLACE=1 PUSH=1
Environment=PAPERS_DIR=/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi/papers
Environment=RIGHTS_FILE=/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi/rights.json
ExecStart=/usr/bin/bash tools/fenbi/run-pipeline.sh
Restart=on-failure
RestartSec=120
[Install]
WantedBy=default.target
```

发布服务不碰浏览器和登录状态，和采集服务互不干扰。转换是增量的：来源和旧卷都没变的卷直接复用；采集服务事后补回答案、改写 `document.json` 时，下一轮会自动重建这卷候选并重新发布，不需要"静置 N 秒"之类的判断。同一路径出现多个粉笔来源时，只发布答案最多、题目最多的那一份，其余计入 `duplicateSources`。

- 每一轮循环：抓取 → 转换 → `promote-all.mjs` 逐卷发布所有未发布的 A 卷（`ALLOW_REPLACE=1` 时按"粉笔优先"替换旧卷，旧版留在 Git 历史和 `legacy-original.md`）→ 有变更就提交并推送集成分支 → 更新看板。
- 授权文件里加 `"coverAllCapturedSources": true`，表示用户同意收录本账号抓到的全部粉笔卷；不加这一项时，只发布 `sourceIds` 里列出的卷。
- **测速看板**：`work/fenbi/BOARD.md`（`board.json` 同内容）由 `pipeline-board.mjs` 每轮生成，给出**含空等的真实每小时卷数**、连续抓取时每卷秒数、卷间空等次数和分钟数、答案覆盖、A/C、已进分支数、分地区和逐小时统计。GPT 巡检只看这一个文件。
- 抓取遇到验证码、登录失效或限流时，以非 0/2 的退出码结束，脚本会写 `work/fenbi/STOP` 并停下，**不会自动重试**，等用户处理。
- GPT 每次巡检都是**独立的一次**：读看板 → 按第五节行动 → 结束。进度只存在看板和台账里，不依赖 GPT 记住上一次做了什么，所以中途断了也不会丢进度。

## 十、待用户确认

- **发布**：抓取计划第一节第 5 条目前写着"上传 GitHub 必须另有许可"。按这一条，T4 不能提交粉笔内容。用户之前的决定是"仓库私有，粉笔内容和解析一起收录"；需要用户再确认一次后修改第 5 条，T4 才能执行。
