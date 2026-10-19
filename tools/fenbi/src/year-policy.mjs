/**
 * Examination-year admission policy, shared by validateDocument and batch-promote.
 *
 * Historically everything is floored at 2016. Zhejiang is the first province whose
 * genuinely older papers are being captured from a real, observed source, so it gets
 * an explicit, area-scoped floor instead of a blanket widening. Nothing here trusts a
 * year on its own: callers still have to satisfy the identity, source-URL, target-SHA
 * and rights gates that already exist.
 *
 * Keep the exceptions explicit and area-scoped. Adding a province here must be backed
 * by real observed captures, not by a desire to turn old papers into A grades.
 */

/** Absolute floor: earlier than this is not a modern civil-service paper. */
export const MIN_MODERN_YEAR = 1900;

/** Default floor for every area not listed below. */
export const DEFAULT_FLOOR = 2016;

/** Areas whose real historical papers are captured, mapped to their own floor. */
export const HISTORICAL_AREA_FLOORS = { 浙江: MIN_MODERN_YEAR };

const normalizeArea = area => String(area ?? '').trim();

/** Lowest year admitted for this identity's area. */
export function yearFloor(identity = {}) {
  return HISTORICAL_AREA_FLOORS[normalizeArea(identity.area)] ?? DEFAULT_FLOOR;
}

/** Highest year admitted: the current calendar year, never a future one. */
export function yearCeiling(now = new Date()) {
  return now.getFullYear();
}

/** True when the identity's year is a real, admissible examination year. */
export function yearAllowed(identity = {}, now = new Date()) {
  const raw = identity?.year;
  if (raw === null || raw === undefined || String(raw).trim() === '') return false;
  const year = Number(raw);
  if (!Number.isInteger(year)) return false;
  if (year < MIN_MODERN_YEAR || year > yearCeiling(now)) return false;
  return year >= yearFloor(identity);
}

/**
 * Target-path rule. Other areas keep the original 20xx shape; an area with a
 * historical floor may also use 19xx. The year itself must still pass yearAllowed.
 */
export function targetPathAllowed(pathname, area, now = new Date()) {
  const match = /^(?:国考|省考\/[^/]+)\/(\d{4})\/(?:行测|申论)-[^/]+\.md$/u.exec(String(pathname ?? ''));
  if (!match) return false;
  const year = Number(match[1]);
  if (!yearAllowed({ area, year }, now)) return false;
  if (normalizeArea(area) === '浙江') return true;
  return year >= 2000 && year <= 2099; // unchanged original rule for everyone else
}
