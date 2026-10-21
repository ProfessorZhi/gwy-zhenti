// 申论清单页的行选择：纯函数，便于离线测试。
//
// 国考等地区同一年有多个卷型（副省级/地市级/行政执法），清单行的可见文本里
// 并没有 sourceId，所以只能「按行号显式绑定」：行号来自清单页按序枚举，并与
// 同一页 API 项的等序编号对应。行号本身不可信，必须再过年份、卷型标记和
// 会员/付费标记这几道闸门，之后仍要靠详情页标题哈希复核身份。

const MAX_ROWS = 200;

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

// 卷型标记：清单行文本里能看到的卷面名称片段。
const MARKERS = {
  a: ['a', 'A卷/A类'],
  b: ['b', 'B卷/B类'],
  c: ['c', 'C卷/C类'],
  xingzheng: ['xingzheng', '行政执法'],
};

export function selectRowByIndex(rows, { index, year, variant }) {
  if (!Array.isArray(rows)) throw fail('ROWS_REQUIRED', 'rows must be an array');
  if (!Number.isInteger(index) || index < 0 || index >= MAX_ROWS) {
    throw fail('ROW_INDEX_INVALID', 'row index must be an integer in [0, 200)');
  }
  const row = rows[index];
  if (!row) throw fail('ROW_NOT_FOUND', `list has no row ${index}`);
  if (!Array.isArray(row.years) || !row.years.includes(year)) {
    throw fail('ROW_YEAR_MISMATCH', `row ${index} does not carry ${year}`);
  }
  const wanted = String(variant ?? '').toLowerCase();
  const marker = MARKERS[wanted];
  if (marker && row[marker[0]] !== true) {
    throw fail('ROW_VARIANT_MISMATCH', `row ${index} lacks the ${marker[1]} marker`);
  }
  if (row.member === true) throw fail('MEMBER_ROW', 'target row is member/paywalled; refusing to open');
  return {
    index,
    row,
    binding: {
      method: 'explicit-row-index',
      rowIndex: index,
      years: row.years,
      markers: {
        a: row.a === true, b: row.b === true, c: row.c === true,
        xingzheng: row.xingzheng === true, fushi: row.fushi === true, dishi: row.dishi === true,
      },
    },
  };
}
