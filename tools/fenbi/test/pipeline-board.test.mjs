import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { speed, buildBoard, renderBoard } from '../src/pipeline-board.mjs';
import { listPending, promoteAll } from '../src/promote-all.mjs';
import { execFileSync } from 'node:child_process';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const MIN = 60e3;

test('speed counts real papers per hour and separates idle gaps from active work', () => {
  const now = Date.parse('2026-10-19T12:00:00Z');
  // Three papers 1 minute apart, a 10-minute idle gap, then two more 1 minute apart.
  const t = [-15, -14, -13, -3, -2].map(m => now + m * MIN);
  const s = speed(t, now);
  assert.equal(s.captured, 5);
  assert.equal(s.lastHourPapers, 5);
  assert.equal(s.activeSecondsPerPaper, 60);
  assert.equal(s.idleGaps, 1);
  assert.equal(s.idleMinutesTotal, 10);
  assert.equal(s.lastCaptureMinutesAgo, 2);
});

test('board reads captures, answers, grades and promotion from local metadata', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'board-'));
  try {
    const work = path.join(root, 'work'), repo = path.join(root, 'repo');
    const paper = path.join(work, 'papers', 'p1');
    await fs.mkdir(paper, { recursive: true });
    await fs.writeFile(path.join(paper, 'checkpoint.json'), JSON.stringify({ updatedAt: new Date().toISOString() }));
    await fs.writeFile(path.join(paper, 'document.json'), JSON.stringify({ identity: { area: '深圳' },
      questions: [{ answerHtml: '<p>A</p>' }, { answerHtml: 'B' }] }));
    const md = Buffer.from('# paper\n');
    const cand = path.join(work, 'batch-ingest', 'p1');
    await fs.mkdir(cand, { recursive: true });
    await fs.writeFile(path.join(cand, 'receipt.json'), JSON.stringify({ area: '深圳', grade: 'A', path: '省考/深圳/2025/行测-统考.md', markdownSha256: sha(md) }));
    await fs.mkdir(path.join(repo, '省考/深圳/2025'), { recursive: true });
    await fs.writeFile(path.join(repo, '省考/深圳/2025/行测-统考.md'), md);

    const b = await buildBoard({ workDir: work, repoRoot: repo });
    assert.equal(b.speed.captured, 1);
    assert.equal(b.answered, 2);
    assert.equal(b.questions, 2);
    assert.deepEqual([b.A, b.C, b.promoted], [1, 0, 1]);
    assert.equal(b.regions['深圳'].withAnswers, 1);
    assert.match(renderBoard(b), /最近 1 小时首次采集/);

    // The same candidate is already promoted, so nothing is pending.
    const { pending, already } = await listPending(path.join(work, 'batch-ingest'), repo);
    assert.equal(pending.length, 0);
    assert.deepEqual(already, ['p1']);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});


test('board accepts split papers and ingest roots', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'board-split-'));
  try {
    const papers = path.join(root, 'owner/papers'), ingest = path.join(root, 's2/batch-ingest'), repo = path.join(root, 'repo');
    const paper = path.join(papers, 'p1');
    await fs.mkdir(paper, { recursive: true });
    await fs.writeFile(path.join(paper, 'checkpoint.json'), JSON.stringify({ updatedAt: new Date().toISOString() }));
    await fs.writeFile(path.join(paper, 'document.json'), JSON.stringify({ identity: { area: '深圳' }, questions: [{ answerHtml: 'A' }] }));
    const md = Buffer.from('# split\n');
    const cand = path.join(ingest, 'p1');
    await fs.mkdir(cand, { recursive: true });
    await fs.writeFile(path.join(cand, 'receipt.json'), JSON.stringify({ area: '深圳', grade: 'A', path: '省考/深圳/2025/行测-统考.md', markdownSha256: sha(md) }));
    await fs.mkdir(path.join(repo, '省考/深圳/2025'), { recursive: true });
    await fs.writeFile(path.join(repo, '省考/深圳/2025/行测-统考.md'), md);
    const b = await buildBoard({ workDir: path.join(root, 'empty-work'), repoRoot: repo, papersRoot: papers, ingestRoot: ingest });
    assert.equal(b.speed.captured, 1);
    assert.deepEqual([b.A, b.C, b.promoted, b.answered], [1, 0, 1, 1]);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});

// --- identity-resolved promotion counting (S3 2026-10-20) ------------------
// The board must use the same target resolution as promote-all, otherwise it reports
// the handful of direct-path publications and misses every canonical-path one.

async function boardFixture(t, { manifest = [], canonical = [], receipts = [] } = {}) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'board-ident-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const work = path.join(root, 'work'), repo = path.join(root, 'repo');
  await fs.mkdir(path.join(repo, 'catalog'), { recursive: true });
  await fs.writeFile(path.join(repo, 'catalog/manifest.jsonl'),
    manifest.map(r => JSON.stringify(r)).join('\n') + (manifest.length ? '\n' : ''));
  for (const { rel, content } of canonical) {
    await fs.mkdir(path.dirname(path.join(repo, rel)), { recursive: true });
    await fs.writeFile(path.join(repo, rel), content);
  }
  for (const rc of receipts) {
    const dir = path.join(work, 'batch-ingest', rc.name);
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(path.join(dir, 'receipt.json'), JSON.stringify(rc.receipt));
  }
  return { workDir: work, repoRoot: repo };
}

const CANON = '省考/浙江/2026/行测-C类.md';
const SLUG = '省考/浙江/2026/行测-c.md';
const MANIFEST_ROW = { area: '浙江', year: 2026, subject: '行测', paper_type: 'C类', path: CANON };

test('board counts a canonical identity-resolved publication', async t => {
  const md = Buffer.from('# 卷\n\n### 第 1 题\n\n题干\n');
  const f = await boardFixture(t, {
    manifest: [MANIFEST_ROW],
    canonical: [{ rel: CANON, content: md }],
    receipts: [{ name: 's1', receipt: { sourceId: '1', area: '浙江', year: 2026, subject: 'xingce', variant: 'C类',
      grade: 'A', path: SLUG, markdownSha256: sha(md), counts: { sourceQuestions: 1 }, answerNumbers: [1] } }],
  });
  const b = await buildBoard(f);
  assert.equal(b.promoted, 1);
  assert.equal(b.regions['浙江'].promoted, 1);
});

test('board counts one target once when several sources feed it', async t => {
  const md = Buffer.from('# 卷\n\n### 第 1 题\n\n题干\n');
  const f = await boardFixture(t, {
    manifest: [MANIFEST_ROW],
    canonical: [{ rel: CANON, content: md }],
    receipts: [
      { name: 'a', receipt: { sourceId: '10', area: '浙江', year: 2026, subject: 'xingce', variant: 'C类',
        grade: 'A', path: SLUG, markdownSha256: sha(md), counts: { sourceQuestions: 1 }, answerNumbers: [1] } },
      { name: 'b', receipt: { sourceId: '11', area: '浙江', year: 2026, subject: 'xingce', variant: 'C类',
        grade: 'A', path: SLUG, markdownSha256: sha(md), counts: { sourceQuestions: 1 }, answerNumbers: [] } },
    ],
  });
  const b = await buildBoard(f);
  assert.equal(b.A, 2, 'both candidates are still counted as A');
  assert.equal(b.promoted, 1, 'but the target is published once');
  assert.equal(b.regions['浙江'].promoted, 1);
});

test('board ignores a canonical target whose SHA does not match the winner', async t => {
  const md = Buffer.from('# candidate\n');
  const f = await boardFixture(t, {
    manifest: [MANIFEST_ROW],
    canonical: [{ rel: CANON, content: '# different content\n' }],
    receipts: [{ name: 's1', receipt: { sourceId: '1', area: '浙江', year: 2026, subject: 'xingce', variant: 'C类',
      grade: 'A', path: SLUG, markdownSha256: sha(md), counts: { sourceQuestions: 1 }, answerNumbers: [1] } }],
  });
  const b = await buildBoard(f);
  assert.equal(b.promoted, 0);
});

test('board refuses to guess when the manifest identity is ambiguous', async t => {
  const md = Buffer.from('# 卷\n');
  const f = await boardFixture(t, {
    manifest: [MANIFEST_ROW, { ...MANIFEST_ROW, path: '省考/浙江/2026/行测-C类-另一.md' }],
    canonical: [
      { rel: CANON, content: md },
      { rel: '省考/浙江/2026/行测-C类-另一.md', content: md },
    ],
    receipts: [{ name: 's1', receipt: { sourceId: '1', area: '浙江', year: 2026, subject: 'xingce', variant: 'C类',
      grade: 'A', path: SLUG, markdownSha256: sha(md), counts: { sourceQuestions: 1 }, answerNumbers: [1] } }],
  });
  const b = await buildBoard(f);
  assert.equal(b.promoted, 0);
  assert.equal(b.A, 1, 'the paper is still graded A, it is just not counted as published');
});

test('board region subtotals sum to the total across regions', async t => {
  const mdZ = Buffer.from('# 浙江\n'), mdJ = Buffer.from('# 江苏\n');
  const f = await boardFixture(t, {
    manifest: [
      MANIFEST_ROW,
      { area: '江苏', year: 2026, subject: '行测', paper_type: 'A类', path: '省考/江苏/2026/行测-A类.md' },
    ],
    canonical: [
      { rel: CANON, content: mdZ },
      { rel: '省考/江苏/2026/行测-A类.md', content: mdJ },
    ],
    receipts: [
      { name: 'z', receipt: { sourceId: '1', area: '浙江', year: 2026, subject: 'xingce', variant: 'C类',
        grade: 'A', path: SLUG, markdownSha256: sha(mdZ), counts: { sourceQuestions: 1 }, answerNumbers: [1] } },
      { name: 'j', receipt: { sourceId: '2', area: '江苏', year: 2026, subject: 'xingce', variant: 'A类',
        grade: 'A', path: '省考/江苏/2026/行测-a.md', markdownSha256: sha(mdJ), counts: { sourceQuestions: 1 }, answerNumbers: [1] } },
    ],
  });
  const b = await buildBoard(f);
  assert.equal(b.promoted, 2);
  const sum = Object.values(b.regions).reduce((a, r) => a + r.promoted, 0);
  assert.equal(sum, b.promoted, 'region subtotals must add up to the total');
  assert.equal(b.regions['浙江'].promoted, 1);
  assert.equal(b.regions['江苏'].promoted, 1);
});

// End-to-end parity: whatever promoteAll actually publishes, the board must count.
// This is the drift guard — it exercises both implementations rather than comparing
// their helper source, so a divergent normalisation fails here.
test('board agrees with promoteAll on an identity-resolved publication', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'board-parity-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const repo = path.join(root, 'repo'), work = path.join(root, 'work'), candRoot = path.join(work, 'batch-ingest');
  const cand = path.join(candRoot, 'p1');
  await fs.mkdir(path.join(repo, 'catalog'), { recursive: true });
  await fs.mkdir(path.join(cand, 'assets-fenbi-1'), { recursive: true });
  execFileSync('git', ['init', '-q', '-b', 'integ', repo]);

  const canon = '省考/浙江/2026/行测-C类.md', slug = '省考/浙江/2026/行测-c.md';
  const oldMd = '# 旧\n\n### 第 1 题\n\n旧题干\n';
  await fs.mkdir(path.dirname(path.join(repo, canon)), { recursive: true });
  await fs.writeFile(path.join(repo, canon), oldMd);
  await fs.writeFile(path.join(repo, 'catalog/manifest.jsonl'),
    JSON.stringify({ area: '浙江', year: 2026, subject: '行测', paper_type: 'C类', path: canon }) + '\n');

  const md = '# 新\n\n### 第 1 题\n\n新题干\n';
  await fs.writeFile(path.join(cand, 'assets-fenbi-1', 'q.png'), 'img');
  await fs.writeFile(path.join(cand, 'paper.md'), md + '\n![图](assets-fenbi-1/q.png)\n');
  await fs.writeFile(path.join(cand, 'receipt.json'), JSON.stringify({
    sourceId: '1', area: '浙江', year: 2026, subject: 'xingce', variant: 'C类', grade: 'A',
    path: slug, counts: { sourceQuestions: 1 }, answerNumbers: [1], markdownSha256: sha(md + '\n![图](assets-fenbi-1/q.png)\n') }));
  const rights = path.join(root, 'rights.json');
  await fs.writeFile(rights, JSON.stringify({ schemaVersion: 1, allowGitHubStorage: true, evidence: 'synthetic parity fixture', sourceIds: ['1'] }));
  execFileSync('git', ['-C', repo, 'add', '.']);
  execFileSync('git', ['-C', repo, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'base']);

  const s = await promoteAll({ repoRoot: repo, candidateRoot: candRoot, rightsFile: rights, apply: true, allowReplace: true });
  assert.equal(s.replaced, 1, 'promoteAll should resolve the canonical target');

  const b = await buildBoard({ workDir: work, repoRoot: repo });
  assert.equal(b.promoted, s.replaced, 'board must count what promoteAll published');
  assert.equal(b.regions['浙江'].promoted, 1);
});


test('backfill checkpoint and file updates never count as fresh captures',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'fenbi-board-backfill-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const work=path.join(root,'work'),repo=path.join(root,'repo');
  const paper=path.join(work,'papers','one');
  const now=Date.parse('2026-10-20T10:00:00Z');
  const oldCapture=new Date(now-3*3600e3).toISOString();
  await fs.mkdir(paper,{recursive:true});
  await fs.mkdir(repo,{recursive:true});
  const doc=path.join(paper,'document.json');
  await fs.writeFile(doc,JSON.stringify({identity:{id:'source-one',subject:'xingce',area:'浙江'},
    source:{capturedAt:oldCapture},questions:[{answerHtml:'A'}]}));
  await fs.writeFile(path.join(paper,'checkpoint.json'),JSON.stringify({updatedAt:new Date(now-60e3).toISOString()}));
  await fs.writeFile(path.join(paper,'run-summary.json'),JSON.stringify({at:oldCapture}));
  await fs.utimes(doc,new Date(now-60e3),new Date(now-60e3));
  const b=await buildBoard({workDir:work,repoRoot:repo,now});
  assert.equal(b.speed.captured,1);
  assert.equal(b.speed.lastHourPapers,0,'backfill cannot manufacture a newly captured paper');
  assert.equal(b.speed.captureTimeUnknown,0);
  assert.equal(b.speed.lastCaptureMinutesAgo,180);
});

test('missing original capture date stays unknown rather than using mutable mtime',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'fenbi-board-unknown-time-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const work=path.join(root,'work'),repo=path.join(root,'repo'),paper=path.join(work,'papers','one');
  const now=Date.parse('2026-10-20T10:00:00Z');
  await fs.mkdir(paper,{recursive:true});
  await fs.mkdir(repo,{recursive:true});
  const doc=path.join(paper,'document.json');
  await fs.writeFile(doc,JSON.stringify({identity:{id:'source-one',subject:'xingce',area:'浙江'},
    questions:[{answerHtml:'A'}]}));
  await fs.writeFile(path.join(paper,'checkpoint.json'),JSON.stringify({updatedAt:new Date(now-60e3).toISOString()}));
  await fs.utimes(doc,new Date(now-60e3),new Date(now-60e3));
  const b=await buildBoard({workDir:work,repoRoot:repo,now});
  assert.equal(b.speed.captured,1);
  assert.equal(b.speed.captureTimeUnknown,1);
  assert.equal(b.speed.lastHourPapers,0);
  assert.equal(b.speed.lastCaptureMinutesAgo,null);
  assert.match(renderBoard(b),/首次采集时间未知/);
});


test('board counts a duplicated subject-and-source ID only once',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'fenbi-board-source-dedup-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const work=path.join(root,'work'),repo=path.join(root,'repo');
  const now=Date.parse('2026-10-20T10:00:00Z');
  await fs.mkdir(repo,{recursive:true});
  for(const folder of ['copy-one','copy-two']){
    const paper=path.join(work,'papers',folder);
    await fs.mkdir(paper,{recursive:true});
    await fs.writeFile(path.join(paper,'document.json'),JSON.stringify({
      identity:{id:'123',subject:'xingce',area:'浙江'},
      source:{capturedAt:'2026-10-20T09:30:00Z'},
      questions:[{answerHtml:'A'}]
    }));
  }
  const b=await buildBoard({workDir:work,repoRoot:repo,now});
  assert.equal(b.speed.captured,1);
  assert.equal(b.speed.lastHourPapers,1);
  assert.equal(b.speed.duplicateSourceDirs,1);
  assert.equal(b.regions['浙江'].captured,1);
});

test('naive timezone and recreated checkpoint timestamp never manufacture a fresh capture',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'fenbi-board-naive-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const work=path.join(root,'work'),repo=path.join(root,'repo'),paper=path.join(work,'papers','one');
  const now=Date.parse('2026-10-20T10:00:00Z');
  await fs.mkdir(paper,{recursive:true});
  await fs.mkdir(repo,{recursive:true});
  await fs.writeFile(path.join(paper,'document.json'),JSON.stringify({
    identity:{id:'123',subject:'xingce',area:'浙江'},
    source:{capturedAt:'2026-10-20T09:59:00'},
    questions:[{answerHtml:'A'}]
  }));
  await fs.writeFile(path.join(paper,'checkpoint.json'),JSON.stringify({
    updatedAt:'2026-10-20T09:59:00Z',createdAt:'2026-10-20T09:59:00Z'
  }));
  const b=await buildBoard({workDir:work,repoRoot:repo,now});
  assert.equal(b.speed.captured,1);
  assert.equal(b.speed.lastHourPapers,0);
  assert.equal(b.speed.captureTimeUnknown,1);
  assert.match(renderBoard(b),/首次采集时间未知/);
});

test('explicit timezone offset is accepted as first-capture evidence',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'fenbi-board-timezone-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const work=path.join(root,'work'),repo=path.join(root,'repo'),paper=path.join(work,'papers','one');
  const now=Date.parse('2026-10-20T10:00:00Z');
  await fs.mkdir(paper,{recursive:true});
  await fs.mkdir(repo,{recursive:true});
  await fs.writeFile(path.join(paper,'document.json'),JSON.stringify({
    identity:{id:'123',subject:'xingce',area:'浙江'},
    source:{capturedAt:'2026-10-20T17:30:00+08:00'},
    questions:[{answerHtml:'A'}]
  }));
  const b=await buildBoard({workDir:work,repoRoot:repo,now});
  assert.equal(b.speed.lastHourPapers,1);
  assert.equal(b.speed.captureTimeUnknown,0);
});
