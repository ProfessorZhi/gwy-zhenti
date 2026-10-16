import { load } from 'cheerio';
import { sanitizeHtml } from './privacy.mjs';

const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj ?? {}, key);
const text = (value) => typeof value === 'string' ? value : value == null ? '' : String(value);
const plain = (value) => load(text(value), null, false).text().replace(/\s+/gu, ' ').trim();
const pathValue = (obj, path) => String(path).split('.').reduce((v, k) => v?.[k], obj);
function pick(obj, canonical, names, map = {}) {
  if (own(map, canonical)) return pathValue(obj, map[canonical]);
  for (const name of names) if (own(obj, name)) return obj[name];
  return undefined;
}
const arrays = (root, paths) => paths.map((path) => pathValue(root, path)).filter(Array.isArray);
const unique = (values) => [...new Set(values)];
const positive = (value) => Number.isInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;

export function createDocument(identity = {}, source = {}) {
  return {
    schemaVersion: 1,
    identity: { id: null, title: '', subject: null, year: null, area: '', variant: '', ...identity },
    source: { url: '', capturedAt: new Date().toISOString(), ...source },
    expected: { questions: null, materials: null, questionNumbers: null, materialIds: null },
    materials: [], questions: [], assets: [], evidence: [], conflicts: [],
  };
}

function merge(doc, old, incoming, scope, id) {
  for (const key of ['contentHtml', 'answerHtml', 'explanationHtml', 'requirementsHtml']) if (typeof incoming[key] === 'string') {
    const clean = sanitizeHtml(incoming[key]); incoming[key] = clean.html;
    if (clean.rejected) doc.conflicts.push({ scope: 'privacy', id, field: key, rejectedReferences: clean.rejected });
  }
  for (const [field, value] of Object.entries(incoming)) {
    if (value == null || value === '' || (Array.isArray(value) && !value.length)) continue;
    if (old[field] == null || old[field] === '' || (Array.isArray(old[field]) && !old[field].length)) {
      old[field] = value;
      continue;
    }
    if (JSON.stringify(old[field]) === JSON.stringify(value)) continue;
    if (field === 'materialIds') {
      old[field] = unique([...old[field], ...value]);
      continue;
    }
    // Keep the first full version on disagreement. Never silently replace it.
    const conflict = { scope, id, field, kept: old[field], incoming: value };
    if (!doc.conflicts.some((item) => JSON.stringify(item) === JSON.stringify(conflict))) doc.conflicts.push(conflict);
  }
}

function upsert(doc, collection, item) {
  const protect = (entry, key) => {
    const clean = sanitizeHtml(entry[key]);
    entry[key] = clean.html;
    if (clean.rejected) doc.conflicts.push({ scope: 'privacy', id: item.id, field: key, rejectedReferences: clean.rejected });
  };
  for (const key of ['contentHtml', 'answerHtml', 'explanationHtml', 'requirementsHtml']) if (typeof item[key] === 'string') protect(item, key);
  for (const option of item.options || []) protect(option, 'contentHtml');
  const existing = item.id ? doc[collection].find((entry) => entry.id === item.id) : null;
  if (existing) merge(doc, existing, item, collection, item.id);
  else doc[collection].push(item);
}

function optionsOf(q, map) {
  const opts = pick(q, 'options', ['options', 'choices'], map);
  if (!Array.isArray(opts)) return [];
  const configuredLabels = Array.isArray(map.optionLabels) && map.optionLabels.length === opts.length
    && map.optionLabels.every((label) => typeof label === 'string' && /^[A-Z]$/u.test(label))
    && new Set(map.optionLabels).size === opts.length ? map.optionLabels : null;
  return opts.map((option, index) => typeof option === 'string'
    ? { label: configuredLabels?.[index] ?? '', contentHtml: option }
    : { label: text(pick(option, 'optionLabel', ['label', 'key'], map)),
      contentHtml: text(pick(option, 'optionContentHtml', ['contentHtml', 'content', 'text'], map)) });
}

function answerOf(q, opts, map, payload) {
  const answer = pick(q, 'answerHtml', ['answerHtml', 'answer', 'correctAnswer'], map);
  const encoding = q.answerEncoding ?? payload.answerEncoding ?? map.answerEncoding;
  if (typeof answer === 'number' && Number.isInteger(answer)) {
    const offset = encoding === 'zero-based-index' ? 0 : encoding === 'one-based-index' ? 1 : null;
    if (offset !== null && opts[answer - offset]?.label) return opts[answer - offset].label;
  }
  return sanitizeHtml(Array.isArray(answer) ? answer.map(text).join(',') : text(answer)).html;
}

/** Conservative adapters for explicit envelopes only; no recursive object guessing. */
export function absorbPayload(doc, payload, { url = '', subject, fieldMap = {} } = {}) {
  if (!payload || typeof payload !== 'object') return doc;
  if (subject && !doc.identity.subject) doc.identity.subject = subject;
  const roots = [payload, payload.data, payload.exercise, payload.data?.exercise].filter((v) => v && typeof v === 'object' && !Array.isArray(v));
  const sourcePaperIds = unique(roots.flatMap((root) => [root.paperId, root.paper?.id]).filter((id) => id != null).map(text));
  if (doc.identity.id != null && sourcePaperIds.some((id) => id !== text(doc.identity.id))) {
    doc.conflicts.push({ scope: 'identity', id: text(doc.identity.id), field: 'paperId', kept: text(doc.identity.id), incoming: sourcePaperIds });
    doc.evidence.push({ type: 'rejected-paper-mismatch', url, paperIds: sourcePaperIds });
    return doc;
  }
  for (const paperId of sourcePaperIds) if (paperId === text(doc.identity.id)
    && !doc.evidence.some((item) => item.type === 'source-paper-identity' && item.paperId === paperId && item.url === url)) {
    doc.evidence.push({ type: 'source-paper-identity', paperId, url });
  }
  for (const root of roots) if (Array.isArray(root.questionIds)) doc.evidence.push({ type: 'source-question-id-order', url, questionIds: root.questionIds.map(text), numberingVerified: false });
  const qArrays = arrays(payload, fieldMap.questions ? [fieldMap.questions] : ['questions', 'data.questions', 'exercise.questions', 'data.exercise.questions']);
  const mArrays = arrays(payload, fieldMap.materials ? [fieldMap.materials] : ['materials', 'accessories', 'data.materials', 'data.accessories', 'exercise.materials', 'exercise.accessories', 'data.exercise.materials', 'data.exercise.accessories']);
  const aArrays = arrays(payload, fieldMap.answers ? [fieldMap.answers] : ['answers', 'data.answers', 'exercise.answers', 'data.exercise.answers']);
  const before = { questions: doc.questions.length, materials: doc.materials.length };
  for (const root of roots) {
    const count = pick(root, 'questionCount', ['questionCount', 'totalQuestions'], fieldMap);
    const materialCount = pick(root, 'materialCount', ['materialCount'], fieldMap);
    if (positive(count)) merge(doc, doc.expected, { questions: positive(count) }, 'expected', null);
    if (Number.isInteger(materialCount) && materialCount >= 0) merge(doc, doc.expected, { materials: materialCount }, 'expected', null);
    if (Array.isArray(root.questionNumbers)) merge(doc, doc.expected, { questionNumbers: root.questionNumbers }, 'expected', null);
    if (Array.isArray(root.materialIds)) merge(doc, doc.expected, { materialIds: root.materialIds.map(text) }, 'expected', null);
  }
  const addMaterial = (item) => {
    if (!item || typeof item !== 'object') return;
    upsert(doc, 'materials', { id: text(pick(item, 'materialId', ['id', 'materialId', 'accessoryId'], fieldMap)),
      contentHtml: text(pick(item, 'materialContentHtml', ['contentHtml', 'content', 'text'], fieldMap)) });
  };
  for (const entries of mArrays) for (const material of entries) addMaterial(material);
  for (const entries of qArrays) for (const q of entries) {
    if (!q || typeof q !== 'object') continue;
    const opts = optionsOf(q, fieldMap);
    const refs = pick(q, 'materialIds', ['materialIds', 'accessoryIds'], fieldMap);
    const embedded = Array.isArray(q.materials) ? q.materials : Array.isArray(q.accessories) ? q.accessories : [];
    const materialIds = Array.isArray(refs) ? refs.map(text) : [];
    for (const material of embedded) {
      if (typeof material === 'object' && material !== null) {
        addMaterial(material);
        const id = pick(material, 'materialId', ['id', 'materialId', 'accessoryId'], fieldMap);
        if (id != null) materialIds.push(text(id));
      } else if (material != null) materialIds.push(text(material));
    }
    const rawNumber = pick(q, 'number', ['number', 'questionNumber', 'questionNo'], fieldMap);
    const questionId = text(pick(q, 'questionId', ['id', 'questionId', 'qid'], fieldMap));
    const mappedNumber = questionId && own(fieldMap.questionNumbersById, questionId)
      ? positive(fieldMap.questionNumbersById[questionId]) : null;
    const sourceNumber = positive(rawNumber);
    if (sourceNumber !== null && mappedNumber !== null && sourceNumber !== mappedNumber) {
      doc.conflicts.push({ scope: 'questions', id: questionId, field: 'number', kept: sourceNumber,
        incoming: mappedNumber, reason: 'explicit-number-map-disagrees-with-source' });
    }
    const item = {
      id: questionId,
      number: sourceNumber ?? (rawNumber == null || rawNumber === '' ? mappedNumber : null),
      contentHtml: text(pick(q, 'contentHtml', ['contentHtml', 'content', 'stem'], fieldMap)),
      options: opts, materialIds: unique(materialIds), answerHtml: answerOf(q, opts, fieldMap, payload),
      explanationHtml: text(pick(q, 'explanationHtml', ['explanationHtml', 'explanation', 'analysis'], fieldMap)),
      requirementsHtml: text(pick(q, 'requirementsHtml', ['requirementsHtml', 'requirements'], fieldMap)),
    };
    upsert(doc, 'questions', item);
  }
  for (const entries of aArrays) for (const answer of entries) {
    if (!answer || typeof answer !== 'object') continue;
    const id = text(pick(answer, 'questionId', ['questionId', 'qid', 'id'], fieldMap));
    const target = id && doc.questions.find((q) => q.id === id);
    if (!target) {
      const rawAnswer = pick(answer, 'answerHtml', ['answerHtml', 'answer', 'correctAnswer'], fieldMap);
      const pending = { type: 'unmatched-answer', questionId: id, url,
        answerHtml: answerOf(answer, [], fieldMap, payload),
        explanationHtml: sanitizeHtml(text(pick(answer, 'explanationHtml', ['explanationHtml', 'explanation', 'analysis'], fieldMap))).html,
        answerEncoding: answer.answerEncoding ?? payload.answerEncoding ?? fieldMap.answerEncoding ?? null,
        numericAnswer: typeof rawAnswer === 'number' && Number.isInteger(rawAnswer) ? rawAnswer : null };
      if (!doc.evidence.some((item) => JSON.stringify(item) === JSON.stringify(pending))) doc.evidence.push(pending);
      continue;
    }
    merge(doc, target, {
      answerHtml: answerOf(answer, target.options, fieldMap, payload),
      explanationHtml: text(pick(answer, 'explanationHtml', ['explanationHtml', 'explanation', 'analysis'], fieldMap)),
    }, 'questions', id);
  }
  // API responses may arrive in either order. Keep only whitelisted answer fields,
  // then join them once the source question ID is observed.
  doc.evidence = doc.evidence.filter((item) => {
    if (item.type !== 'unmatched-answer') return true;
    const target = item.questionId && doc.questions.find((q) => q.id === item.questionId);
    if (!target) return true;
    const answerHtml = item.numericAnswer !== null && item.numericAnswer !== undefined
      ? answerOf({ answer: item.numericAnswer, answerEncoding: item.answerEncoding }, target.options, {}, {})
      : item.answerHtml;
    merge(doc, target, { answerHtml, explanationHtml: item.explanationHtml }, 'questions', target.id);
    return false;
  });
  if (qArrays.length || mArrays.length || aArrays.length) doc.evidence.push({ type: 'payload', url,
    extractedQuestions: doc.questions.length - before.questions, extractedMaterials: doc.materials.length - before.materials });
  return doc;
}

export function extractCatalog(payload, { subject = null, labelId = null } = {}) {
  const papers = [], labels = [];
  for (const entries of arrays(payload, ['papers', 'paperList', 'data.papers', 'data.paperList'])) for (const item of entries) {
    if (!item || item.id == null || !(item.title || item.name)) continue;
    const title = text(item.title || item.name);
    const year = positive(item.year) ?? (title.match(/(?:19|20)\d{2}/u)?.[0] ? Number(title.match(/(?:19|20)\d{2}/u)[0]) : null);
    const paper = { id: text(item.id), title, subject: item.subject ?? subject, labelId: item.labelId ?? labelId,
      questionCount: positive(item.questionCount ?? item.totalQuestions), year };
    if (!papers.some((p) => p.id === paper.id && p.subject === paper.subject)) papers.push(paper);
  }
  for (const entries of arrays(payload, ['labels', 'subLabels', 'data.labels', 'data.subLabels'])) for (const item of entries) {
    if (!item || item.id == null || !(item.title || item.name)) continue;
    const label = { id: text(item.id), title: text(item.title || item.name), subject: item.subject ?? subject, parentId: item.parentId ?? labelId };
    if (!labels.some((l) => l.id === label.id)) labels.push(label);
  }
  return { papers, labels };
}

export function collectAssetUrls(doc) {
  const found = new Set();
  const scan = (html) => {
    const $ = load(text(html), null, false);
    $('img, source, image').each((_, element) => {
      for (const attribute of ['src', 'data-src', 'href', 'xlink:href']) {
        const value = $(element).attr(attribute);
        if (!value) continue;
        try { const parsed = new URL(value, doc.source.url); if (['https:', 'http:'].includes(parsed.protocol)) found.add(parsed.href); } catch { /* Invalid references are rejected by validation. */ }
      }
      const srcset = $(element).attr('srcset');
      if (srcset) for (const entry of srcset.split(',')) {
        try { const parsed = new URL(entry.trim().split(/\s+/u)[0], doc.source.url); if (['https:', 'http:'].includes(parsed.protocol)) found.add(parsed.href); } catch { /* Reported during validation. */ }
      }
    });
  };
  for (const material of doc.materials) scan(material.contentHtml);
  for (const chapter of Array.isArray(doc.chapters) ? doc.chapters : []) scan(chapter.instructionsHtml);
  for (const q of doc.questions) {
    for (const key of ['contentHtml', 'answerHtml', 'explanationHtml', 'requirementsHtml']) scan(q[key]);
    for (const option of Array.isArray(q.options) ? q.options : []) scan(option.contentHtml);
  }
  return [...found];
}

export { plain as htmlText };
