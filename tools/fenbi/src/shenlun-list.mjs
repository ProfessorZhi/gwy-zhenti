// 申论清单页的行选择：纯函数，便于离线测试。
//
// 国考等地区同一年有多个卷型（副省级/地市级/行政执法），清单行的可见文本里
// 并没有 sourceId，所以只能「按行号显式绑定」：行号来自清单页按序枚举，并与
// 同一页 API 项的等序编号对应。行号本身不可信：
//   1. 必须先观察到同一页的真实列表 API（body.list 有序 id 数组）；
//   2. 行数、页码、分页总数必须与 API 完全一致；
//   3. 断言 apiIds[rowIndex] === sourceId；
//   4. 再过年份、卷型标记和会员/付费闸门；
//   5. 详情页标题哈希仍必须与事先固定的期望哈希一致。
// 任何一条观察不到都 FAIL CLOSED（抛错），绝不猜行、绝不点开。

const MAX_ROWS = 200;
const HASH_HEX = /^[0-9a-f]{12,64}$/u;

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

/**
 * 同一页真实列表 API → 有序 id 数组 + 分页信息。
 * 接受的两种信封（都必须是 list + pageInfo 成对出现）：
 *   { list, pageInfo }            —— 当前站点 /api/shenlun/papers/v2 的实时响应
 *   { body: { list, pageInfo } }  —— 历史归档快照的包装
 * 只接受 list 非空且每条都有数字 id 的响应；页面/总数信息缺失或自相矛盾一律拒绝。
 * `names` 只留在内存里用于计算标题哈希，调用方绝不能把它写进采集产物。
 */
export function normalizeListApiSnapshot(json, { path = null } = {}) {
  const envelope = Array.isArray(json?.list) ? json
    : (Array.isArray(json?.body?.list) ? json.body : null);
  const list = envelope?.list;
  if (!Array.isArray(list) || list.length === 0) throw fail('LIST_API_LIST_MISSING', 'list API list is empty or absent');
  if (list.length > MAX_ROWS) throw fail('LIST_API_TOO_LONG', `list API returned ${list.length} items`);
  const pageInfo = envelope?.pageInfo;
  if (!pageInfo || typeof pageInfo !== 'object') throw fail('LIST_API_PAGEINFO_MISSING', 'list API has no body.pageInfo');
  const numbers = ['currentPage', 'totalPage', 'totalItem'];
  for (const field of numbers) {
    if (!Number.isInteger(pageInfo[field])) throw fail('LIST_API_PAGEINFO_INVALID', `pageInfo.${field} is not an integer`);
  }
  const page = pageInfo.currentPage;
  const totalPage = pageInfo.totalPage;
  const totalItem = pageInfo.totalItem;
  const pageSize = Number.isInteger(pageInfo.pageSize) ? pageInfo.pageSize : null;
  if (page < 0 || totalPage < 1 || totalItem < 1) throw fail('LIST_API_PAGEINFO_INVALID', 'pageInfo carries out-of-range numbers');
  if (pageSize != null && pageSize < 1) throw fail('LIST_API_PAGEINFO_INVALID', 'pageInfo.pageSize must be positive');
  if (page >= totalPage) throw fail('LIST_API_PAGEINFO_INVALID', `currentPage ${page} is outside totalPage ${totalPage}`);
  const ids = list.map((item, position) => {
    const id = item?.id;
    if (typeof id !== 'number' && typeof id !== 'string') throw fail('LIST_API_ID_INVALID', `item ${position} has no id`);
    if (!/^\d+$/u.test(String(id))) throw fail('LIST_API_ID_INVALID', `item ${position} id is not numeric`);
    return String(id);
  });
  const seen = new Set();
  for (const id of ids) {
    if (seen.has(id)) throw fail('LIST_API_ID_DUPLICATE', `id ${id} appears twice on one page`);
    seen.add(id);
  }
  return {
    ids,
    page,
    totalPage,
    totalItem,
    pageSize,
    itemCount: ids.length,
    names: list.map((item) => (typeof item?.name === 'string' ? item.name : null)),
    sourcePath: path,
  };
}

/**
 * 显式行号 + 同页 API 有序 id 的硬绑定。
 * 行数与 API 等长、页码一致（currentPage 为 0 基）、分页自洽，
 * 且 apiIds[rowIndex] 必须等于 sourceId；任何一条不成立都在点开行之前抛错。
 * `pagerTotalPages` 只在分页控件显示的确实是「总页数」时才传；站点只渲染
 * 页码窗口（如恒为 1/2/3）时不要传，否则会把窗口大小误当总页数。
 */
export function bindRowToApi(rows, api, { index, sourceId, page, year, variant, pagerTotalPages = null }) {
  const picked = selectRowByIndex(rows, { index, year, variant });
  if (!api || !Array.isArray(api.ids) || !Number.isInteger(api.page)) {
    throw fail('LIST_API_REQUIRED', 'row-index capture needs an observed list API snapshot for the same page');
  }
  if (!Number.isInteger(page) || page < 1) throw fail('LIST_PAGE_INVALID', 'list page must be a positive integer');
  if (api.page !== page - 1) {
    throw fail('ROW_API_PAGE_MISMATCH', `DOM page ${page} but API currentPage ${api.page}`);
  }
  if (api.itemCount !== api.ids.length) throw fail('ROW_API_COUNT_INCONSISTENT', 'API itemCount disagrees with its id array');
  if (Number.isInteger(api.pageSize) && api.pageSize > 0 && api.totalItem > 0) {
    // 分页自洽：每页条数必须等于「总条数 - 已翻过的页」与 pageSize 的较小者。
    const expectedOnPage = Math.min(api.pageSize, api.totalItem - api.page * api.pageSize);
    if (expectedOnPage > 0 && api.ids.length !== expectedOnPage) {
      throw fail('ROW_API_PAGE_COUNT_MISMATCH', `page ${api.page} carries ${api.ids.length} ids, pageInfo implies ${expectedOnPage}`);
    }
  }
  if (pagerTotalPages != null && pagerTotalPages !== api.totalPage) {
    throw fail('ROW_API_PAGER_MISMATCH', `pager shows ${pagerTotalPages} pages but API totalPage is ${api.totalPage}`);
  }
  if (api.ids.length !== rows.length) {
    throw fail('ROW_API_COUNT_MISMATCH', `DOM rows ${rows.length} vs API ids ${api.ids.length}`);
  }
  const apiId = api.ids[index];
  if (apiId === undefined) throw fail('ROW_API_ID_MISSING', `API has no id at row ${index}`);
  if (apiId !== String(sourceId)) {
    // 只报告两侧 id 长度，不回显真实 id 之外的任何正文。
    throw fail('ROW_API_ID_MISMATCH', `row ${index} API id does not match --source-id`);
  }
  return {
    index,
    row: picked.row,
    apiId,
    binding: {
      ...picked.binding,
      method: 'explicit-row-index+api-order',
      apiPage: api.page,
      apiTotalPage: api.totalPage,
      apiItemCount: api.itemCount,
      ...(pagerTotalPages != null ? { apiPagerTotalPages: pagerTotalPages } : {}),
      apiIdAsserted: true,
    },
  };
}

/**
 * 标题身份：期望哈希必须在打开详情页之前就固定（--title-hash），
 * 与详情页 DOM 全标题的 sha256 前缀比较，并在有列表 API 名称哈希时一并比对。
 * 期望哈希缺失即拒绝，绝不把「没核对」写成 verified。
 */
export function verifyTitleHash({ observedHash, observedLen, expectedHash, expectedLen = null, apiNameHash = null }) {
  if (!expectedHash) throw fail('TITLE_HASH_REQUIRED', '--title-hash is required; identity cannot be claimed without it');
  const expected = String(expectedHash).toLowerCase();
  if (!HASH_HEX.test(expected)) throw fail('TITLE_HASH_INVALID', 'expected title hash must be 12-64 lowercase hex chars');
  if (typeof observedHash !== 'string' || !/^[0-9a-f]{64}$/u.test(observedHash)) {
    throw fail('TITLE_HASH_OBSERVED_INVALID', 'observed DOM title hash must be the full sha256 hex digest');
  }
  if (expectedLen != null && Number(expectedLen) !== observedLen) {
    throw fail('TITLE_LEN_MISMATCH', 'live title length does not match the inventory');
  }
  if (!observedHash.startsWith(expected)) throw fail('TITLE_HASH_MISMATCH', 'live DOM title does not match the pinned hash');
  let apiNameVerified = null;
  if (apiNameHash != null) {
    if (typeof apiNameHash !== 'string' || !/^[0-9a-f]{64}$/u.test(apiNameHash)) {
      throw fail('TITLE_API_NAME_UNHASHABLE', 'list API name at the bound row could not be hashed');
    }
    if (!apiNameHash.startsWith(expected)) {
      throw fail('TITLE_API_NAME_MISMATCH', 'list API name at the bound row does not match the pinned hash');
    }
    apiNameVerified = true;
  }
  return {
    verified: true,
    expectedLength: expected.length,
    observedHash,
    apiNameVerified,
  };
}
