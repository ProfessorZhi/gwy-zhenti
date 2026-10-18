#!/usr/bin/env python3
"""Offline, read-only fast10 shard runner.

Ten papers that already have a captured question book are split into four
mutually exclusive identity shards (3 / 3 / 2 / 2). Each worker only ever sees
its own 1-3 papers: nothing re-walks the 1169-paper corpus and nothing opens a
browser.

Input is strictly fingerprint-only metadata:
  - `--observations`  the Owner's sanitised observation batch (no question text,
                      no cookies, no tokens; each paper carries an image sha256)
  - `--verification`  per-paper verification digest (slot/stub/image counts)
  - `--route-stats`   per-paper route evidence digest

Nothing here guesses a site URL, reads an Owner raw directory, chmods, or
invents a number. A category the metadata cannot support is reported as
`blocked` with the exact field that would unblock it -- never as zero.

Exit codes: 0 ran and every shard has usable input; 2 ran but at least one shard
is blocked on missing input; 1 bad arguments or an invalid manifest.

Usage:
    python3 -I tools/qa/fast10_shards.py \
        --manifest tools/qa/fast10.manifest.json \
        --observations <dir>/observations-batch-*.json \
        --verification <dir>/owner-verification-*.json \
        --route-stats  <dir>/route-evidence-stats-*.json \
        --out out/fast10
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

# Keys that would mean the "fingerprint-only" promise was broken.
FORBIDDEN_KEYS = re.compile(
    r'^(?:contentHtml|stem|stemText|questionText|options?|choices?|answer|answerHtml|'
    r'explanation|explanationHtml|analysis|solution|materials?|rawHtml|html|cookie|'
    r'cookies|token|tokens|password|secret|session|authorization)$', re.I)

CATEGORIES = ('exact', 'normalized', 'near', 'weak', 'image_conflict',
              'ambiguous', 'stub', 'unmatched')


def load_json(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


# `permissions` is part of the published schema: a boolean declaration that the batch holds
# NO profile/cookie/token. Its keys name credentials only to deny them, so the subtree is
# checked by value (all must be false) rather than by key name.
PERMISSION_BLOCK = re.compile(r'^permissions$', re.I)


def carries_text(value):
    """Could this value hold question text? A count or a flag cannot.

    The digests legitimately carry `materials: 5` and `options: 0` as counters; only a
    string, or a list/dict holding one, can break the fingerprint-only promise.
    """
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(carries_text(item) for item in value)
    if isinstance(value, dict):
        return any(carries_text(item) for item in value.values())
    return False


def find_forbidden(value, path='$'):
    """Return the first key that would break the fingerprint-only promise."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if PERMISSION_BLOCK.match(str(key)) and isinstance(inner, dict) \
                    and all(isinstance(v, bool) for v in inner.values()):
                continue
            if FORBIDDEN_KEYS.match(str(key)) and carries_text(inner):
                return f'{path}.{key}'
            hit = find_forbidden(inner, f'{path}.{key}')
            if hit:
                return hit
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            hit = find_forbidden(inner, f'{path}[{index}]')
            if hit:
                return hit
    return None


def validate_manifest(manifest):
    """One paper, one shard; every shard within its cap; the union is complete."""
    problems = []
    seen, by_source = {}, {}
    total = 0
    for shard in manifest.get('shards', []):
        sid = shard.get('id')
        papers = shard.get('papers') or []
        if not sid:
            problems.append('shard without an id')
        if not 1 <= len(papers) <= int(manifest.get('rules', {}).get('maxPapersPerShard', 3)):
            problems.append(f'{sid}: paper count {len(papers)} outside 1..3')
        for paper in papers:
            total += 1
            src = str(paper.get('sourceId'))
            if src in seen:
                problems.append(f'source {src} appears in {seen[src]} and {sid}')
            seen[src] = sid
            by_source[src] = paper
    return problems, by_source, total


def classify_paper(paper, obs, verification, route_stats):
    """Build one paper record. Only measured values; unmeasured stay `blocked`."""
    src = str(paper['sourceId'])
    # The caller already resolved this paper's rows; re-indexing by sourceId here would
    # silently yield {} and report every paper as blocked.
    v = verification or {}
    r = route_stats or {}

    images = v.get('images') or {}
    files = images.get('files')
    verified = images.get('shaVerified')
    # A byte conflict is the one thing that must switch auto-accept off outright.
    image_conflict = None
    if isinstance(files, int) and isinstance(verified, int):
        image_conflict = max(0, files - verified)
    elif files is not None:
        image_conflict = 0 if images.get('allVerified') is True else None

    mapping = v.get('mapping') or {}
    basis = str(mapping.get('basis') or '')
    verified_count = mapping.get('verifiedCount')
    remaining = mapping.get('remainingMissing')

    # `exact` vs `normalized` is a property of the matching basis, not a guess.
    exact = normalized = None
    if isinstance(verified_count, int):
        if 'normalized_equal' in basis:
            exact, normalized = 0, verified_count
        elif 'number' in basis or 'reorder' in basis:
            exact, normalized = verified_count, 0

    categories = {
        'exact': exact,
        'normalized': normalized,
        # These need a per-question ledger the digests do not carry.
        'near': None,
        'weak': None,
        'ambiguous': None,
        'image_conflict': image_conflict,
        'stub': v.get('stubCount'),
        'unmatched': remaining,
    }

    blockers = []
    for key in ('near', 'weak', 'ambiguous'):
        if categories[key] is None:
            blockers.append({
                'category': key,
                'state': 'blocked',
                'requires': 'per-question ledger: {sourceId, slot, grade, score, exactBlockedBy}'
                            f' for {src}',
            })
    if image_conflict:
        blockers.append({'category': 'image_conflict', 'state': 'conflict',
                         'requires': 'verified image bytes disagree with the library; human review'})

    official = v.get('officialVerification') is True
    auto = bool(official and not image_conflict
                and isinstance(remaining, int) and remaining == 0
                and not any(b['category'] in ('ambiguous', 'image_conflict') for b in blockers))
    # Single-source evidence can never be self-certified, whatever the match count.
    if not official:
        blockers.append({'category': 'auto_accept', 'state': 'blocked',
                         'requires': 'official verification; current evidence is single-source'})

    # Accounting guard: slots must equal verified + remaining, optionally + stub.
    # The digest is NOT uniform here -- on some papers `remainingMissing` already folds the
    # placeholder stubs in and on others it does not. Report the residue instead of assuming.
    slots = v.get('realQuestionSlots')
    stubs = v.get('stubCount')
    residue = None
    if isinstance(slots, int) and isinstance(verified_count, int) and isinstance(remaining, int):
        residue = slots - verified_count - remaining
    accounting = {
        'slots': slots,
        'verified': verified_count,
        'remaining': remaining,
        'stub': stubs,
        'residue': residue,
        'remainingIncludesStubs': (residue == 0) if residue is not None else None,
        'consistent': (residue == 0 or (isinstance(stubs, int) and residue == stubs))
                       if residue is not None else None,
    }
    if accounting['consistent'] is False:
        blockers.append({'category': 'accounting', 'state': 'inconsistent',
                         'requires': f'slots-verified-remaining={residue} but stubCount={stubs}; '
                                     'the digest mixes "remaining includes stubs" with "does not"'})

    return {
        'sourceId': src,
        'paper': paper.get('paper'),
        'accounting': accounting,
        'area': paper.get('area'), 'year': paper.get('year'), 'variant': paper.get('variant'),
        'input_ready': bool(obs is not None and v),
        'observed': obs is not None,
        'questionCount': (obs or {}).get('questionCount'),
        'route': {
            'kind': ((obs or {}).get('route') or {}).get('kind'),
            'urlPresent': bool(((obs or {}).get('route') or {}).get('url')),
            'requiresOwnerSession': (r.get('route') or {}).get('requiresOwnerSession'),
            'enqueueableForCredentialFreeCollector':
                r.get('captureReadyForCredentialFreeCollector'),
        },
        'slots': v.get('realQuestionSlots'),
        'stemEligible': v.get('stemEligible'),
        'imageOnly': v.get('imageOnlyQuestions'),
        'images': {'files': files, 'shaVerified': verified,
                   'allVerified': images.get('allVerified')},
        'mapping': {'basis': basis or None, 'verifiedCount': verified_count,
                    'remainingMissing': remaining, 'reorder': mapping.get('reorder')},
        'repoComparison': r.get('repoComparison'),
        'evidenceLevel': v.get('evidenceLevel'),
        'officialVerification': official,
        'categories': categories,
        'autoAcceptAllowed': auto,
        'blockers': blockers,
    }


def process_shard(shard, papers_by_source, obs_by_source, verif_by_source, route_by_source):
    records = []
    for paper in shard.get('papers') or []:
        src = str(paper.get('sourceId'))
        records.append(classify_paper(paper, obs_by_source.get(src),
                                      verif_by_source.get(src), route_by_source.get(src)))
    ready = sum(1 for row in records if row['input_ready'])
    totals = {k: None for k in CATEGORIES}
    for key in CATEGORIES:
        values = [row['categories'][key] for row in records
                  if isinstance(row['categories'][key], int)]
        totals[key] = sum(values) if values else None
    return {
        'id': shard.get('id'),
        'label': shard.get('label'),
        'papers': records,
        'papersInShard': len(records),
        'papersWithInput': ready,
        'totals': totals,
        'blocked': any(not row['input_ready'] for row in records),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--observations', required=True)
    ap.add_argument('--verification', required=True)
    ap.add_argument('--route-stats', required=True)
    ap.add_argument('--repo', default='.')
    ap.add_argument('--workers', type=int, default=2,
                    help='shard workers (<=4). Default 2: the host is memory-tight.')
    ap.add_argument('--out', default='out/fast10')
    args = ap.parse_args(argv)

    manifest = load_json(args.manifest)
    problems, papers_by_source, total_papers = validate_manifest(manifest)
    if problems:
        for problem in problems:
            print(f'manifest: {problem}', file=sys.stderr)
        return 1
    workers = max(1, min(4, args.workers))

    observations = load_json(args.observations)
    verification = load_json(args.verification)
    route_stats = load_json(args.route_stats)

    # The promise is checked, not assumed.
    for name, doc in (('observations', observations), ('verification', verification),
                      ('route-stats', route_stats)):
        hit = find_forbidden(doc)
        if hit:
            print(f'{name}: refuses to run, {hit} looks like question text or a credential', file=sys.stderr)
            return 1

    perms = observations.get('permissions') or {}
    if any(perms.get(k) for k in ('browserProfile', 'cookies', 'tokens')):
        print('observations: refuses to run, batch claims profile/cookie/token access', file=sys.stderr)
        return 1

    obs_by_source = {str(o.get('paperSourceId')): o for o in observations.get('observations', [])}
    verif_by_source = {str(p.get('sourceId')): p for p in verification.get('papers', [])}
    route_by_source = {str(p.get('sourceId')): p for p in route_stats.get('papers', [])}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        shards = list(pool.map(
            lambda shard: process_shard(shard, papers_by_source, obs_by_source,
                                        verif_by_source, route_by_source),
            manifest.get('shards', [])))

    os.makedirs(args.out, exist_ok=True)
    report = {
        'schemaVersion': 1,
        'kind': 'gwy-zhenti-fast10-shard-report',
        'baseline': manifest.get('baseline'),
        'workers': workers,
        'manifest': os.path.basename(args.manifest),
        'inputs': {
            'observations': len(obs_by_source),
            'verification': len(verif_by_source),
            'routeStats': len(route_by_source),
            'containsQuestionText': {
                'observations': observations.get('containsQuestionText'),
                'verification': verification.get('containsQuestionText'),
                'routeStats': route_stats.get('containsQuestionText'),
            },
        },
        'shards': shards,
        'papersTotal': total_papers,
        'papersWithInput': sum(s['papersWithInput'] for s in shards),
    }
    path = os.path.join(args.out, 'fast10-report.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
        fh.write('\n')

    print(f'workers={workers}  papers={report["papersTotal"]}  with-input={report["papersWithInput"]}')
    header = f'{"shard":26s}{"papers":>7s}{"ready":>6s}{"exact":>7s}{"norm":>7s}{"stub":>6s}{"unm":>5s}{"imgConf":>8s}'
    print(header)
    for shard in shards:
        t = shard['totals']
        def show(value):
            return 'blocked' if value is None else str(value)
        print(f'{shard["id"]:26s}{shard["papersInShard"]:>7d}{shard["papersWithInput"]:>6d}'
              f'{show(t["exact"]):>7s}{show(t["normalized"]):>7s}{show(t["stub"]):>6s}'
              f'{show(t["unmatched"]):>5s}{show(t["image_conflict"]):>8s}')
        for row in shard['papers']:
            print(f'    {row["sourceId"]:>8} {str(row["paper"]):38s} '
                  f'{"READY" if row["input_ready"] else "BLOCKED"}')
    print(f'\nwrote {path}')
    return 0 if not any(s['blocked'] for s in shards) else 2


if __name__ == '__main__':
    raise SystemExit(main())
