# 给 GPT 的指令（按需查询）

生产线是两个常驻服务，自己一直跑，不需要 GPT 定时驱动或派任务：
- `fenbi-pipeline`：采集，唯一使用浏览器和登录状态的进程
- `fenbi-publisher`：转换、发布到集成分支

设计见 `docs/WORKFLOW-THINKING.md`。原来的"启动指令""定时巡检""任务卡派发"都已废止。

**总计划和任务卡见 `docs/ZHENTI-MASTER-PLAN.md`**：用户批准某张任务卡后，GPT 把它原样派给本地 agent，收回报格式里的数字，原样转给用户。

## 用户问进度时使用

```text
用户在问 gwy-zhenti 的进度。默认只读，不派新任务、不改代码、不开 PR：
1. 读 Dell 上的 work/fenbi/BOARD.md、两个服务的状态
   （systemctl --user status fenbi-pipeline fenbi-publisher），以及 service.log、pipeline.log 最后 50 行。
2. 回答不超过 8 行：粉笔目录卷数、已进入 main 的卷数、今天新增卷数、C 卷数、
   最近 1 小时抓取卷数、两个服务是否在跑。
3. 存在 work/fenbi/STOP：说明停止原因，请用户处理。不要自己删除 STOP，也不要重启。
4. 存在 work/fenbi/ALERT：同一类故障已经连续退避多次，告诉用户原因和次数。
4b. 存在 work/fenbi/ALERT-merge-gate：自动合入 main 的闸门没过（集成分支照常推送，main 没动），把文件里的 reasons 原样告诉用户。单卷流水线的逐卷日志在 work/fenbi/worker.log。
5. 服务没在跑、也没有 STOP：告诉用户，经用户同意后再重启。
6. 需要改代码时，先向用户说明问题，由用户决定。
```
