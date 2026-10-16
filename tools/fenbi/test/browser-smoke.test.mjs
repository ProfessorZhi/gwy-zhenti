import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright-core';
import { captureDom, observeReadResponses, downloadAssets, openSession } from '../src/browser.mjs';
import { createDocument, absorbPayload, collectAssetUrls } from '../src/model.mjs';
import { validateDocument } from '../src/validate.mjs';
import { exportCandidate } from '../src/render.mjs';
import { runBounded } from '../src/schedule.mjs';

const channel = process.env.FENBI_TEST_BROWSER_CHANNEL || 'chrome';
const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jQnQAAAAASUVORK5CYII=', 'base64');

test('installed browser: observed JSON → normalized paper → actual image decode → validated Markdown, offline only', async t => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-browser-'));
  const browser = await chromium.launch({ channel, headless: true });
  t.after(async () => { await browser.close(); await fs.rm(directory, { recursive: true, force: true }); });
  const page = await browser.newPage();
  const identity = { id: 'synthetic-paper', title: '2025江苏行测C类（离线合成测试）', subject: 'xingce', year: 2025, area: '江苏', variant: 'C类' };
  const document = createDocument(identity, { url: 'https://www.fenbi.com/spa/tiku/synthetic-test' });
  const payload = { paperId: identity.id, questionCount: 1, materialCount: 0,
    questions: [{ id: 'q1', number: 1, content: '合成题干<img src="https://img.fbstatic.cn/fixture.png">', options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }], answer: 'A', analysis: '离线合成解析，不是真题。' }] };
  // Every request is fulfilled or aborted inside this test. No real account or website is used.
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname === 'tiku.fenbi.com') await route.fulfill({ contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(payload) });
    else if (url.pathname.endsWith('.png')) await route.fulfill({ contentType: 'image/png', body: pixel });
    else if (url.hostname === 'www.fenbi.com') await route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<meta charset="utf-8"><title>离线测试</title><main class="question"><p>完整合成题干</p><table><tr><td>合成表格</td></tr></table><img src="https://img.fbstatic.cn/fixture.png"></main><script>fetch("https://tiku.fenbi.com/api/xingce/questions").then(r=>r.json()).then(()=>document.documentElement.dataset.ready="yes")</script>' });
    else await route.abort();
  });
  const observer = observeReadResponses(page, (body, meta) => absorbPayload(document, body, meta));
  await page.goto(document.source.url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.documentElement.dataset.ready === 'yes');
  await observer.flush(); observer.stop();
  assert.equal(observer.stats.accepted, 1); assert.equal(document.questions.length, 1);
  const dom = await captureDom(page, '.question');
  assert.ok(dom.html.includes('完整合成题干')); assert.equal(dom.blocked, null);
  document.assets = collectAssetUrls(document).map(url => ({ url }));
  const assetPage = { evaluate: page.evaluate.bind(page), context: () => ({ request: { get: async () => ({
    status: () => 200, headers: () => ({ 'content-type': 'image/png' }), body: async () => pixel, dispose: async () => {},
  }) } }) };
  const assetRoot = path.join(directory, 'assets');
  await downloadAssets(assetPage, document, assetRoot);
  assert.equal(document.assets[0].status, 'downloaded'); assert.equal(document.assets[0].width, 1);
  const verdict = await validateDocument(document, { assetRoot });
  assert.equal(verdict.status, 'complete', JSON.stringify(verdict.issues));
  const output = path.join(directory, 'candidate');
  await exportCandidate(document, verdict, directory, output);
  assert.ok((await fs.readFile(path.join(output, 'paper.md'), 'utf8')).includes('assets/'));
});

test('installed browser: dedicated profile preserves synthetic cookies across restarts, without visiting a site', async t => {
  const profileDir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-profile-'));
  t.after(() => fs.rm(profileDir, { recursive: true, force: true }));
  const config = { profileDir, channel, entryUrl: 'https://www.fenbi.com/spa/tiku' };
  const first = await openSession(config, { headless: true });
  try { await first.context.addCookies([{ name: 'synthetic_test_cookie', value: 'not-a-credential', domain: '.fenbi.com', path: '/', expires: Math.floor(Date.now() / 1000) + 3600, secure: true }]); }
  finally { await first.close(); }
  const second = await openSession(config, { headless: true });
  try { assert.ok((await second.context.cookies()).some(cookie => cookie.name === 'synthetic_test_cookie')); }
  finally { await second.close(); }
});

// Two papers at once, inside the one profile. Synthetic content only; the pages' own route handlers
// take precedence for fenbi hosts, and anything else falls back to the context-level read-only
// guard — which is how the guard is shown to still cover a page opened after the session started.
test('installed browser: two pages of one profile capture different papers concurrently, offline only', async t => {
  const profileDir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-concurrent-'));
  t.after(() => fs.rm(profileDir, { recursive: true, force: true }));
  // Read the override here rather than relying on any other change to this file, so this test is
  // self-contained and can land before or after a separate browser-path change.
  const explicitBrowser = process.env.FENBI_TEST_BROWSER_EXECUTABLE || undefined;
  const session = await openSession({ profileDir, channel, ...(explicitBrowser ? { executablePath: explicitBrowser } : {}),
    entryUrl: 'https://www.fenbi.com/spa/tiku' }, { headless: true });
  try {
    const papers = [{ id: 'fixture-c', title: '离线合成C卷', questions: 3 }, { id: 'fixture-a', title: '离线合成A卷', questions: 2 }];
    const payloadFor = (paper) => ({ paperId: paper.id, questionCount: paper.questions, materialCount: 0,
      questions: Array.from({ length: paper.questions }, (_unused, index) => ({ id: `${paper.id}-q${index + 1}`, number: index + 1,
        content: `合成题干${index + 1}`, options: [{ label: 'A', content: '甲' }, { label: 'B', content: '乙' }], answer: 'A', analysis: '离线合成解析，不是真题。' })) });

    const pages = [session.page, await session.context.newPage()];
    await Promise.all(pages.map((page, index) => page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.hostname === 'tiku.fenbi.com') return route.fulfill({ contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(payloadFor(papers[index])) });
      if (url.hostname === 'www.fenbi.com') return route.fulfill({ contentType: 'text/html; charset=utf-8',
        body: `<meta charset="utf-8"><title>${papers[index].title}</title><main class="question"><p>合成题干</p></main>`
          + '<script>fetch("https://tiku.fenbi.com/api/xingce/questions").then(r=>r.json()).then(()=>document.documentElement.dataset.ready="yes")</script>' });
      return route.fallback();
    })));

    const documents = papers.map(paper => createDocument({ id: paper.id, title: paper.title, subject: 'xingce', year: 2025, area: '江苏', variant: 'C类' },
      { url: `https://www.fenbi.com/spa/tiku/${paper.id}` }));
    const observers = pages.map((page, index) => observeReadResponses(page, (body, meta) => absorbPayload(documents[index], body, meta)));
    const titles = [];
    const run = await runBounded([0, 1], async (index, { slot }) => {
      const page = pages[slot];
      await page.goto(documents[index].source.url, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.documentElement.dataset.ready === 'yes');
      await observers[index].flush();
      titles.push(await page.title());
      return documents[index].questions.length;
    }, { concurrency: 2 });
    for (const observer of observers) observer.stop();

    assert.equal(run.concurrency, 2);
    assert.equal(run.failures.length, 0, 'neither paper may fail the other');
    assert.deepEqual([...titles].sort(), ['离线合成A卷', '离线合成C卷']);
    // Each page observed only its own paper: independent listeners, independent documents.
    assert.equal(documents[0].questions.length, 3);
    assert.equal(documents[1].questions.length, 2);
    assert.equal(observers[0].stats.accepted, 1);
    assert.equal(observers[1].stats.accepted, 1);
    assert.ok(documents[0].questions.every((q) => q.id.startsWith('fixture-c')));
    assert.ok(documents[1].questions.every((q) => q.id.startsWith('fixture-a')));

    // The guard installed when the session opened still covers the page created afterwards.
    const outcome = await pages[1].evaluate(async () => { try { await fetch('https://blocked.invalid/anything'); return 'allowed'; } catch { return 'blocked'; } });
    assert.equal(outcome, 'blocked');
    assert.ok(session.guardStats.blockedHost > 0, 'the guard recorded the blocked host');
  } finally { await session.close(); }
});
