import unittest
from check_batch_summary import parse_report

PREFIX = '''| # | 卷 | sourceId | 初始化 | 复用 | 题数 | 有效题干 | 占位桩 | 材料 | 章节 | 图片(唯一SHA) | 仓库 matched |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 国考2026 地市级 | 5823068 | **新建 1 次** | 否 | 130 | 130 | 0 | 5 | 6 | 31 | **129/130** |
| 2 | 国考2026 行政执法 | 5823067 | **新建 1 次** | 否 | 130 | 130 | 0 | 5 | 6 | 28 | **129/130** |
| 3 | 上海2026 统考 | 8472470 | **新建 1 次** | 否 | 130 | 129 | 1 | 10 | 6 | 44 | **0/130** ⚠️ |
| 4 | 天津2026 统考 | 8399759 | **新建 1 次** | 否 | 120 | 120 | 0 | 4 | 6 | 27 | **119/120** |
| 5 | 广东2026 统考 | 8399765 | **新建 1 次** | 否 | 90 | 89 | 0 | 4 | 7 | 26 | **12/90** ⚠️ |
'''
SUFFIX = '| — | **合计** | — | **5 次** | **0** | **600** | **{valid}** | **1** | — | — | **156** | — |'


class TestSummary(unittest.TestCase):
    def test_fixed_is_consistent_and_unclassified_preserved(self):
        r = parse_report(PREFIX + SUFFIX.format(valid=598))
        self.assertTrue(r['passed'])
        self.assertEqual(r['totals']['questions'], 600)
        self.assertEqual(r['totals']['valid_stems'], 598)
        self.assertEqual(r['totals']['unclassified'], 1)
        self.assertEqual(r['totals']['matched'], 389)
        self.assertEqual(r['by_paper'][-1]['unclassified'], 1)

    def test_original_report_caught(self):
        r = parse_report(PREFIX + SUFFIX.format(valid=597))
        self.assertFalse(r['passed'])
        self.assertEqual(r['mismatches']['valid_stems'], {'reported': 597, 'sum_of_rows': 598})

    def test_overcount_refused(self):
        s = PREFIX.replace('| 90 | 89 | 0 |', '| 90 | 91 | 0 |')
        with self.assertRaisesRegex(ValueError, 'exceed'):
            parse_report(s + SUFFIX.format(valid=600))

    def test_duplicate_source_refused(self):
        s = PREFIX.replace('8399765', '5823068')
        with self.assertRaisesRegex(ValueError, 'duplicate source'):
            parse_report(s + SUFFIX.format(valid=598))

    def test_wrong_match_denominator_refused(self):
        s = PREFIX.replace('**12/90**', '**12/91**')
        with self.assertRaisesRegex(ValueError, 'denominator'):
            parse_report(s + SUFFIX.format(valid=598))


if __name__ == '__main__':
    unittest.main()
