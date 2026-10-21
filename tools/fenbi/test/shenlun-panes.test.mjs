import test from 'node:test';
import assert from 'node:assert/strict';
import { assembleMaterialPanes, materialsThisQuestion, sha256 } from '../src/shenlun-panes.mjs';
import { parseShenlunCapture, inspectShenlunDom } from '../src/shenlun.mjs';
import { validateDocument } from '../src/validate.mjs';

const pane = (n, body = `synthetic material ${n}`) => ({
  tabIndex: n - 1,
  tabLabel: `材料${n}`,
  html: `<p>${body}</p>`,
  textLen: body.length,
  images: 0,
});

test('question-scoped tab strips merge into one paper-level material list without duplication', () => {
  const result = assembleMaterialPanes({
    questions: [
      { index: 1, panes: [pane(1), pane(2), pane(3)] },
      { index: 2, panes: [pane(1), pane(2), pane(3), pane(4), pane(5), pane(6), pane(7)] },
    ],
  });
  assert.equal(result.materials.length, 7);
  assert.equal(result.evidence.distinctPanes, 7);
  assert.equal(result.evidence.paneObservations, 10);
  assert.equal(result.evidence.declaredMaterialTabs, 7);
  assert.deepEqual(result.evidence.perQuestionPanes.map(entry => entry.panes), [3, 7]);
  assert.deepEqual(result.questions[0].materialReferences.map(reference => reference.tabNumber), [1, 2, 3]);
  assert.deepEqual(result.questions[1].materialReferences.map(reference => reference.tabNumber), [1, 2, 3, 4, 5, 6, 7]);
  // 同一材料在不同题下哈希一致，只保留一份。
  assert.equal(new Set(result.materials.map(material => material.htmlSha)).size, 7);
  assert.equal(result.materials[0].firstSeenQuestionIndex, 1);
  assert.deepEqual(result.materials[0].tabNumbers, [1]);
});

test('material numbering follows the observed tab labels, not the capture order', () => {
  const result = assembleMaterialPanes({
    questions: [{ index: 1, panes: [{ tabIndex: 0, tabLabel: '材料2', html: '<p>two</p>' }, { tabIndex: 1, tabLabel: '材料1', html: '<p>one</p>' }] }],
  });
  assert.deepEqual(result.materials.map(material => material.tabNumbers[0]), [2, 1]);
  // 标签序号 1、2 都在且连续 ⇒ 卷面声明 2 个材料（顺序与点击顺序无关）。
  assert.equal(result.evidence.declaredMaterialTabs, 2);
});

test('a pane without a numeric label falls back to its position and is flagged', () => {
  const result = assembleMaterialPanes({
    questions: [{ index: 1, panes: [{ tabIndex: 0, tabLabel: '材料甲', html: '<p>a</p>' }, { tabIndex: 1, tabLabel: '材料2', html: '<p>b</p>' }] }],
  });
  assert.deepEqual(result.evidence.labelNumbering, { fromLabel: 1, fromPosition: 1 });
  assert.equal(result.evidence.declaredMaterialTabs, null);
  assert.equal(result.materials.length, 2);
});

test('a duplicate hash inside one question is collapsed and reported', () => {
  const shared = pane(1).html;
  const result = assembleMaterialPanes({
    questions: [{ index: 1, panes: [{ tabIndex: 0, tabLabel: '材料1', html: shared }, { tabIndex: 1, tabLabel: '材料2', html: shared }] }],
  });
  assert.equal(result.materials.length, 1);
  assert.equal(result.questions[0].materialReferences.length, 1);
  assert.equal(result.evidence.duplicateHashesWithinQuestion.length, 1);
});

test('two different bodies under the same tab number are kept and reported, never overwritten', () => {
  const result = assembleMaterialPanes({
    questions: [{ index: 1, panes: [{ tabIndex: 0, tabLabel: '材料1', html: '<p>one</p>' }, { tabIndex: 1, tabLabel: '材料1', html: '<p>other</p>' }] }],
  });
  assert.equal(result.materials.length, 2);
  assert.equal(result.evidence.duplicateTabNumberWithinQuestion.length, 1);
  assert.equal(result.evidence.declaredMaterialTabs, null);
});

test('an empty pane is dropped and counted instead of stored as an empty material', () => {
  const result = assembleMaterialPanes({
    questions: [{ index: 1, panes: [pane(1), { tabIndex: 1, tabLabel: '材料2', html: '   ' }] }],
  });
  assert.equal(result.materials.length, 1);
  assert.equal(result.evidence.emptyPanes, 1);
});

test('missing tabs are never invented: a question that saw nothing keeps an empty reference list', () => {
  const result = assembleMaterialPanes({
    questions: [{ index: 1, panes: [] }, { index: 2, panes: [pane(1)] }],
  });
  assert.deepEqual(result.questions[0].materialReferences, []);
  assert.deepEqual(result.evidence.perQuestionPanes[0].panes, 0);
  assert.equal(result.materials.length, 1);
});

test('questions-required', () => {
  assert.throws(() => assembleMaterialPanes({ questions: [] }), /questions-required/u);
});

test('merged panes parse back through PR108 into one material per pane with no unresolved reference', async () => {
  const merged = assembleMaterialPanes({
    questions: [
      { index: 1, panes: [pane(1), pane(2)] },
      { index: 2, panes: [pane(1), pane(2), pane(3)] },
    ],
  });
  const questions = merged.questions.map((question, position) => ({
    index: question.index,
    questionKey: `key-${position + 1}`,
    anchorsVisible: ['1题', '2题'],
    prompt: { textLen: 10, html: '<p>synthetic prompt</p>' },
    materialsThisQuestion: materialsThisQuestion(question.materialReferences),
    referenceAnswer: [{ title: '参考答案', html: '<p>synthetic answer</p>' }],
    otherSections: [],
  }));
  const capture = {
    schemaVersion: 2,
    subject: 'shenlun',
    identity: { sourceId: 'synthetic', paperId: 'synthetic', area: '浙江', year: 2020, variant: 'a' },
    materials: merged.materials.map(material => ({ index: material.index, html: material.html, htmlSha: material.htmlSha, textLen: material.textLen })),
    questions,
  };
  const domHtml = `<html><head><title>synthetic</title></head><body>
    <div class="choose-tabs-container"><a class="choose-tab">材料1</a><a class="choose-tab">材料2</a><a class="choose-tab">材料3</a></div>
  </body></html>`;
  assert.equal(inspectShenlunDom(domHtml).materialTabs, 3);
  const { doc, diagnostics } = parseShenlunCapture({ capture, domHtml });
  assert.equal(doc.materials.length, 3);
  assert.equal(doc.expected.materials, 3);
  assert.deepEqual(diagnostics.unresolvedMaterialReferences, []);
  assert.deepEqual(doc.questions.map(question => question.materialIds), [['material-1', 'material-2'], ['material-1', 'material-2', 'material-3']]);
  const verdict = await validateDocument(doc);
  const codes = new Set(verdict.issues.map(issue => issue.code));
  assert.equal(codes.has('material-count-mismatch'), false);
  assert.equal(codes.has('material-pane-incomplete'), false);
  assert.equal(codes.has('material-reference-unstored'), false);
});

test('a shortfall is still a shortfall: 2 stored panes against a 7-tab source fails the pane gate', async () => {
  const capture = {
    schemaVersion: 2,
    subject: 'shenlun',
    identity: { sourceId: 'synthetic', paperId: 'synthetic', area: '浙江', year: 2020, variant: 'a' },
    materials: [pane(1), pane(2)].map((entry, index) => ({ index, html: entry.html, htmlSha: sha256(entry.html), textLen: entry.textLen })),
    questions: [{
      index: 1, questionKey: 'k1', anchorsVisible: ['1题'],
      prompt: { html: '<p>synthetic prompt</p>' },
      materialsThisQuestion: [{ htmlSha: sha256(pane(1).html), textLen: 19 }],
      referenceAnswer: [{ title: '参考答案', html: '<p>synthetic answer</p>' }],
    }],
  };
  const domHtml = `<html><head><title>synthetic</title></head><body><div class="choose-tabs-container">
    ${[1, 2, 3, 4, 5, 6, 7].map(number => `<a class="choose-tab">材料${number}</a>`).join('')}
  </div></body></html>`;
  const { doc } = parseShenlunCapture({ capture, domHtml });
  const verdict = await validateDocument(doc);
  const incomplete = verdict.issues.find(issue => issue.code === 'material-pane-incomplete');
  assert.ok(incomplete, 'shortfall must be reported');
  assert.equal(incomplete.declared, 7);
});
