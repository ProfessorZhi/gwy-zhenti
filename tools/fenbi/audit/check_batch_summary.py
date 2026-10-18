#!/usr/bin/env python3
"""Check a metadata-only Fenbi first-initialization batch report.

No third-party question text, browsing, user profile, or network is involved.
The unknown slot count is deliberately retained rather than inferred away.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def cells(line):
    if not line.startswith('|') or not line.rstrip().endswith('|'):
        return []
    return [x.strip().replace('**', '').replace(chr(96), '') for x in line.strip()[1:-1].split('|')]


def numeric(text, field):
    v = re.fullmatch(r'\d+', text)
    if not v:
        raise ValueError(f'{field}: not an integer: {text!r}')
    return int(text)


def parse_report(text):
    headings = []
    rows = []
    total = None
    for line in text.splitlines():
        a = cells(line)
        if len(a) != 12:
            continue
        if a[0] == '#':
            headings.append(a)
        elif re.fullmatch(r'\d+', a[0]):
            rows.append(a)
        elif a[0] in ('—', '-', '合计') and a[1] == '合计':
            total = a
    if len(headings) != 1 or len(rows) < 1 or total is None:
        raise ValueError('missing or ambiguous 12-column batch summary table')
    if len({a[0] for a in rows}) != len(rows):
        raise ValueError('duplicate row numbers')
    if len({a[2] for a in rows}) != len(rows):
        raise ValueError('duplicate source IDs')
    stats = dict(created=0, reused=0, questions=0, valid_stems=0, stubs=0,
                 per_paper_unique_image_sum=0, matched=0, unclassified=0)
    by_paper = []
    for a in rows:
        init = re.fullmatch(r'新建 (\d+) 次', a[3])
        if init is None:
            raise ValueError(f'{a[0]}: cannot parse initialization count')
        created = int(init.group(1))
        if a[4] not in ('是', '否'):
            raise ValueError(f'{a[0]}: invalid reuse flag')
        reused = 1 if a[4] == '是' else 0
        q, good, stub, imgs = [numeric(a[i], f'{a[0]} {i}') for i in (5, 6, 7, 10)]
        matched = re.fullmatch(r'(\d+)/(\d+)(?:\s*⚠️)?', a[11])
        if matched is None:
            raise ValueError(f'{a[0]}: invalid matched fraction')
        m, denom = map(int, matched.groups())
        if denom != q or m > q:
            raise ValueError(f'{a[0]}: matched denominator inconsistent with question slots')
        unknown = q - good - stub
        if unknown < 0:
            raise ValueError(f'{a[0]}: valid and stub counts exceed question slots')
        for k, value in dict(created=created, reused=reused, questions=q,
                             valid_stems=good, stubs=stub,
                             per_paper_unique_image_sum=imgs, matched=m,
                             unclassified=unknown).items():
            stats[k] += value
        by_paper.append({'number': int(a[0]), 'paper': a[1], 'sourceId': a[2],
                         'question_slots': q, 'valid_stems': good,
                         'stubs': stub, 'unclassified': unknown,
                         'strict_same_number_matches': m})
    checks = {
        'created': numeric(total[3].replace(' 次', ''), 'created total'),
        'reused': numeric(total[4], 'reused total'),
        'questions': numeric(total[5], 'question total'),
        'valid_stems': numeric(total[6], 'valid stems total'),
        'stubs': numeric(total[7], 'stub total'),
        'per_paper_unique_image_sum': numeric(total[10], 'image total'),
    }
    wrong = {k: {'reported': want, 'sum_of_rows': stats[k]}
             for k, want in checks.items() if want != stats[k]}
    return {'checked_papers': len(rows), 'totals': stats, 'by_paper': by_paper,
            'mismatches': wrong, 'passed': not wrong,
            'image_count_scope': 'sum of per-paper unique counts; cross-paper dedup not proven',
            'match_scope': 'strict source-number comparison, not verified correctness'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('report', type=Path)
    args = p.parse_args(argv)
    try:
        result = parse_report(args.report.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
