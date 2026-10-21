# 申论本地档案 publish-preflight（metadata-only）

- 生成时间：2026-10-21T16:52:26.578Z
- 档案根目录：`/home/fjd/s7-shenlun-archive-20261022`
- catalog/index.jsonl SHA256：`4a9dd1ab730b984c45efffda037a1f28e7b2039f8ca85b5a52374d177e1b5259`
- 快照稳定：是
- 卷数：56（只统计扫描期间索引与卷文件未变化的稳定快照；构建中的短暂目录变化不计入）
- 口径：技术完整性（本地可用性）与第三方版权/再分发权利是两个独立门禁；本报告不改变任何 rights 标记。
- main 重叠是按“地区+年份+卷型+题数”给出的可解释候选（archive 无 main 的行号/标题主键），唯一候选不等于版权或内容同一性的最终认证。

## 门禁汇总

| technical | 卷数 | publication | 卷数 |
| --- | ---: | --- | ---: |
| PASS | 30 | BLOCKED | 56 |
| FAIL | 26 | ELIGIBLE | 0 |
| SKIP | 0 | POLICY_VIOLATION | 0 |

## 按地区

| 地区 | 卷数 | PASS | FAIL | SKIP | BLOCKED |
| --- | ---: | ---: | ---: | ---: | ---: |
| 北京 | 1 | 1 | 0 | 0 | 1 |
| 广东 | 5 | 5 | 0 | 0 | 5 |
| 国考 | 13 | 3 | 10 | 0 | 13 |
| 上海 | 1 | 1 | 0 | 0 | 1 |
| 浙江 | 36 | 20 | 16 | 0 | 36 |

## 按年份

| 年份 | 卷数 | PASS | FAIL | SKIP |
| --- | ---: | ---: | ---: | ---: |
| 2008 | 1 | 1 | 0 | 0 |
| 2009 | 1 | 1 | 0 | 0 |
| 2010 | 1 | 1 | 0 | 0 |
| 2011 | 1 | 1 | 0 | 0 |
| 2012 | 1 | 1 | 0 | 0 |
| 2013 | 2 | 2 | 0 | 0 |
| 2014 | 2 | 2 | 0 | 0 |
| 2015 | 2 | 2 | 0 | 0 |
| 2016 | 2 | 2 | 0 | 0 |
| 2017 | 2 | 2 | 0 | 0 |
| 2018 | 2 | 2 | 0 | 0 |
| 2019 | 2 | 0 | 2 | 0 |
| 2020 | 2 | 2 | 0 | 0 |
| 2021 | 3 | 1 | 2 | 0 |
| 2022 | 1 | 0 | 1 | 0 |
| 2023 | 6 | 0 | 6 | 0 |
| 2024 | 6 | 0 | 6 | 0 |
| 2025 | 8 | 2 | 6 | 0 |
| 2026 | 11 | 8 | 3 | 0 |

## issue 汇总

| code | severity | 卷数 |
| --- | --- | ---: |
| answer-above-word-maximum | warning | 50 |
| answer-below-word-minimum | warning | 1 |
| answers-incomplete | fatal | 2 |
| explanation-empty | warning | 53 |
| images-missing | fatal | 8 |
| material-pane-gap | fatal | 16 |
| material-ref-unresolved | fatal | 16 |
| material-tab-count-mismatch | warning | 2 |
| question-count-mismatch | fatal | 2 |
| question-number-set-mismatch | fatal | 2 |
| rights-status-missing | warning | 2 |
| rights-status-unexpected | warning | 2 |
| word-limits-unknown | warning | 4 |

## 图片映射

- 引用 171 张，落地 131 张，SHA 校验通过 131 张，缺字节 40 张，孤儿 0 张。
- 含图片卷 40，无图片卷 16。
- 离线可复制修复 0 张；不可修复 8 卷 / 40 张（本地无 SHA 元数据，禁止按顺序或尺寸猜图）。

## 与 main catalog 的重叠

- 可唯一匹配 main：32 卷；候选不唯一：13 卷；无候选：11 卷。
- 唯一匹配且命中 #110/#112/#113 已补答案路径：1 卷（sourceId：6308806）；仅作为候选命中：3 卷。

## 离线修复可行性

- missing-bytes-no-local-source: 8
- not-needed: 30
- recapture-required: 18

`recapture-required` 表示现有本地 capture 没有更完整的页签/答案/题号，必须由 S4 重新采集；`missing-bytes-no-local-source` 表示缺图且本地没有任何同 SHA 字节，不能用顺序或尺寸猜图。

## 失败/跳过卷（仅元数据）

| sourceId | 地区 | 年份 | 卷型 | technical | fatal codes |
| --- | --- | ---: | --- | --- | --- |
| 113619 | 浙江 | 2021 | b | FAIL | material-pane-gap, material-ref-unresolved |
| 113622 | 浙江 | 2021 | c | FAIL | material-pane-gap, material-ref-unresolved |
| 179084 | 国考 | 2022 |  | FAIL | question-count-mismatch, question-number-set-mismatch, answers-incomplete |
| 199745 | 国考 | 2023 | xingzheng | FAIL | images-missing |
| 203837 | 国考 | 2023 | unknown | FAIL | images-missing |
| 204222 | 国考 | 2023 | unknown | FAIL | images-missing |
| 208888 | 浙江 | 2023 | c | FAIL | material-pane-gap, material-ref-unresolved |
| 209053 | 浙江 | 2023 | b | FAIL | material-pane-gap, material-ref-unresolved |
| 209063 | 浙江 | 2023 | a | FAIL | material-pane-gap, material-ref-unresolved |
| 222978 | 国考 | 2024 | xingzheng | FAIL | images-missing |
| 4508683 | 浙江 | 2024 | a | FAIL | material-pane-gap, material-ref-unresolved |
| 4508685 | 浙江 | 2024 | b | FAIL | material-pane-gap, material-ref-unresolved |
| 4508686 | 浙江 | 2024 | c | FAIL | material-pane-gap, material-ref-unresolved |
| 4961511 | 国考 | 2024 | unknown | FAIL | images-missing |
| 5254748 | 浙江 | 2026 | a | FAIL | material-pane-gap, material-ref-unresolved |
| 5254772 | 浙江 | 2026 | c | FAIL | material-pane-gap, material-ref-unresolved |
| 5758153 | 浙江 | 2026 | b | FAIL | material-pane-gap, material-ref-unresolved |
| 5855987 | 浙江 | 2025 | b | FAIL | material-pane-gap, material-ref-unresolved |
| 6106549 | 国考 | 2025 | unknown | FAIL | images-missing |
| 6700406 | 国考 | 2024 |  | FAIL | question-count-mismatch, question-number-set-mismatch, answers-incomplete |
| 6758563 | 浙江 | 2025 | a | FAIL | material-pane-gap, material-ref-unresolved |
| 7372606 | 浙江 | 2025 | c | FAIL | material-pane-gap, material-ref-unresolved |
| 7601181 | 国考 | 2025 | unknown | FAIL | images-missing |
| 7900381 | 国考 | 2025 | xingzheng | FAIL | images-missing |
| 89920 | 浙江 | 2019 | a | FAIL | material-pane-gap, material-ref-unresolved |
| 89921 | 浙江 | 2019 | b | FAIL | material-pane-gap, material-ref-unresolved |

## 本次变更范围

- 只新增离线 preflight 代码、合成测试和 metadata-only 报告；未改动任何原题、材料、答案、图片字节或 rights 标记。
- 新增独立参考答案 0 处、新增解析 0 处；56 卷 archiveStatus 仍为 PARTIAL，archiveComplete=0。
- 未改 catalog/manifest.jsonl；后续若有内容变更，使用 manifest 行级 patch 工具，不全量重写。

## 结论与边界

- 技术 PASS 30 / FAIL 26 / SKIP 0；publication BLOCKED 56，ELIGIBLE 0。
- 技术 PASS 允许 explanation-empty、answer-above-word-maximum 等 warning 存在；这些是内容质量/解析缺口，不是结构损坏。
- rightsStatus 分布：unverified=54，missing=2；cloudStorageBlocked=true 56 卷；cleared 0 卷。
- 没有任何卷因为本报告而变为可发布；缺失 rights 字段的卷按 BLOCKED 处理，而不是补成 cleared。
- 本报告只含计数、哈希、路径与 issue code，不含题干、材料、答案、解析或标题正文。
