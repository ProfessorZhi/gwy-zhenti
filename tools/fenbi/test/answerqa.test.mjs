import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createDocument } from '../src/model.mjs';
import { validateDocument } from '../src/validate.mjs';
import { comparePaper, alignmentExitCode } from '../src/align.mjs';

/**
 * Offline synthetic fixtures for the answer/explanation evidence path. Nothing here contacts
 * Fenbi, opens a browser, or contains real captured content: every body is generated locally so
 * the answer-verification vocabulary can be tested without a login or a live practice page.
 */

const sha = (value) => createHash('sha256').update(value).digest('hex');

// ── validate: an entitlement notice is not an observed answer ────────────────────────────────

function paper({ subject = 'xingce', answerHtml = 'B', explanationHtml = '根据题干条件，乙符合全部要求，故选择B项。' } = {}) {
  const doc = createDocument({ id: 'synthetic-1', title: '合成卷', subject, year: 2025, area: '江苏', variant: 'C类' },
    { url: 'https://www.fenbi.com/spa/tiku/synthetic-1', capturedAt: new Date().toISOString() });
  doc.expected.questions = 1;
  doc.evidence.push({ type: 'source-paper-identity', paperId: 'synthetic-1', url: doc.source.url });
  if (subject === 'shenlun') {
    doc.expected.materials = 1;
    doc.materials = [{ id: 'm1', contentHtml: `<p>${'合成材料正文。'.repeat(60)}</p>` }];
    doc.questions = [{ id: 'q1', number: 1, contentHtml: '<p>根据材料作答。</p>', options: [], materialIds: ['m1'],
      answerHtml, explanationHtml, requirementsHtml: '<p>围绕材料作答，不超过400字。</p>' }];
  } else {
    doc.expected.materials = 0;
    doc.questions = [{ id: 'q1', number: 1, contentHtml: '<p>合成题干。</p>',
      options: [{ label: 'A', contentHtml: '甲' }, { label: 'B', contentHtml: '乙' }], materialIds: [],
      answerHtml, explanationHtml, requirementsHtml: '' }];
  }
  return doc;
}

// Every string below is a gate notice the framework must refuse to read as content. The first
// three previously validated as `complete`, which then exported a candidate paper and set a
// checkpoint that later runs skipped as verified.
const GATE_NOTICES = [
  '登录后可查看参考答案',
  '本题参考答案与详细解析需要开通粉笔会员后方可查看，请先登录并购买相应课程后再试。',
  '您当前暂无权限查看本题的参考答案与详细解析，请登录已购买该课程的账号后重试。',
];

test('an entitlement notice in the answer slot never counts as an observed answer', async () => {
  for (const notice of GATE_NOTICES) {
    for (const subject of ['xingce', 'shenlun']) {
      const verdict = await validateDocument(paper({ subject, answerHtml: `<p>${notice}</p>` }));
      assert.equal(verdict.dimensions.answers.status, 'partial', `${subject}: ${notice}`);
      assert.ok(verdict.issues.some((issue) => issue.code === 'answer-access-gate'), `${subject}: ${notice}`);
      assert.notEqual(verdict.status, 'complete');
    }
  }
});

test('an entitlement notice in the explanation slot never counts as an observed explanation', async () => {
  for (const notice of GATE_NOTICES) {
    // A correct reference answer must not let a locked explanation view pass the whole paper.
    const verdict = await validateDocument(paper({ subject: 'xingce', answerHtml: 'B', explanationHtml: `<p>${notice}</p>` }));
    assert.equal(verdict.status, 'partial');
    assert.equal(verdict.dimensions.answers.status, 'complete');
    assert.equal(verdict.dimensions.explanations.status, 'partial');
    assert.ok(verdict.issues.some((issue) => issue.code === 'explanation-access-gate'));
  }
});

test('genuine content that merely mentions membership and permissions is still accepted', async () => {
  const body = '消费者开通视频会员后即可获取相应权益，但平台在用户不知情的情况下自动续费，侵犯了消费者的知情权与选择权。'
    + '根据《消费者权益保护法》第八条，经营者应当向消费者提供有关服务的真实信息，故本项表述正确。';
  const doc = paper({ subject: 'shenlun', answerHtml: `<p>${body}</p>`, explanationHtml: `<p>${body}</p>` });
  const verdict = await validateDocument(doc);
  assert.ok(!verdict.issues.some((issue) => /access-gate/u.test(issue.code)));
  assert.equal(verdict.dimensions.answers.status, 'complete');
  assert.equal(verdict.dimensions.explanations.status, 'complete');
  assert.equal(verdict.status, 'complete');
});

test('an image-backed answer is judged by its bytes, not by adjacent gate text', async () => {
  const verdict = await validateDocument(paper({ subject: 'shenlun',
    answerHtml: '<p>登录后可查看参考答案</p><img src="https://img.fbstatic.cn/answer.png">', explanationHtml: '<img src="https://img.fbstatic.cn/analysis.png">' }));
  assert.ok(!verdict.issues.some((issue) => /access-gate/u.test(issue.code)));
});

// ── align: explicit unknown / partial / conflicting / verified ───────────────────────────────

const SOURCE_IDS = ['s-1', 's-2'];
function sourceDoc({ answerHtml = '', explanationHtml = '', materialIdsObserved = true, expected = 2, subject = 'xingce' } = {}) {
  const doc = createDocument({ id: 'paper', title: '合成卷', subject, year: 2025, area: '江苏', variant: 'C类' },
    { url: 'https://www.fenbi.com/spa/tiku/paper', capturedAt: new Date().toISOString() });
  doc.expected.questions = expected; doc.expected.materials = 0;
  doc.questions = SOURCE_IDS.map((id, index) => ({ id, number: index + 1, contentHtml: `<p>第${index + 1}题的合成题干。</p>`,
    options: [{ label: 'A', contentHtml: '甲' }, { label: 'B', contentHtml: '乙' }],
    materialIds: [], materialIdsObserved, answerHtml, explanationHtml, requirementsHtml: '' }));
  return doc;
}
const mdQuestion = (n, id) => `## 第 ${n} 题 <sub>qid ${id}</sub>\n\n第${n}题的合成题干。\n\n- **A**. 甲\n- **B**. 乙\n`;
const mdAnswers = (rows) => `\n## 答案与解析\n${rows.map(([n, answer, explanation]) =>
  `<details>\n<summary>第 ${n} 题</summary>\n\n**答案**：${answer}\n\n**解析**\n\n${explanation}\n\n---\n</details>`).join('\n')}`;
const repositoryPaper = (rows = [['s-1', 'B', '甲不对，故选B。'], ['s-2', 'A', '乙不对，故选A。']]) =>
  SOURCE_IDS.map((id, index) => mdQuestion(index + 1, id)).join('\n') + mdAnswers(rows.map(([id, a, e], index) => [index + 1, a, e]));

test('answers and explanations the practice page never exposed stay explicitly unknown', async () => {
  const report = await comparePaper(sourceDoc(), repositoryPaper());
  assert.equal(report.verification.verdict, 'partial');
  assert.equal(report.verification.dimensions.answer.disposition, 'unknown');
  assert.equal(report.verification.dimensions.explanation.disposition, 'unknown');
  assert.deepEqual(report.verification.dimensions.answer.counts, { same: 0, different: 0, unknown: 2, not_compared: 0 });
  assert.deepEqual(report.verification.unverified, ['answer', 'explanation']);
  assert.equal(report.verification.dimensions.stem.disposition, 'verified');
  assert.equal(report.summary.verdict, 'partial');
  assert.equal(report.summary.allQualityPassed, false);
});

test('observed and equal answers on both sides are the only way to a verified verdict', async () => {
  const doc = sourceDoc({ answerHtml: 'B', explanationHtml: '甲不对，故选B。' });
  doc.questions[1].answerHtml = 'A'; doc.questions[1].explanationHtml = '乙不对，故选A。';
  const report = await comparePaper(doc, repositoryPaper());
  assert.equal(report.verification.dimensions.answer.disposition, 'verified');
  assert.equal(report.verification.dimensions.explanation.disposition, 'verified');
  assert.equal(report.verification.verdict, 'verified');
  assert.equal(report.summary.allQualityPassed, true);
  assert.equal(alignmentExitCode(report), 0);
  // A paper with no images anywhere is "not applicable", never a hidden failure.
  assert.ok(report.verification.notApplicable.includes('images'));
});

test('observed answers that disagree with the repository are conflicting, not unknown', async () => {
  const doc = sourceDoc({ answerHtml: 'B', explanationHtml: '甲不对，故选B。' });
  doc.questions[1].answerHtml = 'B'; doc.questions[1].explanationHtml = '乙不对，故选A。';
  const report = await comparePaper(doc, repositoryPaper());
  assert.equal(report.verification.dimensions.answer.disposition, 'conflicting');
  assert.equal(report.verification.verdict, 'conflicting');
  assert.equal(report.summary.allQualityPassed, false);
  assert.equal(alignmentExitCode(report), 2);
});

test('an observed answer with no repository answer is conflicting, never verified', async () => {
  const report = await comparePaper(sourceDoc({ answerHtml: 'B', explanationHtml: '甲不对，故选B。' }),
    SOURCE_IDS.map((id, index) => mdQuestion(index + 1, id)).join('\n'));
  assert.equal(report.verification.dimensions.answer.disposition, 'conflicting');
  assert.equal(report.questions[0].dimensions.answer.reason, 'repository-content-absent');
  assert.notEqual(report.verification.verdict, 'verified');
});

test('an unmatched paper cannot report "no differences" from an empty dimension list', async () => {
  const doc = sourceDoc({ answerHtml: 'B', explanationHtml: '甲不对，故选B。' });
  const report = await comparePaper(doc, mdQuestion(9, 'unknown-id') + mdQuestion(10, 'unknown-id-2'));
  assert.equal(report.summary.matched, 0);
  // The zero-filled aggregate is the point: an empty object previously satisfied every check.
  assert.deepEqual(Object.keys(report.summary.dimensionCounts).sort(),
    ['answer', 'explanation', 'images', 'materials', 'number', 'options', 'qid', 'stem']);
  assert.ok(Object.values(report.summary.dimensionCounts).every((counts) => counts.same === 0));
  assert.equal(Object.values(report.summary.dimensionCounts).every((counts) => counts.different === 0), true);
  assert.equal(report.verification.verdict, 'unknown');
  assert.equal(report.summary.allQualityPassed, false);
  assert.equal(alignmentExitCode(report), 2);
  assert.equal(report.verification.dimensions.answer.disposition, 'not_applicable');
});

test('a partially matched paper reports partial, and only a fully verified one exits zero', async () => {
  const doc = sourceDoc({ answerHtml: 'B', explanationHtml: '甲不对，故选B。' });
  doc.questions.pop(); doc.expected.questions = 2;
  const report = await comparePaper(doc, repositoryPaper());
  assert.equal(report.summary.matched, 1);
  assert.equal(report.verification.verdict, 'unknown');
  assert.equal(alignmentExitCode(report), 2);
  for (const verdict of ['partial', 'unknown', 'conflicting', null, undefined]) {
    assert.equal(alignmentExitCode({ verification: { verdict } }), 2);
  }
});

test('an undeclared question-ID namespace is disclosed instead of implied compatible', async () => {
  const declared = sourceDoc();
  declared.identity.questionIdNamespace = 'fenbi-question-key';
  const assumed = sourceDoc();
  assert.equal((await comparePaper(declared, repositoryPaper())).identity.questionIdNamespaceAssumed, false);
  assert.equal((await comparePaper(assumed, repositoryPaper())).identity.questionIdNamespaceAssumed, true);
});

// ── align: operator-observed manual evidence ────────────────────────────────────────────────

const manual = (entry) => ({ observedAt: '2026-10-17T00:00:00.000Z', method: 'operator-screenshot-read', ...entry });

test('manual evidence is reported beside the automated counts and never becomes a pass', async () => {
  const doc = sourceDoc();
  doc.manualEvidence = [manual({ dimension: 'answer', questionId: 's-1', value: 'B' }),
    manual({ dimension: 'explanation', questionId: 's-1', value: '甲不对，故选B。' })];
  const report = await comparePaper(doc, repositoryPaper());
  assert.equal(report.verification.dimensions.answer.manual.disposition, 'partial');
  assert.equal(report.verification.dimensions.answer.manual.records[0].status, 'verified');
  assert.equal(report.verification.dimensions.answer.manual.records[0].reason, 'manual-value-compared-with-repository');
  // The automated counts are untouched, so an operator reading alone can never produce a pass.
  assert.deepEqual(report.verification.dimensions.answer.counts, { same: 0, different: 0, unknown: 2, not_compared: 0 });
  assert.equal(report.verification.dimensions.answer.disposition, 'unknown');
  assert.equal(report.verification.verdict, 'partial');
  assert.equal(report.summary.allQualityPassed, false);
});

test('manual evidence that disagrees with the repository is conflicting', async () => {
  const doc = sourceDoc();
  doc.manualEvidence = [manual({ dimension: 'answer', questionId: 's-1', value: 'A' }),
    manual({ dimension: 'explanation', questionId: 's-1', value: '乙不对，故选A。' })];
  const report = await comparePaper(doc, repositoryPaper());
  assert.equal(report.verification.dimensions.answer.manual.disposition, 'conflicting');
  assert.equal(report.verification.dimensions.answer.manual.records[0].status, 'conflicting');
});

test('manual evidence must bind to exactly one captured, automatically matched source question', async () => {
  const doc = sourceDoc();
  doc.manualEvidence = [
    manual({ dimension: 'answer', questionId: 'not-captured', value: 'B' }),
    manual({ dimension: 'answer', value: 'B' }),
    manual({ dimension: 'answer', questionId: 's-1', value: '' }),
    manual({ dimension: 'answer', questionId: 's-1', value: 'B', observedAt: 'not-a-date' }),
    manual({ dimension: 'answer', questionId: 's-1', value: 'B', method: '' }),
    manual({ dimension: 'stem', questionId: 's-1', value: 'B' }),
  ];
  const records = (await comparePaper(doc, repositoryPaper())).verification.dimensions.answer.manual.records;
  assert.equal(records.length, 5);
  assert.deepEqual(records.map((record) => record.status), ['unbound', 'unbound', 'incomplete', 'incomplete', 'incomplete']);
  assert.equal(records[0].reason, 'no-captured-source-question');
  assert.ok(records.every((record) => record.status !== 'verified'));

  // A captured question the automated pass could not match cannot be manually "verified" either.
  const unbound = sourceDoc();
  unbound.manualEvidence = [manual({ dimension: 'answer', questionId: 's-1', value: 'B' })];
  assert.equal((await comparePaper(unbound, mdQuestion(9, 'other') + mdQuestion(10, 'other-2'))).verification.dimensions.answer.manual.records[0].status, 'unmatched-source');
});

test('manually observed values and credential URLs never reach the report', async () => {
  const secret = 'SYNTHETIC_MANUAL_SECRET_VALUE';
  const doc = sourceDoc();
  doc.manualEvidence = [manual({ dimension: 'answer', questionId: 's-1', value: `参考答案 ${secret}`, operator: 'operator-a',
    observedUrl: 'https://www.fenbi.com/spa/tiku/paper?paperId=1&token=SYNTHETIC_PRIVATE_TOKEN' })];
  const report = JSON.stringify(await comparePaper(doc, repositoryPaper()));
  assert.ok(!report.includes(secret));
  assert.ok(!report.includes('SYNTHETIC_PRIVATE_TOKEN'));
  const record = JSON.parse(report).verification.dimensions.answer.manual.records[0];
  assert.equal(record.valueSha256, sha(`参考答案 ${secret}`));
  assert.equal(record.valueLength, `参考答案 ${secret}`.length);
  assert.equal(record.observedUrl, 'https://www.fenbi.com/spa/tiku/paper?paperId=1');
  assert.equal(record.operator, 'operator-a');
});

test('the verification block always names every dimension and its basis', async () => {
  const report = await comparePaper(sourceDoc(), repositoryPaper());
  assert.deepEqual(Object.keys(report.verification.dimensions).sort(),
    ['answer', 'explanation', 'images', 'materials', 'number', 'options', 'qid', 'stem']);
  assert.deepEqual(Object.keys(report.verification.paper).sort(),
    ['materialCount', 'order', 'orderById', 'qidSet', 'questionCount']);
  assert.deepEqual(report.verification.states, ['verified', 'partial', 'conflicting', 'unknown', 'not_applicable']);
  assert.match(JSON.stringify(report.verification), /never changes these automated counts/u);
  for (const [name, entry] of Object.entries(report.verification.dimensions)) {
    assert.ok(report.verification.states.includes(entry.disposition), name);
    assert.deepEqual(Object.keys(entry.counts).sort(), ['different', 'not_compared', 'same', 'unknown'], name);
  }
});

// 征集提示可能带一个含句号的括注，例如「（正确答案默认设置为A项。）」。
// 这类题位仍须识别为未征集，否则原始提示会漏进正文。
test('a collection notice with a bracketed aside is still recognised as a stub', async () => {
  const { isCollectionStub } = await import('../src/validate.mjs');
  for (const body of [
    '题目正在全力以赴征集，将会第一时间上传（正确答案默认设置为A项）',
    '题目正在全力以赴征集，将会第一时间上传。（正确答案默认设置为A项。）',
    '题目正在全力以赴征集，将会在征集到后第一时间上传',
  ]) assert.equal(isCollectionStub(body), true, body);
  assert.equal(isCollectionStub('题目正在全力以赴征集，将会第一时间上传。请根据材料回答下列问题，并结合实际谈谈你的看法。'), false);
  assert.equal(isCollectionStub('关于文物征集的下列说法，与文意相符的是：' + '甲'.repeat(80)), false);
});
