#!/usr/bin/env python3
"""Offline tests for verify_pr62_stats.py.

    python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v

All fixtures are synthetic dictionaries; nothing here reads a paper or a capture.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_pr62_stats as V  # noqa: E402


def case(**over):
    base = {
        "id": "synthetic", "sourceId": "0", "sourceQuestions": 4, "repositoryQuestions": 4,
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
        # 3 descents but many more inversions
        seq = [4, 3, 2, 1]
        self.assertEqual(len(V.descents(seq)), 3)
        self.assertGreater(V.inversions(seq), len(V.descents(seq)))


class TestCoverageDenominator(unittest.TestCase):
    def test_matches_when_formula_holds(self):
        out = V.check_case(case())
        self.assertEqual(by_name(out)["coverage-denominator"]["verdict"], "PASS")

    def test_detects_wrong_denominator(self):
        # report claims 0.75 but 2/4 = 0.5
        out = V.check_case(case(coverage=0.75))
        self.assertEqual(by_name(out)["coverage-denominator"]["verdict"], "FAIL")

    def test_image_only_leaves_denominator(self):
        c = case(sourceQuestions=5, repositoryQuestions=4, coverage=0.5,
                 counts={"exact_same_number": 1, "exact_reordered": 1,
                         "image_only_not_comparable": 1, "repo_only_absent_in_source": 2,
                         "ambiguous_multi_candidate": 0})
        out = V.check_case(c)
        ev = by_name(out)["coverage-denominator"]["evidence"]
        self.assertEqual(ev["denominator"], 4)   # 5 - 1

    def test_coverage_without_weak_is_reported(self):
        c = case(counts={"exact_same_number": 1, "exact_reordered": 1,
                         "weak_candidate_review": 1, "ambiguous_multi_candidate": 0,
                         "image_only_not_comparable": 0, "repo_only_absent_in_source": 2},
                 coverage=0.75, exactPairs=2,
                 mapping=[{"sourceNumber": 1, "repositoryNumber": 2, "exact": True, "score": 1},
                          {"sourceNumber": 2, "repositoryNumber": 1, "exact": True, "score": 1},
                          {"sourceNumber": 3, "repositoryNumber": 3, "exact": False, "score": 0.5}])
        out = V.check_case(c)
        ev = by_name(out)["coverage-denominator"]["evidence"]
        self.assertEqual(ev["weakIncluded"], 1)
        self.assertAlmostEqual(ev["coverageWithoutWeak"], 0.5, places=2)


class TestOneToOne(unittest.TestCase):
    def test_duplicate_source_number_fails(self):
        c = case(mapping=[{"sourceNumber": 1, "repositoryNumber": 1, "exact": True, "score": 1},
                          {"sourceNumber": 1, "repositoryNumber": 2, "exact": True, "score": 1}])
        self.assertEqual(by_name(V.check_case(c))["one-to-one"]["verdict"], "FAIL")

    def test_duplicate_repository_number_fails(self):
        c = case(mapping=[{"sourceNumber": 1, "repositoryNumber": 1, "exact": True, "score": 1},
                          {"sourceNumber": 2, "repositoryNumber": 1, "exact": True, "score": 1}])
        self.assertEqual(by_name(V.check_case(c))["one-to-one"]["verdict"], "FAIL")

    def test_out_of_range_fails(self):
        c = case(mapping=[{"sourceNumber": 9, "repositoryNumber": 1, "exact": True, "score": 1}])
        self.assertEqual(by_name(V.check_case(c))["range"]["verdict"], "FAIL")


class TestClosure(unittest.TestCase):
    def test_source_closure_mismatch_fails(self):
        c = case(counts={"exact_same_number": 1, "ambiguous_multi_candidate": 0,
                         "image_only_not_comparable": 0, "repo_only_absent_in_source": 2})
        self.assertEqual(by_name(V.check_case(c))["closure-source"]["verdict"], "FAIL")

    def test_repository_closure_mismatch_fails(self):
        c = case(counts={"exact_same_number": 1, "exact_reordered": 1,
                         "ambiguous_multi_candidate": 0, "image_only_not_comparable": 0,
                         "repo_only_absent_in_source": 5})
        self.assertEqual(by_name(V.check_case(c))["closure-repository"]["verdict"], "FAIL")


class TestMappingVsClassified(unittest.TestCase):
    """The core finding: `mapping` may bind a source the report calls ambiguous."""

    def test_gap_is_flagged(self):
        # 3 mapping rows but only 2 classified as mapped -> gap 1 (an ambiguous binding)
        c = case(counts={"exact_same_number": 1, "exact_reordered": 1,
                         "ambiguous_multi_candidate": 1, "image_only_not_comparable": 0,
                         "repo_only_absent_in_source": 1},
                 mapping=[{"sourceNumber": 1, "repositoryNumber": 2, "exact": True, "score": 1},
                          {"sourceNumber": 2, "repositoryNumber": 1, "exact": True, "score": 1},
                          {"sourceNumber": 3, "repositoryNumber": 3, "exact": True, "score": 1}])
        out = by_name(V.check_case(c))
        self.assertEqual(out["mapping-vs-classified"]["verdict"], "FAIL")
        self.assertEqual(out["mapping-vs-classified"]["evidence"]["gap"], 1)

    def test_no_gap_passes(self):
        self.assertEqual(by_name(V.check_case(case()))["mapping-vs-classified"]["verdict"], "PASS")


class TestExactSemantics(unittest.TestCase):
    def test_exact_pair_delta_is_reported(self):
        # 2 exact mapping rows but only 1 classified exact -> 1 exact pair went ambiguous
        c = case(counts={"exact_same_number": 1, "ambiguous_multi_candidate": 1,
                         "image_only_not_comparable": 0, "repo_only_absent_in_source": 2})
        ev = by_name(V.check_case(c))["exact-pairs-vs-classified"]["evidence"]
        self.assertEqual(ev["delta"], 1)


class TestMonotonicity(unittest.TestCase):
    def test_reports_both_descents_and_inversions(self):
        c = case(mapping=[{"sourceNumber": 1, "repositoryNumber": 4, "exact": True, "score": 1},
                          {"sourceNumber": 2, "repositoryNumber": 3, "exact": True, "score": 1},
                          {"sourceNumber": 3, "repositoryNumber": 2, "exact": True, "score": 1},
                          {"sourceNumber": 4, "repositoryNumber": 1, "exact": True, "score": 1}])
        ev = by_name(V.check_case(c))["monotonicity"]["evidence"]
        self.assertEqual(ev["inversions"], 6)
        self.assertEqual(len(ev["descents"]), 3)
        self.assertEqual(ev["totalPairs"], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
