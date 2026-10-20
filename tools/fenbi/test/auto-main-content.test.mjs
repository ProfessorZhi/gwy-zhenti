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

function inlinePaper ({placeholder = false, noExplanation = false} = {}) {
  return [
    '## 题目', '### 第 1 题', placeholder ? '未征集' : '题干一的合成测试文本。',
    'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁', '【答案】A', ...(noExplanation ? [] : ['【解析】合成解析一']),
    '### 第 2 题', '题干二的合成测试文本。', 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁',
    '【答案】B', '【解析】合成解析二', ''
  ].join('\n');
}

function schemaAPaper () {
  return [
    '## 题目', '### 第 1 题', '题干一的合成测试文本。', 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁',
    '### 第 2 题', '题干二的合成测试文本。', 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁', '',
    '<details><summary>第 1 题</summary>', '',
    '**参考答案（粉笔题库参考内容）**', '', 'A', '', '**解析**', '', '合成解析一', '', '</details>', '',
    '<details><summary>第 2 题</summary>', '',
    '**参考答案（粉笔题库参考内容）**', '', 'B', '', '**解析**', '', '合成解析二', '', '</details>', ''
  ].join('\n');
}

function schemaBPaper () {
  return [
    '## 题目', '### 第 1 题', '题干一的合成测试文本。', '- **A**. 甲', '- **B**. 乙', '- **C**. 丙', '- **D**. 丁',
    '### 第 2 题', '题干二的合成测试文本。', '- **A**. 甲', '- **B**. 乙', '- **C**. 丙', '- **D**. 丁', '',
    '<details><summary>第 1 题</summary>', '**答案**：A', '**解析**：合成解析一', '</details>',
    '<details><summary>第 2 题</summary>', '**答案**：B', '来源参考解析：合成解析二', '</details>', ''
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

async function writePaper (repo, md, {image = 'assets/图1.png'} = {}) {
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
  return {
    path: PAPER, sourceId: 'zj2020', sha256: sha(bytes), bytes: bytes.length,
    declared_questions: 2, answer_blocks: 2, ...overrides
  };
}

async function commitAll (repo) {
  git(repo, ['add', '-A']);
  git(repo, ['commit', '-q', '-m', 'candidate']);
}

async function writeJson (file, value) {
  await fs.mkdir(path.dirname(file), {recursive: true});
  await fs.writeFile(file, JSON.stringify(value));
}

async function trustedCreds (root, repo, overrides = {}) {
  const dir = path.join(root, 'trusted');
  await fs.mkdir(dir, {recursive: true});
  const report = Buffer.from('independent synthetic QA report');
  const license = Buffer.from('synthetic copyright holder license');
  await fs.writeFile(path.join(dir, 'qa.txt'), report);
  await fs.writeFile(path.join(dir, 'license.txt'), license);
  const bytes = await fs.readFile(path.join(repo, PAPER));
  return {
    trustedRoot: dir,
    value: {
      schemaVersion: 1,
      grants: [{
        sourceId: 'zj2020',
        paperPath: PAPER,
        blobSha256: sha(bytes),
        qa: {verdict: 'pass', reportPath: 'qa.txt', reportSha256: sha(report), reviewedAt: '2026-10-20T00:00:00Z'},
        rights: {basis: 'copyright-holder-license', evidencePath: 'license.txt', evidenceSha256: sha(license), holder: 'synthetic'},
        ...overrides
      }]
    }
  };
}

test('1 legal inline content passes the gate', async () => {
  const {repo} = await setup();
  await writePaper(repo, `${inlinePaper()}\n![图](assets/图1.png)\n`);
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, true, result.reasons.join(','));
});

test('2 mixed code is rejected', async () => {
  const {repo} = await setup();
  await writePaper(repo, inlinePaper() + '\n![图](assets/图1.png)\n');
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
  await writePaper(repo, inlinePaper() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo, {sha256: '0'.repeat(64)})]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, false);
  assert.ok(result.reasons.some(r => r.startsWith('manifest-sha256-mismatch')));
});

test('4 placeholder and missing explanation are rejected', async () => {
  const {repo} = await setup();
  await writePaper(repo, inlinePaper({placeholder: true, noExplanation: true}) + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, false);
  assert.ok(result.reasons.some(r => r.startsWith('placeholder-question')));
  assert.ok(result.reasons.some(r => r.startsWith('missing-explanation')));
});

test('5 missing and escaping images are rejected', async () => {
  const missing = await setup();
  await writePaper(missing.repo, `${inlinePaper()}\n![图](assets/nope.png)\n`);
  await writeManifest(missing.repo, [await manifestRow(missing.repo)]);
  await commitAll(missing.repo);
  const missingResult = await checkContent({repo: missing.repo, base: 'origin/main'});
  assert.ok(missingResult.reasons.some(r => r.startsWith('missing-image')));

  const escape = await setup();
  await writePaper(escape.repo, `${inlinePaper()}\n![图](../../../../etc/passwd)\n`);
  await writeManifest(escape.repo, [await manifestRow(escape.repo)]);
  await commitAll(escape.repo);
  const escapeResult = await checkContent({repo: escape.repo, base: 'origin/main'});
  assert.ok(escapeResult.reasons.some(r => r.startsWith('image-external-or-absolute') || r.startsWith('image-escape')));
});

test('6 schema A (A. options + independent <details> answers) passes', async () => {
  const {repo} = await setup();
  await writePaper(repo, schemaAPaper());
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, true, result.reasons.join(','));
});

test('7 schema B (- **A**. options + **答案**/**解析**) passes', async () => {
  const {repo} = await setup();
  await writePaper(repo, schemaBPaper());
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, true, result.reasons.join(','));
});

test('8 申论 material containing A-D is not mistaken for options', async () => {
  const {repo} = await setup();
  const md = [
    '## 给定材料', '材料中列举 A. 甲、B. 乙、C. 丙、D. 丁 四种说法。', '',
    '## 题目', '### 第 1 题', '请概括材料要点。', '',
    '<details><summary>第 1 题</summary>', '**答案**：合成要点', '**解析**：合成解析', '</details>', ''
  ].join('\n');
  await fs.mkdir(path.join(repo, '省考/浙江/2020'), {recursive: true});
  await fs.writeFile(path.join(repo, '省考/浙江/2020/申论-A.md'), md);
  await fs.mkdir(path.join(repo, 'catalog'), {recursive: true});
  const bytes = await fs.readFile(path.join(repo, '省考/浙江/2020/申论-A.md'));
  await writeManifest(repo, [{path: '省考/浙江/2020/申论-A.md', sourceId: 'zj2020-sl', sha256: sha(bytes), bytes: bytes.length, declared_questions: 1, answer_blocks: 1}]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, true, result.reasons.join(','));
});

test('9 last question does not absorb a trailing answer area', async () => {
  const {repo} = await setup();
  const md = [
    '## 题目', '### 第 1 题', '题干一。', 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁', '',
    '## 参考答案', '**答案**：A', '**解析**：合成解析', ''
  ].join('\n');
  await writePaper(repo, md);
  await writeManifest(repo, [await manifestRow(repo, {declared_questions: 1, answer_blocks: 1})]);
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, false);
  assert.ok(result.reasons.some(r => r.startsWith('missing-answer:1')), result.reasons.join(','));
});

test('10 image-only and manifest-only diffs are rejected', async () => {
  const imageOnly = await setup();
  await fs.mkdir(path.join(imageOnly.repo, '图片'), {recursive: true});
  await fs.writeFile(path.join(imageOnly.repo, '图片/x.png'), Buffer.from('x'));
  await commitAll(imageOnly.repo);
  const imageResult = await checkContent({repo: imageOnly.repo, base: 'origin/main'});
  assert.ok(imageResult.reasons.includes('no-papers-changed'), imageResult.reasons.join(','));

  const manifestOnly = await setup();
  await writeManifest(manifestOnly.repo, [{path: '省考/浙江/2020/行测-A.md', sha256: 'a'.repeat(64), bytes: 1, declared_questions: 1, answer_blocks: 1}]);
  await commitAll(manifestOnly.repo);
  const manifestResult = await checkContent({repo: manifestOnly.repo, base: 'origin/main'});
  assert.ok(manifestResult.reasons.includes('no-papers-changed'));
});

test('11 symlinked changed path is rejected', async () => {
  const {repo} = await setup();
  await fs.mkdir(path.join(repo, '图片'), {recursive: true});
  await fs.symlink('/etc/passwd', path.join(repo, '图片/link.png'));
  await commitAll(repo);
  const result = await checkContent({repo, base: 'origin/main'});
  assert.equal(result.ok, false);
  assert.ok(result.reasons.some(r => r.startsWith('changed-path-symlink')), result.reasons.join(','));
});

test('12 rights: disabled, missing credential, forged report, self-authorization fail closed', async () => {
  const {root, repo} = await setup();
  await writePaper(repo, inlinePaper() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const expectedMainSha = git(repo, ['rev-parse', 'origin/main']);
  const settingsPath = path.join(root, 'settings.json');
  const credentialsPath = path.join(root, 'credentials.json');
  await writeJson(settingsPath, {allowAutoMain: true});
  const creds = await trustedCreds(root, repo);

  assert.equal((await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, env: {}})).stage, 'disabled');

  await writeJson(credentialsPath, {schemaVersion: 1, grants: []});
  const empty = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, trustedRoot: creds.trustedRoot, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.ok(empty.reasons.includes(`rights-credential-missing:${PAPER}`));

  const forged = await trustedCreds(root, repo, {qa: {verdict: 'pass', reportPath: 'qa.txt', reportSha256: 'c'.repeat(64), reviewedAt: '2026-10-20T00:00:00Z'}});
  await writeJson(credentialsPath, forged.value);
  const forgedResult = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, trustedRoot: forged.trustedRoot, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.ok(forgedResult.reasons.some(r => r.startsWith('qa-report-sha-mismatch')), forgedResult.reasons.join(','));

  const selfAuth = await trustedCreds(root, repo, {rights: {basis: 'user-self-authorization', evidencePath: 'license.txt', evidenceSha256: creds.value.grants[0].rights.evidenceSha256}});
  await writeJson(credentialsPath, selfAuth.value);
  const selfResult = await autoMerge({repo, expectedMainSha, credentialsPath, settingsPath, trustedRoot: selfAuth.trustedRoot, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.ok(selfResult.reasons.some(r => r.startsWith('rights-basis-forbidden')));
});

test('13 main moved or non-fast-forward stops without pushing', async () => {
  const {root, repo} = await setup();
  await writePaper(repo, inlinePaper() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const settingsPath = path.join(root, 'settings.json');
  const credentialsPath = path.join(root, 'credentials.json');
  await writeJson(settingsPath, {allowAutoMain: true});
  const creds = await trustedCreds(root, repo);
  await writeJson(credentialsPath, creds.value);

  const moved = await autoMerge({repo, expectedMainSha: 'f'.repeat(40), credentialsPath, settingsPath, trustedRoot: creds.trustedRoot, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(moved.stage, 'race');
  assert.ok(moved.reasons.includes('main-moved'));

  git(repo, ['checkout', '-q', '-b', 'sibling', 'origin/main']);
  await fs.writeFile(path.join(repo, 'README.md'), 'synthetic repo moved\n');
  git(repo, ['add', '.']); git(repo, ['commit', '-q', '-m', 'advance main']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  git(repo, ['checkout', '-q', 'cand']);
  const remoteSha = git(repo, ['rev-parse', 'origin/main']);
  const result = await autoMerge({repo, expectedMainSha: remoteSha, credentialsPath, settingsPath, trustedRoot: creds.trustedRoot, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(result.ok, false);
  assert.notEqual(git(repo, ['rev-parse', 'origin/main']), git(repo, ['rev-parse', 'HEAD']));
});

test('14 changing already-published main content without its base blob is refused', async () => {
  const {root, repo} = await setup();
  await writePaper(repo, inlinePaper());
  await writeManifest(repo, [await manifestRow(repo)]);
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'base paper']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  await writePaper(repo, inlinePaper().replace('题干一', '题干一改'));
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const settingsPath = path.join(root, 'settings14.json');
  const credentialsPath = path.join(root, 'credentials14.json');
  await writeJson(settingsPath, {allowAutoMain: true});
  const creds = await trustedCreds(root, repo);
  await writeJson(credentialsPath, creds.value);
  const result = await autoMerge({repo, expectedMainSha: git(repo, ['rev-parse', 'origin/main']), credentialsPath, settingsPath, trustedRoot: creds.trustedRoot, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(result.stage, 'rights');
  assert.ok(result.reasons.some(r => r.startsWith('base-content-conflict')));
});

test('15 apply:true fast-forwards the local bare main', async () => {
  const {root, bare, repo} = await setup();
  await writePaper(repo, inlinePaper() + '\n![图](assets/图1.png)\n');
  await writeManifest(repo, [await manifestRow(repo)]);
  await commitAll(repo);
  const settingsPath = path.join(root, 'settings15.json');
  const credentialsPath = path.join(root, 'credentials15.json');
  await writeJson(settingsPath, {allowAutoMain: true});
  const creds = await trustedCreds(root, repo);
  await writeJson(credentialsPath, creds.value);
  const head = git(repo, ['rev-parse', 'HEAD']);
  const result = await autoMerge({
    repo, expectedMainSha: git(repo, ['rev-parse', 'origin/main']), credentialsPath, settingsPath,
    trustedRoot: creds.trustedRoot, apply: true, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.stage, 'pushed');
  assert.equal(git(bare, ['rev-parse', 'refs/heads/main']), head);
});

test('settings require an explicit true flag', async () => {
  for (const value of [{}, {allowAutoMain: false}, {allowAutoMain: 'true'}]) {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'auto-main-settings-'));
    const file = path.join(root, 'settings.json');
    await fs.writeFile(file, JSON.stringify(value));
    assert.equal((await loadSettings(file)).ok, false);
  }
});
