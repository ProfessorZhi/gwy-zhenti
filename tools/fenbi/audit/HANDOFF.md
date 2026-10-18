# Handoff 接口：把采集结果交给离线对账器

`handoff_reconcile.py` 消费一份"候选文档"，与本库逐维度比对并输出差异矩阵。
它**只读本库、只写自己的输出**，不回写题库，也不会推断答案。

## 目录

- [接受两种输入](#接受两种输入)
- [精简投影格式](#精简投影格式)
- [命令行](#命令行)
- [join 策略（重要）](#join-策略重要)
- [输出](#输出)
- [去敏要求](#去敏要求)

## 接受两种输入

| 形态 | 识别方式 | 说明 |
|---|---|---|
| 精简投影 `fenbi-candidate-handoff-v1` | `schema` 字段 | 只要元数据即可，正文可为纯文本 |
| 框架 `document.json` | 无 `schema`，按 `identity`/`questions` 适配 | 由本工具自动转换，`assets` 里的 `sha256` 会被取用 |

框架文档常不带本库路径，这时用 `--paper` 指定。

## 精简投影格式

```json
{
  "schema": "fenbi-candidate-handoff-v1",
  "paper": {
    "label": "江苏2025C类",
    "library_path": "省考/江苏/2025/行测-C类.md",
    "fenbi_source_id": "4189916",
    "captured_at": "2026-10-17T00:00:00Z",
    "binding": "unverified"
  },
  "questions": [
    {
      "source_number": 27,
      "qid": "13319300",
      "stem": "<p>…</p>",
      "options": [{"label": "A", "text": "…"}],
      "material_ids": ["1"],
      "images": ["<sha256>"],
      "answer": null,
      "explanation": null
    }
  ]
}
```

字段说明：

| 字段 | 必需 | 说明 |
|---|---|---|
| `paper.library_path` | 是* | 本库卷路径；`*` 可用 `--paper` 代替 |
| `paper.binding` | 否 | `verified` / `unverified`；缺省按 `unverified` 报告 |
| `source_number` | 是 | **来源端**题号（非本库题号，见下文 join） |
| `qid` | 否 | 只记录；与库内 qid 命名空间不兼容，恒为 `not_compared` |
| `stem` / `options[].text` | 是 | 可为 HTML 或纯文本，比对前统一归一化 |
| `material_ids` | 否 | 该题挂靠的共用材料编号 |
| `images` | 否 | **每个图片的 sha256**（不是数量）。缺哈希则记 `unknown` |
| `answer` / `explanation` | 否 | 来源**确实公布**时才填；`null` 表示未公布 |

完整示例见 `examples/handoff-example.json`（合成内容，仅示意形状）。

## 命令行

```bash
python3 tools/fenbi/audit/handoff_reconcile.py \
    --repo . \
    --handoff <捕获文档.json> \
    [--paper <本库卷路径>] \
    [--join auto|number|sequence] \
    [--out <差异矩阵.json>]
```

## join 策略（重要）

本库**保留原卷题号并留空缺号**（广东2020县级 93 题、最高号 100）。

**实测结论（第三批采集，2026-10-17）**：粉笔该两卷也**采用原卷编号并保留缺号**，
不是 1…N 连续编号。江苏2024A 源 135 / 库 131，源侧多出的正是 76/96/110/111；
广东2020 源 100 / 库 93，源侧多出的正是 69–75。两卷 `偏移 = 0`。
**因此正确做法是按号对接（`--join number`），每题按原号插入，不需重编号。**

> **上限提醒（PR #33 更正）**：上句说的是**题号槽位**，**不是内容**。
> 这些槽位在粉笔处是**未征集占位存根**，没有正文。见
> `reports/FENBI-MISSING11-EVIDENCE-PACK-20261017.md`。
> 对账器已把"占位存根"判为 `unknown`（`source-is-uncollected-placeholder-stub`），
> **不会**判成 `different`——"源侧没内容"与"源侧内容不同"是两回事。

| 策略 | 行为 |
|---|---|
| `number` | 来源题号 == 本库题号。**本场景正确** |
| `sequence` | 按**位置**对齐（第 i 题对第 i 题）。仅当来源是连续编号 1…N 时才正确 |
| `auto`（默认） | 按两侧**真实编号**给两种策略打分，取分高者 |

**危险示例（实测）**：广东卷本库缺 69–75。若误用位置对接，**来源第 69 题会被接到本库第 76 题**——
接点整体后移 7 位，11 项缺题全部错配。

**`auto` 不是免责的。** 分数无法区分"来源用同样编号"与"来源连续但号恰好重合"：
一个连续的 1…93 来源在本库上按号对接会得 86 分，其中后 18 分是错的。
故只要本库存在缺号，输出**必定带 `join.warning`**，内含缺号列表、两种策略得分、
以及"位置对接会把源第 N 题接到库第 M 题"的具体示例。

**采集端请一并报告来源的题号口径**（原号留缺，还是连续 1…N）。这是唯一能消除歧义的证据。

## 输出

```json
{
  "join": {"strategy": "sequence", "reason": "…",
           "unmapped_source_items": [], "library_numbers_not_covered": []},
  "dimension_tally": {
    "stem":   {"same": 130, "different": 0, "unknown": 0, "not_compared": 0},
    "answer": {"same": 0, "different": 0, "unknown": 130, "not_compared": 0}
  },
  "items": [{"library_number": 27, "source_number": 27, "join_basis": "same",
             "dimensions": {"stem": {"status": "same", "reason": "normalized-text-equal"}}}],
  "boundary": ["…"]
}
```

四态与理由串和 `tools/fenbi/src/align.mjs` 一致，可与采集期的 `alignment.json` 并排阅读。

## 去敏要求

提交或共享 handoff 文档时：

- **不要**包含 Cookie、token、手机号、账号资料、VNC 截图或带 token 的 URL。
- 图片只给 **sha256**，不要提交图片原件。
- 若需缩减正文，`answer`/`explanation` 可留 `null`——工具会如实记为 `unknown`，
  不会因为缺字段而误判为 `different`。
- `answer` **只填来源确实公布的**内容；不要把本库答案或同年 A 卷答案回填进来当"来源答案"。
