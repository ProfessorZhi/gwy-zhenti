import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { parseAnalysisDom, mergeAnalysisDom, mergeSolutionJson, toLetters, isBlank } from '../worker/analysis-merge.mjs';
import { buildQueue, takeNext, SUBMIT_DONE } from '../worker/queue.mjs';
import { fullGate } from '../worker/gate.mjs';
import { publish } from '../worker/publish.mjs';

// Isolate from the host's global git config (signing, push negotiation); the fixtures set their own identity.
process.env.GIT_CONFIG_GLOBAL = '/dev/null';
const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const plain = html => ({ html, rejected: 0 });
const EXPL = '这是一段足够长的解析文字，用来通过二十个字符的下限检查。';

test('analysis DOM answers and explanations are merged by question key', () => {
  const html = `<app-ti data-question-key="k1"><span class="x correct-answer">B</span>
    <section class="result-common-section"><app-solution-title>解析视频</app-solution-title>视频</section>
    <section class="result-common-section"><app-solution-title>解析</app-solution-title><p>${EXPL}</p></section></app-ti>
    <app-ti data-question-key="k2"><span class="correct-answer">C</span></app-ti>`;
  const doc = { questions: [{ id: 'k1' }, { id: 'k2' }, { id: 'k3' }], conflicts: [] };
  const r = mergeAnalysisDom(doc, parseAnalysisDom(html), plain);
  assert.deepEqual(r, { answers: 1, explanations: 1 });
  assert.equal(doc.questions[0].answerHtml, '<p>B</p>');
  assert.match(doc.questions[0].explanationHtml, /足够长/u);
  assert.equal(doc.questions[1].answerHtml, undefined, 'no explanation means the DOM answer is not trusted alone');
});

test('solution JSON fills only gaps and converts 0-based choices', () => {
  assert.equal(toLetters('2,3'), 'CD');
  const doc = { conflicts: [], questions: [
    { id: '1', options: [{ label: 'A' }, { label: 'B' }, { label: 'C' }], answerHtml: '<p>A</p>', explanationHtml: `<p>${EXPL}</p>` },
    { id: '2', options: [{ label: 'A' }, { label: 'B' }, { label: 'C' }] },
    { id: '3', options: [] }] };
  const s = mergeSolutionJson(doc, { solutions: [
    { globalId: 1, correctAnswer: { choice: '1' }, solution: 'x' },
    { globalId: 2, correctAnswer: { choice: '2' }, solution: `<p>${EXPL}</p>` },
    { globalId: 3, correctAnswer: { answer: '正确' }, solution: '' }] }, plain);
  assert.equal(doc.questions[0].answerHtml, '<p>A</p>', 'DOM answer kept');
  assert.equal(s.domJsonMismatch, 1);
  assert.equal(doc.questions[1].answerHtml, '<p>C</p>');
  assert.equal(doc.questions[2].answerHtml, '<p>正确</p>');
  assert.equal(s.answers, 2);
});

test('blank check refuses any sign of an answered paper', () => {
  assert.equal(isBlank({ checked: 0, aria: 0, hint: undefined }), true);
  assert.equal(isBlank({ checked: 1, aria: 0 }), false);
  assert.equal(isBlank({ checked: 0, aria: 0, hint: '3' }), false);
});

test('queue: resume cached unsubmitted papers first, never resubmit, skip cached and captured sources', () => {
  const year = new Date().getFullYear() - 1;
  const cand = (id, area = '国考', title = `${year}年国考行测（地市级）`) => ({ id, title, year, area, region: area });
  const q = buildQueue({
    cached: [{ key: 'gk-a-1', sourceId: '1', pageUrl: 'https://x/1' }, { key: 'gk-a-2', sourceId: '2', pageUrl: 'https://x/2' },
      { key: 'gk-a-3', sourceId: '3', pageUrl: null }],
    candidates: [cand('1'), cand('3'), cand('4'), cand('5'), cand('6'), cand('7', '浙江', `${year}年浙江行测（A类）`)],
    t2Ledger: { papers: { 'gk-a-2': { status: 'submitting', sourceId: '2' }, other: { status: 'complete', sourceId: '5' } } },
    captureLedger: { targets: { 6: { status: 'ok' } } },
  });
  assert.deepEqual(q.map(x => [x.kind, x.sourceId]), [['resume', '1'], ['new', '4'], ['new', '7']]);
  assert.ok(SUBMIT_DONE.has('submitting'));
  assert.equal(q[1].key, `gk-${year}-xingce-dishiji-4`);
  assert.equal(q[2].paper, `省考/浙江/${year}/行测-a.md`);
  const items = [{ kind: 'new', label: '国考' }, { kind: 'new', label: '浙江' }];
  assert.equal(takeNext(items, '浙江').label, '浙江');
  assert.equal(takeNext(items, '浙江').label, '国考');
});

// ---------- gate + publish against a local bare origin ----------
const git = (repo, ...args) => execFileSync('git', ['-C', repo, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', ...args], { encoding: 'utf8' });
const REL = '国考/2025/行测-dishiji.md';
const IMG = Buffer.from('fake-png-bytes');
const IMG_REL = `国考/2025/assets-fenbi-123/${sha(IMG)}.png`;
const paperMd = n => '# 卷\n\n## 题目\n\n' + Array.from({ length: n }, (_, i) => `### 第 ${i + 1} 题\n\n题干。\n`).join('\n') +
  `\n![图](assets-fenbi-123/${sha(IMG)}.png)\n`;

async function world(t, { baseQuestions = 0 } = {}) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'fenbi-worker-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const origin = path.join(root, 'origin.git'), seed = path.join(root, 'seed'), integ = path.join(root, 'integ');
  execFileSync('git', ['init', '-q', '--bare', '-b', 'main', origin]);
  execFileSync('git', ['init', '-q', '-b', 'main', seed]);
  await fs.mkdir(path.join(seed, 'catalog'), { recursive: true });
  await fs.writeFile(path.join(seed, '.gitignore'), 'work/\n');
  let manifest = '';
  if (baseQuestions) {
    const md = paperMd(baseQuestions);
    await fs.mkdir(path.join(seed, '国考/2025'), { recursive: true });
    await fs.writeFile(path.join(seed, REL), md);
    manifest = JSON.stringify({ path: REL, sha256: sha(md) }) + '\n';
  }
  await fs.writeFile(path.join(seed, 'catalog/manifest.jsonl'), manifest);
  git(seed, 'add', '.'); git(seed, 'commit', '-qm', 'base'); git(seed, 'push', '-q', origin, 'main');
  execFileSync('git', ['clone', '-q', origin, integ]);
  git(integ, 'switch', '-qc', 'fenbi-integ');
  git(integ, 'config', 'user.name', 'F'); git(integ, 'config', 'user.email', 'f@example.invalid');
  const rightsFile = path.join(root, 'rights.json');
  await fs.writeFile(rightsFile, JSON.stringify({ schemaVersion: 1, allowGitHubStorage: true, evidence: 'synthetic fixture', sourceIds: [], coverAllCapturedSources: true }));
  return { root, origin, integ, rightsFile };
}

// Lands a paper the way promote does: paper + content-addressed image + manifest row + receipt in the candidate root.
async function land(w, { questions = 3, receiptQuestions = questions, grade = 'A', image = IMG } = {}) {
  const md = paperMd(questions);
  await fs.mkdir(path.join(w.integ, path.dirname(IMG_REL)), { recursive: true });
  await fs.writeFile(path.join(w.integ, REL), md);
  await fs.writeFile(path.join(w.integ, IMG_REL), image);
  await fs.writeFile(path.join(w.integ, 'catalog/manifest.jsonl'), JSON.stringify({ path: REL, sha256: sha(md) }) + '\n');
  const cand = path.join(w.integ, 'work/fenbi/batch-ingest/gk-2025-123');
  await fs.mkdir(cand, { recursive: true });
  await fs.writeFile(path.join(cand, 'receipt.json'), JSON.stringify({ sourceId: '123', path: REL, grade,
    counts: { sourceQuestions: receiptQuestions }, markdownSha256: sha(md) }));
}
const mainHead = w => execFileSync('git', ['--git-dir', w.origin, 'rev-parse', 'main'], { encoding: 'utf8' }).trim();

test('a gated batch is committed, pushed to the integration branch and fast-forwarded into main', async t => {
  const w = await world(t);
  await land(w);
  const before = mainHead(w);
  const r = await publish({ repo: w.integ, rightsFile: w.rightsFile, message: 'batch', autoMerge: true });
  assert.ok(r.committed);
  assert.equal(r.gate.ok, true, JSON.stringify(r.gate.reasons));
  assert.deepEqual([r.pushedBranch, r.pushedMain], [true, true]);
  assert.notEqual(mainHead(w), before);
  assert.match(execFileSync('git', ['--git-dir', w.origin, 'show', `main:${REL}`], { encoding: 'utf8' }), /第 3 题/u);
});

test('without AUTO_MERGE main is left alone even when the gate passes', async t => {
  const w = await world(t);
  await land(w);
  const before = mainHead(w);
  const r = await publish({ repo: w.integ, rightsFile: w.rightsFile, message: 'batch', autoMerge: false });
  assert.equal(r.gate.ok, true);
  assert.equal(r.pushedMain, false);
  assert.equal(mainHead(w), before);
});

test('the gate refuses a paper that lost questions against main', async t => {
  const w = await world(t, { baseQuestions: 5 });
  await land(w, { questions: 3 });
  const r = await publish({ repo: w.integ, rightsFile: w.rightsFile, message: 'batch', autoMerge: true });
  assert.equal(r.pushedMain, false);
  assert.match(r.gate.reasons.join('\n'), /question-count-regressed/u);
});

test('the gate refuses papers without a matching grade-A receipt, wrong counts, and mismatched image hashes', async t => {
  const w = await world(t);
  await land(w, { grade: 'C', receiptQuestions: 4, image: Buffer.from('other-bytes') });
  git(w.integ, 'add', '-A'); git(w.integ, 'commit', '-qm', 'x');
  const g = await fullGate({ repo: w.integ, base: 'origin/main', candidateRoot: path.join(w.integ, 'work/fenbi/batch-ingest'), rightsFile: w.rightsFile });
  const text = g.reasons.join('\n');
  assert.equal(g.ok, false);
  assert.match(text, /receipt-not-grade-A/u);
  assert.match(text, /question-anchors-invalid/u);
  assert.match(text, /image-sha-mismatch/u);

  await fs.writeFile(path.join(w.integ, REL), paperMd(3) + '\n改过\n');
  git(w.integ, 'commit', '-qam', 'edit');
  const g2 = await fullGate({ repo: w.integ, base: 'origin/main', candidateRoot: path.join(w.integ, 'work/fenbi/batch-ingest'), rightsFile: w.rightsFile });
  assert.match(g2.reasons.join('\n'), /no-matching-receipt/u);
});
