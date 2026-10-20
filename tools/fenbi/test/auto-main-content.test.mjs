import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { checkContent } from '../src/content-gate.mjs';
import { autoMerge, loadSettings } from '../src/auto-main-content.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const git = (repo, args) => execFileSync('git', ['-C', repo, ...args], {encoding: 'utf8'}).trim();

const PAPER = '省考/浙江/2020/行测-A.md';

function paperMd ({placeholder = false, noExplanation = false} = {}) {
  const q1 = placeholder ? '未征集' : '题干一的合成测试文本。';
  return [
    '## 题目',
    '### 第 1 题', q1, 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁',
    '【答案】A', ...(noExplanation ? [] : ['【解析】合成解析一']),
    '### 第 2 题', '题干二的合成测试文本。', 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁',
    '【答案】B', '【解析】合成解析二', ''
  ].join('\n');
}

async function setup () {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'auto-main-'));
  const bare = path.join(root, 'origin.git');
  execFileSync('git', ['init', '--bare', '-q', bare]);
  const repo = path.join(root, 'repo');
  execFileSync('git', ['init', '-q', repo]);
  git(repo, ['config', 'user.email', 'test@example.invalid']);
  git(repo, ['config', 'user.name', 'Synthetic']);
  await fs.writeFile(path.join(repo, 'README.md'), 'synthetic repo\n');
  git(repo, ['add', '.']); git(repo, ['commit', '-q', '-m', 'main']);
  git(repo, ['branch', '-M', 'main']);
  git(repo, ['remote', 'add', 'origin', bare]);
  git(repo, ['push', '-q', '-u', 'origin', 'main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  git(repo, ['checkout', '-q', '-b', 'cand']);
  return {root, bare, repo};
}

async function writePaper (repo, md, {image = 'assets/图1.png', sourceId = 'zj2020'} = {}) {
  const abs = path.join(repo, PAPER);
  await fs.mkdir(path.dirname(abs), {recursive: true});
  await fs.writeFile(abs, md);
  if (image) {
    const img = path.join(repo, '省考/浙江/2020', image);
    await fs.mkdir(path.dirname(img), {recursive: true});
    await fs.writeFile(img, Buffer.from('synthetic-png-bytes'));
  }
}

async function writeManifest (repo, rows) {
  await fs.mkdir(path.join(repo, 'catalog'), {recursive: true});
  await fs.writeFile(path.join(repo, 'catalog/manifest.jsonl'), rows.map(r => JSON.stringify(r)).join('\n') + '\n');
}

async function manifestRow (repo, overrides = {}) {
  const bytes = await fs.readFile(path.join(repo, PAPER));
  return {path: PAPER, sourceId: 'zj2020', sha256: sha(bytes), bytes: bytes.length, questions: 2, answers: 2, ...overrides};
}

async function commitAll (repo) {
  git(repo, ['add', '-A']);
  git(repo, ['commit', '-q', '-m', 'candidate']);
}

async function writeJson (file, value) {
  await fs.mkdir(path.dirname(file), {recursive: true});
  await fs.writeFile(file, JSON.stringify(value));
}

function credentialsFor (repo, overrides = {}) {
  return fs.readFile(path.join(repo, PAPER)).then(bytes => ({
    schemaVersion: 1,
    grants: [{
      sourceId: 'zj2020',
      paperPath: PAPER,
      blobSha256: sha(bytes),
      qa: {verdict: 'pass', reportSha256: 'a'.repeat(64), reviewedAt: '2026-10-20T00:00:00Z'},
      rights: {basis: 'copyright-holder-license', evidenceSha256: 'b'.repeat(64), holder: 'synthetic'},
      ...overrides
    }]
  }));
}

test('1 legal pure content passes the gate', async () => {
  const {repo} = await setup();
  await writePaper(repo, `${paperMd()}\n![图](assets/图1.png)\n`);
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, true, result.reasons.join(','));
  assert.equal(result.papers, 1);
});

test('2 mixed code is rejected', async () => {
  const {repo} = await setup();
  await writePaper(repo, paperMd() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await fs.mkdir(path.join(repo, 'tools/fenbi/src'), {recursive: true});
  await fs.writeFile(path.join(repo, 'tools/fenbi/src/evil.mjs'), 'export default 1;\n');
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, false);
  assert.ok(result.reasons.some(r => r.startsWith('non-content-path')));
});

test('3 manifest sha256 mismatch is rejected', async () => {
  const {repo} = await setup();
  await writePaper(repo, paperMd() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo, {sha256: '0'.repeat(64)})]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, false);
  assert.ok(result.reasons.some(r => r.startsWith('manifest-sha256-mismatch')));
});

test('4 placeholder and missing explanation are rejected', async () => {
  const {repo} = await setup();
  await writePaper(repo, paperMd({placeholder: true, noExplanation: true}) + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, false);
  assert.ok(result.reasons.some(r => r.startsWith('placeholder-question')));
  assert.ok(result.reasons.some(r => r.startsWith('missing-explanation')));
});

test('5 missing and escaping images are rejected', async () => {
  const missing = await setup();
  await writePaper(missing.repo, `${paperMd()}\n![图](assets/nope.png)\n`);
  await writeManifest(missing.repo, [await manifestRow(missing.repo)]);
  await commitAll(missing.repo);
  const missingResult = await checkContent({repo: missing.repo, base: 'origin/main'});
  assert.equal(missingResult.ok, false);
  assert.ok(missingResult.reasons.some(r => r.startsWith('missing-image')));

  const escape = await setup();
  await writePaper(escape.repo, `${paperMd()}\n![图](../../../../etc/passwd)\n`);
  await writeManifest(escape.repo, [await manifestRow(escape.repo)]);
  await commitAll(escape.repo);
  const escapeResult = await checkContent({repo: escape.repo, base: 'origin/main'});
  assert.equal(escapeResult.ok, false);
  assert.ok(escapeResult.reasons.some(r => r.startsWith('image-external-or-absolute') || r.startsWith('image-escape')));
});

test('6 rights: disabled, missing credential, and self-authorization all fail closed', async () => {
  const {root, repo} = await setup();
  await writePaper(repo, paperMd() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const expectedMainSha = git(repo, ['rev-parse', 'origin/main']);
  const settingsPath = path.join(root, 'settings.json');
  const credentialsPath = path.join(root, 'credentials.json');
  await writeJson(settingsPath, {allowAutoMain: true});

  const off = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, env: {}});
  assert.equal(off.stage, 'disabled');
  const noSettings = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath: path.join(root, 'none.json'), env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(noSettings.stage, 'settings');
  const noCreds = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(noCreds.stage, 'rights');
  await writeJson(credentialsPath, {schemaVersion: 1, grants: []});
  const emptyCreds = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(emptyCreds.stage, 'rights');
  assert.ok(emptyCreds.reasons.includes(`rights-credential-missing:${PAPER}`));

  const bad = await credentialsFor(repo, {rights: {basis: 'user-self-authorization', evidenceSha256: 'b'.repeat(64)}});
  await writeJson(credentialsPath, bad);
  const selfAuth = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(selfAuth.stage, 'rights');
  assert.ok(selfAuth.reasons.some(r => r.startsWith('rights-basis-forbidden')));
});

test('7 main moved or non-fast-forward stops without pushing', async () => {
  const {repo} = await setup();
  await writePaper(repo, paperMd() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const settingsPath = path.join(repo, '..', 'settings.json');
  const credentialsPath = path.join(repo, '..', 'credentials.json');
  await writeJson(settingsPath, {allowAutoMain: true});
  await writeJson(credentialsPath, await credentialsFor(repo));

  const moved = await autoMerge({repo, expectedMainSha: 'f'.repeat(40), credentialsPath, settingsPath, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(moved.stage, 'race');
  assert.ok(moved.reasons.includes('main-moved'));

  // Advance origin/main on a sibling commit so the candidate is no longer a descendant.
  git(repo, ['checkout', '-q', '-b', 'sibling', 'origin/main']);
  await fs.writeFile(path.join(repo, 'README.md'), 'synthetic repo moved\n');
  git(repo, ['add', '.']); git(repo, ['commit', '-q', '-m', 'advance main']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  git(repo, ['checkout', '-q', 'cand']);
  const remoteSha = git(repo, ['rev-parse', 'origin/main']);
  const nonFf = await autoMerge({repo, expectedMainSha: remoteSha, credentialsPath, settingsPath, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(nonFf.ok, false);
  assert.ok(['fast-forward', 'gate', 'rights'].includes(nonFf.stage));
  assert.notEqual(git(repo, ['rev-parse', 'origin/main']), git(repo, ['rev-parse', 'HEAD']));
});

test('8 changing already-published main content without its base blob is refused', async () => {
  const {repo} = await setup();
  // Publish the paper on main first.
  await writePaper(repo, paperMd());
  await writeManifest(repo, [await manifestRow(repo)]);
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'base paper']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  // Candidate modifies it, with a credential that does not bind the base blob.
  await writePaper(repo, paperMd().replace('题干一', '题干一改'));
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const settingsPath = path.join(repo, '..', 'settings8.json');
  const credentialsPath = path.join(repo, '..', 'credentials8.json');
  await writeJson(settingsPath, {allowAutoMain: true});
  await writeJson(credentialsPath, await credentialsFor(repo));
  const result = await autoMerge({repo, expectedMainSha: git(repo, ['rev-parse', 'origin/main']), credentialsPath, settingsPath, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(result.ok, false);
  assert.equal(result.stage, 'rights');
  assert.ok(result.reasons.some(r => r.startsWith('base-content-conflict')));
});

test('settings require an explicit true flag', async () => {
  for (const value of [{}, {allowAutoMain: false}, {allowAutoMain: 'true'}]) {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'auto-main-settings-'));
    const file = path.join(root, 'settings.json');
    await fs.writeFile(file, JSON.stringify(value));
    assert.equal((await loadSettings(file)).ok, false);
  }
});
