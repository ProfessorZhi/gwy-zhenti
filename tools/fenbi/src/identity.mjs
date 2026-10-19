/**
 * Paper identity helpers shared by promote-all and pipeline-board.
 *
 * Both must agree on how a receipt is matched to a manifest row, otherwise the
 * board silently disagrees with what the publisher actually did. Keeping one
 * copy here is the cheapest way to stop the two normalisations drifting apart.
 *
 * Pure functions, no I/O except readManifestIdentities which only reads the
 * repository's own catalog.
 */
import fs from 'node:fs/promises';
import path from 'node:path';

export const normVariant = v => {
  const s = String(v ?? '').trim().toLowerCase();
  const map = { tongkao: '统考', '统考': '统考', a: 'a', b: 'b', c: 'c', 'a类': 'a', 'b类': 'b', 'c类': 'c',
    county: '县级', '县级': '县级', township: '乡镇', '乡镇': '乡镇', dishiji: '地市级', '地市级': '地市级',
    fushengji: '副省级', '副省级': '副省级', xingzheng: '行政执法', '行政执法': '行政执法' };
  return map[s] || s.replace(/[类卷]/g, '');
};

export const normSubject = s => ({ 行测: 'xingce', xingce: 'xingce', 申论: 'shenlun', shenlun: 'shenlun' }[String(s ?? '').trim()] || String(s ?? '').trim());

export const identityKey = r => [r.area, String(r.year), normSubject(r.subject ?? r.paper_type), normVariant(r.variant ?? r.paper_type)].join('|');

/** Completeness rank used to pick one source when several target the same paper. */
export const rank = r => [r.answerNumbers?.length ?? 0, r.counts?.sourceQuestions ?? 0, Number(r.sourceId) || 0];

export const better = (a, b) => {
  const x = rank(a), y = rank(b);
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] > y[i];
  return false;
};

/** identityKey -> [manifest paths]. */
export async function readManifestIdentities(repoRoot) {
  const text = await fs.readFile(path.join(repoRoot, 'catalog/manifest.jsonl'), 'utf8').catch(() => '');
  const map = new Map();
  for (const line of text.split(/\r?\n/u).filter(Boolean)) {
    try { const row = JSON.parse(line); const key = identityKey(row); if (!map.has(key)) map.set(key, []); map.get(key).push(row.path); } catch {}
  }
  return map;
}
