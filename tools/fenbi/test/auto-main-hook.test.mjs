import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const hook = path.join(here, '..', 'auto-main-hook.sh');
const runner = path.join(here, '..', 'src', 'auto-main-run.mjs');
const git = (repo, args) => execFileSync('git', ['-C', repo, ...args], {encoding: 'utf8'}).trim();

async function hookEnv (root, extra = {}) {
  const bin = path.join(root, 'bin');
  await fs.mkdir(bin, {recursive: true});
  const argsFile = path.join(root, 'args.txt');
  await fs.writeFile(path.join(bin, 'node'), '#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_FILE"\n', {mode: 0o755});
  const settings = path.join(root, 'settings.json');
  const credentials = path.join(root, 'credentials.json');
  const trusted = path.join(root, 'trusted');
  await fs.writeFile(settings, '{"allowAutoMain":true}\n');
  await fs.writeFile(credentials, '{"schemaVersion":1,"grants":[]}\n');
  await fs.mkdir(trusted, {recursive: true});
  const env = {
    ...process.env,
    PATH: bin + ':' + process.env.PATH,
    REPO: root,
    ARGS_FILE: argsFile,
    AUTO_MAIN_SETTINGS: settings,
    AUTO_MAIN_CREDENTIALS: credentials,
    AUTO_MAIN_TRUSTED_ROOT: trusted,
    ...extra
  };
  return {env, argsFile};
}

async function readArgs (file) {
  try { return (await fs.readFile(file, 'utf8')).trim().split('\n'); } catch { return null; }
}

test('hook applies only when AUTO_MAIN_APPLY is exactly 1', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hook-apply-'));
  for (const value of ['0', 'false', 'yes', '']) {
    const {env, argsFile} = await hookEnv(root, {AUTO_MAIN_CONTENT: '1', AUTO_MAIN_APPLY: value});
    execFileSync('bash', [hook], {env, encoding: 'utf8'});
    const args = await readArgs(argsFile);
    assert.ok(args, 'runner should be invoked');
    assert.ok(!args.includes('--apply'), `AUTO_MAIN_APPLY=${JSON.stringify(value)} must not add --apply`);
    await fs.rm(argsFile, {force: true});
  }
  const {env, argsFile} = await hookEnv(root, {AUTO_MAIN_CONTENT: '1', AUTO_MAIN_APPLY: '1'});
  execFileSync('bash', [hook], {env, encoding: 'utf8'});
  assert.ok((await readArgs(argsFile)).includes('--apply'));
});

test('hook is a no-op when AUTO_MAIN_CONTENT is unset', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hook-off-'));
  const {env, argsFile} = await hookEnv(root, {});
  delete env.AUTO_MAIN_CONTENT;
  const out = execFileSync('bash', [hook], {env, encoding: 'utf8'});
  assert.match(out, /auto-main disabled/);
  assert.equal(await readArgs(argsFile), null);
});

test('CLI exits nonzero for unknown or incomplete arguments', () => {
  const unknown = spawnSync(process.execPath, [runner, '--bogus'], {encoding: 'utf8'});
  assert.notEqual(unknown.status, 0);
  const missing = spawnSync(process.execPath, [runner, '--repo'], {encoding: 'utf8'});
  assert.notEqual(missing.status, 0);
});

test('a caller main pin mismatch is a race and never pushes', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'pin-race-'));
  const bare = path.join(root, 'origin.git');
  execFileSync('git', ['init', '--bare', '-q', bare]);
  const repo = path.join(root, 'repo');
  execFileSync('git', ['init', '-q', repo]);
  git(repo, ['config', 'user.email', 'test@example.invalid']);
  git(repo, ['config', 'user.name', 'Synthetic']);
  await fs.writeFile(path.join(repo, 'README.md'), 'x\n');
  git(repo, ['add', '.']); git(repo, ['commit', '-q', '-m', 'main']);
  git(repo, ['branch', '-M', 'main']);
  git(repo, ['remote', 'add', 'origin', bare]);
  git(repo, ['push', '-q', '-u', 'origin', 'main']);
  git(repo, ['branch', 'integ']);
  const settings = path.join(root, 'settings.json');
  const credentials = path.join(root, 'credentials.json');
  await fs.writeFile(settings, '{"allowAutoMain":true}\n');
  await fs.writeFile(credentials, JSON.stringify({schemaVersion: 1, grants: [{paperPath: '省考/浙江/2020/行测-A.md', sourceId: 'zj1', blobSha256: 'a'.repeat(64)}]}));
  const before = git(bare, ['rev-parse', 'refs/heads/main']);
  const {runAutoMain} = await import('../src/auto-main-run.mjs');
  const result = await runAutoMain({
    repo, sourceRepo: repo, sourceRef: 'integ', expectedMainSha: 'f'.repeat(40),
    settingsPath: settings, credentialsPath: credentials, trustedRoot: root,
    apply: true, env: {AUTO_MAIN_CONTENT: '1'}
  });
  assert.equal(result.stage, 'race');
  assert.equal(git(bare, ['rev-parse', 'refs/heads/main']), before);
});
