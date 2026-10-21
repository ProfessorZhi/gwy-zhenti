// T2 补全：把解析页同一次加载中观察到的第一方 JSON（combine/static/solution）
// 按唯一稳定身份 globalId === document.questions[].id 合并进本地缓存。
// 只读本地 payload，不联网、不打印题文/答案；输出仅计数。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const PAYLOADS = WORK + '/t2-20261019/payloads';
const PAPERS = WORK + '/papers';
const NO_PAPERS = new Set(['sz-2025-xingce-tongkao-5232321']); // T1 已完成，保持不动

const { sanitizeHtml } = await import(B + '/tools/fenbi/src/privacy.mjs');
const { collectAssetUrls } = await import(B + '/tools/fenbi/src/model.mjs');
const { validateDocument } = await import(B + '/tools/fenbi/src/validate.mjs');

const stripTags = s => String(s || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
// 站点 correctAnswer.choice 是 0 基选项索引串（"0"、"2,3"），转为选项字母并按原顺序
const toLetters = c => String(c ?? '').split(/[^0-9]+/).filter(Boolean).map(x => String.fromCharCode(65 + Number(x))).join('');

const payloadDirs = await fs.readdir(PAYLOADS);
let total = { papers: 0, filledAnswers: 0, filledExplanations: 0, stillMissingAnswer: 0,
  stillMissingExplanation: 0, domJsonMismatch: 0, labelMismatch: 0, labelUnavailable: 0, nonChoiceAnswers: 0, solutionMissing: 0 };

async function findSolution(dir) {
  for (const f of await fs.readdir(dir)) {
    const raw = await fs.readFile(path.join(dir, f), 'utf8').catch(() => null);
    if (!raw) continue;
    let j; try { j = JSON.parse(raw); } catch { continue; }
    if (j && Array.isArray(j.solutions)) {
      const st = await fs.stat(path.join(dir, f));
      return { j, at: st.mtime.toISOString() };
    }
  }
  return null;
}

for (const d of payloadDirs) {
  if (NO_PAPERS.has(d)) continue;
  const docPath = path.join(PAPERS, d, 'document.json');
  if (!(await fs.access(docPath).then(() => true).catch(() => false))) continue;
  const found = await findSolution(path.join(PAYLOADS, d));
  if (!found) continue;
  const { j: sol, at: solAt } = found;
  const doc = JSON.parse(await fs.readFile(docPath, 'utf8'));
  const byG = new Map(sol.solutions.map(s => [String(s.globalId), s]));
  total.papers++;

  let fa = 0, fe = 0;
  for (const q of doc.questions) {
    const s = byG.get(String(q.id));
    if (!s) { total.solutionMissing++; continue; }
    const letters = toLetters(s.correctAnswer?.choice);
    const opts = new Set((q.options || []).map(o => String(o.label)));
    const labelsUsable = [...opts].some(l => /^[A-H]$/.test(l));
    // 选项标签全为空（判断题样式）时无法比对字母，但索引仍是站点给出的正确答案
    const goodLabel = letters.length > 0 && (!labelsUsable || letters.split('').every(l => opts.has(l)));
    if (letters.length > 0 && !labelsUsable) total.labelUnavailable++;

    const domA = (String(q.answerHtml || '').match(/[A-H]/g) || []).join('');
    if (domA && letters && domA !== letters) total.domJsonMismatch++;
    if (letters && (!q.answerHtml || stripTags(q.answerHtml) === '')) {
      if (!goodLabel) { total.labelMismatch++; }
      else { q.answerHtml = `<p>${letters}</p>`; fa++; }
    } else if (letters && !goodLabel) total.labelMismatch++;
    // 判断题等无选项题型：站点把答案放在 correctAnswer.answer（纯文本），按原文保存
    if (!q.answerHtml && !letters) {
      const txt = stripTags(s.correctAnswer?.answer);
      if (txt) { q.answerHtml = `<p>${txt}</p>`; fa++; total.nonChoiceAnswers++; }
    }

    const explText = stripTags(q.explanationHtml);
    if (explText.length < 20) {
      const clean = sanitizeHtml(String(s.solution || ''));
      if (stripTags(clean.html).length >= 20) {
        q.explanationHtml = clean.html;
        if (clean.rejected) doc.conflicts.push({ scope: 'privacy', id: q.id, field: 'explanationHtml', rejectedReferences: clean.rejected });
        fe++;
      }
    }
    if (!q.answerHtml) total.stillMissingAnswer++;
    if (stripTags(q.explanationHtml).length < 20) total.stillMissingExplanation++;
  }
  total.filledAnswers += fa;
  total.filledExplanations += fe;

  doc.evidence = Array.isArray(doc.evidence) ? doc.evidence : [];
  const ev = {
    type: 'answer-explanation-source',
    source: 'fenbi-observed-json',
    endpoint: 'tiku.fenbi.com/combine/static/solution',
    page: 'analysis-after-submit',
    keyedBy: 'globalId',
    observedAt: solAt,
    filledAnswers: fa, filledExplanations: fe,
    note: 'choice is 0-based option index; converted to option letters',
  };
  const prevEv = doc.evidence.findIndex(e => e && e.source === 'fenbi-observed-json');
  if (prevEv >= 0) doc.evidence[prevEv] = ev; else doc.evidence.push(ev);

  // 资产：新增解析图进入待下载队列（下载由后续只读 pass 执行）
  const urls = collectAssetUrls(doc);
  const prev = new Map((doc.assets || []).map(a => [a.url, a]));
  doc.assets = urls.map(u => prev.get(u) || { url: u, status: 'pending' });

  const verdict = await validateDocument(doc, { assetRoot: path.join(PAPERS, d, 'assets') });
  const tmp = docPath + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(doc), { mode: 0o600 });
  await fs.rename(tmp, docPath);
  await fs.writeFile(path.join(PAPERS, d, 'validation.json'), JSON.stringify(verdict, null, 2) + '\n', { mode: 0o600 });
  const pending = doc.assets.filter(a => a.status !== 'downloaded').length;
  console.log(`${d} filledA=${fa} filledE=${fe} pendingAssets=${pending} verdict=${verdict.status}`);
}

console.log(JSON.stringify(total));
