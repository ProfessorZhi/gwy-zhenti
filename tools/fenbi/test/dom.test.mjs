import test from 'node:test';
import assert from 'node:assert/strict';
import { parseFenbiExamDom } from '../src/dom.mjs';

const identity = { id: 'synthetic-paper', title: '合成行测', subject: 'xingce', area: '浙江', year: 2026, variant: 'C类' };
const source = { url: 'https://spa.fenbi.com/ti/exam/exercise/synthetic-test' };
const question = (number, key = `3_1_key${number}`) => `<app-ti data-question-key="${key}"><div class="title-index">${number}.</div><div class="question-choice-container"><p>条件 x ≥ ${number}，求结果。</p><app-choice-radio><label class="choice-radio-label"><div class="input-radio">A</div><p class="input-text">甲</p></label><label class="choice-radio-label"><div class="input-radio">B</div><p class="input-text">乙</p></label></app-choice-radio></div></app-ti>`;

test('DOM adapter reads both single and grouped questions with full shared materials and chapter counts', () => {
  const material = '完整材料。'.repeat(2000);
  const html = `<div class="tis-container"><div class="chapter-container">常识判断（1题）请选择。</div><div class="questions-single-container">${question(1)}</div><div class="chapter-container">资料分析（2题）根据资料作答。</div><div class="resizable-container"><div class="left"><div class="materials-container"><div class="material-body"><div class="material-content">${material}</div><p class="material-content"><img src="//fb.fbstatic.cn/chart.png?width=700"></p></div></div></div><div class="right"><div class="questions-container">${question(2)}${question(3)}</div></div></div></div>`;
  const doc = parseFenbiExamDom(html, identity, source);
  assert.equal(doc.questions.length, 3); assert.equal(doc.expected.questions, 3);
  assert.equal(doc.materials.length, 1); assert.equal(doc.expected.materials, 1);
  assert.ok(doc.materials[0].contentHtml.includes(material)); assert.equal(doc.assets.length, 1);
  assert.equal(doc.questions[0].materialIds.length, 0); assert.equal(doc.questions[0].materialIdsObserved, true);
  assert.deepEqual(doc.questions[1].materialIds, doc.questions[2].materialIds);
  assert.equal(doc.questions[1].options.length, 2); assert.equal(doc.questions[1].options[0].label, 'A');
  assert.ok(!doc.questions[1].contentHtml.includes('choice-radio-label'));
  assert.ok(doc.questions[1].contentHtml.includes('≥ 2'));
  assert.equal(doc.identity.questionIdNamespace, 'fenbi-question-key');
});

test('observed DOM nodes never fabricate expected totals, answers, source IDs or original numbers', () => {
  const html = `<div class="questions-single-container">${question(1)}${question(2).replace('2.</div>', '未知.</div>')}</div>`;
  const doc = parseFenbiExamDom(html, identity, source);
  assert.equal(doc.expected.questions, null);
  assert.equal(doc.questions.length, 1); assert.equal(doc.questions[0].answerHtml, '');
  assert.ok(doc.conflicts.some(item => item.field === 'unrecognized-question-number'));
});

test('duplicate source question keys and incomplete material containers remain conflicts', () => {
  const doc = parseFenbiExamDom(`${question(1, 'duplicate')}${question(2, 'duplicate')}<div class="materials-container">缺少材料正文容器</div>`, identity, source);
  assert.ok(doc.conflicts.some(item => item.field === 'duplicate-question-key'));
  assert.ok(doc.conflicts.some(item => item.field === 'unparsed-material-container'));
  assert.throws(() => parseFenbiExamDom('', { ...identity, subject: 'shenlun' }, source), /Xingce only/);
});
