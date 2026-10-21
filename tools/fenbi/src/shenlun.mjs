// 申论采集（schemaVersion 2）→ 规范化文档（schemaVersion 1）的离线解析/转换层。
//
// 只认这三个正文来源：
//   questions[].prompt            题干（其中不含答案；页面的“解析视图”外壳另有分区）
//   questions[].materialsThisQuestion  本题关联的材料 pane（按 htmlSha 指向 materials[]）
//   questions[].referenceAnswer   参考答案
// `otherSections` 只有标题/长度/哈希，没有正文，因此永远不能当作解析或答案。
//
// 页面里“解析视频 / 考点 / 来源”都不是文字解析；只有标题恰为「解析」且存在正文的分区才算。
// 本模块不访问网络、不启动浏览器、不读取登录态，也不写任何正式题库目录。

import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { load } from 'cheerio';
import { createDocument, collectAssetUrls } from './model.mjs';
import { sanitizeHtml } from './privacy.mjs';

export const CAPTURE_SCHEMA_VERSION = 2;
export const AUTHORITATIVE_FIELDS = Object.freeze(['prompt', 'materialsThisQuestion', 'referenceAnswer']);
export const ANSWER_SECTION_TITLE = '参考答案';
export const ANALYSIS_SECTION_TITLE = '解析';
// 粉笔把「解析视频/考点/来源」放在同一张解析视图里，但它们都不是文字解析。
export const NON_ANALYSIS_SECTION_TITLES = Object.freeze(['解析视频', '视频解析', '考点', '来源']);
const isVideoTitle = title => NON_ANALYSIS_SECTION_TITLES.includes(title) && title.includes('视频');

const sha256 = value => createHash('sha256').update(value).digest('hex');
const norm = value => String(value ?? '').replace(/\s+/gu, ' ').trim();
const textOf = html => {
  const $ = load(String(html ?? ''), null, false);
  $('script,style,noscript').remove();
  return norm($.text());
};
const hasImage = html => /<(?:img|image)\b/iu.test(String(html ?? ''));
const positive = value => Number.isInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;

function sanitize(html, sink, scope, id, field) {
  const clean = sanitizeHtml(html);
  if (clean.rejected) sink.push({ scope: 'privacy', id, field, rejectedReferences: clean.rejected });
  return clean.html;
}

/** 解析视图外壳：题干 + 若干 result-common-section。返回题干 HTML 与分区清单（含正文）。 */
export function splitSolutionSections(html) {
  const source = String(html ?? '');
  if (!source.trim()) return { stemHtml: '', sections: [] };
  const $ = load(source, null, false);
  const sections = $('.result-common-section').toArray().map((node) => {
    const section = $(node);
    const title = norm(section.find('.solution-title').first().text());
    const body = section.children('.content').first();
    const bodyHtml = body.length ? body.html() ?? '' : '';
    return { title, bodyHtml, textLen: textOf(bodyHtml).length, htmlSha: sha256(bodyHtml), hasImage: hasImage(bodyHtml) };
  });
  const stem = $.root().clone();
  stem.find('.result-common-section').remove();
  // 旧版页面把分区包在 result-common-container 里；连折叠按钮一起去掉，避免残留空壳。
  stem.find('.result-common-container').remove();
  stem.find('.solution-title-container').remove();
  return { stemHtml: stem.html() ?? '', sections };
}

/** referenceAnswer.html 自带「参考答案」标题节点，只保留正文。 */
export function answerBodyOf(html) {
  const $ = load(String(html ?? ''), null, false);
  const direct = $.root().children('.content').first();
  const body = direct.length ? direct.html() ?? '' : $.root().html() ?? '';
  const out = load(body, null, false);
  out('.solution-title-container,.solution-title').remove();
  return out.root().html() ?? '';
}

/**
 * 把题干里的作答要求独立出来。只在有明确「要求：」段落、或末段本身就是字数要求时拆分，
 * 其余情况整段留在题干，宁可不拆也不猜。正文一字不删。
 */
export function splitRequirements(stemHtml) {
  const $ = load(String(stemHtml ?? ''), null, false);
  const paragraphs = $('p').toArray();
  const text = node => norm($(node).text());
  const labelled = paragraphs.findIndex(node => /^(?:作答)?要求\s*[:：]/u.test(text(node)));
  const isWordLimit = value => /(?:不超过|不少于|至少|至多|字数不限|\d+\s*[-—–~～至到]\s*\d+\s*字|\d+\s*字(?:以内|以下|左右))/u.test(value);
  let cut = labelled;
  if (cut < 0 && paragraphs.length > 1) {
    const last = paragraphs[paragraphs.length - 1];
    if (isWordLimit(text(last))) cut = paragraphs.length - 1;
  }
  // 至少保留一段题干；要求段落若从第一段开始就不拆，宁可不拆也不制造空题干。
  if (cut <= 0) return { contentHtml: stemHtml ?? '', requirementsHtml: '', requirementsSource: 'none' };
  // 只移动“整段尾部都是作答要求”的情况；尾段混入其他正文时不拆，避免把题干切碎。
  // 要求块常见形态：单独一行「要求：」，其后是「（1）…」「1.…」「①②…」或直接的“不超过 N 字”。
  const tail = paragraphs.slice(cut).map(text);
  const requirementLike = value => /^(?:作答)?要求\s*[:：]?/u.test(value) || isWordLimit(value)
    || /^[（(]?\s*\d+\s*[）)]?\s*[.．、]?/u.test(value) || /^[①②③④⑤⑥⑦⑧⑨⑩]/u.test(value)
    || /^[（(]?\s*[一二三四五六七八九十]+\s*[）)]/u.test(value) || /字数/u.test(value);
  if (!tail.every(requirementLike)) return { contentHtml: stemHtml ?? '', requirementsHtml: '', requirementsSource: 'none' };
  const after = $('p').slice(cut).toArray();
  const requirementsHtml = after.map(node => $.html(node)).join('\n');
  for (const node of after) $(node).remove();
  return { contentHtml: $.root().html() ?? '', requirementsHtml, requirementsSource: labelled >= 0 ? 'labelled-paragraph' : 'trailing-word-limit' };
}

/** 从 dom.html 只读观察：标题、材料/题目页签、当前题 key、解析视图分区标题。 */
export function inspectShenlunDom(html) {
  const $ = load(String(html ?? ''), null, false);
  const title = norm($('title').first().text());
  let materialTabs = 0;
  let questionTabs = 0;
  $('.choose-tab').each((_, element) => {
    const text = $(element).text();
    for (const match of text.matchAll(/材料\s*(\d+)/gu)) materialTabs = Math.max(materialTabs, Number(match[1]));
    for (const match of text.matchAll(/(\d+)\s*题/gu)) questionTabs = Math.max(questionTabs, Number(match[1]));
  });
  return {
    title,
    materialTabs: materialTabs || null,
    questionTabs: questionTabs || null,
    activeQuestionKey: $('[data-question-key]').first().attr('data-question-key') ?? null,
    sectionTitles: $('.solution-title').toArray().map(element => norm($(element).text())).filter(Boolean),
  };
}

function anchorNumbers(anchorsVisible) {
  if (!Array.isArray(anchorsVisible)) return null;
  const numbers = anchorsVisible.map(value => {
    const match = /^(\d+)\s*题$/u.exec(norm(value));
    return match ? Number(match[1]) : null;
  });
  return numbers.every(value => value !== null) ? numbers : null;
}

/**
 * 解析单个粉笔申论采集。
 * @returns {{doc: object, diagnostics: object}}
 */
export function parseShenlunCapture({ capture, meta = {}, domHtml = null } = {}) {
  if (!capture || typeof capture !== 'object') throw new Error('capture-required');
  if (capture.schemaVersion !== CAPTURE_SCHEMA_VERSION) throw new Error('unsupported-capture-schema');
  if (capture.subject !== 'shenlun') throw new Error('capture-subject-must-be-shenlun');
  const diagnostics = {
    captureSchemaVersion: capture.schemaVersion,
    storedMaterials: 0,
    materialTabs: null,
    analysis: { textual: 0, imageOnly: 0, videoOnly: 0, absent: 0 },
    materialBodyNotStored: 0,
    sectionTitles: {},
    missingQuestionNumbers: [],
    unresolvedMaterialReferences: [],
    questionKeys: [],
    rightsStatus: meta.rightsStatus ?? null,
    cloudStorageBlocked: meta.cloudStorageBlocked === true || capture.cloudStorageBlocked === true,
    titleSource: 'unknown',
  };
  const identity = capture.identity ?? {};
  const paperId = meta.paperId != null ? String(meta.paperId) : identity.paperId != null ? String(identity.paperId) : identity.sourceId != null ? String(identity.sourceId) : null;
  const sourceId = meta.sourceId != null ? String(meta.sourceId) : identity.sourceId != null ? String(identity.sourceId) : null;
  if (!paperId) throw new Error('paper-identity-missing');
  const dom = domHtml ? inspectShenlunDom(domHtml) : null;
  const title = dom?.title || norm(meta.title);
  diagnostics.titleSource = dom?.title ? 'dom-title' : title ? 'meta-title' : 'unknown';
  diagnostics.materialTabs = dom?.materialTabs ?? null;
  const rawDetailPath = typeof capture.source?.detailPath === 'string' ? capture.source.detailPath : '';
  // 路由里不应带凭据；即使带了也只在路径层保存，查询串/片段一律丢弃。
  const detailPath = rawDetailPath.split('#')[0].split('?')[0];
  const sourceUrl = /^\//u.test(detailPath) ? `https://www.fenbi.com${detailPath}` : `https://www.fenbi.com/`;
  const doc = createDocument({
    id: paperId,
    sourceId,
    title,
    subject: 'shenlun',
    year: positive(identity.year),
    area: norm(identity.area),
    variant: norm(identity.variant),
    questionIdNamespace: 'fenbi-question-key',
  }, {
    url: sourceUrl,
    capturedAt: meta.capturedAt ?? capture.capturedAt ?? null,
  });
  doc.schemaVersion = 1;

  // ---- 身份绑定 ----
  const docPaperId = identity.paperId != null ? String(identity.paperId) : null;
  if (docPaperId && paperId !== docPaperId) {
    doc.conflicts.push({ scope: 'identity', id: paperId, field: 'paperId', kept: paperId, incoming: docPaperId, reason: 'meta-and-document-disagree' });
    doc.evidence.push({ type: 'rejected-paper-mismatch', paperIds: [paperId, docPaperId] });
  } else {
    doc.evidence.push({ type: 'source-paper-identity', paperId, url: sourceUrl });
  }
  doc.evidence.push({ type: 'shenlun-capture-schema', schemaVersion: capture.schemaVersion, authoritativeFields: [...AUTHORITATIVE_FIELDS] });

  // ---- 材料 ----
  const storedHashes = new Map();
  for (const [index, material] of (Array.isArray(capture.materials) ? capture.materials : []).entries()) {
    const html = typeof material?.html === 'string' ? material.html : '';
    const id = `material-${index + 1}`;
    const entry = {
      id,
      number: index + 1,
      index: Number.isInteger(material?.index) ? material.index : index,
      contentHtml: sanitize(html, doc.conflicts, 'materials', id, 'contentHtml'),
      sourceHtmlSha: typeof material?.htmlSha === 'string' ? material.htmlSha : null,
      sourceTextLen: Number.isInteger(material?.textLen) ? material.textLen : null,
      idNamespace: 'capture-material-index',
    };
    if (!html.trim() && entry.sourceHtmlSha) diagnostics.materialBodyNotStored = (diagnostics.materialBodyNotStored ?? 0) + 1;
    doc.materials.push(entry);
    if (entry.sourceHtmlSha) storedHashes.set(entry.sourceHtmlSha, entry.id);
  }
  diagnostics.storedMaterials = doc.materials.length;

  // ---- 题目 ----
  const captureQuestions = Array.isArray(capture.questions) ? capture.questions : [];
  const anchorsSets = new Set(captureQuestions.map(question => JSON.stringify(anchorNumbers(question.anchorsVisible) ?? null)));
  const anchors = captureQuestions.length ? anchorNumbers(captureQuestions[0].anchorsVisible) : null;
  if (anchorsSets.size > 1) doc.conflicts.push({ scope: 'questions', field: 'anchorsVisible', reason: 'questions-disagree-on-visible-anchors', variants: [...anchorsSets].length });
  const anchorsConsistent = Array.isArray(anchors)
    && anchors.length === captureQuestions.length
    && anchors.every((number, index) => number === index + 1);
  const seenKeys = new Set();
  for (const [position, question] of captureQuestions.entries()) {
    const key = question?.questionKey != null ? String(question.questionKey) : '';
    const id = key || `question-${position + 1}`;
    if (key && seenKeys.has(key)) doc.conflicts.push({ scope: 'questions', id, field: 'questionKey', reason: 'duplicate-question-key' });
    if (key) seenKeys.add(key);
    const index = positive(question?.index);
    const number = index ?? (position + 1);
    const { stemHtml, sections } = splitSolutionSections(question?.prompt?.html);
    const analysisSection = sections.find(section => section.title === ANALYSIS_SECTION_TITLE && (section.textLen > 0 || section.hasImage));
    const answerEntries = (Array.isArray(question?.referenceAnswer) ? question.referenceAnswer : [])
      .filter(entry => typeof entry?.html === 'string' && entry.html.trim());
    const embeddedAnswer = sections.find(section => section.title === ANSWER_SECTION_TITLE && (section.textLen > 0 || section.hasImage));
    // 优先用结构化 referenceAnswer；只有当该字段缺失时才回退到同一页面里观察到的「参考答案」分区。
    const answerHtml = answerEntries.length
      ? answerEntries.map(entry => answerBodyOf(entry.html)).filter(html => html.trim()).join('\n')
      : (embeddedAnswer?.bodyHtml ?? '');
    const answerSource = answerEntries.length ? 'referenceAnswer' : embeddedAnswer ? 'embedded-section' : 'absent';
    const answerTitles = answerEntries.length
      ? answerEntries.map(entry => norm(entry.title)).filter(Boolean)
      : embeddedAnswer ? [ANSWER_SECTION_TITLE] : [];
    const requirements = splitRequirements(stemHtml);
    const materialIds = [];
    for (const reference of Array.isArray(question?.materialsThisQuestion) ? question.materialsThisQuestion : []) {
      const hash = typeof reference?.htmlSha === 'string' ? reference.htmlSha : null;
      const resolved = hash ? storedHashes.get(hash) : null;
      if (resolved) {
        if (!materialIds.includes(resolved)) materialIds.push(resolved);
      } else {
        diagnostics.unresolvedMaterialReferences.push({
          questionId: id,
          questionNumber: number,
          htmlSha: hash,
          textLen: Number.isInteger(reference?.textLen) ? reference.textLen : null,
        });
      }
    }
    const hasVideo = sections.some(section => isVideoTitle(section.title));
    const textualAnalysis = analysisSection && analysisSection.textLen > 0;
    if (textualAnalysis) diagnostics.analysis.textual += 1;
    else if (analysisSection) diagnostics.analysis.imageOnly += 1;
    else if (hasVideo) diagnostics.analysis.videoOnly += 1;
    else diagnostics.analysis.absent += 1;
    for (const section of sections) {
      if (section.title) diagnostics.sectionTitles[section.title] = (diagnostics.sectionTitles[section.title] ?? 0) + 1;
    }
    doc.questions.push({
      id,
      number,
      contentHtml: sanitize(requirements.contentHtml, doc.conflicts, 'questions', id, 'contentHtml'),
      options: [],
      materialIds,
      materialIdsObserved: materialIds.length > 0 || (Array.isArray(question?.materialsThisQuestion) && question.materialsThisQuestion.length > 0),
      answerHtml: sanitize(answerHtml, doc.conflicts, 'questions', id, 'answerHtml'),
      answerSource,
      explanationHtml: sanitize(analysisSection?.bodyHtml ?? '', doc.conflicts, 'questions', id, 'explanationHtml'),
      requirementsHtml: sanitize(requirements.requirementsHtml, doc.conflicts, 'questions', id, 'requirementsHtml'),
      answerSectionTitles: answerTitles,
      analysisSectionTitles: sections.map(section => section.title).filter(Boolean),
      analysisStatus: textualAnalysis ? 'textual' : analysisSection ? 'image-only' : hasVideo ? 'video-only' : 'absent',
      requirementsSource: requirements.requirementsSource,
      anchorsVisibleVerified: anchorsConsistent,
    });
    diagnostics.questionKeys.push(key || null);
  }

  // ---- 题位守恒 ----
  const capturedNumbers = new Set(doc.questions.map(question => question.number));
  if (Array.isArray(anchors)) {
    doc.expected.questions = anchors.length;
    doc.expected.questionNumbers = [...anchors];
    diagnostics.missingQuestionNumbers = anchors.filter(number => !capturedNumbers.has(number));
    if (anchorsConsistent) doc.evidence.push({ type: 'question-anchors-verified', numbers: [...anchors] });
    else doc.evidence.push({ type: 'question-anchors-unverified', anchors: [...anchors] });
  } else if (Number.isInteger(dom?.questionTabs) && dom.questionTabs > 0) {
    // 没有 anchors 时，用 DOM 实际渲染的题号页签作为下限；这不是题目声明，但至少不是凭空猜测。
    doc.expected.questions = dom.questionTabs;
    diagnostics.missingQuestionNumbers = Array.from({ length: dom.questionTabs }, (_, index) => index + 1)
      .filter(number => !capturedNumbers.has(number));
    doc.evidence.push({ type: 'source-question-tabs', questionTabs: dom.questionTabs });
  } else {
    doc.evidence.push({ type: 'expected-count-unknown' });
  }
  if (diagnostics.missingQuestionNumbers.length) {
    doc.evidence.push({ type: 'question-slot-missing', numbers: [...diagnostics.missingQuestionNumbers] });
    for (const number of diagnostics.missingQuestionNumbers) doc.conflicts.push({ scope: 'questions', id: null, field: 'number', reason: 'source-slot-missing', number });
  }

  // ---- 材料页签与已存 pane ----
  // 没有 DOM 时无法知道页签总数：保留 unknown，而不是用“已存数量”冒充完整。
  doc.expected.materials = diagnostics.materialTabs ?? null;
  doc.expected.materialIds = doc.materials.map(material => material.id);
  doc.evidence.push({ type: 'shenlun-material-tabs', materialTabs: diagnostics.materialTabs, storedMaterials: doc.materials.length });
  doc.evidence.push({ type: 'shenlun-section-inventory', titles: { ...diagnostics.sectionTitles } });

  // ---- 图片引用（只做引用清单，不下载） ----
  doc.assets = collectAssetUrls(doc).map(url => ({ url, status: 'pending' }));
  doc.shenlun = {
    authoritativeFields: [...AUTHORITATIVE_FIELDS],
    materialTabs: diagnostics.materialTabs,
    storedMaterials: doc.materials.length,
    analysis: { ...diagnostics.analysis },
    sectionTitles: { ...diagnostics.sectionTitles },
    missingQuestionNumbers: [...diagnostics.missingQuestionNumbers],
    unresolvedMaterialReferences: [...diagnostics.unresolvedMaterialReferences],
    rightsStatus: diagnostics.rightsStatus,
    cloudStorageBlocked: diagnostics.cloudStorageBlocked,
    titleSource: diagnostics.titleSource,
    titleHash: identity.titleHash ?? null,
    titleLen: Number.isInteger(identity.titleLen) ? identity.titleLen : null,
    sourceId,
    detailPath: detailPath || null,
  };
  return { doc, diagnostics };
}

/** 读取一个采集目录（document.json / meta.json / dom.html）但不解析。 */
export async function loadShenlunCapture(folder) {
  const base = path.resolve(folder);
  const read = async (name) => {
    try { return await fs.readFile(path.join(base, name), 'utf8'); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  };
  const captureRaw = await read('document.json');
  if (!captureRaw) throw new Error('document.json-missing');
  const capture = JSON.parse(captureRaw);
  const metaRaw = await read('meta.json');
  const meta = metaRaw ? JSON.parse(metaRaw) : {};
  const domHtml = await read('dom.html');
  return { capture, meta, domHtml, base };
}

/** 只有结构校验 complete 且许可状态允许时，才可把正文写进仓库。 */
export function publicationBlockers(doc) {
  const blockers = [];
  if (doc?.shenlun?.cloudStorageBlocked === true) blockers.push('cloud-storage-blocked');
  if (String(doc?.shenlun?.rightsStatus ?? 'unknown') !== 'cleared') blockers.push('rights-not-cleared');
  return blockers;
}

/** metadata-only 回执：不含题干、材料、答案或解析正文。 */
export function metadataReceipt(doc, verdict = null) {
  const questions = Array.isArray(doc?.questions) ? doc.questions : [];
  return {
    sourceId: doc?.shenlun?.sourceId ?? doc?.identity?.sourceId ?? null,
    paperId: doc?.identity?.id ?? null,
    area: doc?.identity?.area ?? null,
    year: doc?.identity?.year ?? null,
    variant: doc?.identity?.variant ?? null,
    subject: doc?.identity?.subject ?? null,
    questionCount: questions.length,
    questionNumbers: questions.map(question => question.number),
    expectedQuestions: doc?.expected?.questions ?? null,
    missingQuestionNumbers: [...(doc?.shenlun?.missingQuestionNumbers ?? [])],
    materialPanesStored: doc?.shenlun?.storedMaterials ?? 0,
    materialTabsDeclared: doc?.shenlun?.materialTabs ?? null,
    unresolvedMaterialReferences: (doc?.shenlun?.unresolvedMaterialReferences ?? []).map(reference => ({
      questionNumber: reference.questionNumber, textLen: reference.textLen, htmlSha: reference.htmlSha,
    })),
    analysis: { ...(doc?.shenlun?.analysis ?? {}) },
    sectionTitles: { ...(doc?.shenlun?.sectionTitles ?? {}) },
    answersPresent: questions.filter(question => String(question.answerHtml ?? '').trim()).length,
    explanationsPresent: questions.filter(question => String(question.explanationHtml ?? '').trim()).length,
    rightsStatus: doc?.shenlun?.rightsStatus ?? null,
    cloudStorageBlocked: doc?.shenlun?.cloudStorageBlocked ?? null,
    validation: verdict ? { status: verdict.status, issueCodes: [...new Set((verdict.issues ?? []).map(issue => issue.code))] } : null,
  };
}

