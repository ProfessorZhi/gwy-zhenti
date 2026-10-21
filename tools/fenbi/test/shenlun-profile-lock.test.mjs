// Profile 锁的失败路径：浏览器起不来、或关闭上下文时报错，都必须释放「我们自己的」锁；
// 别人留下的锁一律不碰。全部用假 launcher，不启动真实浏览器、不访问网络。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { openSession } from '../src/browser.mjs';

const LOCK = '.fenbi-framework.lock';
const code = (name) => (error) => error.code === name;
const config = (profileDir) => ({ profileDir, entryUrl: 'https://www.fenbi.com/spa/tiku', channel: 'chromium' });

test('a failed browser launch releases our own profile lock', async (t) => {
  const profileDir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-lock-fail-'));
  t.after(() => fs.rm(profileDir, { recursive: true, force: true }));
  const launcher = { launchPersistentContext: async () => { throw new Error('synthetic launch failure'); } };
  await assert.rejects(openSession(config(profileDir), { headless: true, launcher }), code('BROWSER_START_FAILED'));
  await assert.rejects(fs.readFile(path.join(profileDir, LOCK), 'utf8'), (error) => error.code === 'ENOENT');
});

test('an owner lock is never removed or reused', async (t) => {
  const profileDir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-lock-owned-'));
  t.after(() => fs.rm(profileDir, { recursive: true, force: true }));
  const lockPath = path.join(profileDir, LOCK);
  await fs.writeFile(lockPath, 'someone-else:lock', { mode: 0o600 });
  const launcher = { launchPersistentContext: async () => { throw new Error('must not be called'); } };
  await assert.rejects(openSession(config(profileDir), { headless: true, launcher }), code('PROFILE_LOCKED'));
  assert.equal(await fs.readFile(lockPath, 'utf8'), 'someone-else:lock');
});

test('a failing context close still releases our lock', async (t) => {
  const profileDir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-lock-close-'));
  t.after(() => fs.rm(profileDir, { recursive: true, force: true }));
  const context = {
    setDefaultTimeout() {},
    async route() {},
    on() {},
    async newPage() { return { on() {} }; },
    async close() { throw new Error('synthetic close failure'); },
  };
  const launcher = { launchPersistentContext: async () => context };
  const session = await openSession(config(profileDir), { headless: true, launcher });
  const owner = await fs.readFile(path.join(profileDir, LOCK), 'utf8');
  assert.ok(owner.startsWith(`${process.pid}:`));
  await assert.rejects(session.close(), /synthetic close failure/u);
  await assert.rejects(fs.readFile(path.join(profileDir, LOCK), 'utf8'), (error) => error.code === 'ENOENT');
  // 第二次 close 是幂等的，不会再删别人的锁。
  await session.close();
  await assert.rejects(fs.readFile(path.join(profileDir, LOCK), 'utf8'), (error) => error.code === 'ENOENT');
});

test('a capture-mode session still refuses non-read methods before any request leaves', async (t) => {
  const profileDir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwy-fenbi-lock-guard-'));
  t.after(() => fs.rm(profileDir, { recursive: true, force: true }));
  let routeHandler = null;
  const context = {
    setDefaultTimeout() {},
    async route(_pattern, handler) { routeHandler = handler; },
    on() {},
    async newPage() { return { on() {} }; },
    async close() {},
  };
  const launcher = { launchPersistentContext: async () => context };
  const session = await openSession(config(profileDir), { headless: true, launcher });
  try {
    assert.equal(typeof routeHandler, 'function');
    const actions = [];
    const route = (method, url, navigation = false) => ({
      request: () => ({ url: () => url, method: () => method, isNavigationRequest: () => navigation }),
      abort: async (reason) => { actions.push(['abort', reason]); },
      continue: async () => { actions.push(['continue']); },
    });
    await routeHandler(route('POST', 'https://tiku.fenbi.com/api/shenlun/exercises/1'));
    await routeHandler(route('GET', 'https://example.com/', true));
    await routeHandler(route('GET', 'https://example.com/asset.js'));
    await routeHandler(route('GET', 'http://tiku.fenbi.com/api/shenlun/questions'));
    await routeHandler(route('GET', 'https://tiku.fenbi.com/api/shenlun/questions'));
    assert.deepEqual(actions, [
      ['abort', 'blockedbyclient'], ['abort', 'blockedbyclient'],
      ['abort', 'blockedbyclient'], ['abort', 'blockedbyclient'], ['continue'],
    ]);
    assert.deepEqual(session.guardStats, { blockedWrites: 1, blockedNavigation: 1, blockedHost: 1, blockedUrl: 1 });
  } finally {
    await session.close();
  }
});
