# -*- coding: utf-8 -*-
"""上游 Markdown 的读取原语。只解析，不改写。"""
import re

FM_LINE = re.compile(r'^([^\s:：]+):\s*"(.*)"\s*$')
QHEAD = re.compile(r'^#{2,4}\s*第\s*(\d+)\s*题')
ANS = re.compile(r'^\*\*答案\*\*：\s*([A-Za-z])')
ANS_ANY = re.compile(r'^\*\*答案\*\*：')
IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')
LEAK = re.compile(r'[\u3000\s]*✅')
OPTION = re.compile(r'^- \*\*([A-Za-z])\*\*\.')


def read_frontmatter(text):
    """取文件头 YAML 里的 `键: "值"`。不做完整 YAML 解析（源固定 7 键）。"""
    out = {}
    for ln in text.split("\n"):
        if ln.strip() == "---" and out:
            break
        m = FM_LINE.match(ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def count_questions(text):
    return sum(1 for ln in text.split("\n") if QHEAD.match(ln))


def iter_images(text):
    """→ [(类型, 相对路径)]。类型由路径段判定。"""
    out = []
    for ln in text.split("\n"):
        for src in IMG.findall(ln):
            if "/题目图/" in src:
                out.append(("题目图", src))
            elif "/公式图/" in src:
                out.append(("公式图", src))
    return out


def split_question_blocks(text):
    """→ (前导行, [题块行列表])。题块 = 从 `第 N 题` 标题到下一题标题（或文末）。"""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if QHEAD.match(ln)]
    if not starts:
        return lines, []
    bounds = starts + [len(lines)]
    blocks = [lines[a:b] for a, b in zip(starts, bounds[1:])]
    return lines[:starts[0]], blocks


def split_answer(block):
    """→ (题干行, 答案行, 尾行)。

    答案行 = 首个 `**答案**：` 起，到其后**第一个** `---` 分隔线（含）。
    尾行 = 该分隔线之后的内容（例如下一段 `## 材料 N`），必须回正文，不能算答案。
    尾随空行不计入尾行（题块之间的空行是排版噪声，不是内容）。
    无答案标记时 → (block, [], [])。
    """
    start = None
    for i, ln in enumerate(block):
        if ANS_ANY.match(ln):
            start = i
            break
    if start is None:
        return block, [], []
    end = None
    for k in range(start, len(block)):
        if block[k].strip() == "---":
            end = k
            break
    if end is None:
        return block, [], []
    tail = block[end + 1:]
    while tail and not tail[-1].strip():
        tail.pop()
    return block[:start], block[start:end + 1], tail


def strip_leak(lines):
    """剥掉选项行尾的 `✅`（及其前面的全角空格）。"""
    return [LEAK.sub("", ln) if "✅" in ln else ln for ln in lines]


def correct_option(block):
    """从 `**答案**：X` 取字母；取不到返回 None。"""
    for ln in block:
        m = ANS.match(ln)
        if m:
            return m.group(1).upper()
    return None
