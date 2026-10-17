import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { validateConfig } from '../src/config.mjs';
import { openQueue } from '../src/queue.mjs';

export async function temporary(t, prefix = 'gwy-pipeline-test-') {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), prefix));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  return dir;
}

export function makeConfig(dir, overrides = {}) {
  return validateConfig({
    dataDir: dir,
    maxConcurrency: 2,
    leaseTtlMs: 60_000,
    collectorLeaseTtlMs: 60_000,
    maxAttempts: 3,
    backoff: { baseMs: 10, factor: 2, maxMs: 1000, jitter: 0 },
    throttle: { minIntervalMs: 100, maxIntervalMs: 10_000, cooldownMs: 1000 },
    backpressure: { maxQueueLength: 50, maxPendingReview: 10, diskFreeFloorBytes: 0, perPaperBytes: 1024 * 1024 },
    // Synthetic tests opt out of the production fail-closed source allowlist.
    authorizedSourceIds: null,
    ...overrides,
  });
}

let counter = 0;
export function enqueueInput(overrides = {}) {
  counter += 1;
  return {
    paperSourceId: `synthetic-${process.pid}-${counter}`,
    version: 'v1',
    title: '合成测试卷（非真实题本）',
    subject: 'xingce',
    area: '浙江',
    year: 2026,
    variant: 'C类',
    url: 'https://www.fenbi.com/spa/tiku/exam/99001?labelId=1',
    urlObserved: true,
    sourceCategory: 'observed_ui',
    evidence: [{ type: 'observed_ui', ref: 'synthetic fixture; no live site was contacted' }],
    expectedQuestions: 2,
    expectedMaterials: 0,
    actor: 'test',
    ...overrides,
  };
}

export async function writeArtifact(queue, jobId, stage, { name = 'artifact.json', body = '{"synthetic":true}\n', kind = 'data' } = {}) {
  const directory = queue.paths.artifactDir(jobId, stage);
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const filename = path.join(directory, name);
  await fs.writeFile(filename, body, { mode: 0o600 });
  return { source: filename, name, kind };
}

export async function claimAndComplete(queue, { jobId, stage, role, owner, declarations = {}, artifact = {} }) {
  const claim = await queue.claimStage(stage, { role, owner, jobId });
  if (!claim) throw new Error(`No claim for ${stage}`);
  const file = await writeArtifact(queue, jobId, stage, artifact);
  const manifest = await queue.putArtifact({
    jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation,
    source: file.source, name: file.name, kind: file.kind,
  });
  const job = await queue.completeStage({
    jobId, stage, owner, token: claim.lease.token, generation: claim.lease.generation,
    artifacts: [manifest], declarations,
  });
  return { claim, job, manifest };
}

export const STAGE_ROLE = {
  capture_ready: 'collector',
  normalized: 'normalizer',
  aligned: 'matcher',
  assets_qa: 'assets_qa',
  answer_explanation_qa: 'answer_qa',
  human_review: 'reviewer',
  candidate_ready: 'verifier',
};

/** Drive all stages up to (but not including) `target`. */
export async function driveTo(queue, jobId, target, { answerProvenance = 'human_authored' } = {}) {
  const order = ['capture_ready', 'normalized', 'aligned', 'assets_qa', 'answer_explanation_qa', 'human_review', 'candidate_ready'];
  for (const stage of order) {
    if (stage === target) return;
    const declarations = stage === 'answer_explanation_qa' ? { answerProvenance }
      : stage === 'human_review' ? { approved: true, reviewer: 'fixture-reviewer' }
        : stage === 'candidate_ready' ? { citationsVerified: true } : {};
    await claimAndComplete(queue, { jobId, stage, role: STAGE_ROLE[stage], owner: `fixture-${stage}`, declarations });
  }
}

export async function newQueue(t, overrides) {
  const dir = await temporary(t);
  const config = makeConfig(dir, overrides);
  const queue = openQueue(config);
  await queue.init();
  return { dir, config, queue };
}
