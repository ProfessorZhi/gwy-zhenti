#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R3 bilateral asset check: source attachment <-> repo-relative path.

Two directions, because either one alone lies:

**A. repo -> source (``attested``)**
    Every ``![](…)`` / ``<img src=…>`` in a paper is resolved *against the MD's
    own directory* (not the repo root -- the repo's own tooling warns that the
    root-relative form silently walks the wrong folder).  The file must exist,
    and because the repo names assets by content hash, the basename must equal
    sha256(contents).  We do not re-read the bytes when Q6 already recorded the
    hash for that path; the Q6 pixel ledger is reused as the hash oracle.

**B. source -> repo (``coverage``)**
    Each file in the paper's source ``assets`` directory is a candidate the
    source actually served.  Either the repo references it, or it is reported
    with a reason.  An unreferenced *small* image is expected (formulas are
    transcribed to text); an unreferenced *large* image is not, and is what a
    human must look at.

Nothing here writes outside ``--out``, and nothing is downloaded.
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r3lib  # noqa: E402

RE_MD_IMG = re.compile(r'!\[[^\]]*\]\(\s*([^)\s]+)')
RE_HTML_IMG = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*"([^"]+)"', re.I)
SHA_NAME = re.compile(r'^([0-9a-fA-F]{32,64})\.(png|jpe?g|webp|bmp|gif)$', re.I)


def refs_of(text):
    out = [(m.group(1), 'md') for m in RE_MD_IMG.finditer(text)]
    out += [(m.group(1), 'html') for m in RE_HTML_IMG.finditer(text)]
    return out


def load_pairs(path):
    """Q6 pair ledger: path -> {src_dir, pair, lane}."""
    idx = {}
    if not path or not os.path.exists(path):
        return idx
    for rec in r3lib.load_json(path):
        idx[rec['path']] = rec
    return idx


def load_pixels(path):
    """Q6 pixel ledger keyed by absolute path AND by sha."""
    by_path, by_sha = {}, {}
    if not path or not os.path.exists(path):
        return by_path, by_sha
    for rec in r3lib.load_json(path):
        p = rec.get('path')
        if p:
            by_path[p] = rec
        s = rec.get('sha')
        if s:
            by_sha[s] = rec
    return by_path, by_sha


def sha_of_basename(ref):
    base = os.path.basename(ref.split('#')[0].split('?')[0])
    return os.path.splitext(base)[0].lower()


def source_assets(src_dir):
    """sha -> relative path for every content-addressed file in a source dir."""
    out = {}
    if not src_dir or not os.path.isdir(src_dir):
        return out
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != 'node_modules']
        for fn in files:
            m = SHA_NAME.match(fn)
            if m:
                out[m.group(1).lower()] = os.path.relpath(os.path.join(root, fn), src_dir)
    return out


def check_paper(rel, repo, pair, by_path, by_sha, deep_source=True):
    full = os.path.join(repo, rel)
    if not os.path.exists(full):
        return {'path': rel, 'error': 'md_missing'}
    text = r3lib.read_text(full)
    refs = refs_of(text)

    resolved = {}
    missing, escaped, noncontent, unverified = [], [], [], []
    seen = set()
    for ref, kind in refs:
        abs_path, why = r3lib.resolve_ref(full, ref)
        if abs_path is None:
            if why == 'external':
                escaped.append({'ref': ref, 'why': 'external'})
            continue
        rel_to_repo = os.path.relpath(abs_path, repo)
        if rel_to_repo.startswith('..'):
            escaped.append({'ref': ref, 'why': 'outside_repo'})
        if not os.path.exists(abs_path):
            missing.append({'ref': ref, 'why': 'not_found'})
            continue

        stem = sha_of_basename(ref)
        is_content_named = bool(re.fullmatch(r'[0-9a-f]{32,64}', stem))
        rec = by_path.get(abs_path)
        if rec:
            sha = rec.get('sha')
            ok = rec.get('ok')
            dims = [rec.get('w'), rec.get('h')]
        else:
            sha, ok, dims = None, None, None
        if not is_content_named:
            noncontent.append({'ref': ref})
        elif sha is None:
            unverified.append({'ref': ref, 'why': 'no_hash_record'})
        elif sha != stem:
            missing.append({'ref': ref, 'why': 'name_hash_mismatch',
                            'name': stem, 'content': sha})
        if kind == 'md' or kind == 'html':
            seen.add(stem)

        resolved.setdefault(stem, abs_path)

    # B: source -> repo coverage
    src_dir = (pair or {}).get('src_dir')
    coverage = None
    if deep_source and src_dir:
        assets = source_assets(src_dir)
        if assets:
            referenced, absent = [], []
            for sha, srel in assets.items():
                if sha in seen:
                    referenced.append(sha)
                else:
                    rec = by_sha.get(sha) or {}
                    absent.append({
                        'sha': sha, 'src_rel': srel,
                        'w': rec.get('w'), 'h': rec.get('h'),
                    })
            big = [a for a in absent if (a.get('h') or 0) >= 150]
            coverage = {
                'src_dir': src_dir,
                'source_assets': len(assets),
                'referenced': len(referenced),
                'absent': len(absent),
                'absent_big': len(big),
                'absent_big_sample': big[:10],
            }

    return {
        'path': rel,
        'refs': len(refs),
        'unique_content_hashes': len(seen),
        'missing': missing,
        'outside': escaped,
        'non_content_named': noncontent[:10],
        'unverified': unverified[:10],
        'coverage': coverage,
        'pair': (pair or {}).get('pair'),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--pairs', help='Q6 q6-pairs.json (source dirs)')
    ap.add_argument('--pixels', help='Q6 q6-pixels.json (hash oracle)')
    ap.add_argument('--papers', help='file with one repo-relative MD path per line')
    ap.add_argument('--manifest', help='else use catalog/manifest.jsonl')
    ap.add_argument('--no-source', action='store_true', help='skip direction B')
    ap.add_argument('--out')
    args = ap.parse_args(argv)

    pairs = load_pairs(args.pairs)
    by_path, by_sha = load_pixels(args.pixels)

    if args.papers:
        with open(args.papers, encoding='utf-8') as fh:
            rels = [l.strip() for l in fh if l.strip() and not l.startswith('#')]
    elif args.manifest:
        import json
        rels = []
        with open(args.manifest, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rels.append(json.loads(line)['path'])
    else:
        rels = [r for r, _ in r3lib.md_files(args.repo)]

    results = []
    totals = Counter()
    for rel in rels:
        rec = check_paper(rel, args.repo, pairs.get(rel), by_path, by_sha,
                          deep_source=not args.no_source)
        results.append(rec)
        if rec.get('error'):
            totals['md_missing'] += 1
            continue
        totals['papers'] += 1
        totals['refs'] += rec['refs']
        totals['missing'] += len(rec['missing'])
        totals['outside'] += len(rec['outside'])
        totals['non_content_named'] += len(rec['non_content_named'])
        totals['unverified'] += len(rec['unverified'])
        c = rec.get('coverage')
        if c:
            totals['source_assets'] += c['source_assets']
            totals['source_referenced'] += c['referenced']
            totals['source_absent'] += c['absent']
            totals['source_absent_big'] += c['absent_big']

    out = {
        'tool': 'r3_assets',
        'repo': os.path.abspath(args.repo),
        'papers': len(rels),
        'totals': dict(totals),
        'papers_with_missing': [r['path'] for r in results if r.get('missing')],
        'coverage_gaps_big': [
            {'path': r['path'], **c} for r in results
            if (c := r.get('coverage')) and c['absent_big']
        ],
        'results': results,
    }
    if args.out:
        r3lib.dump_json(args.out, out)

    print('papers=%d refs=%d missing=%d outside=%d non_content_named=%d unverified=%d'
          % (totals['papers'], totals['refs'], totals['missing'], totals['outside'],
             totals['non_content_named'], totals['unverified']))
    if totals['source_assets']:
        print('source assets=%d referenced=%d absent=%d absent_big=%d'
              % (totals['source_assets'], totals['source_referenced'],
                 totals['source_absent'], totals['source_absent_big']))
    if out['papers_with_missing']:
        print('papers with missing refs:', out['papers_with_missing'][:10])
    return 0


if __name__ == '__main__':
    sys.exit(main())
