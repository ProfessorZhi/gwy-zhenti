import fs from 'node:fs/promises';
import path from 'node:path';
import { atomicWriteJson, ensurePrivateDir, nowIso, safeChild, sha256File } from './fsutil.mjs';
import { assertArtifactRelative, jobIdFor, sanitizeEvidence } from './identity.mjs';
import { assertNoCredentialMaterial } from './handoff.mjs';

export const QA_HANDOFF_KIND = 'gwy-zhenti-staged-qa-handoff';
export const QA_HANDOFF_SCHEMA_VERSION = 1;
export const QA_ARTIFACT_KINDS = Object.freeze(['summary', 'metadata', 'asset_manifest', 'question_index', 'alignment']);
const SUMMARY_KEYS = new Set(['questionCount', 'questionNumbers', 'materialCount', 'placeholderNumbers', 'unknownNumbers', 'imageCount']);
const FORBIDDEN_ARTIFACT_KEYS = /^(?:contentHtml|stemHtml|answerHtml|analysisHtml|optionsHtml|rawHtml|fullText|rawText|bodyText|html)$/i;
const IMAGE_MAGIC = [
  Buffer.from([0x89, 0x50, 0x4e, 0x47]), // PNG
  Buffer.from([0xff, 0xd8, 0xff]),       // JPEG
  Buffer.from('GIF8', 'ascii'),          // GIF
  Buffer.from('RIFF', 'ascii'),          // WebP container
  Buffer.from('%PDF', 'ascii'),
  Buffer.from('PK\u0003\u0004', 'utf8'), // ZIP/docx
];
const MAX_ARTIFACT_BYTES = 2 * 1024 * 1024;

function qaError(code, message) { return Object.assign(new Error(`[${code}] ${message}`), { code }); }
function isObject(value) { return Boolean(value) && typeof value === 'object' && !Array.isArray(value); }
function intArray(value, label, max = 10_000) {
  if (!Array.isArray(value) || value.length > max) throw qaError('QA_HANDOFF_SCHEMA', `${label} must be an integer array`);
  const result = value.map((item) => Number(item));
  if (result.some((item) => !Number.isInteger(item) || item < 0)) throw qaError('QA_HANDOFF_SCHEMA', `${label} must contain non-negative integers`);
  if (new Set(result).size !== result.length) throw qaError('QA_HANDOFF_SCHEMA', `${label} contains duplicates`);
  return result;
}

async function assertPrivatePath(filename, { directory = false, checkParent = true } = {}) {
  let stat;
  try { stat = await fs.lstat(filename); }
  catch (error) { throw qaError('QA_HANDOFF_INSECURE_PERMISSIONS', `Cannot stat ${path.basename(filename)}: ${error.message}`); }
  if (stat.isSymbolicLink()) throw qaError('QA_HANDOFF_INSECURE_PERMISSIONS', 'Symlinks are not accepted');
  if (directory ? !stat.isDirectory() : !stat.isFile()) throw qaError('QA_HANDOFF_INSECURE_PERMISSIONS', `${path.basename(filename)} has the wrong type`);
  if ((stat.mode & 0o077) !== 0) throw qaError('QA_HANDOFF_INSECURE_PERMISSIONS', `${path.basename(filename)} must not be group/other accessible`);
  if (typeof process.getuid === 'function' && stat.uid !== process.getuid()) throw qaError('QA_HANDOFF_INSECURE_PERMISSIONS', `${path.basename(filename)} is owned by another UID`);
  if (!checkParent) return stat;
  const parent = await fs.lstat(path.dirname(filename));
  if (parent.isSymbolicLink() || (parent.mode & 0o077) !== 0) throw qaError('QA_HANDOFF_INSECURE_PERMISSIONS', 'Parent directory is not private 0700');
  if (typeof process.getuid === 'function' && parent.uid !== process.getuid()) throw qaError('QA_HANDOFF_INSECURE_PERMISSIONS', 'Parent directory is owned by another UID');
  return stat;
}

function validateSummary(summary) {
  if (!isObject(summary)) throw qaError('QA_HANDOFF_SCHEMA', 'summary must be an object');
  for (const key of Object.keys(summary)) if (!SUMMARY_KEYS.has(key)) throw qaError('QA_HANDOFF_RAW_CONTENT', `summary contains unsupported key: ${key}`);
  const questionCount = Number(summary.questionCount);
  if (!Number.isInteger(questionCount) || questionCount < 1) throw qaError('QA_HANDOFF_SCHEMA', 'summary.questionCount must be a positive integer');
  const questionNumbers = intArray(summary.questionNumbers, 'summary.questionNumbers');
  if (questionNumbers.length !== questionCount) throw qaError('QA_HANDOFF_SCHEMA', 'summary.questionNumbers must cover questionCount exactly');
  const materialCount = Number(summary.materialCount ?? 0);
  if (!Number.isInteger(materialCount) || materialCount < 0) throw qaError('QA_HANDOFF_SCHEMA', 'summary.materialCount must be a non-negative integer');
  const placeholderNumbers = intArray(summary.placeholderNumbers ?? [], 'summary.placeholderNumbers');
  const unknownNumbers = intArray(summary.unknownNumbers ?? [], 'summary.unknownNumbers');
  const known = new Set(questionNumbers);
  for (const number of [...placeholderNumbers, ...unknownNumbers]) if (!known.has(number)) throw qaError('QA_HANDOFF_SCHEMA', `summary references unknown question ${number}`);
  const imageCount = Number(summary.imageCount ?? 0);
  if (!Number.isInteger(imageCount) || imageCount < 0) throw qaError('QA_HANDOFF_SCHEMA', 'summary.imageCount must be a non-negative integer');
  return { questionCount, questionNumbers, materialCount, placeholderNumbers, unknownNumbers, imageCount };
}

function scanStructuredJson(value, route = '$') {
  if (typeof value === 'string') {
    if (value.length > 4000 || /<html|<p\b|```|<img\b/i.test(value)) throw qaError('QA_HANDOFF_RAW_CONTENT', `raw text-like value at ${route}`);
    return;
  }
  if (Array.isArray(value)) { value.forEach((item, index) => scanStructuredJson(item, `${route}[${index}]`)); return; }
  if (isObject(value)) {
    for (const [key, child] of Object.entries(value)) {
      if (FORBIDDEN_ARTIFACT_KEYS.test(key)) throw qaError('QA_HANDOFF_RAW_CONTENT', `raw content key at ${route}.${key}`);
      scanStructuredJson(child, `${route}.${key}`);
    }
  }
}

function assertNoUrlFields(value, route = '$') {
  if (Array.isArray(value)) { value.forEach((item, index) => assertNoUrlFields(item, `${route}[${index}]`)); return; }
  if (!isObject(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (/^(?:url|href|route|practiceUrl|sourceUrl)$/i.test(key) && child !== null && child !== undefined) {
      throw qaError('QA_HANDOFF_URL_NOT_ALLOWED', `A staged QA handoff must not contain ${route}.${key}`);
    }
    assertNoUrlFields(child, `${route}.${key}`);
  }
}

async function verifyArtifactFile(root, entry) {
  if (!isObject(entry)) throw qaError('QA_HANDOFF_SCHEMA', 'artifact entries must be objects');
  const relative = assertArtifactRelative(String(entry.path ?? ''));
  if (!QA_ARTIFACT_KINDS.includes(entry.kind)) throw qaError('QA_HANDOFF_RAW_CONTENT', `artifact kind not allowed: ${entry.kind}`);
  if (!/^[a-f0-9]{64}$/i.test(String(entry.sha256 ?? ''))) throw qaError('QA_HANDOFF_SCHEMA', `artifact ${relative} lacks a SHA-256`);
  if (!Number.isInteger(entry.bytes) || entry.bytes < 1 || entry.bytes > MAX_ARTIFACT_BYTES) throw qaError('QA_HANDOFF_SCHEMA', `artifact ${relative} has an invalid byte count`);
  const filename = safeChild(root, relative);
  const stat = await assertPrivatePath(filename);
  if (stat.size !== entry.bytes) throw qaError('QA_HANDOFF_HASH_MISMATCH', `artifact ${relative} size mismatch`);
  const bytes = await fs.readFile(filename);
  for (const magic of IMAGE_MAGIC) if (bytes.subarray(0, magic.length).equals(magic)) throw qaError('QA_HANDOFF_RAW_CONTENT', `artifact ${relative} looks like a binary/image file`);
  const actual = await sha256File(filename);
  if (actual.sha256 !== String(entry.sha256).toLowerCase()) throw qaError('QA_HANDOFF_HASH_MISMATCH', `artifact ${relative} hash mismatch`);
  let parsed;
  try { parsed = JSON.parse(bytes.toString('utf8')); }
  catch { throw qaError('QA_HANDOFF_SCHEMA', `artifact ${relative} must be structured JSON, not raw text`); }
  scanStructuredJson(parsed, relative);
  return { path: relative, kind: entry.kind, sha256: actual.sha256, bytes: actual.bytes };
}

export async function readQaHandoff(filename, { artifactRoot } = {}) {
  await assertPrivatePath(filename);
  let value;
  try { value = JSON.parse(await fs.readFile(filename, 'utf8')); }
  catch (error) { throw qaError('QA_HANDOFF_SCHEMA', `Cannot parse QA handoff: ${error.message}`); }
  if (!isObject(value) || value.schemaVersion !== QA_HANDOFF_SCHEMA_VERSION || value.kind !== QA_HANDOFF_KIND) {
    throw qaError('QA_HANDOFF_SCHEMA', 'Unsupported QA handoff schema');
  }
  assertNoCredentialMaterial(value);
  assertNoUrlFields(value);
  const permissions = value.permissions;
  if (!isObject(permissions) || permissions.browserProfile !== false || permissions.cookies !== false ||
      permissions.tokens !== false || permissions.rawSiteTextIncluded !== false || permissions.imageBytesIncluded !== false) {
    throw qaError('QA_HANDOFF_RAW_CONTENT', 'QA handoff must declare no profile, cookies, tokens, raw site text or image bytes');
  }
  if (!isObject(value.producer) || typeof value.producer.agent !== 'string' || !value.producer.agent.trim()) throw qaError('QA_HANDOFF_SCHEMA', 'producer.agent is required');
  if (value.route !== undefined || value.url !== undefined) throw qaError('QA_HANDOFF_URL_NOT_ALLOWED', 'A staged QA handoff must not contain a capture URL');
  const identity = value.identity;
  if (!isObject(identity)) throw qaError('QA_HANDOFF_SCHEMA', 'identity is required');
  for (const key of ['paperSourceId', 'version', 'title', 'subject', 'area']) {
    if (typeof identity[key] !== 'string' || !identity[key].trim()) throw qaError('QA_HANDOFF_SCHEMA', `identity.${key} is required`);
  }
  if (!Number.isInteger(Number(identity.year))) throw qaError('QA_HANDOFF_SCHEMA', 'identity.year is required');
  const summary = validateSummary(value.summary);
  const source = value.source;
  if (!isObject(source)) throw qaError('QA_HANDOFF_SCHEMA', 'source is required');
  if (source.redistribution !== 'local_only') throw qaError('QA_HANDOFF_REDISTRIBUTION', 'Only local_only QA handoffs are accepted');
  let evidence;
  try { evidence = sanitizeEvidence(source.evidence); }
  catch (error) { throw qaError('QA_HANDOFF_SCHEMA', error.message); }
  if (!evidence.some((item) => ['observed_ui', 'observed_catalog'].includes(item.type))) {
    throw qaError('QA_HANDOFF_OBSERVATION_EVIDENCE', 'QA handoff needs observed_ui/observed_catalog evidence');
  }
  const root = artifactRoot ? path.resolve(artifactRoot) : path.dirname(path.resolve(filename));
  await assertPrivatePath(root, { directory: true, checkParent: false });
  if (!Array.isArray(value.artifacts) || !value.artifacts.length || value.artifacts.length > 50) throw qaError('QA_HANDOFF_SCHEMA', 'artifacts must be a non-empty array (max 50)');
  const artifacts = [];
  for (const entry of value.artifacts) artifacts.push(await verifyArtifactFile(root, entry));
  if (!artifacts.some((item) => item.kind === 'summary' || item.kind === 'metadata')) throw qaError('QA_HANDOFF_SCHEMA', 'At least one summary/metadata artifact is required');
  if (!Array.isArray(value.assets) || value.assets.length > 1000) throw qaError('QA_HANDOFF_SCHEMA', 'assets must be an array');
  const assets = value.assets.map((asset) => {
    if (!isObject(asset)) throw qaError('QA_HANDOFF_SCHEMA', 'asset entries must be objects');
    const ref = assertArtifactRelative(String(asset.ref ?? ''));
    if (!/^[a-f0-9]{64}$/i.test(String(asset.sha256 ?? ''))) throw qaError('QA_HANDOFF_SCHEMA', `asset ${ref} lacks a SHA-256`);
    if (asset.bytes !== undefined && (!Number.isInteger(asset.bytes) || asset.bytes < 1)) throw qaError('QA_HANDOFF_SCHEMA', `asset ${ref} has invalid bytes`);
    return { ref, sha256: String(asset.sha256).toLowerCase(), ...(asset.bytes ? { bytes: asset.bytes } : {}) };
  });
  if (new Set(assets.map((item) => item.ref)).size !== assets.length) throw qaError('QA_HANDOFF_SCHEMA', 'Duplicate asset refs');
  if (summary.imageCount > 0 && assets.length !== summary.imageCount) throw qaError('QA_HANDOFF_SCHEMA', 'summary.imageCount must equal assets.length');
  const assetArtifact = artifacts.find((item) => item.kind === 'asset_manifest');
  if (summary.imageCount > 0 && !assetArtifact) throw qaError('QA_HANDOFF_SCHEMA', 'Image assets require an asset_manifest artifact');
  if (assetArtifact) {
    let parsed;
    try { parsed = JSON.parse(await fs.readFile(safeChild(root, assetArtifact.path), 'utf8')); }
    catch { throw qaError('QA_HANDOFF_SCHEMA', 'asset_manifest is not valid JSON'); }
    const entries = Array.isArray(parsed) ? parsed : parsed?.images;
    if (!Array.isArray(entries)) throw qaError('QA_HANDOFF_SCHEMA', 'asset_manifest has no images array');
    const manifestByRef = new Map(entries.map((entry) => [String(entry?.ref ?? ''), String(entry?.sha256 ?? '').toLowerCase()]));
    if (manifestByRef.size !== assets.length) throw qaError('QA_HANDOFF_HASH_MISMATCH', 'asset_manifest and assets disagree');
    for (const asset of assets) {
      if (manifestByRef.get(asset.ref) !== asset.sha256) throw qaError('QA_HANDOFF_HASH_MISMATCH', `asset_manifest hash mismatch for ${asset.ref}`);
    }
  }
  return {
    schemaVersion: QA_HANDOFF_SCHEMA_VERSION, kind: QA_HANDOFF_KIND,
    producer: { agent: value.producer.agent, at: value.producer.at ?? null },
    permissions, identity, source: { category: source.category, license: source.license ?? null, redistribution: 'local_only', evidence },
    summary, assets, artifacts, artifactRoot: root,
  };
}

/** Import a private, metadata-only staged QA handoff without touching a profile or the site. */
export async function importQaHandoff({ queue, config, filename, artifactRoot, allowlist, actor = 'qa-handoff' } = {}) {
  const handoff = await readQaHandoff(filename, { artifactRoot });
  const identity = handoff.identity;
  if (!allowlist?.ids?.has(identity.paperSourceId)) {
    throw qaError('QA_HANDOFF_NOT_AUTHORIZED', 'paperSourceId is not in the local authorization allowlist');
  }
  if (!['observed_ui', 'official', 'licensed_donor'].includes(handoff.source.category)) throw qaError('QA_HANDOFF_SCHEMA', 'Unsupported source category');
  if (handoff.source.category === 'licensed_donor' && !handoff.source.license) throw qaError('QA_HANDOFF_SCHEMA', 'licensed_donor needs a license');
  const input = {
    paperSourceId: identity.paperSourceId,
    version: identity.version,
    title: identity.title,
    subject: identity.subject,
    area: identity.area,
    year: Number(identity.year),
    variant: identity.variant ?? null,
    sourceCategory: handoff.source.category,
    license: handoff.source.license,
    redistribution: 'local_only',
    evidence: handoff.source.evidence,
    images: handoff.assets.map((asset) => ({ ref: asset.ref, sha256: asset.sha256 })),
    expectedQuestions: handoff.summary.questionCount,
    expectedMaterials: handoff.summary.materialCount,
    offline: true,
    actor: `${actor}:${handoff.producer.agent}`,
  };
  const jobId = jobIdFor(input);
  const existing = await queue.getJob(jobId);
  if (existing) return { created: false, duplicate: true, jobId, status: existing.status, summary: existing.qaSummary ?? null };
  const destinationRoot = queue.paths.artifactDir(jobId, 'capture_ready');
  await ensurePrivateDir(destinationRoot);
  const copied = [];
  for (const artifact of handoff.artifacts) {
    const source = safeChild(handoff.artifactRoot, artifact.path);
    await assertPrivatePath(source);
    const destination = safeChild(destinationRoot, artifact.path);
    await ensurePrivateDir(path.dirname(destination));
    const temporary = `${destination}.${Date.now()}.tmp`;
    try {
      await fs.copyFile(source, temporary);
      await fs.chmod(temporary, 0o600);
      await fs.rename(temporary, destination);
    } finally { await fs.rm(temporary, { force: true }).catch(() => {}); }
    const hashed = await sha256File(destination);
    if (hashed.sha256 !== artifact.sha256 || hashed.bytes !== artifact.bytes) throw qaError('QA_HANDOFF_HASH_MISMATCH', `copied artifact changed: ${artifact.path}`);
    copied.push({ path: artifact.path, kind: artifact.kind, sha256: hashed.sha256, bytes: hashed.bytes });
  }
  const result = await queue.enqueueOffline(input, copied, { summary: handoff.summary });
  return {
    created: result.created, duplicate: result.duplicate, jobId: result.jobId,
    status: result.job.status, captureMode: result.job.stages.capture_ready.mode,
    summary: handoff.summary, artifacts: copied, assets: handoff.assets,
  };
}
