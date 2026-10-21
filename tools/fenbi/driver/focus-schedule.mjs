// 重点区低占空比重扫的纯调度逻辑（不联网、不读站点），便于离线单测。
// 规则：距上次任一重点区扫描 ≥ intervalMs 才轮转下一个地区；游标只在成功后推进。
export const FOCUS_REGIONS = ['国考', '浙江', '江苏', '上海', '北京', '天津', '广东', '广州', '深圳', '福建'];

export function chooseFocusScan(state, regions, now, intervalMs) {
  const last = Date.parse(state?.focusLastScanAt || 0);
  if (Number.isFinite(last) && last > 0 && now - last < intervalMs) {
    return { due: false, waitMs: intervalMs - (now - last), lastScanAt: state.focusLastScanAt };
  }
  const n = regions.length;
  const idx = (((state?.focusIndex | 0) % n) + n) % n;
  return { due: true, index: idx, region: regions[idx], lastScanAt: state?.focusLastScanAt || null };
}

export function applyFocusSuccess(state, regions, region, atIso, rec = null) {
  const n = regions.length;
  const idx = regions.indexOf(region);
  const nextIndex = idx >= 0 ? (idx + 1) % n : ((state?.focusIndex | 0) + 1) % n;
  state.focusIndex = nextIndex;
  state.focusLastScanAt = atIso;
  state.focusScans = (state.focusScans || 0) + 1;
  state.focusFailures = 0;
  const rd = (state.regions ||= {});
  const rs = (rd[region] ||= {});
  rs.firstIndexedAt ||= atIso;
  rs.lastScannedAt = atIso;
  rs.lastStatus = rec?.status ?? 'observed';
  rs.lastTotal = rec?.total ?? null;
  rs.lastRows = rec?.rows ?? null;
  rs.lastCoverage = rec?.coverage ?? null;
  rs.lastPageLimitApplied = rec?.pageLimitApplied ?? null;
  return state;
}

export function applyRegionScan(state, region, atIso, rec = null, { firstIndexedAt = null } = {}) {
  const rd = (state.regions ||= {});
  const rs = (rd[region] ||= {});
  rs.firstIndexedAt ||= firstIndexedAt || atIso;
  rs.lastScannedAt = atIso;
  rs.lastStatus = rec?.status ?? 'observed';
  rs.lastTotal = rec?.total ?? null;
  rs.lastRows = rec?.rows ?? null;
  rs.lastCoverage = rec?.coverage ?? null;
  rs.lastPageLimitApplied = rec?.pageLimitApplied ?? null;
  return rs;
}
