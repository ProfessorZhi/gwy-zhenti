# 2026-11-08 跨来源行测补录（PR #194 重建）

## 结果

本轮先**撤回 #194 原 6 题**（原 commit `8aa1dbf6`，备份分支 `backup/pr194-head-8aa1dbf6`），逐题独立复核后用 `tools/source_fill.py` 的 reviewed plan、证据 SHA、前后锚点、预检 `after_sha256` 与 `--expect-after` CAS 重新写入。

最终写入 **18 题**：

| # | 本库题位 | 来源原题位 | 来源性质 | 答案 |
|---:|---|---|---|---|
| 1 | 广西2025 q35 | 云南2025 q34 | 公开真题库镜像（源标注 fenbi） | D |
| 2 | 广西2025 q59 | 甘肃2025 q67（同题云南2025 q59） | 公开真题库镜像 | C |
| 3 | 河北2022 q94 | 浙江2022 C类 q106 | 公开真题库镜像 | C |
| 4 | 青海2020 B q108 | 江西2020 县级 q108 | 公开真题库镜像 | B |
| 5 | 青海2020 B q109 | 江西2020 县级 q109 | 公开真题库镜像 | C |
| 6 | 青海2020 B q110 | 江西2020 县级 q110 | 公开真题库镜像 | C |
| 7 | 青海2020 B q111 | 江西2020 县级 q111 | 公开真题库镜像 | B |
| 8 | 青海2020 B q112 | 江西2020 县级 q112 | 公开真题库镜像 | D |
| 9 | 青海2020 B q113 | 江西2020 县级 q113 | 公开真题库镜像 | B |
| 10 | 青海2020 B q114 | 江西2020 县级 q114 | 公开真题库镜像 | C |
| 11 | 青海2020 B q115 | 江西2020 县级 q115 | 公开真题库镜像 | A |
| 12 | 黑龙江2025 q113 | 辽宁2025 q103 | 公开真题库镜像 | B |
| 13 | 湖南2025 q54 | 新疆2025 q49 | 公开真题库镜像 | D |
| 14 | 甘肃2026 q35 | 贵州2026 q30（同题云南2026 q31） | 公开真题库镜像 | B |
| 15 | 青海2024 q50 | 山西2024 q49 | 公开真题库镜像 | B |
| 16 | 青海2024 q60 | 山西2024 q60 | 公开真题库镜像 | C |
| 17 | 内蒙古2026 q95 | 内蒙古2026 q95（gwyeasy） | 单源考生回忆版；黑龙江2026 q89/辽宁2026 q85 同题佐证（措辞略有差异） | D |
| 18 | 湖南2023 q66 | 湖南2023 q66（海豚公考星光镜像 PDF）；答案由广东2023县级 q58 同题佐证 | 公开 PDF + 同题答案 | B |

> 所有来源均为公开培训机构整理页/考生回忆版，**不冒充官方原卷**；答案来自同源题库参考键，非官方答案。

## 原 6 题的复核结论

| 原题 | 复核结论 | 处理 |
|---|---|---|
| 广西2025 q35 | 题干/选项/答案 D 可读；原 body 来源行写“第35题”，实际来源为云南 q34 | **保留并修正**：source_q=34，body 与 frontmatter 均写 34 |
| 广西2025 q59 | **原写入错误**：写成了“甲和乙两个科研单位共有99名工作人员…”（云南 q60/A）。库内来源注记 q58=甘肃66、q60=甘肃68，锁步指向甘肃 q67＝云南 q59“甲、乙、丙3名研究生…”，答案 C | **撤回后重写**为正确题目 |
| 云南2025 q44 | **无法唯一映射**：库内 q43=免疫系统、q45=传统文博；海南 q47（创造力）所在序列为免疫(q46)→创造力(q47)→金融(q48)，与云南 q45 不符；dtiku q44 实为甘肃 q46 | **撤回**，保持占位 |
| 青海2024 q90 | **锚点不成立**：湖北 q89 有“虫害”，但湖北无后锚“泡沫经济”；青海自身公开页 q90 仍为征集占位 | **撤回**，保持占位 |
| 河北2022 q94 | 题干/选项/答案 C 可读；原 source 写浙江 A q95，但库内 q93=浙江C105、q95=浙江C107、q96=浙江C108，锁步指向浙江 C q106 | **保留并修正**：source_q=106，variant=C类 |
| 内蒙古2026 q95 | 题干/选项/答案 D 可读；单源 gwyeasy | **保留**，标注单源；黑龙江 q89/辽宁 q85 同题佐证 |

## 8 题整块的锚点证明（青海2020 B q108–115）

库内 q106/q107/q116/q117 与江西2020县级同号逐字一致：

- q106 联觉（答案 C）
- q107 疼痛共情（答案 B）
- q116 AI 市场规模（答案 B）
- q117 AI 增长率（答案 D）

中间 q108–q115 八题即缺口，逐题答案 B/C/C/B/D/B/C/A。该块是本轮唯一“连续 8 题”整块补录。

## 质量门禁（实际命令与结果）

```text
# 1) 刷新
python3 -I tools/refresh_manifest.py --write
  → 共 1669 行 · 需刷新 9 · 文件缺失 0
python3 -I tools/catalog_index.py --out catalog/INDEX.md
  → 已写入 catalog/INDEX.md（3,563 行）
python3 -I tools/coverage_stats.py --svg docs/assets
  → 已写入 docs/assets/coverage-heatmap.svg / papers-by-year.svg
python3 -I tools/repo_readmes.py
  → 写入 8 个文件
python3 -I tools/gap_report.py
  → 缺卷 51、待核 15；行测 缺题干 262 缺选项 4 缺答案 0

# 2) 一致性
python3 -I tools/refresh_manifest.py --check      → 需刷新 0
python3 -I tools/catalog_index.py --check         → 校验通过
python3 -I tools/repo_readmes.py --check          → 最新
python3 -I tools/gap_report.py --check            → 最新

# 3) 质量/来源
cd tools && python3 cloud_quality.py --check --verify-images
  → hard_errors=0, forbidden_files=0, truncated_files=0,
    truncated_questions=0, machine_flagged_files=61
cd tools && python3 source_provenance.py --check
  → 试卷 1669 · 已登记结构化来源清单 24 · 来源问题 0

# 4) 单元测试
cd tools && python3 -m unittest discover -s tests
  → Ran 422 tests in 36.057s · OK

# 5) 空白
git diff --check → 通过（rc=0）
```

## 缺口变化

| 指标 | 写入前 | 写入后 |
|---|---:|---:|
| 行测缺题干 | 280 | **262** |
| 行测缺选项 | 4 | 4 |
| 缺卷 | 51 | 51 |
| 考试身份待核 | 15 | 15 |
| 申论缺题目/材料/答案 | 0/0/0 | 0/0/0 |

`a2_excluded_valid_literal` 由 13 降为 12，原因是本轮补入的题中有一道此前含字面“缺”选项的题位被补齐；A2 确认项仍为 1+3=4，未变化。测试基线据此更新为 262/12。

## 未写入/跳过

- 云南2025 q44：保持占位（见上）。
- 青海2024 q90：保持占位（见上）。
- 国考2022副省级 q4：含两幅图片，`source_fill.py` 当前拒绝图片题；未扩展工具，保持未补。
- 北京2020乡镇 q42/q89：q89 与 2010 江西同题存在复用风险，未人工排除前不写。
- 深圳2020 q7/q9：选项仍缺，不写。
- 其余候选未在本轮写入。

## 证据与计划

- `plans/*.json`：18 份 reviewed plan（含 paper_sha256、source_q、anchors、证据 SHA）。
- `evidence/*.txt`：每题题干/选项/答案/锚点快照。
- `write-receipts.jsonl`：18 条写入回执，`before_sha256`/`after_sha256` 构成同卷写入链。

## 边界

未合并任何 PR；未关闭旧 PR；未使用生产服 Admin/Vince；未声称 DeepSeek；未绕验证码/会员/403/429。
