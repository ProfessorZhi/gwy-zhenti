// 申论目录发现与候选队列核心（纯离线回放）。
//
// 输入是已经保存在 work/fenbi 下的真实目录快照：
//   * national-catalog-batch*.json  —— S1 单 Owner 巡目录产物（metadata-only）
//   * shenlun-inventory-*.json      —— 地区级 inventory（浙江 36 卷）
//   * shenlun-api-*.json            —— 列表页自身发出的只读响应快照
//   * catalog-*.json                —— 地区目录巡检产物（可含标题）
// 本模块不联网、不开浏览器、不读 profile、不写 papers。输出只有 sourceId 级元数据、
// 计数和标题指纹，不含题文、材料、答案或 URL。
//
// 身份规则（硬约束）：
//   1. sourceId 是唯一身份。同一 sourceId 在多个地区出现只算一卷，绝不按地区重复计新卷。
//   2. 跨地区 / 跨年份 / 跨卷型冲突一律隔离（flags.crossRegion / identityConflict），
//      不自动挑选“最可能”的地区。
//   3. 标题只用于发现“同名不同 sourceId”的碰撞；碰撞不自动合并，只进待复核。
//
// 费用规则（fail-closed）：
//   * 显式 paid/lockStatus 优先；行级“会员/锁定”标记次之。
//   * 只有“该行未见任何付费/会员标记”时才是 free-visible-unverified，不写成 free。
//   * 显式 free 与会员/锁定信号冲突时降为 unknown 并排除自动队列。
//
// 年份规则：复用 driver/year-policy.mjs —— 2026-10-23 起所有地区都保留全部可见年份
// （下界 1900，上界当前自然年），不再有「其他地区 2016 起」的分区例外。

import { createHash } from 'node:crypto';
import { DEFAULT_MIN_YEAR, yearAllowed } from './year-policy.mjs';

export const SHENLUN_CATALOG_SCHEMA_VERSION = 1;
export const SUBJECT = 'shenlun';
export { DEFAULT_MIN_YEAR };
export const FOCUS_AREAS = Object.freeze(['国考', '浙江', '江苏', '上海', '北京', '天津', '广东', '广州', '深圳', '福建']);
export const NON_REGION_TABS = Object.freeze(['推荐', '小模考', '选调生', '公安招警和公检法']);

export const FEE = Object.freeze({
  FREE: 'free',
  FREE_VISIBLE: 'free-visible-unverified',
  MEMBER: 'member',
  LOCKED: 'locked',
  UNKNOWN: 'unknown',
});

const sha256 = (value) => createHash('sha256').update(String(value), 'utf8').digest('hex');
const sha16 = (value) => sha256(value).slice(0, 16);
const text = (value) => (value == null ? '' : String(value));
const int = (value) => {
  if (value == null || value === '') return null;
  const n = Number(value);
  return Number.isInteger(n) ? n : null;
};
const uniq = (values) => [...new Set(values)];
const sorted = (values) => [...values].sort();

/** Full-width ASCII and ideographic space → ASCII, so titles compare across input paths. */
export function toHalfWidth(value) {
  return text(value)
    .replace(/[！-～]/gu, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xfee0))
    .replace(/　/gu, ' ');
}

/**
 * Variant vocabulary is deliberately the same one the national discovery stored.
 * 副省/地市 are *not* invented here: those titles stay `unknown` for variant, while
 * their title fingerprint keeps the distinguishing text.
 */
export function variantFromTitle(title) {
  const s = toHalfWidth(title);
  if (/[（(]\s*A\s*卷\s*[)）]/iu.test(s)) return 'a';
  if (/[（(]\s*B\s*卷\s*[)）]/iu.test(s)) return 'b';
  if (/[（(]\s*C\s*卷\s*[)）]/iu.test(s)) return 'c';
  if (/行政执法/u.test(s)) return 'xingzheng';
  if (/乡镇/u.test(s)) return 'township';
  if (/(?:县|县级)/u.test(s)) return 'county';
  if (/联考/u.test(s)) return 'liankao';
  return 'unknown';
}

export function variantFromApi(value) {
  const s = text(value).trim().toLowerCase();
  if (['a', 'b', 'c', 'xingzheng', 'township', 'county', 'liankao', 'unknown'].includes(s)) return s;
  return 'unknown';
}

/** First 19xx/20xx year in the title; explicit year fields win elsewhere. */
export function yearFromTitle(title) {
  const match = text(title).match(/(?:19|20)\d{2}/u);
  return match ? Number(match[0]) : null;
}

/**
 * Normalised title fingerprint. Returns `titleKey: null` when too little text remains
 * to be a meaningful discriminator (prevents grouping every untitled row together).
 */
export function normalizeTitle(title) {
  const raw = toHalfWidth(title);
  let s = raw.normalize('NFKC').replace(/\s+/gu, '');
  s = s.replace(/(?:19|20)\d{2}年?/gu, '');
  s = s.replace(/网友回忆版|回忆版/gu, '');
  s = s.replace(/[（(]\s*(A|B|C)\s*卷\s*[)）]/giu, '$1');
  s = s.replace(/[（(]\s*(副省级?|地市级?|行政执法|通用|乡镇|县级?)\s*卷?\s*[)）]/gu, '$1');
  s = s.replace(/公务员录用考试|公务员考试|公考|省考|国考|联考|真题|《申论》|申论|试卷|题|卷/gu, '');
  s = s.replace(/[（）()《》〈〉【】\[\]·•・\-—_/\\|,，.。:：;；'"“”‘’]/gu, '');
  const weak = s.length < 2;
  return {
    norm: s,
    weak,
    titleKey: weak ? null : sha16(s),
    titleLen: raw.length,
  };
}

/** True when the snapshot itself says every row's lockStatus is 0. */
function lockFieldState(lockFieldExposed) {
  if (!lockFieldExposed || typeof lockFieldExposed !== 'object') return null;
  const entries = Object.entries(lockFieldExposed).filter(([, count]) => Number(count) > 0);
  if (!entries.length) return null;
  if (entries.length === 1 && entries[0][0] === 'lockStatus=0') return 'free';
  if (entries.every(([key]) => /^lockStatus=[1-9]/u.test(key))) return 'locked';
  return 'mixed';
}

/**
 * Classify one observation's fee state. `signals`:
 *   explicitPaid: 'free' | 'member' | null
 *   explicitLock: 'free' | 'locked' | 'mixed' | null
 *   memberRows / lockRows: counts observed at region/page level (may not bind to a row)
 *   rowMatched: true | false | null
 */
export function classifyFee(signals = {}) {
  const explicitPaid = signals.explicitPaid === 'member' ? 'member' : signals.explicitPaid === 'free' ? 'free' : null;
  const explicitLock = ['free', 'locked', 'mixed'].includes(signals.explicitLock) ? signals.explicitLock : null;
  const memberRows = Math.max(0, int(signals.memberRows) ?? 0);
  const lockRows = Math.max(0, int(signals.lockRows) ?? 0);
  const positive = memberRows > 0 || lockRows > 0;
  const conflicts = [];

  const explicit = uniq([explicitPaid, explicitLock === 'free' ? 'free' : explicitLock === 'locked' ? 'locked' : null].filter(Boolean));
  if (explicit.includes('member') && explicit.includes('free')) {
    return { fee: FEE.UNKNOWN, conflicts: ['explicit-paid-vs-free'] };
  }
  if (explicit.includes('locked') && explicit.includes('free')) {
    return { fee: FEE.UNKNOWN, conflicts: ['explicit-lock-vs-free'] };
  }
  if (explicit.includes('member') || explicit.includes('locked')) {
    if (positive && signals.rowMatched === false) conflicts.push('unbound-row-marker');
    return { fee: explicit.includes('member') ? FEE.MEMBER : FEE.LOCKED, conflicts };
  }
  if (explicitLock === 'mixed') return { fee: FEE.UNKNOWN, conflicts: ['mixed-lock-field'] };
  if (explicit.includes('free')) {
    // A row-level marker that disagrees with the list field means we cannot call it free.
    if (positive) return { fee: FEE.FREE_VISIBLE, conflicts: ['row-marker-contradicts-lock-field'] };
    return { fee: FEE.FREE, conflicts };
  }
  if (positive) return { fee: FEE.FREE_VISIBLE, conflicts: ['member-signal-unbound'] };
  return { fee: FEE.FREE_VISIBLE, conflicts };
}

/** Merge observed fee states conservatively across snapshots of the same sourceId. */
export function mergeFee(observations) {
  const fees = new Set(observations.map((o) => o.fee));
  const conflicts = uniq(observations.flatMap((o) => o.feeConflicts || []));
  const hasFree = fees.has(FEE.FREE) || fees.has(FEE.FREE_VISIBLE);
  if ((fees.has(FEE.MEMBER) || fees.has(FEE.LOCKED)) && hasFree) {
    conflicts.push('member-or-locked-vs-free');
    return { fee: FEE.UNKNOWN, feeConflicts: uniq(conflicts) };
  }
  if (fees.has(FEE.MEMBER)) return { fee: FEE.MEMBER, feeConflicts: conflicts };
  if (fees.has(FEE.LOCKED)) return { fee: FEE.LOCKED, feeConflicts: conflicts };
  if (fees.has(FEE.UNKNOWN)) return { fee: FEE.UNKNOWN, feeConflicts: conflicts };
  if (fees.has(FEE.FREE_VISIBLE)) return { fee: FEE.FREE_VISIBLE, feeConflicts: conflicts };
  return { fee: FEE.FREE, feeConflicts: conflicts };
}

function observation({ sourceId, area, year, variant, variantSource = 'explicit', title, titleKind = 'normalized', titleLen = null, fee, feeSignals, feeConflicts, kind = 'paper', origin }) {
  const titleMeta = title != null ? normalizeTitle(title) : { norm: null, weak: true, titleKey: null, titleLen: 0 };
  const titleKey = titleKind === 'provided-hash' ? (text(title) || null) : titleMeta.titleKey;
  return {
    sourceId: text(sourceId),
    area: text(area) || null,
    year: int(year),
    variant: variantFromApi(variant),
    variantSource,
    title: title == null ? null : text(title),
    titleKind,
    titleKey,
    titleLen: titleLen ?? titleMeta.titleLen,
    titleWeak: titleKind === 'provided-hash' ? false : titleMeta.weak,
    fee,
    feeSignals: feeSignals || {},
    feeConflicts: feeConflicts || [],
    kind,
    origin,
  };
}

function pageCoverage(record) {
  if (record.coverage) return record.coverage;
  const total = int(record.totalPages);
  const read = int(record.pagesRead);
  if (record.partialPages === true) return 'partial';
  if (total != null && read != null) return read >= total ? 'full' : 'partial';
  return 'unknown';
}

/** national-catalog-batch*.json → observations + area coverage records. */
export function normalizeNationalBatch(json, { file, observedAt = null } = {}) {
  const observations = [];
  const regions = [];
  for (const category of json?.categories || []) {
    const area = text(category?.category);
    if (!area || category.observed === false) continue;
    const pages = Array.isArray(category.pages) ? category.pages : [];
    const lockState = lockFieldState(category.lockFieldExposed);
    const memberRows = Math.max(0, int(category.memberRows) ?? 0);
    const lockRows = Math.max(0, int(category.lockStyledRows) ?? 0);
    const coverage = pageCoverage({ pagesRead: category.pagesRead, totalPages: category.totalPagesObserved, partialPages: category.partialPages });
    let unique = new Set();
    let unpairedPages = 0;
    pages.forEach((page, pageIndex) => {
      const items = Array.isArray(page.apiItems) ? page.apiItems : null;
      const ids = Array.isArray(page.apiIds) ? page.apiIds : [];
      if (!items || (items.length === 0 && ids.length > 0)) {
        unpairedPages += 1;
        for (const id of ids) {
          unique.add(text(id));
          const fee = classifyFee({ memberRows, lockRows, rowMatched: null });
          observations.push(observation({
            sourceId: id, area, year: null, variant: 'unknown', fee: fee.fee,
            feeSignals: { memberRows, lockRows, unpaired: true }, feeConflicts: fee.conflicts,
            origin: { file, kind: 'national-catalog', observedAt, category: area, page: int(page.page) ?? pageIndex + 1, unpaired: true, coverage },
          }));
        }
        return;
      }
      for (const item of items) {
        if (!item || item.id == null) continue;
        // paidFlag=false is the discovery's `absent-defaulted-false`, not an explicit free claim.
        const explicitPaid = item.paidFlag === true ? 'member' : null;
        const fee = classifyFee({
          explicitPaid, explicitLock: lockState, memberRows, lockRows, rowMatched: null,
        });
        observations.push(observation({
          sourceId: item.id, area, year: item.year, variant: item.variant,
          fee: fee.fee, feeSignals: { explicitPaid, explicitLock: lockState, memberRows, lockRows, rowMatched: null },
          feeConflicts: fee.conflicts,
          origin: { file, kind: 'national-catalog', observedAt, category: area, page: int(page.page) ?? pageIndex + 1, coverage },
        }));
        unique.add(text(item.id));
      }
    });
    regions.push({
      area, source: file, kind: 'national-catalog', coverage,
      pagesRead: int(category.pagesRead), totalPages: int(category.totalPagesObserved),
      partialPages: category.partialPages === true, rowsRead: int(category.rowsTotal),
      uniqueIds: unique.size, unpairedPages,
      memberRowsRaw: memberRows, lockStyledRowsRaw: lockRows,
      lockField: lockState, paidBasis: category.paidBasis || null,
      notes: Array.isArray(category.notes) ? category.notes : [],
      observedAt,
    });
  }
  return { observations, regions, categoriesSeen: Array.isArray(json?.categoriesSeen) ? json.categoriesSeen.map(text) : [] };
}

/** shenlun-inventory-*.json (e.g. Zhejiang 36) → observations + area record. */
export function normalizeInventory(json, { file, observedAt = null } = {}) {
  const area = text(json?.area) || null;
  const items = Array.isArray(json?.items) ? json.items : [];
  const coverage = int(json?.totalVisible) != null && int(json.totalVisible) > items.length ? 'partial' : 'full';
  const observations = items.map((item) => {
    const explicitPaid = item.paid === true ? 'member' : null;
    const lock = int(item.lockStatus);
    const explicitLock = lock === 0 ? 'free' : lock != null && lock > 0 ? 'locked' : null;
    const fee = classifyFee({ explicitPaid, explicitLock, memberRows: 0, lockRows: 0, rowMatched: true });
    return observation({
      sourceId: item.sourceId, area, year: item.year, variant: item.variant,
      title: item.titleHash ?? null, titleKind: 'provided-hash', titleLen: int(item.titleLen),
      fee: fee.fee, feeSignals: { explicitPaid, explicitLock, lockStatus: lock }, feeConflicts: fee.conflicts,
      origin: { file, kind: 'inventory', observedAt, coverage },
    });
  });
  return {
    observations,
    regions: [{
      area, source: file, kind: 'inventory', coverage,
      pagesRead: int(json?.totalPages), totalPages: int(json?.totalPages),
      partialPages: coverage === 'partial', rowsRead: int(json?.totalVisible),
      uniqueIds: new Set(observations.map((o) => o.sourceId)).size,
      memberRowsRaw: 0, lockStyledRowsRaw: 0, lockField: null, paidBasis: null,
      notes: Array.isArray(json?.notes) ? json.notes : [], observedAt,
    }],
  };
}

/** catalog-*.json region discovery → observations (titles optional). */
export function normalizeCatalogLive(json, { file, observedAt = null, subject = SUBJECT } = {}) {
  const observations = [];
  const regions = [];
  for (const [area, record] of Object.entries(json?.regions || {})) {
    if (record?.status && record.status !== 'observed') continue;
    const memberRows = Math.max(0, int(record.memberRows) ?? 0);
    const coverage = record.coverage === 'full' ? 'full'
      : pageCoverage({ pagesRead: (record.pages || []).length, totalPages: record.expectedPages, partialPages: record.pageLimitApplied === true || record.coverage === 'partial' });
    const entries = Array.isArray(record.entries) ? record.entries : [];
    let kept = 0;
    for (const entry of entries) {
      if (!entry || entry.id == null) continue;
      const title = entry.title == null ? null : text(entry.title);
      if (subject) {
        if (entry.subject && entry.subject !== subject) continue;
        if (!entry.subject && title && !/申论/u.test(title)) continue;
        // Without a title or an explicit subject there is no proof this row belongs here.
        if (!entry.subject && !title) continue;
      }
      const explicitMember = entry.member === true;
      const explicitLocked = entry.locked === true;
      const explicitPaid = explicitMember ? 'member' : null;
      const explicitLock = explicitLocked ? 'locked' : null;
      const fee = classifyFee({
        explicitPaid, explicitLock, memberRows, lockRows: 0,
        rowMatched: entry.rowMatched === true ? true : entry.rowMatched === false ? false : null,
      });
      observations.push(observation({
        sourceId: entry.id, area, year: entry.year, variant: variantFromTitle(title), variantSource: 'title',
        title, titleKind: 'normalized',
        fee: fee.fee, feeSignals: { explicitPaid, explicitLock, memberRows, rowMatched: entry.rowMatched }, feeConflicts: fee.conflicts,
        origin: { file, kind: 'catalog-live', observedAt, page: int(entry.page), coverage, rowMatched: entry.rowMatched },
      }));
      kept += 1;
    }
    // A catalog-live file can cover another subject. Do not let its empty (filtered)
    // region record claim coverage for this subject.
    if (subject && entries.length > 0 && kept === 0) continue;
    regions.push({
      area, source: file, kind: 'catalog-live', coverage,
      pagesRead: (record.pages || []).length, totalPages: int(record.expectedPages),
      partialPages: coverage === 'partial', rowsRead: int(record.rows),
      uniqueIds: kept,
      memberRowsRaw: memberRows, lockStyledRowsRaw: 0, lockField: null, paidBasis: null,
      notes: [], kept, observedAt,
    });
  }
  return { observations, regions };
}

/** shenlun-api-*.json list response snapshots → observations. */
export function normalizeApiSnapshot(json, { file, observedAt = null, area = null } = {}) {
  const items = Array.isArray(json?.body?.list) ? json.body.list : [];
  const pageInfo = json?.body?.pageInfo || {};
  const page = int(pageInfo.currentPage);
  const totalPages = int(pageInfo.totalPage);
  const totalItems = int(pageInfo.totalItem);
  const coverage = page != null && totalPages != null ? (page + 1 >= totalPages ? 'full' : 'partial') : 'unknown';
  const observations = [];
  for (const item of items) {
    if (!item || item.id == null) continue;
    const title = text(item.name);
    const inferredArea = area || (/浙江省/u.test(title) ? '浙江' : /国考/u.test(title) ? '国考' : null);
    const explicitPaid = item.paid === true ? 'member' : null;
    const lock = int(item.lockStatus);
    const explicitLock = lock === 0 ? 'free' : lock != null && lock > 0 ? 'locked' : null;
    const fee = classifyFee({ explicitPaid, explicitLock, memberRows: 0, lockRows: 0, rowMatched: true });
    observations.push(observation({
      sourceId: item.id, area: inferredArea,
      year: int(item.year) ?? yearFromTitle(title), variant: variantFromTitle(title), variantSource: 'title',
      title, titleKind: 'normalized',
      fee: fee.fee, feeSignals: { explicitPaid, explicitLock, lockStatus: lock }, feeConflicts: fee.conflicts,
      kind: int(item.type) === 2 ? 'mock' : 'paper',
      origin: {
        file, kind: 'api', observedAt, page, totalPages, totalItems, coverage,
        status: int(item.status), date: item.date ?? null,
      },
    }));
  }
  const mockOnly = observations.length > 0 && observations.every((o) => o.kind === 'mock');
  return {
    observations,
    regions: [{
      area: area || observations[0]?.area || null, source: file, kind: 'api', coverage, mockOnly,
      pagesRead: 1, totalPages, partialPages: coverage === 'partial',
      rowsRead: items.length, uniqueIds: new Set(observations.map((o) => o.sourceId)).size,
      memberRowsRaw: 0, lockStyledRowsRaw: 0, lockField: null, paidBasis: null,
      notes: [], observedAt, page,
    }],
  };
}

function mergeTitle(observations) {
  const byKind = new Map();
  for (const o of observations) {
    if (!o.titleKey) continue;
    const set = byKind.get(o.titleKind) || new Set();
    set.add(o.titleKey);
    byKind.set(o.titleKind, set);
  }
  const conflicts = [...byKind.values()].some((set) => set.size > 1);
  const preferredKind = byKind.has('normalized') ? 'normalized' : [...byKind.keys()][0] || null;
  const chosen = preferredKind ? observations.find((o) => o.titleKind === preferredKind && o.titleKey) : null;
  return {
    titleKey: chosen?.titleKey ?? null,
    titleKind: preferredKind,
    titleWeak: observations.every((o) => o.titleWeak),
    titleConflict: conflicts,
    titleLen: chosen?.titleLen ?? null,
  };
}

/**
 * Merge observations into one paper per sourceId. Never guesses a region or year:
 * conflicts are flagged and the resolved value is null/unknown.
 */
export function mergeObservations(observations) {
  const groups = new Map();
  for (const o of observations) {
    if (!o.sourceId) continue;
    groups.set(o.sourceId, [...(groups.get(o.sourceId) || []), o]);
  }
  const papers = [];
  for (const [sourceId, list] of groups) {
    const ordered = [...list].sort((a, b) => `${a.origin.file}|${a.origin.page ?? 0}|${a.origin.category || ''}`
      .localeCompare(`${b.origin.file}|${b.origin.page ?? 0}|${b.origin.category || ''}`));
    const areas = sorted(uniq(ordered.map((o) => o.area).filter(Boolean)));
    const years = uniq(ordered.map((o) => o.year).filter((y) => y != null)).sort((a, b) => a - b);
    // An explicit API/inventory variant outranks a title heuristic. A title-only
    // disagreement is noise (e.g. 浙江 inventory says A, the title also says 联考),
    // so it is recorded separately instead of becoming an identity conflict.
    const explicitVariants = sorted(uniq(ordered.filter((o) => o.variantSource === 'explicit')
      .map((o) => o.variant).filter((v) => v && v !== 'unknown')));
    const titleVariants = sorted(uniq(ordered.filter((o) => o.variantSource === 'title')
      .map((o) => o.variant).filter((v) => v && v !== 'unknown')));
    const variants = explicitVariants.length ? explicitVariants : titleVariants;
    const variantTitleDisagreement = explicitVariants.length > 0 && titleVariants.length > 0
      && !titleVariants.every((v) => explicitVariants.includes(v));
    const kinds = uniq(ordered.map((o) => o.kind));
    const title = mergeTitle(ordered);
    const fee = mergeFee(ordered);
    const coverage = ordered.some((o) => o.origin.coverage === 'partial') ? 'partial'
      : ordered.every((o) => o.origin.coverage === 'full') ? 'full' : 'unknown';
    const identityConflicts = [];
    if (years.length > 1) identityConflicts.push('year');
    if (variants.length > 1) identityConflicts.push('variant');
    const memberSignal = ordered.some((o) => (o.feeSignals?.memberRows || 0) > 0 || (o.feeSignals?.lockRows || 0) > 0);
    const unpaired = ordered.some((o) => o.feeSignals?.unpaired === true);
    papers.push({
      sourceId,
      area: areas.length === 1 ? areas[0] : null,
      areas,
      year: years.length === 1 ? years[0] : null,
      years,
      variant: variants.length === 1 ? variants[0] : 'unknown',
      variants,
      fee: fee.fee,
      feeConflicts: fee.feeConflicts,
      kind: kinds.length === 1 ? kinds[0] : 'mixed',
      kinds,
      titleKey: title.titleKey,
      titleKind: title.titleKind,
      titleLen: title.titleLen,
      titleConflict: title.titleConflict,
      flags: {
        crossRegion: areas.length > 1,
        identityConflict: identityConflicts.length > 0,
        identityConflicts,
        titleConflict: title.titleConflict,
        titleCollision: false,
        titleWeak: title.titleWeak,
        variantTitleDisagreement,
        memberSignal,
        unpaired,
        partialCoverage: coverage !== 'full',
      },
      coverage,
      observations: ordered.map((o) => ({
        source: o.origin.file, snapshot: o.origin.kind, observedAt: o.origin.observedAt,
        area: o.area, year: o.year, variant: o.variant, variantSource: o.variantSource, fee: o.fee,
        page: o.origin.page ?? null, status: o.origin.status ?? null, date: o.origin.date ?? null,
        coverage: o.origin.coverage, unpaired: o.origin.unpaired === true,
      })),
    });
  }
  return papers.sort(comparePapers);
}

function comparePapers(a, b) {
  return (a.area || '￿').localeCompare(b.area || '￿')
    || (b.year ?? -1) - (a.year ?? -1)
    || a.variant.localeCompare(b.variant)
    || a.sourceId.localeCompare(b.sourceId, 'en', { numeric: true });
}

/** Same area/year/variant/normalised-title but different sourceId → needs review, never auto-merge. */
export function markTitleCollisions(papers) {
  const groups = new Map();
  for (const p of papers) {
    if (!p.titleKey || !p.area || p.year == null) continue;
    if (p.kind === 'mock') continue; // mock titles must not block a real paper
    if (p.titleKind !== 'normalized' && p.titleKind !== 'provided-hash') continue;
    const key = `${p.area}|${p.year}|${p.variant}|${p.titleKind}|${p.titleKey}`;
    groups.set(key, [...(groups.get(key) || []), p.sourceId]);
  }
  const collisions = [];
  for (const [key, ids] of groups) {
    const unique = uniq(ids);
    if (unique.length < 2) continue;
    for (const p of papers) if (unique.includes(p.sourceId)) p.flags.titleCollision = true;
    const [area, year, variant, titleKind, titleKey] = key.split('|');
    collisions.push({ area, year: Number(year), variant, titleKind, titleKey, sourceIds: sorted(unique) });
  }
  return collisions.sort((a, b) => `${a.area}|${a.year}|${a.variant}|${a.titleKey}`.localeCompare(`${b.area}|${b.year}|${b.variant}|${b.titleKey}`));
}

function areaCoverage(area, regions) {
  // Mock-exam list pages are a different stream; they must not make the real-paper
  // area look partial (or full).
  const areaRegions = regions.filter((r) => r.area === area && r.mockOnly !== true);
  const apiPages = areaRegions.filter((r) => r.kind === 'api').map((r) => r.page).filter((p) => p != null);
  const apiTotal = areaRegions.filter((r) => r.kind === 'api').map((r) => r.totalPages).filter((p) => p != null);
  if (apiPages.length && apiTotal.length) {
    const covered = new Set(apiPages);
    const total = Math.max(...apiTotal);
    const all = Array.from({ length: total }, (_, i) => i).every((i) => covered.has(i));
    if (all) return 'full';
  }
  if (areaRegions.some((r) => r.coverage === 'partial')) return 'partial';
  if (areaRegions.length && areaRegions.every((r) => r.coverage === 'full')) return 'full';
  if (areaRegions.length && areaRegions.every((r) => r.coverage === 'unknown')) return 'unknown';
  return areaRegions.length ? 'partial' : 'unknown';
}

function countsBy(items, pick) {
  const out = {};
  for (const item of items) {
    const key = pick(item);
    out[key] = (out[key] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)));
}

/** Coverage matrix plus explicit unknown range. Never presents partial as total. */
export function buildCoverage(papers, regions, { now = new Date(), categoriesSeen = [] } = {}) {
  const areas = sorted(uniq([...papers.flatMap((p) => p.areas), ...regions.map((r) => r.area).filter(Boolean)]));
  const byArea = areas.map((area) => {
    const all = papers.filter((p) => p.areas.includes(area));
    // Mock-exam papers are real rows on the site but not real 真题; keep them visible
    // as a separate count and never inside the real-paper fee/variant/year matrix.
    const own = all.filter((p) => p.kind !== 'mock');
    const inScope = own.filter((p) => p.year != null && yearAllowed(area, p.year, now));
    const regionRows = regions.filter((r) => r.area === area && r.mockOnly !== true);
    const pagesRead = regionRows.reduce((sum, r) => sum + (r.pagesRead || 0), 0);
    const totalPages = Math.max(...regionRows.map((r) => r.totalPages ?? 0), 0) || null;
    return {
      area,
      coverage: areaCoverage(area, regions),
      sourceIds: all.length,
      realSourceIds: own.length,
      mock: all.length - own.length,
      inScope: inScope.length,
      outOfScope: own.filter((p) => p.year != null && !yearAllowed(area, p.year, now)).length,
      pre2016: own.filter((p) => p.year != null && p.year < 2016).length,
      future: own.filter((p) => p.year != null && p.year > now.getFullYear()).length,
      unknownYear: own.filter((p) => p.year == null).length,
      fee: countsBy(own, (p) => p.fee),
      variants: countsBy(own, (p) => p.variant),
      years: countsBy(inScope, (p) => String(p.year)),
      flags: {
        crossRegion: own.filter((p) => p.flags.crossRegion).length,
        identityConflict: own.filter((p) => p.flags.identityConflict).length,
        titleCollision: own.filter((p) => p.flags.titleCollision).length,
        titleConflict: own.filter((p) => p.flags.titleConflict).length,
        memberSignal: own.filter((p) => p.flags.memberSignal).length,
        variantTitleDisagreement: own.filter((p) => p.flags.variantTitleDisagreement).length,
      },
      pagesRead,
      totalPages,
      sources: sorted(uniq(regionRows.map((r) => r.source))),
    };
  });
  const observed = byArea.map((a) => a.area);
  const seen = uniq(categoriesSeen);
  const unknownRegions = seen.filter((name) => !observed.includes(name) && !NON_REGION_TABS.includes(name));
  return {
    byArea,
    observedAreas: observed.length,
    categoriesSeen: seen.length,
    unobservedRegions: sorted(unknownRegions),
    nonRegionTabs: NON_REGION_TABS.filter((name) => seen.includes(name)),
    partialAreas: byArea.filter((a) => a.coverage !== 'full').map((a) => a.area),
  };
}

function queueEntry(p) {
  return {
    sourceId: p.sourceId,
    area: p.area,
    year: p.year,
    variant: p.variant,
    fee: p.fee,
    titleKey: p.titleKey,
    sources: sorted(uniq(p.observations.map((o) => o.source))),
  };
}

/** Candidate queue: only in-scope, unambiguous, non-captured, non-paid rows. */
export function buildCandidateQueue(papers, { capturedIds = new Set(), now = new Date(), includeMock = false } = {}) {
  const candidates = [];
  const pendingFreeCheck = [];
  const excluded = {
    outOfYear: 0, captured: 0, member: 0, locked: 0, unknownFee: 0,
    crossRegion: 0, identityConflict: 0, titleConflict: 0, titleCollision: 0,
    missingYear: 0, ambiguousArea: 0, mock: 0,
  };
  const focus = new Set(FOCUS_AREAS);
  for (const p of papers) {
    if (p.kind === 'mock' && !includeMock) { excluded.mock += 1; continue; }
    if (p.flags.crossRegion) { excluded.crossRegion += 1; continue; }
    if (p.flags.identityConflict) { excluded.identityConflict += 1; continue; }
    if (p.flags.titleConflict) { excluded.titleConflict += 1; continue; }
    if (p.flags.titleCollision) { excluded.titleCollision += 1; continue; }
    if (p.year == null) { excluded.missingYear += 1; continue; }
    if (!p.area) { excluded.ambiguousArea += 1; continue; }
    if (!yearAllowed(p.area, p.year, now)) { excluded.outOfYear += 1; continue; }
    if (capturedIds.has(p.sourceId)) { excluded.captured += 1; continue; }
    if (p.fee === FEE.MEMBER) { excluded.member += 1; continue; }
    if (p.fee === FEE.LOCKED) { excluded.locked += 1; continue; }
    if (p.fee === FEE.UNKNOWN) { excluded.unknownFee += 1; continue; }
    // A member marker that cannot be bound to a row, an incomplete page set, or an
    // unpaired id list all force an explicit free check even when another snapshot
    // said "free" or "no marker seen".
    if (p.flags.memberSignal || p.flags.unpaired
      || (p.fee === FEE.FREE_VISIBLE && p.flags.partialCoverage)) {
      pendingFreeCheck.push({
        ...queueEntry(p),
        reasons: [
          ...(p.flags.memberSignal ? ['member-signal-unbound'] : []),
          ...(p.flags.partialCoverage ? ['partial-coverage'] : []),
          ...(p.flags.unpaired ? ['unpaired-page-ids'] : []),
        ],
      });
      continue;
    }
    candidates.push({
      ...queueEntry(p),
      requiresFreeVerification: p.fee === FEE.FREE_VISIBLE,
      priority: focus.has(p.area) ? 'focus' : 'normal',
    });
  }
  const sortQueue = (a, b) => (b.year - a.year)
    || (Number(focus.has(b.area)) - Number(focus.has(a.area)))
    || (a.area || '').localeCompare(b.area || '')
    || a.variant.localeCompare(b.variant)
    || a.sourceId.localeCompare(b.sourceId, 'en', { numeric: true });
  candidates.sort(sortQueue);
  pendingFreeCheck.sort(sortQueue);
  return { candidates, pendingFreeCheck, excluded };
}

function totalsOf(papers, queue, now) {
  const real = papers.filter((p) => p.kind !== 'mock');
  const inScope = real.filter((p) => p.area && p.year != null && yearAllowed(p.area, p.year, now));
  return {
    observations: papers.reduce((sum, p) => sum + p.observations.length, 0),
    uniqueSourceIds: papers.length,
    realSourceIds: real.length,
    mockSourceIds: papers.length - real.length,
    inScope: inScope.length,
    outOfScope: real.filter((p) => p.year != null && p.area && !yearAllowed(p.area, p.year, now)).length,
    pre2016: real.filter((p) => p.year != null && p.year < 2016).length,
    future: real.filter((p) => p.year != null && p.year > now.getFullYear()).length,
    ambiguousArea: real.filter((p) => !p.area).length,
    unknownYear: real.filter((p) => p.year == null).length,
    feeEvidenceDisagreements: real.filter((p) => p.feeConflicts.length).length,
    variantTitleDisagreements: real.filter((p) => p.flags.variantTitleDisagreement).length,
    fee: countsBy(real, (p) => p.fee),
    variants: countsBy(real, (p) => p.variant),
    candidates: queue.candidates.length,
    pendingFreeCheck: queue.pendingFreeCheck.length,
    crossRegion: real.filter((p) => p.flags.crossRegion).length,
    identityConflicts: real.filter((p) => p.flags.identityConflict).length,
    titleCollisions: real.filter((p) => p.flags.titleCollision).length,
    titleConflicts: real.filter((p) => p.flags.titleConflict).length,
    partialCoverage: real.filter((p) => p.flags.partialCoverage).length,
    mock: papers.length - real.length,
  };
}

/** Fields the saved snapshots cannot supply; a single Owner must observe them live. */
export const LIVE_CAPTURE_FIELDS = Object.freeze([
  {
    field: 'row title (sourceId-bound)',
    why: 'national batches store ids/year/variant but no title; title collisions cannot be detected without it',
    from: 'visible shenlun list rows (one Owner, metadata only)',
  },
  {
    field: 'per-sourceId member/lock marker',
    why: 'batch4 四川 memberRows=2 is a known double-count and title-regex-only; it cannot be bound to the two actual rows',
    from: 'row DOM state (member text / lock class), captured together with sourceId',
  },
  {
    field: 'lockStatus / paid for batches 1-3',
    why: 'those snapshots do not expose a per-row lock field; only absence of markers is known',
    from: 'list response or row state already used by the Owner',
  },
  {
    field: 'raw Zhejiang titles',
    why: 'inventory stores only a 12-hex title hash and length, which cannot be compared with normalised titles',
    from: 'Zhejiang inventory regeneration (metadata only)',
  },
]);

/**
 * Pure orchestrator. `snapshots` are already-read JSON objects:
 *   { kind: 'national'|'inventory'|'catalog-live'|'api', file, sha256?, observedAt?, area?, json }
 * Output is deterministic for a fixed `now`.
 */
export function buildShenlunCatalog({
  snapshots = [], capturedIds = new Set(), now = new Date(),
  includeTitles = false, includeMock = false, subject = SUBJECT,
} = {}) {
  const observations = [];
  const regions = [];
  const categoriesSeen = [];
  const sources = [];
  for (const snapshot of snapshots) {
    const options = { file: snapshot.file, observedAt: snapshot.observedAt, area: snapshot.area, subject };
    let normalized;
    if (snapshot.kind === 'national') normalized = normalizeNationalBatch(snapshot.json, options);
    else if (snapshot.kind === 'inventory') normalized = normalizeInventory(snapshot.json, options);
    else if (snapshot.kind === 'catalog-live') normalized = normalizeCatalogLive(snapshot.json, options);
    else if (snapshot.kind === 'api') normalized = normalizeApiSnapshot(snapshot.json, options);
    else throw new Error(`UNKNOWN_SNAPSHOT_KIND: ${snapshot.kind}`);
    observations.push(...normalized.observations);
    regions.push(...normalized.regions);
    if (normalized.categoriesSeen) categoriesSeen.push(...normalized.categoriesSeen);
    sources.push({
      file: snapshot.file,
      kind: snapshot.kind,
      sha256: snapshot.sha256 || null,
      observedAt: snapshot.observedAt || snapshot.json?.at || null,
      records: normalized.observations.length,
    });
  }
  const papers = mergeObservations(observations);
  const titleCollisions = markTitleCollisions(papers);
  // Coverage is an area-level fact. A page-1 API snapshot and the complete three-page
  // set both say "partial" per page; only the area union can support a candidate.
  const preliminary = buildCoverage(papers, regions, { now, categoriesSeen });
  const areaCoverageMap = new Map(preliminary.byArea.map((entry) => [entry.area, entry.coverage]));
  for (const paper of papers) if (paper.area) {
    const coverage = areaCoverageMap.get(paper.area) ?? 'unknown';
    paper.flags.partialCoverage = coverage !== 'full';
    paper.coverage = coverage;
  }
  const queue = buildCandidateQueue(papers, { capturedIds, now, includeMock });
  const coverage = buildCoverage(papers, regions, { now, categoriesSeen });
  const totals = totalsOf(papers, queue, now);
  const crossRegion = papers.filter((p) => p.flags.crossRegion).map((p) => ({ sourceId: p.sourceId, areas: p.areas, year: p.year, variant: p.variant }));
  const identityConflicts = papers.filter((p) => p.flags.identityConflict).map((p) => ({
    sourceId: p.sourceId, areas: p.areas, years: p.years, variants: p.variants,
    fields: p.flags.identityConflicts,
  }));
  const feeConflicts = papers.filter((p) => p.fee === FEE.UNKNOWN && p.feeConflicts.length)
    .map((p) => ({ sourceId: p.sourceId, fee: p.fee, reasons: p.feeConflicts }));
  return {
    schemaVersion: SHENLUN_CATALOG_SCHEMA_VERSION,
    at: now.toISOString(),
    offline: true,
    subject,
    rightsStatus: 'unverified',
    policy: {
      // 2026-10-23：全地区统一下界（1900）；zhejiangAllYears 保留字段兼容既有消费者，
      // 现在对所有地区都成立。
      defaultMinYear: DEFAULT_MIN_YEAR,
      zhejiangAllYears: true,
      maxYear: now.getFullYear(),
      feeRule: 'explicit paid/lock > row marker > free-visible-unverified; conflicts fail closed',
    },
    sources: sources.sort((a, b) => a.file.localeCompare(b.file)),
    totals,
    coverage,
    ambiguities: {
      crossRegion: crossRegion.sort((a, b) => a.sourceId.localeCompare(b.sourceId)),
      identityConflicts: identityConflicts.sort((a, b) => a.sourceId.localeCompare(b.sourceId)),
      titleCollisions,
      feeConflicts: feeConflicts.sort((a, b) => a.sourceId.localeCompare(b.sourceId)),
    },
    excluded: queue.excluded,
    candidates: queue.candidates,
    pendingFreeCheck: queue.pendingFreeCheck,
    needsLiveCapture: LIVE_CAPTURE_FIELDS,
    papers: papers.map((p) => ({
      sourceId: p.sourceId,
      area: p.area,
      areas: p.areas,
      year: p.year,
      years: p.years,
      variant: p.variant,
      variants: p.variants,
      fee: p.fee,
      feeConflicts: p.feeConflicts,
      kind: p.kind,
      titleKey: p.titleKey,
      titleKind: p.titleKind,
      titleLen: p.titleLen,
      ...(includeTitles && p.observations.length ? { title: findTitle(snapshots, p) } : {}),
      flags: p.flags,
      coverage: p.coverage,
      observations: p.observations,
    })),
  };
}

function findTitle(snapshots, paper) {
  for (const snapshot of snapshots) {
    const json = snapshot.json;
    const lists = [];
    if (snapshot.kind === 'api') lists.push(...(json?.body?.list || []));
    if (snapshot.kind === 'catalog-live') for (const record of Object.values(json?.regions || {})) lists.push(...(record.entries || []));
    for (const item of lists) {
      const title = item.title ?? item.name;
      if (text(item.id) === paper.sourceId && title != null) return text(title);
    }
  }
  return null;
}

export { sha256 as sha256Text };
