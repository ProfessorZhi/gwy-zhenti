#!/usr/bin/env python3
"""Offline tests for the metadata-only provenance / identity / count gate.

    python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v

Every fixture is a synthetic metadata dict. No paper, capture, image or credential
is read.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import metadata_provenance_gate as G  # noqa: E402


def official(**over):
    m = {"label": "synthetic", "真题性质": "正式真题",
         "来源明细": "restricted-capture (v6)", "再分发许可": ""}
    m.update(over)
    return m


class TestR1RestrictedLabelling(unittest.TestCase):
    def test_official_claim_with_restricted_source_and_no_permission(self):
        r = G.assess_restricted_label(
            official(来源明细="某公开库 SK_某省_2026_通用卷 · 粉笔会员采(v6)",
                     校验状态="粉笔系上游，再分发条件未核实"))
        self.assertEqual(r["verdict"], "provenance_uncertain")
        self.assertFalse(r["verified"])
        self.assertIn("粉笔会员", r["evidence"]["restrictedMarkers"])

    def test_official_claim_with_permission_is_allowed(self):
        r = G.assess_restricted_label(
            official(来源明细="粉笔会员采", 再分发许可="allowed"))
        self.assertEqual(r["verdict"], "verified_allowed")
        self.assertTrue(r["verified"])

    def test_official_claim_without_restricted_marker(self):
        r = G.assess_restricted_label(official(来源明细="公开政府公告"))
        self.assertEqual(r["verdict"], "no_conflict")
        self.assertTrue(r["verified"])

    def test_non_official_claim_with_restricted_source_is_not_blocking(self):
        r = G.assess_restricted_label(
            {"真题性质": "回忆整理参考", "来源明细": "粉笔会员采", "再分发许可": ""})
        self.assertEqual(r["verdict"], "no_conflict")
        self.assertFalse(r["verified"])

    def test_restricted_marker_only_in_verification_field(self):
        r = G.assess_restricted_label(
            official(来源明细="公开渠道", 校验状态="再分发条件未核实"))
        self.assertEqual(r["verdict"], "provenance_uncertain")

    def test_never_claims_a_legal_determination(self):
        r = G.assess_restricted_label(official(来源明细="粉笔会员采"))
        self.assertIn("requiredAction", r)
        self.assertNotIn("illegal", r["reason"].lower())


class TestR2Identity(unittest.TestCase):
    def test_generic_vs_composite(self):
        r = G.assess_identity({"卷型": "通用卷", "claimed_equivalent": "综合卷"})
        self.assertEqual(r["verdict"], "identity_conflict")
        self.assertEqual(r["conflicts"][0]["kind"], "generic-vs-composite")

    def test_village_cadre_counted_as_shenlun(self):
        r = G.assess_identity({"卷型": "D（优秀村干部）", "科目": "申论"})
        self.assertEqual(r["verdict"], "identity_conflict")
        self.assertEqual(r["conflicts"][0]["kind"], "village-cadre-not-shenlun")

    def test_village_cadre_as_xingce_is_fine(self):
        r = G.assess_identity({"卷型": "D（优秀村干部）", "科目": "行测"})
        self.assertEqual(r["verdict"], "no_conflict")

    def test_enforcement_special_recruitment_is_not_a_third_paper(self):
        r = G.assess_identity({"卷型": "行政执法专项", "aliases": ["市考第三类"]})
        self.assertEqual(r["verdict"], "identity_conflict")
        self.assertEqual(r["conflicts"][0]["kind"], "separate-recruitment-not-third-paper")

    def test_plain_enforcement_variant_is_not_flagged(self):
        r = G.assess_identity({"卷型": "行政执法", "科目": "申论", "来源明细": "公开公告"})
        self.assertEqual(r["verdict"], "no_conflict")

    def test_enforcement_labelled_as_municipal_is_needs_review(self):
        # real shape: variant 行政执法卷, source asserts 市考《申论》, no 专项/招录 marker
        r = G.assess_identity({"卷型": "行政执法卷", "科目": "申论",
                               "来源明细": "2017年上海市公考《申论》题（行政执法卷）（网友回忆版）"})
        self.assertEqual(r["verdict"], "identity_conflict")
        kinds = {c["kind"]: c for c in r["conflicts"]}
        self.assertIn("enforcement-special-labelled-as-municipal", kinds)
        self.assertEqual(kinds["enforcement-special-labelled-as-municipal"]["severity"], "needs_review")

    def test_enforcement_marked_special_is_not_flagged_again(self):
        r = G.assess_identity({"卷型": "行政执法卷", "科目": "申论",
                               "来源明细": "上海市行政执法类公务员专项招录 市考《申论》"})
        self.assertEqual(r["verdict"], "no_conflict")

    def test_multiple_conflicts_are_all_reported(self):
        r = G.assess_identity({"卷型": "行政执法专项", "科目": "申论",
                               "aliases": ["市考B卷"], "claimed_equivalent": "综合卷"})
        kinds = {c["kind"] for c in r["conflicts"]}
        self.assertIn("separate-recruitment-not-third-paper", kinds)


class TestR3CountBoundary(unittest.TestCase):
    def test_unchanged_remaining_passes(self):
        r = G.assess_count_boundary(46, 46, recovered=0, reclassified=11)
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(r["evidence"]["reclassifiedSlotsMustStayInSomeDenominator"])

    def test_reclassification_without_recovery_fails(self):
        r = G.assess_count_boundary(46, 35, recovered=0, reclassified=11)
        self.assertEqual(r["verdict"], "FAIL")

    def test_reduction_backed_by_recovery_passes(self):
        r = G.assess_count_boundary(46, 44, recovered=2)
        self.assertEqual(r["verdict"], "PASS")

    def test_reduction_partly_backed_fails(self):
        r = G.assess_count_boundary(46, 43, recovered=2)
        self.assertEqual(r["verdict"], "FAIL")


class TestR4ImagePromotion(unittest.TestCase):
    def _row(self, **over):
        r = {"grade": "exact", "autoAcceptable": True, "flags": [],
             "images": {"available": True, "similarity": 0}}
        r.update(over)
        return r

    def test_verified_conflict_promoted_to_exact_fails(self):
        r = G.assess_image_promotion(self._row())
        self.assertEqual(r["verdict"], "FAIL")
        self.assertTrue(r["evidence"]["verifiedConflictIsPositiveEvidenceOfDifference"])

    def test_verified_conflict_without_auto_accept_passes(self):
        r = G.assess_image_promotion(self._row(autoAcceptable=False))
        self.assertEqual(r["verdict"], "PASS")

    def test_verified_identical_is_fine(self):
        r = G.assess_image_promotion(self._row(images={"available": True, "similarity": 1}))
        self.assertEqual(r["verdict"], "PASS")

    def test_unavailable_evidence_is_not_this_rule(self):
        r = G.assess_image_promotion(
            self._row(images={"available": False, "similarity": 0},
                      flags=["image_evidence_unverified"]))
        self.assertEqual(r["verdict"], "PASS")

    def test_non_exact_grade_is_not_promotion(self):
        r = G.assess_image_promotion(self._row(grade="strong"))
        self.assertEqual(r["verdict"], "PASS")


class TestDriver(unittest.TestCase):
    def test_record_aggregates_blocking_rules(self):
        rec = G.assess_record({
            "label": "synthetic",
            "真题性质": "正式真题", "来源明细": "粉笔会员采", "再分发许可": "",
            "卷型": "D（优秀村干部）", "科目": "申论",
            "count_boundary": {"before": 46, "after": 46, "recovered": 0, "reclassified": 11},
            "receipt_rows": [{"grade": "exact", "autoAcceptable": True,
                              "images": {"available": True, "similarity": 0}}],
        })
        self.assertEqual(len(rec["blocking"]), 3)
        self.assertIn("R1-restricted-source-labelling", rec["blocking"])
        self.assertIn("R2-identity-conflation", rec["blocking"])
        self.assertIn("R4-image-evidence-promotion", rec["blocking"])

    def test_clean_record_has_no_blocking(self):
        rec = G.assess_record({
            "label": "clean", "真题性质": "回忆整理参考", "来源明细": "公开公告",
            "卷型": "C类", "科目": "申论",
            "count_boundary": {"before": 46, "after": 46, "recovered": 0},
        })
        self.assertEqual(rec["blocking"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
