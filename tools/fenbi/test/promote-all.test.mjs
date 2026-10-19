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

test('an existing paper is replaced only with allowReplace', async t => {
  const f = await fixture(t, { old: true, rights: { sourceIds: ['123'] } });
  const blocked = await promoteAll({ ...f, apply: true });
  assert.ok(blocked.blocked['explicit-allow-replace-required']);
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.deepEqual([s.promoted, s.replaced], [1, 1]);
});
