import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { promoteAll } from '../src/promote-all.mjs';

const sha = x => crypto.createHash('sha256').update(x).digest('hex');

async function fixture(t, { old = false, rights }) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'fenbi-promote-all-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const repo = path.join(root, 'repo'), candidateRoot = path.join(root, 'candidates'), cand = path.join(candidateRoot, 'p1');
  await fs.mkdir(path.join(repo, 'catalog'), { recursive: true });
  await fs.mkdir(path.join(cand, 'assets-fenbi-123'), { recursive: true });
  execFileSync('git', ['init', '-q', '-b', 'integ', repo]);
  await fs.writeFile(path.join(repo, 'catalog/manifest.jsonl'), '');
  const rel = '省考/浙江/2026/行测-C类.md', oldMd = '旧版\n';
  if (old) { await fs.mkdir(path.dirname(path.join(repo, rel)), { recursive: true }); await fs.writeFile(path.join(repo, rel), oldMd); }
  const md = '# 合成卷\n\n## 题目\n\n### 第 1 题\n\n题干。\n\n![图](assets-fenbi-123/q.png)\n';
  await fs.writeFile(path.join(cand, 'assets-fenbi-123/q.png'), 'img');
  await fs.writeFile(path.join(cand, 'paper.md'), md);
  await fs.writeFile(path.join(cand, 'receipt.json'), JSON.stringify({ sourceId: '123', path: rel, area: '浙江', year: 2026,
    subject: 'xingce', variant: 'C类', grade: 'A', counts: { sourceQuestions: 1 }, answerNumbers: [],
    markdownSha256: sha(md), oldSha256: old ? sha(oldMd) : null }));
  const rightsFile = path.join(root, 'rights.json');
  await fs.writeFile(rightsFile, JSON.stringify({ schemaVersion: 1, allowGitHubStorage: true, evidence: 'synthetic fixture', ...rights }));
  execFileSync('git', ['-C', repo, 'add', '.']);
  execFileSync('git', ['-C', repo, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'base']);
  return { repoRoot: repo, candidateRoot, rightsFile, rel, md };
}

test('a rights file covering all captured sources promotes candidates not listed by id', async t => {
  const f = await fixture(t, { rights: { sourceIds: [], coverAllCapturedSources: true } });
  const s = await promoteAll({ ...f, apply: true });
  assert.equal(s.promoted, 1);
  assert.equal(await fs.readFile(path.join(f.repoRoot, f.rel), 'utf8'), f.md);
  const again = await promoteAll({ ...f, apply: true });
  assert.deepEqual([again.pending, again.alreadyPromoted], [0, 1]);
});

test('without the cover-all flag an unlisted source stays blocked', async t => {
  const f = await fixture(t, { rights: { sourceIds: ['999'] } });
  const s = await promoteAll({ ...f, apply: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['explicit-publication-permission-required']);
});

test('two sources for one paper: only the one with more answers is promoted', async t => {
  const f = await fixture(t, { rights: { sourceIds: [], coverAllCapturedSources: true } });
  const second = path.join(f.candidateRoot, 'p2');
  await fs.cp(path.join(f.candidateRoot, 'p1'), second, { recursive: true });
  const receipt = JSON.parse(await fs.readFile(path.join(second, 'receipt.json'), 'utf8'));
  await fs.writeFile(path.join(second, 'receipt.json'), JSON.stringify({ ...receipt, answerNumbers: [1] }));
  const s = await promoteAll({ ...f, apply: true });
  assert.deepEqual([s.pending, s.promoted, s.duplicateSources], [1, 1, 1]);
  const again = await promoteAll({ ...f, apply: true });
  assert.deepEqual([again.pending, again.alreadyPromoted], [0, 1]);
});

test('an existing paper is replaced only with allowReplace', async t => {
  const f = await fixture(t, { old: true, rights: { sourceIds: ['123'] } });
  const blocked = await promoteAll({ ...f, apply: true });
  assert.ok(blocked.blocked['explicit-allow-replace-required']);
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.deepEqual([s.promoted, s.replaced], [1, 1]);
});

test('a manifest identity collision is blocked even with allowReplace', async t => {
  const f = await fixture(t, { rights: { sourceIds: ['123'] } });
  const row = { area: '浙江', year: '2026', subject: '行测', paper_type: 'C类', path: '省考/浙江/2026/行测-C类-旧.md' };
  await fs.writeFile(path.join(f.repoRoot, 'catalog/manifest.jsonl'), JSON.stringify(row) + '\n');
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['duplicate-identity-in-repository']);
  await assert.rejects(fs.readFile(path.join(f.repoRoot, f.rel)));
});

test('an existing target without a matching old SHA is never replaced by allowReplace', async t => {
  const f = await fixture(t, { old: true, rights: { sourceIds: ['123'] } });
  const receiptPath = path.join(f.candidateRoot, 'p1', 'receipt.json');
  const receipt = JSON.parse(await fs.readFile(receiptPath, 'utf8'));
  receipt.oldSha256 = null;
  await fs.writeFile(receiptPath, JSON.stringify(receipt));
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['existing-target-without-old-sha']);
  assert.equal(await fs.readFile(path.join(f.repoRoot, f.rel), 'utf8'), '旧版\n');
});

test('onlySourceIds scopes the batch and does not touch unlisted candidates', async t => {
  const f = await fixture(t, { rights: { sourceIds: ['999', '123'] } });
  const none = await promoteAll({ ...f, apply: true, onlySourceIds: ['999'] });
  assert.equal(none.pending, 0);
  assert.equal(none.promoted, 0);
  await assert.rejects(fs.readFile(path.join(f.repoRoot, f.rel)));
  const one = await promoteAll({ ...f, apply: true, onlySourceIds: ['123'] });
  assert.equal(one.promoted, 1);
});

test('dry-run reports preflightOk, never promoted', async t => {
  const f = await fixture(t, { rights: { sourceIds: ['123'] } });
  const s = await promoteAll({ ...f, apply: false });
  assert.equal(s.promoted, 0);
  assert.equal(s.preflightOk, 1);
  await assert.rejects(fs.readFile(path.join(f.repoRoot, f.rel)));
});

// --- canonical identity resolution (S3 2026-10-20) -------------------------
// A receipt may name a slug path that does not exist while the same paper lives
// in the manifest under its canonical name. Resolving is allowed only when the
// identity match is unique AND the old paper is real AND it does not shrink.

const CANON = '省考/浙江/2026/行测-C类-规范.md';

async function withCanonical(t, { oldQuestions = 1, ambiguous = false } = {}) {
  const f = await fixture(t, { rights: { sourceIds: ['123'] } });
  const oldMd = '# 旧规范卷\n\n' + Array.from({ length: oldQuestions }, (_, i) => `### 第 ${i + 1} 题\n\n旧题干。\n`).join('\n');
  const rows = [];
  if (ambiguous) {
    for (const p of [CANON, '省考/浙江/2026/行测-C类-另一.md']) {
      await fs.mkdir(path.dirname(path.join(f.repoRoot, p)), { recursive: true });
      await fs.writeFile(path.join(f.repoRoot, p), oldMd);
      rows.push({ area: '浙江', year: '2026', subject: '行测', paper_type: 'C类', path: p });
    }
  } else {
    await fs.mkdir(path.dirname(path.join(f.repoRoot, CANON)), { recursive: true });
    await fs.writeFile(path.join(f.repoRoot, CANON), oldMd);
    rows.push({ area: '浙江', year: '2026', subject: '行测', paper_type: 'C类', path: CANON });
  }
  await fs.writeFile(path.join(f.repoRoot, 'catalog/manifest.jsonl'), rows.map(r => JSON.stringify(r)).join('\n') + '\n');
  execFileSync('git', ['-C', f.repoRoot, 'add', '.']);
  execFileSync('git', ['-C', f.repoRoot, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'canonical']);
  return { ...f, oldMd, canon: CANON };
}

test('alternate path with a unique canonical identity and equal questions promotes', async t => {
  const f = await withCanonical(t, { oldQuestions: 1 });
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(s.promoted, 1);
  assert.equal(s.replaced, 1);
  assert.equal(s.identityResolved, 1);
  assert.equal(await fs.readFile(path.join(f.repoRoot, CANON), 'utf8'), f.md);
  // slug path is never created
  await assert.rejects(fs.readFile(path.join(f.repoRoot, f.rel)));
});

test('canonical resolution promotes when fenbi has MORE questions', async t => {
  const f = await withCanonical(t, { oldQuestions: 1 });
  assert.equal((await promoteAll({ ...f, apply: false, allowReplace: true })).preflightOk, 1);
});

test('canonical resolution blocks when fenbi has FEWER questions than the old paper', async t => {
  const f = await withCanonical(t, { oldQuestions: 3 });   // old 3, candidate 1
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['fenbi-has-fewer-questions-than-existing']);
  assert.equal(await fs.readFile(path.join(f.repoRoot, CANON), 'utf8'), f.oldMd);
});

test('canonical resolution requires allowReplace', async t => {
  const f = await withCanonical(t, { oldQuestions: 1 });
  const s = await promoteAll({ ...f, apply: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['explicit-allow-replace-required']);
});

test('an ambiguous identity match is blocked and never guessed', async t => {
  const f = await withCanonical(t, { oldQuestions: 1, ambiguous: true });
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['identity-ambiguous-in-manifest']);
  await assert.rejects(fs.readFile(path.join(f.repoRoot, f.rel)));
});

test('a stale old hash on the canonical target blocks the replacement', async t => {
  const f = await withCanonical(t, { oldQuestions: 1 });
  const rp = path.join(f.candidateRoot, 'p1', 'receipt.json');
  const receipt = JSON.parse(await fs.readFile(rp, 'utf8'));
  receipt.oldSha256 = 'deadbeef'.repeat(8);
  receipt.path = CANON;                       // pretend the receipt points at the canonical file
  await fs.writeFile(rp, JSON.stringify(receipt));
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['repository-paper-changed-since-candidate']);
});

test('re-running on unchanged sources yields zero further promotions', async t => {
  const f = await withCanonical(t, { oldQuestions: 1 });
  const first = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(first.promoted, 1);
  execFileSync('git', ['-C', f.repoRoot, 'add', '.']);
  execFileSync('git', ['-C', f.repoRoot, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'promoted']);
  const before = execFileSync('git', ['-C', f.repoRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const second = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(second.promoted, 0);
  assert.equal(second.alreadyPromoted, 1);
  assert.equal(execFileSync('git', ['-C', f.repoRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), before);
  assert.equal(execFileSync('git', ['-C', f.repoRoot, 'status', '--porcelain'], { encoding: 'utf8' }).trim(), '');
});
