// 异序映射：判定同一份卷子在两个来源之间是否只是**题序/分块**不同。
//
// 设计约束（重要）：
//   * 身份证据只能来自 **normalized_equal**（规范化后完全相同）——**不是**"原文字节相同"。
//     标点/空白/全角折叠都会让不同原文判等，因此它**不能**当作"官方同卷认证"。
//   * 相似度只用于提出候选，**绝不单独定身份**。
//   * 匹配必须**双向互最佳 + 一对一 + 两侧均无同分并列**；任何并列一律进 reviewCandidates，不绑定。
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

/** 题目的比较签名：题干 + 选项（材料是共享的，不进签名）。 */
export function questionSignature(q) {
  const stem = normalizeText(q.stem ?? q.contentHtml ?? '');
  const options = (q.options ?? []).map((o) => normalizeText(o.text ?? o.contentHtml ?? ''));
  // contentLength 才是"有没有实际内容"的判据：combined 里的 '||' 分隔符会让空题看起来非空。
  return { stem, options, contentLength: stem.length + options.join('').length,
    combined: stem + '||' + options.join('|') };
}

export function isImageOnly(sig, imageCount) {
  return sig.stem.length < 8 && Number(imageCount) > 0;
}

/**
 * 双向 top-k 一对一匹配。并列（ambiguous）**一律不绑定**，进 reviewCandidates。
 * @returns {{matches:Array, reviewCandidates:Array, bestForSource:Map, bestForRepository:Map}}
 */
export function matchQuestions(source, repository, { low = 0.45 } = {}) {
  const sSig = source.map(questionSignature);
  const rSig = repository.map(questionSignature);
  const sBg = sSig.map((s) => bigrams(s.combined));
  const rBg = rSig.map((s) => bigrams(s.combined));

  // 图片题不可比较 → 不参与匹配，否则会出现"mapping 里有它、分类里却被排除"的自相矛盾。
  const sourceImageOnly = sSig.map((sig, i) => isImageOnly(sig, source[i].imageCount));
  const pairs = [];
  for (let i = 0; i < source.length; i++) {
    if (sourceImageOnly[i]) continue;
    for (let j = 0; j < repository.length; j++) {
      // 无实际内容的签名（空题干+空选项）不得参与任何比较：
      // 两者的 combined 都会塌缩成 '||'，bigram 集合相同 → jaccard 会错误地给出 1。
      if (sSig[i].contentLength === 0 || rSig[j].contentLength === 0) continue;
      // 注意：判等的是**规范化后**的字符串，不是原文字节。
      const normalizedEqual = sSig[i].combined === rSig[j].combined;
      const score = normalizedEqual ? 1 : jaccard(sBg[i], rBg[j]);
      // score 为 0 表示毫无共同 bigram，即使 low=0 也不得成为候选。
      if (normalizedEqual || (score > 0 && score >= low)) pairs.push({ i, j, normalizedEqual, score });
    }
  }

  const bestForSource = new Map();
  const bestForRepository = new Map();
  for (const p of pairs) {
    const bs = bestForSource.get(p.i); if (!bs || p.score > bs.score) bestForSource.set(p.i, p);
    const br = bestForRepository.get(p.j); if (!br || p.score > br.score) bestForRepository.set(p.j, p);
  }
  const tied = (map, key, self) => pairs.some((p) => p !== self
    && ((map === bestForSource && p.i === key) || (map === bestForRepository && p.j === key))
    && p.score === map.get(key).score);

  const ambiguousSource = new Set();
  const ambiguousRepository = new Set();
  for (const [i, best] of bestForSource) if (tied(bestForSource, i, best)) ambiguousSource.add(i);
  for (const [j, best] of bestForRepository) if (tied(bestForRepository, j, best)) ambiguousRepository.add(j);

  const matches = [];
  const usedSource = new Set();
  const usedRepository = new Set();
  for (const p of [...pairs].sort((a, b) => b.score - a.score)) {
    if (usedSource.has(p.i) || usedRepository.has(p.j)) continue;
    if (ambiguousSource.has(p.i) || ambiguousRepository.has(p.j)) continue; // 并列一律不绑定
    if (bestForSource.get(p.i) !== p || bestForRepository.get(p.j) !== p) continue; // 必须双向互最佳
    usedSource.add(p.i); usedRepository.add(p.j);
    matches.push(p);
  }

  // 供人工复核的候选：所有并列最佳
  const reviewCandidates = [];
  for (const i of ambiguousSource) {
    const best = bestForSource.get(i);
    const candidates = pairs.filter((p) => p.i === i && p.score === best.score).map((p) => p.j);
    reviewCandidates.push({ sourceIndex: i, repositoryIndexes: candidates, score: best.score,
      reason: ambiguousRepository.size ? 'tie_on_both_sides_or_repository' : 'tie_across_repository' });
  }

  return { matches, reviewCandidates, bestForSource, bestForRepository };
}

/** 绑定对的等级。manual 只出现在 reviewCandidates，不会进 matches。 */
export function gradeMatch(pair, source, repository, { suggest = 0.85 } = {}) {
  const same = (source[pair.i].number ?? null) === (repository[pair.j].number ?? null);
  if (pair.normalizedEqual) return same ? 'normalized_equal_same_number' : 'normalized_equal_reordered';
  if (pair.score >= suggest) return 'near';
  return 'weak';
}

/**
 * 逐题分类。无法唯一确定的**不猜**：
 *   并列 → 'manual_review_ambiguous'；无候选 → 'unmatched_no_candidate'。
 */
export function classifyQuestions(source, repository, matching, { suggest = 0.85 } = {}) {
  const { matches, reviewCandidates, bestForSource } = matching;
  const ambiguous = new Map(reviewCandidates.map((r) => [r.sourceIndex, r]));
  const matchedRepository = new Set(matches.map((m) => m.j));
  const rows = [];

  for (let i = 0; i < source.length; i++) {
    const s = source[i];
    if (isImageOnly(questionSignature(s), s.imageCount)) {
      rows.push({ sourceNumber: s.number ?? null, kind: 'image_only_not_comparable' });
      continue;
    }
    if (ambiguous.has(i)) {
      const r = ambiguous.get(i);
      rows.push({ sourceNumber: s.number ?? null, kind: 'manual_review_ambiguous',
        candidates: r.repositoryIndexes.map((j) => repository[j].number ?? null), score: Number(r.score.toFixed(3)) });
      continue;
    }
    const pair = matches.find((x) => x.i === i);
    if (!pair) {
      const best = bestForSource.get(i);
      rows.push({ sourceNumber: s.number ?? null, kind: best ? 'unmatched_below_threshold' : 'unmatched_no_candidate',
        bestScore: best ? Number(best.score.toFixed(3)) : 0,
        bestRepositoryNumber: best ? repository[best.j].number ?? null : null });
      continue;
    }
    rows.push({ sourceNumber: s.number ?? null, repositoryNumber: repository[pair.j].number ?? null,
      kind: gradeMatch(pair, source, repository, { suggest }), score: Number(pair.score.toFixed(3)) });
  }

  for (let j = 0; j < repository.length; j++) {
    if (!matchedRepository.has(j)) rows.push({ repositoryNumber: repository[j].number ?? null, kind: 'repo_only_absent_in_source' });
  }
  return rows;
}

/** 可映射源题数（剔除图片题）。 */
export function eligibleSourceCount(source, rows) {
  return source.length - rows.filter((r) => r.kind === 'image_only_not_comparable').length;
}

const BOUND = ['normalized_equal_same_number', 'normalized_equal_reordered', 'near', 'weak'];
export const EXACT_BOUND = ['normalized_equal_same_number', 'normalized_equal_reordered'];

/**
 * 三种覆盖口径，**必须分开报告**，不得混用：
 *   exact        仅 normalized_equal
 *   highConfidence   exact + near（**不含 weak**）——可用于"已映射"表述
 *   candidates    exact + near + weak（仅表示"有候选"，不得称可用覆盖）
 */
export function coverageTiers(source, rows) {
  const eligible = eligibleSourceCount(source, rows);
  if (eligible <= 0) return { eligible: 0, exact: 0, highConfidence: 0, candidates: 0,
    coverageExact: 0, coverageHighConfidence: 0, coverageCandidates: 0 };
  const exact = rows.filter((r) => EXACT_BOUND.includes(r.kind)).length;
  const near = rows.filter((r) => r.kind === 'near').length;
  const weak = rows.filter((r) => r.kind === 'weak').length;
  return {
    eligible, exact, near, weak,
    highConfidence: exact + near,
    candidates: exact + near + weak,
    coverageExact: exact / eligible,
    coverageHighConfidence: (exact + near) / eligible,
    coverageCandidates: (exact + near + weak) / eligible,
  };
}

/** 逆序指标：**同时**给相邻下降点与真实逆序对，避免用前者冒充单调性。 */
export function orderMetrics(mapping) {
  const sorted = [...mapping].sort((a, b) => a.sourceNumber - b.sourceNumber);
  let adjacentDescents = 0;
  for (let i = 1; i < sorted.length; i++) if (sorted[i].repositoryNumber < sorted[i - 1].repositoryNumber) adjacentDescents++;
  let inversions = 0;
  let totalPairs = 0;
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      totalPairs++;
      if (sorted[i].repositoryNumber > sorted[j].repositoryNumber) inversions++;
    }
  }
  return { count: sorted.length, adjacentDescents, inversions, totalPairs,
    inversionRate: totalPairs ? inversions / totalPairs : 0 };
}

/** 全部偏移（repN − srcN）及其频次，不许只列前几个。 */
export function offsetHistogram(mapping) {
  const hist = {};
  for (const m of mapping) {
    const off = m.repositoryNumber - m.sourceNumber;
    hist[off] = (hist[off] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(hist).map(([k, v]) => [k, v]).sort((a, b) => Number(a[0]) - Number(b[0])));
}

export function summarize(rows) {
  const counts = {};
  for (const r of rows) counts[r.kind] = (counts[r.kind] || 0) + 1;
  return counts;
}
