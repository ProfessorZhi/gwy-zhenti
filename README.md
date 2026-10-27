# R3 媒体 / 表格 / 公式 可读质量工具包

只读扫描 + 只产出**建议**。任何工具都不会修改 `gwy-zhenti` 仓库；唯一的写盘目标是本目录。

## 边界（硬约束）

- 读：`/home/fjd/ci-repair/gwy-zhenti`（活跃主控，**不改 checkout、不 commit**）、
  `/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi`（源侧证据，只读）、
  Q6 独立报告目录（只复核 SHA，不重扫全库图片）。
- 写：仅本目录。`patches/` 里是待人工审核的 diff，**不会**被任何命令应用到主控。
- 不打开粉笔站点、不重新采集、不删除任何原图、不把统计图转成文字、不改题干数据。
- **不做字形判断**：不猜图片里画的是 `∨` 还是 `V`。凡是只能靠看图才能定的，一律标
  `UNKNOWN` / `IMAGE_ONLY`，交给人或源 snapshot 文本。

## 工具

| 文件 | 作用 |
|---|---|
| `tools/r3lib.py` | GFM 表格解析、单元格分类、题号/单元定位、路径解析。无副作用。 |
| `tools/r3_tablescan.py` | **表头语义检测器**：找“数据行被当表头”的表；多级表头归因；生成只改结构的补丁并验证。 |
| `tools/r3_symbolscan.py` | 公式/比较符记法风险扫描，按 **卷 × 单元** 分桶。 |
| `tools/r3_assets.py` | 源附件 ↔ 仓库相对路径**双侧**校验（仓库→源、源→仓库）。 |
| `tools/r3_batch.py` | 把上面三份产物联结成逐卷 QA 表（不引入新推断）。 |

## 用法

```bash
# 1. 表头语义（写报告 + 生成补丁）
python3 -I tools/r3_tablescan.py --repo /home/fjd/ci-repair/gwy-zhenti \
    --out out/tablescan.json --patch patches/table-header-semantics.diff

# 2. 验证补丁确实是“只改结构”：会真的把补丁套上去再比对单元格
python3 -I tools/r3_tablescan.py --repo /home/fjd/ci-repair/gwy-zhenti \
    --verify-patch patches/table-header-semantics.diff
# exit 0 = 通过；非 0 = 拒绝

# 3. 符号风险（复用 Q6 已算好的 SHA 名单，不重扫图片）
python3 -I tools/r3_symbolscan.py --repo /home/fjd/ci-repair/gwy-zhenti \
    --manifest /home/fjd/ci-repair/gwy-zhenti/catalog/manifest.jsonl \
    --pixels <Q6>/q6-pixels.json --out out/symbolscan.json

# 4. 双侧资产校验
python3 -I tools/r3_assets.py --repo /home/fjd/ci-repair/gwy-zhenti \
    --pairs <Q6>/q6-pairs.json --pixels <Q6>/q6-pixels.json \
    --manifest /home/fjd/ci-repair/gwy-zhenti/catalog/manifest.jsonl --out out/assets-all.json

# 5. 逐卷 QA
python3 -I tools/r3_batch.py --repo /home/fjd/ci-repair/gwy-zhenti \
    --tables out/tablescan.json --symbols out/symbolscan.json \
    --assets out/assets-qa.json --papers out/qa-papers.txt \
    --out out/qa-batch.json --out-md reports/QA-BATCH-30.md
```

## 测试

```bash
python3 -I -m unittest discover -s tests -v
```

49 条用例，全部**合成**（不依赖仓库、不联网）。仓库每天在动，测试因此编码**规则**而不是快照。
其中包含一条“反向”用例：把分隔行放错位置的补丁必须被 `verify_patch` 判为失败。

## 设计要点（踩过的坑）

1. **时间轴不是数据。** `2018|2019|2020` 与一行数据的单元格种类相同；必须在**行级**用年份域
   （1900–2100）和单调性判定，否则 66 张正常表被误报。
2. **序号轴不是数据。** `1|2|3|4|5|6` 压在文字行上是座位号表头；但 `1|2|3` 后面接 `4|5|6`
   是九宫格首行。判据是“数字是否继续数下去”。
3. **空角格是表头特征。** `| | 45元 | 75元 |` 是正常表头；被误用的数据行通常是满的。
4. **`数字+中文` 用闭集单位表。** 开放写法会吞掉 `2次逻辑` 这类真列名。
5. **单字母是变量还是列键。** `a|4|8|m` 是数阵数据；`A|B|C|D` 是列键。靠“同行有没有真数字”区分。
6. **多级表头只在“相邻重复标签”时才算。** 否则会把“带行标签列的正常表”全部误判。
7. **补丁的顺序必须严格是** `空表头 → 分隔行 → 原表头作为首数据行`。
   把降级行放在分隔行**上面**会让表被静默摧毁（空行变孤行、数据行又被提升为表头），
   而单元格多重集**看起来没变**——所以验证必须同时断言“表数不变、行数 +1”。
8. **验证不能空转。** 早期版本只比对 diff 的 `+`/`-` 行，两边都是 0 个单元格却报 `identical`。
   现在会真正套用补丁并报告被比较的单元格数，`non_vacuous` 为假即判失败。

## 产物

| 路径 | 内容 |
|---|---|
| `out/snapshot.json` | 取样时刻的 HEAD / 工作树脏状态 / manifest 卷数 |
| `out/tablescan.json` | 全库表头扫描（2,658 张表） |
| `out/symbolscan.json` | 符号风险（按卷×单元分桶） |
| `out/assets-all.json` / `out/assets-qa.json` | 双侧资产校验（全库 / 30 卷） |
| `out/qa-batch.json` / `reports/QA-BATCH-30.md` | 30 卷逐卷 QA + 逐表原图 SHA |
| `patches/table-header-semantics.diff` | 23 张表的**待审**补丁（只改结构） |
| `reports/R3-MEDIA-LAYOUT-REPORT.md` | 主报告（含分母口径） |
| `reports/WORK-RECEIPT.md` | 给 R0 的集成回执 |
