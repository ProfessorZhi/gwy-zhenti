import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import {
  splitSolutionSections, splitRequirements, inspectShenlunDom, parseShenlunCapture,
  loadShenlunCapture, metadataReceipt, publicationBlockers,
} from '../src/shenlun.mjs';
import { validateDocument } from '../src/validate.mjs';
import { renderCandidate } from '../src/render.mjs';

// 本文件全部使用合成文本；不含任何真实粉笔题目、材料、答案或图片字节。
const sha = value => createHash('sha256').update(value).digest('hex');
const STEM = '合成题干：请依据合成材料归纳要点。';
const REQUIREMENTS = '要求：不超过300字。';
const ANSWER = '合成参考答案正文，仅用于离线结构测试，包含足够长度以通过完整性检查。';
const ANALYSIS = '合成文字解析正文，说明本题的作答思路与结构。';
const MATERIAL = '<div><p>合成材料一：这是完全虚构的材料正文，用于验证材料 pane 的哈希关联。</p></div>';
const VIDEO = '合成视频解析占位说明，不是文字解析。';
const SOURCE_NOTE = '合成来源说明，不是解析。';
const EMBEDDED_ANSWER = 'EMBEDDED_COPY_MUST_NOT_BE_USED';

function section(title, body) {
  return `<section class="result-common-section"><app-solution-title><div class="solution-title-container">`
    + `<div class="solution-title">${title}</div></div></app-solution-title>`
    + `<div class="content"><app-format-html>${body}</app-format-html></div></section>`;
}

function promptHtml({ stem = STEM, requirements = REQUIREMENTS, analysis = ANALYSIS, video = false, embeddedAnswer = EMBEDDED_ANSWER, source = SOURCE_NOTE } = {}) {
  const sections = [];
  if (video) sections.push(section('解析视频', `<p>${VIDEO}</p>`));
  sections.push(section('参考答案', `<p>${embeddedAnswer}</p>`));
  if (analysis) sections.push(section('解析', `<p>${analysis}</p>`));
  if (source) sections.push(section('来源', `<p>${source}</p>`));
  const stemBlock = [stem, requirements].filter(Boolean).map(value => `<p>${value}</p>`).join('');
  return `<app-solution-smart><div class="stem-area">${stemBlock}</div>`
    + `<app-result-common><div class="result-common-container">${sections.join('')}</div></app-result-common></app-solution-smart>`;
}

function answerHtml(body = ANSWER) {
  return `<app-solution-title><div class="solution-title-container"><div class="solution-title">参考答案</div></div></app-solution-title>`
    + `<div class="content"><app-format-html><p>${body}</p></app-format-html></div>`;
}

function question({ index, key, materialHash, prompt = {}, total = 1 }) {
  return {
    index,
    questionKey: key,
    anchorsVisible: Array.from({ length: total }, (_, position) => `${position + 1}题`),
    prompt: { html: promptHtml(prompt), textLen: 100, wordLimitVisible: true, marks: ['20分'] },
    materialsThisQuestion: materialHash ? [{ textLen: 30, htmlSha: materialHash, images: [] }] : [],
    referenceAnswer: [{ title: '参考答案', html: answerHtml() }],
    otherSections: [],
  };
}

function domHtml(title = '合成申论卷', tabs = 1) {
  const materialTabs = Array.from({ length: tabs }, (_, i) => `材料${i + 1}`).join('  ');
  return `<!doctype html><html><head><title>${title}</title></head><body>`
    + `<div class="choose-tab">${materialTabs}</div><div class="choose-tab">1题  2题  3题</div>`
    + `<app-ti data-question-key="3_2_synthetic"></app-ti></body></html>`;
}

function capture({ questions, materials = [{ index: 0, textLen: 30, htmlSha: sha(MATERIAL), html: MATERIAL }], identity = {}, meta = {}, total = questions.length } = {}) {
  for (const item of questions) item.anchorsVisible = Array.from({ length: total }, (_, position) => `${position + 1}题`);
  return {
    capture: {
      schemaVersion: 2,
      subject: 'shenlun',
      cloudStorageBlocked: true,
      identity: { sourceId: 'synthetic-1001', paperId: 'synthetic-1001', area: '浙江', year: 2025, variant: 'A类', titleHash: 'synthetichash', titleLen: 12, ...identity },
      source: { entryKind: 'synthetic', detailPath: '/ti/view/paper/3_2_synthetic', listPage: 1 },
      capturedAt: '2026-10-20T00:00:00.000Z',
      materials,
      questions,
    },
    meta: { sourceId: 'synthetic-1001', paperId: 'synthetic-1001', area: '浙江', year: 2025, variant: 'A类', capturedAt: '2026-10-20T00:00:00.000Z', rightsStatus: 'unverified', cloudStorageBlocked: true, ...meta },
    domHtml: domHtml(),
  };
}

const codes = result => new Set(result.issues.map(issue => issue.code));

test('section split keeps stem, answer and analysis separate and never uses the embedded answer copy', () => {
  const { doc, diagnostics } = parseShenlunCapture(capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] }));
  const q = doc.questions[0];
  assert.match(q.contentHtml, /合成题干/u);
  assert.doesNotMatch(q.contentHtml, /EMBEDDED_COPY_MUST_NOT_BE_USED|合成参考答案正文/u);
  assert.match(q.answerHtml, /合成参考答案正文/u);
  assert.doesNotMatch(q.answerHtml, /EMBEDDED_COPY_MUST_NOT_BE_USED/u);
  assert.match(q.explanationHtml, /合成文字解析正文/u);
  assert.doesNotMatch(q.explanationHtml, /合成来源说明|合成视频解析/u);
  assert.equal(q.analysisStatus, 'textual');
  assert.equal(diagnostics.analysis.textual, 1);
  assert.equal(diagnostics.sectionTitles['参考答案'], 1);
  assert.equal(diagnostics.sectionTitles['解析'], 1);
});

test('video/考点/来源 are never counted as explanations', async () => {
  const { doc } = parseShenlunCapture(capture({
    questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL), prompt: { analysis: null, video: true } })],
  }));
  const q = doc.questions[0];
  assert.equal(q.analysisStatus, 'video-only');
  assert.equal(q.explanationHtml.trim(), '');
  assert.doesNotMatch(JSON.stringify(doc.questions), /合成视频解析占位说明/u);
  const verdict = await validateDocument(doc);
  assert.ok(codes(verdict).has('explanation-empty'));
  assert.equal(verdict.dimensions.explanations.status, 'partial');
});

test('material reference resolves by htmlSha; an unstored pane is named, never silently dropped', async () => {
  const questions = [
    question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) }),
    question({ index: 2, key: 'k2', materialHash: 'f'.repeat(64) }),
  ];
  const { doc, diagnostics } = parseShenlunCapture(capture({ questions }));
  assert.deepEqual(doc.questions[0].materialIds, ['material-1']);
  assert.deepEqual(doc.questions[1].materialIds, []);
  assert.equal(diagnostics.unresolvedMaterialReferences.length, 1);
  assert.equal(diagnostics.unresolvedMaterialReferences[0].questionNumber, 2);
  const verdict = await validateDocument(doc);
  assert.ok(codes(verdict).has('material-reference-unstored'));
  assert.ok(codes(verdict).has('material-reference-missing'));
  assert.equal(verdict.dimensions.materials.status, 'partial');
});

test('material tab count above stored panes is reported as an incomplete material pane', async () => {
  const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] });
  fixture.domHtml = domHtml('合成申论卷', 3);
  const { doc, diagnostics } = parseShenlunCapture(fixture);
  assert.equal(diagnostics.materialTabs, 3);
  assert.equal(diagnostics.storedMaterials, 1);
  const verdict = await validateDocument(doc);
  const issue = verdict.issues.find(item => item.code === 'material-pane-incomplete');
  assert.ok(issue);
  assert.equal(issue.declared, 3);
  assert.equal(issue.stored, 1);
});

test('a missing question slot stays missing and is never renumbered', async () => {
  const questions = [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) }), question({ index: 3, key: 'k3', materialHash: sha(MATERIAL) })];
  const { doc, diagnostics } = parseShenlunCapture(capture({ questions, total: 3 }));
  assert.deepEqual(doc.questions.map(q => q.number), [1, 3]);
  assert.deepEqual(diagnostics.missingQuestionNumbers, [2]);
  assert.equal(doc.expected.questions, 3);
  const verdict = await validateDocument(doc);
  assert.ok(codes(verdict).has('question-slot-missing'));
  assert.ok(codes(verdict).has('question-number-set-mismatch'));
});

test('paperId disagreement between meta.json and document.json blocks identity binding', async () => {
  const fixture = capture({
    questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })],
    meta: { paperId: 'synthetic-9999' },
  });
  const { doc } = parseShenlunCapture(fixture);
  assert.equal(doc.identity.id, 'synthetic-9999');
  assert.ok(doc.conflicts.some(conflict => conflict.field === 'paperId'));
  const verdict = await validateDocument(doc);
  assert.ok(codes(verdict).has('paper-identity-mismatch'));
  assert.equal(verdict.dimensions.identity.status, 'partial');
});

test('year policy: all visible Zhejiang years pass, pre-2016 elsewhere fails', async () => {
  const zhejiang = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })], identity: { year: 2005 }, meta: { year: 2005 } });
  assert.ok(!codes(await validateDocument(parseShenlunCapture(zhejiang).doc)).has('year-invalid'));
  const jiangsu = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })], identity: { area: '江苏', year: 2005 }, meta: { area: '江苏', year: 2005 } });
  assert.ok(codes(await validateDocument(parseShenlunCapture(jiangsu).doc)).has('year-invalid'));
});

test('title comes from the observed DOM title, never from the title hash', async () => {
  const { doc } = parseShenlunCapture(capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] }));
  assert.equal(doc.identity.title, '合成申论卷');
  assert.equal(doc.shenlun.titleSource, 'dom-title');
  const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] });
  fixture.domHtml = '<html><body></body></html>';
  const noTitle = parseShenlunCapture(fixture).doc;
  assert.equal(noTitle.identity.title, '');
  assert.ok(codes(await validateDocument(noTitle)).has('identity-unknown'));
});

test('a fully captured synthetic paper can reach complete, and Markdown keeps answer and analysis separate', async () => {
  const { doc } = parseShenlunCapture(capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] }));
  const verdict = await validateDocument(doc);
  assert.equal(verdict.status, 'complete');
  const markdown = renderCandidate(doc, verdict);
  assert.match(markdown, /## 给定材料/u);
  assert.match(markdown, /### 材料 1/u);
  assert.match(markdown, /## 题目/u);
  assert.match(markdown, /### 第 1 题/u);
  assert.match(markdown, /作答要求/u);
  assert.match(markdown, /## 答案与解析/u);
  assert.match(markdown, /\*\*参考答案/u);
  assert.match(markdown, /\*\*解析/u);
  assert.match(markdown, /合成参考答案正文/u);
  assert.match(markdown, /合成文字解析正文/u);
  assert.doesNotMatch(markdown, /EMBEDDED_COPY_MUST_NOT_BE_USED|合成视频解析占位说明|合成来源说明/u);
});

test('an answer-only source renders analysis as unknown instead of copying the answer', async () => {
  const { doc } = parseShenlunCapture(capture({
    questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL), prompt: { analysis: null } })],
  }));
  const verdict = await validateDocument(doc);
  assert.notEqual(verdict.status, 'complete');
  assert.ok(codes(verdict).has('explanation-empty'));
  assert.equal(doc.questions[0].explanationHtml, '');
  // 未通过结构验收的卷不得渲染/导出；解析缺失只能标 unknown，不能复制参考答案来凑完整。
  assert.throws(() => renderCandidate(doc, verdict), /independently validated complete/u);
});

test('metadata receipt never carries question, material, answer or analysis text', async () => {
  const { doc } = parseShenlunCapture(capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] }));
  const verdict = await validateDocument(doc);
  const receipt = JSON.stringify(metadataReceipt(doc, verdict));
  for (const marker of ['合成题干', '合成材料一', '合成参考答案正文', '合成文字解析正文', '合成来源说明', EMBEDDED_ANSWER]) {
    assert.ok(!receipt.includes(marker), `receipt leaked ${marker}`);
  }
  assert.match(receipt, /synthetic-1001/u);
  assert.deepEqual(publicationBlockers(doc), ['cloud-storage-blocked', 'rights-not-cleared']);
});

test('privacy sanitizer strips active content and credential-bearing image references', () => {
  const fixture = capture({
    questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL), prompt: { stem: `${STEM}<script>alert(1)</script><img src="https://example.test/a.png?token=secret">` } })],
  });
  const { doc } = parseShenlunCapture(fixture);
  const serialized = JSON.stringify(doc.questions[0].contentHtml);
  assert.doesNotMatch(serialized, /<script|token=secret/u);
  assert.ok(doc.conflicts.some(conflict => conflict.scope === 'privacy'));
});

test('requirements split by an explicit 要求 paragraph without losing text', () => {
  const split = splitRequirements(`<div><p>${STEM}</p><p>补充条件段。</p><p>${REQUIREMENTS}</p></div>`);
  assert.match(split.contentHtml, /合成题干/u);
  assert.match(split.contentHtml, /补充条件段/u);
  assert.doesNotMatch(split.contentHtml, /不超过300字/u);
  assert.match(split.requirementsHtml, /不超过300字/u);
  assert.equal(split.requirementsSource, 'labelled-paragraph');
  const none = splitRequirements(`<div><p>${STEM}</p><p>补充条件段。</p></div>`);
  assert.equal(none.requirementsHtml, '');
  assert.match(none.contentHtml, /补充条件段/u);
});

test('DOM inspection reads tabs and title without inventing page content', () => {
  const dom = inspectShenlunDom(domHtml('合成申论卷', 8));
  assert.equal(dom.title, '合成申论卷');
  assert.equal(dom.materialTabs, 8);
  assert.equal(dom.questionTabs, 3);
  assert.equal(dom.activeQuestionKey, '3_2_synthetic');
});

test('loadShenlunCapture reads document/meta/dom from a folder and parses identically', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'shenlun-fixture-'));
  try {
    const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] });
    await mkdir(dir, { recursive: true });
    await writeFile(path.join(dir, 'document.json'), JSON.stringify(fixture.capture));
    await writeFile(path.join(dir, 'meta.json'), JSON.stringify(fixture.meta));
    await writeFile(path.join(dir, 'dom.html'), fixture.domHtml);
    const loaded = await loadShenlunCapture(dir);
    const { doc } = parseShenlunCapture(loaded);
    assert.equal(doc.identity.id, 'synthetic-1001');
    assert.equal((await validateDocument(doc)).status, 'complete');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('missing referenceAnswer falls back to the observed 参考答案 section, and says so', () => {
  const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] });
  fixture.capture.questions[0].referenceAnswer = [];
  const { doc } = parseShenlunCapture(fixture);
  assert.equal(doc.questions[0].answerSource, 'embedded-section');
  // 页面里的嵌入副本本来就是合成占位，说明回退读取的是“参考答案”分区而不是别处。
  assert.match(doc.questions[0].answerHtml, new RegExp(EMBEDDED_ANSWER, 'u'));
  const { doc: preferred } = parseShenlunCapture(capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] }));
  assert.equal(preferred.questions[0].answerSource, 'referenceAnswer');
});

test('without DOM evidence the material tab total stays unknown, not assumed complete', async () => {
  const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] });
  fixture.domHtml = null;
  const { doc } = parseShenlunCapture(fixture);
  assert.equal(doc.expected.materials, null);
  assert.equal(doc.shenlun.materialTabs, null);
  assert.ok(codes(await validateDocument(doc)).has('material-count-unknown'));
});

test('numbered sub-requirements after a 要求 heading stay in the requirements block', () => {
  const split = splitRequirements(`<div><p>${STEM}</p><p>要求：</p><p>（1）观点明确；</p><p>（2）不超过300字。</p></div>`);
  assert.match(split.requirementsHtml, /观点明确/u);
  assert.match(split.requirementsHtml, /不超过300字/u);
  assert.doesNotMatch(split.contentHtml, /观点明确|不超过300字/u);
  assert.equal(split.requirementsSource, 'labelled-paragraph');
});

test('requirements split refuses to move a trailing paragraph that is not a requirement', () => {
  const split = splitRequirements(`<div><p>${STEM}</p><p>要求：不超过300字。</p><p>这里是题干后续说明，不是作答要求。</p></div>`);
  assert.equal(split.requirementsHtml, '');
  assert.match(split.contentHtml, /题干后续说明/u);
});

test('image-only analysis is kept as image-only, not promoted to textual analysis', () => {
  const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL), prompt: { analysis: '<img src="https://img.example.test/analysis.png">' } })] });
  const { doc, diagnostics } = parseShenlunCapture(fixture);
  assert.equal(doc.questions[0].analysisStatus, 'image-only');
  assert.equal(diagnostics.analysis.textual, 0);
  assert.equal(diagnostics.analysis.imageOnly, 1);
});

test('DOM question tabs provide a missing-slot lower bound when anchors are absent', async () => {
  const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] });
  delete fixture.capture.questions[0].anchorsVisible;
  fixture.domHtml = domHtml('合成申论卷', 1);
  const { doc, diagnostics } = parseShenlunCapture(fixture);
  assert.equal(doc.expected.questions, 3);
  assert.deepEqual(diagnostics.missingQuestionNumbers, [2, 3]);
  assert.ok(codes(await validateDocument(doc)).has('question-slot-missing'));
});

test('route query strings and fragments never enter the recorded source URL', () => {
  const fixture = capture({ questions: [question({ index: 1, key: 'k1', materialHash: sha(MATERIAL) })] });
  fixture.capture.source.detailPath = '/ti/view/paper/3_2_synthetic?token=secret#frag';
  const { doc } = parseShenlunCapture(fixture);
  assert.equal(doc.source.url, 'https://www.fenbi.com/ti/view/paper/3_2_synthetic');
  assert.doesNotMatch(JSON.stringify(doc), /token=secret/u);
});

test('a non-shenlun or wrong-schema capture is rejected instead of guessed', () => {
  const xingce = capture({ questions: [] });
  xingce.capture.subject = 'xingce';
  assert.throws(() => parseShenlunCapture(xingce), /capture-subject-must-be-shenlun/u);
  const stale = capture({ questions: [] });
  stale.capture.schemaVersion = 1;
  assert.throws(() => parseShenlunCapture(stale), /unsupported-capture-schema/u);
});
