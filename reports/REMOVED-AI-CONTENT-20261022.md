# 移除已进入 main 的 LLM 原创作答（2026-10-22）

用户决定：库内只收粉笔原文，停止一切 LLM 生成的答案/解析。本 PR 只做**逐卷回退**，
不新增任何答案，不改动原题、给定材料、图片、题号和历史来源元数据。

## 删除范围（14 卷 / 25 处答案 + 6 处解析）

| 来源 PR | 卷 | 删除 |
|---|---|---|
| #110 | 上海 2020 行政执法卷 | 第 1–3 题答案 |
| #110 | 上海 2017 行政执法卷 | 第 2、3 题答案 |
| #110 | 广东 2026 行政执法 | 第 1 题答案 |
| #112 | 福建 2018 县级卷 | 第 1–3 题答案 |
| #112 | 四川 2023 上半年行政执法卷 | 第 1–4 题答案 |
| #112 | 福建 2023 县乡 | 第 3 题答案 |
| #112 | 福建 2024 县乡卷 | 第 1 题答案 |
| #112 | 四川 2024 县乡、普通选调卷 | 第 1 题答案 |
| #112 | 福建 2021 县级 | 第 3 题答案 |
| #113 | 福建 2024 行政执法 | 第 1–4 题答案 |
| #113 | 福建 2023 省市 | 第 3、4 题答案 + 第 1、2 题解析 |
| #113 | 四川 2026 县乡、普通选调卷 | 第 3 题答案 |
| #113 | 福建 2021 乡镇 | 第 2 题答案 |
| #113 | 四川 2023 省市 | 第 1–4 题解析 |

合计 **25 处答案、6 处解析**，与三笔 squash commit 的已知增量一致。

## 回退方法

- 每卷从**引入该 AI 内容的 squash commit 的 parent** 取回原始字节：
  #110 → `30ffc8209`，#112 → `74e93797d`，#113 → `1ab49a31b`；
- 14 卷在该 commit 之后均无其他修改（`git log <commit>..HEAD -- <path>` 为空），
  因此整文件恢复不会丢失后续非 AI 变更；
- 校验：恢复后的“材料+题目”正文 SHA 与 parent 完全一致；所有非 AI 答案块的 SHA 与 parent 一致；
- manifest 只回填 8 个 AI 相关字段（sha256/bytes/answer_blocks/has_answer_content/
  missing_answer_numbers/issues/notes/source_validation），其余字段（含 PR #118 的字段）
  保持当前 main 原样；14 行之外的 manifest 行逐字节不变。

## 回退结果

- 14 卷恢复为 pre-AI 版本，AI 标签、frontmatter 的 `新增原创…` 字段、导读表状态全部消失；
- 原有占位/缺失题位恢复（如广东 2026 第 1 题、福建 2023 县乡第 3 题、上海两卷第 1 题）；
- 真实来源已有答案、非 AI 解析、材料、图片、题号、source metadata 全部保留；
- 全库可识别缺答案位置：**426 → 451**（回加 25 处；6 处解析不改变该计数）；
- 清理基线为最新 main `4e8ebdfb7`（含 S1 新落申论批次；与 14 卷无交集），共 **1243 卷**（manifest 1243 行，申论 749，行测去重由 #118 完成）。

## 回归与门禁（本地真实结果）

```bash
cd tools
python3 -m unittest tests.test_remove_ai_content -v
python3 -m unittest tests.test_round10_shenzhen tests.test_shenlun \
  tests.test_export_shenlun tests.test_gates tests.test_round4_answers tests.test_round5_bulk
```

- 6 项清理回归 + 81 项既有测试，共 **87 项 PASS**；
- R10 测试的全局行数由 729 更新为 740（S1 新增 11 份申论后既有硬编码），历史快照的 `remaining=568` 不变；
- `test_remove_ai_content` 断言：14 卷 sha/bytes 与 receipt 一致、无 AI 标签、
  正文 SHA 与 pre-AI 一致、非 AI 答案块未变、manifest 14 行与文件一致、AI 回执/工具已删除；
- `cloud_quality.py --check` 在**干净 main** 上即 FAIL（PR #118 后的清单与生成器行不一致），
  与本次回退无关；本次 14 行经 `cloud_quality.scan()` 对比**0 差异**；
- `verify_repair_receipts.py` 历史链需将约 2GB 仓库多轮复制到 `/tmp`，本机磁盘配额不足，
  无法完成（环境限制，main 上同样存在）；
- GitHub Actions 的 job 因 billing/spending limit 0 步骤失败，**不声称 CI 通过**。

## 其他 AI 遗留（只读清单，未删除）

全库扫描 `原创示范作答`、`AI辅助编写`、`模型生成` 等标签，除本次回退的 14 卷外，
还有 **9 份早期任务加入的 AI 内容（24 个块）**，来源不属于 #110/#112/#113，
本 PR 不擅自删除：

- `省考/江苏/2026/申论-B类.md`（4 块）
- `省考/浙江/2026/申论-A类.md`、`2026/申论-C类.md`、`2025/申论-A类.md`（各 1 块）
- `省考/上海/2019/申论-行政执法卷.md`（3 块）
- `省考/深圳/2025/申论-一卷.md`、`2025/申论-二卷.md`（各 3 块）
- `省考/安徽/2026/申论-A类.md`（4 块）
- `省考/重庆/2024/申论-一卷.md`（4 块）

这些卷的 AI 内容不属于本次已确认的三笔 commit；如需清理，应由主控另行确认来源与范围。

## 证据

`reports/REMOVED-AI-CONTENT-20261022.json`：逐卷记录 before/after SHA、bytes、
正文 SHA、删除的答案/解析题号、保留答案块 SHA、manifest 前后字段。
`tools/tests/test_remove_ai_content.py`：上述断言的回归测试。
