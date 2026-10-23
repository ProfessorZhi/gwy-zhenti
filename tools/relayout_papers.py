#!/usr/bin/env python3
"""把「材料全部堆在卷首」的旧排版改成「材料就近、编号可读」。

行测：材料按首个引用它的题排序为 材料 1…N，直接插在该题组前；`关联材料：` 只在一题
引用多份材料、或材料不在上方时保留。

申论：给定材料本来就是全卷共用，保持前置，只把内部 ID（material-1、哈希）换成 `材料 N`。

只移动、不改写：脚本会对比正文的字符多重集（去掉标题行与 `关联材料：` 行），
有任何内容增减就拒绝写入该卷。

用法：
    python3 tools/relayout_papers.py --check        # 只报告哪些卷需要重排
    python3 tools/relayout_papers.py --write        # 就地重排
"""

import argparse
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def split_front(body):
    return (re.search(r'^##\s*给定材料\s*$', body, re.M),
            re.search(r'^##\s*题目\s*$', body, re.M),
            re.search(r'^##\s*答案与解析\s*$', body, re.M))


def relayout(head, body):
    subject = re.search(r'^科目:\s*"?(行测|申论)"?', head, re.M)
    subject = subject.group(1) if subject else ''
    given, questions_head, answers = split_front(body)
    if not (given and questions_head and answers):
        return None
    pre = body[:given.start()]
    material_segment = body[given.end():questions_head.start()]
    question_segment = body[questions_head.end():answers.start()]
    tail = body[answers.start():]

    parts = re.split(r'^###\s*材料\s+(\S+)\s*$', material_segment, flags=re.M)
    materials = [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
    by_label = {label: block for label, block in materials}

    # material-1 与 1 视为同一份材料
    alias = {}
    for label in by_label:
        if label.isdigit():
            alias['material-' + label] = label
        match = re.fullmatch(r'material-(.+)', label)
        if match and match.group(1) in by_label:
            alias[label] = match.group(1)

    def real(label):
        return alias.get(label, label)

    def links(block):
        found = []
        for line in re.findall(r'^关联材料：([^\n]+)', block, re.M):
            for token in re.split(r'[、,，\s]+', line.strip()):
                if token:
                    found.append(token)
        return found

    if subject == '申论':
        fixed = re.sub(
            r'^关联材料：([^\n]+)',
            lambda m: '关联材料：' + '、'.join(
                '材料 ' + real(x) if x in by_label or real(x) in by_label else x
                for x in re.split(r'[、,，\s]+', m.group(1).strip()) if x),
            question_segment, flags=re.M)
        return (pre.rstrip('\n') + '\n\n## 给定材料\n' + material_segment.rstrip('\n')
                + '\n\n## 题目\n' + fixed.rstrip('\n') + '\n\n' + tail)

    questions = re.split(r'^###\s*第\s*(\d+)\s*题\s*$', question_segment, flags=re.M)
    question_list = [(int(questions[i]), questions[i + 1]) for i in range(1, len(questions), 2)]

    order = []
    for _, block in question_list:
        for label in links(block):
            target = real(label)
            if target in by_label and target not in order:
                order.append(target)
    for label, _ in materials:
        if label not in order:
            order.append(label)
    number = {label: index + 1 for index, label in enumerate(order)}

    first_use = {}
    for index, (_, block) in enumerate(question_list):
        for label in links(block):
            target = real(label)
            if target in by_label and target not in first_use:
                first_use[target] = index

    out = [pre.rstrip('\n'), '', '## 题目', '']
    emitted, last_material = set(), None
    for index, (num, block) in enumerate(question_list):
        labels = [real(x) for x in links(block) if real(x) in by_label]
        for target in [x for x in dict.fromkeys(labels) if first_use.get(x) == index]:
            out += ['## 材料 %d' % number[target], '', by_label[target].strip('\n'), '']
            emitted.add(target)
            last_material = target
        body_text = re.sub(r'^关联材料：.*\n?', '', block, flags=re.M).strip('\n').rstrip()
        link = ''
        if labels and (len(set(labels)) > 1 or labels[0] != last_material):
            link = '关联材料：' + '、'.join('材料 %d' % number[x] for x in dict.fromkeys(labels))
        if body_text:
            marker = re.search(r'^([A-H][.．、]|作答要求：)', body_text, re.M)
            if link and marker:
                head_part = body_text[:marker.start()].rstrip()
                tail_part = body_text[marker.start():]
                body_text = head_part + '\n\n' + link + '\n\n' + tail_part
                link = ''
            out += ['### 第 %d 题' % num, '', body_text, '']
        if link:
            out += [link, '']
    rest = [label for label, _ in materials if label not in emitted]
    if rest:
        out += ['## 其余材料', '']
        for label in rest:
            out += ['### 材料 %d' % number[label], '', by_label[label].strip('\n'), '']
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(out))
    return text.rstrip('\n') + '\n\n' + tail


def bag(text):
    """正文内容指纹：去掉标题与关联材料行，只保留汉字和字母数字。"""
    text = '\n'.join(line for line in text.split('\n') if not line.startswith('关联材料'))
    text = re.sub(r'^#{1,6}\s*.*$', '', text, flags=re.M)
    return collections.Counter(c for c in text if ('一' <= c <= '鿿') or c.isalnum())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', default=os.path.join(ROOT, 'catalog/manifest.jsonl'))
    parser.add_argument('--write', action='store_true', help='就地写入；默认只检查')
    parser.add_argument('--check', action='store_true', help='只检查（默认行为）')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    changed = skipped = lost = 0
    losses = []
    with open(args.manifest, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            path = json.loads(line)['path']
            full = os.path.join(ROOT, path)
            text = open(full, encoding='utf-8').read()
            end = text.find('\n---', 3)
            head, body = text[:end + 4], text[end + 4:]
            new_body = relayout(head, body)
            if new_body is None or new_body == body:
                skipped += 1
                continue
            if bag(body) != bag(new_body):
                lost += 1
                losses.append(path)
                continue
            changed += 1
            if args.write:
                with open(full, 'w', encoding='utf-8') as target:
                    target.write(head + new_body)
            elif args.verbose:
                print('would rewrite', path)
    print(f'重排 {changed} · 无需改动 {skipped} · 内容有差异而拒绝 {lost}')
    if losses:
        print('差异样例', losses[:10])
    return 1 if lost else 0


if __name__ == '__main__':
    sys.exit(main())
