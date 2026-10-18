#!/usr/bin/env python3
"""Regression tests for the offline fenbi target inventory.

Run from the repository root:

    python3 -m unittest discover -s tools/fenbi/audit/tests -t .

These tests read the repository's own `catalog/manifest.jsonl`. Counts that are
properties of the current catalog are asserted as relationships, not magic
numbers, except for a few anchors that would indicate a real regression.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.dirname(HERE)
sys.path.insert(0, AUDIT)

import fenbi_target_inventory as inv  # noqa: E402


def repo_root():
    return os.path.abspath(os.path.join(AUDIT, os.pardir, os.pardir, os.pardir))


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = inv.build(repo_root())

    def test_every_manifest_record_is_a_distinct_raw_identity(self):
        self.assertEqual(self.doc["distinct_identities"], self.doc["manifest_records"])
        self.assertEqual(self.doc["duplicate_identities"], [])

    def test_identity_is_area_year_subject_type(self):
        records = inv.load_manifest(repo_root())
        keys = {inv.raw_identity(r) for r in records}
        self.assertEqual(len(keys), len(records))
        sample = inv.raw_identity(records[0])
        self.assertEqual(len(sample), 4)

    def test_canonical_identity_is_not_a_dedup_key(self):
        """Canonicalisation collapses aliases, so it yields FEWER keys by design."""
        records = inv.load_manifest(repo_root())
        raw = len({inv.raw_identity(r) for r in records})
        canonical = len({inv.identity(r) for r in records})
        self.assertLess(canonical, raw, "aliases should collapse some keys")
        self.assertEqual(canonical, raw - self._collapsed_count())

    def _collapsed_count(self):
        """How many records canonicalisation would collapse away."""
        recs = inv.load_manifest(repo_root())
        return sum(len(c["members"]) - 1 for c in inv.alias_collisions(recs))

    def test_alias_map_only_strips_a_trailing_marker(self):
        self.assertEqual(inv.canonical_type("乡镇卷"), ("乡镇", True))
        self.assertEqual(inv.canonical_type("行政执法卷"), ("行政执法", True))
        # Not aliased, deliberately.
        for raw in ("A卷", "B卷", "甲级", "乙级", "一卷", "二卷", "上半年", "下半年"):
            self.assertEqual(inv.canonical_type(raw), (raw, False), raw)

    def test_collisions_are_reported_and_never_auto_merged(self):
        collisions = self.doc["alias_collisions"]
        self.assertGreater(collisions["count"], 0)
        self.assertEqual(collisions["byte_identical"], 0,
                         "catalog alias pairs are divergent, not duplicates")
        self.assertEqual(collisions["divergent_content"], collisions["count"])
        for group in collisions["groups"]:
            self.assertFalse(group["auto_merge"])
            self.assertTrue(group["content_diverges"])
            self.assertIn("curat", group["reason"])
            # A survivor is suggested but not applied.
            self.assertIn(group["suggested_survivor"],
                          [m["path"] for m in group["members"]])


class GapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = inv.build(repo_root())
        cls.records = inv.load_manifest(repo_root())

    def test_the_declared_gap_anchors(self):
        summary = self.doc["missing_original_summary"]
        self.assertEqual(summary["papers_with_gaps"], 5)
        self.assertEqual(summary["total_missing_numbers"], 106)
        by_path = {b["path"]: b["count"] for b in summary["breakdown"]}
        self.assertEqual(by_path["省考/北京/2026/行测-统考.md"], 51)
        self.assertEqual(by_path["省考/江苏/2026/行测-A类.md"], 42)
        self.assertEqual(by_path["省考/广东/2020/行测-县级卷.md"], 7)
        self.assertEqual(by_path["省考/江苏/2024/行测-A类.md"], 4)
        self.assertEqual(by_path["省考/浙江/2020/行测-A类.md"], 2)

    def test_ranking_puts_the_two_named_priorities_first(self):
        top = self.doc["shortlist_top"]
        self.assertEqual(top[0]["repository_path"], "省考/北京/2026/行测-统考.md")
        self.assertEqual(top[1]["repository_path"], "省考/江苏/2026/行测-A类.md")

    def test_ranking_is_monotonic(self):
        scores = [e["information_gain"]["score"] for e in self.doc["shortlist_top"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_shortlist_length(self):
        self.assertEqual(len(self.doc["shortlist_top"]), 50)

    def test_original_total_is_derived_not_declared(self):
        """declared_questions is the file's own count; the original must be derived."""
        by_path = {e["repository_path"]: e for e in self.doc["shortlist_top"]}
        expect = {
            "省考/北京/2026/行测-统考.md": 118,
            "省考/江苏/2026/行测-A类.md": 135,
            "省考/广东/2020/行测-县级卷.md": 100,
            "省考/江苏/2024/行测-A类.md": 135,
            "省考/浙江/2020/行测-A类.md": 100,
        }
        for path, total in expect.items():
            state = by_path[path]["question_state"]
            self.assertEqual(state["original_total_estimate"], total, path)
            self.assertEqual(state["original_total_estimate"],
                             state["positions_held"] + state["missing_original_count"])

    def test_identity_caveat_is_surfaced_for_beijing_2026(self):
        entry = self.doc["shortlist_top"][0]
        caveat = entry["identity"]["caveat"]
        self.assertIsNotNone(caveat)
        self.assertIn("未归属卷型", caveat["note"])

    def test_beijing_2026_held_count_is_not_inflated(self):
        entry = self.doc["shortlist_top"][0]
        state = entry["question_state"]
        self.assertEqual(state["positions_held"], 67)
        # Missing numbers must never be added to the held count.
        self.assertLess(state["positions_held"], state["original_total_estimate"])


class CaptureReadinessTests(unittest.TestCase):
    """An unknown fenbi id must never be capture-ready."""

    @classmethod
    def setUpClass(cls):
        cls.doc = inv.build(repo_root())
        cls.by_path = {e["repository_path"]: e for e in cls.doc["shortlist_top"]}

    def test_unknown_id_is_null_and_not_ready(self):
        entry = self.by_path["省考/北京/2026/行测-统考.md"]
        self.assertIsNone(entry["capture"]["fenbi_source_id"])
        self.assertFalse(entry["capture"]["capture_ready"])
        self.assertEqual(entry["capture"]["capture_ready_reason"], "fenbi-id-unknown")

    def test_known_id_already_captured_is_not_ready_again(self):
        entry = self.by_path["省考/江苏/2024/行测-A类.md"]
        self.assertEqual(entry["capture"]["fenbi_source_id"], "4162243")
        self.assertFalse(entry["capture"]["capture_ready"])
        self.assertIn("already-", entry["capture"]["capture_ready_reason"])

    def test_known_id_not_yet_captured_is_ready(self):
        entry = self.by_path["省考/浙江/2020/行测-A类.md"]
        self.assertEqual(entry["capture"]["fenbi_source_id"], "96454")
        self.assertTrue(entry["capture"]["capture_ready"])

    def test_ids_are_only_ever_observed_values(self):
        allowed = {v["id"] for v in inv.KNOWN_FENBI_IDS.values()}
        for entry in self.doc["shortlist_top"]:
            fid = entry["capture"]["fenbi_source_id"]
            if fid is not None:
                self.assertIn(fid, allowed)
                self.assertIsNotNone(entry["capture"]["evidence"])


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = inv.build(repo_root())

    def test_handoff_size_is_within_the_requested_range(self):
        self.assertGreaterEqual(self.doc["handoff"]["count"], 20)
        self.assertLessEqual(self.doc["handoff"]["count"], 30)

    def test_handoff_carries_directory_identity_only(self):
        for entry in self.doc["handoff"]["entries"]:
            for key in ("area", "year", "subject", "paper_type"):
                self.assertIn(key, entry)
            # No content-bearing keys.
            for forbidden in ("stem", "options", "answer", "explanation", "text", "content"):
                self.assertNotIn(forbidden, entry)

    def test_unknown_ids_in_handoff_are_lookup_targets_not_ready(self):
        for entry in self.doc["handoff"]["entries"]:
            if entry["fenbi_source_id"] is None:
                self.assertTrue(entry["catalog_lookup_needed"])
                self.assertFalse(entry["capture_ready"])
                self.assertEqual(entry["id_source"], "unknown")
            else:
                self.assertFalse(entry["catalog_lookup_needed"])
                self.assertIsNotNone(entry["evidence"])

    def test_handoff_excludes_already_captured_papers(self):
        for entry in self.doc["handoff"]["entries"]:
            self.assertNotIn(entry["capture_status"],
                             ("captured", "initialized-captured"))

    def test_handoff_does_not_leak_content(self):
        blob = json.dumps(self.doc["handoff"], ensure_ascii=False)
        for phrase in ("巍巍华山", "国家作物种质库", "压舱石", "苍鹰"):
            self.assertNotIn(phrase, blob)


class HygieneTests(unittest.TestCase):
    def test_tool_is_metadata_only(self):
        with open(os.path.join(AUDIT, "fenbi_target_inventory.py"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("urllib", text)
        self.assertNotIn("requests", text)
        self.assertNotIn("/home/", text)

    def test_policy_block_states_the_rules(self):
        doc = inv.build(repo_root(), top=5, handoff=5)
        joined = " ".join(doc["policy"])
        self.assertIn("never capture-ready", joined)
        self.assertIn("never auto-merged", joined)
        self.assertIn("placeholder is not a question", joined)


if __name__ == "__main__":
    unittest.main()
