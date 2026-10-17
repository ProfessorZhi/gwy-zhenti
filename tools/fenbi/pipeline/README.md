# 离线分阶段队列（tools/fenbi/pipeline）

这是 `tools/fenbi` 下的**独立子模块**：本地持久化、可恢复、有界的采集/处理队列。它不修改
`src/cli.mjs`、`src/align.mjs`、`src/validate.mjs`，也不导入浏览器或登录 Profile 代码；所有测试都用合成
fixture，不访问粉笔站点、不读取 Cookie、不写任何正式题本。

## 当前状态（请如实理解）

- ✅ 队列、租约、阶段机、handoff、退避、背压、崩溃恢复、死信、**离线 observation importer** 与 CLI
  已实现，并有 58 个合成测试。
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

## 离线 source-observation importer

唯一 browser Owner 观察题库后写出 `gwy-zhenti-source-observation` JSON；本机用
`observe-import` 离线导入，不打开浏览器、不访问站点、不创建练习、不猜 URL。可交接契约见
`schema/observation-handoff.schema.json`，合成示例见 `examples/observation-handoff.example.json`：

```json
{
  "schemaVersion": 1,
  "kind": "gwy-zhenti-source-observation",
  "producer": { "agent": "browser-owner", "at": "2026-10-17T04:00:00Z" },
  "permissions": { "browserProfile": false, "cookies": false, "tokens": false },
  "observations": [{
    "paperSourceId": "9000001",
    "title": "浙江2026行测C类",
    "subject": "xingce", "area": "浙江", "year": 2026, "variant": "C类",
    "route": {
      "kind": "existing_practice",
      "url": "https://www.fenbi.com/spa/tiku/exam/9000001?labelId=1",
      "urlObserved": true, "contentStatus": "observed",
      "evidence": [{ "type": "observed_ui", "ref": "owner observed this practice" }]
    },
    "rights": {
      "category": "observed_ui", "license": null, "redistribution": "local_only",
      "evidence": [{ "type": "observed_ui", "ref": "owner observed this practice" }]
    },
    "images": [{ "ref": "material/q1.png", "sourceUrl": "https://img.fbstatic.cn/q1.png" }]
  }]
}
```

分类结果（都不产生抓取租约，除非 `capture_ready`）：

| classification | 含义 |
| --- | --- |
| `capture_ready` | 在本地允许名单 + `existing_practice` + 已观察且可复现安全 URL + 已观察内容 + 权利信息齐全 |
| `observed_catalog` | 只登记：`not_found`、占位/unknown 内容；不抓取 |
| `needs_route_review` | 允许名单内但 URL 缺失/不可复现/不安全、route 歧义、图片引用无效、rights 不全 |
| `needs_initialization_review` | sourceId 不在本地允许名单，或 owner 明确报告该练习未初始化 |
| `blocked_auth` | owner 观察到 401/验证码；不产生新任务 |
| `invalid` | 信封/条目格式错误；整个 handoff 的凭证泄漏会直接拒绝导入 |

规则：

- **URL 只能来自 Owner handoff**。importer 不会拼 URL、不会因为知道 sourceId 就构造练习地址。
- `contentStatus` 必须是 `observed`；`placeholder` / `unknown` 只登记，不算内容，也不入队。
- `redistribution: allowed` 只有在 evidence 里存在 `redistribution_permission` 时才保留；否则强制
  降为 `local_only` 并写 warning。
- 导入过程自身不领取 collect 租约；`status` 里仍是 pending，只有 collector adapter 才能领。
- 报告写入 `state/observation-imports/<handoffDigest>.json`；catalog 写入
  `state/observed-catalog.json`，只保存 identity/分类/urlDigest，不保存 Cookie 或原始响应。

### 本地允许名单（gitignored，不是生产 config）

`work/fenbi/pipeline/allowlist.json` 只放已初始化、获授权的 sourceId/标题，**禁止放 URL**：

```json
{ "schemaVersion": 1, "sourceIds": [
  { "id": "9000001", "title": "浙江2026行测C类" },
  { "id": "9000002", "title": "江苏2025行测C类" },
  { "id": "9000003", "title": "江苏2024行测A类" },
  { "id": "9000004", "title": "广东2020县级" }
] }
```

该文件已在当前 workspace 的本机 `work/` 下建立（不提交 Git）。浙江 2020A 与其他新卷不得加入；
名单只授予“允许抓取已存在练习”的资格，绝不创建练习。名单缺失 = 全部 `needs_initialization_review`。

## 图片 SHA / PR42 契约

- 图片引用只允许 `fenbi.com` / `fbstatic.cn` / `fb.fenbike.cn` 的 HTTPS 静态 URL，不允许凭证型查询参数。
- 含图片的卷在 `assets_qa` 必须提交一个 `image_manifest` artifact，逐图给出 `ref + sha256`；
  缺 manifest 报 `IMAGE_ASSET_MANIFEST_REQUIRED`，哈希不符报 `IMAGE_HASH_MISMATCH`。
- `candidate_ready` 对含图卷要求 `imagesVerified=true`。这对应 PR42：图片在文本流里只是占位
  token，没有字节证据时不能把两张不同的图当成同一内容。

## PR45 占位词表

`placeholderVerdict` 同时识别 PR36 的短占位与 PR45 的实站长句
（`题目正在全力以赴征集，将会第一时间上传` / `…将会在征集到后第一时间上传`），以及
`正在搜集中`、`本题暂无收集到`、`网友未回忆起`、`题目缺失`、`非客观题，请交卷后查看参考解析估分`。
有界 courtesy tail 不允许句末标点且不超过 24 字，因此真正引用该句并继续展开的题干不会被误杀。

## PR54 路由参数（routecs）与 GET-only

- 配置字段 `routeParams`（默认 `[]`）显式声明参与路由的查询参数，例如 `["routecs"]`。
- 声明后该参数保留；**未声明仍会被丢弃**，随后 `urlMatchesObserved()` 双向比较发现“归一化 URL
  丢失了非追踪参数”，该 URL 判为 `needs_route_review`，不会进入 capture_ready。
- 凭据形状的名字（token/session/auth/cookie…）即使声明也会被 config 拒绝；取值必须 ≤200 且只含
  `A-Za-z0-9_,.:-`；重复参数折叠为第一个。
- 纯追踪参数（`utm_*`、`spm`、`ref`、`from`、`share`、`fbclid`、`gclid`）可以安全丢弃，不算失配。
- 只接受已观察的 **GET landing page**：`/api/...` 以及 `/submit`、`/initialize`、`/init`、`/create`、
  `/start`、`/finish`、`/save` 路径直接判 `needs_route_review`。importer 自身不发起任何网络请求，
  测试会 stub `fetch` 并断言 0 次调用；它没有初始化/交卷/购买/绕登录入口。

## 批量导入（本批最多 5 份）

```bash
node tools/fenbi/pipeline/src/cli.mjs observe-import \
  --config ... --allowlist work/fenbi/pipeline/allowlist.json \
  --handoff-dir /path/to/owner-handoffs --max-files 5 [--dry-run]
```

- 只读取目录下直接的 `*.json`（不递归），默认最多 5 个，硬上限 20。
- **先校验全部选中文件，再入队**：任一文件含凭证或格式错误会整批中止，不会出现前几份已入队、
  后一份才失败的部分状态。
- 跨文件重复的 `paperSourceId+version` 走同一去重主键，只计 `deduplicated`。
- `observe-import` 不领取 lease；只有 collector adapter 能领 `capture_ready`。

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

# 2b) 导入 Owner 的离线 observation handoff（不打开浏览器；只 enqueue 分类为 capture_ready 的项）
node tools/fenbi/pipeline/src/cli.mjs observe-import \
  --config work/fenbi/pipeline/config.json \
  --allowlist work/fenbi/pipeline/allowlist.json \
  --handoff /path/to/owner-observation.json [--dry-run]
node tools/fenbi/pipeline/src/cli.mjs allowlist show \
  --config work/fenbi/pipeline/config.json --allowlist work/fenbi/pipeline/allowlist.json

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

每小时任务应执行一个**有界 pass**，而不是无限循环。可直接调用
`examples/hourly-drain.sh`（单次、无 loop、无自动刷新）：

```bash
GWY_PIPELINE_CONFIG=work/fenbi/pipeline/config.json \
GWY_OBSERVATION_DIR=/abs/path/to/owner-handoffs \
GWY_MAX_HANDOFFS=5 \
GWY_ALLOWLIST=work/fenbi/pipeline/allowlist.json \
  tools/fenbi/pipeline/examples/hourly-drain.sh
```

脚本实际执行的命令等价于：

```bash
node tools/fenbi/pipeline/src/cli.mjs reconcile --config "$CONFIG"
node tools/fenbi/pipeline/src/cli.mjs status    --config "$CONFIG"
# 可选：最多 5 份 Owner handoff 的 bounded import（先校验再入队）
node tools/fenbi/pipeline/src/cli.mjs observe-import --config "$CONFIG" \
  --handoff-dir "$GWY_OBSERVATION_DIR" --max-files 5 --allowlist "$GWY_ALLOWLIST"
# 未注入 adapter 时：exit 2, reason=collector_unwired, claimed=0
node tools/fenbi/pipeline/src/cli.mjs drain --config "$CONFIG" --role collector \
  --budget "$COLLECTOR_BUDGET" --owner "hourly-$(date -u +%Y%m%dT%H%M%SZ)"
# reviewer 只写 review/human_review.json 清单，不自动批准
node tools/fenbi/pipeline/src/cli.mjs drain --config "$CONFIG" --role reviewer --budget 1
node tools/fenbi/pipeline/src/cli.mjs reconcile --config "$CONFIG"
node tools/fenbi/pipeline/src/cli.mjs status    --config "$CONFIG"
```

行为约定：

- `drain` 一次只处理预算内任务，然后返回 `queue_empty` / `drained` / `rate_limited` /
  `blocked_auth` / `backpressure` / `collector_unwired`，不会常驻。
- **没有 adapter 时 collector 一定 exit 2 且 claimed=0**；这不是测试失败，是“尚未接线”的显式信号。
  `examples/hourly-drain.sh` 会保留这个 exit 2（同时打印 `collector_unwired` 与
  “no capture was attempted”），让每小时调度能看到真实状态；不要把它当成 CI 绿灯，也不要宣称
  24h daemon 已部署。
- 离线阶段由外部 Agent 用 `claim`/`put-artifact`/`complete` 领取；也可以注入 worker adapter 后
  `drain --role normalizer ...`。
- `status` 写回调度日志。若 exit 4/`backpressure`，降低下一轮 budget；若 `blocked_auth`，
  先人工检查 Profile，再 `throttle reset`，绝不自动刷新页面。

429/503 的指数退避会持久化到 `state/throttle.json`，下一次每小时任务会继续等待，不会重新猛刷。
401/403/验证码的 `blocked_auth` 不会被时间自动清除，必须人工 reset。

## 实时队列指标

`status` 返回 `status.metrics`，用于每小时日志和本批报告：

| 字段 | 含义 |
| --- | --- |
| `sourcesEnqueued` | 队列内 source 总数（不等于已验证数） |
| `stagesConsumed` | 已成功完成的 stage 数 |
| `verified` / `candidateReady` | 独立验真 / 仅候选 |
| `blocked` | `blocked_auth` + `blocked_rights` |
| `skippedPlaceholder` / `deadLetter` / `needsReview` / `partial` | 对应状态数 |
| `queueDepth` | 仍有待办/在途的 job 数 |
| `pendingReview` | 待人工审核数 |
| `leasesActive` | 活跃租约文件数 |
| `artifacts` | artifact 数与总字节 |

另有：

- `collector.adapterWired` / `collector.lastReason`：来自 `state/collector-status.json`，由 bounded
  collector drain 写入；没有 adapter 时为 `false`、`collector_unwired`。
- `observedCatalog.entries` / `byClassification`：来自 `state/observed-catalog.json`，用于区分
  capture_ready 与只登记/待路线复核/待初始化复核的观察。
- `host` / `backpressure` / `capacity`：节点繁忙时 collector 页数降为 1、offline workers 降为 ≤4。

这些指标只读本地文件，不访问粉笔站点。

## 测试

```bash
cd tools/fenbi/pipeline
npm test          # 等价于 node --test test/*.test.mjs
```

58 个测试全部使用合成 fixture：重复派发不重复、两 worker 不共享同一 stage、崩溃/租约代际恢复、
429/503 退避与 401 阻断、权限/不可再分发元数据、handoff 凭证负例、占位与 AI 答案不能完成、
**1 producer + 2 独立 consumers + reviewer/verifier 全链路**、**图片 manifest SHA 正负例**、
**未授权源不产生租约**、**无再分发许可强制 local_only**、**占位/unknown 不算内容**、
**PR54 routecs 声明/未声明/重复/超长**、**GET-only 拒绝 API/初始化/交卷路径**、
**batch import 先校验后入队与 max-files**、**offline importer 的 fetch 调用为 0**、
**status.metrics / collector_unwired 指标**、背压、
PR28/PR31/PR36/PR42/PR45 契约相容性、CLI 真实退出码。测试不会打开浏览器、不会访问站点、
不会读取 `work/fenbi/profiles/`。

## 明确的缺口（下一轮需要的人工/授权输入）

- 真实 browser-owner adapter 尚未接入本模块；当前每小时 collector drain 若未提供 adapter 会
  以 `collector_unwired` 干净退出，claimed=0。
- 本机 gitignored 允许名单已加入四卷 sourceId（9000001 / 9000002 / 9000003 / 9000004），
  但**真实 URL 仍必须由唯一 browser Owner 的 observation handoff 提供**；本模块不猜 URL。
- 浙江 2020A 与其他新卷仍缺**首次初始化授权**；任何新来源还需要来源类别、许可、可再分发证据。
- 正式卷的版权/再分发证据仍以 `local_only` 为默认；没有 `redistribution_permission` 证据时
  即使 handoff 请求 `allowed` 也会被强制降级。
- 图片 manifest 的 SHA 来自离线 consumer 的核验；本模块不下载图片，也不接触实站。
