import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { newQueue, enqueueInput } from './helpers.mjs';
import { sha256File } from '../src/fsutil.mjs';
import { importFast10Directory } from '../src/qa-handoff.mjs';
import { runWorkerDrain } from '../src/collector.mjs';
import worker from '../src/fast10-worker.mjs';

const SHA = (c) => c.repeat(64);

async function privateDir(t, prefix = 'fast10-') {
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

function questions({ clean = false } = {}) {
  return [
    { sourceNumber: 1, repositoryNumber: 1, category: 'normalized_equal', image: { sourceImages: 1, repoImages: 1 }, imageSha: [SHA('a')], optionHash: SHA('1'), optionCount: 4, score: 1, answerStatus: 'unverified_answer' },
    { sourceNumber: 2, repositoryNumber: null, category: 'source_stub', image: { sourceImages: 0, repoImages: 0 }, imageSha: [], optionHash: null, optionCount: 4, score: null, answerStatus: 'missing' },
    { sourceNumber: 3, repositoryNumber: null, category: clean ? 'normalized_equal' : 'image_unknown', image: { sourceImages: clean ? 1 : 0, repoImages: 1 }, imageSha: clean ? [SHA('c')] : [], optionHash: SHA('2'), optionCount: 4, score: clean ? 1 : null, answerStatus: 'unverified_answer' },
  ];
}

function countsFor(qs) {
  const counts = {};
  for (const q of qs) counts[q.category] = (counts[q.category] ?? 0) + 1;
  return counts;
}

async function makeFast10Dir(t, { sourceId = '9200001', label = '合成fast10样卷A', area = '浙江', year = 2026, variant = 'C类', clean = false, mutateShard = null, fileMode = 0o600 } = {}) {
  const dir = await privateDir(t);
  const qs = questions({ clean });
  const shard = {
    schemaVersion: 1, at: '2026-10-18T00:00:00.000Z', kind: 'paper-shard', credentials: 'none',
    containsQuestionText: false, containsImageBytes: false,
    sourceId, label, area, year, variant, repoPaper: `省考/${area}/${year}/行测-${variant}.md`,
    identity: { titleLength: label.length, version: 'recall-v1' },
    rights: { category: 'observed_ui', redistribution: 'local_only' },
    questions: qs, counts: countsFor(qs), closure: { slots: qs.length, grouped: qs.length },
    evidence: { level: 'single-source (fenbi UI) + repo paper; no independent third-party QA', officialVerification: false },
  };
  if (mutateShard) mutateShard(shard);
  const file = path.join(dir, `shard-${sourceId}.json`);
  await writePrivate(file, JSON.stringify(shard, null, 2) + '\n');
  await fs.chmod(file, fileMode);
  const hashed = await sha256File(file);
  const manifest = {
    schemaVersion: 1, at: '2026-10-18T00:00:00.000Z', kind: 'fast10-shard-handoff',
    credentials: 'none', containsQuestionText: false, containsImageBytes: false, status: 'OK',
    shards: [{ sourceId, label, file: path.basename(file), handoffSha256: hashed.sha256, slots: qs.length, counts: countsFor(qs) }],
    totals: { shards: 1, slots: qs.length, counts: countsFor(qs) },
  };
  const manifestFile = path.join(dir, 'handoff-manifest.json');
  await writePrivate(manifestFile, JSON.stringify(manifest, null, 2) + '\n');
  return { dir, file, manifestFile, shard, hashed };
}

async function allowlist(t, ids) {
  const dir = await privateDir(t, 'fast10-allow-');
  const file = path.join(dir, 'allowlist.json');
  await writePrivate(file, JSON.stringify({ sourceIds: ids.map((id) => ({ id })) }));
  return { source: file, missing: false, ids: new Set(ids), entries: new Map(ids.map((id) => [id, { id }])), list: ids.map((id) => ({ id })) };
}

async function pendingJob(queue, id) {
  await queue.enqueue(enqueueInput({ paperSourceId: id, version: 'recall-v1', title: `合成fast10样卷-${id}`, area: '浙江', year: 2026, variant: 'C类' }));
  return (await queue.listJobs()).find((job) => job.paperSourceId === id);
}

test('fast10 shard attaches to an existing pending capture job as offline_handoff, idempotently', async (t) => {
  const { queue, config } = await newQueue(t, { maxConcurrency: 2 });
  const pkg = await makeFast10Dir(t, { sourceId: '9200001' });
  const list = await allowlist(t, ['9200001']);
  const before = await pendingJob(queue, '9200001');
  assert.equal(before.stages.capture_ready.status, 'pending');
  const result = await importFast10Directory({ queue, config, directory: pkg.dir, allowlist: list, maxFiles: 1 });
  assert.equal(result.counts.files, 1);
  assert.equal(result.counts.attached, 1);
  const job = await queue.getJob(before.jobId);
  assert.equal(job.stages.capture_ready.status, 'done');
  assert.equal(job.stages.capture_ready.mode, 'offline_handoff');
  assert.equal(job.stages.normalized.status, 'pending');
  assert.equal(job.allowCapture, false);
  assert.equal(job.qaSummary.questionCount, 3);
  assert.equal(job.images.length, 1);
  assert.equal((await queue.listJobs()).length, 1);
  const again = await importFast10Directory({ queue, config, directory: pkg.dir, allowlist: list, maxFiles: 1 });
  assert.equal(again.counts.duplicates, 1);
  assert.equal(again.counts.attached, 0);
  assert.equal((await queue.listJobs()).length, 1);
});

test('fast10 permissions, manifest hash, content, rights, URL and image SHA fail closed', async (t) => {
  const { queue, config } = await newQueue(t);
  const list = await allowlist(t, ['9200001']);
  const loose = await makeFast10Dir(t, { fileMode: 0o644 });
  await pendingJob(queue, '9200001');
  await assert.rejects(importFast10Directory({ queue, config, directory: loose.dir, allowlist: list, maxFiles: 1 }), /QA_HANDOFF_INSECURE_PERMISSIONS/);

  const text = await makeFast10Dir(t, { mutateShard: (s) => { s.containsQuestionText = true; } });
  await assert.rejects(importFast10Directory({ queue, config, directory: text.dir, allowlist: list, maxFiles: 1 }), /QA_HANDOFF_RAW_CONTENT/);
  const rights = await makeFast10Dir(t, { mutateShard: (s) => { s.rights.redistribution = 'allowed'; } });
  await assert.rejects(importFast10Directory({ queue, config, directory: rights.dir, allowlist: list, maxFiles: 1 }), /QA_HANDOFF_REDISTRIBUTION/);
  const url = await makeFast10Dir(t, { mutateShard: (s) => { s.label = 'https://evil.test/x'; } });
  await assert.rejects(importFast10Directory({ queue, config, directory: url.dir, allowlist: list, maxFiles: 1 }), /QA_HANDOFF_URL_NOT_ALLOWED/);
  const sha = await makeFast10Dir(t, { mutateShard: (s) => { s.questions[0].imageSha = ['not-a-sha']; } });
  await assert.rejects(importFast10Directory({ queue, config, directory: sha.dir, allowlist: list, maxFiles: 1 }), /QA_HANDOFF_SCHEMA/);

  const badManifest = await makeFast10Dir(t);
  const manifest = JSON.parse(await fs.readFile(badManifest.manifestFile, 'utf8'));
  manifest.shards[0].handoffSha256 = SHA('0');
  await writePrivate(badManifest.manifestFile, JSON.stringify(manifest, null, 2) + '\n');
  await assert.rejects(importFast10Directory({ queue, config, directory: badManifest.dir, allowlist: list, maxFiles: 1 }), /QA_HANDOFF_HASH_MISMATCH/);
  assert.equal((await queue.listJobs()).length, 1, 'only the pending job exists; no attach from rejected packages');
});

test('two offline consumers process fast10 metadata; assets QA stops on image_unknown and answer QA stops at needs_review', async (t) => {
  const { queue, config } = await newQueue(t, { maxConcurrency: 2 });
  const list = await allowlist(t, ['9200001', '9200002']);
  const clean = await makeFast10Dir(t, { sourceId: '9200001', label: '合成fast10样卷A', clean: true });
  const dirty = await makeFast10Dir(t, { sourceId: '9200002', label: '合成fast10样卷B', clean: false });
  await pendingJob(queue, '9200001');
  await pendingJob(queue, '9200002');
  await importFast10Directory({ queue, config, directory: clean.dir, allowlist: list, maxFiles: 1 });
  await importFast10Directory({ queue, config, directory: dirty.dir, allowlist: list, maxFiles: 1 });
  const jobs = await queue.listJobs();
  assert.equal(jobs.length, 2);
  for (const job of jobs) assert.equal(job.stages.capture_ready.mode, 'offline_handoff');

  const [n1, n2] = await Promise.all([
    runWorkerDrain({ queue, config, role: 'normalizer', stage: 'normalized', budget: 1, owner: 'fast10-n1', adapter: worker }),
    runWorkerDrain({ queue, config, role: 'normalizer', stage: 'normalized', budget: 1, owner: 'fast10-n2', adapter: worker }),
  ]);
  assert.equal(n1.claimed, 1);
  assert.equal(n2.claimed, 1);
  assert.notEqual(n1.results[0].jobId, n2.results[0].jobId);
  const bySource = new Map((await queue.listJobs()).map((job) => [job.paperSourceId, job]));
  assert.equal(bySource.get('9200001').stages.normalized.status, 'done');
  assert.equal(bySource.get('9200002').stages.normalized.status, 'done');

  async function consumeTarget(jobId, stage, role, owner) {
    const claim = await queue.claimStage(stage, { role, owner, jobId });
    assert.ok(claim, `expected claim for ${jobId}/${stage}`);
    const result = await worker.process(claim.job, { stage, config });
    if (result.outcome && ['partial', 'skipped_placeholder', 'blocked_auth', 'blocked_rights', 'needs_review', 'dead_letter'].includes(result.outcome)) {
      await queue.failStage({ jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation, outcome: result.outcome, reason: result.reason });
      return result.outcome;
    }
    const artifacts = [];
    for (const item of result.artifacts ?? []) {
      artifacts.push(await queue.putArtifact({ jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation, source: item.source, name: item.name, kind: item.kind }));
    }
    await queue.completeStage({ jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation, artifacts, declarations: result.declarations ?? {} });
    return 'done';
  }

  assert.equal(await consumeTarget(bySource.get('9200001').jobId, 'aligned', 'matcher', 'fast10-align-clean'), 'done');
  assert.equal(await consumeTarget(bySource.get('9200002').jobId, 'aligned', 'matcher', 'fast10-align-dirty'), 'done');
  assert.equal(await consumeTarget(bySource.get('9200001').jobId, 'assets_qa', 'assets_qa', 'fast10-assets-clean'), 'done');
  const cleanJob = await queue.getJob(bySource.get('9200001').jobId);
  assert.equal(cleanJob.stages.assets_qa.status, 'done');
  assert.equal(cleanJob.stages.assets_qa.artifacts.some((item) => item.kind === 'image_manifest'), true);

  assert.equal(await consumeTarget(bySource.get('9200002').jobId, 'assets_qa', 'assets_qa', 'fast10-assets-dirty'), 'needs_review');
  const dirtyJob = await queue.getJob(bySource.get('9200002').jobId);
  assert.equal(dirtyJob.stages.assets_qa.status, 'needs_review');

  assert.equal(await consumeTarget(bySource.get('9200001').jobId, 'answer_explanation_qa', 'answer_qa', 'fast10-answer'), 'needs_review');
  const answerJob = await queue.getJob(bySource.get('9200001').jobId);
  assert.equal(answerJob.stages.answer_explanation_qa.status, 'needs_review');
  assert.equal(answerJob.status, 'needs_review');
  assert.equal((await queue.status()).metrics.verified, 0);
});
