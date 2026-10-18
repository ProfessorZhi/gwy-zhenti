#!/usr/bin/env python3
"""Offline tests for verify_pr62_stats.py (supports both report schemas).

    python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v

All fixtures are synthetic dictionaries; nothing here reads a paper or a capture.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_pr62_stats as V  # noqa: E402


def case_v1(**over):
    base = {
        "id": "synthetic-v1", "sourceId": "0", "sourceQuestions": 4, "repositoryQuestions": 4,
        "coverage": 0.5,
        "counts": {"exact_same_number": 1, "exact_reordered": 1,
                   "ambiguous_multi_candidate": 0, "image_only_not_comparable": 0,
                   "repo_only_absent_in_source": 2},
        "exactPairs": 2,
        "mapping": [
            {"sourceNumber": 1, "repositoryNumber": 2, "exact": True, "score": 1},
            {"sourceNumber": 2, "repositoryNumber": 1, "exact": True, "score": 1},
        ],
    }
    base.update(over)
    return base


def case_v2(**over):
    """R2 schema: three coverage tiers, separate review candidates, order metrics."""
    mapping = [
        {"sourceNumber": 1, "repositoryNumber": 2},
        {"sourceNumber": 2, "repositoryNumber": 1},
        {"sourceNumber": 3, "repositoryNumber": 4},
    ]
    base = {
        "id": "synthetic-v2", "sourceId": "0", "sourceQuestions": 5, "repositoryQuestions": 5,
        "counts": {"normalized_equal_reordered": 3, "near": 0, "weak": 0,
                   "manual_review_ambiguous": 1, "unmatched_no_candidate": 1,
                   "repo_only_absent_in_source": 2},
        "tiers": {"eligible": 5, "exact": 3, "near": 0, "weak": 0,
                  "highConfidence": 3, "candidates": 3,
                  "coverageExact": 0.6, "coverageHighConfidence": 0.6, "coverageCandidates": 0.6},
        "approvedMappingCount": 3, "strictNormalizedEqualCount": 3, "reviewCandidateCount": 1,
        "mapping": mapping,
        "reviewCandidates": [{"sourceNumber": 4, "repositoryIndexes": [3, 4], "score": 1}],
        "order": {"count": 3, "adjacentDescents": 1, "inversions": 1,
                  "totalPairs": 3, "inversionRate": 0.3333},
        "offsets": {"1": 2, "0": 1},
    }
    base.update(over)
    return base


def by_name(out):
    return {c["check"]: c for c in out["checks"]}


class TestInversions(unittest.TestCase):
    def test_sorted_has_none(self):
        self.assertEqual(V.inversions([1, 2, 3, 4]), 0)
        self.assertEqual(V.descents([1, 2, 3, 4]), [])

    def test_reverse_is_maximal(self):
        self.assertEqual(V.inversions([4, 3, 2, 1]), 6)

    def test_descents_are_adjacent_only(self):
        self.assertEqual(V.descents([1, 3, 2, 4]), [(3, 2)])
        self.assertEqual(len(V.descents([4, 3, 2, 1])), 3)
        self.assertGreater(V.inversions([4, 3, 2, 1]), len(V.descents([4, 3, 2, 1])))


class TestSchemaDetection(unittest.TestCase):
    def test_detects_v1_and_v2(self):
        self.assertEqual(V.check_case(case_v1())["schema"], "v1")
        self.assertEqual(V.check_case(case_v2())["schema"], "r2")


class TestV1Coverage(unittest.TestCase):
    def test_matches_when_formula_holds(self):
        self.assertEqual(by_name(V.check_case(case_v1()))["coverage-denominator"]["verdict"], "PASS")

    def test_detects_wrong_denominator(self):
        self.assertEqual(by_name(V.check_case(case_v1(coverage=0.75)))["coverage-denominator"]["verdict"], "FAIL")

    def test_image_only_leaves_denominator(self):
        c = case_v1(sourceQuestions=5, coverage=0.5,
                    counts={"exact_same_number": 1, "exact_reordered": 1,
                            "image_only_not_comparable": 1, "repo_only_absent_in_source": 2,
                            "ambiguous_multi_candidate": 0})
        ev = by_name(V.check_case(c))["coverage-denominator"]["evidence"]
        self.assertEqual(ev["denominator"], 4)

    def test_coverage_without_weak_is_reported(self):
        c = case_v1(coverage=0.75, counts={"exact_same_number": 1, "exact_reordered": 1,
                                           "weak_candidate_review": 1,
                                           "image_only_not_comparable": 0,
                                           "repo_only_absent_in_source": 2,
                                           "ambiguous_multi_candidate": 0},
                    mapping=[{"sourceNumber": 1, "repositoryNumber": 2, "exact": True, "score": 1},
                             {"sourceNumber": 2, "repositoryNumber": 1, "exact": True, "score": 1},
                             {"sourceNumber": 3, "repositoryNumber": 3, "exact": False, "score": 0.5}])
        ev = by_name(V.check_case(c))["coverage-denominator"]["evidence"]
        self.assertEqual(ev["weakIncluded"], 1)
        self.assertAlmostEqual(ev["coverageWithoutWeak"], 0.5, places=2)

    def test_v1_ambiguous_gap_fails(self):
        c = case_v1(counts={"exact_same_number": 1, "exact_reordered": 1,
                            "ambiguous_multi_candidate": 1, "image_only_not_comparable": 0,
                            "repo_only_absent_in_source": 1},
                    mapping=[{"sourceNumber": 1, "repositoryNumber": 2, "exact": True, "score": 1},
                             {"sourceNumber": 2, "repositoryNumber": 1, "exact": True, "score": 1},
                             {"sourceNumber": 3, "repositoryNumber": 3, "exact": True, "score": 1}])
        out = by_name(V.check_case(c))["mapping-review-disjoint"]
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(out["evidence"]["gap"], 1)


class TestV2Tiers(unittest.TestCase):
    def test_tiers_arithmetic_passes(self):
        self.assertEqual(by_name(V.check_case(case_v2()))["tiers-arithmetic"]["verdict"], "PASS")

    def test_tiers_arithmetic_detects_bad_sum(self):
        c = case_v2(tiers={**case_v2()["tiers"], "candidates": 4})
        self.assertEqual(by_name(V.check_case(c))["tiers-arithmetic"]["verdict"], "FAIL")

    def test_tiers_vs_coverage_passes(self):
        self.assertEqual(by_name(V.check_case(case_v2()))["tiers-vs-coverage"]["verdict"], "PASS")

    def test_tiers_vs_coverage_detects_wrong_ratio(self):
        c = case_v2(tiers={**case_v2()["tiers"], "coverageCandidates": 0.9})
        self.assertEqual(by_name(V.check_case(c))["tiers-vs-coverage"]["verdict"], "FAIL")

    def test_tier_counts_vs_json(self):
        self.assertEqual(by_name(V.check_case(case_v2()))["tier-counts-vs-json"]["verdict"], "PASS")
        c = case_v2(approvedMappingCount=99)
        self.assertEqual(by_name(V.check_case(c))["tier-counts-vs-json"]["verdict"], "FAIL")

    def test_mapping_review_must_be_disjoint(self):
        self.assertEqual(by_name(V.check_case(case_v2()))["mapping-review-disjoint"]["verdict"], "PASS")
        bad = case_v2(reviewCandidates=[{"sourceNumber": 1, "repositoryIndexes": [2, 3], "score": 1}])
        out = by_name(V.check_case(bad))["mapping-review-disjoint"]
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(out["evidence"]["intersection"], [1])

    def test_weak_tier_scales_candidates(self):
        t = {**case_v2()["tiers"], "weak": 2, "candidates": 5,
             "coverageCandidates": 1.0, "coverageHighConfidence": 0.6}
        c = case_v2(tiers=t, counts={**case_v2()["counts"], "weak": 2}, mapping=[
            {"sourceNumber": 1, "repositoryNumber": 2},
            {"sourceNumber": 2, "repositoryNumber": 1},
            {"sourceNumber": 3, "repositoryNumber": 4},
            {"sourceNumber": 4, "repositoryNumber": 5},
            {"sourceNumber": 5, "repositoryNumber": 3}],
            approvedMappingCount=5)
        out = by_name(V.check_case(c))
        self.assertEqual(out["tiers-arithmetic"]["verdict"], "PASS")
        self.assertEqual(out["weak-in-coverage"]["verdict"], "INFO")


class TestV2OrderMetrics(unittest.TestCase):
    def test_recomputes_inversions_and_descents(self):
        # rep sequence [2,1,4] -> one descent (2>1), one inversion
        self.assertEqual(by_name(V.check_case(case_v2()))["order-metrics"]["verdict"], "PASS")

    def test_detects_wrong_inversion_count(self):
        c = case_v2(order={"count": 3, "adjacentDescents": 1, "inversions": 99,
                           "totalPairs": 3, "inversionRate": 1})
        self.assertEqual(by_name(V.check_case(c))["order-metrics"]["verdict"], "FAIL")


class TestCommonChecks(unittest.TestCase):
    def test_duplicate_source_number_fails(self):
        c = case_v1(mapping=[{"sourceNumber": 1, "repositoryNumber": 1, "exact": True, "score": 1},
                             {"sourceNumber": 1, "repositoryNumber": 2, "exact": True, "score": 1}])
        self.assertEqual(by_name(V.check_case(c))["one-to-one"]["verdict"], "FAIL")

    def test_duplicate_repository_number_fails(self):
        c = case_v1(mapping=[{"sourceNumber": 1, "repositoryNumber": 1, "exact": True, "score": 1},
                             {"sourceNumber": 2, "repositoryNumber": 1, "exact": True, "score": 1}])
        self.assertEqual(by_name(V.check_case(c))["one-to-one"]["verdict"], "FAIL")

    def test_out_of_range_fails(self):
        c = case_v1(mapping=[{"sourceNumber": 9, "repositoryNumber": 1, "exact": True, "score": 1}])
        self.assertEqual(by_name(V.check_case(c))["range"]["verdict"], "FAIL")

    def test_source_closure_mismatch_fails(self):
        c = case_v1(counts={"exact_same_number": 1, "ambiguous_multi_candidate": 0,
                            "image_only_not_comparable": 0, "repo_only_absent_in_source": 2})
        self.assertEqual(by_name(V.check_case(c))["closure-source"]["verdict"], "FAIL")

    def test_repository_closure_mismatch_fails(self):
        c = case_v1(counts={"exact_same_number": 1, "exact_reordered": 1,
                            "ambiguous_multi_candidate": 0, "image_only_not_comparable": 0,
                            "repo_only_absent_in_source": 5})
        self.assertEqual(by_name(V.check_case(c))["closure-repository"]["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
