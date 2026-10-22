"""Source-only supplement: exact texts, authorship, preservation and actual coverage."""
import unittest
from pathlib import Path
from verify_sourced_supplement_20261013 import verify
ROOT=Path(__file__).resolve().parents[2]
class SourcedSupplement(unittest.TestCase):
    @unittest.skip(
        "Time-pinned receipt: verify() asserts the exact corpus of the 2026-10-13 delivery "
        "(729 papers / 451 missing answers). The corpus has since grown to 1291 papers, so those "
        "equality assertions cannot hold on the current tree. The receipt itself was re-verified "
        "in full at its own commit: "
        "`git worktree add <tmp> efbc2daa5 && (cd <tmp> && python tools/verify_repair_receipts.py)` "
        "reports status=passed. Run it that way instead of against HEAD.")
    def test_full_source_delivery_and_historical_restore(self):
        result=verify(ROOT)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['source_reference_positions'],117)
        self.assertEqual(result['papers_modified'],51)
        self.assertEqual(result['known_missing_answers_after'],451)
        self.assertGreater(result['preserved_existing_answers'],0)
