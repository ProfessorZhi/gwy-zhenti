#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R3 high-risk Markdown table header-semantics detector.

The defect class
----------------
A Markdown table *must* have a header row.  When the source image is a bare
数阵 (number grid), a matrix, or a multi-block array, the converter has no label
to put there, so it puts the first data row there.  GitHub then renders that row
bold with the rule underneath it, and a reader takes it for column names.

This tool **only reports**.  It never rewrites a cell value, and the patch it
can emit changes the *structure* only: the original header line is preserved
verbatim, demoted to body row 0, and an empty header row is inserted in front.
That is reversible by construction -- the information content of the file is
identical before and after, which is what ``--verify-patch`` checks.

Safety representation for a headerless matrix
---------------------------------------------
Primary (applied in the emitted patch)::

    |  |  |  |
    | ---: | ---: | ---: |
    | 7 | ? | 20 |
    | 6 | 22 | 30 |

GFM accepts empty header cells, so this renders as a table with an empty header
strip -- no invented column names, the values sit in ``<td>`` where they belong.

Alternate (documented, never auto-applied): a ``<table><tbody>`` HTML block has
no header row at all and is the most literal encoding, but it departs from the
repo's pure-Markdown convention and complicates the audit tooling, so it is
offered only for the few tables where an empty header still reads badly
(``--alt-html`` prints a sample).

Usage::

    python3 -I r3_tablescan.py --repo /path/to/repo --out out/tablescan.json
    python3 -I r3_tablescan.py --repo ... --patch patches/tables.diff
    python3 -I r3_tablescan.py --repo ... --verify-patch patches/tables.diff
"""

import argparse
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r3lib  # noqa: E402


def empty_header(ncols):
    """An empty GFM header row with ``ncols`` blank cells.

    GFM accepts empty header cells, so ``| | |`` is a table whose header carries
    no labels.  That is exactly the honest rendering of a 数阵: the values land
    in ``<td>`` and nothing is invented.
    """
    return '|' + '|'.join(' ' for _ in range(ncols)) + '|'


RE_IMG_ANY = re.compile(r'!\[[^\]]*\]\(\s*([^)\s]+)|<img\b[^>]*?\bsrc\s*=\s*"([^"]+)"', re.I)
SHA_STEM = re.compile(r'^([0-9a-fA-F]{32,64})$')


def nearest_image(lines, lineno, lookback=60):
    """Nearest image reference above ``lineno``; the repo names assets by sha."""
    for i in range(lineno - 2, max(-1, lineno - 2 - lookback), -1):
        m = RE_IMG_ANY.search(lines[i])
        if m:
            ref = m.group(1) or m.group(2)
            stem = os.path.splitext(os.path.basename(ref.split('#')[0]))[0]
            sha = stem.lower() if SHA_STEM.match(stem) else None
            return ref, sha, i + 1
    return None, None, None


def analyse_table(tbl, rel, lineno, qidx, lines=None):
    prof = r3lib.header_profile(tbl.header, tbl.rows[0] if tbl.rows else None)
    ml = r3lib.multilevel_report(tbl)
    finding = None
    if prof['verdict'] in ('DATA', 'INTERLEAVED'):
        finding = {
            'kind': 'HEADER_IS_DATA',
            'verdict': prof['verdict'],
            'confidence': prof['confidence'],
            'reason': prof['reason'],
        }
    elif prof['verdict'] == 'EMPTY':
        finding = {
            'kind': 'HEADER_EMPTY',
            'verdict': prof['verdict'],
            'confidence': prof['confidence'],
            'reason': prof['reason'],
        }
    img_ref, img_sha, img_line = nearest_image(lines, lineno) if lines else (None, None, None)
    rec = {
        'path': rel,
        'line': lineno,
        'img_ref': img_ref,
        'img_sha': img_sha,
        'img_line': img_line,
        'unit': r3lib.unit_at(qidx, lineno),
        'ncols': tbl.ncols,
        'nrows': tbl.nrows,
        'header': r3lib.column_signature(tbl.header),
        'header_raw': tbl.header_raw,
        'first_body': r3lib.column_signature(tbl.rows[0]) if tbl.rows else [],
        'finding': finding,
        'multilevel': ml,
    }
    return rec


def demote_table(lines, idx, ncols):
    """Return ``lines`` with the header at ``idx`` turned into the first body row.

    GFM requires the delimiter row to be the *second* line of the block, so the
    result has to be::

        | | | |            <- blank header (new)
        | --- | --- |      <- original delimiter, unchanged
        | 7 | ? | 20 |     <- original header, verbatim, now a body row
        | 6 | 22 | 30 |

    Putting the demoted row *above* the delimiter silently destroys the table
    (the empty row becomes an orphan line and the data row is re-promoted to
    header), which is why ``verify_patch`` also asserts the row count grows by
    one per patched table.
    """
    header_line = lines[idx]
    sep_line = lines[idx + 1]
    return lines[:idx] + [empty_header(ncols), sep_line, header_line] + lines[idx + 2:]


def build_patch(repo, records, only_conf=('high', 'medium')):
    """Build a unified diff that demotes the data-header rows.

    Only records whose finding is ``HEADER_IS_DATA`` are patched, and only at
    high/medium confidence.  The replacement is purely structural.
    """
    by_file = {}
    for r in records:
        f = r.get('finding')
        if not f or f['kind'] != 'HEADER_IS_DATA':
            continue
        if f['confidence'] not in only_conf:
            continue
        by_file.setdefault(r['path'], []).append(r)

    chunks = []
    for rel in sorted(by_file):
        full = os.path.join(repo, rel)
        old = r3lib.read_text(full)
        lines = old.split('\n')
        # Apply bottom-up so line numbers stay valid.
        for r in sorted(by_file[rel], key=lambda x: -x['line']):
            idx = r['line'] - 1
            header_line = lines[idx]
            if r3lib.RE_TABLE_SEP.match(lines[idx + 1] or '') is None:
                continue  # layout moved under us; skip rather than guess
            lines = demote_table(lines, idx, r['ncols'])
        new = '\n'.join(lines)
        if new == old:
            continue
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile='a/' + rel,
            tofile='b/' + rel,
            n=2,
        )
        chunks.extend(diff)
    return ''.join(chunks)


def table_inventory(repo, files, collect=True):
    """Walk every MD file once; return (per-table records, inventory totals)."""
    records = []
    total_tables = 0
    total_rows = 0
    per_file = {}
    for rel, full in files:
        text = r3lib.read_text(full)
        lines = text.split('\n')
        qidx = r3lib.question_index(lines)
        n_local = 0
        for tbl in r3lib.iter_pipe_tables(lines):
            n_local += 1
            total_rows += tbl.nrows
            if collect:
                records.append(analyse_table(tbl, rel, tbl.start, qidx, lines))
        total_tables += n_local
        if n_local:
            per_file[rel] = n_local
    inv = {
        'files_scanned': len(files),
        'tables': total_tables,
        'table_data_rows': total_rows,
        'files_with_tables': len(per_file),
    }
    return records, inv


def parse_unified(diff_text):
    """Yield (old_path, new_path, hunks) from a unified diff."""
    old = new = None
    hunks = []
    cur = None
    for line in diff_text.split('\n'):
        if line.startswith('--- '):
            old = line[4:].strip()
            if old.startswith('a/'):
                old = old[2:]
        elif line.startswith('+++ '):
            new = line[4:].strip()
            if new.startswith('b/'):
                new = new[2:]
        elif line.startswith('@@'):
            m = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
            cur = {'start': int(m.group(1)), 'lines': []}
            hunks.append(cur)
        elif cur is not None and line[:1] in (' ', '+', '-'):
            cur['lines'].append(line)
    return old, new, hunks


def apply_hunks(text, hunks):
    """Apply parsed hunks to ``text`` (the *pre-patch* file body)."""
    src = text.split('\n')
    out = []
    pos = 0                       # 0-based cursor into src
    for h in hunks:
        start = h['start'] - 1
        out.extend(src[pos:start])
        pos = start
        for line in h['lines']:
            tag, body = line[0], line[1:]
            if tag == ' ':
                out.append(src[pos])
                pos += 1
            elif tag == '-':
                pos += 1          # drop it
            elif tag == '+':
                out.append(body)
    out.extend(src[pos:])
    return '\n'.join(out)


def _table_cells(text):
    """Multiset of every non-empty cell in every table of ``text``."""
    out = []
    for tbl in r3lib.iter_pipe_tables(text.split('\n')):
        for row in [tbl.header] + tbl.rows:
            for c in row:
                c = r3lib.norm_cell(c)
                if c:
                    out.append(c)
    return sorted(out)


def verify_patch(repo, patch_text):
    """Prove the patch is content-preserving, by actually applying it.

    The check must be able to *fail*.  An earlier version compared only the
    ``+``/``-`` lines of the diff, which is vacuously true for a patch that adds
    one blank row and keeps everything else as context -- zero cells on both
    sides, "identical".  So we now reconstruct the patched file and compare the
    real cell multisets, and require a non-zero denominator.
    """
    # Group the diff by file.  Splitting on "\n--- a/" loses the first hunk,
    # because the diff starts with "--- a/" and has no leading newline.
    chunks, cur_lines = [], []
    for line in patch_text.split('\n'):
        if line.startswith('--- a/') and cur_lines:
            chunks.append('\n'.join(cur_lines))
            cur_lines = [line]
        else:
            cur_lines.append(line)
    if cur_lines:
        chunks.append('\n'.join(cur_lines))

    files = []
    for chunk in chunks:
        o, n, hunks = parse_unified(chunk)
        if o and n:
            files.append((o, hunks))

    # Each converted table contributes exactly one added blank header row.
    added_blank = 0
    for line in patch_text.split('\n'):
        if line.startswith('+') and not line.startswith('+++'):
            cells = r3lib.split_row(line[1:])
            if cells and all(c == '' for c in cells):
                added_blank += 1

    report = {'files': [], 'identical_multiset': True, 'cells_compared': 0,
              'rows_before': 0, 'rows_after': 0, 'applied': 0}
    for rel, hunks in files:
        full = os.path.join(repo, rel)
        if not os.path.exists(full):
            report['identical_multiset'] = False
            report['files'].append({'path': rel, 'error': 'missing'})
            continue
        before = r3lib.read_text(full)
        after = apply_hunks(before, hunks)
        tb = [t for t in r3lib.iter_pipe_tables(before.split('\n'))]
        ta = [t for t in r3lib.iter_pipe_tables(after.split('\n'))]
        cb, ca = _table_cells(before), _table_cells(after)
        same = cb == ca
        report['cells_compared'] += len(cb)
        report['rows_before'] += sum(t.nrows for t in tb)
        report['rows_after'] += sum(t.nrows for t in ta)
        report['applied'] += 1
        if not same:
            report['identical_multiset'] = False
        # Structural invariants.  A demotion must not create or destroy tables,
        # and must add exactly one body row per converted header.  Without this
        # the cell-multiset check alone passes even when the delimiter row ends
        # up in the wrong place and the table is silently destroyed.
        if len(ta) != len(tb):
            report['identical_multiset'] = False
        report['files'].append({
            'path': rel,
            'sha_before': r3lib.sha256_text(before),
            'sha_after': r3lib.sha256_text(after),
            'bytes_before': len(before.encode('utf-8')),
            'bytes_after': len(after.encode('utf-8')),
            'tables_before': len(tb), 'tables_after': len(ta),
            'rows_before': sum(t.nrows for t in tb),
            'rows_after': sum(t.nrows for t in ta),
            'cells_before': len(cb), 'cells_after': len(ca),
            'identical_multiset': same,
            'only_after': [x for x in ca if x not in cb][:5],
            'only_before': [x for x in cb if x not in ca][:5],
        })

    # A patch that cannot be checked is not verified.
    report['non_vacuous'] = report['cells_compared'] > 0
    report['rows_delta'] = report['rows_after'] - report['rows_before']
    report['rows_added_expected'] = added_blank
    report['rows_delta_ok'] = report['rows_delta'] == added_blank
    report['ok'] = (report['identical_multiset'] and report['non_vacuous']
                    and report['rows_delta_ok']
                    and report['applied'] == len(files) and len(files) > 0)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', required=True, help='read-only repo root')
    ap.add_argument('--out', help='write JSON report here')
    ap.add_argument('--patch', help='write a unified diff here (never applied)')
    ap.add_argument('--verify-patch', help='verify an existing diff is content-preserving')
    ap.add_argument('--alt-html', action='store_true', help='print an HTML alternate sample')
    ap.add_argument('--limit', type=int, default=0, help='debug: only first N files')
    args = ap.parse_args(argv)

    if args.verify_patch:
        text = r3lib.read_text(args.verify_patch)
        res = verify_patch(args.repo, text)
        import json
        summary = {k: v for k, v in res.items() if k != 'files'}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        bad = [f for f in res['files'] if not f.get('identical_multiset')]
        print('files=%d  applied=%d  rows %d -> %d'
              % (len(res['files']), res['applied'],
                 res['rows_before'], res['rows_after']))
        for f in res['files']:
            print('  %-42s %s -> %s  rows %d->%d'
                  % (f['path'][:42], f['sha_before'][:12], f['sha_after'][:12],
                     f['rows_before'], f['rows_after']))
        if bad:
            print('MISMATCH:', [f['path'] for f in bad])
        return 0 if res['ok'] else 1

    files = r3lib.md_files(args.repo)
    if args.limit:
        files = files[:args.limit]
    records, inv = table_inventory(args.repo, files)

    flagged = [r for r in records if r['finding']]
    data_like = [r for r in records if r['finding']
                 and r['finding']['kind'] == 'HEADER_IS_DATA']
    empty_like = [r for r in records if r['finding']
                  and r['finding']['kind'] == 'HEADER_EMPTY']
    multi = [r for r in records if r['multilevel']]

    conf = {}
    for r in data_like:
        conf[r['finding']['confidence']] = conf.get(r['finding']['confidence'], 0) + 1

    result = {
        'tool': 'r3_tablescan',
        'repo': os.path.abspath(args.repo),
        'inventory': inv,
        'summary': {
            'tables_flagged': len(flagged),
            'header_is_data': len(data_like),
            'header_empty_already': len(empty_like),
            'multilevel_candidates': len(multi),
            'header_is_data_confidence': conf,
        },
        'findings': flagged,
        'multilevel': multi,
    }

    if args.out:
        r3lib.dump_json(args.out, result)

    print('tables=%d  flagged=%d  header_is_data=%d  empty=%d  multilevel=%d'
          % (inv['tables'], len(flagged), len(data_like), len(empty_like), len(multi)))
    for k in sorted(conf):
        print('  header_is_data confidence %s: %d' % (k, conf[k]))

    if args.patch:
        diff = build_patch(args.repo, records)
        with open(args.patch, 'w', encoding='utf-8') as fh:
            fh.write(diff)
        print('patch written: %s (%d bytes)' % (args.patch, len(diff)))

    if args.alt_html:
        import json
        sample = next((r for r in data_like if r['ncols'] >= 3), None)
        if sample:
            print('\n--- HTML alternate for %s:%d (%s) ---'
                  % (sample['path'], sample['line'], sample['unit']))
            print('<table>')
            print('<tbody>')
            for row in [sample['header'], sample['first_body']]:
                print('  <tr>' + ''.join('<td>%s</td>' % c for c in row) + '</tr>')
            print('  <tr>…</tr>')
            print('</tbody>')
            print('</table>')
    return 0


if __name__ == '__main__':
    sys.exit(main())
