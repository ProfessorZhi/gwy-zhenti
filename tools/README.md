# 工具

[← 返回首页](../README.md) · [文档](../docs/README.md)

题库的所有统计、导航、检查与采集都由本目录的脚本完成。Python 脚本只依赖标准库（图片像素校验另需 Pillow），建议用 `python3 -I` 运行；采集工具在 [`fenbi/`](fenbi/)，需要 Node.js 22+。

先保存粉笔/华图题目与答案、暂不入库：使用[三步原始归档流程](../docs/workflow/SOURCE-ARCHIVE.md)。执行 `node tools/fenbi/driver/archive-jobs.mjs work/archive-jobs.json --concurrency 2`，程序复用 OpenCLI 登录态，按会话排队并下载图片，结果仅写入 `work/`。

除特别注明外，脚本都以仓库根目录为工作目录，读取 [`catalog/manifest.jsonl`](../catalog/manifest.jsonl) 和试卷文件，**默认只读**；会写文件的脚本都提供 `--check` 或 dry-run 模式。

## 日常维护

入库新卷或修改试卷后，按顺序运行：

```bash
python3 -I tools/refresh_manifest.py --write               # 刷新清单里每卷的字节数与 sha256（--check 只报告）
python3 -I tools/catalog_index.py --out catalog/INDEX.md    # 重新生成全部试卷索引
python3 -I tools/coverage_stats.py --svg docs/assets       # 重新生成逐年柱状图与覆盖热力图
python3 -I tools/repo_readmes.py                           # 重新生成首页横幅、地区入口与各目录导航页
python3 -I tools/gap_report.py                             # 重新生成缺口总账与首页缺口表
python3 tools/cloud_quality.py --check --verify-images     # 结构与图片引用检查（CI 同款）
```

### 统计与导航

| 脚本 | 作用 | 常用参数 |
| --- | --- | --- |
| [`refresh_manifest.py`](refresh_manifest.py) | 按试卷文件刷新清单的 `bytes` 与 `sha256` | — |
| [`catalog_index.py`](catalog_index.py) | 生成 [全部试卷索引](../catalog/INDEX.md) | `--out`、`--check` |
| [`coverage_stats.py`](coverage_stats.py) | 统计地区 × 年份覆盖，生成 `docs/assets` 下两张 SVG | `--svg`、`--json` |
| [`gap_report.py`](gap_report.py) | 生成 [缺口总账](../docs/GAP-STATUS.md) 与首页缺口表：生成槽位台账 `catalog/exam-slots.jsonl`（全部应有试卷，未收录部分维护于 `catalog/uncollected-slots.jsonl`），局部缺口从试卷正文逐题识别 | `--check` |
| [`repo_readmes.py`](repo_readmes.py) | 生成首页横幅、首页地区入口、`国考/`、`省考/` 与各地区 README | `--check` |

### 质量检查

| 脚本 | 作用 |
| --- | --- |
| [`cloud_quality.py`](cloud_quality.py) | 全库结构检查与质量汇总；`--build` 重新生成 [重点地区覆盖表](../docs/COVERAGE-PRIORITY.md)，`--verify-images` 同时核对图片引用 |
| [`gap_content_audit.py`](gap_content_audit.py) | 逐题扫描缺原题、缺选项、缺参考答案，结果见 [缺口总账](../docs/GAP-STATUS.md) |
| [`audit_frontmatter.py`](audit_frontmatter.py) | 试卷结构、命名与槽位审计 |
| [`audit_images.py`](audit_images.py) | 断图、孤儿图、重复图片审计 |
| [`audit_fidelity.py`](audit_fidelity.py) | 逐题比对仓库 Markdown 与本地采集的 `document.json`（需本地采集缓存） |
| [`verify_image_pixels.py`](verify_image_pixels.py) | 完整解码每张被引用图片的像素（需 Pillow） |
| [`paper_identity.py`](paper_identity.py) | 题号连续性与对照题量判断（供其他检查调用） |

### 补录

| 脚本 | 作用 |
| --- | --- |
| [`huatu_fill.py`](huatu_fill.py) | 用华图同卷缓存补入粉笔未收录的题目与材料：整卷锚点与邻题夹逼对齐，默认只出报告，`--write` 写入并更新来源清单；用法见 [任务卡](../docs/workflow/HUATU-FILL.md) |

### 排版

| 脚本 | 作用 |
| --- | --- |
| [`polish_markdown.py`](polish_markdown.py) | 统一卷面：答案随题折叠、卷首概览、统一空行；不改动任何正文字符 |
| [`verify_polish.py`](verify_polish.py) | 与 Git 旧版逐项比对，证明排版只搬位置、没改文字 |
| [`relayout_papers.py`](relayout_papers.py) | 把堆在卷首的材料移到对应题组前；`--check` 只报告 |

## 采集与落盘：[`fenbi/`](fenbi/)

从粉笔题库采集试卷、转换为 Markdown 并落入仓库的完整流水线。安装、登录与风险控制见 [fenbi/README.md](fenbi/README.md)，整体流程见 [架构与流水线](../docs/ARCHITECTURE.md)。

| 位置 | 作用 |
| --- | --- |
| [`fenbi/worker/`](fenbi/worker/) | 单卷流水线：`worker.mjs` 采集新卷；`land-cached.mjs` 把已采集的行测落盘；`land-shenlun.mjs` 把已采集的申论落盘 |
| [`fenbi/driver/`](fenbi/driver/) | 目录巡检、候选生成、申论采集等驱动脚本；`huatu-capture.mjs` 抓取华图解析页整卷数据，见 [任务卡](../docs/workflow/HUATU-FILL.md) |
| [`fenbi/src/`](fenbi/src/) | 解析、校验、渲染、闸门与发布的公共模块 |
| [`fenbi/test/`](fenbi/test/) | 离线测试：`npm ci && node --test test/*.test.mjs` |
| [`fenbi/policy.json`](fenbi/policy.json) | 年份范围、替换规则、缺题处理等入库策略 |

## 早期整编管线：[`gwyzhenti/`](gwyzhenti/)

2026-10 上旬把多个公开上游合并成本库初版所用的 Python 管线，现已不再用于新增试卷，保留以便复现初版。三步同属一个入口：

```bash
cd tools
python -X utf8 -m gwyzhenti.cli catalog --upstream <上游克隆目录> --out ../work/catalog     # 汇总清单
python -X utf8 -m gwyzhenti.cli export  --catalog ../work/catalog --upstream <上游克隆目录> --repo ..   # 逐卷导出
python -X utf8 -m gwyzhenti.cli gate    --catalog ../work/catalog --upstream <上游克隆目录> --repo ..   # G1–G6 闸门
python -X utf8 -m unittest discover -s tests -v                                                  # 测试
```

新增上游需在 `gwyzhenti/sources/` 写适配器、注册到 `sources.ADAPTERS`，并在 `cli._uproots` 补一条源根映射。

## 历史修复脚本

2026-10-11 至 10-22 各轮定向修复用的一次性脚本（`round3_*`～`round6_*`、`r7_*`、`verify_round*`、`paper_integrity_repair`、`essay_transcript_restore` 等）及其输入数据 `data/`，绑定当时的修复回执，只能在当时的语料上复现，已于 2026-11-06 从当前树移除。需要复现时检出 `9c1265ba4` 或更早的提交即可。对应报告仍在 [`reports/`](../reports/README.md)。

## 测试

| 位置 | 内容 | 运行 |
| --- | --- | --- |
| `cloud_quality_test.py` | 质量检查的回归测试 | `cd tools && python -m unittest cloud_quality_test` |
| [`tests/`](tests/) | 早期整编管线的单元测试与冒烟测试 | `cd tools && python -m unittest discover -s tests` |
| [`fenbi/test/`](fenbi/test/) | 采集流水线的离线测试 | `cd tools/fenbi && node --test test/*.test.mjs` |

CI 配置见 [`.github/workflows/`](../.github/workflows/)。
