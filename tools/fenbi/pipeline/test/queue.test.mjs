import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { newQueue, enqueueInput, writeArtifact, driveTo, claimAndComplete } from './helpers.mjs';
import { acquireLease } from '../src/lease.mjs';

test('enqueue is idempotent per paperSourceId+version and conflicting identity is refused', async (t) => {
  const { queue } = await newQueue(t);
  const input = enqueueInput();
  const first = await queue.enqueue(input);
  assert.equal(first.created, true);
  const second = await queue.enqueue({ ...input });
  assert.equal(second.created, false);
  assert.equal(second.duplicate, true);
  assert.equal((await queue.listJobs()).length, 1);
  await assert.rejects(queue.enqueue({ ...input, title: '另一个标题' }), /DUPLICATE_CONFLICT/);
  const job = await queue.getJob(first.jobId);
  assert.notEqual(job.taskKeys.capture_ready, job.taskKeys.normalized, 'task key includes the processing stage');
  assert.equal(new Set(Object.values(job.taskKeys)).size, 7);
});

test('capture_ready only accepts an explicitly observed, credential-free practice URL', async (t) => {
  const { queue } = await newQueue(t);
  await assert.rejects(queue.enqueue(enqueueInput({ urlObserved: false })), /explicitly observed/);
  await assert.rejects(queue.enqueue(enqueueInput({ url: 'https://www.fenbi.com/spa/tiku?token=SECRET' })), /credential-like/);
  await assert.rejects(queue.enqueue(enqueueInput({ url: 'https://user:pass@www.fenbi.com/spa/tiku' })), /without credentials/);
  await assert.rejects(queue.enqueue(enqueueInput({ url: 'https://evil.test/spa/tiku' })), /authorised practice host/);
  await assert.rejects(queue.enqueue(enqueueInput({ sourceCategory: 'licensed_donor', license: 'CC-BY', url: 'https://www.fenbi.com/spa/tiku' })), /OFFLINE_HANDOFF_REQUIRED/);
  const job = await queue.enqueue(enqueueInput({ url: 'https://www.fenbi.com/spa/tiku?labelId=1&utm_source=x#fragment' }));
  assert.equal(job.job.url, 'https://www.fenbi.com/spa/tiku?labelId=1');
  assert.equal(job.job.allowCapture, true);
  assert.equal(job.job.permissions.browserProfile, false);
  assert.equal(job.job.permissions.cookies, false);
});

test('roles are confined to their own stage and two consumers cannot claim the same lease', async (t) => {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  await assert.rejects(queue.claimStage('capture_ready', { role: 'normalizer', owner: 'n1' }), /ROLE_FORBIDDEN/);
  const claim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c1' });
  assert.ok(claim);
  const second = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c2' });
  assert.equal(second, null);
  await assert.rejects(acquireLease(config.dataDir, jobId, 'capture_ready', { owner: 'c3' }), (error) => error.code === 'LEASE_HELD');
  await assert.rejects(queue.claimStage('normalized', { role: 'collector', owner: 'c1' }), /ROLE_FORBIDDEN/);
});

test('a crashed lease is reclaimed, generation advances and the old owner cannot commit', async (t) => {
  const { queue, config } = await newQueue(t, { leaseTtlMs: 1000, collectorLeaseTtlMs: 1000 });
  const { jobId } = await queue.enqueue(enqueueInput());
  const first = await queue.claimStage('capture_ready', { role: 'collector', owner: 'old-owner' });
  const future = Date.now() + 5000;
  const reconciled = await queue.reconcile({ now: future });
  assert.equal(reconciled.reclaimed.length, 1);
  assert.equal(reconciled.reclaimed[0].jobId, jobId);
  const jobAfter = await queue.getJob(jobId);
  assert.equal(jobAfter.stages.capture_ready.status, 'pending');
  assert.equal(jobAfter.stages.capture_ready.attempts, 1);
  const retryAt = jobAfter.stages.capture_ready.nextAttemptAt;
  const second = await queue.claimStage('capture_ready', { role: 'collector', owner: 'new-owner', now: retryAt });
  assert.equal(second.lease.generation, 2);
  const file = await writeArtifact(queue, jobId, 'capture_ready');
  await assert.rejects(queue.completeStage({
    jobId, stage: 'capture_ready', owner: 'old-owner', token: first.lease.token,
    generation: first.lease.generation, artifacts: [file], now: future,
  }), /LEASE_LOST|LEASE_EXPIRED/);
  const manifest = await queue.putArtifact({
    jobId, stage: 'capture_ready', owner: 'new-owner', token: second.lease.token,
    generation: second.lease.generation, source: file.source, name: file.name, now: retryAt,
  });
  const done = await queue.completeStage({
    jobId, stage: 'capture_ready', owner: 'new-owner', token: second.lease.token,
    generation: second.lease.generation, artifacts: [manifest], now: retryAt,
  });
  assert.equal(done.stages.capture_ready.status, 'done');
});

test('partial outcomes back off, resume, and become dead letters after the attempt ceiling', async (t) => {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  let claim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c1' });
  let job = await queue.failStage({
    jobId, stage: 'capture_ready', owner: 'c1', token: claim.lease.token,
    generation: claim.lease.generation, outcome: 'partial', reason: 'synthetic timeout',
  });
  assert.equal(job.stages.capture_ready.status, 'pending');
  assert.ok(job.stages.capture_ready.nextAttemptAt > Date.now());
  assert.equal(await queue.claimStage('capture_ready', { role: 'collector', owner: 'c2' }), null);
  claim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c2', now: job.stages.capture_ready.nextAttemptAt });
  assert.equal(claim.job.stages.capture_ready.attempts, 2);
  job = await queue.failStage({
    jobId, stage: 'capture_ready', owner: 'c2', token: claim.lease.token,
    generation: claim.lease.generation, outcome: 'partial', reason: 'still failing',
  });
  claim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c3', now: job.stages.capture_ready.nextAttemptAt });
  assert.equal(claim.job.stages.capture_ready.attempts, 3);
  job = await queue.failStage({
    jobId, stage: 'capture_ready', owner: 'c3', token: claim.lease.token,
    generation: claim.lease.generation, outcome: 'partial', reason: 'attempt ceiling',
  });
  assert.equal(job.stages.capture_ready.status, 'dead_letter');
  assert.equal(job.status, 'dead_letter');
  const dead = await fs.readFile(path.join(config.dataDir, 'dead-letter', `${jobId}.capture_ready.json`), 'utf8');
  assert.match(dead, /attempt ceiling/);
});

test('placeholders are skipped, never completed, and never unlock a downstream stage', async (t) => {
  const { queue } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const claim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c1' });
  const file = await writeArtifact(queue, jobId, 'capture_ready');
  const manifest = await queue.putArtifact({
    jobId, stage: 'capture_ready', owner: 'c1', token: claim.lease.token,
    generation: claim.lease.generation, source: file.source, name: file.name,
  });
  await assert.rejects(queue.completeStage({
    jobId, stage: 'capture_ready', owner: 'c1', token: claim.lease.token,
    generation: claim.lease.generation, artifacts: [manifest], declarations: { placeholder: true },
  }), /PLACEHOLDER_NOT_COMPLETABLE/);
  const job = await queue.failStage({
    jobId, stage: 'capture_ready', owner: 'c1', token: claim.lease.token,
    generation: claim.lease.generation, outcome: 'skipped_placeholder', reason: 'Fenbi shows 未征集',
  });
  assert.equal(job.status, 'skipped_placeholder');
  assert.equal(await queue.claimStage('normalized', { role: 'normalizer', owner: 'n1' }), null);
  const status = await queue.status();
  assert.equal(status.completed, 0);
  assert.equal(status.jobs.byStatus.skipped_placeholder, 1);
});

test('AI-assisted or unknown answers cannot complete the answer stage', async (t) => {
  const { queue } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  await driveTo(queue, jobId, 'answer_explanation_qa');
  for (const provenance of ['ai_assisted', 'unknown']) {
    const claim = await queue.claimStage('answer_explanation_qa', { role: 'answer_qa', owner: `a-${provenance}` });
    const file = await writeArtifact(queue, jobId, 'answer_explanation_qa', { name: 'answers.json' });
    const manifest = await queue.putArtifact({
      jobId, stage: 'answer_explanation_qa', owner: `a-${provenance}`, token: claim.lease.token,
      generation: claim.lease.generation, source: file.source, name: file.name,
    });
    await assert.rejects(queue.completeStage({
      jobId, stage: 'answer_explanation_qa', owner: `a-${provenance}`, token: claim.lease.token,
      generation: claim.lease.generation, artifacts: [manifest], declarations: { answerProvenance: provenance },
    }), /ANSWER_PROVENANCE_UNVERIFIED/);
    await queue.failStage({
      jobId, stage: 'answer_explanation_qa', owner: `a-${provenance}`, token: claim.lease.token,
      generation: claim.lease.generation, outcome: 'needs_review', reason: `${provenance} provenance needs a human`,
    });
    await queue.reopen({ jobId, stage: 'answer_explanation_qa', actor: 'fixture-reviewer', reason: 'replace with sourced answer' });
  }
  const claim = await queue.claimStage('answer_explanation_qa', { role: 'answer_qa', owner: 'a-human' });
  const file = await writeArtifact(queue, jobId, 'answer_explanation_qa', { name: 'answers.json' });
  const manifest = await queue.putArtifact({
    jobId, stage: 'answer_explanation_qa', owner: 'a-human', token: claim.lease.token,
    generation: claim.lease.generation, source: file.source, name: file.name,
  });
  const done = await queue.completeStage({
    jobId, stage: 'answer_explanation_qa', owner: 'a-human', token: claim.lease.token,
    generation: claim.lease.generation, artifacts: [manifest], declarations: { answerProvenance: 'source_observed' },
  });
  assert.equal(done.stages.answer_explanation_qa.status, 'done');
});

test('human review and candidate promotion require explicit declarations; only verification counts as complete', async (t) => {
  const { queue } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  await driveTo(queue, jobId, 'human_review');
  const reviewClaim = await queue.claimStage('human_review', { role: 'reviewer', owner: 'r1' });
  const reviewFile = await writeArtifact(queue, jobId, 'human_review', { name: 'review.json' });
  const reviewManifest = await queue.putArtifact({
    jobId, stage: 'human_review', owner: 'r1', token: reviewClaim.lease.token,
    generation: reviewClaim.lease.generation, source: reviewFile.source, name: reviewFile.name,
  });
  await assert.rejects(queue.completeStage({
    jobId, stage: 'human_review', owner: 'r1', token: reviewClaim.lease.token,
    generation: reviewClaim.lease.generation, artifacts: [reviewManifest],
  }), /REVIEW_NOT_APPROVED/);
  await queue.completeStage({
    jobId, stage: 'human_review', owner: 'r1', token: reviewClaim.lease.token,
    generation: reviewClaim.lease.generation, artifacts: [reviewManifest],
    declarations: { approved: true, reviewer: 'fixture-reviewer' },
  });

  const candidateClaim = await queue.claimStage('candidate_ready', { role: 'verifier', owner: 'v1' });
  const receipt = await writeArtifact(queue, jobId, 'candidate_ready', { name: 'receipt.json' });
  const receiptManifest = await queue.putArtifact({
    jobId, stage: 'candidate_ready', owner: 'v1', token: candidateClaim.lease.token,
    generation: candidateClaim.lease.generation, source: receipt.source, name: receipt.name,
  });
  await assert.rejects(queue.completeStage({
    jobId, stage: 'candidate_ready', owner: 'v1', token: candidateClaim.lease.token,
    generation: candidateClaim.lease.generation, artifacts: [receiptManifest],
  }), /CITATIONS_UNVERIFIED/);
  const candidate = await queue.completeStage({
    jobId, stage: 'candidate_ready', owner: 'v1', token: candidateClaim.lease.token,
    generation: candidateClaim.lease.generation, artifacts: [receiptManifest],
    declarations: { citationsVerified: true },
  });
  assert.equal(candidate.status, 'candidate_ready');
  let status = await queue.status();
  assert.equal(status.completed, 0);
  assert.equal(status.jobs.candidateReady, 1);

  await assert.rejects(queue.verify({ jobId, actor: 'v1', receipt: { path: '../escape.json' } }), /escapes|relative/);
  const verified = await queue.verify({ jobId, actor: 'v1', receipt: { path: 'receipt.json', sha256: receiptManifest.sha256 } });
  assert.equal(verified.status, 'verified');
  status = await queue.status();
  assert.equal(status.completed, 1);
  assert.equal(status.jobs.candidateReady, 0);
  await assert.rejects(queue.verify({ jobId, actor: 'v1', receipt: { path: 'receipt.json' } }), /ALREADY_VERIFIED/);
});

test('reopen is explicit and reconcile never invents jobs', async (t) => {
  const { queue } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const claim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c1' });
  await queue.failStage({
    jobId, stage: 'capture_ready', owner: 'c1', token: claim.lease.token,
    generation: claim.lease.generation, outcome: 'blocked_auth', reason: 'synthetic 401',
  });
  await assert.rejects(queue.reopen({ jobId, stage: 'capture_ready', actor: 'human', reason: '' }), /REASON_REQUIRED/);
  const reopened = await queue.reopen({ jobId, stage: 'capture_ready', actor: 'human', reason: 'logged in again' });
  assert.equal(reopened.stages.capture_ready.status, 'pending');
  assert.equal((await queue.listJobs()).length, 1);
  const reconciled = await queue.reconcile();
  assert.equal((await queue.listJobs()).length, 1);
  assert.equal(reconciled.reclaimed.length, 0);
});

test('job, lease and artifact files are private', async (t) => {
  const { queue, config } = await newQueue(t);
  const { jobId } = await queue.enqueue(enqueueInput());
  const jobStat = await fs.stat(path.join(config.dataDir, 'jobs', `${jobId}.json`));
  assert.equal(jobStat.mode & 0o777, 0o600);
  const rootStat = await fs.stat(config.dataDir);
  assert.equal(rootStat.mode & 0o777, 0o700);
  const claim = await queue.claimStage('capture_ready', { role: 'collector', owner: 'c1' });
  const file = await writeArtifact(queue, jobId, 'capture_ready');
  const manifest = await queue.putArtifact({
    jobId, stage: 'capture_ready', owner: 'c1', token: claim.lease.token,
    generation: claim.lease.generation, source: file.source, name: file.name,
  });
  assert.equal(manifest.bytes > 0, true);
  const artifactStat = await fs.stat(path.join(config.dataDir, 'artifacts', jobId, 'capture_ready', file.name));
  assert.equal(artifactStat.mode & 0o777, 0o600);
});
