import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { newQueue } from './helpers.mjs';
import { sha256File } from '../src/fsutil.mjs';
import { importQaHandoff } from '../src/qa-handoff.mjs';
import { buildStageManifest } from '../src/manifest.mjs';
import { runWorkerDrain } from '../src/collector.mjs';

const SHA = (char) => char.repeat(64);

async function privateDir(t, prefix = 'qa-e2e-') {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), prefix));
  await fs.chmod(dir, 0o700);
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  return dir;
}

async function writePrivate(file, body) {
  await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  await fs.writeFile(file, body, { mode: 0o600 });
  await fs.chmod(file, 0o600);
}

async function packageFor(t, { id, title }) {
  const dir = await privateDir(t, `qa-${id}-`);
  const artDir = path.join(dir, 'artifacts');
  await fs.mkdir(artDir, { recursive: true, mode: 0o700 });
  const files = [
    { name: 'summary.json', kind: 'summary', body: JSON.stringify({ questions: [{ number: 1, status: 'metadata_only' }, { number: 2, status: 'metadata_only' }] }) + '\n' },
    { name: 'index.json', kind: 'question_index', body: JSON.stringify({ index: [{ number: 1 }, { number: 2 }] }) + '\n' },
    { name: 'asset-manifest.json', kind: 'asset_manifest', body: JSON.stringify({ images: [{ ref: 'material/q1.png', sha256: SHA('a') }] }) + '\n' },
  ];
  const artifacts = [];
  for (const file of files) {
    const filename = path.join(artDir, file.name);
    await writePrivate(filename, file.body);
    const hashed = await sha256File(filename);
    artifacts.push({ path: `artifacts/${file.name}`, kind: file.kind, sha256: hashed.sha256, bytes: hashed.bytes });
  }
  const handoff = {
    schemaVersion: 1, kind: 'gwy-zhenti-staged-qa-handoff',
    producer: { agent: 'synthetic-browser-owner', at: '2026-10-18T00:00:00.000Z' },
    permissions: { browserProfile: false, cookies: false, tokens: false, rawSiteTextIncluded: false, imageBytesIncluded: false },
    identity: { paperSourceId: id, version: 'qa-v1', title, subject: 'xingce', area: '浙江', year: 2026, variant: 'C类' },
    source: { category: 'observed_ui', license: null, redistribution: 'local_only', evidence: [{ type: 'observed_ui', ref: 'synthetic owner metadata package' }] },
    summary: { questionCount: 2, questionNumbers: [1, 2], materialCount: 0, placeholderNumbers: [], unknownNumbers: [], imageCount: 1 },
    artifacts,
    assets: [{ ref: 'material/q1.png', sha256: SHA('a'), bytes: 12 }],
  };
  const handoffFile = path.join(dir, 'qa-handoff.json');
  await writePrivate(handoffFile, JSON.stringify(handoff, null, 2) + '\n');
  return { dir, handoffFile };
}

async function makeAllowlist(t, ids) {
  const dir = await privateDir(t, 'qa-e2e-allow-');
  const file = path.join(dir, 'allowlist.json');
  await writePrivate(file, JSON.stringify({ sourceIds: ids.map((id) => ({ id })) }));
  return { source: file, missing: false, ids: new Set(ids), entries: new Map(ids.map((id) => [id, { id }])), list: ids.map((id) => ({ id })) };
}

function stageAdapter(dir, filename, delayMs = 20) {
  return {
    async process(job) {
      await sleep(delayMs);
      const file = path.join(dir, `${filename}-${job.jobId}`);
      await fs.writeFile(file, JSON.stringify({ jobId: job.jobId, synthetic: true }) + '\n', { mode: 0o600 });
      return { outcome: 'done', artifacts: [{ source: file, name: filename, kind: 'data' }] };
    },
  };
}

async function put(queue, { jobId, stage, owner, token, generation, dir, name, body, kind = 'data' }) {
  const file = path.join(dir, `${name}-${owner}-${Date.now()}`);
  await fs.writeFile(file, body, { mode: 0o600 });
  return queue.putArtifact({ jobId, stage, owner, token, generation, source: file, name, kind });
}

test('QA handoff producer + two independent consumers + QA/reviewer/verifier, with a needs_review stop', async (t) => {
  const { queue, config } = await newQueue(t, { maxConcurrency: 2 });
  const list = await makeAllowlist(t, ['9000001', '9000002']);
  const p1 = await packageFor(t, { id: '9000001', title: '合成QA样卷A' });
  const p2 = await packageFor(t, { id: '9000002', title: '合成QA样卷B' });
  const r1 = await importQaHandoff({ queue, config, filename: p1.handoffFile, artifactRoot: p1.dir, allowlist: list });
  const r2 = await importQaHandoff({ queue, config, filename: p2.handoffFile, artifactRoot: p2.dir, allowlist: list });
  assert.equal(r1.created, true);
  assert.equal(r2.created, true);
  const manifestBefore = buildStageManifest({ jobs: await queue.listJobs(), stage: 'normalized', config });
  assert.equal(manifestBefore.tasks.length, 2);
  assert.ok(manifestBefore.tasks.every((task) => task.actionable && !task.blocked));
  assert.ok(manifestBefore.tasks.every((task) => task.permissions.readOnly && task.permissions.browserProfile === false));

  const scratch = await privateDir(t, 'qa-e2e-scratch-');
  const [n1, n2] = await Promise.all([
    runWorkerDrain({ queue, config, role: 'normalizer', stage: 'normalized', budget: 1, owner: 'normalizer-1', adapter: stageAdapter(scratch, 'normalized.json', 80) }),
    runWorkerDrain({ queue, config, role: 'normalizer', stage: 'normalized', budget: 1, owner: 'normalizer-2', adapter: stageAdapter(scratch, 'normalized.json', 80) }),
  ]);
  assert.equal(n1.claimed, 1);
  assert.equal(n2.claimed, 1);
  assert.notEqual(n1.results[0].jobId, n2.results[0].jobId, 'two consumers must take different jobs');
  const jobs = new Map((await queue.listJobs()).map((job) => [job.paperSourceId, job]));
  const a = jobs.get('9000001');
  const b = jobs.get('9000002');
  assert.equal(a.stages.normalized.status, 'done');
  assert.equal(b.stages.normalized.status, 'done');

  // Consumer A: aligned → assets_qa with image-manifest SHA gate.
  let claim = await queue.claimStage('aligned', { role: 'matcher', owner: 'matcher-a', jobId: a.jobId });
  let artifact = await put(queue, { jobId: a.jobId, stage: 'aligned', owner: 'matcher-a', token: claim.lease.token, generation: claim.lease.generation, dir: scratch, name: 'aligned.json', body: '{"aligned":true}\n' });
  await queue.completeStage({ jobId: a.jobId, stage: 'aligned', owner: 'matcher-a', token: claim.lease.token, generation: claim.lease.generation, artifacts: [artifact] });

  claim = await queue.claimStage('assets_qa', { role: 'assets_qa', owner: 'assets-a', jobId: a.jobId });
  const assets = await put(queue, { jobId: a.jobId, stage: 'assets_qa', owner: 'assets-a', token: claim.lease.token, generation: claim.lease.generation, dir: scratch, name: 'assets.json', body: '{"checked":true}\n' });
  await assert.rejects(queue.completeStage({
    jobId: a.jobId, stage: 'assets_qa', owner: 'assets-a', token: claim.lease.token,
    generation: claim.lease.generation, artifacts: [assets],
  }), /IMAGE_ASSET_MANIFEST_REQUIRED/);
  const wrongImages = await put(queue, {
    jobId: a.jobId, stage: 'assets_qa', owner: 'assets-a', token: claim.lease.token,
    generation: claim.lease.generation, dir: scratch, name: 'images.json', kind: 'image_manifest',
    body: JSON.stringify({ images: [{ ref: 'material/q1.png', sha256: SHA('0'), bytes: 12 }] }) + '\n',
  });
  await assert.rejects(queue.completeStage({
    jobId: a.jobId, stage: 'assets_qa', owner: 'assets-a', token: claim.lease.token,
    generation: claim.lease.generation, artifacts: [assets, wrongImages],
  }), /IMAGE_HASH_MISMATCH/);
  const images = await put(queue, {
    jobId: a.jobId, stage: 'assets_qa', owner: 'assets-a', token: claim.lease.token,
    generation: claim.lease.generation, dir: scratch, name: 'images.json', kind: 'image_manifest',
    body: JSON.stringify({ images: [{ ref: 'material/q1.png', sha256: SHA('a'), bytes: 12 }] }) + '\n',
  });
  await queue.completeStage({ jobId: a.jobId, stage: 'assets_qa', owner: 'assets-a', token: claim.lease.token, generation: claim.lease.generation, artifacts: [assets, images] });

  // Consumer A: answer → human → candidate → verifier.
  for (const [stage, role, declarations] of [
    ['answer_explanation_qa', 'answer_qa', { answerProvenance: 'source_observed' }],
    ['human_review', 'reviewer', { approved: true, reviewer: 'fixture-reviewer' }],
    ['candidate_ready', 'verifier', { citationsVerified: true, imagesVerified: true }],
  ]) {
    claim = await queue.claimStage(stage, { role, owner: `${role}-a`, jobId: a.jobId });
    artifact = await put(queue, { jobId: a.jobId, stage, owner: `${role}-a`, token: claim.lease.token, generation: claim.lease.generation, dir: scratch, name: `${stage}.json`, body: '{"ok":true}\n' });
    await queue.completeStage({ jobId: a.jobId, stage, owner: `${role}-a`, token: claim.lease.token, generation: claim.lease.generation, artifacts: [artifact], declarations });
  }
  const verified = await queue.verify({ jobId: a.jobId, actor: 'verifier-a', receipt: { path: 'candidate_ready.json' } });
  assert.equal(verified.status, 'verified');

  // Consumer B stops at needs_review and never becomes candidate_ready.
  claim = await queue.claimStage('aligned', { role: 'matcher', owner: 'matcher-b', jobId: b.jobId });
  await queue.failStage({
    jobId: b.jobId, stage: 'aligned', owner: 'matcher-b', token: claim.lease.token,
    generation: claim.lease.generation, outcome: 'needs_review', reason: 'synthetic mapping requires a human',
  });
  assert.equal((await queue.getJob(b.jobId)).status, 'needs_review');
  const manifestAfter = buildStageManifest({ jobs: await queue.listJobs(), stage: 'aligned', config });
  const blocked = manifestAfter.tasks.find((task) => task.jobId === b.jobId);
  assert.ok(blocked);
  assert.equal(blocked.blocked, true);
  assert.equal(blocked.actionable, false);

  const status = await queue.status();
  assert.equal(status.metrics.sourcesEnqueued, 2);
  assert.equal(status.metrics.verified, 1);
  assert.equal(status.metrics.stagesConsumed, 9);
  assert.equal(status.metrics.needsReview, 1);
  assert.equal(status.metrics.blocked, 0);
  assert.equal(status.metrics.queueDepth, 0);
  assert.equal(status.metrics.pendingReview, 1);
  assert.equal(status.metrics.leasesActive, 0);
  assert.ok(status.metrics.artifacts.count >= 12);
});
