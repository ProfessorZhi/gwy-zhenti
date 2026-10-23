# 粉笔真题落盘总计划

> 唯一依据。GPT 和 Dell 上的 agent 只按本文做，不靠聊天记录。

## 一、目标

把粉笔上合适的**行测和申论**真题抓下来，转成本库的 Markdown（题干、选项、材料、插图、答案、解析），推进 `main`。
衡量进度只看一个数：**`main` 里来自粉笔的卷数**，每张任务卡回报都要带上它。

## 二、规则（已定，不再讨论）

| 事项 | 决定 |
|---|---|
| 范围 | 国考、省考；行测、申论；**全量年份 2008–当年**（不设历史下限，各地区一致） |
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

代码：一律用 main 最新提交。

**历史记录（2026-10-22）**：当时 L1 已完成，main 有 408 份粉笔行测；其中 340 份原先用拼音卷名另存、没有覆盖原卷，已由 `worker/fix-paper-names.mjs` 改正（行测共 494 份，不再重复）。当时申论粉笔卷 0 份 → 下一步 S1。
**当前规模（2026-10-23，见 README）**：库内 1,422 份（行测 533 / 申论 889），粉笔来源 1,213 份（行测 520 / 申论 693）；按上述 grep 口径 `Fenbi-priority structural check` 667 份（行测 104 / 申论 563）。

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
重新生成候选（不设年份下限）：node driver/build-candidates-live.mjs
collector.env：SERVICE_MODE=worker、INTEG_REPO=<INTEG>、RIGHTS_FILE、PUSH=1、AUTO_MERGE=1、
  WORKER_TABS=3、WORKER_DWELL_MS=15000、WORKER_MAX_PAPERS 依次 3 → 10 → 60
停用 fenbi-publisher，重启 fenbi-pipeline。每档跑一轮。
回报：worker.log 里每轮的 publish 行原文；本轮抓了几卷、推进 main 几卷；main 粉笔卷数；有无 STOP / ALERT。
```

### L3 C 卷修复（Claude Code）

L1 回报里的 C 卷按原因修代码（图片解码、选项标号、选项正文等），修完重跑 L1 的命令把它们补推上去。

### S1 已采集申论落盘（现在就做；不开浏览器）

```text
把所有已采集的申论卷（shenlun-capture-panes 的 --out 目录）放到同一个上级目录 <CAPTURES>（每卷一个子目录，含 document.json / meta.json / dom.html）。
用 main 最新代码，在 L1 的集成工作树上运行：
  CAPTURES_DIR=<CAPTURES> INTEG_REPO=<INTEG> RIGHTS_FILE=<rights.json> PUSH=1 AUTO_MERGE=1 node worker/land-shenlun.mjs
回报：最后一行 JSON 原文；main 申论粉笔卷数：
  git -C <INTEG> show origin/main:catalog/manifest.jsonl | grep '"subject":"申论"' | grep -c 'Fenbi-priority structural check'
```

授权只看 RIGHTS_FILE；采集时写死的 `cloudStorageBlocked`、`rightsStatus: unverified` 不再拦落盘。
缺参考答案、缺文字解析的题照常发布并标"来源未提供"；缺题、缺材料、图片下载失败的卷判 C，回执 `cReasons` 列原因。

### S2 申论持续采集 + 落盘

```text
按申论候选清单，逐卷运行 driver/shenlun-capture-panes.mjs（现有参数，--out 写到 <CAPTURES>/<地区>-<年份>-<卷型>-<sourceId>）。
每采 10 卷跑一次 S1 的命令。只停在必须停的情况（验证码、登录失效、一小时 3 次 403/429）。
回报：本轮采集几卷、成功几卷；land-shenlun 最后一行 JSON；main 申论粉笔卷数。
```

### S3 申论 C 卷修复（Claude Code）

S1/S2 回执里 cReasons 的原因交给 Claude Code 修，修完重跑 S1 命令补推。

### 不做

不写"原创学习参考作答"、不让 LLM 生成或改写答案和解析：库里只收粉笔原文，粉笔没有的就标"来源未提供"。

## 六、回报格式

```text
任务：L1 / L2 / …
结果：完成 / 阻塞
数字：（卡上要求的各项）+ main 粉笔卷数
问题：（没有写"无"）
```
