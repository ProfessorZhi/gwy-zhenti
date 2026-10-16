# tools/fenbi/assetsqa — 素材/公式/视觉一致性 独立审计

只读、离线、**无凭据**的素材审计工具。用于核对粉笔采集包（handoff）与本仓库图片/题号之间的一致性。

## 脚本

| 文件 | 作用 |
| --- | --- |
| `visual_consistency_audit.py` | 全卷审计：图像字节可用性、自检回执强度、源 URL 策略、**真实解码**、声明尺寸 vs 真实尺寸、handoff↔仓库逐图连接、内容分类、题号跨号、跨卷同图 |
| `backfill_provenance.py` | 定向溯源：江苏2025C Q81/Q85（A 类图片树）、广东2020县级 69–75、江苏2024A 76/96/110/111 |
| `test_visual_consistency_audit.py` | 单测（`unittest`；本机**无 pytest**） |

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
