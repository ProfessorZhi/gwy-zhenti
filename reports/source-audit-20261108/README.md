# 2026-11-08 跨来源行测补录 · 第二轮（PR #194）

## 结论

- PR #194 最终 **19 道净新增行测题**（原 18 题重验 + 国考2022副省级 q4）。
- 行测缺题干：**280 → 261**；缺选项 4、缺卷 51、待核 15 不变。
- 原 18 题全部通过新的**源侧快照门禁**；没有因新门禁撤回的题（云南2025 q44、青海2024 q90 在上一轮已撤回，仍保持占位）。
- 国考2022副省级 q4 用真实 GitHub PDF 第1页原题、两幅 PDF 原始图片、答案 PDF q4=D 写入；图片 SHA 与 PDF SHA 均已登记。
- 青海2024 q90 仍**未写**：唯一可核的 dtiku 同卷页返回 anti-bot 202，未绕过。
- 内蒙古2024 只登记 5 道完整候选，**未建题本、未写题卷**（源页 72 个可见条目、9–25 缺失、多题缺图/选项损坏）。

## A. 根因修复（source_fill.py）

### A1. 源侧锚点验证改为快照绑定

新增 `tools/source_snapshot.py`，从公开源页抓取结构化快照（题号 → 题干/选项/答案）：

- `gkhenti`：同时抓 paper 页与 answer 页；120/130 题可解析。
- `gwyeasy`：解析 HTML 题号/选项（无答案时由 `answer_snapshot` 补）。
- `text`：从公开 PDF 的文本抽取题号/选项（用于海豚公考湖南2023）。

`source_fill.py` 现在要求每份 plan 带 `source_snapshot`（path + SHA256），并逐项验证：

1. 快照文件 SHA 与 plan 一致；
2. 快照 URL 与 `source_url` 规范化后一致；
3. 快照必须含 **source_q-1 / source_q / source_q+1**；
4. 目标题干/四选项/答案必须与快照的 source_q 记录一致；
5. 每个 anchor 的 `source_text` 必须出现在它所声明的 source_q 记录内（不再接受“证据文件任意位置出现”）；
6. 至少一个 anchor 在目标前、一个在后；
7. 无答案时，`answer_snapshot` 必须有答案，且同题文本满足 `exact` 或 ≥0.90 的 `minor_wording`（必须写 note）。

这直接堵住了上一轮 q59/q44/q90/q94 的错误：旧工具只查“文本在 evidence 文件里出现过”，不查它在源卷的哪一题。

### A2. metadata-only 同步正文来源行

`--metadata-only` 现在同时更新：

- frontmatter 来源条目的 `题号: [N]`；
- 目标题正文 `**来源**：... 第N题；` 中的题号。

要求 plan 提供 `old_source_q`；正文缺少“第N题”、或当前 N 与 old 不一致时拒绝。新增参数化测试覆盖 **广西 q35 (35→34)、广西 q59 (59→67)、河北 q94 (95→106)** 三组历史不一致。

### A3. fail-closed 撤回

新增 `--withdraw`：仅当当前题块与 `expected_current` 的题干/选项/答案逐字匹配时，才恢复“粉笔暂未收录”占位、删除对应来源条目、在 `校验状态` 记撤回原因；CAS 仍要求 `--expect-after`。本轮用它修复了 q4 的图片路径错误。

### A4. 写入回执

新增 `--receipt`：每题一条 JSONL，含 action、target、source_q、**规范化 URL**、source_snapshot SHA、answer_snapshot SHA、plan SHA、before/after SHA、UTC 时间。19 条 verify 回执见 `verify-receipts.jsonl`。

### A5. 图片题支持（fail-closed）

`images` 计划现在要求：

- 每张图 `source_path` + SHA256 + 安全 filename + `{{IMGn}}` marker（题干中恰好一次）；
- `assets_dir` 必须是试卷同目录下的**单个** `assets-` 目录名，拒绝 `/`、`\`、`..`；
- 目标同名文件已存在且 SHA 不同则拒绝覆盖；
- `source_pdf` 记录公开 URL + PDF SHA（可选本地 path + SHA）；
- 写入前按 SHA 校验并原子复制图片；`--verify-existing` 校验引用与目标文件 SHA。

新增 4 个图片测试（写图/哈希不符/marker 缺失/路径穿越）。

## B. 19 道题

| # | 本库题位 | 来源原题位 | 答案 | 源侧快照 | 备注 |
|---:|---|---|:---:|---|---|
| 1 | 广西2025 q35 | 云南2025 q34 | D | `yn2025.json` q33/34/35 | 原 body 误写第35题，已修正 |
| 2 | 广西2025 q59 | 甘肃2025 q67（同题云南 q59） | C | `gs2025.json` q66/67/68 | 原写入“99人/A”已撤回重写 |
| 3 | 河北2022 q94 | 浙江2022 C类 q106 | C | `zj2022c.json` q105/106/107 | 原写浙江 A q95，已修正 |
| 4–11 | 青海2020 B q108–q115 | 江西2020 县级 q108–q115 | B/C/C/B/D/B/C/A | `jx2020x.json` q107/116 边界 + q±1 | 连续 8 题整块 |
| 12 | 黑龙江2025 q113 | 辽宁2025 q103 | B | `ln2025.json` q102/103/104 | 源页括号公式简写，已记录 minor wording |
| 13 | 湖南2025 q54 | 新疆2025 q49 | D | `xj2025.json` q48/49/50 | |
| 14 | 甘肃2026 q35 | 贵州2026 q30（同题云南 q31） | B | `gz2026.json` q29/30/31 | 锚点 q29 源页多“更”字，已缩短为公共前缀 |
| 15 | 青海2024 q50 | 山西2024 q49 | B | `sx2024.json` q48/49/50 | |
| 16 | 青海2024 q60 | 山西2024 q60 | C | `sx2024.json` q59/60/61 | 锚点 q61 源页分数被剥，已缩短为公共前缀 |
| 17 | 内蒙古2026 q95 | 内蒙古2026 q95（gwyeasy） | D | `gw20446.json` q94/95/96 + `answer_snapshot` 黑龙江2026 q89 | 单源题干；答案由同题黑龙江 q89 佐证 |
| 18 | 湖南2023 q66 | 湖南2023 q66（海豚PDF） | B | `hn2023pdf.json` q65/66/67 + `answer_snapshot` 广东2023县级 q58 | 同题逐字一致 |
| 19 | 国考2022 副省级 q4 | 国考2022 副省级 q4（GitHub PDF） | D | `gk2022fs.json` q3/4/5 | 两幅 PDF 原图，SHA 登记 |

## C. 未写入/阻塞

| 项 | 原因 | 状态 |
|---|---|---|
| 青海2024 q90 | dtiku 青海同卷页 `202 anti-bot`；gkhenti 青海页 q90 仍是“征集/默认A”占位；湖北 q89 无后锚泡沫经济 | **未写**，保持占位 |
| 云南2025 q44 | 海南 q47 所在序列与云南 q45=传统文博不连接 | 上一轮已撤回，保持占位 |
| 广西2025 q34 | 来源答案 A/C 冲突 | 跳过 |
| 北京2020乡镇 q42/q89 | q89 与 2010 江西同题复用风险 | 跳过 |
| 内蒙古2024 行测 | 源页不完整（72 个可见条目、9–25 缺失、多题缺图/选项损坏）；仓库规范允许“来源原缺”但不允许把 5 题误表成整卷 | **仅候选**，见 `candidates/nm2024/` |

## D. 质量门禁（实际输出）

```text
python3 -I tools/refresh_manifest.py --write   → 1669 行，需刷新 1，缺失 0
python3 -I tools/catalog_index.py --out ...    → 3,563 行
python3 -I tools/coverage_stats.py --svg ... --update-doc docs/COVERAGE.md
  → 两张 SVG + COVERAGE.md 已同步
python3 -I tools/repo_readmes.py               → 1 个文件
python3 -I tools/gap_report.py                 → 缺卷 51、待核 15；缺题干 261、缺选项 4、缺答案 0
python3 -I tools/refresh_manifest.py --check   → 需刷新 0
python3 -I tools/catalog_index.py --check      → 校验通过（1669 卷；89,717 题；19,363 图）
python3 -I tools/repo_readmes.py --check       → 最新
python3 -I tools/gap_report.py --check         → 最新
cd tools && python3 cloud_quality.py --check --verify-images
  → papers=1669, images=19170, image_refs=19363,
    truncated_files=0, truncated_questions=0,
    hard_errors=0, forbidden_files=0, machine_flagged_files=60
cd tools && python3 source_provenance.py --check
  → 试卷 1669 · 结构化来源清单 25 · 来源问题 0
cd tools && python3 -m unittest discover -s tests
  → Ran 435 tests in 39.043s · OK
git diff --check → 通过
```

测试基线由 262 更新为 **261**（新增 q4）；A2 字面“缺”排除数仍为 12，A2 确认项仍为 4。

## E. 产物

- `plans/*.json`：19 份 reviewed plan（q4 另有 withdraw 计划）。
- `snapshots/*.json`：14 份源侧快照（按 q±1 窗口裁剪，含 URL/抓取方式/窗口）。
- `evidence/images/gk2022-q4-*.png`：两幅真实 PDF 图片。
- `verify-receipts.jsonl`：19 条逐题验证回执（URL 规范化、snapshot/plan/before/after SHA）。
- `write-receipts-20261108.jsonl`：q4 的写入回执（含撤回后重写）。
- `candidates/nm2024/`：内蒙古2024 的 5 道完整候选，明确 NOT_WRITTEN。

## F. 边界

未合并 PR；未关闭旧 PR；未 force-push；未 reset/stash/clean 既有工作区；未使用生产服 Admin/Vince；未声称 DeepSeek；未绕验证码/会员/403/429/anti-bot；题卷正文只经 `tools/source_fill.py` 写入或撤回。
