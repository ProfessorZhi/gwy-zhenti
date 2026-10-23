// 年份准入策略：粉笔上能看到的全部年份都要（用户 2026-10-23 决定，取消 2016 下限，不限地区）。
// 纯函数，便于离线 fixture 测试。上界始终是当前自然年，防止未来年份/脏数据。
export const AREA_MIN_YEAR = {};
// 没有分区覆盖时的下界。2026-10-23 起对所有地区统一为 1900（原为「其他地区 2016」）。
export const DEFAULT_MIN_YEAR = 1900;

export function yearAllowed(area, year, now = new Date()) {
  const y = Number(year);
  if (!Number.isInteger(y)) return false;
  const max = now.getFullYear();
  const min = Object.prototype.hasOwnProperty.call(AREA_MIN_YEAR, area) ? AREA_MIN_YEAR[area] : DEFAULT_MIN_YEAR;
  return y >= min && y <= max;
}
