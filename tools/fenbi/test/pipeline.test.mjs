import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { loadConfig, publicUrl, safeChild, WORK } from '../src/config.mjs';
import { digest, jobKey, writeJson, acquireLock, resumeBundle } from '../src/store.mjs';
import { makePlan } from '../src/plan.mjs';
import { createDocument, absorbPayload } from '../src/model.mjs';
import { validateDocument } from '../src/validate.mjs';
import { markdown, renderCandidate, exportCandidate } from '../src/render.mjs';
import { observedReadUrl, replayReads } from '../src/reads.mjs';
import { sanitizeHtml } from '../src/privacy.mjs';
import { normalizeCatalogPayload, mergeCatalog } from '../src/catalog.mjs';

async function temporary(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-test-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  return dir;
}
function complete() {
  const doc = createDocument({ id: 'fixture', title: '2025江苏行测C类（合成测试）', subject: 'xingce', year: 2025, area: '江苏', variant: 'C类' }, { url: 'https://www.fenbi.com/spa/tiku/fixture' });
  absorbPayload(doc, { paperId: 'fixture', questionCount: 1, materialCount: 0, questions: [{ id: 'q1', number: 1, content: '离线合成题干', options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }], answer: 'B', analysis: '这是离线合成解析。' }] });
  return doc;
}

test('configuration isolates private output, rejects typos and preserves only safe page parameters', async t => {
  const config = await loadConfig();
  assert.ok(config.profileDir.startsWith(WORK + path.sep));
  assert.equal(publicUrl('https://www.fenbi.com/spa/tiku?labelId=3&token=not-a-real-token'), 'https://www.fenbi.com/spa/tiku?labelId=3');
  assert.equal(publicUrl('https://www.fenbi.com/spa/tiku#access_token=not-a-real-token'), 'https://www.fenbi.com/spa/tiku');
  for (const value of ['https://fenbi.com.evil.test/', 'http://www.fenbi.com/', 'https://user:pass@www.fenbi.com/']) assert.throws(() => publicUrl(value));
  for (const value of ['../formal.md', '/absolute', '..\\..\\formal.md']) {
    if (process.platform === 'win32' || !value.includes('\\')) assert.throws(() => safeChild(WORK, value));
  }
  const dir = await temporary(t), filename = path.join(dir, 'config.json');
  await writeJson(filename, { profleName: 'typo' });
  await assert.rejects(loadConfig(filename), /Unknown configuration/);
});

test('sensitive image links, pending explanations and HTML account controls never persist credential values', async () => {
  const secret = 'SYNTHETIC_PRIVATE_QUERY_VALUE';
  const html = `<img src="https://img.fbstatic.cn/a.png?token=${secret}"><a href="https://www.fenbi.com/?auth=${secret}">参考</a><input value="${secret}">`;
  const clean = sanitizeHtml(html);
  assert.ok(!clean.html.includes(secret)); assert.ok(clean.rejected > 0);
  const doc = complete(); doc.questions[0].contentHtml = '';
  absorbPayload(doc, { paperId: 'fixture', questions: [{ id: 'q1', content: html }] });
  absorbPayload(doc, { answers: [{ questionId: 'not-yet-seen', analysis: html }] });
  assert.ok(!JSON.stringify(doc).includes(secret));
  assert.notEqual((await validateDocument(doc)).status, 'complete');
});

test('work lock prevents competing collectors and never removes another owner', async t => {
  const dir = await temporary(t), release = await acquireLock(dir);
  await assert.rejects(acquireLock(dir), /Another capture/);
  await writeJson(path.join(dir, '.capture.lock'), { marker: 'another-owner' });
  await release();
  assert.equal(JSON.parse(await fs.readFile(path.join(dir, '.capture.lock'))).marker, 'another-owner');
});

test('planning keeps Guangzhou distinct from Guangdong and excludes unidentified or out-of-scope entries', () => {
  const catalog = { labels: [], papers: [
    { id: 'g', title: '2017广州行测统考', subject: 'xingce' },
    { id: 'j', title: '2025江苏行测C类', subject: 'xingce' },
    { id: 'old', title: '2015浙江行测A类', subject: 'xingce' },
    { id: 'unknown', title: '未知试卷', subject: 'xingce' },
  ] };
  const inventory = [
    { area: '广东', year: '2017', subject: '行测', paper_type: '统考', path: '省考/广东/2017/行测-统考.md' },
    { area: '江苏', year: '2025', subject: '行测', paper_type: 'C类', path: '省考/江苏/2025/行测-C类.md', missing_original_numbers: [] },
  ];
  const plan = makePlan(catalog, inventory, { fromYear: 2016, toYear: 2026, areas: ['广州', '江苏', '浙江'] });
  assert.equal(plan.jobs.length, 1); assert.equal(plan.jobs[0].identity.area, '广州');
  assert.deepEqual(plan.jobs[0].repositoryMatches, []); assert.equal(plan.excluded.length, 1);
  assert.equal(plan.catalogComplete, false);
});

test('authenticated v2 catalog and nested labels preserve declared coverage without confusing exercise count with question count', () => {
  const catalog = { papers: [], labels: [] };
  mergeCatalog(catalog, normalizeCatalogPayload({ pageInfo: { totalItem: 36, totalPage: 3, currentPage: 0, pageSize: 15 },
    list: [{ id: 7, name: '2025年江苏行测C类', paperMeta: { exerciseCount: 999999 }, encodeCheckInfo: 'SYNTHETIC_PRIVATE_FIELD' }] },
  { url: 'https://tiku.fenbi.com/api/xingce/papers/v2?labelId=1&toPage=0&pageSize=15', subject: 'xingce' }));
  assert.equal(catalog.papers.length, 1); assert.equal(catalog.papers[0].questionCount, null);
  assert.equal(catalog.pages[0].totalItems, 36);
  assert.ok(!JSON.stringify(catalog).includes('SYNTHETIC_PRIVATE_FIELD'));
  const labels = normalizeCatalogPayload([{ id: 1, name: '江苏', labelMeta: { paperCount: 2, paperIds: [7, 8] }, childrenLabels: [{ id: 2, name: '江苏C类', labelMeta: { paperCount: 1, paperIds: [7] } }] }],
    { url: 'https://tiku.fenbi.com/api/xingce/subLabels', subject: 'xingce' });
  assert.equal(labels.labels.length, 2); assert.equal(String(labels.labels[1].parentId), '1');
  assert.deepEqual(labels.labels[0].declaredPaperIds, ['7', '8']);
});

test('mock and institution practice papers never become real-paper gap targets', () => {
  const plan = makePlan({ labels: [], papers: [{ id: 1, title: '2026江苏行测C类模拟卷', subject: 'xingce' }] }, [], { fromYear: 2016, toYear: 2026, areas: ['江苏'] });
  assert.equal(plan.jobs.length, 0); assert.equal(plan.excluded.length, 1);
});

test('resume revalidates exact document bytes, job expectations and assets', async t => {
  const dir = await temporary(t), doc = complete();
  const job = { identity: doc.identity, url: doc.source.url, expected: doc.expected };
  const bundle = path.join(dir, 'papers', jobKey(job));
  await fs.mkdir(path.join(bundle, 'assets'), { recursive: true });
  await writeJson(path.join(bundle, 'document.json'), doc);
  const checkpoint = { status: 'complete', configFingerprint: 'cfg', jobFingerprint: digest(job), documentFile: 'document.json', sha256: digest(await fs.readFile(path.join(bundle, 'document.json'))) };
  await writeJson(path.join(bundle, 'checkpoint.json'), checkpoint);
  assert.ok(await resumeBundle(dir, job, 'cfg', validateDocument));
  assert.equal(await resumeBundle(dir, job, 'changed', validateDocument), null);
  assert.equal(await resumeBundle(dir, { ...job, expected: { questions: 2 } }, 'cfg', validateDocument), null);
  await fs.appendFile(path.join(bundle, 'document.json'), ' ');
  assert.equal(await resumeBundle(dir, job, 'cfg', validateDocument), null);
});

test('Markdown preserves long text, tables, MathML, formula markup and local image variants', () => {
  const body = '材料不能截断。'.repeat(2000);
  const assets = [{ url: 'https://www.fenbi.com/a.png', localPath: 'a.png', status: 'downloaded' }];
  const result = markdown(`<p>${body}</p><table><tr><th>年份</th><th>数值</th></tr><tr><td>2025</td><td>42</td></tr></table><math><mi>x</mi></math><span data-latex="x^2">x²</span><img src="/a.png"><svg><image href="/a.png"/></svg>`, assets);
  assert.ok(result.includes(body)); assert.ok(result.includes('| 年份 | 数值 |'));
  assert.ok(result.includes('<math>')); assert.ok(result.includes('$x^2$'));
  assert.ok(result.includes('assets/a.png')); assert.ok(result.includes('<svg>'));
  assert.ok(!result.includes('https://www.fenbi.com/a.png'));
});

test('candidate renderer orders source question numbers and keeps answers folded', async () => {
  const doc = complete();
  doc.questions.push({ ...doc.questions[0], id: 'q2', number: 2 });
  doc.questions.reverse(); doc.expected.questions = 2;
  const verdict = await validateDocument(doc);
  const result = renderCandidate(doc, verdict);
  assert.ok(result.indexOf('### 第 1 题') < result.indexOf('### 第 2 题'));
  assert.ok(result.indexOf('## 答案与解析') < result.indexOf('<details><summary>第 1 题'));
  assert.throws(() => renderCandidate(doc, { status: 'partial' }), /validated complete/);
});

test('source chapter instructions survive candidate rendering instead of disappearing after extraction', async () => {
  const doc = complete();
  doc.chapters = [{ title: '合成章节', questionCount: 1, instructionsHtml: '<p>合成章节（1题）根据材料选择唯一答案。</p>' }];
  const output = renderCandidate(doc, await validateDocument(doc));
  assert.ok(output.includes('## 题型与作答说明'));
  assert.ok(output.includes('根据材料选择唯一答案。'));
});

test('candidate exports never overwrite a prior candidate and partial papers never export', async t => {
  const dir = await temporary(t), doc = complete(), verdict = await validateDocument(doc);
  const destination = path.join(dir, 'candidate');
  await exportCandidate(doc, verdict, dir, destination);
  await assert.rejects(exportCandidate(doc, verdict, dir, destination));
  assert.ok((await fs.readFile(path.join(destination, 'paper.md'), 'utf8')).includes('候选采集稿'));
  await assert.rejects(exportCandidate(doc, { status: 'partial' }, dir, path.join(dir, 'partial')), /validated complete/);
});

test('direct JSON reads require a previously observed safe URL and retain current context cookies', async () => {
  const url = 'https://tiku.fenbi.com/api/xingce/exercises/123/questions';
  const calls = [], received = [];
  const context = { request: { get: async (actual, options) => {
    calls.push({ actual, options });
    return { status: () => 200, headers: () => ({ 'content-type': 'application/json' }), body: async () => Buffer.from('{"questions":[]}'), dispose: async () => {} };
  } } };
  await assert.rejects(replayReads(context, [url], [], () => {}), /not observed/);
  const result = await replayReads(context, [url], [url], (body, meta) => received.push({ body, meta }), { sleep: async () => {} });
  assert.equal(result[0].outcome, 'accepted'); assert.equal(received[0].meta.subject, 'xingce');
  assert.equal(calls[0].options.maxRedirects, 0);
  for (const invalid of ['https://evil.test/api/xingce/questions', `${url}?token=not-a-real-token`, 'https://tiku.fenbi.com/api/xingce/exercises', 'https://tiku.fenbi.com/api/xingce/user/history']) assert.throws(() => observedReadUrl(invalid));
});

test('HTTP login errors, HTML envelopes, oversized JSON and captcha cannot count as successful direct reads', async () => {
  const url = 'https://tiku.fenbi.com/api/shenlun/papers';
  for (const [status, headers, bytes, expected] of [
    [401, { 'content-type': 'application/json' }, '{}', 'http_error'],
    [200, { 'content-type': 'text/html' }, '<html>登录</html>', 'non_json'],
    [200, { 'content-type': 'application/json', 'content-length': '9000000' }, '{}', 'oversized'],
    [200, { 'content-type': 'application/json' }, '{"msg":"验证码"}', 'captcha'],
  ]) {
    const context = { request: { get: async () => ({ status: () => status, headers: () => headers, body: async () => Buffer.from(bytes), dispose: async () => {} }) } };
    const result = await replayReads(context, [url], [url], () => assert.fail('must not accept'), { sleep: async () => {} });
    assert.equal(result[0].outcome, expected);
  }
});
