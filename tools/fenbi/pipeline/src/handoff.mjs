import fs from 'node:fs/promises';
import path from 'node:path';
import { atomicWriteJson, ensurePrivateDir, randomToken, safeChild, sha256File } from './fsutil.mjs';
import { assertArtifactRelative, placeholderVerdict } from './identity.mjs';
import { STAGES, SCHEMA_VERSION } from './constants.mjs';

const FORBIDDEN_KEY = /cookie|token|password|secret|session|authorization|credential|profileDir/i;
const CREDENTIAL_VALUE = [
  /(?:^|[?&;])(?:token|auth|sessionid|cookie|signature)=/i,
  /\bbearer\s+[A-Za-z0-9._~+/-]{16,}/i,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
];
const ANSWER_PROVENANCE = ['official', 'source_observed', 'human_authored', 'ai_assisted', 'unknown'];
const PERMISSION_FIELDS = new Set(['browserProfile', 'cookies', 'tokens', 'redistribution', 'localOnly']);

function handoffError(code, message) { return Object.assign(new Error(`[${code}] ${message}`), { code }); }

function inspectStrings(value, route = '$') {
  if (typeof value === 'string') {
    for (const pattern of CREDENTIAL_VALUE) {
      if (pattern.test(value)) throw handoffError('HANDOFF_CREDENTIAL_LEAK', `Credential-like value at ${route}`);
    }
    return;
  }
  if (Array.isArray(value)) { value.forEach((item, index) => inspectStrings(item, `${route}[${index}]`)); return; }
  if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      const permissionDeclaration = route === '$.permissions' && PERMISSION_FIELDS.has(key);
      if (FORBIDDEN_KEY.test(key) && !permissionDeclaration) throw handoffError('HANDOFF_CREDENTIAL_LEAK', `Forbidden handoff field ${route}.${key}`);
      inspectStrings(child, `${route}.${key}`);
    }
  }
}

/** Shared with the observation importer: no handoff may carry a browser session or a secret. */
export function assertNoCredentialMaterial(value) { inspectStrings(value); }

function safeSourceUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw handoffError('HANDOFF_BAD_URL', 'Source URL is invalid'); }
  if (url.protocol !== 'https:' || url.username || url.password) throw handoffError('HANDOFF_BAD_URL', 'Source URL must be HTTPS without credentials');
  for (const key of url.searchParams.keys()) {
    if (/token|auth|session|cookie|signature|key|secret|password/i.test(key)) throw handoffError('HANDOFF_CREDENTIAL_LEAK', 'Source URL contains a credential-like query parameter');
  }
  url.hash = '';
  return url.toString();
}

/**
 * The handoff is an *offline slice*, not a session export: no cookies, no profile path, no
 * browser handle. It carries just enough identity to join the job, hashed artifacts, rights
 * metadata and the review flags a downstream agent must honour.
 */
export function buildHandoff({ job, stage, artifacts, producer = 'collector', reviewReasons = [], now = new Date().toISOString() }) {
  if (!STAGES.includes(stage)) throw handoffError('HANDOFF_BAD_STAGE', `Unknown stage: ${stage}`);
  if (!Array.isArray(artifacts) || !artifacts.length) throw handoffError('HANDOFF_NO_ARTIFACTS', 'A handoff needs at least one artifact');
  const provenance = job.pipelineDeclarations?.answerProvenance ?? null;
  const review = [...reviewReasons];
  if (['answer_explanation_qa', 'human_review', 'candidate_ready'].includes(stage)) {
    if (provenance === null || ['ai_assisted', 'unknown'].includes(provenance)) review.push('answer-provenance-unverified');
  }
  if (job.source?.category === 'licensed_donor' && job.source?.redistribution !== 'allowed') review.push('license-restricts-redistribution');
  return {
    schemaVersion: SCHEMA_VERSION,
    kind: 'gwy-zhenti-offline-handoff',
    jobId: job.jobId,
    taskKey: job.taskKeys?.[stage] ?? null,
    stage,
    paperSourceId: job.paperSourceId,
    version: job.version,
    title: job.title,
    subject: job.subject,
    area: job.area,
    year: job.year,
    variant: job.variant,
    observed: { url: job.url ? safeSourceUrl(job.url) : null, urlObserved: Boolean(job.urlObserved) },
    source: {
      category: job.source.category,
      license: job.source.license ?? null,
      redistribution: job.source.redistribution,
      evidence: (job.source.evidence ?? []).map((item) => ({ type: item.type, ref: item.ref, ...(item.digest ? { digest: item.digest } : {}) })),
    },
    permissions: {
      browserProfile: false, cookies: false, tokens: false,
      redistribution: job.permissions.redistribution, localOnly: job.permissions.localOnly,
    },
    artifacts: artifacts.map((item) => ({
      path: assertArtifactRelative(item.path), kind: item.kind ?? 'data',
      sha256: item.sha256, bytes: item.bytes,
    })),
    images: (job.images ?? []).map((item) => ({
      ref: assertArtifactRelative(item.ref),
      sourceUrl: item.sourceUrl ? safeSourceUrl(item.sourceUrl) : null,
      sha256: item.sha256 ?? null,
    })),
    review: { required: review.length > 0, reasons: [...new Set(review)] },
    answerProvenance: provenance,
    producer: { agent: String(producer).slice(0, 80), at: now },
  };
}

export async function verifyHandoff(value, { root = null, config = null } = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw handoffError('HANDOFF_INVALID', 'Handoff must be an object');
  if (value.schemaVersion !== SCHEMA_VERSION || value.kind !== 'gwy-zhenti-offline-handoff') throw handoffError('HANDOFF_INVALID', 'Unsupported handoff schema');
  inspectStrings(value);
  if (!STAGES.includes(value.stage)) throw handoffError('HANDOFF_BAD_STAGE', 'Handoff stage is not a queue stage');
  if (!value.jobId || !/^[a-f0-9]{24}$/.test(value.jobId)) throw handoffError('HANDOFF_INVALID', 'Handoff jobId is invalid');
  if (!value.permissions || value.permissions.browserProfile !== false || value.permissions.cookies !== false || value.permissions.tokens !== false) {
    throw handoffError('HANDOFF_PROFILE_LEAK', 'A handoff must explicitly carry no browser profile, cookies or tokens');
  }
  if (value.observed?.url) safeSourceUrl(value.observed.url);
  if (!Array.isArray(value.artifacts) || !value.artifacts.length) throw handoffError('HANDOFF_NO_ARTIFACTS', 'Handoff has no artifacts');
  let total = 0;
  const verified = [];
  for (const item of value.artifacts) {
    const relative = assertArtifactRelative(item.path);
    if (!/^[a-f0-9]{64}$/.test(String(item.sha256 ?? ''))) throw handoffError('HANDOFF_BAD_HASH', `Artifact lacks a SHA-256: ${relative}`);
    if (!Number.isInteger(item.bytes) || item.bytes < 1) throw handoffError('HANDOFF_BAD_SIZE', `Artifact lacks a byte count: ${relative}`);
    total += item.bytes;
    if (root) {
      const filename = safeChild(root, relative);
      const stat = await fs.lstat(filename).catch(() => null);
      if (!stat || !stat.isFile() || stat.isSymbolicLink()) throw handoffError('HANDOFF_ARTIFACT_MISSING', `Missing artifact: ${relative}`);
      const actual = await sha256File(filename);
      if (actual.sha256 !== item.sha256 || actual.bytes !== item.bytes) throw handoffError('HANDOFF_HASH_MISMATCH', `Artifact hash/size mismatch: ${relative}`);
      verified.push({ ...item, path: relative, sha256: actual.sha256, bytes: actual.bytes });
    } else {
      verified.push({ ...item, path: relative });
    }
  }
  if (config && total > config.backpressure.perPaperBytes) throw handoffError('HANDOFF_QUOTA_EXCEEDED', 'Handoff exceeds the per-paper byte quota');
  if (value.answerProvenance !== undefined && value.answerProvenance !== null && !ANSWER_PROVENANCE.includes(value.answerProvenance)) throw handoffError('HANDOFF_BAD_PROVENANCE', 'Unknown answer provenance');
  if (['ai_assisted', 'unknown'].includes(value.answerProvenance) && value.review?.required !== true) {
    throw handoffError('HANDOFF_REVIEW_REQUIRED', 'AI-assisted/unknown answers must be flagged for human review');
  }
  for (const image of value.images ?? []) {
    assertArtifactRelative(image.ref);
    if (image.sourceUrl) safeSourceUrl(image.sourceUrl);
  }
  return { ok: true, artifacts: verified, totalBytes: total, review: value.review ?? { required: true, reasons: ['unspecified'] } };
}

export async function writeHandoff(filename, handoff) {
  await verifyHandoff(handoff);
  await atomicWriteJson(filename, handoff);
  return filename;
}

export async function readHandoff(filename, options = {}) {
  const value = JSON.parse(await fs.readFile(filename, 'utf8'));
  const verified = await verifyHandoff(value, options);
  return { handoff: value, verified };
}

/**
 * Copy a verified handoff's artifacts into an isolated destination (usually a claimed stage
 * directory). Names cannot collide: duplicate relative paths are rejected rather than overwritten.
 */
export async function copyHandoffArtifacts(handoff, sourceRoot, destinationRoot, { config = null } = {}) {
  const { artifacts: verified } = await verifyHandoff(handoff, { root: sourceRoot, config });
  await ensurePrivateDir(destinationRoot);
  const seen = new Set();
  const copied = [];
  for (const item of verified) {
    if (seen.has(item.path)) throw handoffError('HANDOFF_DUPLICATE_ARTIFACT', `Duplicate artifact path: ${item.path}`);
    seen.add(item.path);
    const source = safeChild(sourceRoot, item.path);
    const destination = safeChild(destinationRoot, item.path);
    await ensurePrivateDir(path.dirname(destination));
    const temporary = `${destination}.${randomToken()}.tmp`;
    try {
      await fs.copyFile(source, temporary);
      await fs.chmod(temporary, 0o600);
      await fs.rename(temporary, destination);
    } finally { await fs.rm(temporary, { force: true }).catch(() => {}); }
    const hashed = await sha256File(destination);
    if (hashed.sha256 !== item.sha256 || hashed.bytes !== item.bytes) throw handoffError('HANDOFF_HASH_MISMATCH', `Copy changed artifact: ${item.path}`);
    copied.push({ ...item, sha256: hashed.sha256, bytes: hashed.bytes });
  }
  return copied;
}

export { placeholderVerdict };
