import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { temporary } from './helpers.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLI = path.join(HERE, '..', 'src', 'cli.mjs');

function cli(args) {
  return new Promise((resolve) => {
    execFile(process.execPath, [CLI, ...args], { timeout: 30_000 }, (error, stdout, stderr) => {
      let json = null;
      try { json = JSON.parse(stdout); } catch { /* asserted by the caller */ }
      resolve({ code: error?.code ?? 0, stdout, stderr, json });
    });
  });
}

function observation(overrides = {}) {
  return {
    paperSourceId: '9000001', title: '浙江2026行测C类', subject: 'xingce', area: '浙江', year: 2026, variant: 'C类',
    route: {
      kind: 'existing_practice', url: 'https://www.fenbi.com/spa/tiku/exam/9000001?labelId=1',
      urlObserved: true, contentStatus: 'observed', questionCount: 100,
      evidence: [{ type: 'observed_ui', ref: 'synthetic CLI owner observation' }],
    },
    rights: {
      category: 'observed_ui', license: null, redistribution: 'local_only',
      evidence: [{ type: 'observed_ui', ref: 'synthetic CLI owner observation' }],
    },
    images: [],
    ...overrides,
  };
}

function handoff(observations) {
  return {
    schemaVersion: 1, kind: 'gwy-zhenti-source-observation',
    producer: { agent: 'cli-synthetic-owner', at: '2026-10-17T04:00:00.000Z' },
    permissions: { browserProfile: false, cookies: false, tokens: false },
    observations,
  };
}

async function setup(t) {
  const dir = await temporary(t, 'cli-obs-');
  const data = path.join(dir, 'data');
  const configFile = path.join(dir, 'pipeline.json');
  await fs.writeFile(configFile, JSON.stringify({ authorizedSourceIds: null }));
  const allowFile = path.join(dir, 'allowlist.json');
  await fs.writeFile(allowFile, JSON.stringify({ schemaVersion: 1, sourceIds: [{ id: '9000001' }] }));
  const handoffFile = path.join(dir, 'observation.json');
  await fs.writeFile(handoffFile, JSON.stringify(handoff([
    observation(),
    observation({ paperSourceId: '9999999', title: '未授权合成卷' }),
    observation({ paperSourceId: '9000001', title: '浙江2026行测C类', route: { ...observation().route, contentStatus: 'placeholder' } }),
  ])));
  return { dir, data, configFile, allowFile, handoffFile };
}

test('CLI observe-import classifies and enqueues only authorized existing practices', async (t) => {
  const { data, configFile, allowFile, handoffFile } = await setup(t);
  const show = await cli(['allowlist', 'show', '--config', configFile, '--data-dir', data, '--allowlist', allowFile]);
  assert.equal(show.code, 0, show.stderr);
  assert.equal(show.json.count, 1);
  const imported = await cli(['observe-import', '--config', configFile, '--data-dir', data, '--allowlist', allowFile, '--handoff', handoffFile]);
  assert.equal(imported.code, 0, imported.stderr);
  assert.equal(imported.json.counts.created, 1);
  assert.equal(imported.json.counts.needs_initialization_review, 1);
  assert.equal(imported.json.counts.observed_catalog, 1);
  const status = await cli(['status', '--config', configFile, '--data-dir', data]);
  assert.equal(status.code, 0);
  assert.equal(status.json.status.jobs.total, 1);
  assert.equal(status.json.status.metrics.sourcesEnqueued, 1);
  assert.equal(status.json.status.metrics.blocked, 0);
  assert.equal(status.json.status.metrics.queueDepth, 1);
  assert.equal(status.json.collector.adapterWired, false);
  assert.equal(status.json.observedCatalog.entries, 3);
  const leases = await fs.readdir(path.join(data, 'leases'));
  assert.equal(leases.filter((name) => name.endsWith('.json')).length, 0);
  const unwired = await cli(['drain', '--config', configFile, '--data-dir', data, '--role', 'collector', '--budget', '1']);
  assert.equal(unwired.code, 2);
  assert.equal(unwired.json.reason, 'collector_unwired');
  assert.equal(unwired.json.claimed, 0);
  const afterDrain = await cli(['status', '--config', configFile, '--data-dir', data]);
  assert.equal(afterDrain.json.collector.adapterWired, false);
  assert.equal(afterDrain.json.collector.lastReason, 'collector_unwired');
  const dry = await cli(['observe-import', '--config', configFile, '--data-dir', data, '--allowlist', allowFile, '--handoff', handoffFile, '--dry-run']);
  assert.equal(dry.code, 0);
  assert.equal(dry.json.dryRun, true);
  assert.equal(dry.json.counts.created, 0);
});

test('CLI observe-import fail-closes when the allowlist is absent and rejects credential leakage', async (t) => {
  const { dir, data, configFile, handoffFile } = await setup(t);
  const missing = await cli(['observe-import', '--config', configFile, '--data-dir', data, '--allowlist', path.join(dir, 'none.json'), '--handoff', handoffFile]);
  assert.equal(missing.code, 0, missing.stderr);
  assert.equal(missing.json.allowlist.missing, true);
  assert.equal(missing.json.counts.created, 0);
  assert.equal(missing.json.counts.needs_initialization_review, 3);
  const status = await cli(['status', '--config', configFile, '--data-dir', data]);
  assert.equal(status.json.status.jobs.total, 0);

  const leaked = path.join(dir, 'leaked.json');
  await fs.writeFile(leaked, JSON.stringify({
    ...handoff([observation()]),
    cookies: 'sessionid=SYNTHETIC',
  }));
  const rejected = await cli(['observe-import', '--config', configFile, '--data-dir', data, '--allowlist', path.join(dir, 'none.json'), '--handoff', leaked]);
  assert.equal(rejected.code, 5);
  assert.equal(rejected.json.error.code, 'HANDOFF_CREDENTIAL_LEAK');
});

test('CLI bounded directory import honours max-files and deduplicates across files', async (t) => {
  const { dir, data, configFile } = await setup(t);
  const handoffDir = path.join(dir, 'owner-handoffs');
  await fs.mkdir(handoffDir, { recursive: true, mode: 0o700 });
  await fs.writeFile(path.join(handoffDir, '01.json'), JSON.stringify(handoff([observation()])));
  await fs.writeFile(path.join(handoffDir, '02.json'), JSON.stringify(handoff([
    observation({
      paperSourceId: '9000002', title: '江苏2025行测C类', area: '江苏', year: 2025, variant: 'C类',
      route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku/exam/9000002?labelId=2' },
    }),
  ])));
  const allowFile = path.join(dir, 'allow-two.json');
  await fs.writeFile(allowFile, JSON.stringify({ sourceIds: [{ id: '9000001' }, { id: '9000002' }] }));
  const one = await cli(['observe-import', '--config', configFile, '--data-dir', data,
    '--allowlist', allowFile, '--handoff-dir', handoffDir, '--max-files', '1']);
  assert.equal(one.code, 0, one.stderr);
  assert.equal(one.json.selected, 1);
  assert.equal(one.json.counts.created, 1);
  const two = await cli(['observe-import', '--config', configFile, '--data-dir', data,
    '--allowlist', allowFile, '--handoff-dir', handoffDir, '--max-files', '2']);
  assert.equal(two.code, 0, two.stderr);
  assert.equal(two.json.selected, 2);
  assert.equal(two.json.counts.created, 1);
  assert.equal(two.json.counts.deduplicated, 1);
  const status = await cli(['status', '--config', configFile, '--data-dir', data]);
  assert.equal(status.json.status.jobs.total, 2);
  assert.equal(status.json.status.metrics.sourcesEnqueued, 2);
});
