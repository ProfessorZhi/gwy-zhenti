# -*- coding: utf-8 -*-
"""段二：单卷合并 + 五项机械变换。除这五项外逐字符保真。

五项变换：
  1 合并（按 MODULE_ORDER 拼接各模块）
  2 题号重建（模块内序号 → 连续原卷号）
  3 答案去泄露（剥 ✅；答案与解析移到卷末 <details>）
  4 图片重写（相对路径按输出深度计算）
  5 frontmatter 契约
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from . import mdread
from .model import PaperKey

MODULE_ORDER = (
    "政治理论", "常识判断", "言语理解与表达",
    "数量关系", "判断推理", "资料分析",
)
IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')
QNUM = re.compile(r'^(#{2,4})\s*第\s*(\d+)\s*题(.*)$')


@dataclass
class RenderedPaper:
    body: str = ""
    images_used: list = field(default_factory=list)
    n_questions: int = 0
    numbering: str = ""


def _renumber(lines, offset):
    out = []
    for ln in lines:
        m = QNUM.match(ln)
        out.append("%s 第 %d 题%s" % (m.group(1), int(m.group(2)) + offset, m.group(3))
                   if m else ln)
    return out


def _rewrite_images(lines, image_map):
    used = []

    def sub(m):
        src = m.group(1)
        if src in image_map:
            used.append(image_map[src])
            return m.group(0).replace(src, image_map[src])
        return m.group(0)

    return [IMG.sub(sub, ln) for ln in lines], used


def _frontmatter(key, nature, form, sources, numbering):
    lines = [
        "---",
        '考试: "%s"' % key.level,
        '地区: "%s"' % (key.region or key.level),
        '年份: "%s"' % key.year,
        '科目: "%s"' % key.subject,
        '卷型: "%s"' % key.ptype,
        '真题性质: "%s"' % nature,
        '命题形式: "%s"' % form,
        '来源: [%s]' % ", ".join('"%s"' % s for s in sources),
        '题号口径: "%s"' % numbering,
        '校验状态: "机器校验（并卷/题号/图片/去泄露/G1–G5）；未人工通读"',
        "---",
    ]
    return lines


def render_paper(parts, key, *, nature, form, sources, modules, image_map):
    """parts 必须已按 MODULE_ORDER 排好；modules 与之等长，给出模块名。"""
    # 1) frontmatter 契约（先按「模块内序号」估，若模块齐则用「原卷重建」）
    standard = [m for m in MODULE_ORDER if m in set(modules)]
    numbering = "原卷重建" if standard == list(modules) else "模块内序号"

    blocks, answers, used = [], [], []
    offset = 0
    for part, module in zip(parts, modules):
        pre, qblocks = mdread.split_question_blocks(part)
        # 每个部分的前导正文（含 `## 材料 N` 与材料图）按**原位**进正文 ——
        # 只取第一部分会把后续部分的材料整段丢掉（资料分析作第二模块时必现）。
        seg = mdread.strip_leak(_body_head(pre))
        if seg:
            if blocks:
                blocks += [""]
            blocks += seg
        for b in qblocks:
            stem, ans, tail = mdread.split_answer(b)
            blocks += _renumber(mdread.strip_leak(stem), offset)
            if tail:
                blocks += mdread.strip_leak(tail)
            if ans:
                answers.append((int(mdread.QHEAD.match(b[0]).group(1)) + offset,
                                mdread.strip_leak(ans)))
        offset += len(qblocks)

    # 4) 图片重写（在正文与答案里都要做）
    flat, u1 = _rewrite_images(blocks, image_map)
    used.extend(u1)
    ans_lines = []
    for num, al in answers:
        al, u2 = _rewrite_images(al, image_map)
        used.extend(u2)
        ans_lines.append((num, al))

    body = _frontmatter(key, nature, form, sources, numbering) + [""]
    body += ["# %s" % key_label(key), ""]
    body += ["> %s · %d 题 · %s %s" % (key.subject, offset, key.region or key.level, key.year), ""]
    body += flat
    body += ["", "## 答案与解析", ""]
    for num, al in ans_lines:
        body += ["<details>", "<summary>第 %d 题</summary>" % num, ""]
        body += al
        body += ["</details>", ""]

    # 合并相邻空行，去首尾空白，行尾统一 LF
    text = "\n".join(body)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    return RenderedPaper(text, used, offset, numbering)


def key_label(key):
    if key.level == "国考":
        return "%s %s %s（%s）" % (key.year, "国家公务员录用考试", key.subject, key.ptype)
    return "%s %s省公务员录用考试 %s（%s）" % (key.year, key.region, key.subject, key.ptype)


def _body_head(pre):
    """取源前导块里除 frontmatter / `---` / 一级标题 / 引言（`>` 行）之外的**正文**行。"""
    out, seen_h1 = [], False
    for ln in pre:
        if ln.strip() == "---":
            continue
        if mdread.FM_LINE.match(ln):
            continue
        if ln.startswith("# ") and not seen_h1:
            seen_h1 = True
            continue
        if ln.startswith("> "):
            continue
        out.append(ln)
    while out and not out[0].strip():
        out.pop(0)
    return out


LEAK_SUB = re.compile(r"[　\s]*✅")
QNUM_ANY = re.compile(r"^(#{2,4})\s*第\s*\d+\s*题(.*)$")
SRC_ATTR = re.compile(r'(src=")(?:[^"]*/)?([^"/]+)(")')
# 我们**声明过**要新增或删除的结构行；G5 在两侧都剔除它们
STRUCTURAL = re.compile(
    r"^\s*(---|#{1,2}\s*答案与解析|<details>|</details>|<summary>.*</summary>)\s*$")
FM_BLOCK = re.compile(r"\A(?:---\n.*?\n---\n)", re.S)


def _strip_declared(text):
    """剔除双方共有的「声明过的结构性差异」：frontmatter 块、一级标题、引言、答案区容器、空行。"""
    text = FM_BLOCK.sub("", text)
    out = []
    for ln in text.split("\n"):
        if not ln.strip():
            continue
        if ln.startswith("# ") or ln.startswith("> "):
            continue
        if STRUCTURAL.match(ln):
            continue
        out.append(ln)
    return out


def _normalize(lines):
    """可比较形态：去 ✅（连前导全角空格）、`第 N 题` 编号抹成 `?`、图片路径只留文件名。"""
    out = []
    for ln in lines:
        ln = LEAK_SUB.sub("", ln)
        ln = QNUM_ANY.sub(lambda m: "%s 第 ? 题%s" % (m.group(1), m.group(2)), ln)
        ln = SRC_ATTR.sub(lambda m: m.group(1) + m.group(2) + m.group(3), ln)
        out.append(ln)
    return out


def diff_report(out_text, src_texts):
    """G5 判据：导出 vs 源，返回 (源里有而导出没有的行, 导出有而源里没有的行)，各为排序后的列表。

    两侧都剔除**声明过的**结构性差异后做逐行多重集比较 —— 即**零内容增删**。
    刻意**不**做「导入导出互为逆变换」：题号重建本就不是逆变换，硬构造逆向只会把判据做脆。
    """
    src_lines = []
    for t in src_texts:
        src_lines += _strip_declared(t)
    cs = Counter(_normalize(src_lines))
    co = Counter(_normalize(_strip_declared(out_text)))
    return sorted((cs - co).elements()), sorted((co - cs).elements())
