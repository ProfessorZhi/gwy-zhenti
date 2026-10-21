// 子进程风控回执的统一判定。各子进程 summary 形状不同：
//   t2-collector       { stopReason, metrics: { risk: { captcha, loginLost, http403, http429 } } }
//   p0-discover        { risk: { captcha, unauthorized, rateLimited } }
//   t2-asset-pass      { risk: { s401_403, s429_503 } }
// hard：验证码、登录失效、未授权、子进程已因限流自停 → 立即 STOP。
// soft：403/429 次数 → 计入滑动窗口，一小时内累计达到阈值才 STOP，否则退避（与抓取计划第七节一致）。
export const SOFT_LIMIT_PER_HOUR = 3;

export function classifyRisk(summary) {
  if (!summary || typeof summary !== 'object') return { hard: [], soft: 0 };
  const r = { ...(summary.risk || {}), ...(summary.metrics?.risk || {}) };
  const hard = [];
  if (r.captcha > 0) hard.push('captcha');
  if (r.loginLost > 0) hard.push('login_lost');
  if (r.unauthorized > 0) hard.push('unauthorized');
  if (['captcha', 'login_lost', 'rate_limited_3_per_hour'].includes(summary.stopReason)) hard.push(summary.stopReason);
  const soft = (r.http403 || 0) + (r.http429 || 0) + (r.rateLimited || 0) + (r.s401_403 || 0) + (r.s429_503 || 0);
  return { hard: [...new Set(hard)], soft };
}

// 记录 soft 命中并返回本次是否应 STOP。hits 是时间戳数组（会被就地修剪），由调用方持久化。
export function riskDecision(summary, hits, now = Date.now()) {
  const { hard, soft } = classifyRisk(summary);
  for (let i = 0; i < soft; i++) hits.push(now);
  const recent = hits.filter(t => t > now - 3600e3);
  hits.splice(0, hits.length, ...recent);
  if (hard.length) return { action: 'stop', reason: hard.join(','), soft, recent: recent.length };
  if (recent.length >= SOFT_LIMIT_PER_HOUR) return { action: 'stop', reason: 'http_403_429_limit', soft, recent: recent.length };
  if (soft) return { action: 'backoff', reason: 'http_403_429', soft, recent: recent.length };
  return { action: 'ok', soft: 0, recent: recent.length };
}
