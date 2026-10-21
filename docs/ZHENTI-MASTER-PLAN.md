# 粉笔真题落盘总计划

> 唯一依据。GPT 和 Dell 上的 agent 只按本文做，不靠聊天记录。

## 一、目标

把粉笔上合适的**行测和申论**真题抓下来，转成本库的 Markdown（题干、选项、材料、插图、答案、解析），推进 `main`。
衡量进度只看一个数：**`main` 里来自粉笔的卷数**，每张任务卡回报都要带上它。

## 二、规则（已定，不再讨论）

| 事项 | 决定 |
|---|---|
| 范围 | 国考、省考；行测、申论；默认 2016–当年，**浙江取粉笔上全部年份** |
| 目录 | 就用本库现有目录，不另开目录 |
| 和本库冲突 | **一律以粉笔为准，直接覆盖**同一卷；答案、解析也用粉笔的，不另注明 |
| 粉笔缺的题 | 本库有就用本库补；都没有就保留题位、标"粉笔暂未收录本题"，照常发布 |
| 只有本库有的卷 | 保持不动 |
| 合入 main | 闸门只查题数不倒退、图片齐全、格式正确；通过即自动推 `main`（`AUTO_MERGE=1`） |
| 交白卷 | 允许；每卷最多开 1 次练习、交 1 次白卷，交卷前停 15 秒 |
| 账号 | 风险用户接受；可以用多个账号 |
| 必须停 | 验证码、登录失效、一小时内 3 次 403/429 → 写 STOP，等用户 |
| 不做 | 绕验证码或限流；购买；把 Profile、Cookie 放进 git |

## 三、流程（只有三步）

```text
抓：目录 → 逐卷开练习、交白卷 → 原始数据存 work/fenbi/papers/
转：原始数据 → Markdown + 图片（A 卷可发布，C 卷有缺陷待修）
推：A 卷覆盖写进本库目录 → 闸门 → 推 main
```

- 已抓到但没推的卷：`worker/land-cached.mjs` 一条命令完成"转 + 推"，不开浏览器。
- 新卷：`worker/worker.mjs`（`SERVICE_MODE=worker`）一卷一卷走完三步。

## 四、分工

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| 用户 | 批准下一张卡、登录账号、处理 STOP | — |
| Claude Code | 改代码、修卡住的地方、维护本文 | 不碰 Dell |
| GPT | 把任务卡原样派给 Dell agent，把回报原样转给用户 | 不加检查、不加前提、不改卡 |
| Dell agent | 照卡执行命令，按格式回报 | 不扩大范围、不写新工具、不开审计分支 |

纪律：
1. 回报没有数字 = 没完成。
2. 命令报错就停，贴原样输出，交给 Claude Code 修。
3. 只允许 agent 改挡住当前命令的小缺陷（≤20 行、附测试）。
4. 新的担忧写进回报"问题"一栏，不自行拦截落盘。

## 五、任务卡（按顺序，上一张回报后用户批准再发下一张）

代码分支：`claude/bold-brahmagupta-lkou1e`（合并进 main 后改用 main）。

### L1 首批行测落盘（现在就做；不开浏览器，不停服务）

```text
1. 在 Dell 上 checkout 代码分支到一个独立目录，tools/fenbi 下 npm ci。
2. 从 origin/main 新建集成工作树，分支 fenbi-integ：
     git -C <main checkout> worktree add <INTEG> -B fenbi-integ origin/main
3. 运行（RIGHTS_FILE 沿用 T1 用过的那份）：
     FENBI_WORK_DIR=<生产 work/fenbi> INTEG_REPO=<INTEG> RIGHTS_FILE=<rights.json> PUSH=1 AUTO_MERGE=1 \
       node worker/land-cached.mjs
回报：最后一行 JSON 原文；main 里来自粉笔的卷数：git -C <INTEG> fetch -q origin main && git -C <INTEG> show origin/main:catalog/manifest.jsonl | grep -c 'Fenbi-priority structural check'。
gate.ok=false 时不要改任何东西，原样贴 reasons，交给 Claude Code。
```

### L2 生产切到 worker，持续抓新卷并自动推 main

```text
重新生成候选（浙江不设年份下限）：node driver/build-candidates-live.mjs
collector.env：SERVICE_MODE=worker、INTEG_REPO=<INTEG>、RIGHTS_FILE、PUSH=1、AUTO_MERGE=1、
  WORKER_TABS=3、WORKER_DWELL_MS=15000、WORKER_MAX_PAPERS 依次 3 → 10 → 60
停用 fenbi-publisher，重启 fenbi-pipeline。每档跑一轮。
回报：worker.log 里每轮的 publish 行原文；本轮抓了几卷、推进 main 几卷；main 粉笔卷数；有无 STOP / ALERT。
```

### L3 C 卷修复（Claude Code）

L1 回报里的 C 卷按原因修代码（图片解码、选项标号、选项正文等），修完重跑 L1 的命令把它们补推上去。

### S1 申论样本（为写代码准备）

```text
用现有账号打开 1 份已做过的申论题目页和解析页，不交卷、不开新练习。
保存去掉账号信息的页面 HTML（题目、材料、解析区）和解析页加载的题目/答案 JSON 到 work/fenbi/shenlun-sample/。
同时只读巡检一次申论目录，保存目录快照。
回报：文件路径和大小；答案、解析在页面里的位置；申论目录卷数。
```

### S2 申论支持（Claude Code）→ S3 申论试跑

按 S1 样本写申论的抓取、转换、渲染；试跑按 L2 的 3 → 10 → 60。

## 六、回报格式

```text
任务：L1 / L2 / …
结果：完成 / 阻塞
数字：（卡上要求的各项）+ main 粉笔卷数
问题：（没有写"无"）
```
