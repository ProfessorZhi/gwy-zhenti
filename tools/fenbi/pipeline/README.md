# 离线分阶段队列（tools/fenbi/pipeline）

这是 `tools/fenbi` 下的**独立子模块**：本地持久化、可恢复、有界的采集/处理队列。它不修改
`src/cli.mjs`、`src/align.mjs`、`src/validate.mjs`，也不导入浏览器或登录 Profile 代码；所有测试都用合成
fixture，不访问粉笔站点、不读取 Cookie、不写任何正式题本。

## 当前状态（请如实理解）

- ✅ 队列、租约、阶段机、handoff、退避、背压、崩溃恢复、死信与 CLI 已实现，并有 39 个合成测试。
- ❌ **没有部署 24 小时常驻 collector，也没有启动 daemon/systemd。** 本模块只提供单次有界
  `drain` / `reconcile`，适合由现有每小时调度任务调用。
- ❌ **没有内置真实粉笔浏览器 adapter。** 不注入 adapter 时，`drain --role collector` 会以
  `collector_unwired`（exit 2）退出，并且**不领取任何 capture 租约**。这是故意的：队列代码不能伪装成
  已经完成真实采集。
- 真实采集仍由持有唯一 Fenbi profile 的浏览器 owner 执行；PR28 的 `schedule.mjs` 负责单 profile 内
  最多 3 个 Page。本模块用 `MAX_CONCURRENCY = 3` 与相同的 `clampConcurrency` 语义和它相容。
- `verified` 只由独立 verifier 的 receipt 产生；`candidate_ready` 不算完成，AI 答案、占位存根、
  `needs_review` 都不算完成。

## 安全与来源边界

1. 只接受**显式 `enqueue`**：调用方必须给出已观察的 `paperSourceId`、`version`、标题、科目、地区、
   年份和已观察/已授权 URL。没有目录爬虫、没有 API 推测、没有从 ID 合成练习 URL。
2. 生产配置的 `authorizedSourceIds` **默认空 = 关闭 capture**。必须把已获得首次初始化授权的
   paper source ID 显式列进去；当前只应列入**已真实初始化的四卷**（浙江 2026C 及另外三卷）。
   浙江 2020A 和其他新卷尚未获首次初始化授权，不得加入，也不得通过本工具创建。
   本模块没有任何“初始化练习”的命令。
3. `licensed_donor` 只能走 `enqueue-offline`，永远不会进入 `capture_ready`；再分发放行需要显式
   license，默认 `local_only`。
4. URL 必须 HTTPS、无账号密码、无 `token/session/cookie/auth/signature` 等查询参数；只保留白名单
   页面参数。图片引用同样只允许 `fenbi.com` / `fbstatic.cn` / `fb.fenbike.cn` 的静态 URL。
5. 自动作答、交卷、购买、绕登录、验证码绕过都没有入口；遇到 401/403/验证码会停止开新任务。
6. 队列数据默认在 `work/fenbi/pipeline/`，根 `.gitignore` 已忽略 `work/`；目录 0700、文件 0600。
   第三方原题、图片和账号资料不进入 Git。

## 阶段与角色

```
capture_ready -> normalized -> aligned -> assets_qa -> answer_explanation_qa
              -> human_review -> candidate_ready -> (verifier receipt) verified
```

| stage | role | 说明 |
| --- | --- | --- |
| `capture_ready` | `collector` | 唯一允许浏览器 Profile 的阶段；注入 adapter 才领取 |
| `normalized` | `normalizer` | 离线规范化，无浏览器 |
| `aligned` | `matcher` | 与原卷对齐 |
| `assets_qa` | `assets_qa` | 图片/公式/素材核验 |
| `answer_explanation_qa` | `answer_qa` | 答案/解析核验；`ai_assisted`/`unknown` 不能完成 |
| `human_review` | `reviewer` | 必须 `approved=true` + reviewer 姓名 |
| `candidate_ready` | `verifier` | 必须 `citationsVerified=true`；仍不算完成 |
| — | `verifier` receipt | 写入 `verifiedAt` 后，`status.completed` 才 +1 |

阶段结果：`pending`、`leased`、`done`、`partial`（可重试，带退避）、`skipped_placeholder`、
`blocked_auth`、`blocked_rights`、`needs_review`、`dead_letter`。后四种与 `skipped_placeholder`
都是终态，只有带书面理由的 `reopen` 能重新入队。

## 持久化、去重与恢复

- 每个 job 一个 JSON：`jobs/<jobId>.json`，写入采用 same-dir temp + fsync + rename。
- job 主键：`sha256(paperSourceId + version)`；**任务去重主键**：
  `sha256(paperSourceId + version + processingStage)`，每个 job 的 `taskKeys` 都保存。
- 重复 `enqueue` 同身份/同版本 → 返回同一 job（`duplicate:true`），不会重复建练习；
  同主键但标题/URL/权限不同 → `DUPLICATE_CONFLICT`，需人工处理，绝不覆盖。
- 阶段租约：`leases/<jobId>.<stage>.json`，`open(..., "wx", 0600)` 原子创建；过期租约通过
  **原子 rename** 移到 `leases/stale/`（保留审计）并递增 generation。旧 owner 的
  token/generation 无法再提交。
- 每个 job 的读改写还有短锁 `jobs/.<jobId>.lock`，避免两个完成操作丢更新。
- `reconcile` 只修复已有 job：回收过期/缺失租约 → `pending` + 退避；超过 `maxAttempts` → `dead_letter`
  并复制到 `dead-letter/`。它**从不创建新 job**。
- artifacts：`artifacts/<jobId>/<stage>/`，逐文件 SHA-256、字节数、每卷配额；不允许 symlink、
  绝对路径或 `..` 逃逸。

## 最小 handoff

`build-handoff` 只输出离线分片：job 身份、stage、来源类别/许可/再分发、artifact 相对路径与
SHA-256、逐图 `ref/sourceUrl`、`review.required` 和 producer。它明确写入
`permissions.browserProfile/cookies/tokens = false`，不含 Profile 路径、Cookie、Token、请求头。
`verify-handoff` 会拒绝凭证型字段/值、绝对路径、`..`、哈希不符、AI/unknown 答案未标人审。
别的 Agent 不需要、也不应该接触账号 Profile。

## 常用命令

```bash
# 0) 配置：先复制示例，然后把四卷已授权的 source ID 填进 authorizedSourceIds
cp tools/fenbi/pipeline/config.example.json work/fenbi/pipeline/config.json

# 1) 初始化目录（0700）
node tools/fenbi/pipeline/src/cli.mjs init --config work/fenbi/pipeline/config.json

# 2) 显式登记一个已观察、已授权的卷/版本（不会抓页面）
node tools/fenbi/pipeline/src/cli.mjs enqueue \
  --config work/fenbi/pipeline/config.json \
  --source-id 123456 --version 2026C-v1 --title '浙江2026行测C类' \
  --subject xingce --area 浙江 --year 2026 --variant C类 \
  --url 'https://www.fenbi.com/spa/tiku/exam/123456?labelId=1' --observed \
  --source-category observed_ui --evidence observed_ui:'operator saw it in the live catalog' \
  --image material/q1.png:https://img.fbstatic.cn/example.png \
  --questions 100 --actor operator

# 3) 单次有界 drain。没有 adapter 时 collector 以 exit 2 退出且不领取租约。
node tools/fenbi/pipeline/src/cli.mjs drain --config ... --role collector \
  --budget 2 --owner collector-hourly --adapter-module /path/to/owner-adapter.mjs

# 4) 离线 Agent 领取一个阶段（独立租约；打印 token/generation 供本次处理使用）
node tools/fenbi/pipeline/src/cli.mjs claim --config ... --role normalizer \
  --stage normalized --owner normalizer-1 [--job JOB_ID]

# 5) 把处理结果放进本阶段目录并提交（哈希自动计算）
node tools/fenbi/pipeline/src/cli.mjs put-artifact --config ... --job ID --stage normalized \
  --owner normalizer-1 --token TOKEN --generation N --file /tmp/out.json --name out.json
node tools/fenbi/pipeline/src/cli.mjs complete --config ... --job ID --stage normalized \
  --owner normalizer-1 --token TOKEN --generation N --artifact out.json

# 6) 失败/占位/阻断；partial 会退避，达到上限进 dead-letter
node tools/fenbi/pipeline/src/cli.mjs fail --config ... --job ID --stage capture_ready \
  --owner collector-hourly --token TOKEN --generation N \
  --outcome skipped_placeholder --reason '粉笔显示未征集'

# 7) 崩溃恢复、状态、节流
node tools/fenbi/pipeline/src/cli.mjs reconcile --config ...
node tools/fenbi/pipeline/src/cli.mjs status --config ...
node tools/fenbi/pipeline/src/cli.mjs throttle show --config ...
node tools/fenbi/pipeline/src/cli.mjs throttle reset --config ... --host www.fenbi.com
```

退出码：`0` 正常/队列空；`2` 阻断（`blocked_auth`、未接 adapter、collector 已占用）；
`3` 429/503 退避；`4` 背压；`5` 输入/状态错误。

## 如何让现有每小时调度消费队列

每小时任务应执行一个**有界 pass**，而不是无限循环：

1. `reconcile`（回收崩溃租约）。
2. `drain --role collector --budget <N>`：有 adapter 才真正采集；返回 `queue_empty`/`drained`/
   `rate_limited`/`blocked_auth`/`backpressure` 后立即退出。
3. 对 `normalizer`、`matcher`、`assets_qa`、`answer_qa` 分别
   `drain --role ... --budget <M> --adapter-module ...`；外部 CC Agent 也可以直接用
   `claim`/`put-artifact`/`complete` 领离线分片。
4. `drain --role reviewer` / `--role verifier`：只生成 `review/<stage>.json` 清单，**不自动批准**。
5. `status` 写回调度日志。若 `reason=backpressure` 或 exit 4，降低下一轮 budget；若
   `blocked_auth`，先人工检查 Profile，再 `throttle reset`。

429/503 的指数退避会持久化到 `state/throttle.json`，下一次每小时任务会继续等待，不会重新猛刷。
401/403/验证码的 `blocked_auth` 不会被时间自动清除，必须人工 reset。

## 测试

```bash
cd tools/fenbi/pipeline
npm test          # 等价于 node --test test/*.test.mjs
```

39 个测试全部使用合成 fixture：重复派发不重复、两 worker 不共享同一 stage、崩溃/租约代际恢复、
429/503 退避与 401 阻断、权限/不可再分发元数据、handoff 凭证负例、占位与 AI 答案不能完成、
背压、PR28/PR31/PR36 契约相容性、CLI 真实退出码。测试不会打开浏览器、不会访问站点、不会读取
`work/fenbi/profiles/`。

## 明确的缺口（下一轮需要的人工/授权输入）

- 真实 browser-owner adapter 尚未接入本模块；当前每小时 collector drain 若未提供 adapter 会
  以 `collector_unwired` 干净退出。
- 四卷已初始化试卷的真实 `paperSourceId` 尚未写入生产 config；在填入前 capture 保持关闭。
- 浙江 2020A 与其他新卷仍缺**首次初始化授权**；任何新来源还需要来源类别、许可、可再分发证据。
- 正式卷的版权/再分发证据仍以 `local_only` 为默认；没有证据不得标 `redistribution: allowed`。
