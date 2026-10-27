#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R3 notation-risk scanner for formulas and comparison operators.

What this tool does **not** do
------------------------------
It never decides what a glyph in a picture is.  A bitmap is only ever used as
an *evidence pointer*: we record its content hash (the repo stores images under
their sha256, so the filename is already the hash) and leave the glyph question
to a human or to the source snapshot's text.  Every finding therefore carries
``evidence`` in {``SOURCE_TEXT``, ``IMAGE_ONLY``} and ``confidence`` is capped at
``medium`` whenever the only evidence is an image.

Risk classes
------------
``LT_RAW``        a ``<`` used as a comparison operator, written as raw HTML-ish
                  text inside Markdown
``LT_FULLWIDTH``  ``＜`` (fullwidth)
``GT_FULLWIDTH``  ``＞`` (fullwidth)
``GT_RAW``        a ``>`` used as a comparison operator
``HTML_ENTITY``   ``&lt;`` / ``&gt;`` escapes standing in for a comparison
``WORD_OP``       小于 / 大于 / 不大于 / 不小于 written as words instead of a sign
``MATH_SYMBOL``   ∑ √ ∫ ≤ ≥ ≠ ≈ ± ÷ ∝ ∞ ∠ △ ⊥ ∥ ° ℃ ‰
``GREEK``         α β γ δ π σ θ λ μ ω Σ Ω
``FRACTION``      a bare a/b that is a mathematical fraction, not a date or URL
``SUPERSCRIPT``   ² ³ ¹ ₀ ₁ ₂ or ^2-style exponents

The important output is not the per-hit list but the **units** that mix
notations inside one question, because that is what a reader trips over.
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r3lib  # noqa: E402

# Anything that is legitimately angle-bracketed in this repo's Markdown.
RE_HTML_TAG = re.compile(r'</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>')
RE_HTML_COMMENT = re.compile(r'<!--.*?-->', re.S)
RE_AUTOLINK = re.compile(r'<[a-zA-Z][a-zA-Z0-9+.-]*:[^<>\s]*>')
RE_IMG_MD = re.compile(r'!\[[^\]]*\]\([^)]*\)')
RE_IMG_MD_CAPTURE = re.compile(r'!\[[^\]]*\]\(\s*([^)\s]+)')
RE_IMG_HTML = re.compile(r'<img\b[^>]*>', re.I)
RE_IMG_HTML_SRC = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*"([^"]+)"', re.I)

RE_FULL_LT = re.compile(r'＜')
RE_FULL_GT = re.compile(r'＞')
RE_ENTITY = re.compile(r'&(lt|gt);')
RE_WORD_OP = re.compile(r'(?<!不)小于|(?<!不)大于|不小于|不大于|小于等于|大于等于')
RE_MATH = re.compile(r'[∑∏√∫≤≥≠≈±÷∝∞∠△⊥∥°℃‰∵∴∈∉⊂⊆∪∩]')
RE_GREEK = re.compile(r'[αβγδεζηθλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]')
RE_SUP = re.compile(r'[²³¹⁰⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]|\^\s*\d')
# a/b where b is not a date-like or ratio-of-years pattern
RE_FRACTION = re.compile(r'(?<![\d/])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\d/])')
# A raw '<' still present after HTML tags are removed.  Both "23%<x" and
# "23% < x" are comparison operators, so whitespace after the sign must NOT be
# excluded; adjacency to a number decides whether it is an operator at all.
RE_RAW_LT = re.compile(r'(?<![<=])<(?![<=])')
RE_RAW_GT = re.compile(r'(?<![-=<>])>(?!>)')

# Chinese words that mark a "解析"/"答案" region; a comparison there is a
# rendered formula rather than a question stem we should leave alone.
RE_ANALYSIS = re.compile(r'^\s*\*\*解析\*\*|^\s*\*\*答案\*\*|参考答案')


def strip_non_prose(line):
    """Remove Markdown/HTML constructs that legitimately contain < and >."""
    s = RE_HTML_COMMENT.sub(' ', line)
    s = RE_IMG_HTML.sub(' ', s)
    s = RE_IMG_MD.sub(' ', s)
    s = RE_AUTOLINK.sub(' ', s)
    s = RE_HTML_TAG.sub(' ', s)
    return s


def is_fraction_hit(m, context):
    """Filter out dates (2024/10) and year ratios."""
    a, b = m.group(1), m.group(2)
    if len(a) == 4 and len(b) <= 2:      # 2024/10 is a date
        return False
    if len(a) == 4 and len(b) == 4:      # 2024/2025 is a year span
        return False
    try:
        if len(a) <= 2 and len(b) <= 2 and '.' not in a and '.' not in b:
            # 1/2 is a fraction; 3/5 could be a date 3月5日 only with 月/日 nearby
            if re.search(r'[月日]', context):
                return False
    except Exception:
        pass
    return True


def scan_line(line, in_analysis):
    """Return list of (category, matched_text) for one prose line."""
    hits = []
    prose = strip_non_prose(line)

    for m in RE_FULL_LT.finditer(prose):
        hits.append(('LT_FULLWIDTH', m.group(0), m.start()))
    for m in RE_FULL_GT.finditer(prose):
        hits.append(('GT_FULLWIDTH', m.group(0), m.start()))
    for m in RE_ENTITY.finditer(prose):
        hits.append(('HTML_ENTITY', m.group(0), m.start()))
    # 大于/小于 are only operators when numbers sit next to them.  "利大于弊"
    # and "供大于求" are idioms and must not be counted as comparison notation.
    for m in RE_WORD_OP.finditer(prose):
        i, j = m.start(), m.end()
        left = prose[max(0, i - 6):i]
        right = prose[j:j + 6]
        if re.search(r'\d', left) or re.search(r'\d', right):
            hits.append(('WORD_OP', m.group(0), i))
    for m in RE_MATH.finditer(prose):
        hits.append(('MATH_SYMBOL', m.group(0), m.start()))
    for m in RE_GREEK.finditer(prose):
        hits.append(('GREEK', m.group(0), m.start()))
    for m in RE_SUP.finditer(prose):
        hits.append(('SUPERSCRIPT', m.group(0), m.start()))
    for m in RE_FRACTION.finditer(prose):
        if is_fraction_hit(m, prose):
            hits.append(('FRACTION', m.group(0), m.start()))

    # Raw < and > only when they clearly act as comparison operators: they must
    # have a digit/percent/letter on at least one side.
    for m in RE_RAW_LT.finditer(prose):
        i = m.start()
        left = prose[max(0, i - 2):i]
        right = prose[i + 1:i + 3]
        if re.search(r'[\d%]', left) or re.search(r'[\d%]', right):
            hits.append(('LT_RAW', '<', i))
    for m in RE_RAW_GT.finditer(prose):
        i = m.start()
        left = prose[max(0, i - 2):i]
        right = prose[i + 1:i + 3]
        if re.search(r'[\d%]', left) and left.strip():
            hits.append(('GT_RAW', '>', i))
    return hits


def nearest_image(lines, lineno):
    """Nearest image reference at or above ``lineno`` (1-based), else below."""
    for i in range(lineno - 1, max(-1, lineno - 40), -1):
        line = lines[i]
        m = RE_IMG_MD_CAPTURE.search(line)
        if m:
            return m.group(1)
        m = RE_IMG_HTML_SRC.search(line)
        if m:
            return m.group(1)
    return None


def ref_sha(ref):
    """The repo names assets by sha256; the basename is the content hash."""
    if not ref:
        return None
    base = os.path.basename(ref.split('#')[0].split('?')[0])
    stem, ext = os.path.splitext(base)
    return stem.lower() if re.fullmatch(r'[0-9a-fA-F]{32,64}', stem) else None


def scan_paper(rel, full, pixel_index):
    text = r3lib.read_text(full)
    lines = text.split('\n')
    qidx = r3lib.question_index(lines)
    findings = []
    in_analysis = False
    for i, line in enumerate(lines, 1):
        # Track the answer/analysis region, because a comparison there is a
        # rendered formula whereas the same characters in a stem may be data.
        if r3lib.RE_Q_ANCHOR.match(line) or line.strip().startswith('</details>'):
            in_analysis = False
        elif RE_ANALYSIS.match(line):
            in_analysis = True
        if not line.strip():
            continue
        hits = scan_line(line, in_analysis)
        if not hits:
            continue
        unit = r3lib.unit_at(qidx, i)
        img = nearest_image(lines, i)
        sha = ref_sha(img)
        for cat, tok, _pos in hits:
            ev = 'IMAGE_ONLY'
            conf = 'medium' if sha else 'low'
            dims = None
            if sha and sha in pixel_index:
                p = pixel_index[sha]
                dims = [p.get('w'), p.get('h')]
            findings.append({
                'path': rel, 'line': i, 'unit': unit, 'cat': cat,
                'token': tok, 'in_analysis': in_analysis,
                'img_ref': img, 'img_sha': sha, 'img_dims': dims,
                'evidence': ev, 'confidence': conf,
                'text': line.strip()[:160],
            })
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--manifest', help='restrict to catalog/manifest.jsonl papers')
    ap.add_argument('--pixels', help='Q6 q6-pixels.json, reused instead of rescanning')
    ap.add_argument('--out')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args(argv)

    pixel_index = {}
    if args.pixels and os.path.exists(args.pixels):
        for rec in r3lib.load_json(args.pixels):
            sha = rec.get('sha')
            if sha:
                pixel_index[sha] = rec

    files = r3lib.md_files(args.repo)
    if args.manifest:
        keep = set()
        with open(args.manifest, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line:
                    import json
                    keep.add(json.loads(line)['path'])
        files = [(r, f) for r, f in files if r in keep]
    if args.limit:
        files = files[:args.limit]

    all_findings = []
    papers_with = {}
    for rel, full in files:
        f = scan_paper(rel, full, pixel_index)
        if f:
            papers_with[rel] = len(f)
            all_findings.extend(f)

    by_cat = Counter(x['cat'] for x in all_findings)
    # Units that mix two different notations for the same operator are the
    # interesting ones: that is what makes a reader doubt the symbol.
    mixed = defaultdict(lambda: defaultdict(set))
    for x in all_findings:
        mixed[(x['path'], x['unit'])][x['cat']].add(x['token'])

    # "Mixed notation" is only a real reader risk when the *same relation* is
    # written with two different symbols inside one question.  Word forms
    # (小于) are a different register and are tracked separately, otherwise the
    # bucket fills with statistics explanations that are perfectly readable.
    SYMBOL_CATS = {'LT_RAW', 'LT_FULLWIDTH', 'HTML_ENTITY'}
    mixed_units = []
    for (path, unit), cats in mixed.items():
        present = SYMBOL_CATS & set(cats)
        if len(present) >= 2:
            mixed_units.append({
                'path': path, 'unit': unit,
                'notations': sorted(present),
                'tokens': {k: sorted(cats[k]) for k in sorted(present)},
            })

    # Word-form comparisons used in a formula context are worth surfacing too,
    # as a lower-severity class: the meaning survives but the sign is gone.
    word_op_units = sorted({
        (x['path'], x['unit']) for x in all_findings if x['cat'] == 'WORD_OP'
    })

    # Bucket by unit within each paper, as the brief asks.
    by_unit = defaultdict(list)
    for x in all_findings:
        by_unit[(x['path'], x['unit'])].append(x)

    result = {
        'tool': 'r3_symbolscan',
        'repo': os.path.abspath(args.repo),
        'files_scanned': len(files),
        'papers_with_hits': len(papers_with),
        'total_hits': len(all_findings),
        'by_category': dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        'papers_with_lt_comparison': len({x['path'] for x in all_findings
                                          if x['cat'] in ('LT_RAW', 'LT_FULLWIDTH')}),
        'lt_raw_split': {
            'total': sum(1 for x in all_findings if x['cat'] == 'LT_RAW'),
            'in_analysis': sum(1 for x in all_findings
                               if x['cat'] == 'LT_RAW' and x['in_analysis']),
            'papers': len({x['path'] for x in all_findings if x['cat'] == 'LT_RAW'}),
            'papers_in_analysis': len({x['path'] for x in all_findings
                                       if x['cat'] == 'LT_RAW' and x['in_analysis']}),
        },
        'word_op_units': len(word_op_units),
        'mixed_notation_units': len(mixed_units),
        'mixed_units': mixed_units,
        'units': [
            {'path': p, 'unit': u, 'hits': len(v),
             'cats': dict(Counter(x['cat'] for x in v))}
            for (p, u), v in sorted(by_unit.items())
        ],
        'findings': all_findings,
    }
    if args.out:
        r3lib.dump_json(args.out, result)

    print('files=%d  papers_with_hits=%d  hits=%d  mixed_units=%d'
          % (len(files), len(papers_with), len(all_findings), len(mixed_units)))
    print('by_category:', dict(result['by_category']))
    print('papers with < comparison:', result['papers_with_lt_comparison'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
