import test from 'node:test';
import assert from 'node:assert/strict';
import { selectRowByIndex } from '../src/shenlun-list.mjs';

const row = (overrides = {}) => ({ index: 0, years: [2026], a: false, b: false, c: false, xingzheng: false, fushi: false, dishi: false, member: false, ...overrides });

const code = (name) => (error) => error.code === name;

const rows = [
  row({ index: 0, fushi: true }),
  row({ index: 1, dishi: true }),
  row({ index: 2, xingzheng: true }),
];

test('an explicit row index binds the row the inventory enumerated', () => {
  const picked = selectRowByIndex(rows, { index: 1, year: 2026, variant: 'unknown' });
  assert.equal(picked.index, 1);
  assert.deepEqual(picked.binding.markers, { a: false, b: false, c: false, xingzheng: false, fushi: false, dishi: true });
});

test('the row still has to carry the year', () => {
  assert.throws(() => selectRowByIndex(rows, { index: 2, year: 2025, variant: 'unknown' }), code('ROW_YEAR_MISMATCH'));
});

test('an out-of-range or missing row is refused, never clamped', () => {
  assert.throws(() => selectRowByIndex(rows, { index: 3, year: 2026, variant: 'unknown' }), code('ROW_NOT_FOUND'));
  assert.throws(() => selectRowByIndex(rows, { index: -1, year: 2026, variant: 'unknown' }), code('ROW_INDEX_INVALID'));
  assert.throws(() => selectRowByIndex(rows, { index: 1.5, year: 2026, variant: 'unknown' }), code('ROW_INDEX_INVALID'));
  assert.throws(() => selectRowByIndex(rows, { index: 999, year: 2026, variant: 'unknown' }), code('ROW_INDEX_INVALID'));
});

test('a declared variant must appear on the row', () => {
  assert.throws(() => selectRowByIndex(rows, { index: 0, year: 2026, variant: 'xingzheng' }), code('ROW_VARIANT_MISMATCH'));
  assert.equal(selectRowByIndex(rows, { index: 2, year: 2026, variant: 'xingzheng' }).index, 2);
  assert.throws(() => selectRowByIndex(rows, { index: 1, year: 2026, variant: 'b' }), code('ROW_VARIANT_MISMATCH'));
});

test('a member/paywalled row is refused before any click', () => {
  const paid = [row({ index: 0, member: true })];
  assert.throws(() => selectRowByIndex(paid, { index: 0, year: 2026, variant: 'unknown' }), code('MEMBER_ROW'));
});

test('rows must actually be an array', () => {
  assert.throws(() => selectRowByIndex(null, { index: 0, year: 2026, variant: 'unknown' }), code('ROWS_REQUIRED'));
});
