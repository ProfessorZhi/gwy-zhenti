# gwy-zhenti 管线

两段式 + 闸门：**段一 `catalog`** 产清单（不碰正文）→ **段二 `export`** 逐卷导出（正文 + 被引用的图片 + manifest）→ **`gate`** 对已导出的树跑 G1–G6 闸门。
三条命令同属一个入口 `python -X utf8 -m gwyzhenti.cli`。

```bash
cd D:/projects/gwy-zhenti/tools
export PYTHONIOENCODING=utf-8

# 段一：把上游克隆汇总成清单
python -X utf8 -m gwyzhenti.cli catalog \
  --upstream "D:/projects/_gwy-upstream" \
  --out "../work/catalog"

# 段二：按清单逐卷导出（--repo 为仓库根；先小样可加 --limit 20 并另指一个目录）
python -X utf8 -m gwyzhenti.cli export \
  --catalog "../work/catalog" \
  --upstream "D:/projects/_gwy-upstream" \
  --repo ".."

# 闸门：对导出的树跑 G1–G6（任一 FAIL 时退出码非 0）
python -X utf8 -m gwyzhenti.cli gate \
  --catalog "../work/catalog" \
  --upstream "D:/projects/_gwy-upstream" \
  --repo ".."

# 跑测试
python -X utf8 -m unittest discover -s tests -v
```

- 上游只读；产物全在 `../work/`（已 gitignore）。
- 加新源 = 在 `gwyzhenti/sources/` 写一个 adapter + 注册到 `sources.ADAPTERS` + **在 `cli._uproots` 里补一条源根**。
  （`cli._uproots` 是**硬编码**的源根映射，新 adapter 若不在其中补一行，其卷**不会进 catalog**。）
