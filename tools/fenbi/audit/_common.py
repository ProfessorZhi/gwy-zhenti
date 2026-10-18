"""Shared parsing helpers for the missing-25 evidence audit.

Pure standard library, no network, no credentials. Every path this module
touches is derived from the caller-supplied repository root.
"""

import os
import re

# A question heading in this repository's 行测 markdown, at any level, e.g.
#   ## 第 42 题　<sub>qid 13319300 · 逻辑填空</sub>
#   ### 第 46 题　<sub>qid 13319302 · 逻辑填空</sub>
HEAD_RE = re.compile(r"^#{1,6}\s*第\s*(\d+)\s*题")

# Shared-material blocks ("## 材料 1（第46—50题共用）") are boundaries, not
# question bodies. Treating them as boundaries stops a question block from
# absorbing an adjacent material group.
MATERIAL_RE = re.compile(r"^#{1,6}\s*材料")

# Boilerplate that marks an unresolvable collection placeholder rather than a
# real stem. Kept short on purpose: these identify a slot's state, they are not
# reproductions of any source's question text.
PLACEHOLDER_MARKERS = {
    "collection_pending": r"题目正在全力以赴征集|正在搜集中",
    "not_collected": r"本题暂无收集到|暂无收集到",
    "recollection_missing": r"网友未回忆起",
    "stub_options": r"正确答案[是为]A",
    "absent_options": r"缺失|暂缺|^\s*A\.\s*缺",
    "grading_stub": r"题目缺失|非客观题，请交卷后查看参考解析估分",
    "bracketed_absent": r"\d+\s*题暂缺|暂缺$",
}

FRONTMATTER_FIELDS = (
    "考试", "地区", "年份", "科目", "卷型", "真题性质", "命题形式",
    "对照题本题量", "实有题数", "缺失原题号", "整卷核验状态", "题号口径",
    "题序对照来源",
)


def default_repo_root():
    """Repository root inferred from this file's location (tools/fenbi/audit/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir))


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_frontmatter(text):
    """Split a markdown file into (frontmatter dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fm[key.strip()] = value.strip().strip('"')
    return fm, text[end + 4:]


def parse_int_list(raw):
    return [int(x) for x in re.findall(r"\d+", raw or "")]


def question_numbers(body):
    """Every question number carrying a heading, in document order."""
    return [int(m.group(1)) for line in body.splitlines()
            if (m := HEAD_RE.match(line))]


def question_blocks(body):
    """Question number -> stem+options text (shared material excluded)."""
    blocks, current, number = {}, [], None
    for line in body.splitlines():
        if MATERIAL_RE.match(line):
            if number is not None:
                blocks[number] = "\n".join(current).strip()
            current, number = [], None
            continue
        m = HEAD_RE.match(line)
        if m:
            if number is not None:
                blocks[number] = "\n".join(current).strip()
            number, current = int(m.group(1)), [line]
        elif number is not None:
            current.append(line)
    if number is not None:
        blocks[number] = "\n".join(current).strip()
    return blocks


def fold_for_compare(block_text):
    """Fold a block to a comparison key: drop the heading, option markers, whitespace.

    Used only to decide whether two blocks are the same text. Never used to
    rewrite content.
    """
    body = "\n".join(l for l in block_text.splitlines() if not HEAD_RE.match(l))
    body = re.sub(r"[-\*]\s*\*\*[A-D]\*\*[\.、]?", "", body)
    return re.sub(r"\s+", "", body)


def detect_placeholders(text):
    """Names of placeholder markers found in a chunk of text."""
    return [name for name, pattern in PLACEHOLDER_MARKERS.items()
            if re.search(pattern, text, re.M)]
