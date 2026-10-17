# tools/fenbi/assetsqa — 素材/公式/视觉一致性 独立审计

只读、离线、**无凭据**的素材审计工具。用于核对粉笔采集包（handoff）与本仓库图片/题号之间的一致性。

## 脚本

| 文件 | 作用 |
| --- | --- |
| `visual_consistency_audit.py` | 全卷审计：图像字节可用性、自检回执强度、源 URL 策略、**真实解码**、声明尺寸 vs 真实尺寸、handoff↔仓库逐图连接、内容分类、题号跨号、跨卷同图 |
| `backfill_provenance.py` | 定向溯源：江苏2025C Q81/Q85（A 类图片树）、广东2020县级 69–75、江苏2024A 76/96/110/111 |
| `visual_representation_audit.py` | **第 2 轮**：把差异拆成 *表达差异* 与 *真实内容差异*；逐项比选项；占位存根识别；vacuous-stem 匹配；尺寸错误分桶；图形题合成图 XY-cut 可切分性 |
| `tile_pilot.py` | **第 3 轮**：图形题**标签行锚定**的选项槽位定位与切块（确定性切块 + sha256 + 完整性门）；写盘强制在 `work/` |
| `test_visual_consistency_audit.py` | 单测（第 1 轮） |
| `test_visual_representation_audit.py` | 单测（第 2 轮） |
| `paper_question_validator.py` | **第 4 轮**：逐题离线校验器（sourceID/身份/题号/材料/题干与图片 SHA/选项内容/占位/答案未知）；词表区分 `structurally_valid` / `incomplete` / `invalid` |
| `test_tile_pilot.py` | 单测（第 3 轮，27 条，含负例） |
| `test_paper_question_validator.py` | 单测（第 4 轮，29 条，含负例） |

## 用法

```bash
python3 -I visual_consistency_audit.py --repo <repo-root> --handoff <handoff-root> [--out ledger.json]
python3 -I backfill_provenance.py     --repo <repo-root> --handoff <handoff-root> [--out prov.json]

ASSETSQA_REPO=$PWD ASSETSQA_HANDOFF=<handoff-root> \
  python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v
```

需要 `Pillow`（真实解码）。缺 handoff / 图片树时相关用例自动 skip。

## 三条认识论规则

1. **sha256 相等 ⇒ 字节相同**（可靠）。
2. **sha256 不等 ⇏ 像素不同**。handoff **不带图片字节**，本机**无 OCR**，故不做视觉判定——一律 `unknown` / `need_review`。
3. handoff schema **没有 题目→图片 绑定**，故「图形推理选项对应」**无法**在该 handoff 上核验。

## 输出边界

台账为 **no-content**：只有计数、题号、哈希、图片 basename 与尺寸。**不含**题文、选项文、图片字节、源 URL。
**禁止**把第三方图片原文件或受限题文提交进本仓库。

## 注意（踩过的坑）

- **材料块归因**：`材料 N（第X—Y题共用）` 块内的 `<img>` 属于**材料**，不属于其上方的题。按「最近的前一个题头」归因会把材料图错记到上一题，从而产生假的「缺图」结论。`parse_md()` 已按块正确处理，并有回归测试。
- **答案段**：文件末尾 `## 答案与解析` 会再次引用题干里的公式图，造成大量**假的**「卷内重复图」。统计卷内重复时要先截断该段。
- **公式图文件名不是内容寻址**：`formula-<hash>.png` 的 hash **不是**内容 sha256，字节相同的图可能有两个不同文件名。这与 handoff「文件名 == 内容 sha256」的约定**相反**，不要互推。
- **图片 token 会被 tag 剥离吃掉**：先插入 `<IMG>` 再跑 `<[^>]+>` 剥离，token 就没了（图片选项会被读成长度 0）。必须用非标签形状的 token（`\x01IMG\x02`）。
- **占位哨兵不统一**：同一批采集里 `缺失` 与 `暂缺` 并存，征集文案也有两种。只认单一字符串会漏报（江苏2024A Q76 就是 `暂缺`）。
- **`text-vs-image` 不是「内容相同」**：它只说明文字层一致、差一个公式图 token。栅格里的数值**没有 OCR 就无法确认**，一律 `need_review`。
- **图形题没有「选项图对象」**：源侧就是 1 张合成图 + 4 个标签字母选项。要做逐项对应，必须在入库时 XY-cut 切块并绑定；XY-cut 只证明**可切**，不证明**切得对**。
- **裸 XY-cut 的块数不等于「1 题干 + 4 选项」**：常见版式是「图形焊成一条图带 + 下方 4 个**字母标签**」。把标签当选项图会得到假的 5 块（广东 Q41 实测 2 行带：图带 1 段 + 标签 4 段）。
- **第一槽不能用 `[0, 中点]`**：题干在左时会把题干吃进第一槽（实测 284 px vs 其余 ~119 px）。槽宽取**相邻字母中心间距的中位数**，并以字母为中心。
- **选项行带要取「标签行正上方最近」的那条**，不能按墨迹多少取：双行版式（广东 Q42）题干行墨迹更多，按墨迹会取错。
- **切块必须落在 `work/`**：`tile_pilot.py` 的 `--out-dir` 越界直接 `exit 2`；切块可 `rm -rf work/assetsqa-tiles` 完全回滚。
- **A–D 归属不可从几何得出**：字母是印刷字形，本机无 OCR。`A_D_resolved` 恒为 `false`，`binding` 恒为 `need_review`，有测试锁定。
- **`split_options` 必须先剥题头**：`## 第 N 题 <sub>qid…</sub>` 若留在块里，会被当成题干文本，`stemChars` 虚高（国考 Q31 读成 63，实际 32）。
- **重复题号要在 dict 折叠前统计**：题块存进 dict 后重复号已被覆盖，`gaps`/`duplicates` 永远看不到。
- **`sourceId` 没有授权 handoff 就填 `unknown`**：不要把别处报告里的 sourceId 抄成本地事实。
- **`structurally_valid` 不等于 verified**：它只表示本地结构检查通过，不代表官方原卷、也不代表采集侧一致。答案/解析恒为 `unknown`，不得从答案逆推题干。
