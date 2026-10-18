import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { loadConfig, normalizeRouteParams, publicUrl, safeChild, urlIsReproducible, urlMatchesObserved, urlRouteLoss, WORK } from '../src/config.mjs';
import { digest, jobKey, readJson, writeJson, acquireLock, resumeBundle } from '../src/store.mjs';
import { MAX_CONCURRENCY, clampConcurrency, createControl, createHostThrottle, createSerialQueue, runBounded } from '../src/schedule.mjs';
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

// ── bounded concurrency for one persistent profile ─────────────────────────────────────────
// Offline only: no browser, no account, no network. These pin the properties that make a second
// page inside the same context safe, and the properties that must stop it.

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('concurrency is clamped to one page minimum and three pages maximum', () => {
  assert.equal(MAX_CONCURRENCY, 3);
  assert.equal(clampConcurrency(1), 1);
  assert.equal(clampConcurrency(2), 2);
  assert.equal(clampConcurrency(MAX_CONCURRENCY), MAX_CONCURRENCY);
  for (const value of [4, 99, 0, -1, 1.5, 'two', null, undefined]) {
    const clamped = clampConcurrency(value);
    assert.ok(clamped >= 1 && clamped <= MAX_CONCURRENCY, `${value} -> ${clamped}`);
  }
  assert.equal(clampConcurrency(4), MAX_CONCURRENCY);
  assert.equal(clampConcurrency('3'), 3);
  assert.equal(clampConcurrency(undefined, 2), 2);
});

test('a configured concurrency above the ceiling is rejected rather than silently honoured', async (t) => {
  const dir = await temporary(t), filename = path.join(dir, 'config.json');
  await writeJson(filename, { concurrency: 2 });
  assert.equal((await loadConfig(filename)).concurrency, 2);
  await writeJson(filename, { concurrency: MAX_CONCURRENCY });
  assert.equal((await loadConfig(filename)).concurrency, MAX_CONCURRENCY);
  for (const bad of [0, -1, MAX_CONCURRENCY + 1, 1.5, 'two']) {
    await writeJson(filename, { concurrency: bad });
    await assert.rejects(loadConfig(filename), /Invalid concurrency/, `concurrency=${bad}`);
  }
  assert.equal((await loadConfig()).concurrency, 2, 'new installations default to two pages in one profile');
});

test('the runner never exceeds its cap, keeps order, and gives each task an exclusive slot', async () => {
  const active = new Set(), duplicated = [], order = [];
  let inFlight = 0, peak = 0;
  const items = [1, 2, 3, 4, 5, 6, 7];
  const run = await runBounded(items, async (item, { slot }) => {
    if (active.has(slot)) duplicated.push(slot);
    active.add(slot); inFlight += 1; peak = Math.max(peak, inFlight);
    await delay(4);
    order.push(item); inFlight -= 1; active.delete(slot);
    return item * 10;
  }, { concurrency: 2 });
  assert.equal(run.concurrency, 2);
  assert.ok(peak <= 2, `peak in flight was ${peak}`);
  assert.deepEqual(duplicated, [], 'a slot must never hold two tasks at once — it owns one page');
  assert.deepEqual(run.results.map((entry) => entry.value), items.map((item) => item * 10));
  assert.equal(run.failures.length, 0);
  assert.deepEqual(run.skipped, []);
  assert.equal(run.stopped, false);
  assert.equal(order.length, items.length);
});

test('concurrency 1 stays strictly sequential, matching the original behaviour', async () => {
  let inFlight = 0, peak = 0;
  await runBounded([1, 2, 3, 4], async () => { inFlight += 1; peak = Math.max(peak, inFlight); await delay(2); inFlight -= 1; }, { concurrency: 1 });
  assert.equal(peak, 1);
});

test('one failing paper never aborts the others, and a stop leaves the rest unstarted', async () => {
  const isolated = await runBounded([1, 2, 3, 4], async (item) => {
    if (item === 2) throw Object.assign(new Error('boom'), { code: 'TASK_FAILED' });
    return item;
  }, { concurrency: 2 });
  assert.equal(isolated.failures.length, 1);
  assert.equal(isolated.failures[0].item, 2);
  assert.deepEqual(isolated.results.map((entry) => entry.ok), [true, false, true, true]);
  assert.deepEqual(isolated.skipped, []);

  for (const reason of ['authentication-required', 'captcha', 'rate-limited']) {
    const control = createControl(), started = [];
    const run = await runBounded([1, 2, 3, 4, 5], async (item) => {
      started.push(item);
      if (item === 2) control.stop(reason);
      await delay(1);
      return item;
    }, { concurrency: 1, control });
    assert.equal(run.stopped, true);
    assert.equal(run.reason, reason);
    assert.deepEqual(started, [1, 2], `${reason} must not launch further papers`);
    assert.deepEqual(run.skipped, [2, 3, 4]);
  }
});

test('one host is spaced by the shared gate and two hosts never block each other', async () => {
  // The gate hands out consecutive time slots, so measure the waits it imposed and the span covered.
  const sleeps = [];
  let clock = 0;
  const throttle = createHostThrottle({ minIntervalMs: 1000, now: () => clock, sleep: async (ms) => { sleeps.push(ms); clock += ms; } });
  await Promise.all([1, 2, 3].map(() => throttle.acquire('tiku.fenbi.com')));
  assert.deepEqual(sleeps, [1000, 1000], 'the second and third caller each wait one interval');
  assert.equal(clock, 2000, 'three callers on one host span two intervals');
  const before = clock, sleepsBefore = sleeps.length;
  await throttle.acquire('img.fbstatic.cn');
  assert.equal(clock, before, 'a different host is not held up by the first host queue');
  assert.equal(sleeps.length, sleepsBefore, 'its first request goes out with no wait at all');
});

test('429 and 503 widen the spacing, saturate the throttle, and decay back after clean reads', () => {
  let clock = 0;
  const throttle = createHostThrottle({ minIntervalMs: 500, maxIntervalMs: 4000, factor: 2, now: () => clock, sleep: async (ms) => { clock += ms; } });
  assert.equal(throttle.saturated(), false);
  assert.deepEqual([1, 2, 3].map((n) => throttle.penalize('tiku.fenbi.com').intervalMs), [1000, 2000, 4000]);
  assert.equal(throttle.penalize('tiku.fenbi.com').intervalMs, 4000, 'the ceiling holds');
  assert.equal(throttle.saturated(), true, 'three penalties on one host stop the run');
  assert.equal(throttle.state().hosts['tiku.fenbi.com'].penalties, 4);
  assert.equal(throttle.settle('tiku.fenbi.com'), 2000);
  assert.equal(throttle.settle('tiku.fenbi.com'), 1000);
  assert.equal(throttle.settle('tiku.fenbi.com'), 500);
  assert.equal(throttle.saturated(), false, 'a recovered host is no longer saturated');
  assert.equal(throttle.settle('tiku.fenbi.com'), null, 'settling an already-clean host is a no-op');
});

test('the shared registry is written one task at a time, so simultaneous pages cannot lose an update', async (t) => {
  const url1 = 'https://tiku.fenbi.com/api/xingce/exercises/1/questions';
  const url2 = 'https://tiku.fenbi.com/api/xingce/exercises/2/questions';
  const events = [];

  // Without the queue the two writes overlap — this is the regression being guarded against.
  await Promise.all([1, 2].map(async (n) => { events.push(`raw-start${n}`); await delay(5); events.push(`raw-end${n}`); }));
  assert.deepEqual(events, ['raw-start1', 'raw-start2', 'raw-end1', 'raw-end2']);
  events.length = 0;

  const dir = await temporary(t);
  const filename = path.join(dir, 'observed-reads-fenbi-main.json');
  const registry = new Set(['https://tiku.fenbi.com/api/xingce/papers?labelId=1']);
  const serialize = createSerialQueue();
  const write = () => serialize(async () => {
    events.push('write-start'); await delay(5);
    await writeJson(filename, { schemaVersion: 2, profileName: 'fenbi-main', urls: [...registry] });
    events.push('write-end');
  });
  await Promise.all([
    (async () => { registry.add(url1); await write(); })(),
    (async () => { registry.add(url2); await write(); })(),
  ]);
  assert.deepEqual(events, ['write-start', 'write-end', 'write-start', 'write-end'], 'writes are serialised');
  const saved = await readJson(filename, null);
  assert.equal(saved.schemaVersion, 2);
  assert.equal(saved.urls.length, 3);
  assert.deepEqual([...saved.urls].sort(), ['https://tiku.fenbi.com/api/xingce/papers?labelId=1', url1, url2].sort());
});

test('a rejected concurrency flag cannot open more pages than the ceiling', async () => {
  // The CLI clamps rather than trusting the flag; the ceiling is the same constant config enforces.
  for (const flag of ['2', '3', '4', '99', '0', 'abc']) {
    const clamped = clampConcurrency(flag);
    assert.ok(clamped >= 1 && clamped <= MAX_CONCURRENCY, `--concurrency ${flag} -> ${clamped}`);
  }
  assert.equal(clampConcurrency('99'), MAX_CONCURRENCY);
});

// ── navigation targets must be reproducible, or refused ─────────────────────────────────────
// The driver navigates to a normalised URL. If normalising drops part of the route, the browser
// lands somewhere the framework never observed. That must be refused, never silently rewritten.

test('an in-app fragment route survives while credential fragments are still dropped', () => {
  assert.equal(publicUrl('https://www.fenbi.com/spa/tiku#/exam/8399763'), 'https://www.fenbi.com/spa/tiku#/exam/8399763');
  assert.ok(urlIsReproducible('https://www.fenbi.com/spa/tiku#/exam/8399763'));
  assert.equal(publicUrl('https://www.fenbi.com/spa/tiku#/exam/8399763?paperId=8399763&token=SYNTHETIC_PRIVATE_VALUE'),
    'https://www.fenbi.com/spa/tiku#/exam/8399763?paperId=8399763');
  // The pre-existing privacy behaviour is untouched: a fragment that is not an in-app route is dropped.
  assert.equal(publicUrl('https://www.fenbi.com/spa/tiku#access_token=SYNTHETIC_PRIVATE_VALUE'), 'https://www.fenbi.com/spa/tiku');
  assert.equal(urlRouteLoss('https://www.fenbi.com/spa/tiku#access_token=SYNTHETIC_PRIVATE_VALUE').hash, true);
  assert.equal(urlIsReproducible('https://www.fenbi.com/spa/tiku#access_token=SYNTHETIC_PRIVATE_VALUE'), false);
  for (const value of ['https://www.fenbi.com/spa/tiku#//evil.invalid', 'https://www.fenbi.com/spa/tiku#/a b']) {
    assert.equal(publicUrl(value), 'https://www.fenbi.com/spa/tiku', value);
  }
});

test('a dropped non-credential parameter is a route loss; a dropped credential is not', () => {
  const unknown = urlRouteLoss('https://www.fenbi.com/spa/tiku?route=exam&paperId=8399763');
  assert.deepEqual(unknown.routeParams, ['route']);
  assert.deepEqual(unknown.secretParams, []);
  assert.equal(urlIsReproducible('https://www.fenbi.com/spa/tiku?route=exam&paperId=8399763'), false);

  const credential = urlRouteLoss('https://www.fenbi.com/spa/tiku?labelId=3&token=SYNTHETIC_PRIVATE_VALUE');
  assert.deepEqual(credential.routeParams, []);
  assert.deepEqual(credential.secretParams, ['token']);
  assert.ok(urlIsReproducible('https://www.fenbi.com/spa/tiku?labelId=3&token=SYNTHETIC_PRIVATE_VALUE'));
});

test('the page-URL and navigation-URL allowlists disagreeing is reported as a route loss', () => {
  // safePageUrl (browser) keeps provinceId/year; publicUrl (config) does not. A job built from such
  // a link would otherwise navigate to a URL that differs from the one actually observed.
  const value = 'https://www.fenbi.com/spa/tiku?provinceId=32&year=2026';
  assert.equal(urlIsReproducible(value), false);
  assert.deepEqual(urlRouteLoss(value).routeParams.sort(), ['provinceId', 'year']);
});

test('a planned job built from an unreproducible link is never marked ready', () => {
  const scope = { fromYear: 2016, toYear: 2026, areas: ['江苏'] };
  const bad = makePlan({ labels: [], papers: [{ id: 'p1', title: '2025江苏行测C类', subject: 'xingce', url: 'https://www.fenbi.com/spa/tiku?provinceId=32&year=2025' }] }, [], scope);
  assert.equal(bad.jobs.length, 1);
  assert.equal(bad.jobs[0].status, 'needs_route_review');
  assert.equal(bad.jobs[0].reason, 'observed_url_not_reproducible');
  assert.equal(bad.jobs[0].url, null);
  assert.equal(bad.jobs[0].identity.variant, 'C类', 'identity is still reported; only the URL is refused');
  const good = makePlan({ labels: [], papers: [{ id: 'p1', title: '2025江苏行测C类', subject: 'xingce', url: 'https://www.fenbi.com/spa/tiku?labelId=3' }] }, [], scope);
  assert.equal(good.jobs[0].status, 'ready');
});

// ── shared-state negative tests ─────────────────────────────────────────────────────────────

test('without the serial queue a concurrent registration is genuinely lost', async (t) => {
  const dir = await temporary(t), filename = path.join(dir, 'observed-reads-fenbi-main.json');
  await writeJson(filename, { schemaVersion: 2, profileName: 'fenbi-main', urls: [] });
  // Each page reads the file, then writes the whole document back. Interleaved, the second write is
  // built from a snapshot read before the first landed, so one registration vanishes.
  const losingWrite = async (url) => {
    const current = await readJson(filename, { urls: [] });
    await delay(5);
    await writeJson(filename, { schemaVersion: 2, profileName: 'fenbi-main', urls: [...current.urls, url] });
  };
  const first = 'https://tiku.fenbi.com/api/xingce/exercises/1/questions';
  const second = 'https://tiku.fenbi.com/api/xingce/exercises/2/questions';
  await Promise.all([losingWrite(first), losingWrite(second)]);
  const saved = await readJson(filename, null);
  assert.equal(saved.urls.length, 1, 'the later write overwrote the earlier registration');
  assert.ok(!(saved.urls.includes(first) && saved.urls.includes(second)), 'this is the race the queue prevents');
});

test('one profile name cannot reach another profile directory or registry file', async (t) => {
  const dir = await temporary(t), filename = path.join(dir, 'config.json');
  await writeJson(filename, { profileName: 'fenbi-main' });
  const first = await loadConfig(filename);
  await writeJson(filename, { profileName: 'fenbi-second' });
  const second = await loadConfig(filename);
  assert.notEqual(first.profileDir, second.profileDir);
  assert.ok(first.profileDir.endsWith(path.join('profiles', 'fenbi-main')));
  assert.ok(second.profileDir.endsWith(path.join('profiles', 'fenbi-second')));
  for (const bad of ['../escape', 'a/b', 'a\\b', '', 'a'.repeat(60)]) {
    await writeJson(filename, { profileName: bad });
    await assert.rejects(loadConfig(filename), /Invalid profileName/, `profileName=${bad}`);
  }
});

// ── an observed route parameter must survive, but only when it is declared and safe ──────────
// A real practice URL carries a route query parameter this framework does not know (`routecs`).
// Dropping it changes where the browser lands; accepting anything unlisted would turn the allowlist
// into a hole. The rule is: declare it explicitly, keep it only if it is a bare identifier with a
// short opaque value, and compare the observed URL with the normalised one in both directions.

const ROUTE_URL = 'https://www.fenbi.com/spa/tiku/exercise/12345?routecs=SYNTHETIC_ROUTE_VALUE&paperId=8399763';

test('a declared route parameter survives; an undeclared one still means the URL is not reproducible', () => {
  assert.equal(urlIsReproducible(ROUTE_URL), false, 'undeclared route parameter → needs_route_review');
  assert.deepEqual(urlRouteLoss(ROUTE_URL).routeParams, ['routecs']);
  assert.equal(urlIsReproducible(ROUTE_URL, ['routecs']), true);
  assert.equal(publicUrl(ROUTE_URL, ['routecs']),
    'https://www.fenbi.com/spa/tiku/exercise/12345?routecs=SYNTHETIC_ROUTE_VALUE&paperId=8399763');
  assert.deepEqual(urlRouteLoss(ROUTE_URL, ['routecs']).routeParams, []);
  // Declaring a different name does not help.
  assert.equal(urlIsReproducible(ROUTE_URL, ['nav']), false);
});

test('a credential-shaped name is never accepted, even when declared', () => {
  assert.deepEqual(normalizeRouteParams(['routecs', 'token', 'session', 'auth', 'cookie', 'a b', '']), ['routecs']);
  // `token` is dropped from the URL even though the operator listed it.
  assert.equal(publicUrl(`${ROUTE_URL}&token=SYNTHETIC_PRIVATE_VALUE`, ['routecs', 'token']),
    'https://www.fenbi.com/spa/tiku/exercise/12345?routecs=SYNTHETIC_ROUTE_VALUE&paperId=8399763');
  assert.ok(!publicUrl(`${ROUTE_URL}&token=SYNTHETIC_PRIVATE_VALUE`, ['routecs', 'token']).includes('SYNTHETIC_PRIVATE_VALUE'));
});

test('a declared route parameter still cannot smuggle a long or structured value', () => {
  const base = 'https://www.fenbi.com/spa/tiku/exercise/1';
  for (const value of ['a'.repeat(300), 'https://evil.invalid/x', 'a%20b', 'a=b', 'a&b', 'a/b']) {
    const url = `${base}?routecs=${encodeURIComponent(value)}`;
    assert.equal(urlIsReproducible(url, ['routecs']), false, value.slice(0, 20));
  }
  // An empty route value is a faithful reproduction, not a security question.
  assert.equal(publicUrl(`${base}?routecs=`, ['routecs']), `${base}?routecs=`);
});

test('the observed/normalised comparison is bidirectional and rejects injection', () => {
  const observed = 'https://www.fenbi.com/spa/tiku/exercise/1?paperId=8399763';
  assert.equal(urlMatchesObserved(observed, 'https://www.fenbi.com/spa/tiku/exercise/1?paperId=8399763'), true);
  assert.equal(urlMatchesObserved(observed, 'https://www.fenbi.com/spa/tiku/exercise/1?paperId=8399763&routecs=x'), false,
    'the normalised URL may not gain a parameter the observation never had');
  assert.equal(urlMatchesObserved(observed, 'https://www.fenbi.com/spa/tiku/exercise/2?paperId=8399763'), false, 'path change');
  assert.equal(urlMatchesObserved(observed, 'https://evil.invalid/spa/tiku/exercise/1?paperId=8399763'), false, 'origin change');
  assert.equal(urlMatchesObserved(`${observed}&token=SYNTHETIC_PRIVATE_VALUE`, observed), true,
    'a deliberately stripped credential is not a mismatch');
});

test('routeParams is validated by config: identifier-shaped, credential-free, short, unique', async (t) => {
  const dir = await temporary(t), filename = path.join(dir, 'config.json');
  await writeJson(filename, { routeParams: ['routecs'] });
  assert.deepEqual((await loadConfig(filename)).routeParams, ['routecs']);
  assert.deepEqual((await loadConfig()).routeParams, [], 'empty by default — nothing is accepted implicitly');
  for (const bad of [['token'], ['routecs', 'routecs'], ['a b'], ['1abc'], [''], 'routecs', Array.from({ length: 9 }, (_v, i) => `p${i}`)]) {
    await writeJson(filename, { routeParams: bad });
    await assert.rejects(loadConfig(filename), /Invalid routeParams/, JSON.stringify(bad));
  }
});

test('a planned job becomes ready only when its observed URL is reproducible under the declared set', () => {
  const scope = { fromYear: 2016, toYear: 2026, areas: ['江苏'] };
  const catalog = { labels: [], papers: [{ id: 'p1', title: '2025江苏行测C类', subject: 'xingce',
    url: 'https://www.fenbi.com/spa/tiku/exercise/12345?routecs=SYNTHETIC_ROUTE_VALUE' }] };
  const blocked = makePlan(catalog, [], scope);
  assert.equal(blocked.jobs[0].status, 'needs_route_review');
  assert.equal(blocked.jobs[0].reason, 'observed_url_not_reproducible');

  const allowed = makePlan(catalog, [], { ...scope, }, { routeParams: ['routecs'] });
  assert.equal(allowed.jobs[0].status, 'ready');
  assert.equal(allowed.jobs[0].url, 'https://www.fenbi.com/spa/tiku/exercise/12345?routecs=SYNTHETIC_ROUTE_VALUE');
});

test('two concurrent papers keep their own route: a slot never sees the other job\'s target', async () => {
  const jobs = [
    { id: 'js2025c', url: 'https://www.fenbi.com/spa/tiku/exercise/111?routecs=ROUTE_ONE' },
    { id: 'zj2026c', url: 'https://www.fenbi.com/spa/tiku/exercise/222?routecs=ROUTE_TWO' },
  ];
  const seen = [];
  const run = await runBounded(jobs, async (job, { slot }) => {
    const target = publicUrl(job.url, ['routecs']);
    seen.push({ slot, id: job.id, target });
    await delay(2);
    return target;
  }, { concurrency: 2 });
  assert.equal(run.failures.length, 0);
  for (const job of jobs) {
    const row = seen.find((entry) => entry.id === job.id);
    assert.ok(row.target.includes(job.url.split('routecs=')[1]), `${job.id} kept its own route`);
    assert.equal(publicUrl(job.url, ['routecs']), row.target);
  }
  assert.notEqual(seen[0].target, seen[1].target);
  assert.equal(new Set(seen.map((entry) => entry.slot)).size, 2, 'each task held its own slot');
});
