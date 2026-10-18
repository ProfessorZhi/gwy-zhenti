// Independent release-gate probe. Deliberately does NOT reuse the repository's own test
// assertions: it re-derives each behaviour from the merged release-candidate source, so a
// PR that merely asserts its own correctness cannot make this pass.
//
// Run: node tools-audit/release_gate_probe.mjs <path-to-rc>/tools/fenbi/src
import assert from 'node:assert/strict';

const SRC = process.argv[2];
if (!SRC) { console.error('usage: node release_gate_probe.mjs <.../tools/fenbi/src>'); process.exit(2); }

const { isCollectionStub, validateDocument, paperProvenance } = await import(`${SRC}/validate.mjs`);
const { comparePaper, normalizeComparisonText } = await import(`${SRC}/align.mjs`);
const { requestPolicy } = await import(`${SRC}/browser.mjs`);
const { createDocument, absorbPayload } = await import(`${SRC}/model.mjs`);

let pass = 0, fail = 0;
const check = (name, fn) => {
  try { fn(); pass++; console.log(`  PASS  ${name}`); }
  catch (e) { fail++; console.log(`  FAIL  ${name}\n          ${String(e.message).split('\n')[0]}`); }
};

// ── 1. collection stub detection: true positives AND false-positive guard ──
console.log('\n[1] collection-stub classifier');
const STUBS = [
  '题目正在全力以赴征集',
  '题目正在全力以赴征集，将会第一时间上传',
  '题目正在全力以赴征集，将会在征集到后第一时间上传',
  '正在搜集中',
  '本题暂无收集到',
  '网友未回忆起',
  '题目缺失',
  '非客观题，请交卷后查看参考解析估分',
  '题目正在全力以赴征集，请稍后再试',
];
for (const s of STUBS) check(`stub detected: ${s.slice(0, 18)}…`, () => assert.equal(isCollectionStub(s), true));

const GENUINE = [
  '关于网友未回忆起的内容，下列说法正确的是：',
  '材料中提到的"正在搜集中"指的是该平台的哪一项业务？',
  '题目正在全力以赴征集，这是命题组的工作节奏，而考生需要做的是把握已有材料。'.repeat(2),
  '本题暂无收集到的数据需要考生根据表格推算。',
];
for (const s of GENUINE) check(`genuine stem NOT flagged: ${s.slice(0, 18)}…`, () => assert.equal(isCollectionStub(s), false));
check('empty/null not flagged', () => { assert.equal(isCollectionStub(''), false); assert.equal(isCollectionStub(null), false); });

// ── 2. validator gate ──
console.log('\n[2] validateDocument rejects a stub as content');
const fixture = (stem) => {
  const doc = createDocument({ id: 'paper', subject: 'xingce' }, { url: 'https://www.fenbi.com/spa/tiku' });
  absorbPayload(doc, { paperId: 'paper', questionCount: 1, materialCount: 0, questions: [
    { id: 'q-1', number: 1, content: stem, options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }] }] });
  return doc;
};
const stubRes = await validateDocument(fixture('题目正在全力以赴征集'));
check('stub stem produces question-body-placeholder', () =>
  assert.ok(stubRes.issues.some((i) => i.code === 'question-body-placeholder')));
check('stub stem never yields status complete', () => assert.notEqual(stubRes.status, 'complete'));
const realRes = await validateDocument(fixture('甲与乙相比，哪一个更符合题意？'));
check('genuine stem is not flagged as placeholder', () =>
  assert.ok(!realRes.issues.some((i) => i.code === 'question-body-placeholder')));

// ── 3. THE PR#33 REGRESSION: source stub must be `unknown`, never `different` ──
console.log('\n[3] PR#33 regression: source stub is unknown, not "content differs"');
const mdFor = (content, qid = '101') =>
  `## 第 1 题 <sub>qid ${qid} · 计算</sub>\n\n${content}\n\n- **A**. 5\n- **B**. 6\n\n## 答案与解析\n` +
  `<details>\n<summary>第 1 题</summary>\n\n**答案**：A\n\n**来源参考解析（非官方标准答案）**\n\n相加得5。\n\n---\n</details>\n`;
const srcDoc = (contentHtml, extra = {}) => {
  const doc = createDocument({ id: 'paper', subject: 'xingce' }, { url: 'https://www.fenbi.com/spa/tiku' });
  doc.questions = [{ id: '101', number: 1, contentHtml,
    options: [{ label: 'A', contentHtml: '5' }, { label: 'B', contentHtml: '6' }], materialIds: [], ...extra }];
  doc.expected.questions = 1;
  return doc;
};
const rep = await comparePaper(srcDoc('题目正在全力以赴征集'), mdFor('当 x ≥ 10 时，求 2 + 3。'));
const dim = rep.questions[0]?.dimensions?.stem;
check('matched by qid despite stub source', () => assert.equal(rep.questions[0]?.matchMethod, 'qid'));
check('stem status is unknown (NOT different)', () => assert.equal(dim.status, 'unknown'));
check('reason names the collection placeholder', () => assert.match(String(dim.reason), /collection-placeholder/));

// repo holding a stub must not be silently equal either
const rep2 = await comparePaper(srcDoc('当 x ≥ 10 时，求 2 + 3。'), mdFor('题目正在全力以赴征集'));
check('repo stub is never "same"', () => assert.notEqual(rep2.questions[0]?.dimensions?.stem?.status, 'same'));

// ── 4. unobserved answers/explanations stay unknown ──
console.log('\n[4] unobserved answer/explanation never become `same`');
const noAns = await comparePaper(srcDoc('当 x ≥ 10 时，求 2 + 3。', { answerHtml: null, explanationHtml: null }),
  mdFor('当 x ≥ 10 时，求 2 + 3。'));
check('answer unknown when source did not expose it', () => assert.equal(noAns.questions[0].dimensions.answer.status, 'unknown'));
check('explanation unknown when source did not expose it', () => assert.equal(noAns.questions[0].dimensions.explanation.status, 'unknown'));
check('paper verdict is not verified while answers unknown', () => assert.notEqual(noAns.verification?.verdict, 'verified'));

// ── 5. GET protection ──
console.log('\n[5] request policy blocks writes');
// requestPolicy returns null when allowed and a reason-code STRING when blocked.
const pol = (o, mode = 'capture') => requestPolicy(o, mode);
check('GET to tiku API allowed', () => assert.equal(pol({ url: 'https://tiku.fenbi.com/api/xingce/papers/v2?labelId=31', method: 'GET' }), null));
check('POST to exercises blocked in capture mode', () => assert.equal(pol({ url: 'https://tiku.fenbi.com/api/xingce/exercises', method: 'POST' }), 'blockedWrites'));
check('POST to analytics beacon blocked', () => assert.equal(pol({ url: 'https://data-api.fenbi.com/sa.gif', method: 'POST' }), 'blockedWrites'));
check('PUT/DELETE blocked', () => { assert.equal(pol({ url: 'https://tiku.fenbi.com/api/x', method: 'PUT' }), 'blockedWrites'); assert.equal(pol({ url: 'https://tiku.fenbi.com/api/x', method: 'DELETE' }), 'blockedWrites'); });
check('off-domain navigation blocked', () => assert.equal(pol({ url: 'https://evil.example.com/', method: 'GET', navigation: true }), 'blockedNavigation'));
check('login mode still blocks non-auth writes', () => assert.equal(pol({ url: 'https://tiku.fenbi.com/api/xingce/exercises', method: 'POST' }, 'login'), 'blockedWrites'));
check('credentials in URL blocked', () => assert.equal(pol({ url: 'https://user:pw@tiku.fenbi.com/api/x', method: 'GET' }), 'blockedUrl'));
check('plain http blocked', () => assert.equal(pol({ url: 'http://tiku.fenbi.com/api/x', method: 'GET' }), 'blockedUrl'));

console.log(`\n=== independent probe: ${pass} passed, ${fail} failed ===`);
process.exit(fail === 0 ? 0 : 1);
