// 单卷流水线的队列（纯函数）：把目录候选、本地缓存和两本台账合成一条队列。
// 两本台账沿用旧链路的文件，新旧链路可以互相接续：
//   t2 台账（t2-20261019/ledger.json，按缓存目录名）：交卷状态。出现过的卷永不再交第二次。
//   phaseb2 台账（t2-20261019/phaseb2-ledger.json，按 sourceId）：抓题状态。
import { yearAllowed } from '../driver/year-policy.mjs';

const META = {
  国考: { label: '国考', area: '国考', paperDir: '国考', pre: 'gk' },
  浙江: { label: '浙江', area: '浙江', paperDir: '省考/浙江', pre: 'zj' },
  江苏: { label: '江苏', area: '江苏', paperDir: '省考/江苏', pre: 'js' },
  上海: { label: '上海', area: '上海', paperDir: '省考/上海', pre: 'sh' },
  北京: { label: '北京', area: '北京', paperDir: '省考/北京', pre: 'bj' },
  天津: { label: '天津', area: '天津', paperDir: '省考/天津', pre: 'tj' },
  广东: { label: '广东', area: '广东', paperDir: '省考/广东', pre: 'gd' },
  广州: { label: '广州', area: '广州', paperDir: '省考/广州', pre: 'gz' },
  深圳: { label: '深圳', area: '深圳', paperDir: '省考/深圳', pre: 'sz' },
  福建: { label: '福建', area: '福建', paperDir: '省考/福建', pre: 'fj' },
};
const PRE = { 国考: 'gk', 北京: 'bj', 天津: 'tj', 上海: 'sh', 重庆: 'cq', 河北: 'he', 山西: 'sx',
  内蒙古: 'nm', 辽宁: 'ln', 吉林: 'jl', 黑龙江: 'hl', 江苏: 'js', 浙江: 'zj', 安徽: 'ah', 福建: 'fj',
  江西: 'jx', 山东: 'sd', 河南: 'ha', 湖北: 'hb', 湖南: 'hn', 广东: 'gd', 广西: 'gx', 海南: 'hi',
  四川: 'sc', 贵州: 'gz', 云南: 'yn', 西藏: 'xz', 陕西: 'sn', 甘肃: 'gs', 青海: 'qh', 宁夏: 'nx',
  新疆: 'xj', 深圳: 'sz', 广州: 'gz' };
export const metaOf = (area, region) => META[area] || {
  label: region || area, area, paperDir: `省考/${area}`, pre: PRE[area] || 'xx' };
export const variantOf = t => {
  if (/副省级/.test(t)) return 'fushengji';
  if (/地市级/.test(t)) return 'dishiji';
  if (/行政执法/.test(t)) return 'xingzheng';
  if (/A类|A卷/.test(t)) return 'a';
  if (/B类|B卷/.test(t)) return 'b';
  if (/C类|C卷/.test(t)) return 'c';
  if (/县级/.test(t)) return 'county';
  if (/乡镇/.test(t)) return 'township';
  const m = t.match(/行测([12])/); if (m) return 'hangce' + m[1];
  return 'tongkao';
};
const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// 已交卷（或正在交卷时中断）的状态：这些卷不再打开交卷页。
export const SUBMIT_DONE = new Set(['complete', 'submitted_partial', 'out_of_scope', 'not_blank', 'submitting']);

/**
 * cached: [{ key, sourceId, pageUrl, label?, title? }] —— 本地已有缓存的卷（run-summary.json 里有 pageUrl）
 * candidates: 目录候选（build-candidates-live 输出的 candidates）
 * t2Ledger: { papers: { [key]: { status, sourceId } } }；captureLedger: { targets: { [sid]: { status } } }
 * quarantined: Set<sourceId>
 * 返回 [{ kind:'resume'|'new', key, sourceId, ... }]：先续交已抓未交的卷，再抓新卷。
 */
export function buildQueue({ cached = [], candidates = [], t2Ledger = {}, captureLedger = {}, quarantined = new Set() }) {
  const t2 = t2Ledger.papers || {};
  const submittedSids = new Set(Object.values(t2).filter(x => SUBMIT_DONE.has(x?.status)).map(x => String(x.sourceId || '')).filter(Boolean));
  const cachedSids = new Set(cached.map(c => String(c.sourceId)));
  const queue = [], seen = new Set();
  for (const c of cached) {
    const sid = String(c.sourceId);
    if (!sid || seen.has(sid) || quarantined.has(sid)) continue;
    if (SUBMIT_DONE.has(t2[c.key]?.status) || submittedSids.has(sid) || !c.pageUrl) continue;
    seen.add(sid);
    queue.push({ kind: 'resume', key: c.key, sourceId: sid, pageUrl: c.pageUrl, label: c.label || null });
  }
  for (const p of candidates) {
    const meta = metaOf(p.area, p.region);
    if (!yearAllowed(meta.area, p.year)) continue;
    const sid = String(p.id);
    if (seen.has(sid) || quarantined.has(sid) || cachedSids.has(sid) || submittedSids.has(sid)) continue;
    if (captureLedger.targets?.[sid]?.status === 'ok') continue;
    const variant = variantOf(p.title);
    seen.add(sid);
    queue.push({ kind: 'new', key: `${meta.pre}-${p.year}-xingce-${variant}-${sid}`, sourceId: sid,
      label: meta.label, area: meta.area, year: p.year, titleRe: escapeRe(p.title), titleFrag: [String(p.year)],
      identity: { id: sid, title: p.title, subject: 'xingce', year: p.year, area: meta.area, variant },
      paper: `${meta.paperDir}/${p.year}/行测-${variant}.md` });
  }
  return queue;
}

// 取下一卷：在前 lookahead 个里优先挑与该标签页当前目录地区相同的新卷，省掉重新进入目录和切换地区。
export function takeNext(queue, region, lookahead = 10) {
  if (!queue.length) return null;
  if (region) {
    const i = queue.slice(0, lookahead).findIndex(t => t.kind === 'new' && t.label === region);
    if (i > 0) return queue.splice(i, 1)[0];
  }
  return queue.shift();
}
