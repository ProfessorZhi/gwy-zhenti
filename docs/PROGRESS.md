# 总进度

[← 返回首页](../README.md) · [文档](README.md)

<!-- 由 tools/cloud_quality.py --build 生成，勿手改 -->

本页只给当前机器统计和现行入口。缺卷与局部缺口以 [缺口总账](GAP-STATUS.md) 为准；各轮补录与修复的过程记录见 [报表索引](../reports/README.md)。

| 指标 | 当前数量 |
| --- | ---: |
| 已收录试卷 | 1,669 |
| 行测 / 申论 | 735 / 934 |
| 独立引用图片 | 19,175 |
| 图片引用次数 | 19,368 |
| 材料尾部截断（现存） | 0 份 / 0 题 |

机器清单指纹：`c9f481b45e0f0413350c3f496989fbdb156df230d45c21e4ec9ee86602ee1ec3`（`reports/QUALITY-SUMMARY.json` 的 `inventory_sha256`，清单或试卷有改动即变化）。

## 现行入口

| 想看 | 去这里 |
| --- | --- |
| 缺卷、缺题 | [缺口总账](GAP-STATUS.md) |
| 分地区、分年份统计 | [收录统计](COVERAGE.md) · [重点地区逐年卷表](COVERAGE-PRIORITY.md) |
| 机器告警明细 | [质量事项](../reports/QUALITY-AUDIT.md) · [质量汇总数据](../reports/QUALITY-SUMMARY.json) |
| 逐卷字节数与 SHA-256 | [逐卷清单](../catalog/manifest.jsonl) |
| 入库与验收标准 | [归档与质量标准](QUALITY-STANDARD.md) |

## 复现

```bash
python3 tools/cloud_quality.py --build --verify-images   # 重写本页与质量汇总
python3 tools/cloud_quality.py --check --verify-images   # 只读核对
```
