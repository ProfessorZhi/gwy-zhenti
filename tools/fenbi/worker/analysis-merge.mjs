// 解析页合并（纯函数，不联网）：交白卷后解析页的 DOM 与同一次加载里的 combine/static/solution JSON，
// 按题目身份（data-question-key / globalId === document.questions[].id）写回答案与解析。
// 规则与 driver/t2-collector.mjs、driver/t2-backfill-json.mjs 相同：DOM 优先，JSON 只补空缺。
const strip = s => String(s || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
// 站点 correctAnswer.choice 是 0 基选项索引串（"0"、"2,3"），转为选项字母并按原顺序
export const toLetters = c => String(c ?? '').split(/[^0-9]+/).filter(Boolean).map(x => String.fromCharCode(65 + Number(x))).join('');

export function parseAnalysisDom(html) {
  const byKey = new Map();
  for (const b of String(html || '').split(/<app-ti\b/).slice(1)) {
    const key = (b.match(/data-question-key="([^"]+)"/) || [])[1];
    if (!key) continue;
    const ansSpan = b.match(/<span[^>]*class="[^"]*correct-answer[^"]*"[^>]*>([\s\S]*?)<\/span>/);
    const answer = ansSpan ? strip(ansSpan[1]).replace(/[^A-H]/g, '') : '';
    let expl = null;
    for (const sec of [...b.matchAll(/<section[^>]*result-common-section[^>]*>([\s\S]*?)<\/section>/g)].map(m => m[1])) {
      const tm = sec.match(/<app-solution-title[^>]*>([\s\S]*?)<\/app-solution-title>/);
      const title = tm ? strip(tm[1]) : '';
      if (/解析视频/.test(title)) continue;
      if (/^解析/.test(title)) expl = tm ? sec.slice(tm.index + tm[0].length) : sec;
    }
    byKey.set(key, { answer, expl });
  }
  return byKey;
}

// sanitize: privacy.mjs 的 sanitizeHtml（返回 { html, rejected }）。返回本次写入的计数。
export function mergeAnalysisDom(doc, byKey, sanitize) {
  let answers = 0, explanations = 0;
  for (const q of doc.questions) {
    const s = byKey.get(q.id);
    if (!s || !s.answer || !s.expl || strip(s.expl).length < 20) continue;
    const clean = sanitize(s.expl);
    q.answerHtml = `<p>${s.answer}</p>`;
    q.explanationHtml = clean.html;
    if (clean.rejected) doc.conflicts.push({ scope: 'privacy', id: q.id, field: 'explanationHtml', rejectedReferences: clean.rejected });
    answers++; explanations++;
  }
  return { answers, explanations };
}

export function mergeSolutionJson(doc, sol, sanitize) {
  const stats = { answers: 0, explanations: 0, domJsonMismatch: 0, labelMismatch: 0, missing: 0 };
  if (!sol || !Array.isArray(sol.solutions)) return stats;
  const byG = new Map(sol.solutions.map(s => [String(s.globalId), s]));
  for (const q of doc.questions) {
    const s = byG.get(String(q.id));
    if (!s) { stats.missing++; continue; }
    const letters = toLetters(s.correctAnswer?.choice);
    const opts = new Set((q.options || []).map(o => String(o.label)));
    const labelsUsable = [...opts].some(l => /^[A-H]$/.test(l));
    // 选项标签全为空（判断题样式）时无法比对字母，但索引仍是站点给出的正确答案
    const goodLabel = letters.length > 0 && (!labelsUsable || letters.split('').every(l => opts.has(l)));
    const domA = (String(q.answerHtml || '').match(/[A-H]/g) || []).join('');
    if (domA && letters && domA !== letters) stats.domJsonMismatch++;
    if (letters && strip(q.answerHtml) === '') {
      if (goodLabel) { q.answerHtml = `<p>${letters}</p>`; stats.answers++; } else stats.labelMismatch++;
    }
    // 判断题等无选项题型：站点把答案放在 correctAnswer.answer（纯文本），按原文保存
    if (!q.answerHtml && !letters) {
      const txt = strip(s.correctAnswer?.answer);
      if (txt) { q.answerHtml = `<p>${txt}</p>`; stats.answers++; }
    }
    if (strip(q.explanationHtml).length < 20) {
      const clean = sanitize(String(s.solution || ''));
      if (strip(clean.html).length >= 20) {
        q.explanationHtml = clean.html;
        if (clean.rejected) doc.conflicts.push({ scope: 'privacy', id: q.id, field: 'explanationHtml', rejectedReferences: clean.rejected });
        stats.explanations++;
      }
    }
  }
  return stats;
}

// 交卷前的空白校验：页面上没有任何已选项、也没有"已答 N"提示。
export const isBlank = b => !(b.checked > 0 || b.aria > 0 || Number(b.hint) > 0);
