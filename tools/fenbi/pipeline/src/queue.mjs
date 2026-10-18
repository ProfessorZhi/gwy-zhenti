import fs from 'node:fs/promises';
import path from 'node:path';
import {
  atomicWriteJson, digest, diskFreeBytes, ensurePrivateDir, nowIso, readJson, readObject,
  safeChild, sha256File, withFileLock,
} from './fsutil.mjs';
import { queuePaths } from './config.mjs';
import {
  NON_COMPLETION, REPORTABLE_OUTCOMES, ROLE_STAGES, STAGES, STAGE_INDEX, SUCCESS, TERMINAL_BAD,
} from './constants.mjs';
import {
  assertArtifactRelative, identityFingerprint, jobIdFor, normalizeEnqueueInput, taskKeyFor,
} from './identity.mjs';
import { acquireLease, assertLease, readLease, releaseLease } from './lease.mjs';

function queueError(code, message, extra = {}) {
  return Object.assign(new Error(`[${code}] ${message}`), { code, ...extra });
}

export function backoffFor(attempts, config, { random = Math.random } = {}) {
  const { baseMs, factor, maxMs, jitter } = config.backoff;
  const raw = Math.min(maxMs, baseMs * factor ** Math.max(0, attempts - 1));
  const spread = raw * jitter * random();
  return Math.round(raw + spread);
}

export function deriveStatus(job) {
  if (job.verifiedAt) return 'verified';
  for (const stage of STAGES) {
    const status = job.stages?.[stage]?.status;
    if (TERMINAL_BAD.includes(status)) return status;
  }
  if (Object.values(job.stages ?? {}).some((entry) => entry.status === SUCCESS) === false) {
    if (Object.values(job.stages ?? {}).some((entry) => entry.status === 'leased')) return 'running';
    return 'queued';
  }
  if (Object.values(job.stages).some((entry) => entry.status === 'partial')) return 'partial';
  if (Object.values(job.stages).some((entry) => entry.status === 'leased')) return 'running';
  if (job.stages.candidate_ready?.status === SUCCESS) return 'candidate_ready';
  return 'queued';
}

function initialStages(now) {
  return Object.fromEntries(STAGES.map((stage) => [stage, {
    status: 'pending', attempts: 0, nextAttemptAt: 0, artifacts: [], lease: null,
    reason: null, updatedAt: now,
  }]));
}

function assertStage(stage) {
  if (!STAGES.includes(stage)) throw queueError('INVALID_STAGE', `Unknown stage: ${stage}`);
}

export class PipelineQueue {
  constructor(config) {
    this.config = config;
    this.paths = queuePaths(config.dataDir);
    this.now = () => Date.now();
  }

  async init() {
    for (const directory of [
      this.paths.root, this.paths.jobs, this.paths.leases, this.paths.staleLeases,
      this.paths.artifacts, this.paths.handoffs, this.paths.deadLetter, this.paths.state, this.paths.review,
    ]) await ensurePrivateDir(directory);
    return this.paths.root;
  }

  async #scan() {
    let entries = [];
    try { entries = await fs.readdir(this.paths.jobs, { withFileTypes: true }); } catch (error) { if (error.code === 'ENOENT') return { jobs: [], invalid: [] }; throw error; }
    const jobs = [], invalid = [];
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith('.json') || entry.name.startsWith('.')) continue;
      const filename = path.join(this.paths.jobs, entry.name);
      try {
        const job = await readObject(filename);
        if (job.schemaVersion !== 1 || typeof job.jobId !== 'string' || !job.stages) throw queueError('INVALID_STATE', 'Unsupported job record');
        jobs.push(job);
      } catch (error) {
        invalid.push({ file: entry.name, error: error.message });
      }
    }
    jobs.sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)) || a.jobId.localeCompare(b.jobId));
    return { jobs, invalid };
  }

  async listJobs() { return (await this.#scan()).jobs; }

  async getJob(jobId) {
    try { return await readObject(this.paths.jobFile(jobId)); }
    catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  }

  async #mutate(jobId, mutator) {
    return withFileLock(this.paths.jobs, `.${jobId}.lock`, async () => {
      const current = await readObject(this.paths.jobFile(jobId));
      const draft = structuredClone(current);
      const result = await mutator(draft);
      draft.revision = (current.revision ?? 0) + 1;
      draft.updatedAt = nowIso(this.now());
      draft.status = deriveStatus(draft);
      await atomicWriteJson(this.paths.jobFile(jobId), draft);
      return { job: draft, result };
    });
  }

  /**
   * Create exactly one job per (paperSourceId, version). Repeating an identical enqueue returns the
   * existing job. Conflicting metadata for the same key is an error, never a silent overwrite.
   */
  async enqueue(input, { authorizedSourceIds } = {}) {
    await this.init();
    const effectiveConfig = authorizedSourceIds === undefined
      ? this.config
      : { ...this.config, authorizedSourceIds };
    const normalized = normalizeEnqueueInput(input, effectiveConfig, this.now());
    const jobId = jobIdFor(normalized);
    const existing = await this.getJob(jobId);
    if (existing) {
      if (identityFingerprint(existing) !== identityFingerprint({ ...normalized, jobId })) {
        throw queueError('DUPLICATE_CONFLICT', 'Same paperSourceId/version already exists with different identity or permissions; review it instead of overwriting');
      }
      return { created: false, duplicate: true, jobId, job: existing };
    }
    const now = this.now();
    const taskKeys = Object.fromEntries(STAGES.map((stage) => [stage, taskKeyFor(normalized, stage)]));
    const stages = initialStages(now);
    // An offline handoff may already contain a verified staged artifact. It is never a synthetic
    // capture: the caller must provide a manifest and the files are copied by importHandoff().
    if (normalized.startingOffline) {
      throw queueError('OFFLINE_HANDOFF_REQUIRED', 'Offline jobs are created by import-handoff, not by a bare enqueue');
    }
    if (normalized.source.category === 'licensed_donor') {
      throw queueError('OFFLINE_HANDOFF_REQUIRED', 'Licensed donor jobs are imported offline; they never enter capture_ready');
    }
    const job = {
      schemaVersion: 1,
      jobId,
      taskKeys,
      paperSourceId: normalized.paperSourceId,
      version: normalized.version,
      title: normalized.title,
      subject: normalized.subject,
      area: normalized.area,
      year: normalized.year,
      variant: normalized.variant,
      url: normalized.url,
      urlObserved: normalized.urlObserved,
      allowCapture: normalized.allowCapture,
      images: normalized.images,
      source: normalized.source,
      expected: normalized.expected,
      permissions: normalized.permissions,
      createdAt: nowIso(now),
      updatedAt: nowIso(now),
      revision: 1,
      status: 'queued',
      stages,
      history: [{ at: nowIso(now), event: 'enqueued', actor: input.actor ?? 'cli' }],
    };
    await atomicWriteJson(this.paths.jobFile(jobId), job);
    return { created: true, duplicate: false, jobId, job };
  }

  /** Add a manifest-only offline job whose staged artifact has already been imported. */
  async enqueueOffline(input, artifacts) {
    await this.init();
    const normalized = normalizeEnqueueInput({ ...input, offline: true }, this.config, this.now());
    if (!['licensed_donor', 'official'].includes(normalized.source.category)) {
      throw queueError('OFFLINE_SOURCE_REQUIRED', 'Offline jobs need an official or licensed-donor source');
    }
    if (!Array.isArray(artifacts) || !artifacts.length) throw queueError('ARTIFACT_REQUIRED', 'Offline jobs need at least one verified staged artifact');
    const jobId = jobIdFor(normalized);
    const existing = await this.getJob(jobId);
    if (existing) return { created: false, duplicate: true, jobId, job: existing };
    const now = this.now();
    const manifest = await this.#verifyArtifacts({ jobId, stages: {} }, 'capture_ready', artifacts);
    const stages = initialStages(now);
    stages.capture_ready = {
      ...stages.capture_ready, status: SUCCESS, mode: 'offline_handoff',
      artifacts: manifest, completedAt: nowIso(now), updatedAt: nowIso(now),
      reason: 'verified offline handoff; no browser capture was performed',
    };
    const job = {
      schemaVersion: 1, jobId,
      taskKeys: Object.fromEntries(STAGES.map((stage) => [stage, taskKeyFor(normalized, stage)])),
      paperSourceId: normalized.paperSourceId, version: normalized.version,
      title: normalized.title, subject: normalized.subject, area: normalized.area,
      year: normalized.year, variant: normalized.variant,
      url: normalized.url, urlObserved: normalized.urlObserved, allowCapture: false,
      images: normalized.images,
      source: normalized.source, expected: normalized.expected, permissions: normalized.permissions,
      createdAt: nowIso(now), updatedAt: nowIso(now), revision: 1, status: 'queued', stages,
      history: [{ at: nowIso(now), event: 'enqueued_offline', actor: input.actor ?? 'cli' }],
    };
    await atomicWriteJson(this.paths.jobFile(jobId), job);
    return { created: true, duplicate: false, jobId, job };
  }

  #eligible(job, stage, now) {
    if (job.verifiedAt) return false;
    if (TERMINAL_BAD.includes(job.status)) return false;
    const entry = job.stages?.[stage];
    if (!entry || entry.status !== 'pending') return false;
    if (entry.nextAttemptAt && entry.nextAttemptAt > now) return false;
    if ((entry.attempts ?? 0) >= this.config.maxAttempts) return false;
    const index = STAGE_INDEX[stage];
    if (index > 0) {
      const previous = job.stages[STAGES[index - 1]];
      if (previous?.status !== SUCCESS) return false;
    }
    if (stage === 'capture_ready') {
      if (!job.allowCapture || !job.url || !job.urlObserved) return false;
      if (job.source?.category === 'licensed_donor') return false;
    }
    return true;
  }

  /**
   * Claim at most one stage. The lease is acquired before the job record is changed, so two
   * processes racing for the same (job, stage) cannot both observe an unlocked job.
   */
  async claimStage(stage, { role, owner, jobId = null, now = this.now() } = {}) {
    assertStage(stage);
    if (!ROLE_STAGES[role]?.includes(stage)) throw queueError('ROLE_FORBIDDEN', `Role ${role} may not claim ${stage}`);
    if (!owner) throw queueError('OWNER_REQUIRED', 'A stable owner identifier is required');
    await this.init();
    const { jobs } = await this.#scan();
    const candidates = (jobId ? jobs.filter((job) => job.jobId === jobId) : jobs).filter((job) => this.#eligible(job, stage, now));
    if (!candidates.length) return null;
    const ttlMs = stage === 'capture_ready' ? this.config.collectorLeaseTtlMs : this.config.leaseTtlMs;
    for (const candidate of candidates) {
      let lease;
      try {
        lease = await acquireLease(this.config.dataDir, candidate.jobId, stage, { owner, ttlMs, now: () => now });
      } catch (error) {
        if (error.code === 'LEASE_HELD') continue;
        throw error;
      }
      try {
        const { job } = await this.#mutate(candidate.jobId, (draft) => {
          if (!this.#eligible(draft, stage, now)) throw queueError('CLAIM_LOST', 'Another worker changed the job before it could be claimed');
          const entry = draft.stages[stage];
          entry.status = 'leased';
          entry.attempts = (entry.attempts ?? 0) + 1;
          entry.lease = { owner, token: lease.token, generation: lease.generation, expiresAt: lease.expiresAt };
          entry.updatedAt = nowIso(now);
          draft.history.push({ at: nowIso(now), event: 'claimed', stage, owner, generation: lease.generation, attempt: entry.attempts });
        });
        return { job, stage, lease };
      } catch (error) {
        await lease.release().catch(() => {});
        if (error.code === 'CLAIM_LOST') continue;
        throw error;
      }
    }
    return null;
  }

  /** Copy an external artifact into the stage directory under the caller's lease. */
  async putArtifact({ jobId, stage, owner, token, generation, source, name, kind = 'data' }) {
    assertStage(stage);
    await assertLease(this.config.dataDir, jobId, stage, { token, generation, now: this.now });
    const job = await this.getJob(jobId);
    if (!job) throw queueError('JOB_NOT_FOUND', 'No such job');
    const entry = job.stages[stage];
    if (entry.status !== 'leased' || entry.lease?.owner !== owner || entry.lease?.token !== token) throw queueError('LEASE_LOST', 'This worker does not own the stage');
    const relative = assertArtifactRelative(name);
    const directory = this.paths.artifactDir(jobId, stage);
    const destination = safeChild(directory, relative);
    await ensurePrivateDir(path.dirname(destination));
    const temporary = `${destination}.${digest(String(this.now()) + Math.random())}.tmp`;
    try {
      await fs.copyFile(source, temporary);
      await fs.chmod(temporary, 0o600);
      await fs.rename(temporary, destination);
    } finally { await fs.rm(temporary, { force: true }).catch(() => {}); }
    const { sha256, bytes } = await sha256File(destination);
    return { path: relative, kind, sha256, bytes };
  }

  async #verifyArtifacts(job, stage, artifacts) {
    if (!Array.isArray(artifacts) || !artifacts.length) throw queueError('ARTIFACT_REQUIRED', 'Completion requires at least one artifact');
    const directory = this.paths.artifactDir(job.jobId, stage);
    const manifest = [];
    let total = 0;
    for (const item of artifacts) {
      if (!item || typeof item !== 'object') throw queueError('INVALID_ARTIFACT', 'Artifact entries must be objects');
      const relative = assertArtifactRelative(item.path);
      const filename = safeChild(directory, relative);
      const stat = await fs.lstat(filename).catch(() => null);
      if (!stat || !stat.isFile() || stat.isSymbolicLink()) throw queueError('ARTIFACT_MISSING', `Artifact does not exist as a regular file: ${relative}`);
      const actual = await sha256File(filename);
      if (item.sha256 && String(item.sha256).toLowerCase() !== actual.sha256) throw queueError('ARTIFACT_HASH_MISMATCH', `Artifact hash mismatch: ${relative}`);
      if (item.bytes !== undefined && Number(item.bytes) !== actual.bytes) throw queueError('ARTIFACT_SIZE_MISMATCH', `Artifact size mismatch: ${relative}`);
      total += actual.bytes;
      manifest.push({ path: relative, kind: item.kind ?? 'data', sha256: actual.sha256, bytes: actual.bytes });
    }
    const existing = Object.values(job.stages).flatMap((entry) => entry.artifacts ?? []).reduce((sum, item) => sum + (Number(item.bytes) || 0), 0);
    if (existing + total > this.config.backpressure.perPaperBytes) throw queueError('PAPER_QUOTA_EXCEEDED', 'Artifacts for this paper exceed the configured per-paper byte quota');
    return manifest;
  }

  /**
   * PR42: an image-only question is a placeholder in the text stream. Its content may only be
   * accepted at assets_qa when a hashed image manifest covers every referenced image, so two
   * different pictures can never be treated as the same content without byte evidence.
   */
  async #verifyImageManifest(job, manifest, declarations) {
    const references = job.images ?? [];
    if (!references.length) {
      if (declarations.imageContentOnly === true) {
        throw queueError('IMAGE_EVIDENCE_REQUIRED', 'Image-only content needs at least one observed image reference and byte evidence');
      }
      return;
    }
    const artifact = manifest.find((item) => item.kind === 'image_manifest');
    if (!artifact) throw queueError('IMAGE_ASSET_MANIFEST_REQUIRED', 'This paper references images; assets_qa must store an image_manifest with per-image SHA-256');
    const filename = safeChild(this.paths.artifactDir(job.jobId, 'assets_qa'), artifact.path);
    let parsed;
    try { parsed = JSON.parse(await fs.readFile(filename, 'utf8')); }
    catch { throw queueError('IMAGE_ASSET_MANIFEST_INVALID', 'image_manifest is not valid JSON'); }
    const entries = Array.isArray(parsed) ? parsed : parsed?.images;
    if (!Array.isArray(entries) || !entries.length) throw queueError('IMAGE_ASSET_MANIFEST_INVALID', 'image_manifest has no images array');
    const byRef = new Map(entries.map((entry) => [String(entry?.ref ?? ''), entry]));
    for (const image of references) {
      const entry = byRef.get(image.ref);
      if (!entry) throw queueError('IMAGE_HASH_MISSING', `No byte evidence for image ${image.ref}`);
      if (!/^[a-f0-9]{64}$/i.test(String(entry.sha256 ?? ''))) throw queueError('IMAGE_HASH_INVALID', `Image ${image.ref} lacks a SHA-256`);
      if (image.sha256 && String(entry.sha256).toLowerCase() !== image.sha256.toLowerCase()) {
        throw queueError('IMAGE_HASH_MISMATCH', `Image ${image.ref} hash changed since observation`);
      }
      if (entry.bytes !== undefined && (!Number.isInteger(entry.bytes) || entry.bytes < 1)) {
        throw queueError('IMAGE_HASH_INVALID', `Image ${image.ref} has an invalid byte count`);
      }
    }
  }

  async completeStage({ jobId, stage, owner, token, generation, artifacts, declarations = {}, now = this.now() }) {
    assertStage(stage);
    const currentLease = await assertLease(this.config.dataDir, jobId, stage, { token, generation, now: () => now });
    if (currentLease.owner !== owner) throw queueError('LEASE_LOST', 'Lease owner mismatch');
    if (declarations.placeholder === true) {
      throw queueError('PLACEHOLDER_NOT_COMPLETABLE', 'A placeholder/stub observation must be reported as skipped_placeholder, never completed');
    }
    if (declarations.contentUnknown === true) {
      throw queueError('CONTENT_UNKNOWN_NOT_COMPLETABLE', 'Unknown/placeholder content must go to needs_review or be marked skipped_placeholder, never completed');
    }
    if (stage === 'answer_explanation_qa') {
      const acceptable = ['official', 'source_observed', 'human_authored'];
      if (!acceptable.includes(declarations.answerProvenance)) {
        throw queueError('ANSWER_PROVENANCE_UNVERIFIED', 'Answer stage completion requires official/source-observed/human-authored provenance; AI-assisted or unknown must go to needs_review');
      }
    }
    if (stage === 'human_review') {
      if (declarations.approved !== true || typeof declarations.reviewer !== 'string' || !declarations.reviewer.trim()) {
        throw queueError('REVIEW_NOT_APPROVED', 'Human review completion requires an explicit reviewer and approved=true');
      }
    }
    if (stage === 'candidate_ready' && declarations.citationsVerified !== true) {
      throw queueError('CITATIONS_UNVERIFIED', 'Candidate promotion requires citationsVerified=true from a reviewer/verifier');
    }
    const job = await this.getJob(jobId);
    if (!job) throw queueError('JOB_NOT_FOUND', 'No such job');
    const manifest = await this.#verifyArtifacts(job, stage, artifacts);
    if (stage === 'assets_qa') await this.#verifyImageManifest(job, manifest, declarations);
    if (stage === 'candidate_ready' && (job.images?.length ?? 0) > 0 && declarations.imagesVerified !== true) {
      throw queueError('IMAGE_EVIDENCE_REQUIRED', 'A paper with images cannot be promoted without imagesVerified=true');
    }
    const { job: updated } = await this.#mutate(jobId, (draft) => {
      const entry = draft.stages[stage];
      if (entry.status !== 'leased') throw queueError('STAGE_NOT_LEASED', 'Stage is not leased');
      if (entry.lease?.token !== token || entry.lease?.generation !== generation || entry.lease?.owner !== owner) {
        throw queueError('LEASE_LOST', 'Another consumer reclaimed this stage before commit');
      }
      entry.status = SUCCESS;
      entry.artifacts = manifest;
      entry.lease = null;
      entry.reason = null;
      entry.completedAt = nowIso(now);
      entry.updatedAt = nowIso(now);
      entry.declarations = { ...declarations, placeholder: false };
      draft.history.push({ at: nowIso(now), event: 'completed', stage, owner, artifacts: manifest.map((item) => item.path) });
    });
    await releaseLease(this.config.dataDir, jobId, stage, { token, generation }).catch(() => {});
    return updated;
  }

  async failStage({ jobId, stage, owner, token, generation, outcome, reason, now = this.now() }) {
    assertStage(stage);
    if (!REPORTABLE_OUTCOMES.includes(outcome) || outcome === SUCCESS) throw queueError('INVALID_OUTCOME', `Unsupported failure outcome: ${outcome}`);
    if (typeof reason !== 'string' || !reason.trim()) throw queueError('REASON_REQUIRED', 'Every non-completion outcome needs a reason');
    const currentLease = await assertLease(this.config.dataDir, jobId, stage, { token, generation, now: () => now });
    if (currentLease.owner !== owner) throw queueError('LEASE_LOST', 'Lease owner mismatch');
    const { job } = await this.#mutate(jobId, (draft) => {
      const entry = draft.stages[stage];
      if (entry.lease?.token !== token || entry.lease?.generation !== generation) throw queueError('LEASE_LOST', 'Another consumer reclaimed this stage');
      entry.lease = null;
      entry.reason = reason.slice(0, 1000);
      entry.updatedAt = nowIso(now);
      if (outcome === 'partial') {
        if ((entry.attempts ?? 0) >= this.config.maxAttempts) {
          entry.status = 'dead_letter';
          entry.deadLetterAt = nowIso(now);
        } else {
          entry.status = 'pending';
          entry.nextAttemptAt = now + backoffFor(entry.attempts ?? 1, this.config);
        }
      } else {
        entry.status = outcome;
        if (outcome === 'dead_letter') entry.deadLetterAt = nowIso(now);
      }
      draft.history.push({ at: nowIso(now), event: 'failed', stage, outcome, reason: entry.reason });
    });
    await releaseLease(this.config.dataDir, jobId, stage, { token, generation }).catch(() => {});
    if (job.stages[stage].status === 'dead_letter') {
      await atomicWriteJson(path.join(this.paths.deadLetter, `${jobId}.${stage}.json`), {
        copiedAt: nowIso(now), jobId, stage, job,
      });
    }
    return job;
  }

  /** A reviewer alone may put a terminal/needs-review stage back into the queue, with a reason. */
  async reopen({ jobId, stage, actor, reason, now = this.now() }) {
    assertStage(stage);
    if (typeof actor !== 'string' || !actor.trim()) throw queueError('ACTOR_REQUIRED', 'Reopen needs a named reviewer');
    if (typeof reason !== 'string' || !reason.trim()) throw queueError('REASON_REQUIRED', 'Reopen needs a written reason');
    const { job } = await this.#mutate(jobId, (draft) => {
      const entry = draft.stages[stage];
      if (!['needs_review', 'blocked_auth', 'blocked_rights', 'partial', 'dead_letter'].includes(entry.status)) {
        throw queueError('NOT_REOPENABLE', `Stage state ${entry.status} is not reopenable`);
      }
      entry.status = 'pending';
      entry.nextAttemptAt = 0;
      entry.attempts = 0;
      entry.reason = null;
      entry.lease = null;
      entry.updatedAt = nowIso(now);
      draft.history.push({ at: nowIso(now), event: 'reopened', stage, actor, reason: reason.slice(0, 1000) });
    });
    return job;
  }

  async verify({ jobId, actor, receipt, now = this.now() }) {
    if (typeof actor !== 'string' || !actor.trim()) throw queueError('ACTOR_REQUIRED', 'Verification needs a named verifier');
    if (!receipt || typeof receipt.path !== 'string') throw queueError('RECEIPT_REQUIRED', 'Verification needs a receipt artifact');
    const relative = assertArtifactRelative(receipt.path);
    const filename = safeChild(this.paths.artifactDir(jobId, 'candidate_ready'), relative);
    const stat = await fs.lstat(filename).catch(() => null);
    if (!stat || !stat.isFile() || stat.isSymbolicLink()) throw queueError('RECEIPT_MISSING', 'Receipt artifact is missing');
    const hashed = await sha256File(filename);
    if (receipt.sha256 && String(receipt.sha256).toLowerCase() !== hashed.sha256) throw queueError('RECEIPT_HASH_MISMATCH', 'Receipt hash mismatch');
    const { job } = await this.#mutate(jobId, (draft) => {
      if (draft.stages.candidate_ready?.status !== SUCCESS) throw queueError('NOT_CANDIDATE_READY', 'Only a completed candidate_ready job can be verified');
      if (draft.verifiedAt) throw queueError('ALREADY_VERIFIED', 'Job is already verified');
      draft.verifiedAt = nowIso(now);
      draft.verification = { actor, receipt: { ...receipt, path: relative, sha256: hashed.sha256, bytes: hashed.bytes } };
      draft.history.push({ at: nowIso(now), event: 'verified', actor, receipt: relative });
    });
    return job;
  }

  async status({ now = this.now() } = {}) {
    await this.init();
    const { jobs, invalid } = await this.#scan();
    const perStage = Object.fromEntries(STAGES.map((stage) => [stage, { pending: 0, leased: 0, done: 0, terminal: 0 }]));
    const byStatus = {};
    let pendingReview = 0, active = 0, verified = 0, candidateReady = 0, oldestPendingAt = null;
    for (const job of jobs) {
      byStatus[job.status] = (byStatus[job.status] ?? 0) + 1;
      if (job.status === 'verified') verified += 1;
      if (job.status === 'candidate_ready') candidateReady += 1;
      let hasOpen = false;
      for (const stage of STAGES) {
        const entry = job.stages[stage];
        const bucket = perStage[stage];
        if (entry.status === 'pending') { bucket.pending += 1; hasOpen = true; }
        else if (entry.status === 'leased') { bucket.leased += 1; hasOpen = true; }
        else if (entry.status === SUCCESS) bucket.done += 1;
        else bucket.terminal += 1;
        if (entry.status === 'pending' && (!oldestPendingAt || entry.updatedAt < oldestPendingAt)) oldestPendingAt = entry.updatedAt;
      }
      if (hasOpen && !TERMINAL_BAD.includes(job.status) && job.status !== 'verified') active += 1;
      const reviewReady = ['pending', 'leased'].includes(job.stages.human_review?.status)
        && job.stages.answer_explanation_qa?.status === SUCCESS;
      if (reviewReady || job.status === 'needs_review') pendingReview += 1;
    }
    let freeBytes = null;
    try { freeBytes = await diskFreeBytes(this.paths.root); } catch { /* status remains useful without statfs */ }
    return {
      schemaVersion: 1, generatedAt: nowIso(now), dataDir: this.paths.root,
      jobs: { total: jobs.length, active, verified, candidateReady, pendingReview, byStatus },
      perStage, invalidJobs: invalid, queueLength: active, pendingReview,
      diskFreeBytes: freeBytes, oldestPendingAt,
      completed: verified, // only independent verification counts as completed
    };
  }

  /**
   * Recover after crashes. Expired leases are moved aside; every job claim that no longer has a
   * live lease is returned to pending (with backoff) or dead-lettered. No job is ever created.
   */
  async reconcile({ now = this.now() } = {}) {
    await this.init();
    const reclaimed = [];
    const { jobs } = await this.#scan();
    for (const job of jobs) {
      for (const stage of STAGES) {
        const entry = job.stages[stage];
        if (entry.status !== 'leased') continue;
        const lease = await readLease(this.config.dataDir, job.jobId, stage);
        if (lease && Number.isFinite(lease.expiresAt) && lease.expiresAt > now) continue;
        const { job: updated, result } = await this.#mutate(job.jobId, (draft) => {
          const current = draft.stages[stage];
          if (current.status !== 'leased') return { skipped: true };
          current.lease = null;
          current.updatedAt = nowIso(now);
          if ((current.attempts ?? 0) >= this.config.maxAttempts) {
            current.status = 'dead_letter';
            current.deadLetterAt = nowIso(now);
          } else {
            current.status = 'pending';
            current.nextAttemptAt = now + backoffFor(current.attempts ?? 1, this.config);
          }
          draft.history.push({ at: nowIso(now), event: 'lease-reclaimed', stage, attempts: current.attempts ?? 0 });
          return { recovered: true, status: current.status };
        });
        if (result?.recovered) reclaimed.push({ jobId: job.jobId, stage, status: updated.stages[stage].status, attempts: updated.stages[stage].attempts });
      }
    }
    const summary = await this.status({ now });
    return { reconciledAt: nowIso(now), reclaimed, status: summary };
  }
}

export function openQueue(config) { return new PipelineQueue(config); }
