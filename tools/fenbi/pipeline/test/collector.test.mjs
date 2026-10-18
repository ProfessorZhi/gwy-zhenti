import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { newQueue, enqueueInput, temporary, makeConfig } from './helpers.mjs';
import { runCollector, runWorkerDrain, runAwaitedManifest } from '../src/collector.mjs';
import { openQueue } from '../src/queue.mjs';
import { loadThrottle } from '../src/throttle.mjs';

async function adapterSource(dir) {
  const sourceDir = path.join(dir, 'adapter-source');
  await fs.mkdir(sourceDir, { recursive: true, mode: 0o700 });
  const file = path.join(sourceDir, 'staged.json');
  await fs.writeFile(file, '{"synthetic":"adapter output"}\n', { mode: 0o600 });
  return file;
}

function doneAdapter(file, tracker = null, delayMs = 20) {
  return {
    opensProfile: false,
    async capture(job, context) {
      tracker?.start(context.slot);
      try {
        await sleep(delayMs);
        return { outcome: 'done', artifacts: [{ source: file, name: 'staged.json', kind: 'staged_raw' }] };
      } finally { tracker?.end(context.slot); }
    },
  };
}

test('without a browser-owner adapter the collector refuses to strand capture leases', async (t) => {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const result = await runCollector({ queue, config, adapter: null, budget: 2 });
  assert.equal(result.reason, 'collector_unwired');
  assert.equal(result.exit, 2);
  assert.equal(result.claimed, 0);
  const job = await queue.getJob(jobId);
  assert.equal(job.stages.capture_ready.status, 'pending');
  assert.equal(await fs.readdir(path.join(config.dataDir, 'leases')).then((items) => items.filter((x) => x.endsWith('.json')).length), 0);
});

test('one collector processes up to its bounded page count and hands off staged artifacts', async (t) => {
  const { dir, queue, config } = await newQueue(t);
  const source = await adapterSource(dir);
  const tracker = { active: 0, max: 0, starts: 0, start() { this.starts += 1; this.active += 1; this.max = Math.max(this.max, this.active); }, end() { this.active -= 1; } };
  for (let index = 0; index < 3; index += 1) await queue.enqueue(enqueueInput());
  const result = await runCollector({ queue, config, adapter: doneAdapter(source, tracker, 250), budget: 3, owner: 'collector-a' });
  assert.equal(result.exit, 0);
  assert.equal(result.claimed, 2, 'default maxConcurrency is 2');
  assert.equal(tracker.max, 2);
  const jobs = await queue.listJobs();
  const done = jobs.filter((job) => job.stages.capture_ready.status === 'done');
  assert.equal(done.length, 2);
  for (const job of done) {
    const artifact = job.stages.capture_ready.artifacts[0];
    assert.equal(artifact.path, 'staged.json');
    const bytes = await fs.readFile(path.join(config.dataDir, 'artifacts', job.jobId, 'capture_ready', 'staged.json'), 'utf8');
    assert.match(bytes, /adapter output/);
  }
  const pending = jobs.filter((job) => job.stages.capture_ready.status === 'pending');
  assert.equal(pending.length, 1, 'the third job stays queued rather than exceeding the page cap');
  assert.equal((await queue.status()).completed, 0);
});

test('a 429 produces a persisted exponential backoff and does not mark the job complete', async (t) => {
  const { queue, config, dir } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const adapter = { opensProfile: false, async capture() { throw Object.assign(new Error('synthetic 429'), { statusCode: 429 }); } };
  // The test backoff is 10ms, shorter than a slow run takes, so compare with the start, not "now".
  const started = Date.now();
  const result = await runCollector({ queue, config, adapter, budget: 1 });
  assert.equal(result.exit, 3);
  assert.equal(result.reason, 'rate_limited');
  const job = await queue.getJob(jobId);
  assert.equal(job.stages.capture_ready.status, 'pending');
  assert.ok(job.stages.capture_ready.nextAttemptAt >= started + config.backoff.baseMs);
  const throttle = await loadThrottle(dir, config, Date.now());
  assert.equal(throttle.hosts['www.fenbi.com'].intervalMs, 200);
  assert.equal(throttle.hosts['www.fenbi.com'].penalties, 1);
});

test('a 401 blocks the job and every subsequent drain until a human resets the throttle', async (t) => {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const adapter = { opensProfile: false, async capture() { throw Object.assign(new Error('synthetic 401'), { statusCode: 401 }); } };
  const first = await runCollector({ queue, config, adapter, budget: 1 });
  assert.equal(first.exit, 2);
  assert.equal(first.reason, 'blocked_auth');
  assert.equal((await queue.getJob(jobId)).stages.capture_ready.status, 'blocked_auth');
  const second = await runCollector({ queue, config, adapter: doneAdapter('/nonexistent'), budget: 1 });
  assert.equal(second.reason, 'blocked_auth');
  assert.equal(second.claimed, 0);
  assert.equal(second.exit, 2);
});

test('a second collector cannot share the profile while the first is alive', async (t) => {
  const { dir, queue, config } = await newQueue(t);
  const source = await adapterSource(dir);
  await queue.enqueue(enqueueInput());
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let started;
  const startedPromise = new Promise((resolve) => { started = resolve; });
  const blocking = {
    opensProfile: false,
    async capture() { started(); await gate; return { outcome: 'done', artifacts: [{ source, name: 'staged.json' }] }; },
  };
  const first = runCollector({ queue, config, adapter: blocking, budget: 1, owner: 'collector-first' });
  await startedPromise;
  await assert.rejects(runCollector({ queue, config, adapter: blocking, budget: 1, owner: 'collector-second' }), /COLLECTOR_LOCKED/);
  release();
  const result = await first;
  assert.equal(result.exit, 0);
  assert.equal(result.claimed, 1);
});

test('offline workers require an adapter and otherwise leave the stage unclaimed', async (t) => {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const source = await adapterSource(path.dirname(config.dataDir));
  // Finish capture with the collector first.
  await runCollector({ queue, config, adapter: doneAdapter(source), budget: 1 });
  const unwired = await runWorkerDrain({ queue, config, role: 'normalizer', stage: 'normalized', adapter: null, budget: 1 });
  assert.equal(unwired.reason, 'worker_unwired');
  assert.equal(unwired.exit, 2);
  assert.equal((await queue.getJob(jobId)).stages.normalized.status, 'pending');
  const processed = await runWorkerDrain({
    queue, config, role: 'normalizer', stage: 'normalized', budget: 1, owner: 'normalizer-a',
    adapter: { async process() { return { outcome: 'done', artifacts: [{ source, name: 'normalized.json' }] }; } },
  });
  assert.equal(processed.exit, 0);
  assert.equal(processed.claimed, 1);
  assert.equal((await queue.getJob(jobId)).stages.normalized.status, 'done');
});

test('review manifests are advisory and never approve a paper', async (t) => {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const source = await adapterSource(path.dirname(config.dataDir));
  await runCollector({ queue, config, adapter: doneAdapter(source), budget: 1 });
  const manifest = await runAwaitedManifest({ queue, stage: 'human_review' });
  // answer_explanation_qa is not done, so nothing is reviewable yet.
  assert.equal(manifest.count, 0);
  assert.match(manifest.note, /grants no approval/);
  void jobId;
});
