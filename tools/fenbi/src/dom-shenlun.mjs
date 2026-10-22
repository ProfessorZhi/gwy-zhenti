import { load } from 'cheerio';
import { createHash } from 'node:crypto';
import { createDocument, collectAssetUrls } from './model.mjs';
import { sanitizeHtml } from './privacy.mjs';

// 粉笔申论详情页（只读，2026 观察）：
//   左栏 .material-body > .material-content ×N 给定材料，切题时不变；
//   右栏 .ti-content > article.content 题面（第一个 <p> 起是题干，到「要求」段止是作答要求），
//   同一容器内 .result-common-section ×N 依次是「解析视频 / 参考答案 / 考点 / 来源」。
// 页面一次只渲染一题，多题靠在 .questions-anchors 上点「N题」切换；因此适配器以"单题视图"为单位，
// 由 buildShenlunDocument 合并成框架标准 document（schemaVersion 1）。
// 解析视频是会员推广位：只有 poster 图和 play-icon，没有 href、没有视频源地址，按源站缺失记录。

const ANSWER_TITLE = /参考(?:答案|作答|范文|解析)|范文/u;
const VIDEO_TITLE = /解析视频|视频/u;
// 早年卷的解析分节标题就叫「解析」，近年卷拆成「考点」「来源」；两者都要认。
const ANALYSIS_TITLE = /解析|点评|评析|分析/u;
const KEYPOINT_TITLE = /考点|知识点/u;
const SOURCE_TITLE = /来源/u;
// 粉笔把「答案正文」和「答案分析」放在同一个「参考答案」分节里：前者到「参考答案说明」/
// 「文章分析」或方括号批注为止，后者是逐段的思路与优点讲评。按段切开，答案与解析各归各位，
// 否则批注字数会算进答案，导致答案看上去超出题目字数要求。
const ANALYSIS_START = /^(?:参考答案说明|参考解析说明|范文分析|文章分析|答案分析)/u;
// 有的卷把分节标题写进正文第一段（<p align="center"><b>参考答案一</b></p>），有的放在 app-solution-title。
// 短标题段不是答案内容，留着会和正文连读、虚增字数，必须剔除。
const TITLE_ONLY = /^(?:参考(?:答案|作答|范文)|范文)[一二三四五六七八九十\d]{0,3}$/u;

const sha = value => createHash('sha256').update(String(value ?? '')).digest('hex').slice(0, 16);
const visible = html => load(String(html ?? ''), null, false).text().replace(/\s+/gu, ' ').trim();
const plain = html => load(String(html ?? ''), null, false).text().replace(/\s+/gu, '').trim();

// 页面标题锚点（「1题」「2题」）给出的题数；没有锚点时退回单题。
export function shenlunAnchorNumbers(html) {
  const $ = load(String(html ?? ''), null, false);
  const numbers = new Set();
  $('.questions-anchors *').each((_, element) => {
    const match = visible($(element).text()).match(/^(\d+)\s*题$/u);
    if (match) numbers.add(Number(match[1]));
  });
  return [...numbers].sort((a, b) => a - b);
}

// 解析一个题目视图。materialHtml 是左栏快照（可缺省），html 是 .ti-content 所在容器快照。
export function parseShenlunView(html, { questionKey = null, number = null, materialHtml = null } = {}) {
  const sanitized = sanitizeHtml(html);
  const conflicts = [];
  if (sanitized.rejected) conflicts.push({ scope: 'privacy', rejectedReferences: sanitized.rejected });
  const $ = load(sanitized.html, null, false);

  // ---- 给定材料：同一层 .material-content 是并列的几则材料，嵌套的属于上一则 ----
  const materialSource = load(sanitizeHtml(materialHtml ?? html).html, null, false);
  const materials = [];
  for (const body of materialSource('.material-body').toArray()) {
    const node = materialSource(body);
    const blocks = node.find('.material-content').filter((_, item) =>
      !materialSource(item).parentsUntil(node).filter('.material-content').length);
    for (const block of (blocks.length ? blocks : node).toArray()) {
      const contentHtml = materialSource.html(block) || '';
      if (!plain(contentHtml)) continue;
      const id = `material-${sha(contentHtml)}`;
      if (!materials.some(material => material.id === id)) materials.push({ id, contentHtml });
    }
  }

  // ---- 题面：article.content 的 <p> 序列，从第一个「要求」段起是作答要求 ----
  const article = $('.ti-content article.content').first();
  const paragraphs = (article.length ? article : $('article.content').first()).find('p').toArray();
  const splitAt = paragraphs.findIndex(paragraph => /^要求/u.test(visible($.html(paragraph))));
  const pick = list => list.map(paragraph => $.html(paragraph)).join('');
  const contentHtml = pick(splitAt >= 0 ? paragraphs.slice(0, splitAt) : paragraphs);
  const requirementsHtml = splitAt >= 0 ? pick(paragraphs.slice(splitAt)) : '';
  // 早年卷的题面把作答指示写在题干括号里（如「（根据资料一、二作答）（10分）」），没有独立「要求」段。
  // 这是源站形态而非冲突，记成证据供人工核对，不阻断整卷。
  const requirementsAbsent = splitAt < 0 && paragraphs.length > 0;

  // ---- 解析分节：按标题分流，正文取 .result-common-container 里的 .content（不含标题）----
  const sections = [];
  $('.result-common-section').each((_, element) => {
    const node = $(element);
    const title = visible(node.find('.solution-title').first().text());
    const body = node.find('.result-common-container .content').first();
    const container = body.length ? body : node.find('.result-common-container').first();
    const scope = container.length ? container : node;
    sections.push({ title, scope, html: scope.first().toString(), textLen: plain(scope.first().toString()).length });
  });
  const answers = sections.filter(section => ANSWER_TITLE.test(section.title) && !VIDEO_TITLE.test(section.title));
  const analyses = sections.filter(section => ANALYSIS_TITLE.test(section.title) && !VIDEO_TITLE.test(section.title)
    && !ANSWER_TITLE.test(section.title) && !KEYPOINT_TITLE.test(section.title) && !SOURCE_TITLE.test(section.title));
  const keypoints = sections.filter(section => KEYPOINT_TITLE.test(section.title));
  const sources = sections.filter(section => SOURCE_TITLE.test(section.title));
  const videos = sections.filter(section => VIDEO_TITLE.test(section.title));

  // 答案正文与答案分析同节：按段切开，分析并入解析。
  const answerHtml = [], answerAnalysis = [];
  for (const section of answers) {
    const paragraphs = section.scope.find('p').toArray();
    if (!paragraphs.length) { answerHtml.push(section.html); continue; }
    const cut = paragraphs.findIndex(paragraph => {
      const line = visible($.html(paragraph));
      return ANALYSIS_START.test(line) || line.startsWith('【');
    });
    const body = cut < 0 ? paragraphs : paragraphs.slice(0, cut);
    const rest = cut < 0 ? [] : paragraphs.slice(cut);
    const kept = body.filter(paragraph => !(visible($.html(paragraph)).length <= 14
      && TITLE_ONLY.test(visible($.html(paragraph)))));
    answerHtml.push((kept.length ? kept : body).map(paragraph => $.html(paragraph)).join(''));
    if (rest.length) answerAnalysis.push({ title: `${section.title}（分析）`, html: rest.map(paragraph => $.html(paragraph)).join('') });
  }

  // 解析按可靠程度排列：真实「解析/点评」分节 → 答案自带的分段讲评 → 考点/来源标签；
  // 近年卷没有文字解析时只剩后者，视频栏是会员推广位，一并如实说明。不补写、不推测任何内容。
  const explanation = [];
  for (const section of analyses) explanation.push(section.html);
  for (const section of answerAnalysis) explanation.push(section.html);
  for (const section of keypoints) explanation.push(`<p><strong>${section.title}</strong>：${visible(section.html)}</p>`);
  for (const section of sources) explanation.push(`<p><strong>${section.title}</strong>：${visible(section.html)}</p>`);
  if (videos.length) explanation.push('<p>粉笔申论页面对本题只提供「解析视频」入口，该入口是会员推广位，页面无视频地址与文字解析。</p>');
  if (!answers.length) conflicts.push({ scope: 'dom', field: 'reference-answer-missing' });
  const hasTextualAnalysis = analyses.length > 0 || answerAnalysis.length > 0;
  if (!hasTextualAnalysis && !keypoints.length && !sources.length) conflicts.push({ scope: 'dom', field: 'analysis-sections-missing' });

  return {
    questionKey, number,
    contentHtml, requirementsHtml,
    answerHtml: answerHtml.join('\n'),
    explanationHtml: explanation.join('\n'),
    materials,
    sections: sections.map(section => ({ title: section.title, textLen: section.textLen })),
    absent: {
      analysisText: hasTextualAnalysis ? 'present (textual 解析/点评 section)' : 'source-absent (no textual 解析/点评 section rendered)',
      analysisVideo: videos.length ? 'label-present-without-address' : 'source-absent',
      requirementsSection: requirementsAbsent ? 'source-absent (directions are inline in the stem)' : 'present',
    },
    requirementsAbsent,
    conflicts,
  };
}

// 把多个题目视图合并成框架标准 document。identity 由调用方给出（含 id/title/subject/year/area/variant）。
export function buildShenlunDocument(views, identity, source = {}) {
  const doc = createDocument({ ...identity, questionIdNamespace: 'fenbi-question-key' }, source);
  const byKey = new Map();
  for (const view of views) {
    if (view.number == null || !Number.isInteger(view.number)) {
      doc.conflicts.push({ scope: 'dom', field: 'unrecognized-question-number' });
      continue;
    }
    if (!view.questionKey || byKey.has(view.questionKey)) {
      doc.conflicts.push({ scope: 'dom', field: 'duplicate-question-key', id: view.questionKey || null });
      continue;
    }
    byKey.set(view.questionKey, true);
    for (const material of view.materials) {
      if (!doc.materials.some(item => item.id === material.id)) doc.materials.push({ ...material, idNamespace: 'dom-content-hash' });
    }
    const materialIds = [...new Set(view.materials.map(material => material.id))];
    doc.questions.push({
      id: view.questionKey, number: view.number,
      contentHtml: view.contentHtml, options: [], materialIds,
      materialIdsObserved: materialIds.length > 0,
      answerHtml: view.answerHtml, explanationHtml: view.explanationHtml, requirementsHtml: view.requirementsHtml,
    });
    doc.conflicts.push(...view.conflicts);
    doc.evidence.push({ type: 'shenlun-sections', questionId: view.questionKey, sections: view.sections, absent: view.absent });
    if (view.requirementsAbsent) doc.evidence.push({ type: 'shenlun-requirements-absent', questionId: view.questionKey,
      reason: 'the source stem carries its directions inline; no standalone 要求 section is rendered' });
  }
  doc.questions.sort((a, b) => a.number - b.number);
  doc.expected.questions = doc.questions.length;
  doc.expected.materials = doc.materials.length;
  doc.expected.questionNumbers = doc.questions.map(question => question.number);
  doc.evidence.push({ type: 'dom-question-keys', namespace: 'fenbi-question-key', count: byKey.size });
  doc.evidence.push({ type: 'answer-explanation-source', source: 'fenbi-shenlun-detail-dom',
    page: 'read-only detail view (no exercise created, no submission)', observedAt: new Date().toISOString() });
  doc.assets = collectAssetUrls(doc).map(url => ({ url, status: 'pending' }));
  return doc;
}
