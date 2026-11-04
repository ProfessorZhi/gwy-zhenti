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

每份卷只开一次练习、交一次白卷，进入解析页，逐题保存题干、选项、参考答案、解析、所属材料；下载题干、选项、材料与解析中的全部图片。

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
- 对齐报告 `anchor` < 0.8（该版本跳过，换下一个版本或下一份卷）；
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
