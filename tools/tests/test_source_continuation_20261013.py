import unittest
from pathlib import Path
from verify_source_continuation_20261013 import verify
class SourceContinuation(unittest.TestCase):
 def test_existing_sources_original_exam_and_actual_coverage(self):
  result=verify(Path(__file__).resolve().parents[2])
  self.assertEqual(result["status"],"passed")
  self.assertEqual(result["source_reference_positions"],140)
  self.assertEqual(result["papers_modified"],75)
  self.assertEqual(result["known_missing_answers_after"],311)
  self.assertGreater(result["preserved_existing_answers"],0)
