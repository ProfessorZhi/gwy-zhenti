import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { speed, buildBoard, renderBoard } from '../src/pipeline-board.mjs';
import { listPending } from '../src/promote-all.mjs';

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
    assert.match(renderBoard(b), /最近 1 小时抓取/);

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
