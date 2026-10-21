# 公务员真题库总计划：粉笔 → Markdown 知识库

本文是唯一的执行依据。与 `docs/WORKFLOW-GPT-DISPATCH.md`、`docs/FENBI-FULL-CAPTURE-PLAN.md` 冲突时以本文为准；
设计细节见 `docs/WORKFLOW-THINKING.md`。

## 一、目标

把粉笔网 2016–2026 年国考、省考的**行测和申论**整理成本库的 Markdown：题干、选项、材料、插图、答案、解析齐全，
并以粉笔为准逐卷核对已有试卷。

**进度只看两个数，分科目统计**：粉笔目录卷数（分母）、已进入 `main` 且来源为粉笔的卷数（分子）。

## 二、已定规则（不再讨论，代码和 agent 都按此执行）

| 事项 | 决定 |
|---|---|
| 仓库 | 私有；粉笔题目、答案、解析全部收录（rights 文件 `coverAllCapturedSources: true`） |
| 年份 | 默认 2016–2026；浙江另有例外（代码 `driver/year-policy.mjs` 现为不设下限，GPT 报告的口径为 2008 起，待用户确认） |
| 优先级 | 重点地区优先；免费卷优先，会员卷单列 |
| 交白卷 | 允许，用于取得答案和解析；每卷最多开 1 次练习、交 1 次白卷，不作答 |
| 停留 | 交卷前停留 15 秒 |
| 替换已有卷 | 粉笔优先；粉笔题数比已有卷少则不替换 |
| 粉笔也缺的题（"征集中"） | 标注后照常发布 |
| 答案冲突 | 用粉笔答案，并注明另一来源的答案 |
| 合入 main | 完整闸门通过后自动合入（`AUTO_MERGE=1`） |
| 账号风险 | 用户接受；可以使用多个粉笔账号 |
| 不做 | 绕过验证码或限流；购买；把登录 Profile、Cookie 放进 git |
| 必须停 | 验证码、登录失效、一小时内累计 3 次 403/429 → 写 STOP，等用户处理 |

## 三、现状（2026-10-21）

- `main`：1191 份（申论 738、行测 453），**其中来自粉笔的 0 份**。
- Dell 本地缓存：517 份行测已抓题并交白卷，但一份都没落进 `main`。
- 代码：PR #104（单卷流水线 worker + 完整闸门 + 自动合入）已写好；本地含浏览器测试全部通过（Dell 上缺 Chromium 时 2 项浏览器测试会跳过，跳过不算通过）；尚未在真实站点跑过。
- GitHub Actions 因计费/额度问题不运行，CI 红色不代表代码失败；以本地 `node --test` 为准。

| 环节 | 行测 | 申论 |
|---|---|---|
| 目录巡检 | 有；Dell 现有快照 34 个地区均为 1–4 页、无截断（GPT 核实），行测目录缺口需另行实站核验 | **无** |
| 题目、材料、图片 | 有 | **无** |
| 答案、解析 | 有（解析页 DOM + solution JSON） | **无**，需先确认交白卷后能否看到参考答案 |
| 结构核对 | 有（题数、编号、选项、图片、占位文字，不合格判 C） | 校验规则有，无数据 |
| 与已有卷比对 | 半成品：按题目内容配对、补继承答案、题数少不替换 | 无 |
| 答案冲突标注 | **无**（现在直接用粉笔答案，不标注旧答案） | 无 |
| 粉笔缺题 | 按规则保留题位、标注"粉笔暂未收录本题"后发布；缺题超过半数仍判 C；不会替换本库更完整的卷 | — |
| 试卷身份 | 目录行按完整标题精确选择；练习页 JSON 的 paperId 与 sourceId 不一致则不交卷并隔离；已缓存卷用 verify-identity 离线核对 | — |
| 落地进 main | 代码有，**从未跑通** | — |

## 四、分工

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| 用户 | 定规则、批准阶段切换、处理 STOP、登录账号 | — |
| Claude Code（本仓库会话） | 写代码、开 PR、根据回报修问题、维护本文 | 不碰 Dell、不碰账号 |
| GPT（总调度） | 在 Dell 上按第五节的任务卡派给本地 agent；收集回报；把回报原样转给用户和 Claude Code | 不自己设计方案、不加验证层、不新建分支或工具、不改任务卡范围 |
| 本地 agent（Dell 上的 Claude Code 会话） | 一次只执行一张任务卡，照命令运行，按回报格式交结果 | 不扩大范围；任务卡没写的事一律不做，写进回报的"问题"一栏 |

**防止绕圈的纪律**：
1. 每张任务卡只有一个交付物：回报格式里的那几项数字。没有数字的回报视为未完成。
2. 遇到阻塞（命令报错、权限、缺文件）：停下，回报原样的错误输出，不自行设计替代方案。
3. 只有一种情况允许 agent 改代码：阻塞当前命令的明显缺陷（如缓冲区太小），改动 ≤20 行、附测试、推到当前 PR 分支，并在回报里写明。其他改动交给 Claude Code。
4. 第二节的规则不再论证。新的担忧写进回报，由用户决定。
5. 不开新的 `audit/*`、`assetsqa/*` 一类分支，不写新的检查工具。

## 五、任务卡（按顺序；上一张回报后用户批准才发下一张）

### T1 落地实验（不开浏览器，不停服务，不 push）

```text
用 PR #104 的最新提交建 scratch checkout，在 tools/fenbi 下 npm ci。
从 origin/main 新建临时集成工作树（分支 fenbi-landing-trial）。把生产 work/fenbi/papers 复制一份作为输入。
用 worker/publish.mjs 的 landMany 把全部已交卷的卷（t2 台账状态 complete / submitted_partial）转换并发布进临时工作树，
然后本地提交，用 worker/gate.mjs 的 fullGate 对 origin/main 检查。不要 push。
回报：
  卷数（输入/已交卷）、A 数、C 数、新增几份、替换几份
  promote 被拦原因及计数
  C 的原因 Top 5（原因 + 卷数）
  闸门 ok 与否；不通过时 reasons 前 10 条
  总耗时
```

**T1 结果（2026-10-21，Dell 回执）**：516 份缓存 → 落地 363（新增 340、替换 23），C 100 份：
64 份粉笔与本库都缺题、1 份缺题且材料计数冲突、35 份技术缺陷（26 图片解码校验、6 选项标签、2 选项正文、1 复合）。
闸门在大批量时因输出缓冲 1MB 报错，已修。另发现两处需修：缺题卷按规则应标注后发布（已实现，见下）；试卷身份只靠标题匹配（已加固，见 T1b）。

### T1b 已缓存卷身份核对（不开浏览器）

```text
在 scratch checkout（PR #104 最新提交）的 tools/fenbi 下，对生产 work/fenbi 的一份副本运行：
  FENBI_WORK_DIR=<副本> node worker/verify-identity.mjs
先不加 --write。回报最后一行 JSON 原文，以及 identity-report.json 里 verdict=quarantine 的前 10 行。
用户确认后，对生产 work/fenbi 运行一次 --write（只写本卷 document.json 的身份证据和 identity-quarantine.json），然后重跑 T1。
```

### T2 缺口报告（只读本地文件）

```text
读 work/fenbi/catalog-live-*/ 和 p0-discover-*/ 下的目录快照，按 地区 × 年份 统计粉笔行测卷数（去重 sourceId），
与 main 的 catalog/manifest.jsonl 对比。
回报一张表：地区、粉笔卷数、本库行测卷数、已缓存卷数、巡检页数、是否被页数截断（pageLimitApplied）；最后一行合计。
```

### T3 Claude Code 修复 → 用户合并 #104

Claude Code 根据 T1 回报修卡住落地的原因，并补上答案冲突标注。用户合并 PR 后进入 T4。

### T4 生产切换到 worker 并自动合入

前提：T1b 的身份核对结果已回报，且用户已就"身份无法离线证明的卷是否合入"做出决定。

```text
按 docs/WORKFLOW-THINKING.md 第六节部署：main checkout 更新；集成工作树从 origin/main 新建 fenbi-integ；
collector.env 设 SERVICE_MODE=worker、INTEG_REPO、RIGHTS_FILE、PUSH=1、AUTO_MERGE=1、WORKER_TABS=3、WORKER_DWELL_MS=15000、WORKER_MAX_PAPERS=3；
停用 fenbi-publisher；重启 fenbi-pipeline。第一轮会先把已缓存的卷补落地并合入 main。
回报：worker.log 里 catchup_land 和 publish 两行原文；main 新增的粉笔卷数；ALERT / ALERT-merge-gate / STOP 是否存在。
```

### T5 行测补巡检 + 实跑

```text
对 T2 中被截断的地区，用 MAX_PAGES_PER_REGION=30 重新巡检（只读，不开练习）。
然后 WORKER_MAX_PAPERS 依次 3 → 10 → 60，每档跑一轮。
每档回报：worker.log 每卷一行（status、题数/应有、答案数、图片数、init 次数、耗时）的统计，
最后一行汇总的 papersPerHour、landed、mainPushes；任何风控信号。
```

### T6 申论样本（为写代码准备）

```text
用现有账号打开 1 份已做过的申论题目页和它的解析页，不交卷、不开新练习。
保存去掉账号信息的页面 HTML（题目区、材料区、解析区）到 work/fenbi/shenlun-sample/，
另存解析页加载时的 JSON 响应（只保留和题目/答案/解析相关的接口）。
回报：文件路径、每个文件的大小，以及答案和解析在页面里的位置（选择器或 JSON 字段名）。
```

### T7 Claude Code 写申论支持 → 试跑

申论目录巡检、抓取、解析、答案合并、Markdown 渲染。试跑按 T5 的 3 → 10 → 60。

### T8 C 卷修复队列（LLM agent，T4 稳定后）

```text
对 C 卷逐卷修复结构问题（漏题、编号、选项、图片引用）。
硬性约束：题干、选项、答案、解析的原文字符不得改动，只允许调整结构；
修复后用脚本比对修复前后的正文字符序列，一致才提交；不一致的卷退回。
```

## 六、回报格式（所有任务卡通用）

```text
任务：T?
结果：完成 / 阻塞
数字：（任务卡要求的各项）
问题：（没有就写"无"）
```
