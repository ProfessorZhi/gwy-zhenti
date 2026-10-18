#!/usr/bin/env python3
"""Regression tests for the four-granularity gap table.

Run from the repository root:

    python3 -m unittest discover -s tools/fenbi/audit/tests -t .

These assert the invariants that stop the four numbers being confused: each
granularity is counted from its own source, A and B are disjoint units, and the
PR #74 mis-split is recorded correctly.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.dirname(HERE)
sys.path.insert(0, AUDIT)

import partitioned_gap_table as pgt  # noqa: E402


def repo_root():
    return os.path.abspath(os.path.join(AUDIT, os.pardir, os.pardir, os.pardir))


class GranularityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = pgt.build(repo_root())
        cls.g = {x["id"]: x for x in cls.doc["granularities"]}

    # ---- A: paper slots -------------------------------------------------
    def test_a_counts_46_paper_slots(self):
        self.assertEqual(self.g["A"]["count"], 46)

    def test_a_matches_the_registry_declaration(self):
        self.assertTrue(self.g["A"]["reconciliation_ok"])
        self.assertEqual(self.g["A"]["registry_declared"], 46)

    def test_a_area_breakdown(self):
        self.assertEqual(self.g["A"]["by_area"], {
            "上海": 16, "浙江": 15, "天津": 6,
            "江苏": 4, "北京": 3, "福建": 1, "深圳": 1,
        })

    def test_a_subject_split_is_19_essay_27_aptitude(self):
        self.assertEqual(self.g["A"]["by_subject"], {"行测": 27, "申论": 19})

    def test_a_recovered_two_were_essay(self):
        rec = self.g["A"]["recovered_this_round"]
        self.assertEqual(len(rec), 2)
        for item in rec:
            self.assertEqual(item["subject"], "申论")
            self.assertEqual(item["area"], "江苏")

    # ---- B: year-subject cells -----------------------------------------
    def test_b_counts_47_cells(self):
        self.assertEqual(self.g["B"]["count"], 47)

    def test_b_state_split(self):
        self.assertEqual(self.g["B"]["by_state"], {"资料缺失": 29, "待核实": 18})

    def test_b_has_no_variant_dimension(self):
        self.assertTrue(self.g["B"]["no_variant_field"])
        self.assertEqual(self.g["B"]["fields_present"], ["evidence", "path", "state"])

    def test_b_unverified_cells_are_all_tibet(self):
        self.assertEqual(self.g["B"]["unverified_areas"], ["西藏"])

    # ---- C: missing question numbers -----------------------------------
    def test_c_counts_106_question_numbers(self):
        self.assertEqual(self.g["C"]["count"], 106)
        self.assertEqual(self.g["C"]["paper_count"], 5)

    def test_c_per_paper_breakdown(self):
        counts = {(p["area"], p["year"]): p["missing_count"]
                  for p in self.g["C"]["papers"]}
        self.assertEqual(counts, {
            ("北京", "2026"): 51, ("江苏", "2026"): 42,
            ("广东", "2020"): 7, ("江苏", "2024"): 4, ("浙江", "2020"): 2,
        })

    def test_c_numbers_are_real_lists(self):
        for paper in self.g["C"]["papers"]:
            self.assertEqual(len(paper["missing_numbers"]), paper["missing_count"])

    # ---- D: source stubs -----------------------------------------------
    def test_d_counts_24_source_stubs(self):
        self.assertEqual(self.g["D"]["count"], 24)

    def test_d_rows(self):
        rows = {(r["area"], r["year"]): r["stub_count"]
                for r in self.g["D"]["rows"]}
        self.assertEqual(rows, {
            ("江苏", "2025"): 12, ("江苏", "2024"): 4,
            ("广东", "2020"): 7, ("上海", "2026"): 1,
        })

    def test_d_marks_which_row_is_derived_in_repo(self):
        origins = {(r["area"], r["year"]): r["origin"] for r in self.g["D"]["rows"]}
        self.assertEqual(origins[("江苏", "2025")], "derived-in-repo")
        self.assertEqual(origins[("江苏", "2024")], "cited-owner-report")
        self.assertEqual(origins[("广东", "2020")], "cited-owner-report")

    # ---- non-additivity -------------------------------------------------
    def test_granularities_are_never_summed(self):
        rule = self.doc["never_add"]
        self.assertIn("never be summed", rule["rule"])
        self.assertTrue(rule["a_b_disjoint"])
        self.assertEqual(rule["totals"], {"A": 46, "B": 47, "C": 106, "D": 24})

    def test_a_and_b_use_different_units(self):
        self.assertIn("paper_slot", self.g["A"]["unit"])
        self.assertIn("cell", self.g["B"]["unit"])
        self.assertNotIn("卷型", self.g["B"]["unit"].replace("无卷型维度", ""))

    # ---- corrections ----------------------------------------------------
    def test_pr74_correction_is_recorded(self):
        corrections = self.doc["corrections"]
        self.assertTrue(corrections)
        c = corrections[0]
        self.assertIn("21", c["claim"])
        self.assertIn("25", c["claim"])
        self.assertIn("19", c["correct"])
        self.assertIn("27", c["correct"])

    def test_46_equals_19_plus_27(self):
        subj = self.g["A"]["by_subject"]
        self.assertEqual(subj["申论"] + subj["行测"], 46)

    # ---- fenbi catalogue ------------------------------------------------
    def test_catalogue_only_marks_explicitly_reported_absences(self):
        absent = self.doc["fenbi_catalogue"]["explicitly_absent"]
        self.assertEqual(absent, {"北京": "2026", "江苏": "2026"})

    def test_catalogue_counts(self):
        cat = self.doc["fenbi_catalogue"]
        self.assertEqual(cat["papers_observed"], 191)
        self.assertEqual(sum(cat["by_region"].values()), 191)
        self.assertEqual(cat["readable_count"], 10)
        self.assertEqual(cat["catalogue_total_minus_readable"], 181)

    def test_catalogue_absent_is_not_claimed_as_nonexistent(self):
        note = self.doc["fenbi_catalogue"]["note"]
        self.assertIn("observed_catalog_absent", note)
        self.assertIn("NOT proof", note)

    def test_catalogue_181_is_not_called_pending_or_valid(self):
        note = self.doc["fenbi_catalogue"]["catalogue_note"]
        self.assertIn("does NOT mean", note)

    # ---- content cohort -------------------------------------------------
    def test_content_cohort_closes(self):
        cohort = self.doc["content_cohort"]
        self.assertTrue(cohort["closure"]["positions_ok"])
        self.assertTrue(cohort["closure"]["matched_ok"])
        self.assertEqual(cohort["positions"], 1210)
        self.assertEqual(cohort["source_stubs"], 24)
        self.assertEqual(cohort["remaining"], 90)
        self.assertEqual(cohort["remaining_with_image"] + cohort["remaining_text_only"],
                         cohort["remaining"])

    # ---- per-paper rows -------------------------------------------------
    def test_paper_rows_carry_all_required_fields(self):
        required = {"repo_status", "fenbi_catalogue_status", "fenbi_body_status",
                    "known_stub_count", "original_number_gaps", "quality_severity",
                    "source_rights", "next_action"}
        for row in self.doc["paper_rows"]:
            self.assertTrue(required <= set(row), row["area"])

    def test_all_five_gap_papers_have_a_row(self):
        self.assertEqual(len(self.doc["paper_rows"]), 5)

    def test_guangdong_row_is_stub_only_with_restricted_rights(self):
        row = next(r for r in self.doc["paper_rows"]
                   if r["area"] == "广东" and r["year"] == "2020")
        self.assertEqual(row["fenbi_body_status"], "stub_only")
        self.assertEqual(row["known_stub_count"], 7)
        self.assertEqual(row["source_rights"], "restricted-institution")
        self.assertEqual(row["repo_status"], "partial")

    def test_beijing_and_jiangsu_2026_are_catalogue_absent_not_nonexistent(self):
        for area in ("北京", "江苏"):
            row = next(r for r in self.doc["paper_rows"]
                       if r["area"] == area and r["year"] == "2026")
            self.assertEqual(row["fenbi_catalogue_status"], "observed_catalog_absent")
            self.assertEqual(row["next_action"],
                             "locate a source that actually holds the paper")


class HygieneTests(unittest.TestCase):
    def test_no_question_text_and_no_host_paths(self):
        doc = pgt.build(repo_root())
        blob = json.dumps(doc, ensure_ascii=False)
        for phrase in ("巍巍华山", "国家作物种质库", "压舱石", "苍鹰", "极简婚礼"):
            self.assertNotIn(phrase, blob)
        self.assertNotIn("/home/", blob)

    def test_tool_is_offline(self):
        with open(os.path.join(AUDIT, "partitioned_gap_table.py"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("urllib", text)
        self.assertNotIn("requests", text)


if __name__ == "__main__":
    unittest.main()
