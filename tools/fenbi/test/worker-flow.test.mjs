// Offline: drives the real per-paper flow (worker/flow.mjs) in a real browser against a fake Fenbi site.
// Every request is fulfilled or aborted inside this test; no account or website is used.
// Needs a Chromium build: FENBI_TEST_BROWSER_EXECUTABLE, or the cloud image's /opt/pw-browsers/chromium.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright-core';
import { ENTRY, createGate, createMutex, installRoutes, watchRisk, runPaper } from '../worker/flow.mjs';

const executablePath = process.env.FENBI_TEST_BROWSER_EXECUTABLE || '/opt/pw-browsers/chromium';
const skip = fsSync.existsSync(executablePath) ? false : 'no Chromium executable for the offline flow test';
const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jQnQAAAAASUVORK5CYII=', 'base64');
const EXAM = 'https://www.fenbi.com/spa/tiku/exam/practice/fake-1';
const TITLE = '2025年国考行测（地市级）';
const EXPL = '这是一段足够长的离线合成解析文字，不是真题内容。';

const question = (n, key) => `<app-ti data-question-key="${key}"><div class="title-index">${n}.</div><div class="question-choice-container"><p>合成题干 ${n}，求结果。<img src="https://fb.fbstatic.cn/q${n}.png"></p><app-choice-radio><label class="choice-radio-label"><div class="input-radio">A</div><p class="input-text">甲</p></label><label class="choice-radio-label"><div class="input-radio">B</div><p class="input-text">乙</p></label></app-choice-radio></div></app-ti>`;
const analysisTi = (key, ans) => `<app-ti data-question-key="${key}"><p>正确答案 <span class="correct-answer">${ans}</span></p><section class="result-common-section"><app-solution-title>解析</app-solution-title><p>${EXPL}</p></section></app-ti>`;

const catalogHtml = rowText => `<!doctype html><html><head><title>真题</title></head><body>
<span class="categories-item">国考</span><span class="categories-item">浙江</span><div id="list"></div>
<script>
document.querySelectorAll('.categories-item').forEach(el => el.onclick = () => {
  document.getElementById('list').innerHTML = el.textContent === '国考' ? '<div class="paper-item">${TITLE} ${rowText}</div>' : '';
  const row = document.querySelector('.paper-item');
  if (row) row.onclick = async () => { await fetch('https://tiku.fenbi.com/api/xingce/exercises', { method: 'POST' }).catch(() => {}); location.href = '${EXAM}'; };
});
</script></body></html>`;

const examHtml = () => `<!doctype html><html><head><title>${TITLE}</title></head><body>
<script>fetch('https://tiku.fenbi.com/api/xingce/exercises/fake-1').catch(() => {});</script>
<div class="tis-container"><div class="chapter-container">常识判断（2题）请选择。</div><div class="questions-single-container">${question(1, '3_1_k1')}${question(2, '3_1_k2')}</div></div>
<div class="submit-btn">交卷</div><div id="modal"></div>
<script>
document.querySelector('.submit-btn').onclick = () => {
  document.getElementById('modal').innerHTML = '<div class="modal-action-btn btn-submit">确认交卷</div>';
  document.querySelector('.btn-submit').onclick = async () => {
    await fetch('https://tiku.fenbi.com/combine/exercise/submit', { method: 'POST' });
    document.body.innerHTML = '${analysisTi('3_1_k1', 'A')}${analysisTi('3_1_k2', '')}';
    await fetch('https://tiku.fenbi.com/combine/static/solution?id=1');
  };
};
</script></body></html>`;

async function fakeSite(ctx, { rowText = '', paperId = 1 } = {}) {
  const seen = { init: 0, submit: 0, otherWrites: 0 };
  await ctx.route('**/*', route => {
    const req = route.request(), u = new URL(req.url()), m = req.method();
    if (m === 'POST') {
      if (u.pathname === '/api/xingce/exercises') seen.init++;
      else if (/\/combine\/exercise\/submit$/.test(u.pathname)) seen.submit++;
      else seen.otherWrites++;
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    }
    if (req.url().startsWith(ENTRY)) return route.fulfill({ contentType: 'text/html; charset=utf-8', body: catalogHtml(rowText) });
    if (u.pathname === '/api/xingce/exercises/fake-1') return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'fake-1', sheet: { paperId } }) });
    if (req.url().startsWith(EXAM)) return route.fulfill({ contentType: 'text/html; charset=utf-8', body: examHtml() });
    if (u.pathname.startsWith('/combine/static/solution')) return route.fulfill({ contentType: 'application/json',
      body: JSON.stringify({ solutions: [{ globalId: '3_1_k1', correctAnswer: { choice: '0' } }, { globalId: '3_1_k2', correctAnswer: { choice: '1' }, solution: `<p>${EXPL}</p>` }] }) });
    if (/\.png$/.test(u.pathname)) return route.fulfill({ contentType: 'image/png', body: pixel });
    return route.abort();
  });
  return seen;
}

async function setup(t, opts) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'fenbi-flow-'));
  const ctx = await chromium.launchPersistentContext(path.join(dir, 'profile'), { executablePath, headless: true });
  t.after(async () => { await ctx.close(); await fs.rm(dir, { recursive: true, force: true }); });
  const seen = await fakeSite(ctx, opts);      // registered first, so the worker policy below runs before it
  const policy = { initBudget: 0, initCalls: 0, blockedWrites: 0 };
  await installRoutes(ctx, policy);
  const risk = { captcha: 0, loginLost: 0, http403: 0, http429: 0 };
  watchRisk(ctx, risk);
  const marks = [];
  const ledger = { markSubmit: async (item, s) => marks.push(['submit', s]), markCapture: async (item, s) => marks.push(['capture', s]),
    quarantine: async (item, info) => marks.push(['quarantine', info.stage]) };
  const env = { ctx, gate: createGate(50), openLock: createMutex(), policy, risk, dwellMs: 300, papersDir: path.join(dir, 'papers'), ledger };
  const item = { kind: 'new', key: 'gk-2025-xingce-dishiji-1', sourceId: '1', label: '国考', area: '国考', year: 2025,
    titleRe: TITLE.replace(/[()（）]/g, '\\$&'), titleFrag: ['2025'],
    identity: { id: '1', title: TITLE, subject: 'xingce', year: 2025, area: '国考', variant: 'dishiji' } };
  return { ctx, env, item, seen, marks, policy, risk, slot: { page: await ctx.newPage(), region: null } };
}

test('one paper: catalog → one init → blank submit once → answers, explanations and images on disk', { skip, timeout: 90e3 }, async t => {
  const { env, item, seen, marks, slot, risk } = await setup(t);
  const rec = await runPaper(slot, item, env);
  assert.ok(['complete', 'submitted_partial'].includes(rec.status), JSON.stringify(rec));
  assert.deepEqual([seen.init, seen.submit, seen.otherWrites], [1, 1, 0]);
  assert.equal(rec.initCalls, 1);
  assert.equal(rec.answers, 2, 'DOM answer for q1, JSON fills q2');
  assert.deepEqual(marks.map(m => m.join(':')), ['capture:ok', 'submit:submitting', 'submit:submitted_partial', `submit:${rec.status}`]);
  const doc = JSON.parse(await fs.readFile(path.join(env.papersDir, item.key, 'document.json'), 'utf8'));
  assert.deepEqual(doc.questions.map(q => q.answerHtml), ['<p>A</p>', '<p>B</p>']);
  // Image bytes go through the context's API client, which page routes do not intercept, so offline they fail;
  // what matters here is that both question images were queued for download.
  assert.equal(doc.assets.length, 2);
  const run = JSON.parse(await fs.readFile(path.join(env.papersDir, item.key, 'run-summary.json'), 'utf8'));
  assert.equal(run.pageUrl, EXAM);
  assert.equal(risk.http403 + risk.http429 + risk.captcha + risk.loginLost, 0);
  assert.equal(rec.binding, 'verified');
  assert.ok(doc.evidence.some(e => e.type === 'source-paper-identity' && e.paperId === '1'));
  assert.ok(rec.dwellMs >= 300);
});

test('a row that already has a practice gets no init budget', { skip, timeout: 90e3 }, async t => {
  const { env, item, seen, slot } = await setup(t, { rowText: '继续练习' });
  const rec = await runPaper(slot, item, env);
  assert.equal(rec.hadExistingExercise, true);
  assert.equal(seen.init, 0, 'the page tried, the policy aborted it');
  assert.equal(seen.submit, 1);
});

test('an opened exercise whose paperId is another paper is not submitted and is quarantined', { skip, timeout: 90e3 }, async t => {
  const { env, item, seen, marks, slot } = await setup(t, { paperId: 999 });
  const rec = await runPaper(slot, item, env);
  assert.equal(rec.status, 'PAPER_ID_MISMATCH');
  assert.equal(seen.submit, 0);
  assert.deepEqual(marks.filter(m => m[0] !== 'capture').map(m => m.join(':')), ['quarantine:before-submit']);
});
