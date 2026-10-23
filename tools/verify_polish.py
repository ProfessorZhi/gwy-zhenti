#!/usr/bin/env python3
"""把排版后的文件与 git 里的旧版本逐项比对，证明“只搬家、没改字”。

用法：
    python3 -I tools/verify_polish.py --base-ref HEAD --paths a.md,b.md
    git diff --name-only | python3 -I tools/verify_polish.py --base-ref HEAD --stdin

检查项：题数、选项行、图片引用、<details>/<summary> 数、答案块正文多重集、
非折叠块文本多重集（忽略 `## 答案与解析` 标题行与概览块）。任一不符 → 退出码 1。
"""

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('polish', ROOT / 'tools/polish_markdown.py')
polish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(polish)


def git_blob(ref, path):
    return subprocess.run(['git', 'show', f'{ref}:{path}'], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout


def compare(old, new):
    problems = []
    for key in ('questions', 'options', 'images', 'details', 'summaries'):
        before, after = polish.count_stats(old.split('\n')), polish.count_stats(new.split('\n'))
        if before[key] != after[key]:
            problems.append(f'{key}: {before[key]} -> {after[key]}')
    if polish.answer_bodies(old.split('\n')) != polish.answer_bodies(new.split('\n')):
        problems.append('答案块正文有变化')

    def text(lines):
        _, body = polish.split_frontmatter('\n'.join(lines))
        body = [line for line in polish.strip_overview(body)
                if not polish.ANSWER_HEAD.match(line.strip())]
        return polish.line_counter(polish.without_details(body))

    if text(old.split('\n')) != text(new.split('\n')):
        problems.append('非折叠块文本有增删')
    return problems


def main():
    parser = argparse.ArgumentParser(description='核对排版前后内容一致。')
    parser.add_argument('--base-ref', default='HEAD')
    parser.add_argument('--paths')
    parser.add_argument('--stdin', action='store_true', help='从 stdin 读文件列表')
    args = parser.parse_args()

    if args.stdin:
        paths = [line.strip() for line in sys.stdin if line.strip().endswith('.md')]
    elif args.paths:
        paths = [item for item in args.paths.split(',') if item.strip()]
    else:
        paths = [line for line in subprocess.run(
            ['git', '-c', 'core.quotepath=false', 'diff', '--name-only', args.base_ref],
            cwd=ROOT, capture_output=True, text=True).stdout.split('\n')
            if line.endswith('.md')]

    failed = 0
    for path in paths:
        try:
            old = git_blob(args.base_ref, path)
        except subprocess.CalledProcessError:
            print(f'新增文件，跳过比对: {path}')
            continue
        new = (ROOT / path).read_text(encoding='utf-8')
        problems = compare(old, new)
        if problems:
            failed += 1
            print(f'FAIL {path}: {"; ".join(problems)}')
        else:
            print(f'ok   {path}')
    print(f'共 {len(paths)} 份，失败 {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
