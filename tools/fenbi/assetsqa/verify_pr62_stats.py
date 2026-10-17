#!/usr/bin/env python3
"""Recompute the PR #62 reorder-audit statistics from its own JSON.

Pure arithmetic over a metadata-only report. No paper, no capture, no network.

Checks
  coverage-denominator   : coverage == mapped / (source - imageOnly)
  one-to-one             : no duplicated source or repository number in `mapping`
  range                  : every mapped number inside its declared range
  closure-source         : source-side categories sum to sourceQuestions
  closure-repository     : len(mapping) + repo_only == repositoryQuestions
  exact-vs-mapping       : exactPairs == number of mapping rows with exact=true
  mapping-vs-classified  : mapping length vs the classified mapped total
  ambiguity-bound        : does `mapping` contain sources the report calls ambiguous
  inversions             : descents vs actual inversion count
  coverage-without-weak  : coverage excluding weak_candidate_review

Usage:
  python3 -I verify_pr62_stats.py reports/FENBI-REORDER-AUDIT-20261018.json [--out ledger.json]
Exit 0 = checks ran (verdicts are data). Exit 2 = unreadable input.
"""
import argparse
import collections
import json
import sys

MAPPED_KINDS = ["exact_same_number", "exact_reordered", "near_same_number",
                "near_reordered", "weak_candidate_review"]


def inversions(seq):
    n = 0
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            if seq[i] > seq[j]:
                n += 1
    return n


def descents(seq):
    return [(seq[i], seq[i + 1]) for i in range(len(seq) - 1) if seq[i] > seq[i + 1]]


def check_case(c):
    counts = c["counts"]
    src = c["sourceQuestions"]
    rep = c["repositoryQuestions"]
    img = counts.get("image_only_not_comparable", 0)
    denom = src - img
    mapped = sum(counts.get(k, 0) for k in MAPPED_KINDS)
    exact = counts.get("exact_same_number", 0) + counts.get("exact_reordered", 0)
    weak = counts.get("weak_candidate_review", 0)

    mapping = c.get("mapping", [])
    src_nums = [x["sourceNumber"] for x in mapping]
    rep_nums = [x["repositoryNumber"] for x in mapping]
    exact_in_mapping = sum(1 for x in mapping if x.get("exact"))

    repo_side = sum(v for k, v in counts.items() if k != "repo_only_absent_in_source")
    repo_only = counts.get("repo_only_absent_in_source", 0)

    ordered = sorted(mapping, key=lambda x: x["sourceNumber"])
    seq = [x["repositoryNumber"] for x in ordered]
    inv = inversions(seq)
    desc = descents(seq)

    out = collections.OrderedDict()
    out["id"] = c.get("id")
    out["sourceId"] = c.get("sourceId")
    out["sourceQuestions"] = src
    out["repositoryQuestions"] = rep
    out["checks"] = []

    def add(name, verdict, detail, evidence=None):
        out["checks"].append({"check": name, "verdict": verdict, "detail": detail,
                              "evidence": evidence or {}})

    # 1 coverage denominator
    recomputed = round(mapped / denom, 4) if denom else None
    add("coverage-denominator",
        "PASS" if recomputed is not None and abs(recomputed - c["coverage"]) <= 0.0006 else "FAIL",
        f"coverage reported {c['coverage']} vs recomputed {recomputed} = {mapped}/{denom}",
        {"mapped": mapped, "denominator": denom, "imageOnly": img,
         "weakIncluded": weak, "coverageWithoutWeak": round((mapped - weak) / denom, 4)})

    # 2 one-to-one
    dup_src = [k for k, v in collections.Counter(src_nums).items() if v > 1]
    dup_rep = [k for k, v in collections.Counter(rep_nums).items() if v > 1]
    add("one-to-one", "PASS" if not dup_src and not dup_rep else "FAIL",
        f"{len(mapping)} pairs; duplicate source {dup_src}, duplicate repository {dup_rep}",
        {"pairs": len(mapping), "uniqueSource": len(set(src_nums)),
         "uniqueRepository": len(set(rep_nums))})

    # 3 range
    bad = ([x for x in src_nums if not 1 <= x <= src]
           + [x for x in rep_nums if not 1 <= x <= rep])
    add("range", "PASS" if not bad else "FAIL",
        f"{len(bad)} mapped numbers outside 1..source / 1..repository", {"bad": bad[:10]})

    # 4 closure
    add("closure-source", "PASS" if repo_side == src else "FAIL",
        f"source-side categories {repo_side} vs sourceQuestions {src}",
        {"kinds": {k: v for k, v in counts.items() if k != "repo_only_absent_in_source"}})
    add("closure-repository", "PASS" if len(mapping) + repo_only == rep else "FAIL",
        f"mapping {len(mapping)} + repo_only {repo_only} = {len(mapping) + repo_only} vs {rep}")

    # 5 exact
    add("exact-vs-mapping",
        "PASS" if exact_in_mapping == c.get("exactPairs") else "FAIL",
        f"mapping exact rows {exact_in_mapping} vs reported exactPairs {c.get('exactPairs')}")
    add("exact-pairs-vs-classified",
        "INFO" if exact_in_mapping != exact else "PASS",
        f"exact pairs {exact_in_mapping} vs classified exact {exact} -> "
        f"{exact_in_mapping - exact} exact pair(s) classified ambiguous",
        {"delta": exact_in_mapping - exact})

    # 6 mapping vs classified mapped  (the ambiguous-binding gap)
    gap = len(mapping) - mapped
    add("mapping-vs-classified", "FAIL" if gap else "PASS",
        f"mapping {len(mapping)} vs classified mapped {mapped}; gap {gap} = sources classified "
        f"ambiguous that are still bound in `mapping`",
        {"gap": gap, "ambiguous": counts.get("ambiguous_multi_candidate", 0)})

    # 7 monotonicity
    total_pairs = len(seq) * (len(seq) - 1) // 2
    add("monotonicity", "INFO",
        f"{len(desc)} adjacent descent point(s) but {inv}/{total_pairs} inverted pairs "
        f"({(100.0 * inv / total_pairs if total_pairs else 0):.1f}%); "
        f"'nearly monotonic' is not supported",
        {"descents": desc, "inversions": inv, "totalPairs": total_pairs})

    # 8 weak candidates inside mapping
    weak_in_mapping = sum(1 for x in mapping if x.get("score", 1) < 0.85)
    add("weak-inside-mapping", "INFO",
        f"{weak_in_mapping} mapping row(s) have score < 0.85 (weak_candidate_review)",
        {"weakInMapping": weak_in_mapping,
         "coverageWithoutWeak": round((mapped - weak) / denom, 4) if denom else None})

    # 9 offsets
    offs = collections.Counter(x["repositoryNumber"] - x["sourceNumber"] for x in mapping)
    out["offsetDistribution"] = dict(offs.most_common())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        doc = json.load(open(a.report, encoding="utf8"))
    except Exception as e:
        print(f"cannot read {a.report}: {e}", file=sys.stderr)
        return 2
    ledger = {
        "schemaVersion": 1,
        "kind": "no-content-matcher-statistics-verification",
        "contentPolicy": "counts, ratios and checks only; no question text, no URLs",
        "note": "metadata/algorithm verification, not source truth verification",
        "thresholds": doc.get("thresholds"),
        "cases": [check_case(c) for c in doc.get("cases", [])],
    }
    out = json.dumps(ledger, ensure_ascii=False, indent=1)
    (open(a.out, "w").write(out) if a.out else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
