# gwy-zhenti 管线

两段式：**段一** 产清单（不碰正文），**段二** 逐卷导出。

```bash
cd D:/projects/gwy-zhenti/tools
export PYTHONIOENCODING=utf-8

# 段一：把上游克隆汇总成清单
python -X utf8 -m gwyzhenti.cli catalog \
  --upstream "D:/projects/_gwy-upstream" \
  --out "../work/catalog"

# 跑测试
python -X utf8 -m unittest discover -s tests -v
```

- 上游只读；产物全在 `../work/`（已 gitignore）。
- 加新源 = 在 `gwyzhenti/sources/` 写一个 adapter + 在 `sources/__init__.py` 注册一行。
