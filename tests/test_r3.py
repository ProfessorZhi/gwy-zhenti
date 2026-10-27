#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synthetic regression tests for the R3 media/layout tools.

Everything here is built from strings in this file -- no repository, no source
lane, no network.  That is deliberate: the tests must keep working when the
live repo moves (it moves several times a day), so they encode *rules*, not
snapshots of current data.

Run:  python3 -I -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))

import r3lib            # noqa: E402
import r3_tablescan     # noqa: E402
import r3_symbolscan    # noqa: E402


def kinds(cells):
    return [r3lib.cell_kind(c) for c in cells]


class TestSplitRow(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(r3lib.split_row('| a | b | c |'), ['a', 'b', 'c'])

    def test_no_outer_pipes(self):
        self.assertEqual(r3lib.split_row('a | b'), ['a', 'b'])

    def test_escaped_pipe(self):
        self.assertEqual(r3lib.split_row(r'| a \| b | c |'), [r'a \| b', 'c'])

    def test_empty_cells_preserved(self):
        self.assertEqual(r3lib.split_row('|  |  |'), ['', ''])


class TestTableParsing(unittest.TestCase):
    def test_simple_table(self):
        lines = ['| a | b |', '| --- | --- |', '| 1 | 2 |', '| 3 | 4 |']
        tables = list(r3lib.iter_pipe_tables(lines))
        self.assertEqual(len(tables), 1)
        t = tables[0]
        self.assertEqual(t.header, ['a', 'b'])
        self.assertEqual(t.nrows, 2)
        self.assertEqual(t.start, 1)

    def test_table_inside_fence_is_ignored(self):
        lines = ['```', '| a | b |', '| --- | --- |', '| 1 | 2 |', '```']
        self.assertEqual(list(r3lib.iter_pipe_tables(lines)), [])

    def test_pipe_rows_without_separator_are_not_a_table(self):
        lines = ['| a | b |', '| 1 | 2 |']
        self.assertEqual(list(r3lib.iter_pipe_tables(lines)), [])

    def test_ragged_body_is_tolerated(self):
        lines = ['| a | b | c |', '| --- | --- | --- |', '| 1 | 2 |']
        t = list(r3lib.iter_pipe_tables(lines))[0]
        self.assertEqual(t.body_cell(0, 2), '')


class TestCellKind(unittest.TestCase):
    def test_numbers_and_placeholders(self):
        self.assertEqual(kinds(['7', '?', '（ ）', '1/2']),
                         ['NUM', 'PLACEHOLDER', 'PLACEHOLDER', 'FRACTION'])

    def test_year_is_time_not_number(self):
        self.assertEqual(r3lib.cell_kind('2018年'), 'TIME')
        self.assertEqual(r3lib.cell_kind('2018'), 'TIME')

    def test_known_unit_is_a_number(self):
        self.assertEqual(r3lib.cell_kind('45元'), 'NUM')
        self.assertEqual(r3lib.cell_kind('3.5亿元'), 'NUM')

    def test_unknown_cjk_suffix_is_text(self):
        # This is the regression that mattered: an open "number + CJK" pattern
        # swallowed real column labels such as "2次逻辑".
        self.assertEqual(r3lib.cell_kind('2次逻辑'), 'TEXT')

    def test_single_letter_is_var(self):
        self.assertEqual(r3lib.cell_kind('a'), 'VAR')
        self.assertEqual(r3lib.cell_kind('x'), 'VAR')

    def test_words_are_text(self):
        self.assertEqual(r3lib.cell_kind('东部地区'), 'TEXT')


class TestTimeAxis(unittest.TestCase):
    def test_ascending_years(self):
        self.assertTrue(r3lib.row_is_time_axis(['2018', '2019', '2020']))

    def test_months_and_days(self):
        self.assertTrue(r3lib.row_is_time_axis(['21日', '22日', '23日']))

    def test_scattered_numbers_are_not_a_time_axis(self):
        self.assertFalse(r3lib.row_is_time_axis(['7', '?', '20']))

    def test_years_out_of_range_are_not_a_axis(self):
        self.assertFalse(r3lib.row_is_time_axis(['7', '20', '30']))


class TestIndexAxis(unittest.TestCase):
    def test_position_index_over_text_labels(self):
        self.assertTrue(r3lib.row_is_index_axis(
            ['1', '2', '3', '4', '5', '6'],
            ['人社', '财政', '农业', '教育', '住建', '交通']))

    def test_grid_header_that_continues_into_body_is_data(self):
        # 1|2|3 then 4|5|6 ... is the first row of a 3x3 grid, not a key.
        self.assertFalse(r3lib.row_is_index_axis(['1', '2', '3'], ['4', '5', '6']))


class TestHeaderProfile(unittest.TestCase):
    def test_data_row_as_header(self):
        p = r3lib.header_profile(['7', '?', '20'])
        self.assertEqual(p['verdict'], 'DATA')
        self.assertEqual(p['confidence'], 'high')

    def test_placeholder_row(self):
        p = r3lib.header_profile(['（ ）', '14', '19', '102'])
        self.assertEqual(p['verdict'], 'DATA')

    def test_algebraic_variables_are_data(self):
        p = r3lib.header_profile(['a', '4', '8', 'm'], ['3', '17', 'b', '11'])
        self.assertEqual(p['verdict'], 'DATA')

    def test_pure_letter_key_is_a_header(self):
        p = r3lib.header_profile(['A', 'B', 'C', 'D'])
        self.assertEqual(p['verdict'], 'LABEL')

    def test_empty_corner_cell_is_a_header(self):
        # | | 45元 | 75元 | 85元 | -- a real header, not a data row.
        p = r3lib.header_profile(['', '45元', '75元', '85元'], ['甲店', '45元', '49.5元', '58.5元'])
        self.assertEqual(p['verdict'], 'LABEL')

    def test_year_axis_is_a_header(self):
        p = r3lib.header_profile(['2018', '2019', '2020'], ['1', '2', '3'])
        self.assertEqual(p['verdict'], 'LABEL')

    def test_interleaved_label_value_is_data(self):
        p = r3lib.header_profile(['东部地区', '28', '中部地区', '23.9', '西部地区', '25.24'])
        self.assertEqual(p['verdict'], 'INTERLEAVED')
        self.assertEqual(p['confidence'], 'medium')

    def test_real_labelled_header(self):
        p = r3lib.header_profile(['年份', '数量'], ['2018', '3'])
        self.assertEqual(p['verdict'], 'MIXED')


class TestMultilevel(unittest.TestCase):
    def _table(self, header, body):
        lines = ['| ' + ' | '.join(header) + ' |',
                 '| ' + ' | '.join(['---'] * len(header)) + ' |']
        lines += ['| ' + ' | '.join(r) + ' |' for r in body]
        return list(r3lib.iter_pipe_tables(lines))[0]

    def test_duplicated_group_labels(self):
        t = self._table(['', '单位', '5月', '5月', '增长（%）', '增长（%）'],
                        [['', '', '累计', '当月', '累计', '当月'],
                         ['邮电', '亿元', '1', '2', '3', '4']])
        ml = r3lib.multilevel_report(t)
        self.assertIsNotNone(ml)
        self.assertEqual(ml['shape'], 'DUPLICATED_GROUP')
        self.assertFalse(ml['info_lost'])

    def test_span_title_row(self):
        t = self._table(['', '全国', '东部'],
                        [['外出从业构成', '', ''],
                         ['乡外县内', '19.2', '29.9']])
        ml = r3lib.multilevel_report(t)
        self.assertIsNotNone(ml)
        self.assertEqual(ml['shape'], 'SPAN_TITLE_ROW')

    def test_row_label_column_is_not_multilevel(self):
        # | | 周一 | 周二 | ... with a 限行 row-label column: perfectly normal.
        t = self._table(['', '周一', '周二'],
                        [['限行', 'A/C', 'C/A'],
                         ['不限行', 'B', 'D']])
        self.assertIsNone(r3lib.multilevel_report(t))

    def test_ordinary_header_is_not_multilevel(self):
        t = self._table(['城镇', '农村'], [['a', '1'], ['b', '2']])
        self.assertIsNone(r3lib.multilevel_report(t))


class TestPatchGeneration(unittest.TestCase):
    """The patch must be structural only: same cell multiset, plus a blank head."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.rel = 'papers/demo.md'
        os.makedirs(os.path.join(self.tmp, 'papers'))
        self.body = (
            '# demo\n\n'
            '| 7 | ? | 20 |\n'
            '| ---: | ---: | ---: |\n'
            '| 6 | 22 | 30 |\n'
            '| 17 | 21 | 40 |\n'
        )
        with open(os.path.join(self.tmp, self.rel), 'w', encoding='utf-8') as fh:
            fh.write(self.body)

    def test_patch_is_content_preserving(self):
        files = [(self.rel, os.path.join(self.tmp, self.rel))]
        records, inv = r3_tablescan.table_inventory(self.tmp, files)
        self.assertEqual(inv['tables'], 1)
        self.assertEqual(records[0]['finding']['verdict'], 'DATA')

        diff = r3_tablescan.build_patch(self.tmp, records)
        res = r3_tablescan.verify_patch(self.tmp, diff)
        self.assertTrue(res['identical_multiset'],
                        'patch changed cell content: %s' % res)

    def test_demote_table_keeps_delimiter_second(self):
        lines = self.body.split('\n')
        idx = 2                      # 0-based index of the header line
        self.assertEqual(lines[idx], '| 7 | ? | 20 |')
        out = r3_tablescan.demote_table(lines, idx, 3)
        self.assertEqual(out[idx], '| | | |')             # blank header
        self.assertEqual(out[idx + 1], '| ---: | ---: | ---: |')  # delimiter stays 2nd
        self.assertEqual(out[idx + 2], '| 7 | ? | 20 |')  # original, verbatim
        # the table is still a table, and gained exactly one body row
        before = list(r3lib.iter_pipe_tables(lines))
        after = list(r3lib.iter_pipe_tables(out))
        self.assertEqual(len(after), len(before))
        self.assertEqual(after[0].nrows, before[0].nrows + 1)

    def test_demote_table_preserves_every_value(self):
        lines = self.body.split('\n')
        out = r3_tablescan.demote_table(lines, 2, 3)

        def cells(ls):
            return sorted(c for t in r3lib.iter_pipe_tables(ls)
                          for row in [t.header] + t.rows
                          for c in row if c)

        self.assertEqual(cells(lines), cells(out))

    def test_verify_patch_is_not_vacuous(self):
        files = [(self.rel, os.path.join(self.tmp, self.rel))]
        records, _ = r3_tablescan.table_inventory(self.tmp, files)
        diff = r3_tablescan.build_patch(self.tmp, records)
        res = r3_tablescan.verify_patch(self.tmp, diff)
        self.assertTrue(res['ok'])
        self.assertTrue(res['non_vacuous'])
        self.assertGreater(res['cells_compared'], 0)
        self.assertEqual(res['rows_delta'], 1)

    def test_verify_patch_rejects_a_delimiter_breaking_patch(self):
        # A patch that puts the demoted row ABOVE the delimiter destroys the
        # table; verification must fail rather than report "identical cells".
        bad = (
            '--- a/papers/demo.md\n'
            '+++ b/papers/demo.md\n'
            '@@ -2,3 +2,4 @@\n'
            '+| | | |\n'
            ' | 7 | ? | 20 |\n'
            ' | ---: | ---: | ---: |\n'
            ' | 6 | 22 | 30 |\n'
        )
        res = r3_tablescan.verify_patch(self.tmp, bad)
        self.assertFalse(res['ok'])

    def test_high_confidence_only(self):
        files = [(self.rel, os.path.join(self.tmp, self.rel))]
        records, _ = r3_tablescan.table_inventory(self.tmp, files)
        diff = r3_tablescan.build_patch(self.tmp, records, only_conf=('high',))
        self.assertTrue(diff)


class TestSymbolScan(unittest.TestCase):
    def test_idiom_is_not_a_comparison(self):
        hits = r3_symbolscan.scan_line('A. 围湖造田是一项弊大于利的错误举措', False)
        self.assertNotIn('WORD_OP', [h[0] for h in hits])

    def test_numeric_word_comparison_is_flagged(self):
        hits = r3_symbolscan.scan_line('因为 23 小于 47，故排除', False)
        self.assertIn('WORD_OP', [h[0] for h in hits])

    def test_spaced_angle_comparison(self):
        hits = r3_symbolscan.scan_line('解得：23% < x < 47%。', True)
        self.assertGreaterEqual([h[0] for h in hits].count('LT_RAW'), 2)

    def test_fullwidth_is_flagged_separately(self):
        hits = r3_symbolscan.scan_line('80 × 0.2 ＜ 4.5 + 50x', True)
        self.assertIn('LT_FULLWIDTH', [h[0] for h in hits])

    def test_details_tag_is_not_a_comparison(self):
        hits = r3_symbolscan.scan_line('<details><summary>第 1 题 · 答案与解析</summary>', False)
        self.assertNotIn('LT_RAW', [h[0] for h in hits])

    def test_entity_is_flagged(self):
        hits = r3_symbolscan.scan_line('3月:2+17=19&lt;20；', True)
        self.assertIn('HTML_ENTITY', [h[0] for h in hits])

    def test_mixed_notation_same_sentence(self):
        hits = r3_symbolscan.scan_line('23% < x < 47% 与 80 × 0.2 ＜ 4.5 等价', True)
        cats = {h[0] for h in hits}
        self.assertIn('LT_RAW', cats)
        self.assertIn('LT_FULLWIDTH', cats)


class TestResolveRef(unittest.TestCase):
    def test_relative_to_md_directory(self):
        p, why = r3lib.resolve_ref('/repo/a/b/c.md', '../img/x.png')
        self.assertEqual(p, '/repo/a/img/x.png')
        self.assertIsNone(why)

    def test_external(self):
        self.assertEqual(r3lib.resolve_ref('/r/c.md', 'https://x/y.png')[1], 'external')

    def test_anchor(self):
        self.assertEqual(r3lib.resolve_ref('/r/c.md', '#frag')[1], 'anchor')


class TestAssets(unittest.TestCase):
    def test_sha_named_and_legacy(self):
        import r3_assets
        self.assertTrue(r3_assets.SHA_NAME.match('a' * 64 + '.png'))
        self.assertFalse(r3_assets.SHA_NAME.match('00348feff341773.jpg'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
