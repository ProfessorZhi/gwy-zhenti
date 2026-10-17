import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { newQueue, temporary, makeConfig } from './helpers.mjs';
import {
  classifyObservation, importObservations, importObservationDirectory, loadAllowlist, validateObservationHandoff,
} from '../src/observation.mjs';
import { digest } from '../src/fsutil.mjs';

const SHA = (char) => char.repeat(64);

function observation(overrides = {}) {
  return {
    paperSourceId: '9000001',
    title: '浙江2026行测C类',
    subject: 'xingce',
    area: '浙江',
    year: 2026,
    variant: 'C类',
    route: {
      kind: 'existing_practice',
      url: 'https://www.fenbi.com/spa/tiku/exam/9000001?labelId=1',
      urlObserved: true,
      contentStatus: 'observed',
      questionCount: 100,
      evidence: [{ type: 'observed_ui', ref: 'synthetic owner observed this practice' }],
    },
    rights: {
      category: 'observed_ui',
      license: null,
      redistribution: 'local_only',
      evidence: [{ type: 'observed_ui', ref: 'synthetic owner observed this practice' }],
    },
    images: [{ ref: 'material/q1.png', sourceUrl: 'https://img.fbstatic.cn/q1.png', sha256: SHA('a') }],
    ...overrides,
  };
}

function handoff(observations) {
  return {
    schemaVersion: 1,
    kind: 'gwy-zhenti-source-observation',
    producer: { agent: 'synthetic-browser-owner', at: '2026-10-17T04:00:00.000Z' },
    permissions: { browserProfile: false, cookies: false, tokens: false },
    observations,
  };
}

async function allowlist(ids = ['9000001', '9000002', '9000003', '9000004']) {
  const dir = await fs.mkdtemp(path.join(process.env.TMPDIR ?? '/tmp', 'allow-'));
  const file = path.join(dir, 'allowlist.json');
  await fs.writeFile(file, JSON.stringify({ schemaVersion: 1, sourceIds: ids.map((id) => ({ id })) }));
  return { file, dir, value: await loadAllowlist(file) };
}

test('only an allowlisted, observed, reproducible existing practice becomes capture_ready', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  const list = await allowlist();
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const item = classifyObservation(observation(), { allowlist: list.value, config, producer: 'owner' });
  assert.equal(item.classification, 'capture_ready');
  assert.equal(item.reason, 'existing-practice-observed-and-authorized');
  assert.equal(item.input.url, 'https://www.fenbi.com/spa/tiku/exam/9000001?labelId=1');
  assert.equal(item.input.sourceCategory, 'observed_ui');
  assert.equal(item.input.redistribution, 'local_only');
  assert.ok(item.warnings.includes('title-differs-from-allowlist') === false);
  assert.match(item.version, /^obs-v1-[a-f0-9]{16}$/);
  assert.equal(item.urlDigest, digest(item.input.url).slice(0, 16));
  assert.equal(item.input.images[0].sha256, SHA('a'));
});

test('unauthorized, incomplete, placeholder and unknown observations never produce a capture input', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  const list = await allowlist();
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const cases = [
    [observation({ paperSourceId: '9999999' }), 'needs_initialization_review', /source-not-in-local-allowlist/],
    [observation({ route: { ...observation().route, kind: 'not_initialized', url: null } }), 'needs_initialization_review', /exercise-not-initialized/],
    [observation({ route: { ...observation().route, urlObserved: false } }), 'needs_route_review', /url-not-observed/],
    [observation({ route: { ...observation().route, url: null } }), 'needs_route_review', /url-missing/],
    [observation({ route: { ...observation().route, contentStatus: 'placeholder' } }), 'observed_catalog', /placeholder-content-not-captured/],
    [observation({ route: { ...observation().route, contentStatus: 'unknown' } }), 'observed_catalog', /unknown-content-not-captured/],
    [observation({ route: { ...observation().route, kind: 'not_found', url: null } }), 'observed_catalog', /route-not-found/],
    [observation({ route: { ...observation().route, kind: 'blocked_auth' } }), 'blocked_auth', /auth-challenge/],
    [observation({ route: { ...observation().route, kind: 'multiple' } }), 'needs_route_review', /ambiguous-route/],
    [observation({ subject: 'unknown' }), 'needs_route_review', /identity-incomplete/],
    [observation({ rights: { ...observation().rights, category: 'licensed_donor', license: 'synthetic' } }), 'needs_route_review', /licensed-donor-requires-offline/],
  ];
  for (const [input, expected, reason] of cases) {
    const result = classifyObservation(input, { allowlist: list.value, config });
    assert.equal(result.classification, expected, JSON.stringify(input));
    assert.match(result.reason, reason);
    assert.equal(result.input, undefined, 'non-capture classifications never carry enqueue input');
  }
});

test('unsafe or ephemeral URLs and image references are sent to route review', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  const list = await allowlist();
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const unsafe = [
    observation({ route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku/exam/9000001?token=SECRET' } }),
    observation({ route: { ...observation().route, url: 'https://evil.test/spa/tiku/exam/9000001' } }),
    observation({ route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku?toPage=2' } }),
    observation({ route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku' } }),
    observation({ images: [{ ref: '/absolute.png' }] }),
    observation({ images: [{ ref: 'q.png', sourceUrl: 'https://img.fbstatic.cn/q.png?token=x' }] }),
    observation({ route: { ...observation().route, imageContentOnly: true }, images: [] }),
  ];
  for (const input of unsafe) {
    const result = classifyObservation(input, { allowlist: list.value, config });
    assert.equal(result.classification, 'needs_route_review', JSON.stringify(input));
    assert.equal(result.input, undefined);
  }
});

test('redistribution defaults to local_only unless written permission evidence exists', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  const list = await allowlist();
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const requested = observation({ rights: { ...observation().rights, redistribution: 'allowed' } });
  const downgraded = classifyObservation(requested, { allowlist: list.value, config });
  assert.equal(downgraded.effectiveRedistribution, 'local_only');
  assert.ok(downgraded.warnings.includes('redistribution-downgraded-to-local-only'));
  const permitted = observation({
    rights: {
      ...observation().rights,
      redistribution: 'allowed',
      evidence: [...observation().rights.evidence, { type: 'redistribution_permission', ref: 'synthetic written permission' }],
    },
  });
  const allowed = classifyObservation(permitted, { allowlist: list.value, config });
  assert.equal(allowed.effectiveRedistribution, 'allowed');
  assert.equal(allowed.input.redistribution, 'allowed');
});

test('allowlist files may not carry URLs and a missing allowlist authorizes nothing', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  const bad = path.join(dir, 'bad-allowlist.json');
  await fs.writeFile(bad, JSON.stringify({ sourceIds: [{ id: '9000001', url: 'https://www.fenbi.com/spa/tiku/exam/9000001' }] }));
  await assert.rejects(loadAllowlist(bad), /ALLOWLIST_URL_FORBIDDEN/);
  const missing = await loadAllowlist(path.join(dir, 'does-not-exist.json'));
  assert.equal(missing.missing, true);
  assert.equal(missing.ids.size, 0);
  const result = classifyObservation(observation(), { allowlist: missing, config });
  assert.equal(result.classification, 'needs_initialization_review');
});

test('handoff envelopes reject credentials but allow the false permission declarations', async (t) => {
  const dir = await temporary(t);
  const config = makeConfig(dir);
  const list = await allowlist();
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  validateObservationHandoff(handoff([observation()]));
  assert.throws(() => validateObservationHandoff({ ...handoff([observation()]), cookies: 'sessionid=SYNTHETIC' }), /CREDENTIAL_LEAK/);
  assert.throws(() => validateObservationHandoff({
    ...handoff([observation()]), permissions: { browserProfile: true, cookies: false, tokens: false },
  }), /PROFILE_LEAK/);
  assert.throws(() => validateObservationHandoff(handoff([{ ...observation(), route: { ...observation().route, url: 'https://www.fenbi.com/x?token=SYNTHETIC' } }])), /CREDENTIAL_LEAK/);
  assert.equal(list.value.ids.size, 4);
});

test('PR54 route params are preserved only when declared; write routes never become capture_ready', async (t) => {
  const dir = await temporary(t);
  const list = await allowlist();
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const routed = observation({
    route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku/exam/9000001?labelId=1&routecs=opaque123' },
  });
  const declaredConfig = makeConfig(dir, { routeParams: ['routecs'] });
  const declared = classifyObservation(routed, { allowlist: list.value, config: declaredConfig });
  assert.equal(declared.classification, 'capture_ready');
  assert.match(declared.input.url, /routecs=opaque123/);
  const undeclaredConfig = makeConfig(dir, { routeParams: [] });
  const undeclared = classifyObservation(routed, { allowlist: list.value, config: undeclaredConfig });
  assert.equal(undeclared.classification, 'needs_route_review');
  assert.equal(undeclared.reason, 'url-not-reproducible');
  const writeRoute = classifyObservation(observation({
    route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku/exam/9000001/submit?labelId=1' },
  }), { allowlist: list.value, config: declaredConfig });
  assert.equal(writeRoute.classification, 'needs_route_review');
  assert.equal(writeRoute.reason, 'url-not-reproducible');
});

test('import is purely offline: no fetch, no browser, no initialise/submit request', async (t) => {
  const { queue, config } = await newQueue(t, { routeParams: ['routecs'] });
  const list = await allowlist(['9000001']);
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const originalFetch = globalThis.fetch;
  let fetchCalls = 0;
  globalThis.fetch = async () => { fetchCalls += 1; throw new Error('network must not be used by the offline importer'); };
  try {
    const input = handoff([observation({
      route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku/exam/9000001?labelId=1&routecs=opaque123' },
    })]);
    const report = await importObservations({ queue, config, handoff: input, allowlist: list.value });
    assert.equal(report.counts.created, 1);
    assert.equal(fetchCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('bounded directory import validates all selected files first and honours maxFiles', async (t) => {
  const { dir, queue, config } = await newQueue(t);
  const list = await allowlist(['9000001', '9000002']);
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const handoffDir = path.join(dir, 'handoffs');
  await fs.mkdir(handoffDir, { recursive: true, mode: 0o700 });
  await fs.writeFile(path.join(handoffDir, '01.json'), JSON.stringify(handoff([observation()])));
  await fs.writeFile(path.join(handoffDir, '02.json'), JSON.stringify(handoff([observation({
    paperSourceId: '9000002', title: '江苏2025行测C类', area: '江苏', year: 2025, variant: 'C类',
    route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku/exam/9000002?labelId=2' },
    images: [],
  })])));
  const one = await importObservationDirectory({ queue, config, directory: handoffDir, allowlist: list.value, maxFiles: 1 });
  assert.equal(one.selected, 1);
  assert.equal(one.counts.created, 1);
  assert.equal((await queue.listJobs()).length, 1);
  const both = await importObservationDirectory({ queue, config, directory: handoffDir, allowlist: list.value, maxFiles: 2 });
  assert.equal(both.selected, 2);
  assert.equal(both.counts.created, 1, 'the first file deduplicates');
  assert.equal(both.counts.deduplicated, 1);
  assert.equal((await queue.listJobs()).length, 2);
  await assert.rejects(importObservationDirectory({ queue, config, directory: handoffDir, allowlist: list.value, maxFiles: 21 }), /INVALID_MAX_FILES/);
});

test('a credential leak in any selected handoff aborts the directory before enqueueing', async (t) => {
  const { dir, queue, config } = await newQueue(t);
  const list = await allowlist(['9000001']);
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const handoffDir = path.join(dir, 'leaky-handoffs');
  await fs.mkdir(handoffDir, { recursive: true, mode: 0o700 });
  await fs.writeFile(path.join(handoffDir, '01.json'), JSON.stringify(handoff([observation()])));
  await fs.writeFile(path.join(handoffDir, '02.json'), JSON.stringify({ ...handoff([observation()]), cookies: 'sessionid=SYNTHETIC' }));
  await assert.rejects(importObservationDirectory({ queue, config, directory: handoffDir, allowlist: list.value, maxFiles: 2 }), /CREDENTIAL_LEAK/);
  assert.equal((await queue.listJobs()).length, 0, 'nothing is enqueued when a later file fails validation');
});

test('import enqueues only eligible items, deduplicates on repeat, and records the rest as catalog', async (t) => {
  const { dir, queue, config } = await newQueue(t);
  const list = await allowlist();
  t.after(() => fs.rm(list.dir, { recursive: true, force: true }));
  const input = handoff([
    observation(),
    observation({ paperSourceId: '9999999', title: '未授权合成卷' }),
    observation({ paperSourceId: '9000002', title: '江苏2025行测C类', route: { ...observation().route, contentStatus: 'placeholder' } }),
    observation({ paperSourceId: '9000003', title: '江苏2024行测A类', route: { ...observation().route, urlObserved: false } }),
  ]);
  const first = await importObservations({ queue, config, handoff: input, allowlist: list.value });
  assert.equal(first.counts.observations, 4);
  assert.equal(first.counts.capture_ready, 1);
  assert.equal(first.counts.created, 1);
  assert.equal(first.counts.needs_initialization_review, 1);
  assert.equal(first.counts.observed_catalog, 1);
  assert.equal(first.counts.needs_route_review, 1);
  assert.equal((await queue.listJobs()).length, 1);
  const job = (await queue.listJobs())[0];
  assert.equal(job.paperSourceId, '9000001');
  const leases = await fs.readdir(path.join(config.dataDir, 'leases'));
  assert.equal(leases.filter((name) => name.endsWith('.json')).length, 0, 'import does not claim a lease');
  const catalog = JSON.parse(await fs.readFile(path.join(config.dataDir, 'state', 'observed-catalog.json'), 'utf8'));
  assert.equal(Object.keys(catalog.entries).length, 4);
  const second = await importObservations({ queue, config, handoff: input, allowlist: list.value });
  assert.equal(second.counts.created, 0);
  assert.equal(second.counts.deduplicated, 1);
  assert.equal((await queue.listJobs()).length, 1);
  const dry = await importObservations({ queue, config, handoff: input, allowlist: list.value, dryRun: true });
  assert.equal(dry.dryRun, true);
  assert.equal(dry.items.find((item) => item.classification === 'capture_ready').enqueued, false);
  void dir;
});
