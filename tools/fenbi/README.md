# 粉笔本地 Playwright 采集框架

面向 `gwy-zhenti` 的缺卷、缺题和解析核对。使用本机 Chrome/Edge 的专用持久配置，人工短信登录一次后复用；日常采集由固定脚本执行，**不调用 LLM、TinyFish Agent 或云浏览器**。

已完成一份行测的实站题面对齐小样及离线验证，不是“已取得粉笔全部试卷”。其他卷型、申论、解析权限和完整性仍需逐卷验收。`xingcezhenti` 只是补充源，不能替代粉笔核对。

## 安装与启动

需要 Node.js 22+、已安装的 Chrome 或 Edge。依赖只有 `playwright-core`、HTML解析与Markdown转换器，不下载浏览器，不安装 OpenCLI，不修改其他工具配置。

在本目录打开 PowerShell：

```powershell
npm.cmd ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmmirror.com
node src/cli.mjs init
node src/cli.mjs doctor
node src/cli.mjs login
```

`init` 创建 `../../work/fenbi/config.json`；已有配置绝不覆盖。`doctor` 只检查本机浏览器能否启动，不访问粉笔账号。

`login` 打开专用窗口。**在网页里自行完成手机号、验证码登录，进入题库目录后回到终端按 Enter。不要把验证码、密码或 Cookie 发给协作 Agent。** 工具只观察认证请求的 HTTP 状态，不保存用户资料响应。无法观察到认证成功时报告 unknown，不以按钮是否可见冒充成功。保存登录状态并不能保证永不失效。

默认配置使用 Chrome；若要用 Edge，修改本地配置的 `channel` 为 `msedge`。可设置 `executablePath` 指向已安装浏览器；不会下载安装程序。`chromium` 仅适用于自行提供的可用浏览器或已存在缓存。

## 运行目录与协作边界

```text
tools/fenbi/                  框架、依赖锁、测试、说明（可提交）
work/fenbi/                   本地专用，仓库已有 work/ 忽略规则
  config.json                 本机配置与经核实的字段映射
  profiles/fenbi-main/        登录状态和浏览器数据，禁止提交
  catalog.json                实际观察到的目录，不代表全站清单
  observed-reads-*.json       该配置实际观察到的只读数据URL
  inspect.json               字段结构与明确选中的题目容器
  plan*.json                 缺口候选、身份与待核状态
  papers/<任务键>/            逐次采集版本、图片、检查点和验收
  candidates/<任务键>-<时间>/ 候选Markdown，禁止直接当正式卷
```

同一浏览器配置和同一采集工作区分别加独占锁。多个 Agent 并行处理已取得的数据，浏览器采集由一个进程集中执行。异常退出留下的锁需要先检查对应进程再人工处理；工具不会自动删除别人的锁，也不会重置配置。Windows 的 `work/` 还应只对当前用户可读；POSIX 文件模式不替代 Windows ACL。

## 先观察目录和实际字段

```powershell
node src/cli.mjs catalog
node src/cli.mjs inspect --url "https://www.fenbi.com/spa/tiku"
node src/cli.mjs plan
```

浏览器会话中人工打开所需分类或现有试卷，回终端按 Enter 保存。本机入口固定从正常 `/spa/tiku` 进入，避免旧深链接未执行认证初始化。

- 仅观察页面**实际发生**的行测/申论只读 JSON 响应；不枚举未知接口，不扫描目录ID。
- `inspect.json` 记录字段路径和类型，默认不保存整页、不保存原始响应、请求头、HAR或账户资料。
- 若要保留题目DOM，在本地配置填写准确的 `contentSelector`，例如经实际检查确认的题目根容器。默认 `null`，不能用 `body/html/*` 代替题目容器。
- 已实站观察新版 `papers/v2` 的 `list/pageInfo` 及 `subLabels/childrenLabels/labelMeta`，保留分页与来源声明覆盖信息。`exerciseCount` 不当作题数；目录项不当作正文。
- `plan` 对照 `catalog/manifest.jsonl`；未知身份、未知卷型、未观察到页面URL均保留待核。广州和广东省考分开匹配。新计划单独落盘，已有人工计划不覆盖。
- 分类切换若需要写请求，采集模式会阻止；应先核对真实请求及其作用后扩展明确规则，不能假装已遍历全部地区。

## 明确一份采集目标

从真实目录和页面核实源ID、标题、年份、地区、卷型、题数，以及实际题本URL，再用 `add` 加入本地计划：

```powershell
node src/cli.mjs add --id SOURCE_ID --title "原始试卷标题" --subject xingce --area 江苏 --year 2025 --variant C类 --url "OBSERVED_PAPER_URL" --questions 130 --materials 6
```

上面是**参数示例，不是已核实题本**。请替换为真实源值；`--questions` 和 `--materials` 必须来自题本核对，不能照抄示例数字。未知时不填，验收保持 partial。实际任务键由命令输出，可避免不同科目源ID重复。

`plan.json` 中的 `expected.questionNumbers`、`expected.materialIds` 可以填写明确核实的集合；默认不由已采集数量反推预期数量。

## 字段映射与直接读取

默认支持明示 `questions/data.questions/exercise.questions`、`materials/accessories`、`answers` 等结构。**这些JSON候选映射尚不能代替当前粉笔实站响应核对。** 新字段通过本机 `fieldMap` 配置，示意：

```json
{
  "questions": "data.questions",
  "contentHtml": "content",
  "explanationHtml": "solution",
  "answerHtml": "correctAnswer",
  "answerEncoding": "zero-based-index",
  "optionLabels": ["A", "B", "C", "D"],
  "questionNumbersById": {"OBSERVED_QUESTION_ID": 1}
}
```

只有核实索引编码后才能设置 `answerEncoding`；只有核实原题选项标签后才设置 `optionLabels`。源ID或数组序号不会默认成为原题号。题号映射与源号冲突时保留冲突并阻止完整验收。示意值不能直接用于生产。

若同一数据请求需要复用，可以在该任务的 `readUrls` 数组填写 `observed-reads-<profileName>.json` 中**本配置已经观察到的完整只读URL**。框架使用当前浏览器 context 的 Cookie 发起 GET，并核对登记记录、域名、参数、状态、JSON类型和体积；不传递账号密码，不创建新练习，不拼接猜测的接口或ID，不跟随重定向。这样可减少逐题点击。

有些响应可能只有题目ID或需要额外打开解析页。未知字段、缺正文、无卷归属证据均保持 partial，不能补成假数据。响应没有 paperId 时，必须有原卷声明的完整题目ID集合或经独立核对的人工关联证据。

## 采集、续跑和导出

```powershell
node src/cli.mjs capture --job TASK_KEY --manual
node src/cli.mjs capture --all
node src/cli.mjs validate --job TASK_KEY
node src/cli.mjs export --job TASK_KEY
```

- `--manual` 允许先人工打开完整题本/解析，再按 Enter 采集。
- 自动翻页只有在核实 `nextQuestionSelector` 后启用；核实只读“查看解析”按钮后才能填 `explanationSelector`，绝不填交卷/开始练习/购买按钮。所有非GET/HEAD/OPTIONS写请求默认阻止；登录模式仅额外允许粉笔认证域的登录请求。
- 只点击唯一、可见、可用的控件；重复内容、翻页上限、认证失败、验证码、非JSON和超大响应均记录，不默默截断。
- 每次采集保存独立文档版本；**完整**检查点才可跳过，跳过前重新验证任务/配置指纹、文档哈希及图片。partial任务重试保留旧版本，目前不跨次混合正文，避免不同源版本拼卷。
- 图片限真实引用、允许的粉笔静态域、单图12MiB/总128MiB/最多256张；下载后浏览器解码，记录尺寸与SHA256，不转码和有损压缩。超出限额保持partial，需核对后显式扩展。
- 答案与解析分开保存，异步先到的答案按源题ID关联；缺关联不算完成。
- `export` 仅接受重新验收通过的采集，导出到新的候选目录。保留材料、题目、选项、表格、公式和本地图片，参考答案集中折叠。不会写入 `国考/`、`省考/`、正式 `图片/` 或修改缺口数字。

正式入库还需人工核对身份、题序、原文完整性、来源使用许可和参考答案性质，再走仓库已有导入与验收流程。机器 `complete` 只表示本框架定义的结构检查通过，不表示官方原卷认证、评分正确或全站覆盖。

## 验收口径

分别报告 identity/questions/materials/answers/explanations/images。预期数量未知、题号缺失或重复、材料关联断裂、来源题目ID不匹配、正文为空、只有链接/提纲/占位符、选项与答案不匹配、图片未落盘或哈希不符均不能完整。

申论单独检查作答要求和可识别的字数上下限；复杂分小问要求保守待核。“左右”的±20%只是工具复核口径，不是官方评分规则。图片浏览器解码证据绑定实际字节；正式库仍使用已有逐帧像素检查。敏感URL引用删除后标待核，不把删失内容算完整。

## 已验证的行测DOM路线与逐题对齐

[浙江2026行测C实站试跑](../../reports/FENBI-LIVE-TRIAL-20261016.md)已实际取得110题、4组材料和6段题型说明。该页面题面并未通过原JSON监听器取得，因此新增 `fenbi-xingce-v1` DOM适配器。它读取 `.tis-container` 内全部 `app-ti[data-question-key]`，不能只抓 `.questions-single-container`：本次后者仅93题，会漏组合题。

行测专用本地配置可设置 `contentSelector: ".tis-container"`、`domAdapter: "fenbi-xingce-v1"`，再使用 `capture --manual`。先从目录进入已存在的练习，回终端确认采集；本轮直接重开旧题本深链接未取得题面，不因此判登录失效。首次打开新卷可能需要练习初始化，默认只读保护不会自动放行；本次小样仅执行过一次明确限定到该卷的初始化，之后均复用原练习，未作答/交卷。

DOM模式只提取当前已验证的行测题面、选项、材料、原号、复合题目key和题型说明；不从选中状态或CSS猜答案，不冒充已验证申论DOM或解析。答案未取得时整卷仍为partial。新增观察到的静态域仅放行 `fb.fenbike.cn` 的两类图片/公式路径，未放开该域其他路径或导航。

已有本地DOM快照也可离线规范化和对齐，不重新登录或启动浏览器：

```powershell
node src/cli.mjs normalize-dom --document work/fenbi/inspect.json --id SOURCE_ID --title "源试卷标题" --subject xingce --year 2026 --area 浙江 --variant C类 --url "OBSERVED_EXAM_URL"
node src/cli.mjs align --document work/fenbi/NORMALIZED_FILE.json --paper "省考/浙江/2026/行测-C类.md" --asset-root work/fenbi/ASSET_DIRECTORY
```

输入快照需有 `html` 或 `contentHtml`，身份及来源取自实际目录/页面；示例占位符必须替换。路径参数相对于仓库根，规范化文档和图片目录必须位于 `work/fenbi/`。报告只写本地候选区，不改正式卷。

粉笔DOM复合key与库内数字qid不是同一命名空间，因此不把ID格式不同判作错题；改用明确原号、完整题干和选项唯一对齐。相对图片地址按真实来源页面解析，核对实际图片字节。未采到的答案解析标记unknown；数学条件、数字、图片位置不做宽松删除。公式图和文字等价需单独留证，不能在严格统计里静默算作完全相同。

退出码：`0`命令成功；`2`采集/认证/验收不完整；`1`配置、依赖或运行错误。错误不打印原始账号响应和带凭据URL。

## 题号映射候选报告（乱序/残卷/不同回忆版本）

`src/mapping.mjs` 为**严格对齐器**无法裁决的情况提供一份**候选**一对一映射供人工复核：
来源题号与库内题号不对应、只采到部分题目、或同一场考试的不同回忆版本措辞略有差异。

它**只出候选，绝不算验证**：`comparePaper` 仍是唯一能报 `matched`/`verified` 的地方，本报告的
`advisoryOnly` 恒为 `true`，`limitation` 固定写明"不是已验证匹配"。

```js
import { buildMappingReport, validateMappingReport } from './src/mapping.mjs';
const report = buildMappingReport({
  source: { label: '…', questions: [...] },
  repository: { label: '…', questions: [...] },
  sourceRights: 'cleared',                    // 必填，由操作者自行判定
  isEligible: (q) => !isCollectionStub(plainText(q.contentHtml)),   // 必填：调用方自己的闸门
});
if (!validateMappingReport(report).ok) throw new Error('report contract violated');
```

规则（全部可离线复现）：

- **题号本身从不参与评分**，只作为观察值报在 `sameNumber`。乱序试卷靠题干/选项/材料/图片身份对齐。
- **图片证据只认内容哈希，不认引用路径**。题对象通过
  `imageBytes: [{ sha256: "<64位十六进制>", verified: true }]` 声明同源可复验的图像内容 SHA-256；
  路径相同不代表字节相同，字节相同也不必路径相同。缺 manifest、哈希格式不对、或
  `verified !== true`（来源未授权）时，图片信号是 **neutral**（`available: false` + `reason`），
  **不按 0 分扣权**，也不会因此把本来完全一致的文本题降级。
- **`⟦IMAGE⟧` 占位符不是文本证据**：题干去掉图片占位符后若无文字，stem 信号即 unavailable；
  纯图题只有**字节相同且已复验**才可能判 `exact`，绝不靠占位符相等。
- **只有 `grade: "exact"` 才可自动接受**（题干与选项都完全相等）；其余一律
  `autoAcceptable: false`、`requiresHumanReview: true`。
- **低于 `candidateFloor` 不映射**，在 `unmatchedSource[].bestScore` 里留下最接近的分数。
- **两个候选落在 `ambiguityMargin` 内 → 进 `ambiguous`，不做选择**；两道来源题抢同一道库内题时
  第二道记 `repository-row-already-claimed`。
- **选项标签集合或顺序不同 → 该对不可映射**（不是低分），因为两边不是同一题形。
- **`isEligible` 必填**：占位存根、受限来源、未观察题位由调用方剔除，落进 `source.rejected`，
  **永不进入候选池**；完全没有可比内容的行记 `no-comparable-content`。
- **权限否决**：`sourceRights` 不是 `cleared` 时 `blocked = "source-rights-not-cleared"`，
  `assignments` 为空，只保留结构统计。
- 题号重复在两侧各自记 `duplicateNumbers` 与 `conflicts`。

报告结构由 `MAPPING_REPORT_SCHEMA` 声明、`validateMappingReport()` 校验（`advisoryOnly` 必须为
`true`；非 `exact` 的配对不得 `autoAcceptable`）。下游可据此审计，也可直接比对两次运行的 JSON
——同一输入产生完全相同的报告。

## 测试

```powershell
node --test test/model.test.mjs test/browser.test.mjs test/pipeline.test.mjs test/dom.test.mjs test/align.test.mjs
node --test test/browser-smoke.test.mjs
```

第二条使用本机已安装Chrome，真实运行浏览器但**所有页面/API/图片均为离线合成数据**，不访问真实账号。包含图片解码→完整性检查→Markdown导出及专用配置重启持久化测试。可用环境变量 `FENBI_TEST_BROWSER_CHANNEL=msedge` 改用Edge。没有浏览器时此测试明确失败，不当作通过。

CI只运行不依赖浏览器安装的离线单元测试；不使用粉笔账户、网络采集或付费服务。后续真实小样应独立记录行测/申论各一卷的完整率、耗时、人工介入和来源证据，不能用合成测试替代。

官方参考：[Playwright持久配置](https://playwright.dev/docs/api/class-browsertype#browser-type-launch-persistent-context)、[认证状态](https://playwright.dev/docs/auth)、[响应读取](https://playwright.dev/docs/api/class-response)。
