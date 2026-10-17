#!/usr/bin/env python3
"""Recompute the PR #62 reorder-audit statistics from its own JSON.

Pure arithmetic over a metadata-only report. No paper, no capture, no network.
Supports both the first report schema and the R2 schema (three coverage tiers,
separate review candidates, order metrics).

Checks
  closure-source           : source-side categories sum to sourceQuestions
  closure-repository       : len(mapping) + repo_only == repositoryQuestions
  one-to-one               : no duplicated source or repository number in `mapping`
  range                    : every mapped number inside its declared range
  mapping-review-disjoint  : reviewCandidates must not also appear in `mapping`  (R2)
  tiers-arithmetic         : exact + near + weak == candidates; exact <= highConfidence <= candidates
  tiers-vs-coverage        : the three coverage ratios equal their tier counts / eligible
  tier-counts-vs-json      : approvedMapping / strictNormalizedEqual / reviewCandidate match arrays
  order-metrics            : adjacentDescents / inversions / totalPairs recomputed from `mapping`
  semantics-disclosure     : the report must say identity is normalized_equal, not byte identity
  weak-in-coverage         : reports whether the candidates tier includes weak (it should say so)

Usage:
  python3 -I verify_pr62_stats.py <report.json> [--out ledger.json]
Exit 0 = checks ran (verdicts are data). Exit 2 = unreadable input.
"""
import argparse
import collections
import json
import sys

MAPPED_KINDS_V1 = ["exact_same_number", "exact_reordered", "near_same_number",
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


def check_common(c, out, add):
    src = c["sourceQuestions"]
    rep = c["repositoryQuestions"]
    counts = c["counts"]
    mapping = c.get("mapping", [])
    src_nums = [x["sourceNumber"] for x in mapping]
    rep_nums = [x["repositoryNumber"] for x in mapping]
    repo_only = counts.get("repo_only_absent_in_source", 0)

    src_side = sum(v for k, v in counts.items() if k != "repo_only_absent_in_source")
    add("closure-source", "PASS" if src_side == src else "FAIL",
        f"source-side categories {src_side} vs sourceQuestions {src}")
    add("closure-repository", "PASS" if len(mapping) + repo_only == rep else "FAIL",
        f"mapping {len(mapping)} + repo_only {repo_only} = {len(mapping) + repo_only} vs {rep}")

    dup_src = [k for k, v in collections.Counter(src_nums).items() if v > 1]
    dup_rep = [k for k, v in collections.Counter(rep_nums).items() if v > 1]
    add("one-to-one", "PASS" if not dup_src and not dup_rep else "FAIL",
        f"{len(mapping)} pairs; duplicate source {dup_src}, duplicate repository {dup_rep}",
        {"pairs": len(mapping)})

    bad = ([x for x in src_nums if not 1 <= x <= src]
           + [x for x in rep_nums if not 1 <= x <= rep])
    add("range", "PASS" if not bad else "FAIL",
        f"{len(bad)} mapped numbers outside range", {"bad": bad[:10]})
    return mapping, src_nums, rep_nums


def check_case(c):
    out = collections.OrderedDict([("id", c.get("id")), ("sourceId", c.get("sourceId")),
                                   ("sourceQuestions", c["sourceQuestions"]),
                                   ("repositoryQuestions", c["repositoryQuestions"]),
                                   ("schema", "r2" if "tiers" in c else "v1"),
                                   ("checks", [])])

    def add(name, verdict, detail, evidence=None):
        out["checks"].append({"check": name, "verdict": verdict, "detail": detail,
                              "evidence": evidence or {}})

    mapping, src_nums, rep_nums = check_common(c, out, add)
    order_mapping = sorted(mapping, key=lambda x: x["sourceNumber"])
    seq = [x["repositoryNumber"] for x in order_mapping]

    if "tiers" not in c:
        # ---- first schema ----
        counts = c["counts"]
        img = counts.get("image_only_not_comparable", 0)
        denom = c["sourceQuestions"] - img
        mapped = sum(counts.get(k, 0) for k in MAPPED_KINDS_V1)
        weak = counts.get("weak_candidate_review", 0)
        recomputed = round(mapped / denom, 4) if denom else None
        add("coverage-denominator",
            "PASS" if recomputed is not None and abs(recomputed - c["coverage"]) <= 0.0006 else "FAIL",
            f"coverage {c['coverage']} vs recomputed {recomputed} = {mapped}/{denom}",
            {"mapped": mapped, "denominator": denom, "imageOnly": img, "weakIncluded": weak,
             "coverageWithoutWeak": round((mapped - weak) / denom, 4) if denom else None})
        gap = len(mapping) - mapped
        add("mapping-review-disjoint", "FAIL" if gap else "PASS",
            f"mapping {len(mapping)} vs classified mapped {mapped}; gap {gap} = sources classified "
            f"ambiguous that are still bound in `mapping`", {"gap": gap})
        add("semantics-disclosure", "INFO", "first schema does not state normalized_equal semantics")
    else:
        # ---- R2 schema ----
        t = c["tiers"]
        counts = c["counts"]
        weak = counts.get("weak", counts.get("weak_candidate_review", 0))
        add("tiers-arithmetic",
            "PASS" if (t["exact"] + t["near"] + t["weak"] == t["candidates"]
                       and t["exact"] <= t["highConfidence"] <= t["candidates"]) else "FAIL",
            f"exact {t['exact']} + near {t['near']} + weak {t['weak']} = "
            f"{t['exact'] + t['near'] + t['weak']} vs candidates {t['candidates']}")

        elig = t["eligible"] or 1
        calc = {"exact": round(t["exact"] / elig, 3),
                "highConfidence": round((t["exact"] + t["near"]) / elig, 3),
                "candidates": round((t["exact"] + t["near"] + t["weak"]) / elig, 3)}
        ok = all(abs(calc[k] - t["coverage" + k[0].upper() + k[1:]]) <= 0.0015 for k in calc)
        add("tiers-vs-coverage", "PASS" if ok else "FAIL",
            f"recomputed {calc} vs reported "
            f"{{{t['coverageExact']}, {t['coverageHighConfidence']}, {t['coverageCandidates']}}}")

        add("tier-counts-vs-json",
            "PASS" if (t["candidates"] == c.get("approvedMappingCount")
                       and t["exact"] == c.get("strictNormalizedEqualCount")
                       and len(c.get("reviewCandidates", [])) == c.get("reviewCandidateCount")
                       and len(mapping) == c.get("approvedMappingCount")) else "FAIL",
            f"candidates {t['candidates']} / approved {c.get('approvedMappingCount')} / "
            f"mapping {len(mapping)}; exact {t['exact']} / strict {c.get('strictNormalizedEqualCount')}; "
            f"review {len(c.get('reviewCandidates', []))} / {c.get('reviewCandidateCount')}")

        ms = {x["sourceNumber"] for x in mapping}
        rs = {x["sourceNumber"] for x in c.get("reviewCandidates", [])}
        add("mapping-review-disjoint", "PASS" if not (ms & rs) else "FAIL",
            f"mapping {len(ms)} and reviewCandidates {len(rs)}; intersection {sorted(ms & rs)}",
            {"intersection": sorted(ms & rs), "mapping": len(ms), "review": len(rs)})

        om = c.get("order", {})
        inv = inversions(seq)
        desc = descents(seq)
        total = len(seq) * (len(seq) - 1) // 2
        ok_order = (om.get("inversions") == inv and om.get("adjacentDescents") == len(desc)
                    and om.get("count") == len(mapping) and om.get("totalPairs") == total)
        add("order-metrics", "PASS" if ok_order else "FAIL",
            f"recomputed inversions {inv}, descents {len(desc)}, pairs {total} vs reported "
            f"{om.get('inversions')}, {om.get('adjacentDescents')}, {om.get('totalPairs')}",
            {"inversionRate": round(inv / total, 4) if total else None})

        sem = json.dumps(c.get("_semantics") or {}, ensure_ascii=False)
        add("weak-in-coverage", "INFO",
            f"candidates tier includes {weak} weak row(s); not usable coverage",
            {"coverageCandidates": t["coverageCandidates"],
             "coverageHighConfidence": t["coverageHighConfidence"]})

    out["offsetDistribution"] = dict(collections.Counter(
        x["repositoryNumber"] - x["sourceNumber"] for x in mapping).most_common())
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
    semantics = doc.get("semantics") or {}
    cases = []
    for c in doc.get("cases", []):
        c = dict(c)
        c["_semantics"] = semantics
        cases.append(check_case(c))
    ledger = {
        "schemaVersion": 1,
        "kind": "no-content-matcher-statistics-verification",
        "contentPolicy": "counts, ratios and checks only; no question text, no URLs",
        "note": "metadata/algorithm verification, not source truth verification",
        "thresholds": doc.get("thresholds"),
        "semantics": semantics,
        "semanticsDisclosure": {
            "statesNormalizedEqual": "normalized_equal" in json.dumps(semantics, ensure_ascii=False),
            "statesNotByteIdentity": "NOT byte" in json.dumps(semantics, ensure_ascii=False)
                                      or "not byte" in json.dumps(semantics, ensure_ascii=False).lower(),
        },
        "cases": cases,
    }
    out = json.dumps(ledger, ensure_ascii=False, indent=1)
    (open(a.out, "w").write(out) if a.out else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
