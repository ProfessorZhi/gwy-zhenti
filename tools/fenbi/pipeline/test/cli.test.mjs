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
      try { json = JSON.parse(stdout); } catch { /* the caller asserts on exit/stdout */ }
      resolve({ code: error?.code ?? 0, stdout, stderr, json });
    });
  });
}

test('CLI performs the full synthetic enqueue → claim → stage → handoff workflow', async (t) => {
  const dir = await temporary(t);
  const data = path.join(dir, 'data');
  const configFile = path.join(dir, 'pipeline.json');
  await fs.writeFile(configFile, JSON.stringify({ authorizedSourceIds: null }));
  const base = ['--config', configFile, '--data-dir', data];

  const enqueued = await cli(['enqueue', ...base,
    '--source-id', 'cli-synthetic-1', '--version', 'v1', '--title', 'CLI 合成测试卷',
    '--subject', 'xingce', '--area', '浙江', '--year', '2026', '--variant', 'C类',
    '--url', 'https://www.fenbi.com/spa/tiku/exam/1?labelId=1', '--observed',
    '--source-category', 'observed_ui', '--evidence', 'observed_ui:synthetic CLI fixture',
    '--questions', '1', '--actor', 'cli-test']);
  assert.equal(enqueued.code, 0, enqueued.stderr);
  assert.equal(enqueued.json.ok, true);
  const jobId = enqueued.json.jobId;
  assert.equal(enqueued.json.created, true);

  const duplicate = await cli(['enqueue', ...base,
    '--source-id', 'cli-synthetic-1', '--version', 'v1', '--title', 'CLI 合成测试卷',
    '--subject', 'xingce', '--area', '浙江', '--year', '2026', '--variant', 'C类',
    '--url', 'https://www.fenbi.com/spa/tiku/exam/1?labelId=1', '--observed',
    '--source-category', 'observed_ui', '--evidence', 'observed_ui:synthetic CLI fixture',
    '--questions', '1', '--actor', 'cli-test']);
  assert.equal(duplicate.code, 0);
  assert.equal(duplicate.json.duplicate, true);

  const claim = await cli(['claim', ...base, '--role', 'collector', '--stage', 'capture_ready', '--owner', 'cli-collector']);
  assert.equal(claim.code, 0, claim.stderr);
  assert.equal(claim.json.claimed, true);
  const token = claim.json.lease.token;
  const generation = String(claim.json.lease.generation);

  const artifactFile = path.join(dir, 'staged.json');
  await fs.writeFile(artifactFile, '{"synthetic":"cli staged"}\n');
  const put = await cli(['put-artifact', ...base, '--job', jobId, '--stage', 'capture_ready',
    '--owner', 'cli-collector', '--token', token, '--generation', generation,
    '--file', artifactFile, '--name', 'staged.json', '--kind', 'staged_raw']);
  assert.equal(put.code, 0, put.stderr);
  assert.match(put.json.artifact.sha256, /^[a-f0-9]{64}$/);

  const complete = await cli(['complete', ...base, '--job', jobId, '--stage', 'capture_ready',
    '--owner', 'cli-collector', '--token', token, '--generation', generation, '--artifact', 'staged.json']);
  assert.equal(complete.code, 0, complete.stderr);
  assert.equal(complete.json.status, 'queued');

  const handoffFile = path.join(dir, 'handoff.json');
  const built = await cli(['build-handoff', ...base, '--job', jobId, '--stage', 'capture_ready',
    '--producer', 'cli-test', '--out', handoffFile]);
  assert.equal(built.code, 0, built.stderr);
  const handoff = JSON.parse(await fs.readFile(handoffFile, 'utf8'));
  assert.equal(handoff.permissions.cookies, false);
  const verified = await cli(['verify-handoff', handoffFile, '--artifact-root',
    path.join(data, 'artifacts', jobId, 'capture_ready')]);
  assert.equal(verified.code, 0, verified.stderr);
  assert.equal(verified.json.artifacts, 1);
  assert.equal(verified.json.credentials, 'none');

  const status = await cli(['status', ...base]);
  assert.equal(status.code, 0);
  assert.equal(status.json.status.completed, 0);
  assert.equal(status.json.status.jobs.total, 1);
});

test('CLI review/worker drains exit blocked instead of claiming without a processor', async (t) => {
  const dir = await temporary(t);
  const data = path.join(dir, 'data');
  const configFile = path.join(dir, 'pipeline.json');
  await fs.writeFile(configFile, JSON.stringify({ authorizedSourceIds: null }));
  const enqueued = await cli(['enqueue', '--config', configFile, '--data-dir', data,
    '--source-id', 'cli-synthetic-2', '--version', 'v1', '--title', 'CLI 合成测试卷 2',
    '--subject', 'xingce', '--area', '浙江', '--year', '2026',
    '--url', 'https://www.fenbi.com/spa/tiku/exam/2', '--observed',
    '--evidence', 'observed_ui:synthetic CLI fixture', '--actor', 'cli-test']);
  assert.equal(enqueued.code, 0, enqueued.stderr);
  const collector = await cli(['drain', '--config', configFile, '--data-dir', data, '--role', 'collector', '--budget', '1']);
  assert.equal(collector.code, 2);
  assert.equal(collector.json.reason, 'collector_unwired');
  assert.equal(collector.json.claimed, 0);
  const worker = await cli(['drain', '--config', configFile, '--data-dir', data, '--role', 'normalizer', '--budget', '1']);
  assert.equal(worker.code, 2);
  assert.equal(worker.json.reason, 'worker_unwired');
  const review = await cli(['drain', '--config', configFile, '--data-dir', data, '--role', 'reviewer', '--budget', '1']);
  assert.equal(review.code, 0);
  assert.equal(review.json.count, 0);
  const reconciled = await cli(['reconcile', '--config', configFile, '--data-dir', data]);
  assert.equal(reconciled.code, 0);
  assert.equal(reconciled.json.reclaimed.length, 0);
});

test('CLI rejects an unobserved URL and returns a stable nonzero exit', async (t) => {
  const dir = await temporary(t);
  const configFile = path.join(dir, 'pipeline.json');
  await fs.writeFile(configFile, JSON.stringify({ authorizedSourceIds: null }));
  const result = await cli(['enqueue', '--config', configFile, '--data-dir', path.join(dir, 'data'),
    '--source-id', 'cli-synthetic-3', '--version', 'v1', '--title', 'CLI 合成测试卷 3',
    '--subject', 'xingce', '--area', '浙江', '--year', '2026',
    '--url', 'https://www.fenbi.com/spa/tiku/exam/3',
    '--evidence', 'observed_ui:forgot the observation flag', '--actor', 'cli-test']);
  assert.equal(result.code, 5);
  assert.equal(result.json.ok, false);
  assert.equal(result.json.error.code, 'INVALID_INPUT');
});
