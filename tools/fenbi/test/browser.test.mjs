import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mkdtemp, readFile, rm, access, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { openSession, requestPolicy, observeReadResponses, captureDom, downloadAssets } from '../src/browser.mjs';

test('capture guard blocks writes, external navigation, HTTP and deceptive hosts', () => {
  assert.equal(requestPolicy({ url: 'https://tiku.fenbi.com/api/xingce/papers', method: 'GET' }), null);
  assert.equal(requestPolicy({ url: 'https://tiku.fenbi.com/api/xingce/exercises', method: 'POST' }), 'blockedWrites');
  assert.equal(requestPolicy({ url: 'https://login.fenbi.com/api/users/login', method: 'POST' }), 'blockedWrites');
  assert.equal(requestPolicy({ url: 'https://login.fenbi.com/api/users/login', method: 'POST' }, 'login'), null);
  assert.equal(requestPolicy({ url: 'https://tiku.fenbi.com/api/xingce/exercises', method: 'POST' }, 'login'), 'blockedWrites');
  assert.equal(requestPolicy({ url: 'https://img.fbstatic.cn/test.png', navigation: true }), 'blockedNavigation');
  assert.equal(requestPolicy({ url: 'https://fenbi.com.evil.invalid/test' }), 'blockedHost');
  assert.equal(requestPolicy({ url: 'http://www.fenbi.com/' }), 'blockedUrl');
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
