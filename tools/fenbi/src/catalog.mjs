import { extractCatalog } from './model.mjs';

/** Adapters for list envelopes actually observed in the authenticated web client. */
export function normalizeCatalogPayload(payload, meta) {
  if (!payload || typeof payload !== 'object') return { papers: [], labels: [], pages: [] };
  const pathname = new URL(meta.url).pathname;
  let normalized = payload;
  if (/\/papers(?:\/v2)?\/?$/.test(pathname)) {
    const list = payload.list ?? payload.data?.list ?? (Array.isArray(payload) ? payload : null);
    if (Array.isArray(list)) normalized = { papers: list };
  } else if (/\/subLabels\/?$/.test(pathname)) {
    const list = Array.isArray(payload) ? payload : payload.list ?? payload.data?.list;
    const labels = [];
    const visit = (items, parentId = null) => {
      for (const item of items || []) {
        const id = item.id ?? item.labelMeta?.id;
        if (id === undefined || id === null) continue;
        labels.push({ id, title: item.title || item.name, parentId,
          declaredPaperCount: item.labelMeta?.paperCount ?? null,
          declaredPaperIds: Array.isArray(item.labelMeta?.paperIds) ? item.labelMeta.paperIds.map(String) : null });
        if (Array.isArray(item.childrenLabels)) visit(item.childrenLabels, id);
      }
    };
    if (Array.isArray(list)) { visit(list); normalized = { labels }; }
  }
  const result = extractCatalog(normalized, { ...meta, labelId: new URL(meta.url).searchParams.get('labelId') });
  if (normalized.labels) for (const label of result.labels) {
    const original = normalized.labels.find(item => String(item.id) === String(label.id));
    if (original) Object.assign(label, { declaredPaperCount: original.declaredPaperCount ?? null, declaredPaperIds: original.declaredPaperIds ?? null });
  }
  const info = payload.pageInfo ?? payload.data?.pageInfo;
  result.pages = info ? [{ url: meta.url, subject: meta.subject, labelId: new URL(meta.url).searchParams.get('labelId'),
    totalItems: info.totalItem ?? null, totalPages: info.totalPage ?? null, currentPage: info.currentPage ?? null, pageSize: info.pageSize ?? null }] : [];
  return result;
}

export function mergeCatalog(target, incoming) {
  for (const group of ['papers', 'labels']) for (const item of incoming[group]) {
    const key = x => `${x.subject}:${x.id}`;
    const old = target[group].find(x => key(x) === key(item));
    if (old) Object.assign(old, Object.fromEntries(Object.entries(item).filter(([, value]) => value !== null && value !== undefined)));
    else target[group].push(item);
  }
  target.pages ||= [];
  for (const page of incoming.pages || []) {
    const old = target.pages.find(item => item.url === page.url);
    if (old) Object.assign(old, page); else target.pages.push(page);
  }
}
