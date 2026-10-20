import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { buildProjection } from '../src/content-project.mjs';
import { autoMerge } from '../src/auto-main-content.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const git = (repo, args, opts = {}) => execFileSync('git', ['-C', repo, ...args], {encoding: 'utf8', ...opts}).trim();
const P1 = '省考/浙江/2020/行测-A.md';
const P2 = '省考/浙江/2021/行测-A.md';

function paper () {
  return [
    '## 题目', '### 第 1 题', '题干一的合成测试文本。', 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁',
    '【答案】A', '【解析】合成解析一',
    '### 第 2 题', '题干二的合成测试文本。', 'A. 甲', 'B. 乙', 'C. 丙', 'D. 丁',
    '【答案】B', '【解析】合成解析二', '', '![图](assets/图1.png)', ''
  ].join('\n');
}

async function setup () {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'content-project-'));
  const bare = path.join(root, 'origin.git');
  execFileSync('git', ['init', '--bare', '-q', bare]);
  const repo = path.join(root, 'repo');
  execFileSync('git', ['init', '-q', repo]);
  git(repo, ['config', 'user.email', 'test@example.invalid']);
  git(repo, ['config', 'user.name', 'Synthetic']);
  await fs.mkdir(path.join(repo, 'tools'), {recursive: true});
  await fs.writeFile(path.join(repo, 'tools/x.mjs'), 'export const base = 1;\n');
  await fs.mkdir(path.join(repo, 'catalog'), {recursive: true});
  await fs.writeFile(path.join(repo, 'catalog/manifest.jsonl'), '');
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'main']);
  git(repo, ['branch', '-M', 'main']);
  git(repo, ['remote', 'add', 'origin', bare]);
  git(repo, ['push', '-q', '-u', 'origin', 'main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  return {root, bare, repo};
}

async function put (repo, file, content) {
  const abs = path.join(repo, file);
  await fs.mkdir(path.dirname(abs), {recursive: true});
  await fs.writeFile(abs, content);
}

function row (p, sourceId, bytes) {
  return {path: p, sourceId, area: p.split('/')[1], year: Number(p.split('/')[2]), subject: p.includes('申论') ? 'shenlun' : 'xingce', paper_type: 'A', sha256: sha(bytes), bytes: bytes.length, declared_questions: 2, answer_blocks: 2};
}

async function trusted (root, reportText, licenseText) {
  const dir = path.join(root, 'trusted');
  await fs.mkdir(dir, {recursive: true});
  const report = Buffer.from(reportText), license = Buffer.from(licenseText);
  await fs.writeFile(path.join(dir, 'qa.txt'), report);
  await fs.writeFile(path.join(dir, 'license.txt'), license);
  return {dir, reportSha: sha(report), licenseSha: sha(license)};
}

function grant (paperPath, bytes, trusted, extra = {}) {
  return {
    sourceId: extra.sourceId || 'zj-' + paperPath.length,
    paperPath,
    blobSha256: sha(bytes),
    qa: {verdict: 'pass', reportPath: 'qa.txt', reportSha256: trusted.reportSha, reviewedAt: '2026-10-20T00:00:00Z'},
    rights: {basis: 'copyright-holder-license', evidencePath: 'license.txt', evidenceSha256: trusted.licenseSha, holder: 'synthetic'},
    ...extra
  };
}

async function addIntegration ({repo, papers}) {
  git(repo, ['checkout', '-q', '-b', 'integ']);
  await put(repo, 'tools/y.mjs', 'export const mixed = 1;\n');
  await put(repo, 'docs/note.md', 'mixed docs\n');
  const rows = [];
  for (const p of papers) {
    await put(repo, p.path, p.content);
    if (p.asset) await put(repo, path.posix.join(path.posix.dirname(p.path), p.asset.path), p.asset.content);
    const bytes = Buffer.from(p.content);
    rows.push(row(p.path, p.sourceId, bytes));
  }
  await put(repo, 'catalog/manifest.jsonl', rows.map(r => JSON.stringify(r)).join('\n') + '\n');
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'integration']);
  return git(repo, ['rev-parse', 'HEAD']);
}

test('E2E: one audited paper projects and fast-forwards bare main; code and unapproved paper never enter', async () => {
  const {root, bare, repo} = await setup();
  const trustedRoot = await trusted(root, 'independent QA pass', 'copyright holder license');
  const sourceHead = await addIntegration({repo, papers: [
    {path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}},
    {path: P2, sourceId: 'zj2', content: paper()}
  ]});
  const p1Bytes = Buffer.from(paper());
  const creds = {schemaVersion: 1, grants: [grant(P1, p1Bytes, trustedRoot, {sourceId: 'zj1'})]};
  const credentialsPath = path.join(root, 'creds.json');
  const settingsPath = path.join(root, 'settings.json');
  await fs.writeFile(credentialsPath, JSON.stringify(creds));
  await fs.writeFile(settingsPath, JSON.stringify({allowAutoMain: true}));

  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1, P2],
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']),
    credentialsPath, trustedRoot: trustedRoot.dir, apply: true, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, true, JSON.stringify(plan));
  assert.equal(plan.eligible, 1);
  assert.ok(plan.files.includes(P1));
  assert.ok(plan.files.includes('catalog/manifest.jsonl'));
  assert.ok(!plan.files.some(f => f.startsWith('tools/') || f.startsWith('docs/')));
  assert.ok(!plan.files.includes(P2));
  assert.ok(plan.rejected.some(r => r.path === P2));

  git(repo, ['checkout', '-q', '--detach', plan.commit]);
  const merged = await autoMerge({
    repo, expectedMainSha: git(repo, ['rev-parse', 'origin/main']), credentialsPath, settingsPath,
    trustedRoot: trustedRoot.dir, apply: true, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(merged.ok, true, JSON.stringify(merged));
  assert.equal(git(bare, ['rev-parse', 'refs/heads/main']), plan.commit);
  const tree = git(bare, ['-c', 'core.quotepath=false', 'ls-tree', '-r', '--name-only', 'refs/heads/main']);
  const files = tree.split('\n');
  assert.ok(files.includes(P1));
  assert.ok(!files.includes(P2));
  assert.ok(!files.includes('tools/y.mjs'));
  assert.ok(!files.includes('docs/note.md'));
  assert.ok(files.includes('tools/x.mjs'));
});

test('no credentials yields zero eligible papers and no commit', async () => {
  const {root, repo} = await setup();
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1], credentialsPath: null,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: null, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, false);
  assert.equal(plan.eligible, 0);
  assert.equal(plan.commit, undefined);
});

test('an existing main paper with a different blob is a conflict unless the base blob is bound', async () => {
  const {root, repo} = await setup();
  // Publish v1 on main first.
  const v1 = paper();
  await put(repo, P1, v1);
  await put(repo, 'catalog/manifest.jsonl', JSON.stringify(row(P1, 'zj1', Buffer.from(v1))) + '\n');
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'v1']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  const trustedRoot = await trusted(root, 'qa', 'license');
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: v1 + '\n修改', asset: null}]});
  const credentialsPath = path.join(root, 'creds-conflict.json');
  const v2 = Buffer.from(v1 + '\n修改');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, v2, trustedRoot, {sourceId: 'zj1'})]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, false);
  assert.ok(plan.rejected.some(r => r.path === P1 && r.reasons.some(x => x.startsWith('base-content-conflict'))), JSON.stringify(plan));
});

test('main race stops projection before any commit', async () => {
  const {root, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  const credentialsPath = path.join(root, 'creds-race.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1], credentialsPath,
    expectedMainSha: 'f'.repeat(40), trustedRoot: trustedRoot.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.stage, 'race');
  assert.equal(plan.commit, undefined);
});

test('manifest keeps unrelated main rows and only adds selected paper rows', async () => {
  const {root, repo} = await setup();
  const oldRow = {path: '省考/浙江/2019/行测-B.md', sourceId: 'old', sha256: 'a'.repeat(64), bytes: 1, declared_questions: 1, answer_blocks: 1};
  await put(repo, 'catalog/manifest.jsonl', JSON.stringify(oldRow) + '\n');
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'old manifest']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  const trustedRoot = await trusted(root, 'qa', 'license');
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  const credentialsPath = path.join(root, 'creds-manifest.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, apply: true, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, true, JSON.stringify(plan));
  const text = execFileSync('git', ['-C', repo, 'cat-file', 'blob', `${plan.commit}:catalog/manifest.jsonl`], {encoding: 'utf8'});
  const paths = text.trim().split('\n').map(l => JSON.parse(l).path);
  assert.ok(paths.includes(oldRow.path));
  assert.ok(paths.includes(P1));
  assert.equal(paths.filter(p => p === P1).length, 1);
});

test('duplicate identities and duplicate sourceIds are rejected', async () => {
  const {root, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  const twin = '省考/浙江/2020/行测-B.md';
  const sourceHead = await addIntegration({repo, papers: [
    {path: P1, sourceId: 'same', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}},
    {path: twin, sourceId: 'same', content: paper()}
  ]});
  const credentialsPath = path.join(root, 'creds-dup.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [
    grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'same'}),
    grant(twin, Buffer.from(paper()), trustedRoot, {sourceId: 'same'})
  ]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1, twin], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, false);
  assert.ok(plan.rejected.some(r => r.reasons.some(x => x.startsWith('duplicate-source-id') || x.startsWith('duplicate-paper-identity'))), JSON.stringify(plan));
});

test('escaping images and symlinked assets are rejected', async () => {
  const {root, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  const escaping = paper().replace('assets/图1.png', '../../../../etc/passwd');
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: escaping, asset: null}]});
  const credentialsPath = path.join(root, 'creds-img.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(escaping), trustedRoot, {sourceId: 'zj1'})]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, false);
  assert.ok(plan.rejected.some(r => r.reasons.some(x => x.startsWith('image-external-or-absolute') || x.startsWith('image-is-symlink'))), JSON.stringify(plan));

  // Symlinked asset in the source tree.
  const {root: root2, repo: repo2} = await setup();
  const trusted2 = await trusted(root2, 'qa', 'license');
  git(repo2, ['checkout', '-q', '-b', 'integ']);
  await put(repo2, P1, paper());
  await fs.mkdir(path.join(repo2, '省考/浙江/2020/assets'), {recursive: true});
  await fs.symlink('/etc/passwd', path.join(repo2, '省考/浙江/2020/assets/图1.png'));
  await put(repo2, 'catalog/manifest.jsonl', JSON.stringify(row(P1, 'zj1', Buffer.from(paper()))) + '\n');
  git(repo2, ['add', '-A']); git(repo2, ['commit', '-q', '-m', 'symlink integration']);
  const head2 = git(repo2, ['rev-parse', 'HEAD']);
  const creds2 = path.join(root2, 'creds-sym.json');
  await fs.writeFile(creds2, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trusted2, {sourceId: 'zj1'})]}));
  const symPlan = await buildProjection({
    repo: repo2, sourceRepo: repo2, sourceHead: head2, papers: [P1], credentialsPath: creds2,
    expectedMainSha: git(repo2, ['rev-parse', 'origin/main']), trustedRoot: trusted2.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(symPlan.ok, false);
  assert.ok(symPlan.rejected.some(r => r.reasons.some(x => x.startsWith('image-is-symlink'))), JSON.stringify(symPlan));
});

test('projection is disabled without AUTO_MAIN_CONTENT=1', async () => {
  const {repo} = await setup();
  const plan = await buildProjection({repo, sourceRepo: repo, sourceHead: 'main', papers: [P1], expectedMainSha: 'x', env: {}});
  assert.equal(plan.stage, 'disabled');
  assert.equal(plan.eligible, 0);
});

import { runAutoMain } from '../src/auto-main-run.mjs';

test('P1 unreadable main manifest fails closed instead of clearing it', async () => {
  const {root, repo} = await setup();
  await put(repo, 'catalog/manifest.jsonl', '{not json}\n');
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'corrupt manifest']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  const trustedRoot = await trusted(root, 'qa', 'license');
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  const credentialsPath = path.join(root, 'creds-p1.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, false);
  assert.ok(plan.reasons.some(r => r.startsWith('main-manifest-unreadable')), JSON.stringify(plan));
});

test('P2 assets of a base-conflicted paper never enter the projection', async () => {
  const {root, repo} = await setup();
  const v1 = paper();
  await put(repo, P2, v1);
  await put(repo, 'catalog/manifest.jsonl', JSON.stringify(row(P2, 'zj2', Buffer.from(v1))) + '\n');
  git(repo, ['add', '-A']); git(repo, ['commit', '-q', '-m', 'main p2']);
  git(repo, ['push', '-q', 'origin', 'HEAD:main']);
  git(repo, ['fetch', '-q', 'origin', 'main']);
  const trustedRoot = await trusted(root, 'qa', 'license');
  const p1Content = paper().replace('assets/图1.png', 'assets/p1.png');
  const p2Content = (v1 + '\n修改').replace('assets/图1.png', 'assets/p2.png');
  const sourceHead = await addIntegration({repo, papers: [
    {path: P1, sourceId: 'zj1', content: p1Content, asset: {path: 'assets/p1.png', content: Buffer.from('p1')}},
    {path: P2, sourceId: 'zj2', content: p2Content, asset: {path: 'assets/p2.png', content: Buffer.from('p2')}}
  ]});
  const credentialsPath = path.join(root, 'creds-p2.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [
    grant(P1, Buffer.from(p1Content), trustedRoot, {sourceId: 'zj1'}),
    grant(P2, Buffer.from(p2Content), trustedRoot, {sourceId: 'zj2'})
  ]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1, P2], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, apply: true, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, true, JSON.stringify(plan));
  assert.equal(plan.eligible, 1);
  assert.ok(plan.files.includes('省考/浙江/2020/assets/p1.png'));
  assert.ok(!plan.files.includes('省考/浙江/2021/assets/p2.png'));
  assert.ok(!plan.files.includes(P2));
});

test('P3 a branch name is not accepted as a pinned source head', async () => {
  const {root, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  const credentialsPath = path.join(root, 'creds-p3.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead: 'integ', papers: [P1], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, false);
  assert.ok(plan.reasons.includes('source-head-not-pinned-sha'));
});

test('P4 manifest declared_questions mismatch rejects the paper', async () => {
  const {root, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  // Rewrite the manifest on the integration commit with a wrong declared count.
  const badRow = row(P1, 'zj1', Buffer.from(paper()));
  badRow.declared_questions = 9;
  git(repo, ['checkout', '-q', 'integ']);
  await put(repo, 'catalog/manifest.jsonl', JSON.stringify(badRow) + '\n');
  git(repo, ['commit', '-q', '-am', 'bad counts']);
  const badHead = git(repo, ['rev-parse', 'HEAD']);
  const credentialsPath = path.join(root, 'creds-p4.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead: badHead, papers: [P1], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, false);
  assert.ok(plan.rejected.some(r => r.path === P1 && r.reasons.some(x => x.startsWith('manifest-questions-mismatch'))), JSON.stringify(plan));
});

test('P5 dry-run writes no objects and no refs', async () => {
  const {root, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  const sourceHead = await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  const credentialsPath = path.join(root, 'creds-p5.json');
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const refsBefore = git(repo, ['for-each-ref', 'refs/heads/s3/']);
  const objectsBefore = git(repo, ['count-objects', '-v']).split('\n')[0];
  const plan = await buildProjection({
    repo, sourceRepo: repo, sourceHead, papers: [P1], credentialsPath,
    expectedMainSha: git(repo, ['rev-parse', 'origin/main']), trustedRoot: trustedRoot.dir, apply: false, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(plan.ok, true, JSON.stringify(plan));
  assert.equal(plan.stage, 'dry-run');
  assert.equal(plan.commit, undefined);
  assert.equal(git(repo, ['for-each-ref', 'refs/heads/s3/']), refsBefore);
  assert.equal(git(repo, ['count-objects', '-v']).split('\n')[0], objectsBefore);
});

test('P6 default-OFF runner does not push and uncredentialed selection stays 0', async () => {
  const {root, bare, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  await addIntegration({repo, papers: [{path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}}]});
  const settingsPath = path.join(root, 'settings.json');
  const credentialsPath = path.join(root, 'creds-run.json');
  await fs.writeFile(settingsPath, JSON.stringify({allowAutoMain: true}));
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const mainBefore = git(bare, ['rev-parse', 'refs/heads/main']);

  const off = await runAutoMain({repo, sourceRepo: repo, sourceRef: 'integ', settingsPath, credentialsPath, trustedRoot: trustedRoot.dir, apply: true, env: {}});
  assert.equal(off.stage, 'disabled');
  assert.equal(git(bare, ['rev-parse', 'refs/heads/main']), mainBefore);

  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: []}));
  const none = await runAutoMain({repo, sourceRepo: repo, sourceRef: 'integ', settingsPath, credentialsPath, trustedRoot: trustedRoot.dir, apply: true, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(none.ok, false);
  assert.equal(none.eligible, 0);
  assert.equal(git(bare, ['rev-parse', 'refs/heads/main']), mainBefore);
});

test('P7 runner projects one audited paper in an isolated worktree and fast-forwards bare main', async () => {
  const {root, bare, repo} = await setup();
  const trustedRoot = await trusted(root, 'qa', 'license');
  const sourceHead = await addIntegration({repo, papers: [
    {path: P1, sourceId: 'zj1', content: paper(), asset: {path: 'assets/图1.png', content: Buffer.from('png')}},
    {path: P2, sourceId: 'zj2', content: paper()}
  ]});
  const settingsPath = path.join(root, 'settings.json');
  const credentialsPath = path.join(root, 'creds-run2.json');
  await fs.writeFile(settingsPath, JSON.stringify({allowAutoMain: true}));
  await fs.writeFile(credentialsPath, JSON.stringify({schemaVersion: 1, grants: [grant(P1, Buffer.from(paper()), trustedRoot, {sourceId: 'zj1'})]}));
  const result = await runAutoMain({repo, sourceRepo: repo, sourceRef: 'integ', settingsPath, credentialsPath, trustedRoot: trustedRoot.dir, apply: true, env: {AUTO_MAIN_CONTENT: '1'}});
  assert.equal(result.ok, true, JSON.stringify(result));
  const files = git(bare, ['-c', 'core.quotepath=false', 'ls-tree', '-r', '--name-only', 'refs/heads/main']).split('\n');
  assert.ok(files.includes(P1));
  assert.ok(!files.includes(P2));
  assert.ok(!files.includes('tools/y.mjs'));
  assert.ok(files.includes('tools/x.mjs'));
  assert.equal(git(bare, ['rev-parse', 'refs/heads/main']), result.projectionCommit);
});
