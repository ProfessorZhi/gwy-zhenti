"""修复 GitHub 上不渲染的加粗：合并切碎的 `****`，并把加粗边界上的标点移到 `**` 外侧。

CommonMark / GFM 的定界符规则：结束 `**` 若前一字符是标点、后一字符是汉字等非空白非标点，
就不算右侧定界符（开头 `**` 同理），于是 `**参考答案说明：**思路` 会原样显示星号。

做法（逐行）：
1. `****` → 空（相邻两段加粗合并为一段）。
2. 每对 `**…**`：内容尾部的标点在「后一字符既非空白也非标点」时移到结束 `**` 之后；
   内容头部的标点在「前一字符既非空白也非标点」时移到开头 `**` 之前；内容只剩标点则去掉这对 `**`。
3. 只接受同时满足以下条件的改动，否则该行保持原样：
   - 去掉全部 `**` 后文字逐字节不变；
   - 用 CommonMark 渲染后该行不再残留字面 `**`（转义后的遮挡位 `\\*` 除外）。
4. 行测解析里 `10**亿元` 这类遮挡位数的星号先转义为 `\\*`，原样显示，不参与加粗配对。

用法：
    python3 tools/fix_cjk_bold.py            # dry-run，只统计
    python3 tools/fix_cjk_bold.py --write    # 写回
    python3 tools/fix_cjk_bold.py --check    # 有可修行即退出码 1
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
MD = MarkdownIt("commonmark")
CODE = re.compile(r"<code>.*?</code>", re.S)


def is_punct(ch: str) -> bool:
    return unicodedata.category(ch).startswith(("P", "S"))


def is_space(ch: str) -> bool:
    return ch == "" or ch.isspace()


def renders_literal_stars(line: str) -> bool:
    return "**" in CODE.sub("", MD.renderInline(line))


STARS = re.compile(r"(?<!\\)\*+")


def escape_digit_masks(line: str) -> str:
    """行测解析常用 `10**亿元`、`16**/19**` 表示被遮住的位数，这类星号转义为 `\\*`，不当加粗。

    判定：星号紧跟在数字后、该串数字前面不是 `**`、星号后不是反斜杠，且此前已出现的加粗定界符为偶数个
    （即它不可能是某段加粗的结束符）。
    """
    out = []
    pos = 0
    open_delims = 0
    for m in STARS.finditer(line):
        run = m.group(0)
        start = m.start()
        j = start
        while j > 0 and line[j - 1].isdigit():
            j -= 1
        is_mask = (
            j < start
            and not line[:j].endswith("**")
            and not line[m.end():].startswith("\\")
            and open_delims % 2 == 0
        )
        out.append(line[pos:start])
        if is_mask:
            out.append("\\*" * len(run))
        else:
            out.append(run)
            open_delims += len(run) // 2
        pos = m.end()
    out.append(line[pos:])
    return "".join(out)


def plain(s: str) -> str:
    return s.replace("\\*", "*").replace("**", "")


def fix_line(line: str) -> str:
    s = escape_digit_masks(line).replace("****", "")
    parts = s.split("**")
    if len(parts) % 2 == 0:  # 奇数个 `**`，无法配对，不动
        return line
    out = [parts[0]]
    for k in range(1, len(parts), 2):
        before = out[-1]
        inner = parts[k]
        after = parts[k + 1]
        lead = ""
        while inner and is_punct(inner[0]) and not (is_space(before[-1:]) or is_punct(before[-1:])):
            lead += inner[0]
            inner = inner[1:]
        trail = ""
        while inner and is_punct(inner[-1]) and not (is_space(after[:1]) or is_punct(after[:1])):
            trail = inner[-1] + trail
            inner = inner[:-1]
        out[-1] = before + lead
        if inner.strip():
            out.append("**" + inner + "**")
        else:
            out.append(inner)
        out.append(trail + after)
    return "".join(out)


def process(text: str) -> tuple[str, int, int]:
    lines = text.split("\n")
    fixed = still = 0
    in_fence = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence or "**" not in ln:
            continue
        broken = "****" in ln or renders_literal_stars(ln.strip().replace("\\*", ""))
        if not broken:
            continue
        new = fix_line(ln)
        if new != ln and plain(new) == plain(ln) and not renders_literal_stars(new.strip().replace("\\*", "")):
            lines[i] = new
            fixed += 1
        else:
            still += 1
    return "\n".join(lines), fixed, still


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()
    files = [Path(p) for p in args.paths] or sorted(
        p for top in ("国考", "省考") for p in (ROOT / top).rglob("*.md") if p.name != "README.md"
    )
    tot_fixed = tot_still = changed = 0
    for p in files:
        text = p.read_text(encoding="utf-8")
        new, fixed, still = process(text)
        tot_fixed += fixed
        tot_still += still
        if new != text:
            changed += 1
            if args.write:
                p.write_text(new, encoding="utf-8")
        if still:
            print(f"unfixed {still:4d}  {p.relative_to(ROOT)}", file=sys.stderr)
    mode = "write" if args.write else "dry-run"
    print(f"[{mode}] files={len(files)} changed={changed} lines_fixed={tot_fixed} lines_unfixed={tot_still}")
    return 1 if args.check and tot_fixed else 0


if __name__ == "__main__":
    sys.exit(main())
