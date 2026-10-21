// 试卷身份核对（纯函数）。目录 sourceId 与实际打开、交卷的练习是不是同一份卷：
//   1. 目录行按完整标题精确匹配；标题互相包含（如"……（地市级）"与"……（地市级）网友回忆版"）时不靠"第一个匹配"猜。
//   2. 练习页/解析页加载的 JSON 里出现的 paperId 与 sourceId 比对：一致才算有来源身份证据，不一致不交卷、不落地。
const norm = s => String(s || '').replace(/\s+/g, '').replace(/[（]/g, '(').replace(/[）]/g, ')');

// rows: 目录里含该标题的各行文字；otherTitles: 同地区其他卷的标题。
// 行文字以本卷标题开头、且不以任何"以本卷标题开头的更长标题"开头的行，才是本卷；恰好一行才点击。
export function pickRow(rows, title, otherTitles = []) {
  const t = norm(title);
  const longer = otherTitles.map(norm).filter(o => o.length > t.length && o.startsWith(t));
  const mine = x => !longer.some(o => x.includes(o));
  let own = rows.map((text, i) => [i, norm(text)]).filter(([, x]) => x.startsWith(t) && mine(x));
  if (!own.length) own = rows.map((text, i) => [i, norm(text)]).filter(([, x]) => x.includes(t) && mine(x));
  if (own.length === 1) return own[0][0];
  return { error: own.length ? 'AMBIGUOUS_ROW' : 'ROW_NOT_FOUND' };
}

// 在 JSON 里收集名为 paperId 的值（深度有限，避免大对象）。
export function collectPaperIds(json, out = new Set(), depth = 0) {
  if (!json || typeof json !== 'object' || depth > 6) return out;
  if (Array.isArray(json)) { for (const x of json.slice(0, 50)) collectPaperIds(x, out, depth + 1); return out; }
  for (const [k, v] of Object.entries(json)) {
    if (/^paperId$/i.test(k) && (typeof v === 'number' || typeof v === 'string') && /^\d{1,15}$/.test(String(v))) out.add(String(v));
    else if (v && typeof v === 'object') collectPaperIds(v, out, depth + 1);
  }
  return out;
}

// verified：观察到的 paperId 中有 sourceId 且没有别的；mismatch：只观察到别的；unobserved：没观察到。
export function bindingStatus(ids, sourceId) {
  const set = new Set([...ids].map(String));
  if (!set.size) return 'unobserved';
  if (set.has(String(sourceId))) return set.size === 1 ? 'verified' : 'mixed';
  return 'mismatch';
}

// 同一地区同一年里，标题互相包含的其他卷（可能被"包含匹配"误选）。
export function ambiguousTitles(candidates) {
  const out = new Map();
  for (const a of candidates) for (const b of candidates) {
    if (a === b || a.area !== b.area || a.year !== b.year) continue;
    if (norm(b.title).includes(norm(a.title))) (out.get(String(a.id)) || out.set(String(a.id), []).get(String(a.id))).push(String(b.id));
  }
  return out;
}
