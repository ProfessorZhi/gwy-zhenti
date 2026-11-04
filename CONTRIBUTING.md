# 参与贡献

感谢你帮助改进本题库。本文说明勘误、补充来源与提交修改的方式，以及提交说明的统一格式。

## 勘误

发现错字、错题、参考答案或解析有误、题图缺失、卷别标注错误或排版问题，请使用 [勘误模板](https://github.com/ProfessorZhi/gwy-zhenti/issues/new?template=erratum.yml) 新建 issue，写明试卷、题号、问题与依据。勘误经核对后更新，处理结果在原 issue 中回复。

## 补充来源

试卷来源以粉笔为主，华图与网络检索补充。已登记的缺口见 [#148](https://github.com/ProfessorZhi/gwy-zhenti/issues/148)。持有缺失题目、答案或整卷的可靠来源，请在对应的缺口 issue 下提供链接或文件说明。补录只采用同年、同地区、同科目、同卷型且题序一致的来源，并在文件头 `来源清单` 中登记。新发现的应有试卷（缺卷）请登记到 `catalog/uncollected-slots.jsonl`，写明依据。

## 提交修改

1. 修改试卷 Markdown，格式见 [文档格式](docs/SCHEMA.md) 与 [归档与质量标准](docs/QUALITY-STANDARD.md)。
2. 运行 `python3 -I tools/refresh_manifest.py --write` 刷新清单；新增或删除试卷后，再运行 [工具说明](tools/README.md#日常维护) 中的生成命令。
3. 运行 `python3 tools/cloud_quality.py --check --verify-images` 与 `cd tools && python3 -m unittest discover -s tests`，确认通过。
4. 按下文格式填写提交说明，发起 Pull Request。

## 提交说明格式

```
<类型>: <摘要>

- <要点>
- <要点>
```

**类型**（必选其一）：

| 类型 | 用于 |
| --- | --- |
| `content` | 试卷内容：新增、删除、补录、勘误 |
| `style` | 试卷排版，不改变文字内容 |
| `docs` | README 与说明文档 |
| `tools` | 脚本与采集工具 |
| `test` | 测试 |
| `ci` | 持续集成配置 |

**摘要**：

- 中文，不超过 30 字，结尾不加句号；
- 写明做了什么，不写过程和统计细节；
- 示例：`content: 删除广州市考重复卷`、`style: 统一申论答案折叠格式`、`docs: 新增勘误模板`。

**正文**（可选）：用列表写明主要改动、影响的试卷与验证结果。

合并 Pull Request 时使用 Squash 合并，合并后的提交标题与 PR 标题一致，并以上述格式书写。
