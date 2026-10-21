// 年份准入策略：浙江允许真实可见的全部历史年份；其他地区维持 2016–当前年。
// 纯函数，便于离线 fixture 测试。上界始终是当前自然年，防止未来年份/脏数据。
export const AREA_MIN_YEAR = { 浙江: 1900 };

export function yearAllowed(area, year, now = new Date()) {
  const y = Number(year);
  if (!Number.isInteger(y)) return false;
  const max = now.getFullYear();
  const min = Object.prototype.hasOwnProperty.call(AREA_MIN_YEAR, area) ? AREA_MIN_YEAR[area] : 2016;
  return y >= min && y <= max;
}
