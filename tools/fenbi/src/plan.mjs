import { publicUrl } from './config.mjs';

export function inferIdentity(paper, labels = []) {
  const label = labels.find(x => String(x.id) === String(paper.labelId));
  const text = [paper.title, paper.area, label?.title, label?.name].filter(Boolean).join(' ');
  const area = paper.area || ['广州', '深圳', '浙江', '江苏', '上海', '北京', '天津', '广东', '福建'].find(x => text.includes(x)) || (/国考|国家公务员|中央机关/.test(text) ? '国考' : null);
  const year = Number(paper.year || text.match(/20\d{2}/)?.[0]) || null;
  let variant = paper.variant || null;
  if (!variant) {
    const found = text.match(/副省级|地市级|行政执法|县级以上|县镇|省市|乡镇|公安|[ABCＡＢＣ]\s*类|统考/);
    variant = found?.[0].replace(/\s/g, '') || null;
  }
  return { id: String(paper.id), title: paper.title, subject: paper.subject, year, area, variant };
}

const variantKey = value => String(value || '').normalize('NFKC').replace(/[\s（）()]/g, '').replace(/[类卷]/g, '');
const subjectKey = value => ({ 行测: 'xingce', 申论: 'shenlun' }[value] || value);

export function makePlan(catalog, inventory, scope, { all = false } = {}) {
  const jobs = [], excluded = [];
  for (const paper of catalog.papers || []) {
    if (/模拟|模考|预测|密卷|冲刺|练习|事业单位|选调生/.test(paper.title || '')) {
      excluded.push({ id: paper.id, title: paper.title, reason: 'not_a_verified_civil_service_past_paper' }); continue;
    }
    const identity = inferIdentity(paper, catalog.labels);
    if (!identity.year || !identity.area || !['xingce', 'shenlun'].includes(identity.subject)) {
      excluded.push({ id: identity.id, title: paper.title, reason: 'identity_unknown' }); continue;
    }
    if (identity.year < scope.fromYear || identity.year > scope.toYear || !scope.areas.includes(identity.area)) continue;
    // Guangzhou municipal examinations must never match Guangdong provincial papers.
    const candidates = inventory.filter(row => {
      const area = row.path?.includes('广州市考') ? '广州' : row.area;
      return String(row.year) === String(identity.year) && area === identity.area && subjectKey(row.subject) === identity.subject;
    });
    const matches = identity.variant ? candidates.filter(row => variantKey(row.paper_type) === variantKey(identity.variant)) : [];
    const missing = ['missing_original_numbers', 'missing_answer_numbers', 'missing_option_numbers', 'known_material_gaps', 'missing_stem_figure_numbers'];
    const hasGap = row => missing.some(key => Array.isArray(row[key]) ? row[key].length > 0 : Boolean(row[key])) || Boolean(row.issues?.length);
    if (!all && matches.length === 1 && !hasGap(matches[0])) continue;
    let url = null;
    if (paper.url) { try { url = publicUrl(paper.url); } catch {} }
    jobs.push({
      identity, url, expected: { questions: Number.isInteger(paper.questionCount) && paper.questionCount > 0 ? paper.questionCount : null, materials: null, questionNumbers: null, materialIds: null },
      expectedBasis: paper.questionCount ? 'observed_source_catalog' : 'unknown',
      repositoryMatches: matches.map(row => row.path),
      reason: !identity.variant ? 'variant_needs_review' : matches.length > 1 ? 'ambiguous_repository_match' : matches.length === 0 ? 'no_exact_repository_match' : 'existing_quality_gap',
      status: !identity.variant ? 'needs_identity_review' : !url ? 'needs_observed_paper_url' : 'ready',
    });
  }
  return { schemaVersion: 1, generatedAt: new Date().toISOString(), source: 'fenbi_observed_catalog',
    catalogComplete: false, note: 'Only observed catalog entries are compared. Unseen categories and papers are unknown, not absent.', jobs, excluded };
}

export function parseInventory(text) {
  return text.split('\n').filter(x => x.trim()).map((line, index) => {
    try { return JSON.parse(line); } catch { throw new Error(`Invalid repository inventory line ${index + 1}`); }
  });
}
