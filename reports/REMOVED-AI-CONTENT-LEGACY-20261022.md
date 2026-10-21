# 移除早期遗留的 LLM 作答（第二阶段，2026-10-22）

用户决定：库内只收粉笔原文。本 PR 只删除第二阶段已核实的 **9 卷 / 24 块**早期 AI 作答，
不生成任何新答案，不改粉笔原题、材料、图片、题号或真实第三方参考答案。

## 删除范围（9 卷 / 24 块）

| 来源轮次 | 卷 | 删除题号 |
|---|---|---|
| R8 `8c2368361` | 江苏 2026 申论-B类 | 1, 2, 3, 4 |
| R8 | 浙江 2026 申论-A类 | 2 |
| R8 | 浙江 2026 申论-C类 | 2 |
| R8 | 浙江 2025 申论-A类 | 2 |
| R9 `0faccfb1e` | 上海 2019 申论-行政执法卷 | 1, 2, 3 |
| R9 | 安徽 2026 申论-A类 | 1, 2, 3, 4 |
| R9 | 重庆 2024 申论-一卷 | 1, 2, 3, 4 |
| R10 `f0649b5c1` | 深圳 2025 申论-一卷 | 1, 2, 3 |
| R10 | 深圳 2025 申论-二卷 | 1, 2, 3 |

合计 **24 块**，与 `ROUND8/9/10-ORIGINAL-ANSWERS-20261013.jsonl` 的 `added_answers`/`answers`
逐一对应；每份 receipt 的 `before_sha256` 是 AI 写入前的精确字节，`after_sha256` 与当前
main 文件完全一致，故可**逐字节逆转**回 pre-AI 状态。

## 来源认定（为何不是粉笔/第三方原版）

- 三份 receipt 明确记录 `kind: independent_original_study_answers`，
  `model_authored: true` / `authorship: AI-assisted original, not sourced scored exam script`；
- 文内块标签为 `原创示范作答（AI辅助编写；非机构原文，未经实考评分）`，
  frontmatter 含 `新增原创示范作答题号`、`新增示范性质`、`第X轮示范修复凭据`；
- 这些块均含 AI 写作说明与同题对照链接，不是粉笔页面原文；
- 每份 receipt 的 `preserved_answers` 记录了同卷已有第三方答案的哈希，
  逆转后逐题 digest 校验一致（浙江 2025A/2026A/2026C 各保留 2 处）。

## 回退方法

- 用 R8/R9 的行级 `operations` 逆序还原；R10 用 `verify_round10_reference.reverse()`
  按 receipt 还原；
- 9 份文件全部恢复为 receipt 的 `before_sha256`；材料+题目正文 SHA 与 receipt 记录一致；
- 原占位题位恢复（如“本题参考答案尚未核实收录”或整段缺失），不伪造替代答案；
- manifest 仅回填 9 行的 8 个 AI 相关字段（sha/bytes/answer_blocks/has_answer_content/
  missing/issues/notes/source_validation），来源为各 AI commit 的 parent 清单行；
  其余 1234 行与最新 main 完全一致（S1/S2 的 38 份粉笔申论、PR#120 的 14 卷均保留）；
- 删除 R8/R9/R10 的 AI receipt/draft/verifier/test/报告与交付脚本，
  避免对已移除内容继续做通过断言。

## 回退结果

- 当前 **1243 行 / 1243 卷**，粉笔申论 **38** 份（不变）；
- 全库可识别缺答案位置：**451 → 475**（回加 24 处）；
- 全库扫描 `原创示范作答`/`AI辅助编写`/`模型生成` 等标签：**0 份**（本次之前为 9 份）。

## 回归与门禁（本地真实结果）

```bash
cd tools
python3 -m unittest tests.test_remove_legacy_ai -v
python3 -m unittest tests.test_remove_ai_content tests.test_remove_legacy_ai \
  tests.test_shenlun tests.test_export_shenlun tests.test_gates \
  tests.test_round4_answers tests.test_round5_bulk
```

- **91 项测试 PASS**（7 项本轮回退 + 6 项 PR#120 清理 + 78 项既有）；
- 9 行与 `cloud_quality.scan()` 对比 **0 差异**；manifest 全部 1243 行 sha256/bytes 与文件一致；
- `verify_repair_receipts.py` 在 sourced 旧计数基线上 FAIL（main 上同样存在）；
- `cloud_quality.py --check` 在干净 main 上即 FAIL（#118 后既有）；
- GitHub Actions 0 步骤（billing），不声称 CI 通过。

## 证据

`reports/REMOVED-AI-CONTENT-LEGACY-20261022.json`：逐卷 before/after SHA、body SHA、
删除题号、保留第三方答案 digest、manifest 前后字段；不含任何题文/材料正文。
