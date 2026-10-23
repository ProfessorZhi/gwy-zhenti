#!/usr/bin/env python3
"""按卷面规范整理试卷 Markdown：每题后面紧跟可折叠的答案与解析，并统一版式。

做三件事，全部逐卷自检：

1. **答案随题折叠**：把卷末 `## 答案与解析` 里的 `<details>` 块搬到对应 `第 N 题`
   之后，默认折叠；`参考答案` / `解析` 原文逐字搬运，不重写。
2. **卷首概览**：H1 之后插入 `<!-- gwy:overview:start/end -->` 块：地区·年份·科目·卷型、
   题数、图片数、（行测）题型结构表、章节导航。
3. **统一空白**：去行尾空格、连续空行压到 1 行、标题后补空行、文件单个换行结尾。

题干、选项、答案、解析、材料正文与图片路径**一个字符都不改**（搬移除外）。每次写盘
都会自检：题数 / 选项行 / 图片引用 / <details> / <summary> 数量不变，答案块内容多重集
不变，且去掉概览块后与原文仅差空白；任一不符即拒绝写入该文件。

用法：
    python3 -I tools/polish_markdown.py --check                       # 只报告
    python3 -I tools/polish_markdown.py --check --paths a.md,b.md
    python3 -I tools/polish_markdown.py --write --limit 20
    python3 -I tools/polish_markdown.py --write --paths 省考/浙江/2008/行测-统考.md
    python3 -I tools/polish_markdown.py --write --no-interleave        # 保留卷末答案区

退出码：0 正常；1 有文件自检失败；2 参数错误。
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = '<!-- gwy:overview:start -->'
END = '<!-- gwy:overview:end -->'
HEADING = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
Q_HEADING = re.compile(r'^(#{2,3})\s+第\s*(\d+)\s*题(?:\s.*|[（(【].*)?$')
MODULE_COUNT = re.compile(r'^（\s*(\d+)\s*题\s*）$')
OPTION = re.compile(r'^[A-DＡ-Ｄ][.、．]')
IMG_MD = re.compile(r'!\[[^\]]*\]\(')
IMG_HTML = re.compile(r'<img\b', re.I)
MATERIAL_HEADING = re.compile(r'^##\s+给定资料\s+材料\s*([0-9一二三四五六七八九十百]+)\s*[:：]?\s*$')
ANSWER_HEAD = re.compile(r'^##\s+答案与解析(\s*[（(].*[）)])?\s*$')
SUMMARY_LINE = re.compile(r'^(<details>\s*<summary>)第\s*\d+\s*题(</summary>.*)$')
CN_NUM = '零一二三四五六七八九十'


def split_frontmatter(text):
    """返回 (frontmatter 行列表, 正文行列表)；没有 frontmatter 时前者为空。"""
    lines = text.split('\n')
    if lines and lines[0].strip() == '---':
        for index in range(1, min(len(lines), 200)):
            if lines[index].strip() == '---':
                return lines[:index + 1], lines[index + 1:]
    return [], lines


def frontmatter_value(fm_lines, key):
    prefix = f'{key}:'
    for line in fm_lines:
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            return value
    return ''


def count_stats(lines):
    return {
        'questions': sum(1 for line in lines if Q_HEADING.match(line.strip())),
        'options': sum(1 for line in lines if OPTION.match(line.strip())),
        'images': sum(len(IMG_MD.findall(line)) + len(IMG_HTML.findall(line)) for line in lines),
        'details': sum(line.count('<details') for line in lines),
        'summaries': sum(line.count('<summary') for line in lines),
    }


def answer_bodies(lines):
    """答案块正文的多重集合（去掉 <details>/<summary> 外壳行），用于比对搬移前后。"""
    bodies, depth, current = Counter(), 0, []
    for line in lines:
        opened, closed = line.count('<details'), line.count('</details>')
        if depth == 0 and opened:
            current = []
        elif depth > 0:
            current.append(line.rstrip())
        depth += opened - closed
        if depth == 0 and closed and current is not None:
            body = re.sub(r'\s+', '', '\n'.join(
                current[1:] if current and '<summary' in current[0] else current))
            bodies[body] += 1
    return bodies


def without_details(lines):
    """去掉 <details>…</details> 整块，用于比对题面/材料是否被改动。"""
    out, depth = [], 0
    for line in lines:
        opened, closed = line.count('<details'), line.count('</details>')
        if depth == 0 and not opened and not closed:
            out.append(line)
            continue
        depth += opened - closed
        if depth < 0:
            depth = 0
    return out


def line_counter(lines):
    """非空行的多重集合：搬移会改变顺序，但不许增删任何一行。"""
    return Counter(line.strip() for line in lines if line.strip())


def strip_overview(lines):
    """去掉概览块；没有块就原样返回。"""
    out, skipping = [], False
    for line in lines:
        if line.strip() == START:
            skipping = True
            continue
        if line.strip() == END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return out


def normalize(lines):
    """统一空白：去行尾空格、压缩空行、标题后空行、去首尾空行。代码块内不动。"""
    out = []
    in_fence = False
    fence = ''
    for raw in lines:
        stripped = raw.rstrip()
        marker = stripped.strip()
        if marker.startswith('```') or marker.startswith('~~~'):
            if not in_fence:
                in_fence, fence = True, marker[:3]
            elif marker.startswith(fence):
                in_fence = False
            out.append(raw.rstrip() if not in_fence else raw)
            continue
        if in_fence:
            out.append(raw)
            continue
        if stripped == '':
            if out and out[-1] == '':
                continue
            out.append('')
            continue
        out.append(stripped)
        if HEADING.match(stripped) and not stripped.startswith('#######'):
            out.append('')
    while out and out[0] == '':
        out.pop(0)
    while out and out[-1] == '':
        out.pop()
    compact = []
    for line in out:
        if line == '' and compact and compact[-1] == '':
            continue
        compact.append(line)
    return compact


def anchor(text):
    cleaned = re.sub(r'[：:，。、！？"“”‘’（）()\[\]【】《》<>' + "'" + ']', '', text)
    cleaned = re.sub(r'\s+', '-', cleaned.strip())
    return '#' + cleaned


def parse_modules(lines):
    """从「题型与作答说明」里取「模块名 + （N题）」成对文本；失败返回空列表。"""
    start = None
    for index, line in enumerate(lines):
        if line.strip() == '## 题型与作答说明':
            start = index + 1
            break
    if start is None:
        return []
    end = next((i for i in range(start, len(lines)) if lines[i].startswith('## ')), len(lines))
    modules = []
    index = start
    while index < end:
        line = lines[index].strip()
        if line and not HEADING.match(line) and not line.startswith('>'):
            look = index + 1
            while look < end and lines[look].strip() == '':
                look += 1
            match = MODULE_COUNT.match(lines[look].strip()) if look < end else None
            if match:
                modules.append((line, int(match.group(1))))
                index = look + 1
                continue
        index += 1
    return modules


def split_answer_section(lines):
    """拆出答案区。

    返回 (起始行号, {题号: 块行列表}, 前言行, 尾随章节行)；失败时首项为 None，
    第二项是原因。允许块前有 `>` 说明、`<a id="r7-reference-N">` 锚点，
    允许答案区之后还有别的 `##` 章节（原样留在卷末）。
    """
    index = next((i for i, line in enumerate(lines) if ANSWER_HEAD.match(line.strip())), None)
    if index is None:
        return None, 'no-answer-section', None, None

    blocks, preamble, tail, anchors = {}, [], [], []
    cursor, started = index + 1, False
    while cursor < len(lines):
        stripped = lines[cursor].strip()
        if stripped == '':
            cursor += 1
            continue
        if stripped.startswith('## '):
            tail = lines[cursor:]
            break
        if stripped.startswith('<a id='):
            anchors.append(lines[cursor])
            cursor += 1
            continue
        if stripped.startswith('<details'):
            block, depth = [], 0
            while cursor < len(lines):
                block.append(lines[cursor])
                depth += lines[cursor].count('<details') - lines[cursor].count('</details>')
                cursor += 1
                if depth == 0:
                    break
            match = re.search(r'<summary>\s*第\s*(\d+)\s*题', '\n'.join(block))
            if not match:
                return None, 'answer-summary-unparsed', None, None
            number = int(match.group(1))
            if number in blocks:
                return None, f'answer-duplicate:{number}', None, None
            blocks[number] = anchors + block
            anchors, started = [], True
            continue
        if not started and not anchors:
            preamble.append(lines[cursor])
            cursor += 1
            continue
        return None, f'answer-section-extra-content:{lines[cursor][:24]}', None, None
    if not blocks:
        return None, 'answer-section-empty', None, None
    return index, blocks, preamble, tail


def question_spans(lines):
    """返回 [(题号, 起始行, 结束行)]；结束行是下一个同级或更高级标题的行号。"""
    heads = []
    for index, line in enumerate(lines):
        match = Q_HEADING.match(line.strip())
        if match:
            heads.append((int(match.group(2)), index, len(match.group(1))))
    spans = []
    for number, start, level in heads:
        end = len(lines)
        for other in range(start + 1, len(lines)):
            match = re.match(r'^(#{1,6})\s', lines[other])
            if match and len(match.group(1)) <= level:
                end = other
                break
        spans.append((number, start, end))
    return spans


def interleave(lines, enabled=True):
    """把卷末答案块搬到每题之后。返回 (新行列表, 是否搬移, 原因)。"""
    if not enabled:
        return lines, False, 'disabled'
    answer_index, blocks, preamble, tail = split_answer_section(lines)
    if answer_index is None:
        return lines, False, blocks
    spans = question_spans(lines[:answer_index])
    if not spans:
        return lines, False, 'no-questions'

    numbers = [number for number, _, _ in spans]
    if len(set(numbers)) != len(numbers):
        return lines, False, 'duplicate-question-numbers'
    if set(numbers) != set(blocks):
        return lines, False, f'answer-mismatch:{len(numbers)}q/{len(blocks)}a'

    out = lines[:answer_index]
    for number, _, end in sorted(spans, key=lambda item: item[2], reverse=True):
        end = min(end, len(out))
        block = []
        for line in blocks[number]:
            match = SUMMARY_LINE.match(line.strip())
            if match:
                block.append(f'{match.group(1)}第 {number} 题 · 答案与解析{match.group(2)}')
            elif re.match(r'^<summary>\s*第\s*\d+\s*题\s*</summary>$', line.strip()):
                block.append(f'<summary>第 {number} 题 · 答案与解析</summary>')
            else:
                block.append(line.rstrip())
        out[end:end] = block + ['']

    if preamble:
        anchor_at = next((i for i, line in enumerate(out) if line.strip() == '## 题目'), None)
        if anchor_at is None:
            anchor_at = next((i for i, line in enumerate(out)
                              if line.startswith('# ') and not line.startswith('## ')), 0)
        out[anchor_at + 1:anchor_at + 1] = [''] + preamble + ['']
    if tail:
        out.extend([''] + tail)
    return normalize(out), True, 'interleaved'


def build_overview(fm_lines, body_lines, answers_inline):
    area = frontmatter_value(fm_lines, '地区')
    year = frontmatter_value(fm_lines, '年份')
    subject = frontmatter_value(fm_lines, '科目')
    paper_type = frontmatter_value(fm_lines, '卷型')
    stats = count_stats(body_lines)
    title_bits = [bit for bit in (area, year, subject, paper_type) if bit]
    suffix = f' ｜ {stats["questions"]:,} 题 · 图片 {stats["images"]:,} 处'
    if answers_inline:
        suffix += ' · 答案随题折叠'
    meta = '> **' + ' · '.join(title_bits) + '**' + suffix

    headings = {}
    for line in body_lines:
        match = HEADING.match(line.strip())
        if match:
            headings.setdefault(match.group(2), match.group(1))

    links = []
    if '题型与作答说明' in headings:
        links.append(('[题型与作答说明]', '题型与作答说明'))
    if '题目' in headings:
        links.append(('[题目]', '题目'))
    first_material = next((text for text in headings if re.match(r'^材料\s*\d+$', text)), None)
    if first_material:
        links.append((f'[{first_material}]', first_material))
    if '给定资料 材料一：' in headings:
        links.append(('[给定资料]', '给定资料 材料一：'))
    if not answers_inline and '答案与解析' in headings:
        links.append(('[答案与解析]', '答案与解析'))

    block = [START, meta, '']
    modules = parse_modules(body_lines) if subject == '行测' else []
    if modules and sum(count for _, count in modules) == stats['questions']:
        block.extend(['| 题型模块 | 题量 | 题号 |', '| --- | ---: | ---: |'])
        cursor = 1
        for name, count in modules:
            block.append(f'| {name} | {count} | {cursor}–{cursor + count - 1} |')
            cursor += count
        block.append(f'| **合计** | **{sum(count for _, count in modules)}** | |')
        block.append('')

    if links:
        block.append('导航：' + ' · '.join(f'{label}({anchor(text)})' for label, text in links))
    block.append(END)
    return block, stats


def polish_text(text, interleave_answers=True, normalize_material_heads=False):
    fm_lines, body = split_frontmatter(text)
    had_overview = any(line.strip() == START for line in body)
    base = normalize(strip_overview(body))

    if normalize_material_heads:
        base = [MATERIAL_HEADING.sub(lambda m: f'## 材料{cn_number(m.group(1))}', line)
                if MATERIAL_HEADING.match(line) else line for line in base]

    original = base
    moved_before = answer_bodies(base)
    base, inline, reason = interleave(base, interleave_answers)
    if inline and answer_bodies(base) != moved_before:
        return None, 'self-check-answer-body-changed', ''

    h1 = next((index for index, line in enumerate(base)
               if line.startswith('# ') and not line.startswith('## ')), None)
    if h1 is None:
        return None, 'no-h1', ''

    # 重跑时答案区已不存在，但折叠块仍逐题分布，概览里要保留同样的标注。
    inline_label = inline or (
        not any(ANSWER_HEAD.match(line.strip()) for line in base)
        and any('<details' in line for line in base))
    block, stats = build_overview(fm_lines, base, inline_label)
    pre, post = base[:h1 + 1], base[h1 + 1:]
    while pre and pre[-1] == '':
        pre.pop()
    while post and post[0] == '':
        post.pop(0)
    new_body = pre + [''] + block + [''] + post

    if normalize(strip_overview(new_body)) != base:
        return None, 'self-check-body-mismatch', ''
    if inline:
        expected = line_counter(without_details(
            [line for line in original if not ANSWER_HEAD.match(line.strip())]))
        actual = line_counter(without_details(strip_overview(new_body)))
        if expected != actual:
            return None, 'self-check-question-text-changed', ''
    before, after = count_stats(base), count_stats(strip_overview(new_body))
    if before != after:
        return None, f'self-check-counts {before} != {after}', ''

    header = (fm_lines + ['']) if fm_lines else []
    result = '\n'.join(header + new_body) + '\n'
    status = 'unchanged' if result == text else ('updated' if had_overview else 'added-overview')
    detail = 'answers-inline' if inline_label else f'answers-kept:{reason}'
    return result, status, detail


def cn_number(token):
    if token.isdigit() or len(token) == 1:
        return token
    if len(token) == 2 and token[0] == '十' and token[1] in CN_NUM:
        return '十' + token[1]
    if len(token) == 2 and token[1] == '十' and token[0] in CN_NUM:
        return token[0] + '十'
    if len(token) == 3 and token[1] == '十':
        return token[0] + '十' + token[2]
    return token


def load_paths(args):
    if args.paths_file:
        with open(args.paths_file, encoding='utf-8') as handle:
            return [ROOT / line.strip() for line in handle if line.strip()]
    if args.paths:
        return [Path(item.strip()) if Path(item.strip()).is_absolute() else ROOT / item.strip()
                for item in args.paths.split(',') if item.strip()]
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = ROOT / manifest
    paths = []
    with manifest.open(encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                paths.append(ROOT / json.loads(line)['path'])
    return paths


def main():
    parser = argparse.ArgumentParser(description='按卷面规范整理试卷 Markdown（只动版式）。')
    parser.add_argument('--write', action='store_true', help='写盘；省略则只报告')
    parser.add_argument('--check', action='store_true', help='只检查不写盘（默认行为，保留兼容）')
    parser.add_argument('--paths', help='逗号分隔的文件路径；省略则按 manifest 全量')
    parser.add_argument('--paths-file', help='每行一个文件路径（便于分片并行）')
    parser.add_argument('--limit', type=int, default=0, help='最多处理多少份')
    parser.add_argument('--manifest', default='catalog/manifest.jsonl', help='manifest 路径')
    parser.add_argument('--no-interleave', action='store_true', help='保留卷末答案区，不随题折叠')
    parser.add_argument('--normalize-material-headings', action='store_true',
                        help='把「## 给定资料 材料一：」规范成「## 材料一」')
    parser.add_argument('--report', help='把逐卷结果写成 JSON')
    args = parser.parse_args()

    paths = load_paths(args)
    if args.limit:
        paths = paths[:args.limit]

    results = []
    failures = 0
    counts, details = {}, {}
    for path in paths:
        relative = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        if not path.exists():
            results.append({'path': relative, 'status': 'missing'})
            failures += 1
            continue
        text = path.read_text(encoding='utf-8')
        outcome, status, detail = polish_text(text, not args.no_interleave,
                                              args.normalize_material_headings)
        counts[status] = counts.get(status, 0) + 1
        details[detail] = details.get(detail, 0) + 1
        if outcome is None:
            failures += 1
            results.append({'path': relative, 'status': status, 'detail': detail})
            continue
        results.append({'path': relative, 'status': status, 'detail': detail})
        if args.write and status in ('updated', 'added-overview'):
            path.write_text(outcome, encoding='utf-8', newline='\n')

    summary = {'files': len(paths), 'counts': counts, 'details': details,
               'failures': failures, 'write': args.write}
    print(json.dumps(summary, ensure_ascii=False))
    if args.report:
        Path(args.report).write_text(
            json.dumps({'summary': summary, 'files': results}, ensure_ascii=False, indent=1) + '\n',
            encoding='utf-8')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
