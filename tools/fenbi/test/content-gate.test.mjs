import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { checkContent } from '../src/content-gate.mjs';

const git = (repo, ...args) => execFileSync('git', ['-C', repo, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', ...args], { encoding: 'utf8' });
const write = async (repo, file, text) => { await fs.mkdir(path.dirname(path.join(repo, file)), { recursive: true }); await fs.writeFile(path.join(repo, file), text); };
const PAPER = '省考/浙江/2026/行测-C类.md';

async function fixture(t) {
  const repo = await fs.mkdtemp(path.join(os.tmpdir(), 'gate-'));
  t.after(() => fs.rm(repo, { recursive: true, force: true }));
  execFileSync('git', ['init', '-q', '-b', 'main', repo]);
  await write(repo, 'catalog/manifest.jsonl', '');
  await write(repo, 'README.md', 'x\n');
  git(repo, 'add', '.'); git(repo, 'commit', '-qm', 'base');
  git(repo, 'switch', '-qc', 'integ');
  return repo;
}
const addPaper = async (repo, { image = true, listed = true } = {}) => {
  await write(repo, PAPER, '### 第 1 题\n\n![图](../../../图片/p/q.png)\n');
  if (image) await write(repo, '图片/p/q.png', 'img');
  await write(repo, 'catalog/manifest.jsonl', listed ? JSON.stringify({ path: PAPER }) + '\n' : '');
  git(repo, 'add', '.'); git(repo, 'commit', '-qm', 'paper');
};

test('a content-only branch with listed papers and resolvable images passes', async t => {
  const repo = await fixture(t);
  await addPaper(repo);
  const r = await checkContent({ repo, base: 'main' });
  assert.equal(r.ok, true, JSON.stringify(r.reasons));
  assert.equal(r.papers, 1);
});

test('code changes, missing images, unlisted papers and deletions are refused', async t => {
  const repo = await fixture(t);
  await addPaper(repo, { image: false, listed: false });
  await write(repo, 'tools/x.mjs', 'code');
  git(repo, 'add', '.'); git(repo, 'commit', '-qm', 'code');
  const r = await checkContent({ repo, base: 'main' });
  assert.equal(r.ok, false);
  const text = r.reasons.join('\n');
  assert.match(text, /non-content-path: tools\/x\.mjs/u);
  assert.match(text, /missing-image/u);
  assert.match(text, /paper-not-in-manifest/u);

  git(repo, 'switch', '-q', 'main');
  await addPaper(repo);
  git(repo, 'switch', '-qc', 'integ2');
  git(repo, 'rm', '-q', PAPER); git(repo, 'commit', '-qm', 'delete');
  const d = await checkContent({ repo, base: 'main' });
  assert.match(d.reasons.join('\n'), /paper-deleted/u);
});

test('nothing to merge is not a pass', async t => {
  const repo = await fixture(t);
  const r = await checkContent({ repo, base: 'main' });
  assert.equal(r.ok, false);
});
