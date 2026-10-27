#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the R3 per-paper QA batch from the three scan artifacts.

This is a *joining* step, not a new analysis: it takes the table scan, the
symbol scan and the bilateral asset check and produces one row per paper with
the evidence already collected, plus the Markdown rendered by
``--out-md``.  Anything the scanners did not observe is reported as ``UNKNOWN``
rather than inferred.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r3lib  # noqa: E402


def load(path):
    if not path or not os.path.exists(path):
        return None
    return r3lib.load_json(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--tables', required=True)
    ap.add_argument('--symbols', required=True)
    ap.add_argument('--assets', required=True)
    ap.add_argument('--papers', required=True, help='one MD path per line; # comments')
    ap.add_argument('--out')
    ap.add_argument('--out-md')
    args = ap.parse_args(argv)

    with open(args.papers, encoding='utf-8') as fh:
        papers = [l.strip() for l in fh if l.strip() and not l.strip().startswith('#')]

    tables = load(args.tables) or {}
    symbols = load(args.symbols) or {}
    assets = load(args.assets) or {}

    tbl_by_paper = defaultdict(list)
    for r in tables.get('findings', []):
        tbl_by_paper[r['path']].append(r)
    ml_by_paper = defaultdict(list)
    for r in tables.get('multilevel', []):
        ml_by_paper[r['path']].append(r)
    sym_by_paper = defaultdict(list)
    for x in symbols.get('findings', []):
        sym_by_paper[x['path']].append(x)
    mixed_by_paper = defaultdict(list)
    for m in symbols.get('mixed_units', []):
        mixed_by_paper[m['path']].append(m)
    asset_by_paper = {r['path']: r for r in assets.get('results', [])}

    rows = []
    for rel in papers:
        full = os.path.join(args.repo, rel)
        if not os.path.exists(full):
            rows.append({'path': rel, 'error': 'md_missing'})
            continue
        text = r3lib.read_text(full)
        a = asset_by_paper.get(rel, {})
        syms = sym_by_paper.get(rel, [])
        cat = Counter(x['cat'] for x in syms)
        tbls = tbl_by_paper.get(rel, [])
        cov = a.get('coverage') or {}
        rows.append({
            'path': rel,
            'md_sha': r3lib.sha256_text(text),
            'bytes': len(text.encode('utf-8')),
            'refs': a.get('refs'),
            'refs_missing': len(a.get('missing', [])),
            'refs_outside': len(a.get('outside', [])),
            'refs_unverified': len(a.get('unverified', [])),
            'source_assets': cov.get('source_assets'),
            'source_absent': cov.get('absent'),
            'source_absent_big': cov.get('absent_big'),
            'tables_flagged': len(tbls),
            'tables': [
                {'line': t['line'], 'unit': t['unit'], 'verdict': t['finding']['verdict'],
                 'confidence': t['finding']['confidence'], 'ncols': t['ncols'],
                 'header': t['header'], 'img_sha': t['img_sha']}
                for t in tbls
            ],
            'multilevel': len(ml_by_paper.get(rel, [])),
            'symbol_hits': len(syms),
            'symbol_by_cat': dict(cat),
            'mixed_units': [{'unit': m['unit'], 'notations': m['notations']}
                            for m in mixed_by_paper.get(rel, [])],
            'pair': a.get('pair'),
        })

    summary = {
        'tool': 'r3_batch',
        'papers': len(rows),
        'papers_missing': sum(1 for r in rows if r.get('error')),
        'tables_flagged': sum(r.get('tables_flagged') or 0 for r in rows),
        'symbol_hits': sum(r.get('symbol_hits') or 0 for r in rows),
        'papers_with_mixed_units': sum(1 for r in rows if r.get('mixed_units')),
        'refs_missing': sum(r.get('refs_missing') or 0 for r in rows),
        'refs_outside': sum(r.get('refs_outside') or 0 for r in rows),
        'source_absent_big': sum(r.get('source_absent_big') or 0 for r in rows),
    }
    out = {'summary': summary, 'papers': rows}
    if args.out:
        r3lib.dump_json(args.out, out)

    print(json.dumps(summary, ensure_ascii=False, indent=1))

    if args.out_md:
        lines = [
            '# R3 首批高风险卷 QA（%d 卷）' % len(rows),
            '',
            '由 `tools/r3_batch.py` 从 `tablescan` / `symbolscan` / `assets` 三份产物联结生成，',
            '不含人工推测。`img_sha` 是该表上方最近一张原图的**内容哈希**（仓库以内容哈希命名图片，',
            '文件名即 sha256），用于把表格回溯到原图。',
            '',
            '| 卷 | md_sha | 引用 | 缺图 | 表(疑) | 多级 | 符号 | 混记法单元 | 源附件 | 无引用大图 |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
        ]
        for r in rows:
            if r.get('error'):
                lines.append('| %s | MISSING | | | | | | | | |' % r['path'])
                continue
            lines.append('| %s | `%s` | %s | %s | %s | %s | %s | %s | %s | %s |' % (
                r['path'], (r['md_sha'] or '')[:12], r['refs'], r['refs_missing'],
                r['tables_flagged'], r['multilevel'], r['symbol_hits'],
                len(r['mixed_units']), r['source_assets'], r['source_absent_big']))
        lines += ['', '## 逐表证据（含原图 SHA）', '']
        lines += ['| 卷 | 行 | 单元 | 判定 | 置信 | 表头 | 原图 SHA |',
                  '|---|---:|---|---|---|---|---|']
        for r in rows:
            if r.get('error'):
                continue
            for t in r['tables']:
                lines.append('| %s | %d | %s | %s | %s | %s | `%s` |' % (
                    r['path'], t['line'], t['unit'], t['verdict'], t['confidence'],
                    ' '.join(t['header'])[:40], (t['img_sha'] or '无原图')[:12]))
        lines += ['', '## 同一单元的记法混用', '']
        for r in rows:
            if r.get('error') or not r['mixed_units']:
                continue
            for m in r['mixed_units']:
                lines.append('- `%s` %s：%s' % (r['path'], m['unit'], ' + '.join(m['notations'])))
        with open(args.out_md, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
        print('markdown written:', args.out_md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
