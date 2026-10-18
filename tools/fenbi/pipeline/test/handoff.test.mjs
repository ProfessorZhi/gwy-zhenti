import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { newQueue, enqueueInput, claimAndComplete, writeArtifact } from './helpers.mjs';
import { buildHandoff, writeHandoff, readHandoff, verifyHandoff, copyHandoffArtifacts } from '../src/handoff.mjs';

async function completedCapture(t) {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const { job } = await claimAndComplete(queue, {
    jobId, stage: 'capture_ready', role: 'collector', owner: 'c1',
    artifact: { name: 'staged.json', body: '{"synthetic":"staged"}\n' },
  });
  return { queue, config, jobId, job, root: queue.paths.artifactDir(jobId, 'capture_ready') };
}

test('a handoff carries hashed artifacts and rights metadata but no profile, cookies or tokens', async (t) => {
  const { job, root } = await completedCapture(t);
  const handoff = buildHandoff({
    job, stage: 'capture_ready', artifacts: job.stages.capture_ready.artifacts, producer: 'fixture-collector',
  });
  const text = JSON.stringify(handoff);
  assert.doesNotMatch(text, /sessionid=|token=|password=|profileDir|-----BEGIN/i);
  assert.equal(handoff.permissions.browserProfile, false);
  assert.equal(handoff.permissions.cookies, false);
  assert.equal(handoff.permissions.tokens, false);
  assert.equal(handoff.source.redistribution, 'local_only');
  assert.equal(handoff.artifacts.length, 1);
  assert.equal(handoff.artifacts[0].path, 'staged.json');
  const verified = await verifyHandoff(handoff, { root });
  assert.equal(verified.artifacts[0].sha256, handoff.artifacts[0].sha256);
  const filename = path.join(t.name.replaceAll(/[^\w.-]+/gu, '-') + '.json');
  void filename;
});

test('handoff verification rejects credentials, escapes, hash mismatches and un-reviewed AI answers', async (t) => {
  const { job, root, queue, jobId } = await completedCapture(t);
  const handoff = buildHandoff({ job, stage: 'capture_ready', artifacts: job.stages.capture_ready.artifacts });
  await assert.rejects(verifyHandoff({ ...handoff, cookies: 'sessionid=SYNTHETIC' }, { root }), /HANDOFF_CREDENTIAL_LEAK/);
  await assert.rejects(verifyHandoff({ ...handoff, artifacts: [{ ...handoff.artifacts[0], path: '../escape.json' }] }, { root }), /escape|relative/);
  await assert.rejects(verifyHandoff({ ...handoff, artifacts: [{ ...handoff.artifacts[0], path: '/absolute.json' }] }, { root }), /relative/);
  await assert.rejects(verifyHandoff({ ...handoff, artifacts: [{ ...handoff.artifacts[0], sha256: '0'.repeat(64) }] }, { root }), /HANDOFF_HASH_MISMATCH/);
  await assert.rejects(verifyHandoff({ ...handoff, permissions: { ...handoff.permissions, browserProfile: true } }), /HANDOFF_PROFILE_LEAK|CREDENTIAL/);
  await assert.rejects(verifyHandoff({ ...handoff, answerProvenance: 'ai_assisted', review: { required: false, reasons: [] } }), /HANDOFF_REVIEW_REQUIRED/);
  await assert.rejects(verifyHandoff({ ...handoff, observed: { ...handoff.observed, url: 'https://www.fenbi.com/x?token=SYNTHETIC' } }), /CREDENTIAL_LEAK|BAD_URL/);
  // A clean handoff still verifies after all those rejected copies.
  assert.equal((await verifyHandoff(handoff, { root })).ok, true);
  const status = await queue.status();
  assert.equal(status.jobs.total, 1);
  assert.equal(status.completed, 0);
  void jobId;
});

test('copyHandoffArtifacts is hash-checked and refuses duplicate paths', async (t) => {
  const { job, root } = await completedCapture(t);
  const handoff = buildHandoff({ job, stage: 'capture_ready', artifacts: job.stages.capture_ready.artifacts });
  const destination = path.join(path.dirname(root), 'copy-target');
  const copied = await copyHandoffArtifacts(handoff, root, destination);
  assert.equal(copied.length, 1);
  assert.equal(await fs.readFile(path.join(destination, 'staged.json'), 'utf8'), '{"synthetic":"staged"}\n');
  const doubled = { ...handoff, artifacts: [handoff.artifacts[0], { ...handoff.artifacts[0] }] };
  await assert.rejects(copyHandoffArtifacts(doubled, root, path.join(destination, 'dup')), /HANDOFF_DUPLICATE_ARTIFACT/);
});

test('write/read round-trips a minimal handoff on disk at 0600', async (t) => {
  const { job, root } = await completedCapture(t);
  const handoff = buildHandoff({ job, stage: 'capture_ready', artifacts: job.stages.capture_ready.artifacts });
  const filename = path.join(path.dirname(root), 'handoff.json');
  await writeHandoff(filename, handoff);
  const stat = await fs.stat(filename);
  assert.equal(stat.mode & 0o777, 0o600);
  const { handoff: loaded, verified } = await readHandoff(filename, { root });
  assert.equal(loaded.jobId, job.jobId);
  assert.equal(verified.totalBytes, handoff.artifacts[0].bytes);
});

test('an offline licensed-donor job starts after capture and never opens capture_ready', async (t) => {
  const { queue } = await newQueue(t);
  const input = {
    paperSourceId: 'donor-1', version: 'v1', title: '合成授权样卷', subject: 'xingce',
    area: '浙江', year: 2025, sourceCategory: 'licensed_donor', license: 'synthetic-test-license',
    redistribution: 'local_only', evidence: [{ type: 'license_record', ref: 'synthetic permission for tests only' }],
  };
  const { jobIdFor } = await import('../src/identity.mjs');
  const { sha256File } = await import('../src/fsutil.mjs');
  const jobId = jobIdFor(input);
  const directory = queue.paths.artifactDir(jobId, 'capture_ready');
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const filename = path.join(directory, 'paper.json');
  await fs.writeFile(filename, '{"synthetic":"donor"}\n', { mode: 0o600 });
  const hashed = await sha256File(filename);
  const manifest = [{ path: 'paper.json', kind: 'normalized_source', sha256: hashed.sha256, bytes: hashed.bytes }];
  const created = await queue.enqueueOffline(input, manifest);
  assert.equal(created.created, true);
  const job = created.job;
  assert.equal(job.stages.capture_ready.status, 'done');
  assert.equal(job.stages.capture_ready.mode, 'offline_handoff');
  assert.equal(job.allowCapture, false);
  assert.equal(await queue.claimStage('capture_ready', { role: 'collector', owner: 'c1' }), null);
  const normalized = await queue.claimStage('normalized', { role: 'normalizer', owner: 'n1' });
  assert.equal(normalized.job.jobId, job.jobId);
  assert.equal((await queue.status()).completed, 0);
});

test('handoff artifacts cannot silently rewrite a different stage directory', async (t) => {
  const { queue, jobId } = await completedCapture(t);
  const file = await writeArtifact(queue, jobId, 'normalized', { name: 'n.json' });
  // putArtifact only accepts an active lease owned by the caller.
  await assert.rejects(queue.putArtifact({
    jobId, stage: 'normalized', owner: 'intruder', token: 'not-a-token', generation: 1,
    source: file.source, name: file.name,
  }), /LEASE_LOST/);
});
