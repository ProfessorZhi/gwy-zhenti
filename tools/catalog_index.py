#!/usr/bin/env python3
"""从 catalog/manifest.jsonl 生成可读的 Markdown 试卷索引。

用法：
    python3 -I tools/catalog_index.py                     # 输出到 stdout
    python3 -I tools/catalog_index.py --out catalog/INDEX.md
    python3 -I tools/catalog_index.py --check             # 只校验，不写文件

题目数取 manifest 的 declared_questions，图片数取 image_references。
输出不含时间戳，同一输入重复运行结果完全一致。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / 'catalog' / 'manifest.jsonl'
SUBJECTS = ('行测', '申论')
SUBJECT_ORDER = {name: index for index, name in enumerate(SUBJECTS)}

# 与 tools/cloud_quality.py 的统计口径保持一致。
HEAD_Q = re.compile(r'^#{2,3}\s+第\s*(\d+)\s*题', re.M)
DECLARED_Q = re.compile(r'>\s*(?:行测|申论)\s*·\s*(\d+)\s*题')
IMG_TAG = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
IMG_MD = re.compile(r'!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))')

REQUIRED_FIELDS = (
    'path', 'area', 'year', 'subject', 'declared_questions',
    'question_anchors', 'image_references',
)


def image_refs(text):
    refs = IMG_TAG.findall(text)
    refs += [a or b for a, b in IMG_MD.findall(text)]
    return refs


def resolve_root(manifest):
    parent = manifest.parent
    return parent.parent if parent.name == 'catalog' else REPO_ROOT


def load_records(manifest):
    records, errors = [], []
    with open(manifest, encoding='utf-8') as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f'第 {lineno} 行 JSON 解析失败：{exc}')
                continue
            if not isinstance(record, dict):
                errors.append(f'第 {lineno} 行不是 JSON 对象')
                continue
            missing = [key for key in REQUIRED_FIELDS if key not in record]
            if missing:
                errors.append(f'第 {lineno} 行缺字段：{", ".join(missing)}')
                continue
            records.append(record)
    return records, errors


def check_records(records, root):
    errors = []
    seen_paths = set()

    for record in records:
        path = record['path']
        label = path

        if path in seen_paths:
            errors.append(f'{label}：路径重复')
        seen_paths.add(path)

        for field in ('declared_questions', 'question_anchors', 'image_references'):
            value = record[field]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f'{label}：{field} 不是非负整数（{value!r}）')

        if record['subject'] not in SUBJECT_ORDER:
            errors.append(f'{label}：未知科目 {record["subject"]!r}')
        if record['area'] != '国考' and not path.startswith('省考/'):
            errors.append(f'{label}：非国考路径未位于 省考/ 下')
        if f'/{record["year"]}/' not in path:
            errors.append(f'{label}：路径年份与 manifest 年份 {record["year"]} 不符')

        full = root / PurePosixPath(path)
        if not full.is_file():
            errors.append(f'{label}：文件不存在')
            continue

        data = full.read_bytes()
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            errors.append(f'{label}：不是合法 UTF-8（{exc}）')
            continue

        if record.get('bytes') != len(data):
            errors.append(f'{label}：字节数 {record.get("bytes")} != 实际 {len(data)}')
        if record.get('sha256') != hashlib.sha256(data).hexdigest():
            errors.append(f'{label}：sha256 与文件不符')

        anchors = len(HEAD_Q.findall(text))
        if anchors != record['question_anchors']:
            errors.append(
                f'{label}：question_anchors {record["question_anchors"]} != 文件题目标题 {anchors}'
            )

        declared_match = DECLARED_Q.search(text)
        declared = int(declared_match.group(1)) if declared_match else anchors
        if declared != record['declared_questions']:
            errors.append(
                f'{label}：declared_questions {record["declared_questions"]} != 文内计数 {declared}'
            )

        images = len(image_refs(text))
        if images != record['image_references']:
            errors.append(
                f'{label}：image_references {record["image_references"]} != 文件图片 {images}'
            )

    return errors


def subject_counts(rows):
    counts = Counter(record['subject'] for record in rows)
    return [(subject, counts.get(subject, 0)) for subject in SUBJECTS]


def summarize(rows):
    years = sorted({int(record['year']) for record in rows})
    return {
        'papers': len(rows),
        'questions': sum(record['declared_questions'] for record in rows),
        'images': sum(record['image_references'] for record in rows),
        'areas': len({record['area'] for record in rows}),
        'years': years,
    }


def area_sort_key(area, count):
    return (0 if area == '国考' else 1, -count, area)


def build_index(rows, link_prefix=''):
    summary = summarize(rows)
    area_counter = Counter(record['area'] for record in rows)
    areas = sorted(area_counter, key=lambda area: area_sort_key(area, area_counter[area]))

    lines = [
        '# 试卷目录索引',
        '',
        '> 由 tools/catalog_index.py 生成，勿手改。',
        '',
        (
            f'共 **{summary["papers"]:,}** 份试卷 · **{summary["areas"]}** 个地区 · '
            f'**{len(summary["years"])}** 个年份'
            f'（{summary["years"][0]}–{summary["years"][-1]}） · '
            f'题目 **{summary["questions"]:,}** 道 · 图片引用 **{summary["images"]:,}** 处'
        ),
        '',
        '## 按科目',
        '',
        '| 科目 | 试卷数 | 题目 | 图片引用 |',
        '| --- | ---: | ---: | ---: |',
    ]
    for subject, count in subject_counts(rows):
        subset = [record for record in rows if record['subject'] == subject]
        lines.append(
            f'| {subject} | {count:,} | '
            f'{sum(r["declared_questions"] for r in subset):,} | '
            f'{sum(r["image_references"] for r in subset):,} |'
        )
    lines.extend([
        f'| **合计** | **{summary["papers"]:,}** | '
        f'**{summary["questions"]:,}** | **{summary["images"]:,}** |',
        '',
        '## 按地区',
        '',
        '> 国考置顶，其余按试卷数降序；试卷数相同按地区名排序。',
        '',
        '| 地区 | 试卷数 | 行测 | 申论 | 题目 | 图片引用 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ])
    for area in areas:
        subset = [record for record in rows if record['area'] == area]
        counts = dict(subject_counts(subset))
        lines.append(
            f'| {area} | {len(subset):,} | {counts.get("行测", 0):,} | '
            f'{counts.get("申论", 0):,} | '
            f'{sum(r["declared_questions"] for r in subset):,} | '
            f'{sum(r["image_references"] for r in subset):,} |'
        )
    lines.append(
        f'| **合计** | **{summary["papers"]:,}** | '
        f'**{sum(1 for r in rows if r["subject"] == "行测"):,}** | '
        f'**{sum(1 for r in rows if r["subject"] == "申论"):,}** | '
        f'**{summary["questions"]:,}** | **{summary["images"]:,}** |'
    )
    lines.append('')

    for area in areas:
        subset = [record for record in rows if record['area'] == area]
        counts = dict(subject_counts(subset))
        lines.extend([
            f'## {area}',
            '',
            (
                f'> {len(subset):,} 份 · 行测 {counts.get("行测", 0):,} · '
                f'申论 {counts.get("申论", 0):,} · '
                f'题目 {sum(r["declared_questions"] for r in subset):,} · '
                f'图片 {sum(r["image_references"] for r in subset):,}'
            ),
            '',
        ])
        by_year = defaultdict(list)
        for record in subset:
            by_year[int(record['year'])].append(record)
        for year in sorted(by_year, reverse=True):
            lines.extend([f'### {year}', ''])
            year_rows = sorted(
                by_year[year],
                key=lambda record: (
                    SUBJECT_ORDER.get(record['subject'], len(SUBJECTS)),
                    str(record.get('paper_type', '')),
                    PurePosixPath(record['path']).stem,
                    record['path'],
                ),
            )
            for record in year_rows:
                stem = PurePosixPath(record['path']).stem
                lines.append(
                    f'- [{stem}]({link_prefix}{record["path"]}) · {record["subject"]} · '
                    f'题目 {record["declared_questions"]:,} · '
                    f'图片 {record["image_references"]:,}'
                )
            lines.append('')

    lines.extend([
        '---',
        '',
        '> 统计口径：题目取 manifest 的 `declared_questions`，图片取 `image_references`；'
        '链接路径相对仓库根目录。',
        '',
    ])
    return '\n'.join(lines)


def run_check(manifest, rows, parse_errors, root):
    errors = list(parse_errors)
    errors.extend(check_records(rows, root))
    summary = summarize(rows)
    print(f'清单：{manifest}')
    print(
        f'记录 {len(rows):,} 行 · 地区 {summary["areas"]} 个 · '
        f'年份 {summary["years"][0] if summary["years"] else "-"}–'
        f'{summary["years"][-1] if summary["years"] else "-"} · '
        f'题目 {summary["questions"]:,} · 图片 {summary["images"]:,}'
    )
    if errors:
        print(f'校验失败：{len(errors)} 项不一致')
        for message in errors[:50]:
            print(f'  - {message}')
        if len(errors) > 50:
            print(f'  …… 另有 {len(errors) - 50} 项')
        return 1
    print('校验通过：路径均存在，题量/图片计数与文件一致，sha256/字节数相符。')
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='从 manifest.jsonl 生成稳定的 Markdown 试卷索引。'
    )
    parser.add_argument('--manifest', default=str(DEFAULT_MANIFEST), help='manifest 路径')
    parser.add_argument('--out', help='输出文件；省略则写到 stdout')
    parser.add_argument('--check', action='store_true', help='只校验数据一致性，不写文件')
    parser.add_argument('--root', help='试卷路径的根目录；默认从 manifest 位置推断')
    args = parser.parse_args()

    manifest = Path(args.manifest).expanduser()
    if not manifest.is_absolute():
        manifest = (Path.cwd() / manifest).resolve()
    root = Path(args.root).resolve() if args.root else resolve_root(manifest)

    try:
        rows, parse_errors = load_records(manifest)
    except OSError as exc:
        print(f'无法读取 manifest：{exc}', file=sys.stderr)
        return 2

    if args.check:
        return run_check(manifest, rows, parse_errors, root)

    if parse_errors:
        for message in parse_errors:
            print(message, file=sys.stderr)
        return 1

    out = None
    link_prefix = ''
    if args.out:
        out = Path(args.out).expanduser()
        if not out.is_absolute():
            out = Path.cwd() / out
        # 链接要相对「输出文件所在目录」，否则 INDEX.md 放进 catalog/ 后 1,422 条全断。
        relative = os.path.relpath(root, out.parent)
        link_prefix = '' if relative == '.' else relative.replace(os.sep, '/') + '/'
    output = build_index(rows, link_prefix)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding='utf-8', newline='\n')
        print(f'已写入 {out}（{len(output.splitlines()):,} 行）', file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
