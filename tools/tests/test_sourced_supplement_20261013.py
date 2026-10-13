"""Source-only supplement: exact texts, authorship, preservation and actual coverage."""
import unittest
from pathlib import Path
from verify_sourced_supplement_20261013 import verify
ROOT=Path(__file__).resolve().parents[2]
class SourcedSupplement(unittest.TestCase):
    def test_full_source_delivery_and_historical_restore(self):
        result=verify(ROOT)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['source_reference_positions'],117)
        self.assertEqual(result['papers_modified'],51)
        self.assertEqual(result['known_missing_answers_after'],451)
        self.assertGreater(result['preserved_existing_answers'],0)
