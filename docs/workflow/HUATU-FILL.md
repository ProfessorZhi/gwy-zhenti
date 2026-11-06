# 任务卡：华图补题（第一批 80 题）

[← 文档](../README.md) · 跟踪：[#155](https://github.com/ProfessorZhi/gwy-zhenti/issues/155)

## 目标

用华图在线的同卷数据，补全以下 4 份行测中粉笔未收录的 80 道题（含所在题组的给定材料）。

| 试卷 | 缺题 | 题号 |
| --- | ---: | --- |
| `省考/北京/2023/行测-统考.md` | 35 | 15、17–27、111–125、128–135 |
| `省考/新疆/2023/行测-统考.md` | 19 | 14–25、50、60–65 |
| `省考/吉林/2024/行测-统考.md` | 13 | 17–20、42–45、65–68、77 |
| `省考/上海/2021/行测-B类.md` | 13 | 18–21、80、119–126 |

## 分工

| 步骤 | 执行方 | 内容 |
| --- | --- | --- |
| 1–3 | Dell 本地 agent | 在华图找到同卷、交白卷取解析、保存为缓存目录 |
| 4–6 | `tools/huatu_fill.py` | 对齐、写入、校验（离线，不联网） |
| 7 | Dell 本地 agent | 提交并发起 Pull Request |

## 步骤

### 1. 找到同一份卷

在华图在线题库中按「地区 + 年份 + 科目 + 卷型」查找对应试卷，记录 `paperId`。

省考行测不公开发布原卷，华图与粉笔的版本都是考生回忆整理，**「网友回忆」不是跳过理由**；两家回忆版的总题数、个别题的有无和题序可以不同，**题数不一致也不是跳过理由**。是否同一份卷、每道缺题能否补，交给第 4 步的对齐报告判断，不要人工按题数筛选。

同一卷在华图有多个版本时，逐个抓取、逐个出对齐报告，取可补题最多的一个。

### 2. 取解析

用抓取脚本，不要用浏览器控制工具逐题读页面或手工监听网络（事件会在页面跳转时丢失，且工具日志会带出登录 Cookie）。在 `tools/fenbi` 目录下：

```bash
npm ci                                                     # 首次
node driver/huatu-capture.mjs --login                      # 首次：在弹出的专用浏览器里登录华图，回终端按回车
node driver/huatu-capture.mjs --paper-id <paperId> --url "<解析页地址>"
```

专用窗口里登录不了华图时，改为连接自己启动的 Chrome：用调试端口和单独的配置目录启动 Chrome（Chrome 136 起默认配置不能开调试端口），在这个窗口里照常手动登录，再让脚本连上它：

```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=D:\huatu-chrome
node driver/huatu-capture.mjs --cdp http://127.0.0.1:9222 --paper-id <paperId> --url "<解析页地址>"
```

脚本只新开一个标签页抓取，结束时关闭该标签页并断开，不关闭浏览器；`--cdp` 只接受本机地址。

- 每份卷只开一次练习、交一次白卷，复制解析页地址交给脚本；脚本只打开该地址、滚动到底、等待网络空闲，不点击、不提交。
- 登录状态保存在 `work/profiles/huatu-main/`，与日常 Chrome 分开；脚本只保存响应体和图片，不保存请求头，记录的接口地址去掉查询参数。
- 输出在 `work/huatu/<paperId>/raw/`：每个 JSON 响应一个文件、`images/` 下的图片、`index.json`（按「像题目数据」的程度打分，终端列出得分最高的 5 个）与 `page.html`。

第一份卷跑通后，找出 `raw/` 中承载整卷题目的响应，写一次转换脚本把它转成下一节的 `paper.json`；其余卷沿用同一转换脚本。

### 3. 保存缓存

每份卷保存为一个目录 `work/huatu/<paperId>/`（`work/` 不进仓库）：

```text
work/huatu/<paperId>/
├── paper.json
└── images/
    └── <任意文件名>.png
```

`paper.json` 格式：

```json
{
  "paperId": "4092439",
  "title": "华图页面上的试卷标题",
  "url": "华图试卷页面地址（不含账号参数）",
  "capturedAt": "2026-11-05T08:00:00Z",
  "questions": [
    {
      "stem_html": "<p>题干 HTML</p>",
      "options": [{"label": "A", "html": "选项 A"}, {"label": "B", "html": "选项 B"}],
      "answer": "B",
      "analysis_html": "<p>解析 HTML</p>",
      "material_id": "m3"
    }
  ],
  "materials": [{"id": "m3", "html": "<p>资料分析材料 HTML</p>"}],
  "images": [{"url": "页面中图片的原始地址", "file": "images/xxx.png"}]
}
```

- `questions` 按华图卷内顺序排列，**包含全部题目**（不只是缺的题），工具依靠已有题完成对齐。
- `material_id` 仅题组题目填写，对应 `materials` 中的材料；无材料的题省略该字段。
- `images` 列出 HTML 中出现的每一张图片，`url` 与 HTML 中的 `src` 完全一致。

### 4. 对齐报告（不写入）

选项缺口使用同一入口的 `--option-q <题号>`，必须先查看题干、邻题和图片校验结果；只采用来源完整选项组，不混排版本。申论材料缺口使用 `--essay-plan <本地计划.json>`，按华图原文和仓库锚点核对，先预览，再以 `--write --expect-after <预览哈希>` 写入。两个模式均不依据同号直接填入。

申论计划也支持 `https://gwy.gkzhenti.cn/paper/<数字ID>` 的公开题本，但仅限 2016 年及以后的卷。工具将实际来源登记为“公开真题库”，不冒记华图；仍要求原始快照哈希、同卷题目与材料锚点、完整段落边界及预览哈希。页面标注来源粉笔只说明其自述来源，不视为独立于粉笔的交叉证据。

```bash
python3 -I tools/huatu_fill.py --paper 省考/北京/2023/行测-统考.md --cache work/huatu/<paperId>
```

报告字段：

| 字段 | 含义 | 要求 |
| --- | --- | --- |
| `anchor` | 卷级锚点：本库已有题在华图卷中按题序对上的比例 | ≥ 0.8，否则不是同一份卷 |
| `offset` | 最常见的局部偏移（华图题号 − 本库题号） | 回忆卷可能不为 0，属正常 |
| `fills` | 可补的题，含华图题号与邻题夹逼票数 | 越多越好，不要求与缺题清单一致 |
| `skipped` | 不补的题及原因 | 逐条写进回报 |

对齐只采用题序单调递增的匹配作锚点；每道缺题按前后最近各 2 个锚点的局部偏移推算华图题号，前后两侧须同时支持。华图在中间增删题时，增删点前后的偏移各自成立；缺题恰好落在增删点、或华图同样缺这道题，工具会跳过并写明原因。

#### 乱序卷的显式逐题复核计划

自动模式仍要求 `anchor >= 0.8`。人工逐题核对已确认同卷、且有独立定位证据的乱序卷，可以另建 `--reviewed-plan` 计划。计划仅补列出的 A1 缺题，每题必须有完整题干、四选项、参考答案和解析。工具会检查全卷已有题及计划内目标，拒绝重复补入。当前人工模式要求题干含可比文字，纯图片题须停止补入。

计划 JSON 使用 `schema_version: 1`，包含 `paper`、原卷 `paper_sha256`、缓存 `cache_sha256`、原始归档清单 `source_manifest_sha256`、原始 HTML `source_html_sha256`、目录文件 `source_catalog` 及 `source_catalog_sha256`、`reviewer`、`reviewed_at` 和 `items`。目录须提供与缓存一致的标题、题量及 `paperId`，或与原始解析页 URL 一致的 `answerid`。后一种情况下报告 `source_identity` 明确区分目录核验的 answerid 与缓存记录的 paperId。缓存须保留 `sourceArchive`、`sourceHtmlSha256`，每张被引用的图片须带 `sha256`。

每个 item 记录 `q`、`huatu`、`method`、`rationale` 及 `anchors`，锚点记录本库 `q` 与来源 `huatu`，题号均从 1 开始。支持三种定位证据。

- `neighbors` 使用前后最近各两道已有题，至少三票同偏移且两侧均支持。
- `elimination` 声明闭区间 `local_range` 和 `source_range`，逐题核对整组，至少四个一一对应的已有题，唯一剩余题才能填入。
- `material_group` 在整组排除法上增加 `local_material` 和 `source_material`，要求两侧材料实际覆盖的题号集合恰好等于计划范围、来源材料 ID 唯一，完整材料规范化相似度至少 0.95。目前仅接受文字材料，含图片材料须停止补入。

锚点使用完整题干，相似度至少 0.85。已确认的同题异文若低于此值，必须在该锚点另列 `shared_passages` 与 `rationale`。共有条件须至少两段、每段至少十字、合计至少六十字，且组合在两卷中各唯一出现。复核记录应保留选项异文与弱证据排除理由。

```bash
python3 -I tools/huatu_fill.py --paper <试卷.md> --cache <缓存目录> --reviewed-plan <复核计划.json>
python3 -I tools/huatu_fill.py --paper <试卷.md> --cache <缓存目录> --reviewed-plan <复核计划.json> --write --expect-after <预检的after_sha256>
```

A2 选项缺口可同时指定 `--option-q <题号>` 和 `--reviewed-plan`，计划须设置 `mode: "A2"`，且仅列出这一个目标。原卷须实际存在选项占位，目标仍须通过题干相似或同法律、同选非方向及至少两个相同选项的核对。工具采用华图整组选项、答案及解析，并保存粉笔原题块供追溯，预检与写入哈希规则相同。

预检完成全部渲染和图片存在性检查，输出 `after_sha256`。写入必须带相同哈希，原卷或来源变化后必须重新复核。计划副本保存在 `assets-huatu-<paperId>/review-<sha256>.json`，各补题答案块链接该证据。人工复核写入串行锁定清单，先在同目录完整预写临时文件及恢复副本，再依次原子替换。I/O 异常时逐项回滚，某一路径回滚失败后仍继续恢复其他文件，并保留无法恢复路径的备份供排查。每卷仍单独提交 PR。

### 5. 写入

对齐报告符合要求后执行：

```bash
python3 -I tools/huatu_fill.py --paper 省考/北京/2023/行测-统考.md --cache work/huatu/<paperId> --write
```

工具会：替换题目与材料占位；图片复制到试卷目录下的 `assets-huatu-<paperId>/`；在文件头 `来源清单` 增加华图条目并更新 `校验状态`；刷新 `catalog/manifest.jsonl`。除被补题目与材料外，其余内容逐字节不变，否则工具报错且不写入。

### 6. 校验与重新生成

```bash
python3 tools/cloud_quality.py --check --verify-images
python3 tools/source_provenance.py --check
python3 -I tools/gap_report.py
python3 -I tools/repo_readmes.py
cd tools && python3 -m unittest discover -s tests
```

`gap_report.py` 输出中「缺题干」应相应减少。测试中写死的缺口数字（`tools/tests/test_gap_content_audit.py` 的 280）如有变化，按实际更新。

### 7. 提交

每份卷单独一个分支、一个 Pull Request，提交说明按 [参与贡献](../../CONTRIBUTING.md) 格式：

```
content: 华图补入北京2023行测 35 题
```

## 停止条件

出现以下任一情况立即停止，回报原始信息，不自行绕过：

- 验证码、登录失效，或一小时内累计 3 次 403/429；
- 自动对齐报告 `anchor` < 0.8（该版本跳过；已完成上述显式逐题复核的卷使用独立计划入口）；
- 工具报错。

## 回报格式

```text
任务：华图补题第一批
试卷：省考/北京/2023/行测-统考.md
华图 paperId：
对齐：anchor=… offset=… 可补 N 题 / 不补 M 题（原因）
写入：是 / 否
校验：cloud_quality hard_errors=… · 单元测试 通过/失败
缺题干：补前 280 → 补后 …
PR：
问题：
```
