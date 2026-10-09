# -*- coding: utf-8 -*-
"""申论源（linfukai186 题级 JSON）读取 + 成卷渲染。

与行测的差别（实测，见 M3 计划「源的真实形态」）：
  * 无「模块」概念 ⇒ 不能走 `render.render_paper`（它按 `zip(parts, modules)` 驱动，申论会零轮空转）。
  * 每题自带 `s`（该题相关材料子集），**不是**整卷共享的给定资料 ⇒ **按题原样排**，不做合并（裁定 R-M3-2）。
  * `a` 恒为空串，范文/解析在 `e`。
  * `s` 在源内被硬截断于 6000 字 ⇒ 事实写进 frontmatter 的 `校验状态`，**不往正文加提示行**（裁定 R-M3-5）。
  * 源无卷内题号 ⇒ 按源序编号，口径如实声明。
本模块**只读源、只造字符串**，不写盘。
"""
import io
import json
import os
import re

from . import render
from .model import PaperKey

CATS = ("shengkao-shenlun", "guokao-shenlun")
NUMBERING = "源无卷内题号，按源序编号"
TRUNCATED_LEN = 6000
# 我们**声明过**要新增的结构行 —— 保真判据（G5）在两侧都剔除它们。
STRUCT = re.compile(
    r"^\s*(?:---|#{2,4}\s*第\s*\d+\s*题.*|###\s*(?:给定材料|作答要求)"
    r"|##\s*答案与解析|<details>|</details>|<summary>.*</summary>)\s*$")
FM_BLOCK = re.compile(r"\A(?:---\n.*?\n---\n)", re.S)


def load_source(uproot):
    """→ {卷标识: [题, ...]}，同时扫 `shengkao-shenlun` 与 `guokao-shenlun`。

    目录不存在 ⇒ 跳过（不抛）。同一年两文件不冲突（题在各自类目的 `y<年>.json` 里）。
    """
    out = {}
    for cat in CATS:
        d = os.path.join(uproot, "data", cat)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not (fn.startswith("y") and fn.endswith(".json")):
                continue
            with io.open(os.path.join(d, fn), encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for title, qs in data.items():
                    if isinstance(qs, list):
                        out[title] = qs
    return out


def titles_of(row):
    """该卷在 linfukai186 源里的卷名（保序）。空 = 该源没有此卷。"""
    return list(row.get("titles", {}).get("linfukai186", []))


def questions_for_titles(src, titles):
    """按 titles 顺序拼接各卷名的题；标题在源里找不到 ⇒ 跳过该标题（不抛）。"""
    out = []
    for t in titles:
        qs = src.get(t)
        if isinstance(qs, list):
            out.extend(qs)
    return out


def _lines(v):
    return (v or "").split("\n")


def render_paper(questions, key, *, nature, form, sources):
    """把题列表渲染成一卷 Markdown。逐字节保真的只有材料的文本行本身（§6 五项之外零改写）。"""
    n_trunc = sum(1 for q in questions if len(q.get("s") or "") >= TRUNCATED_LEN)
    status = ("机器校验（并卷/题号/去泄露/G1–G5）；未人工通读"
              "；材料截断 %d 题（源内硬截断于 %d 字）" % (n_trunc, TRUNCATED_LEN))
    head = render._frontmatter(key, nature, form, sources, NUMBERING)
    head = [ln if not ln.startswith('校验状态:') else '校验状态: "%s"' % status for ln in head]

    body = head + [""]
    body += ["# %s" % render.key_label(key), ""]
    body += ["> %s · %d 题 · %s %s" % (key.subject, len(questions),
                                     key.region or key.level, key.year), ""]
    for i, q in enumerate(questions, 1):
        t = (q.get("t") or "").strip()
        body += ["## 第 %d 题%s" % (i, "（%s）" % t if t else ""), ""]
        s = q.get("s") or ""
        if s:
            body += ["### 给定材料", ""] + _lines(s) + [""]
        body += ["### 作答要求", ""] + _lines(q.get("q")) + [""]
    body += ["## 答案与解析", ""]
    for i, q in enumerate(questions, 1):
        body += ["<details>", "<summary>第 %d 题</summary>" % i, ""]
        for f in ("a", "e"):
            v = q.get(f) or ""
            if v:
                body += _lines(v) + [""]
        body += ["</details>", ""]
    text = "\n".join(body)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    return render.RenderedPaper(text, [], len(questions), NUMBERING)


def source_lines(questions):
    """保真判据的**源侧**行：只有 s/q/a/e 的文本行（空字段不计）。"""
    out = []
    for q in questions:
        for f in ("s", "q", "a", "e"):
            v = q.get(f) or ""
            if v:
                out += _lines(v)
    return out


def strip_structure(text):
    """保真判据的**导出侧**行：剔 frontmatter 块、H1、引言、我们声明的结构行、空行。"""
    text = FM_BLOCK.sub("", text)
    out = []
    for ln in text.split("\n"):
        if not ln.strip() or ln.startswith("# ") or ln.startswith("> "):
            continue
        if STRUCT.match(ln):
            continue
        out.append(ln)
    return out
