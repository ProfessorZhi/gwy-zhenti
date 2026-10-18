import { load } from 'cheerio';
import { createHash } from 'node:crypto';
import { createDocument, collectAssetUrls } from './model.mjs';
import { sanitizeHtml } from './privacy.mjs';

/** Verified 2026 Fenbi web Xingce markup. No answer is inferred from option selection or CSS. */
export function parseFenbiExamDom(html, identity, source = {}) {
  if (identity.subject !== 'xingce') throw new Error('This observed DOM adapter supports Xingce only');
  const sanitized = sanitizeHtml(html);
  const dom = load(sanitized.html, null, false);
  const document = createDocument({ ...identity, questionIdNamespace: 'fenbi-question-key' }, source);
  if (sanitized.rejected) document.conflicts.push({ scope: 'privacy', rejectedReferences: sanitized.rejected });
  document.chapters = dom('.chapter-container').toArray().map(element => {
    const text = dom(element).text().normalize('NFKC').trim();
    const match = text.match(/^(.*?)\((\d+)题\)/u);
    return { title: match?.[1]?.trim() || '', questionCount: match ? Number(match[2]) : null, instructionsHtml: dom(element).html() || '' };
  });
  if (document.chapters.length && document.chapters.every(chapter => Number.isInteger(chapter.questionCount) && chapter.questionCount > 0)) {
    document.expected.questions = document.chapters.reduce((sum, chapter) => sum + chapter.questionCount, 0);
    document.evidence.push({ type: 'source-chapter-declared-counts', counts: document.chapters.map(chapter => chapter.questionCount) });
  }
  const groups = new Map();
  dom('.resizable-container').each((_, element) => {
    const body = dom(element).find('.materials-container .material-body').first();
    const contents = body.find('.material-content').filter((_, item) => !dom(item).parentsUntil(body).filter('.material-content').length);
    if (!contents.length) return;
    const contentHtml = contents.toArray().map(item => dom.html(item)).join('\n');
    const id = `dom-material-${createHash('sha256').update(contentHtml).digest('hex').slice(0, 16)}`;
    if (!document.materials.some(material => material.id === id)) document.materials.push({ id, contentHtml, idNamespace: 'dom-content-hash' });
    groups.set(element, id);
  });
  // Explicit source chapter counters establish the expected question total; observed nodes do not.
  document.expected.materials = dom('.materials-container').length;
  document.evidence.push({ type: 'source-rendered-material-headings', count: document.expected.materials });
  const questionKeys = new Set();
  dom('app-ti[data-question-key]').each((_, element) => {
    const node = dom(element), heading = node.find('.title-index').filter((_, child) => dom(child).closest('app-ti')[0] === element).first();
    const numberMatch = heading.text().trim().match(/^(\d+)\s*[.．]$/u);
    if (!numberMatch) { document.conflicts.push({ scope: 'dom', field: 'unrecognized-question-number' }); return; }
    const number = Number(numberMatch[1]), id = node.attr('data-question-key');
    if (questionKeys.has(id)) { document.conflicts.push({ scope: 'dom', field: 'duplicate-question-key', id }); return; }
    questionKeys.add(id);
    const choice = node.find('.question-choice-container').filter((_, child) => dom(child).closest('app-ti')[0] === element).first().clone();
    choice.find('app-choice-radio,app-choice-checkbox').remove();
    const options = node.find('.choice-radio-label,.choice-checkbox-label').filter((_, child) => dom(child).closest('app-ti')[0] === element).toArray().map(option => {
      const original = dom(option), label = original.find('.input-radio,.input-checkbox').first().text().trim();
      const copy = original.clone(); copy.find('.input-radio,.input-checkbox,input').remove();
      return { label: /^[A-Z]$/u.test(label) ? label : '', contentHtml: copy.html() || '' };
    });
    const group = node.closest('.resizable-container')[0], materialId = groups.get(group);
    document.questions.push({ id, number, contentHtml: choice.html() || '', options,
      materialIds: materialId ? [materialId] : [],
      materialIdsObserved: Boolean(materialId || node.closest('.questions-single-container').length),
      answerHtml: '', explanationHtml: '', requirementsHtml: '' });
  });
  if (dom('.materials-container').length !== groups.size) document.conflicts.push({ scope: 'dom', field: 'unparsed-material-container' });
  if (document.expected.questions === null) document.evidence.push({ type: 'expected-count-unknown' });
  document.evidence.push({ type: 'dom-question-keys', namespace: 'fenbi-question-key', count: questionKeys.size });
  document.assets = collectAssetUrls(document).map(url => ({ url, status: 'pending' }));
  return document;
}
