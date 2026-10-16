import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mkdtemp, readFile, rm, access, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { openSession, requestPolicy, observeReadResponses, captureDom, downloadAssets } from '../src/browser.mjs';
import { parseFenbiExamDom } from '../src/dom.mjs';
import { sanitizeHtml } from '../src/privacy.mjs';

test('capture guard blocks writes, external navigation, HTTP and deceptive hosts', () => {
  assert.equal(requestPolicy({ url: 'https://tiku.fenbi.com/api/xingce/papers', method: 'GET' }), null);
  assert.equal(requestPolicy({ url: 'https://tiku.fenbi.com/api/xingce/exercises', method: 'POST' }), 'blockedWrites');
  assert.equal(requestPolicy({ url: 'https://login.fenbi.com/api/users/login', method: 'POST' }), 'blockedWrites');
  assert.equal(requestPolicy({ url: 'https://login.fenbi.com/api/users/login', method: 'POST' }, 'login'), null);
  assert.equal(requestPolicy({ url: 'https://tiku.fenbi.com/api/xingce/exercises', method: 'POST' }, 'login'), 'blockedWrites');
  assert.equal(requestPolicy({ url: 'https://img.fbstatic.cn/test.png', navigation: true }), 'blockedNavigation');
  assert.equal(requestPolicy({ url: 'https://fenbi.com.evil.invalid/test' }), 'blockedHost');
  assert.equal(requestPolicy({ url: 'http://www.fenbi.com/' }), 'blockedUrl');
  assert.equal(requestPolicy({ url: 'https://fb.fenbike.cn/api/tarzan/images/fixture.png?width=700' }), null);
  assert.equal(requestPolicy({ url: 'https://fb.fenbike.cn/api/planet/accessories/formulas?fontSize=18&latex=synthetic-formula' }), null);
  assert.equal(requestPolicy({ url: 'https://fb.fenbike.cn/api/tarzan/images/fixture.png', navigation: true }), 'blockedNavigation');
  assert.equal(requestPolicy({ url: 'https://fb.fenbike.cn/unknown' }), 'blockedHost');
  assert.equal(requestPolicy({ url: 'https://evil.fenbike.cn/api/tarzan/images/a.png' }), 'blockedHost');
});

function response(url, payload, { status = 200, method = 'GET', length, type = 'application/json' } = {}) {
  return { url: () => url, request: () => ({ method: () => method }), status: () => status,
    headers: () => ({ 'content-type': type, ...(length ? { 'content-length': String(length) } : {}) }),
    body: async () => Buffer.from(JSON.stringify(payload)) };
}

test('response observer filters account data, strips secret query and refuses truncation', async () => {
  const page = new EventEmitter();
  const received = [];
  const observer = observeReadResponses(page, async (payload, meta) => { received.push({ payload, meta }); }, { maxResponseBytes: 200 });
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/papers?labelId=1&token=secret', { papers: [{ id: 7 }] }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/users/info', { phone: 'private' }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/userCollectNoteError', { private: true }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/category-exercises-unfinished', { private: true }));
  page.emit('response', response('https://tiku.fenbi.com/api/shenlun/papers', {}, { status: 401 }));
  page.emit('response', response('https://tiku.fenbi.com/api/shenlun/papers', {}, { length: 201 }));
  page.emit('response', response('https://tiku.fenbi.com/api/shenlun/papers', { message: '验证码' }));
  page.emit('response', response('https://tiku.fenbi.com/api/shenlun/papers', { large: 'x'.repeat(300) }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/papers', {}, { method: 'POST' }));
  await observer.flush();
  observer.stop();
  assert.equal(received.length, 1);
  assert.equal(received[0].meta.url, 'https://tiku.fenbi.com/api/xingce/papers?labelId=1');
  assert.equal(observer.stats.oversized, 2);
  assert.equal(observer.stats.unauthorized, 1);
  assert.equal(observer.stats.captcha, 1);
  assert.equal(observer.stats.accepted, 1);
  assert.equal(page.listenerCount('response'), 0);
});

test('existing exercise question reads are observed without observing exercise account lists', async () => {
  const page = new EventEmitter();
  const received = [];
  const observer = observeReadResponses(page, async (payload, meta) => received.push({ payload, meta }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/exercises/12345/questions', { questions: [{ id: 1 }] }));
  page.emit('response', response('https://tiku.fenbi.com/api/shenlun/exercises/12345', { materials: [] }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/exercises', { private: true }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/exercises/current', { private: true }));
  await observer.flush(); observer.stop();
  assert.equal(received.length, 2);
});

test('replay registration keeps exact observed query parameters and never registers a redacted URL', async () => {
  const page = new EventEmitter(), received = [];
  const observer = observeReadResponses(page, (_body, meta) => received.push(meta));
  const exact = 'https://tiku.fenbi.com/api/xingce/questions?questionIds=123,456&app=web&kav=100';
  page.emit('response', response(exact, { questions: [] }));
  page.emit('response', response(`${exact}&unknown=value`, { questions: [] }));
  page.emit('response', response(`${exact}&token=SYNTHETIC_PRIVATE_QUERY_VALUE`, { questions: [] }));
  await observer.flush(); observer.stop();
  assert.equal(received[0].replayUrl, exact);
  assert.equal(received[1].replayUrl, null);
  assert.equal(received[2].replayUrl, null);
  assert.ok(!JSON.stringify(received).includes('SYNTHETIC_PRIVATE_QUERY_VALUE'));
});

test('persistent session exclusively locks profile and releases on close or launch failure', async () => {
  const profile = await mkdtemp(path.join(os.tmpdir(), 'fenbi-profile-'));
  let browserOptions;
  const context = new EventEmitter();
  context.setDefaultTimeout = () => {};
  context.route = async () => {};
  context.newPage = async () => ({ goto: async () => {} });
  context.close = async () => {};
  const launcher = { launchPersistentContext: async (_profile, options) => { browserOptions = options; return context; } };
  const config = { profileDir: profile, channel: 'chrome', entryUrl: 'https://www.fenbi.com/spa/tiku' };
  try {
    const session = await openSession(config, { launcher });
    assert.equal(browserOptions.serviceWorkers, 'block');
    assert.equal(browserOptions.acceptDownloads, false);
    await assert.rejects(openSession(config, { launcher }), { code: 'PROFILE_LOCKED' });
    context.emit('response', response('https://login.fenbi.com/api/users/info', { private: true }));
    assert.equal(session.auth.status, 'authenticated');
    assert.equal('private' in session.auth.evidence[0], false);
    await session.close();
    await assert.rejects(access(path.join(profile, '.fenbi-framework.lock')));
    await assert.rejects(openSession(config, { launcher: { launchPersistentContext: async () => { throw new Error('secret!'); } } }), /Could not open/);
    await assert.rejects(access(path.join(profile, '.fenbi-framework.lock')));
  } finally { await rm(profile, { recursive: true, force: true }); }
});

test('session close does not remove another owner lock and releases its own after browser close failure', async () => {
  const profile = await mkdtemp(path.join(os.tmpdir(), 'fenbi-profile-'));
  const context = new EventEmitter();
  context.setDefaultTimeout = () => {};
  context.route = async () => {};
  context.newPage = async () => ({});
  context.close = async () => { throw new Error('browser close failure'); };
  const config = { profileDir: profile, entryUrl: 'https://www.fenbi.com/spa/tiku' };
  const launcher = { launchPersistentContext: async () => context };
  try {
    let session = await openSession(config, { launcher });
    await assert.rejects(session.close(), /browser close failure/);
    await assert.rejects(access(path.join(profile, '.fenbi-framework.lock')));
    session = await openSession(config, { launcher });
    await writeFile(path.join(profile, '.fenbi-framework.lock'), 'another-owner', 'utf8');
    await assert.rejects(session.close(), /browser close failure/);
    assert.equal(await readFile(path.join(profile, '.fenbi-framework.lock'), 'utf8'), 'another-owner');
  } finally { await rm(profile, { recursive: true, force: true }); }
});

test('DOM capture retains complete material, tables, math and images while removing controls', async () => {
  const fragment = '<section class="paper"><header>account</header><p>' + '正文'.repeat(20000) + '</p><table><tr><td>42</td></tr></table><math><mi>x</mi></math><img src="https://img.fbstatic.cn/figure.png"><script>secret</script><input value="phone"><button>submit</button></section>';
  const page = { url: () => 'https://www.fenbi.com/spa/tiku/paper/1', title: async () => 'paper', locator: () => ({ count: async () => 1, evaluateAll: async () => [fragment] }) };
  const document = await captureDom(page, '.paper');
  assert.ok(document.html.includes('正文'.repeat(20000)));
  assert.match(document.html, /<table>/);
  assert.match(document.html, /<math>/);
  assert.equal(document.images.length, 1);
  assert.doesNotMatch(document.html, /account|secret|input|button/);
  await assert.rejects(captureDom(page, 'body'), { code: 'UNSAFE_SELECTOR' });
});

test('asset collection rejects unknown hosts, redirects and oversized bodies before writing', async () => {
  const assetDir = await mkdtemp(path.join(os.tmpdir(), 'fenbi-assets-'));
  const bytes = Buffer.from('test-image-bytes');
  const requests = [];
  const page = {
    context: () => ({ request: { get: async (url, options) => {
      requests.push({ url, options });
      return { status: () => url.includes('redirect') ? 302 : 200, headers: () => ({ 'content-type': 'image/png', 'content-length': url.includes('large') ? String(13 * 1024 * 1024) : String(bytes.length) }), body: async () => bytes, dispose: async () => {} };
    } } }),
    evaluate: async () => ({ width: 10, height: 20 }),
  };
  const document = { url: 'https://www.fenbi.com/spa/tiku', html: '<img src="https://img.fbstatic.cn/a.png">', assets: [{ url: 'https://evil.invalid/a.png' }, { url: 'https://img.fbstatic.cn/redirect.png' }, { url: 'https://img.fbstatic.cn/large.png' }, { url: 'https://img.fbstatic.cn/private.png?token=secret' }] };
  try {
    const result = await downloadAssets(page, document, assetDir);
    assert.equal(requests.length, 3);
    assert.ok(requests.every(item => item.options.maxRedirects === 0));
    assert.equal(result.filter(item => item.status === 'rejected_url').length, 2);
    assert.equal(result.filter(item => item.status === 'oversized').length, 1);
    const downloaded = result.find(item => item.status === 'downloaded');
    assert.equal(downloaded.width, 10);
    assert.equal(downloaded.bytes, bytes.length);
    assert.equal(downloaded.decoded, true);
    assert.equal(downloaded.decode.sha256, downloaded.sha256);
    assert.deepEqual(await readFile(path.join(assetDir, downloaded.localPath)), bytes);
    assert.doesNotMatch(JSON.stringify(result), /secret|evil\.invalid/);
  } finally { await rm(assetDir, { recursive: true, force: true }); }
});

test('DOM lazy image references preserve safe CDN transforms and report missing sources', async () => {
  const fragment = '<section class="paper"><img data-src="https://img.fbstatic.cn/a.png?width=1200&amp;format=webp"><img srcset="https://img.fbstatic.cn/b.png?height=400 1x, https://img.fbstatic.cn/b2.png 2x"><img src="https://img.fbstatic.cn/c.png?token=private"></section>';
  const page = { url: () => 'https://www.fenbi.com/spa/tiku/paper/1', title: async () => 'paper', locator: () => ({ count: async () => 1, evaluateAll: async () => [fragment] }) };
  const document = await captureDom(page, '.paper');
  assert.equal(document.images.length, 2);
  assert.equal(document.images[0].url, 'https://img.fbstatic.cn/a.png?width=1200&format=webp');
  assert.equal(document.images[1].url, 'https://img.fbstatic.cn/b.png?height=400');
  assert.equal(document.blocked.missingImages, 1);
  assert.doesNotMatch(document.html, /private|token|data-src|srcset/);
});

// ── concurrency safety: one guard for every page of one profile ─────────────────────────────
// Extra pages are created inside the single persistent context, so the read-only route guard is
// installed once and covers them all. Nothing here opens a real browser or touches an account.

test('the read-only guard is installed once per context, so every concurrently opened page is covered', async () => {
  const profile = await mkdtemp(path.join(os.tmpdir(), 'fenbi-profile-'));
  const context = new EventEmitter();
  context.setDefaultTimeout = () => {};
  context.newPage = async () => ({ goto: async () => {} });
  context.close = async () => {};
  const routes = [];
  context.route = async (pattern, handler) => routes.push({ pattern, handler });
  const launcher = { launchPersistentContext: async () => context };
  const config = { profileDir: profile, channel: 'chrome', entryUrl: 'https://www.fenbi.com/spa/tiku' };
  try {
    const session = await openSession(config, { launcher });
    assert.equal(routes.length, 1, 'exactly one context-level route, never one per page');
    assert.equal(routes[0].pattern, '**/*');
    const aborts = [], continues = [];
    const send = (url, method) => routes[0].handler({
      request: () => ({ url: () => url, method: () => method, isNavigationRequest: () => false }),
      abort: async () => aborts.push(url), continue: async () => continues.push(url),
    });
    // The second batch's papers have no existing exercise, so they would need exactly these writes.
    await send('https://tiku.fenbi.com/api/xingce/exercises', 'POST');
    await send('https://tiku.fenbi.com/api/xingce/exercises/4189916/answers', 'POST');
    await send('https://tiku.fenbi.com/api/xingce/exercises/4189916/submit', 'PUT');
    await send('https://tiku.fenbi.com/api/xingce/papers/v2?labelId=1&toPage=0&pageSize=15', 'GET');
    assert.deepEqual(aborts, ['https://tiku.fenbi.com/api/xingce/exercises',
      'https://tiku.fenbi.com/api/xingce/exercises/4189916/answers',
      'https://tiku.fenbi.com/api/xingce/exercises/4189916/submit']);
    assert.equal(continues.length, 1, 'only the observed read-only list request is allowed through');
    assert.equal(session.guardStats.blockedWrites, 3, 'guard statistics are shared by the whole context');
    await session.close();
  } finally { await rm(profile, { recursive: true, force: true }); }
});

test('429 and 503 are counted as rate limits so a scheduler can back off instead of retrying blindly', async () => {
  const page = new EventEmitter(), received = [];
  const observer = observeReadResponses(page, (payload, meta) => received.push(meta));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/papers', { message: 'slow down' }, { status: 429 }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/papers', { message: 'unavailable' }, { status: 503 }));
  page.emit('response', response('https://tiku.fenbi.com/api/xingce/papers', { message: 'boom' }, { status: 500 }));
  await observer.flush(); observer.stop();
  assert.equal(observer.stats.rateLimited, 2);
  assert.equal(observer.stats.failed, 1);
  assert.equal(observer.stats.accepted, 0);
  assert.equal(received.length, 0, 'a rate-limited response is never treated as data');
});

// ── captureDom → DOM adapter contract ───────────────────────────────────────────────────────
// The verified Xingce DOM adapter selects on `app-ti[data-question-key]`. captureDom removed
// every unrecognised `data-*`, so the key never survived capture and the adapter returned zero
// questions while chapter counters still declared the real total. These fixtures are synthetic:
// no account, no network, no browser.

const SYNTHETIC_SECRET = 'SYNTHETIC_PRIVATE_SESSION_VALUE';

const examQuestion = (number, key, choices) =>
  `<app-ti data-question-key="${key}" data-user-id="account-1" onclick="steal()" style="color:red">` +
  `<div class="title-index">${number}.</div>` +
  `<div class="question-choice-container" data-token="${SYNTHETIC_SECRET}"><p>离线合成题干${number}。</p>` +
  `<app-choice-radio>${choices.map((label, index) =>
    `<label class="choice-radio-label"><div class="input-radio">${label}</div><p class="input-text">选项${index + 1}</p></label>`).join('')}</app-choice-radio></div></app-ti>`;

const examFragment = () =>
  '<div class="tis-container">' +
  '<div class="chapter-container">常识判断（2题）请选择唯一答案。</div>' +
  `<div class="questions-single-container">${examQuestion(1, '3_1_beq2d', ['A', 'B', 'C', 'D'])}${examQuestion(2, '3_2_cfr9x', ['A', 'B'])}</div>` +
  '<div class="chapter-container">资料分析（2题）根据材料作答。</div>' +
  '<div class="resizable-container"><div class="left"><div class="materials-container"><div class="material-body">' +
  '<div class="material-content">离线合成材料正文。<img data-src="https://img.fbstatic.cn/chart.png?width=700"></div>' +
  '</div></div></div><div class="right"><div class="questions-container">' +
  `${examQuestion(3, '4_1-zzz_01', ['A', 'B'])}${examQuestion(4, '4_2-zzz_02', ['A', 'B'])}` +
  '</div></div></div>' +
  `<script>fetch("https://tiku.fenbi.com/api/xingce/user/history")</script><input value="${SYNTHETIC_SECRET}"><button>交卷</button>` +
  '</div>';

const examPage = (fragment) => ({
  url: () => 'https://www.fenbi.com/spa/tiku/synthetic-capture',
  title: async () => 'synthetic',
  locator: () => ({ count: async () => 1, evaluateAll: async () => [fragment] }),
});

const captureIdentity = { id: 'synthetic-capture', title: '离线合成卷', subject: 'xingce', year: 2026, area: '浙江', variant: 'C类' };

test('captureDom keeps the composite question key so the verified DOM adapter still parses every question', async () => {
  const dom = await captureDom(examPage(examFragment()), '.tis-container');
  assert.equal(dom.blocked, null);
  assert.equal((dom.html.match(/<app-ti[^>]*data-question-key/g) || []).length, 4);

  const document = parseFenbiExamDom(sanitizeHtml(dom.html).html, captureIdentity, { url: dom.url });
  assert.equal(document.questions.length, 4, 'captureDom -> DOM adapter must not lose questions');
  assert.deepEqual(document.questions.map((q) => q.id), ['3_1_beq2d', '3_2_cfr9x', '4_1-zzz_01', '4_2-zzz_02']);
  assert.deepEqual(document.questions.map((q) => q.number), [1, 2, 3, 4]);
  assert.equal(document.expected.questions, 4, 'chapter counters still establish the expected total');
  assert.equal(document.chapters.length, 2);
  assert.equal(document.materials.length, 1);
  // Grouped questions under one material group and standalone questions both survive.
  assert.deepEqual(document.questions[0].materialIds, []);
  assert.deepEqual(document.questions[2].materialIds, document.questions[3].materialIds);
  assert.equal(document.questions[2].materialIds.length, 1);
  assert.equal(document.questions[0].options.length, 4);
  assert.equal(document.questions[1].options.length, 2);
  assert.deepEqual(document.conflicts, []);
});

test('a dropped question key is the exact failure mode: the adapter silently returns zero questions', async () => {
  const dom = await captureDom(examPage(examFragment()), '.tis-container');
  const stripped = dom.html.replace(/ data-question-key="[^"]*"/gu, '');
  const document = parseFenbiExamDom(sanitizeHtml(stripped).html, captureIdentity, { url: dom.url });
  assert.equal(document.questions.length, 0);
  assert.equal(document.expected.questions, 4, 'the chapter counters still claim four questions');
  assert.equal(document.chapters.length, 2);
  assert.deepEqual(document.conflicts, [], 'the loss is unobservable from the document alone');
});

test('captureDom still strips account state, handlers and credential-shaped question keys', async () => {
  const fragment = examFragment()
    .replace('data-question-key="3_1_beq2d"', `data-question-key="https://tiku.fenbi.com/api/xingce/exercises/1/questions?token=${SYNTHETIC_SECRET}"`)
    .replace('data-question-key="3_2_cfr9x"', `data-question-key="session=${SYNTHETIC_SECRET}"`)
    .replace('data-question-key="4_1-zzz_01"', `data-question-key="${'a'.repeat(81)}"`)
    .replace('data-question-key="4_2-zzz_02"', 'data-question-key="4_2-zzz_02"');
  const dom = await captureDom(examPage(fragment), '.tis-container');
  assert.ok(!dom.html.includes(SYNTHETIC_SECRET), 'no credential value may reach the captured DOM');
  assert.equal((dom.html.match(/<app-ti[^>]*data-question-key/g) || []).length, 1, 'only the well-formed key survives');
  assert.match(dom.html, /data-question-key="4_2-zzz_02"/u);
  assert.doesNotMatch(dom.html, /onclick|style=|data-user-id|data-token|<script|<input|<button/iu);
  assert.equal(dom.images.length, 1);
  assert.equal(dom.blocked, null, 'a well-formed page reports no capture block');
});
