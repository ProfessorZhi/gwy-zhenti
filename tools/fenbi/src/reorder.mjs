// 异序映射：判定同一份卷子在两个来源之间是否只是**题序/分块**不同。
//
// 设计约束（重要）：
//   * 身份只由**规范化正文完全相同**（exact hash）确立；相似度只用于提出候选，绝不单独定身份。
//   * 匹配必须是**双向互最佳 + 一对一**；一题不得多绑。
//   * 内容雷同的题（如资料分析公共提示语）会自然落进 multiCandidate，交由人工核，不强行绑定。
//   * 本模块不读网络、不读账号，只做纯函数计算。

/** 规范化：NFKC、全角→半角、去空括号、只留中日韩/字母/数字。 */
export function normalizeText(value) {
  return String(value ?? '')
    .replace(/<[^>]*>/g, ' ')
    .normalize('NFKC')
    .replace(/[！-～]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(/　/g, ' ')
    .replace(/[（(]\s*[)）]/g, '')
    .replace(/\s+/g, ' ')
    .replace(/[^一-龥A-Za-z0-9]/g, '')
    .trim();
}

export function bigrams(text) {
  const out = new Set();
  for (let i = 0; i < text.length - 1; i++) out.add(text.slice(i, i + 2));
  return out;
}

export function jaccard(a, b) {
  if (!a.size || !b.size) return 0;
  let shared = 0;
  for (const x of a) if (b.has(x)) shared++;
  return shared / (a.size + b.size - shared);
}

/** 题目的比较签名：题干 + 选项（材料是共享的，不进签名，避免一材料多题互相干扰）。 */
export function questionSignature(q) {
  const stem = normalizeText(q.stem ?? q.contentHtml ?? '');
  const options = (q.options ?? []).map((o) => normalizeText(o.text ?? o.contentHtml ?? ''));
  return { stem, options, combined: stem + '||' + options.join('|') };
}

export function isImageOnly(sig, imageCount) {
  return sig.stem.length < 8 && Number(imageCount) > 0;
}

/**
 * 双向 top-k 一对一匹配。
 * @returns {{matches:Array, multiCandidates:Array, bestForSrc:Map, bestForRepo:Map}}
 */
export function matchQuestions(source, repository, { low = 0.45 } = {}) {
  const sSig = source.map(questionSignature);
  const rSig = repository.map(questionSignature);
  const sBg = sSig.map((s) => bigrams(s.combined));
  const rBg = rSig.map((s) => bigrams(s.combined));

  const pairs = [];
  for (let i = 0; i < source.length; i++) {
    for (let j = 0; j < repository.length; j++) {
      const exact = sSig[i].combined === rSig[j].combined && sSig[i].combined.length > 0;
      const score = exact ? 1 : jaccard(sBg[i], rBg[j]);
      if (exact || score >= low) pairs.push({ i, j, exact, score });
    }
  }

  const bestForSrc = new Map();
  const bestForRepo = new Map();
  for (const p of pairs) {
    const bs = bestForSrc.get(p.i); if (!bs || p.score > bs.score) bestForSrc.set(p.i, p);
    const br = bestForRepo.get(p.j); if (!br || p.score > br.score) bestForRepo.set(p.j, p);
  }

  const matches = [];
  const usedSrc = new Set();
  const usedRepo = new Set();
  for (const p of [...pairs].sort((a, b) => b.score - a.score)) {
    if (usedSrc.has(p.i) || usedRepo.has(p.j)) continue;
    if (bestForSrc.get(p.i) !== p || bestForRepo.get(p.j) !== p) continue; // 必须双向互最佳
    usedSrc.add(p.i); usedRepo.add(p.j);
    matches.push(p);
  }

  const multiCandidates = [];
  for (const [i, best] of bestForSrc) {
    const ties = pairs.filter((p) => p.i === i && p.j !== best.j && p.score === best.score);
    if (ties.length) multiCandidates.push({ sourceIndex: i, repositoryIndexes: [best.j, ...ties.map((t) => t.j)], score: best.score });
  }

  return { matches, multiCandidates, bestForSrc, bestForRepo };
}

/**
 * 把每个源题归入明确类别。不猜测：无法唯一匹配的一律标 unmatched/ambiguous。
 * 类别：exact_same_number | exact_reordered | near_same_number | near_reordered |
 *       weak_candidate_review | ambiguous_multi_candidate | image_only_not_comparable |
 *       unmatched_no_candidate | unmatched_below_threshold | repo_only_absent_in_source
 */
export function classifyQuestions(source, repository, matching, { suggest = 0.85 } = {}) {
  const { matches, multiCandidates, bestForSrc } = matching;
  const ambiguous = new Set(multiCandidates.map((m) => m.sourceIndex));
  const matchedRepo = new Set(matches.map((m) => m.j));
  const rows = [];

  for (let i = 0; i < source.length; i++) {
    const s = source[i];
    const sig = questionSignature(s);
    if (isImageOnly(sig, s.imageCount)) { rows.push({ sourceNumber: s.number ?? null, kind: 'image_only_not_comparable' }); continue; }
    if (ambiguous.has(i)) { rows.push({ sourceNumber: s.number ?? null, kind: 'ambiguous_multi_candidate' }); continue; }
    const m = matches.find((x) => x.i === i);
    if (!m) {
      const best = bestForSrc.get(i);
      rows.push({ sourceNumber: s.number ?? null, kind: best ? 'unmatched_below_threshold' : 'unmatched_no_candidate',
        bestScore: best ? Number(best.score.toFixed(3)) : 0, bestRepositoryNumber: best ? repository[best.j].number ?? null : null });
      continue;
    }
    const repN = repository[m.j].number ?? null;
    const same = (s.number ?? null) === repN;
    const kind = m.exact ? (same ? 'exact_same_number' : 'exact_reordered')
      : m.score >= suggest ? (same ? 'near_same_number' : 'near_reordered') : 'weak_candidate_review';
    rows.push({ sourceNumber: s.number ?? null, repositoryNumber: repN, kind, score: Number(m.score.toFixed(3)) });
  }

  for (let j = 0; j < repository.length; j++) {
    if (!matchedRepo.has(j)) rows.push({ repositoryNumber: repository[j].number ?? null, kind: 'repo_only_absent_in_source' });
  }
  return rows;
}

/** 覆盖率：已建立一对一映射的源题占比（仅计 non-image-only）。 */
export function coverage(source, rows) {
  const imageOnly = rows.filter((r) => r.kind === 'image_only_not_comparable').length;
  const denom = source.length - imageOnly;
  if (denom <= 0) return 0;
  const mapped = rows.filter((r) => ['exact_same_number', 'exact_reordered', 'near_same_number', 'near_reordered', 'weak_candidate_review'].includes(r.kind)).length;
  return mapped / denom;
}

/** 汇总计数，供 metadata-only 报告使用。 */
export function summarize(rows) {
  const counts = {};
  for (const r of rows) counts[r.kind] = (counts[r.kind] || 0) + 1;
  return counts;
}
