import test from 'node:test';
import assert from 'node:assert/strict';
import { selectRowByIndex, bindRowToApi, normalizeListApiSnapshot, verifyTitleHash } from '../src/shenlun-list.mjs';

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

// ---- 同页列表 API 的有序 id 绑定 ----

const apiSnapshot = (overrides = {}) => ({
  ids: ['100', '200', '300'], page: 0, totalPage: 1, totalItem: 3, pageSize: 15,
  itemCount: 3, names: ['alpha', 'beta', 'gamma'], sourcePath: '/api/shenlun/list', ...overrides,
});
const bind = (rows, api, overrides = {}) => bindRowToApi(rows, api, {
  index: 1, sourceId: '200', page: 1, year: 2026, variant: 'unknown', ...overrides,
});

test('the observed API id at the same row must equal the requested source id', () => {
  const picked = bind(rows, apiSnapshot());
  assert.equal(picked.index, 1);
  assert.equal(picked.apiId, '200');
  assert.equal(picked.binding.method, 'explicit-row-index+api-order');
  assert.equal(picked.binding.apiIdAsserted, true);
  assert.equal(picked.binding.apiPage, 0);
});

test('a row that points at another paper id is refused before any click', () => {
  assert.throws(() => bind(rows, apiSnapshot(), { sourceId: '300' }), code('ROW_API_ID_MISMATCH'));
  assert.throws(() => bind(rows, apiSnapshot({ ids: ['100', '999', '300'] })), code('ROW_API_ID_MISMATCH'));
});

test('page, row-count and pagination disagreements are refused', () => {
  assert.throws(() => bind(rows, apiSnapshot({ page: 1 })), code('ROW_API_PAGE_MISMATCH'));
  assert.throws(() => bind(rows, apiSnapshot({ ids: ['100', '200'], itemCount: 2, totalItem: 2 })), code('ROW_API_COUNT_MISMATCH'));
  assert.throws(() => bind(rows, apiSnapshot(), { pagerTotalPages: 2 }), code('ROW_API_PAGER_MISMATCH'));
  assert.throws(() => bind(rows, apiSnapshot({ itemCount: 2 })), code('ROW_API_COUNT_INCONSISTENT'));
  // 15/page, 31 items → last page (currentPage 2) must carry exactly 1 id.
  assert.throws(() => bind(rows, apiSnapshot({
    ids: ['100', '200', '300'], page: 2, totalPage: 3, totalItem: 31, itemCount: 3,
  }), { page: 3 }), code('ROW_API_PAGE_COUNT_MISMATCH'));
});

test('the live top-level {list,pageInfo} envelope is accepted alongside archived body-wrapped snapshots', () => {
  const live = normalizeListApiSnapshot({
    list: [{ id: '100', name: 'alpha' }, { id: '200', name: 'beta' }],
    pageInfo: { currentPage: 0, totalPage: 15, totalItem: 221, pageSize: 15 },
  });
  assert.deepEqual(live.ids, ['100', '200']);
  assert.equal(live.page, 0);
  assert.equal(live.totalPage, 15);
  const wrapped = normalizeListApiSnapshot({
    body: { list: [{ id: '100' }], pageInfo: { currentPage: 1, totalPage: 3, totalItem: 31, pageSize: 15 } },
  });
  assert.equal(wrapped.page, 1);
  assert.throws(() => normalizeListApiSnapshot({ list: [], pageInfo: { currentPage: 0, totalPage: 1, totalItem: 1 } }), code('LIST_API_LIST_MISSING'));
  assert.throws(() => normalizeListApiSnapshot({ list: [{ id: 1 }] }), code('LIST_API_PAGEINFO_MISSING'));
});

test('a missing or malformed list API snapshot fails closed', () => {
  assert.throws(() => bind(rows, null), code('LIST_API_REQUIRED'));
  assert.throws(() => bind(rows, { ids: ['100', '200', '300'] }), code('LIST_API_REQUIRED'));
  assert.throws(() => normalizeListApiSnapshot({ body: { list: [] } }), code('LIST_API_LIST_MISSING'));
  assert.throws(() => normalizeListApiSnapshot({ body: { list: [{ id: 1 }] } }), code('LIST_API_PAGEINFO_MISSING'));
  assert.throws(() => normalizeListApiSnapshot({ body: { list: [{ id: 'x' }], pageInfo: { currentPage: 0, totalPage: 1, totalItem: 1 } } }), code('LIST_API_ID_INVALID'));
  assert.throws(() => normalizeListApiSnapshot({
    body: { list: [{ id: 1 }, { id: 1 }], pageInfo: { currentPage: 0, totalPage: 1, totalItem: 2 } },
  }), code('LIST_API_ID_DUPLICATE'));
  assert.throws(() => normalizeListApiSnapshot({
    body: { list: [{ id: 1 }], pageInfo: { currentPage: 1, totalPage: 1, totalItem: 1 } },
  }), code('LIST_API_PAGEINFO_INVALID'));
});

// ---- 标题哈希：缺失、冲突、未知卷型 ----

const FULL = 'a'.repeat(64);

test('an absent or malformed pinned title hash is refused, never treated as verified', () => {
  assert.throws(() => verifyTitleHash({ observedHash: FULL, observedLen: 19 }), code('TITLE_HASH_REQUIRED'));
  assert.throws(() => verifyTitleHash({ observedHash: FULL, observedLen: 19, expectedHash: 'not-hex' }), code('TITLE_HASH_INVALID'));
  assert.throws(() => verifyTitleHash({ observedHash: FULL.slice(0, 16), observedLen: 19, expectedHash: 'a'.repeat(12) }), code('TITLE_HASH_OBSERVED_INVALID'));
});

test('unknown-variant rows still need a matching title hash', () => {
  // variant=unknown 只跳过年份/卷型标记，不跳过标题身份。
  assert.equal(bind(rows, apiSnapshot(), { variant: 'unknown' }).binding.apiIdAsserted, true);
  assert.throws(() => verifyTitleHash({ observedHash: FULL, observedLen: 19, expectedHash: null }), code('TITLE_HASH_REQUIRED'));
  assert.throws(() => verifyTitleHash({ observedHash: FULL, observedLen: 19, expectedHash: 'c'.repeat(12) }), code('TITLE_HASH_MISMATCH'));
});

test('a conflicting title hash or list-API name is refused', () => {
  assert.equal(verifyTitleHash({ observedHash: FULL, observedLen: 19, expectedHash: 'a'.repeat(12) }).verified, true);
  assert.throws(() => verifyTitleHash({ observedHash: FULL, observedLen: 19, expectedHash: 'b'.repeat(12) }), code('TITLE_HASH_MISMATCH'));
  assert.throws(() => verifyTitleHash({ observedHash: FULL, observedLen: 19, expectedHash: 'a'.repeat(12), expectedLen: 20 }), code('TITLE_LEN_MISMATCH'));
  assert.throws(() => verifyTitleHash({
    observedHash: FULL, observedLen: 19, expectedHash: 'a'.repeat(12), apiNameHash: 'b'.repeat(64),
  }), code('TITLE_API_NAME_MISMATCH'));
  assert.equal(verifyTitleHash({
    observedHash: FULL, observedLen: 19, expectedHash: 'a'.repeat(12), apiNameHash: 'a'.repeat(64),
  }).apiNameVerified, true);
});
