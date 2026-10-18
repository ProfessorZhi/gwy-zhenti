import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { newQueue, temporary } from './helpers.mjs';
import { importObservations, loadAllowlist } from '../src/observation.mjs';
import { runCollector, runWorkerDrain, runAwaitedManifest } from '../src/collector.mjs';
import { evaluateBackpressure } from '../src/backpressure.mjs';

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
      category: 'observed_ui', license: null, redistribution: 'local_only',
      evidence: [{ type: 'observed_ui', ref: 'synthetic owner observed this practice' }],
    },
    images: [{ ref: 'material/q1.png', sourceUrl: 'https://img.fbstatic.cn/q1.png', sha256: SHA('a') }],
    ...overrides,
  };
}

function handoff(observations) {
  return {
    schemaVersion: 1, kind: 'gwy-zhenti-source-observation',
    producer: { agent: 'synthetic-browser-owner', at: '2026-10-17T04:00:00.000Z' },
    permissions: { browserProfile: false, cookies: false, tokens: false },
    observations,
  };
}

async function writeAllowlist(t, ids) {
  const dir = await temporary(t, 'e2e-allow-');
  const file = path.join(dir, 'allowlist.json');
  await fs.writeFile(file, JSON.stringify({ schemaVersion: 1, sourceIds: ids.map((id) => ({ id })) }));
  return { file, value: await loadAllowlist(file) };
}

async function sourceFile(dir, name, body) {
  const file = path.join(dir, name);
  await fs.writeFile(file, body, { mode: 0o600 });
  return file;
}

function producerAdapter(dir) {
  return {
    opensProfile: false,
    async capture(job) {
      const file = await sourceFile(dir, `staged-${job.jobId}.json`, JSON.stringify({ jobId: job.jobId, synthetic: true }) + '\n');
      return { outcome: 'done', artifacts: [{ source: file, name: 'staged.json', kind: 'staged_raw' }] };
    },
  };
}

function stageAdapter(dir, filename, kind = 'data', delayMs = 20) {
  return {
    async process(job) {
      await sleep(delayMs);
      const file = await sourceFile(dir, `${filename}-${job.jobId}`, JSON.stringify({ jobId: job.jobId, filename }) + '\n');
      return { outcome: 'done', artifacts: [{ source: file, name: filename, kind }] };
    },
  };
}

async function put(queue, { jobId, stage, owner, token, generation, dir, name, body, kind = 'data' }) {
  const file = await sourceFile(dir, `${name}-${owner}-${Date.now()}`, body);
  return queue.putArtifact({ jobId, stage, owner, token, generation, source: file, name, kind });
}

test('end-to-end: import → 1 producer → 2 independent consumers → reviewer → verifier', async (t) => {
  const dir = await temporary(t, 'e2e-');
  const { queue, config } = await newQueue(t, { maxConcurrency: 2 });
  const list = await writeAllowlist(t, ['9000001', '9000004']);
  const input = handoff([
    observation(),
    observation({
      paperSourceId: '9000004', title: '广东2020县级', area: '广东', year: 2020, variant: '县级',
      route: { ...observation().route, url: 'https://www.fenbi.com/spa/tiku/exam/9000004?labelId=2' },
      images: [],
    }),
    observation({ paperSourceId: '9999999', title: '未授权合成卷' }),
  ]);
  const imported = await importObservations({ queue, config, handoff: input, allowlist: list.value });
  assert.equal(imported.counts.created, 2);
  assert.equal(imported.counts.needs_initialization_review, 1);
  const jobs = await queue.listJobs();
  assert.equal(jobs.length, 2);
  assert.ok(!jobs.some((job) => job.paperSourceId === '9999999'));

  // One producer owns the (synthetic) browser profile and captures both ready jobs.
  const producer = await runCollector({ queue, config, adapter: producerAdapter(dir), budget: 2, owner: 'producer-1' });
  assert.equal(producer.exit, 0);
  assert.equal(producer.claimed, 2);
  const bySource = new Map((await queue.listJobs()).map((job) => [job.paperSourceId, job]));
  const zhejiang = bySource.get('9000001');
  const guangdong = bySource.get('9000004');
  assert.equal(zhejiang.stages.capture_ready.status, 'done');
  assert.equal(guangdong.stages.capture_ready.status, 'done');

  // Advance Zhejiang to aligned so the two consumers can work on different stages.
  const nz = await runWorkerDrain({
    queue, config, role: 'normalizer', stage: 'normalized', budget: 1, owner: 'normalizer-z',
    adapter: stageAdapter(dir, 'normalized.json'),
  });
  assert.equal(nz.claimed, 1);
  // Two independent consumers on different jobs/stages at the same time.
  const [normalizedGuangdong, alignedZhejiang] = await Promise.all([
    runWorkerDrain({
      queue, config, role: 'normalizer', stage: 'normalized', budget: 1, owner: 'normalizer-g',
      adapter: stageAdapter(dir, 'normalized.json', 'data', 120),
    }),
    runWorkerDrain({
      queue, config, role: 'matcher', stage: 'aligned', budget: 1, owner: 'matcher-z2',
      adapter: stageAdapter(dir, 'aligned.json', 'data', 120),
    }),
  ]);
  assert.equal(normalizedGuangdong.claimed, 1);
  assert.equal(alignedZhejiang.claimed, 1);
  const afterConsumers = new Map((await queue.listJobs()).map((job) => [job.paperSourceId, job]));
  assert.equal(afterConsumers.get('9000004').stages.normalized.status, 'done');
  assert.equal(afterConsumers.get('9000001').stages.aligned.status, 'done');

  // assets_qa must carry hashed byte evidence for every referenced image (PR42).
  let claim = await queue.claimStage('assets_qa', { role: 'assets_qa', owner: 'assets-z', jobId: zhejiang.jobId });
  assert.ok(claim);
  const assets = await put(queue, {
    jobId: zhejiang.jobId, stage: 'assets_qa', owner: 'assets-z',
    token: claim.lease.token, generation: claim.lease.generation,
    dir, name: 'assets.json', body: JSON.stringify({ checked: true }) + '\n',
  });
  await assert.rejects(queue.completeStage({
    jobId: zhejiang.jobId, stage: 'assets_qa', owner: 'assets-z',
    token: claim.lease.token, generation: claim.lease.generation, artifacts: [assets],
  }), /IMAGE_ASSET_MANIFEST_REQUIRED/);
  const wrongImages = await put(queue, {
    jobId: zhejiang.jobId, stage: 'assets_qa', owner: 'assets-z',
    token: claim.lease.token, generation: claim.lease.generation,
    dir, name: 'images.json', kind: 'image_manifest',
    body: JSON.stringify({ images: [{ ref: 'material/q1.png', sha256: SHA('0'), bytes: 12 }] }) + '\n',
  });
  await assert.rejects(queue.completeStage({
    jobId: zhejiang.jobId, stage: 'assets_qa', owner: 'assets-z',
    token: claim.lease.token, generation: claim.lease.generation, artifacts: [assets, wrongImages],
  }), /IMAGE_HASH_MISMATCH/);
  const correctImages = await put(queue, {
    jobId: zhejiang.jobId, stage: 'assets_qa', owner: 'assets-z',
    token: claim.lease.token, generation: claim.lease.generation,
    dir, name: 'images.json', kind: 'image_manifest',
    body: JSON.stringify({ images: [{ ref: 'material/q1.png', sha256: SHA('a'), bytes: 12 }] }) + '\n',
  });
  const assetsDone = await queue.completeStage({
    jobId: zhejiang.jobId, stage: 'assets_qa', owner: 'assets-z',
    token: claim.lease.token, generation: claim.lease.generation, artifacts: [assets, correctImages],
  });
  assert.equal(assetsDone.stages.assets_qa.status, 'done');

  // Answer, human review, candidate, verification.
  claim = await queue.claimStage('answer_explanation_qa', { role: 'answer_qa', owner: 'answer-z', jobId: zhejiang.jobId });
  const answers = await put(queue, {
    jobId: zhejiang.jobId, stage: 'answer_explanation_qa', owner: 'answer-z',
    token: claim.lease.token, generation: claim.lease.generation,
    dir, name: 'answers.json', body: JSON.stringify({ source: 'observed' }) + '\n',
  });
  await queue.completeStage({
    jobId: zhejiang.jobId, stage: 'answer_explanation_qa', owner: 'answer-z',
    token: claim.lease.token, generation: claim.lease.generation, artifacts: [answers],
    declarations: { answerProvenance: 'source_observed' },
  });
  const manifest = await runAwaitedManifest({ queue, stage: 'human_review' });
  assert.equal(manifest.count, 1);
  assert.equal(manifest.items[0].jobId, zhejiang.jobId);
  assert.match(manifest.note, /grants no approval/);

  claim = await queue.claimStage('human_review', { role: 'reviewer', owner: 'reviewer-1', jobId: zhejiang.jobId });
  const review = await put(queue, {
    jobId: zhejiang.jobId, stage: 'human_review', owner: 'reviewer-1',
    token: claim.lease.token, generation: claim.lease.generation,
    dir, name: 'review.json', body: JSON.stringify({ approved: true }) + '\n',
  });
  await queue.completeStage({
    jobId: zhejiang.jobId, stage: 'human_review', owner: 'reviewer-1',
    token: claim.lease.token, generation: claim.lease.generation, artifacts: [review],
    declarations: { approved: true, reviewer: 'fixture-reviewer' },
  });

  claim = await queue.claimStage('candidate_ready', { role: 'verifier', owner: 'verifier-1', jobId: zhejiang.jobId });
  const receipt = await put(queue, {
    jobId: zhejiang.jobId, stage: 'candidate_ready', owner: 'verifier-1',
    token: claim.lease.token, generation: claim.lease.generation,
    dir, name: 'receipt.json', body: JSON.stringify({ verified: true }) + '\n',
  });
  await assert.rejects(queue.completeStage({
    jobId: zhejiang.jobId, stage: 'candidate_ready', owner: 'verifier-1',
    token: claim.lease.token, generation: claim.lease.generation, artifacts: [receipt],
    declarations: { citationsVerified: true },
  }), /IMAGE_EVIDENCE_REQUIRED/);
  await queue.completeStage({
    jobId: zhejiang.jobId, stage: 'candidate_ready', owner: 'verifier-1',
    token: claim.lease.token, generation: claim.lease.generation, artifacts: [receipt],
    declarations: { citationsVerified: true, imagesVerified: true },
  });
  const verified = await queue.verify({
    jobId: zhejiang.jobId, actor: 'verifier-1', receipt: { path: 'receipt.json', sha256: receipt.sha256 },
  });
  assert.equal(verified.status, 'verified');
  const status = await queue.status();
  assert.equal(status.completed, 1);
  assert.equal(status.jobs.verified, 1);
  assert.equal(status.jobs.candidateReady, 0);
});

test('backpressure stops the collector without claiming and crash recovery hands the stage to a new owner', async (t) => {
  const dir = await temporary(t, 'e2e-bp-');
  const { queue, config } = await newQueue(t, {
    maxConcurrency: 1,
    backpressure: { maxQueueLength: 1, maxPendingReview: 50, diskFreeFloorBytes: 0, perPaperBytes: 1024 * 1024 },
  });
  const list = await writeAllowlist(t, ['9000001']);
  await importObservations({ queue, config, handoff: handoff([observation()]), allowlist: list.value });
  let producerCalls = 0;
  const adapter = { opensProfile: false, async capture() { producerCalls += 1; throw new Error('must not run under backpressure'); } };
  const status = await queue.status();
  const backpressure = evaluateBackpressure({ status, config });
  assert.equal(backpressure.level, 'pause_capture');
  const blocked = await runCollector({ queue, config, adapter, budget: 1, backpressure });
  assert.equal(blocked.exit, 4);
  assert.equal(blocked.reason, 'backpressure');
  assert.equal(blocked.claimed, 0);
  assert.equal(producerCalls, 0);

  await queue.enqueue({
    paperSourceId: '9000004', version: 'crash-v1', title: '广东2020县级', subject: 'xingce',
    area: '广东', year: 2020, url: 'https://www.fenbi.com/spa/tiku/exam/9000004', urlObserved: true,
    sourceCategory: 'observed_ui', evidence: [{ type: 'observed_ui', ref: 'synthetic crash fixture' }],
  }, { authorizedSourceIds: null });
  const crashJob = (await queue.listJobs()).find((job) => job.paperSourceId === '9000004');
  const crashClaim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'crashed-producer', jobId: crashJob.jobId });
  assert.ok(crashClaim);
  const future = Date.now() + 120_000;
  const reconciled = await queue.reconcile({ now: future });
  assert.ok(reconciled.reclaimed.some((item) => item.jobId === crashJob.jobId));
  const retryAt = (await queue.getJob(crashJob.jobId)).stages.capture_ready.nextAttemptAt;
  const newClaim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'replacement-producer', now: retryAt, jobId: crashJob.jobId });
  assert.ok(newClaim);
  await assert.rejects(queue.completeStage({
    jobId: crashJob.jobId, stage: 'capture_ready', owner: 'crashed-producer',
    token: crashClaim.lease.token, generation: crashClaim.lease.generation,
    artifacts: [], now: retryAt,
  }), /LEASE_LOST|LEASE_EXPIRED/);
  await newClaim.lease.release();
  const leases = await fs.readdir(path.join(config.dataDir, 'leases'));
  assert.equal(leases.filter((name) => name.endsWith('.json')).length, 0);
  void dir;
});
