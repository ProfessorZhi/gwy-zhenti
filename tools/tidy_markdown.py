#!/usr/bin/env python3
"""试卷排版整理：只改 Markdown 标记，不改任何文字。

1. 正文中的半角 `~` 写成 `\\~`。GitHub 会把一行里成对的 `~` 当作删除线，
   「1~2月」「公元前140年~前88年」这类区间会被划掉；转义后照常显示为「~」。
   文件头、代码块、链接与图片地址不动。
2. 行测「题型与作答说明」中「模块名 / （N题） / 说明」三行合为一行列表项：
   `- **政治理论**（20题） 根据题目要求……`。

每个文件写入前校验：去掉空白、`**`、行首列表符号与转义反斜杠后，改前改后全文逐字相同，否则不写。

用法：
    python3 -I tools/tidy_markdown.py            # 只报告
    python3 -I tools/tidy_markdown.py --write    # 写入
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TILDE = re.compile(r'(?<!\\)~')
LINK = re.compile(r'\]\([^)]*\)|</?[A-Za-z][^<>]*>')
SECTION = re.compile(r'(## 题型与作答说明\n\n)(.*?)(?=\n## |\Z)', re.S)
BLOCK = re.compile(r'(?m)^([^\n#<>|（(\-*][^\n]{0,15})\n\n([（(]\d+\s*题[）)])\n\n([^\n#<]+)$')


def split_frontmatter(text):
    if text.startswith('---\n'):
        end = text.index('\n---\n', 4) + 5
        return text[:end], text[end:]
    return '', text


def escape_tildes(body):
    out, fence = [], False
    for line in body.split('\n'):
        if line.lstrip().startswith(('```', '~~~')):
            fence = not fence
        if fence or '~' not in line:
            out.append(line)
            continue
        # 链接、图片地址与 HTML 标签内部不转义
        parts, last = [], 0
        for m in LINK.finditer(line):
            parts.append(TILDE.sub(r'\\~', line[last:m.start()]))
            parts.append(m.group(0))
            last = m.end()
        parts.append(TILDE.sub(r'\\~', line[last:]))
        out.append(''.join(parts))
    return '\n'.join(out)


def compact_sections(body):
    def one(m):
        lines = BLOCK.sub(lambda b: f'- **{b.group(1).strip()}**{b.group(2)} {b.group(3).strip()}', m.group(2))
        # 列表项之间不留空行
        lines = re.sub(r'(?m)^(- \*\*[^\n]+)\n\n(?=- \*\*)', r'\1\n', lines)
        return m.group(1) + lines
    return SECTION.sub(one, body)


def plain(text):
    _, body = split_frontmatter(text)
    body = body.replace('\\~', '~').replace('**', '')
    body = re.sub(r'(?m)^\s*- ', '', body)
    return re.sub(r'\s+', '', body)


def tidy(text):
    head, body = split_frontmatter(text)
    return head + compact_sections(escape_tildes(body))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    rows = [json.loads(line) for line in (ROOT / 'catalog/manifest.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    changed, bad = [], []
    for r in rows:
        path = ROOT / r['path']
        old = path.read_text(encoding='utf-8')
        new = tidy(old)
        if new == old:
            continue
        if plain(new) != plain(old):
            bad.append(r['path'])
            continue
        changed.append(r['path'])
        if args.write:
            path.write_text(new, encoding='utf-8')
    print(f"{'写入' if args.write else '将修改'} {len(changed)} 份；校验未通过 {len(bad)} 份")
    for p in bad[:20]:
        print('  未通过：', p)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
