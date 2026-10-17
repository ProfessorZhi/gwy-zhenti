import fs from 'node:fs/promises';
import path from 'node:path';
import { atomicWriteJson, digest, ensurePrivateDir, nowIso, readJson } from './fsutil.mjs';
import { queuePaths } from './config.mjs';
import {
  REDISTRIBUTION, SOURCE_CATEGORIES, assertArtifactRelative, sanitizeEvidence,
  sanitizeImageUrl, sanitizeSourceUrl,
} from './identity.mjs';
import { assertNoCredentialMaterial } from './handoff.mjs';

export const OBSERVATION_SCHEMA_VERSION = 1;
export const OBSERVATION_KIND = 'gwy-zhenti-source-observation';
export const CLASSIFICATIONS = Object.freeze([
  'capture_ready', 'observed_catalog', 'needs_route_review', 'needs_initialization_review',
  'blocked_auth', 'invalid',
]);

function observationError(code, message) { return Object.assign(new Error(`[${code}] ${message}`), { code }); }
const OBSERVED_EVIDENCE = new Set(['observed_ui', 'observed_catalog']);
const PERMISSION_EVIDENCE = new Set(['redistribution_permission']);

function text(value, label, { max = 500, pattern } = {}) {
  if (typeof value !== 'string') throw observationError('INVALID_OBSERVATION', `${label} must be a string`);
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > max) throw observationError('INVALID_OBSERVATION', `Invalid ${label}`);
  if (pattern && !pattern.test(trimmed)) throw observationError('INVALID_OBSERVATION', `Invalid ${label}`);
  return trimmed;
}

/** Validate the envelope only; a single bad item is reported instead of aborting the whole import. */
export function validateObservationHandoff(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw observationError('OBSERVATION_INVALID', 'Observation handoff must be an object');
  if (value.schemaVersion !== OBSERVATION_SCHEMA_VERSION || value.kind !== OBSERVATION_KIND) {
    throw observationError('OBSERVATION_INVALID', 'Unsupported observation handoff schema');
  }
  if (!value.producer || typeof value.producer !== 'object' || typeof value.producer.agent !== 'string' || !value.producer.agent.trim()) {
    throw observationError('OBSERVATION_INVALID', 'Observation handoff needs a producer.agent');
  }
  if (!value.permissions || value.permissions.browserProfile !== false || value.permissions.cookies !== false || value.permissions.tokens !== false) {
    throw observationError('OBSERVATION_PROFILE_LEAK', 'Observation handoff must explicitly carry no browser profile, cookies or tokens');
  }
  assertNoCredentialMaterial(value);
  if (!Array.isArray(value.observations) || !value.observations.length || value.observations.length > 10_000) {
    throw observationError('OBSERVATION_INVALID', 'observations must be a non-empty array');
  }
  return value;
}

function normalizeAllowlistEntry(entry) {
  const source = typeof entry === 'string' ? { id: entry } : entry;
  if (!source || typeof source !== 'object' || Array.isArray(source)) throw observationError('ALLOWLIST_INVALID', 'Allowlist entries must be IDs or objects');
  if (source.url !== undefined || source.href !== undefined) throw observationError('ALLOWLIST_URL_FORBIDDEN', 'The allowlist may contain source IDs and titles, never URLs');
  const id = text(String(source.id ?? source.sourceId ?? ''), 'allowlist.id', { max: 120, pattern: /^[A-Za-z0-9_.:-]+$/ });
  const result = { id };
  if (source.title !== undefined) result.title = text(String(source.title), 'allowlist.title', { max: 200 });
  if (source.note !== undefined) result.note = text(String(source.note), 'allowlist.note', { max: 500 });
  return result;
}

/**
 * A local, gitignored authorization file. Missing file means "nothing authorized" rather than an
 * error: a fresh checkout cannot capture anything by accident. URLs are deliberately forbidden
 * here — the URL must come from the browser owner's observation handoff, not from a guess.
 */
export async function loadAllowlist(filename) {
  if (!filename) return { source: null, missing: true, ids: new Set(), entries: new Map(), list: [] };
  let value;
  try { value = JSON.parse(await fs.readFile(filename, 'utf8')); }
  catch (error) {
    if (error.code === 'ENOENT') return { source: filename, missing: true, ids: new Set(), entries: new Map(), list: [] };
    throw error;
  }
  const raw = Array.isArray(value) ? value : value?.sourceIds;
  if (!Array.isArray(raw)) throw observationError('ALLOWLIST_INVALID', 'Allowlist must be an array or {schemaVersion:1, sourceIds:[...]}');
  const entries = new Map();
  for (const item of raw) {
    const entry = normalizeAllowlistEntry(item);
    const previous = entries.get(entry.id);
    if (previous && previous.title && entry.title && previous.title !== entry.title) {
      throw observationError('ALLOWLIST_CONFLICT', `Allowlist has conflicting titles for ${entry.id}`);
    }
    entries.set(entry.id, { ...previous, ...entry });
  }
  return { source: filename, missing: false, ids: new Set(entries.keys()), entries, list: [...entries.values()] };
}

function isReproducibleObservedUrl(sanitized) {
  const url = new URL(sanitized);
  if (['toPage', 'page', 'pageSize'].some((key) => url.searchParams.has(key))) return false;
  if (/^\/spa\/tiku\/?$/u.test(url.pathname)) return false;
  return url.pathname.replace(/\/+$/u, '').length >= 6;
}

function normalizeObservationImages(images, config) {
  if (images === undefined || images === null) return [];
  if (!Array.isArray(images)) throw observationError('INVALID_OBSERVATION', 'images must be an array');
  if (images.length > 1000) throw observationError('INVALID_OBSERVATION', 'Too many image references');
  const seen = new Set();
  return images.map((image, index) => {
    if (!image || typeof image !== 'object' || Array.isArray(image)) throw observationError('INVALID_OBSERVATION', `images[${index}] must be an object`);
    const ref = assertArtifactRelative(String(image.ref ?? ''));
    if (seen.has(ref)) throw observationError('INVALID_OBSERVATION', `Duplicate image reference: ${ref}`);
    seen.add(ref);
    const result = { ref };
    if (image.sourceUrl !== undefined && image.sourceUrl !== null && image.sourceUrl !== '') {
      result.sourceUrl = sanitizeImageUrl(String(image.sourceUrl), { allowedHosts: config.allowedImageHosts });
    }
    if (image.sha256 !== undefined) {
      if (!/^[a-f0-9]{64}$/i.test(String(image.sha256))) throw observationError('INVALID_OBSERVATION', 'image.sha256 must be a SHA-256');
      result.sha256 = String(image.sha256).toLowerCase();
    }
    return result;
  });
}

function evidenceList(...groups) {
  try { return sanitizeEvidence(groups.flat().filter(Boolean)); }
  catch (error) { throw observationError('INVALID_OBSERVATION', error.message); }
}

/**
 * Classify one observation without touching the queue. Only an allowlisted, explicitly observed,
 * reproducible existing practice with known rights can become `capture_ready`; everything else is
 * a catalog/review record and never creates a capture lease.
 */
export function classifyObservation(observation, { allowlist, config, producer = 'browser-owner' } = {}) {
  const warnings = [];
  if (!observation || typeof observation !== 'object' || Array.isArray(observation)) {
    return { classification: 'invalid', reason: 'observation-not-an-object', warnings };
  }
  let sourceId, title;
  try {
    sourceId = text(String(observation.paperSourceId ?? observation.sourceId ?? ''), 'paperSourceId', { max: 120, pattern: /^[A-Za-z0-9_.:-]+$/ });
    title = text(observation.title, 'title', { max: 200 });
  } catch (error) {
    return { classification: 'invalid', reason: error.message, warnings };
  }
  const base = { sourceId, title, warnings };
  if (!['xingce', 'shenlun'].includes(observation.subject) ||
      typeof observation.area !== 'string' || !observation.area.trim() ||
      !Number.isInteger(Number(observation.year))) {
    return { ...base, classification: 'needs_route_review', reason: 'identity-incomplete' };
  }
  let entry;
  if (!allowlist?.ids?.has(sourceId)) {
    return { ...base, classification: 'needs_initialization_review', reason: 'source-not-in-local-allowlist' };
  }
  entry = allowlist.entries.get(sourceId);
  if (entry?.title && entry.title !== title) warnings.push('title-differs-from-allowlist');

  const route = observation.route;
  if (!route || typeof route !== 'object' || Array.isArray(route)) {
    return { ...base, classification: 'needs_route_review', reason: 'route-missing' };
  }
  const contentStatus = route.contentStatus ?? observation.contentStatus ?? 'unknown';
  if (route.kind === 'blocked_auth') return { ...base, classification: 'blocked_auth', reason: 'owner-observed-auth-challenge' };
  if (route.kind === 'not_initialized') return { ...base, classification: 'needs_initialization_review', reason: 'exercise-not-initialized' };
  if (route.kind === 'not_found') return { ...base, classification: 'observed_catalog', reason: 'route-not-found' };
  if (route.kind === 'multiple') return { ...base, classification: 'needs_route_review', reason: 'ambiguous-route' };
  if (route.kind !== 'existing_practice') return { ...base, classification: 'needs_route_review', reason: 'unknown-route-kind' };
  if (contentStatus === 'placeholder') return { ...base, classification: 'observed_catalog', reason: 'placeholder-content-not-captured', contentStatus };
  if (contentStatus === 'unknown') return { ...base, classification: 'observed_catalog', reason: 'unknown-content-not-captured', contentStatus };
  if (contentStatus !== 'observed') return { ...base, classification: 'needs_route_review', reason: 'content-status-unrecognized', contentStatus };

  if (route.urlObserved !== true) return { ...base, classification: 'needs_route_review', reason: 'url-not-observed' };
  if (typeof route.url !== 'string' || !route.url.trim()) return { ...base, classification: 'needs_route_review', reason: 'url-missing' };
  let url;
  try { url = sanitizeSourceUrl(route.url, { allowedHosts: config.allowedCaptureHosts }); }
  catch (error) { return { ...base, classification: 'needs_route_review', reason: `url-unsafe: ${error.message}` }; }
  if (!isReproducibleObservedUrl(url)) return { ...base, classification: 'needs_route_review', reason: 'url-not-reproducible' };

  const rights = observation.rights;
  if (!rights || typeof rights !== 'object' || Array.isArray(rights)) {
    return { ...base, classification: 'needs_route_review', reason: 'rights-missing' };
  }
  if (!SOURCE_CATEGORIES.includes(rights.category)) return { ...base, classification: 'needs_route_review', reason: 'rights-category-unknown' };
  const requestedRedistribution = rights.redistribution ?? 'local_only';
  if (!REDISTRIBUTION.includes(requestedRedistribution)) return { ...base, classification: 'needs_route_review', reason: 'redistribution-unknown' };
  if (rights.category === 'licensed_donor' && !rights.license) return { ...base, classification: 'needs_route_review', reason: 'license-missing' };
  if (rights.category === 'licensed_donor') {
    return { ...base, classification: 'needs_route_review', reason: 'licensed-donor-requires-offline-handoff-import' };
  }

  let evidence;
  try { evidence = evidenceList(route.evidence, rights.evidence); }
  catch (error) { return { ...base, classification: 'needs_route_review', reason: error.message }; }
  if (!evidence.some((item) => OBSERVED_EVIDENCE.has(item.type))) {
    return { ...base, classification: 'needs_route_review', reason: 'observation-evidence-missing' };
  }
  let effectiveRedistribution = requestedRedistribution;
  if (requestedRedistribution === 'allowed' && !evidence.some((item) => PERMISSION_EVIDENCE.has(item.type))) {
    // No written redistribution permission: the queue stays local-only rather than inferring one.
    effectiveRedistribution = 'local_only';
    warnings.push('redistribution-downgraded-to-local-only');
  }

  let images;
  try { images = normalizeObservationImages(observation.images ?? route.images, config); }
  catch (error) { return { ...base, classification: 'needs_route_review', reason: `image-ref-invalid: ${error.message}` }; }
  if (route.imageContentOnly === true && !images.length) {
    return { ...base, classification: 'needs_route_review', reason: 'image-content-unobserved' };
  }

  let version;
  if (observation.version !== undefined) {
    try { version = text(String(observation.version), 'version', { max: 64, pattern: /^[A-Za-z0-9_.:-]+$/ }); }
    catch (error) { return { ...base, classification: 'needs_route_review', reason: error.message }; }
  } else {
    version = `obs-v1-${digest(`${sourceId}\u0000${url}`).slice(0, 16)}`;
  }
  const questionCount = observation.questionCount ?? route.questionCount;
  const expectedQuestions = Number.isInteger(Number(questionCount)) && Number(questionCount) > 0 ? Number(questionCount) : null;

  return {
    ...base,
    classification: 'capture_ready',
    reason: 'existing-practice-observed-and-authorized',
    version,
    urlDigest: digest(url).slice(0, 16),
    contentStatus,
    requestedRedistribution,
    effectiveRedistribution,
    input: {
      paperSourceId: sourceId,
      version,
      title,
      subject: observation.subject,
      area: observation.area,
      year: Number(observation.year),
      variant: observation.variant ?? null,
      url,
      urlObserved: true,
      sourceCategory: rights.category,
      license: rights.license ?? null,
      redistribution: effectiveRedistribution,
      evidence,
      images,
      expectedQuestions,
      actor: `observation:${String(producer).slice(0, 60)}`,
    },
  };
}

/**
 * Import an Owner-produced observation handoff. This function never opens a browser, never calls
 * an initialization endpoint and never creates a URL: the only URL it can enqueue is the one in
 * the handoff, after sanitization. Non-capture classifications are persisted as observations.
 */
export async function importObservations({
  queue, config, handoff: raw, allowlist, dryRun = false, now = Date.now,
} = {}) {
  const handoff = validateObservationHandoff(raw);
  const authorization = allowlist ?? { source: null, missing: true, ids: new Set(), entries: new Map(), list: [] };
  if (!authorization.ids || !authorization.entries) throw observationError('ALLOWLIST_INVALID', 'A normalized allowlist is required');
  const producer = handoff.producer.agent;
  const items = [];
  const counts = {
    observations: handoff.observations.length,
    capture_ready: 0, created: 0, deduplicated: 0,
    observed_catalog: 0, needs_route_review: 0, needs_initialization_review: 0,
    blocked_auth: 0, invalid: 0,
  };
  for (let index = 0; index < handoff.observations.length; index += 1) {
    let item;
    try {
      item = classifyObservation(handoff.observations[index], { allowlist: authorization, config, producer });
    } catch (error) {
      item = { classification: 'invalid', reason: error.message, warnings: [] };
    }
    const record = {
      index,
      sourceId: item.sourceId ?? null,
      title: item.title ?? null,
      classification: item.classification,
      reason: item.reason,
      warnings: item.warnings ?? [],
      version: item.version ?? null,
      urlDigest: item.urlDigest ?? null,
      contentStatus: item.contentStatus ?? null,
      requestedRedistribution: item.requestedRedistribution ?? null,
      effectiveRedistribution: item.effectiveRedistribution ?? null,
    };
    if (item.classification === 'capture_ready') {
      counts.capture_ready += 1;
      if (dryRun) {
        record.enqueued = false;
      } else {
        try {
          const result = await queue.enqueue(item.input, { authorizedSourceIds: [...authorization.ids] });
          record.jobId = result.jobId;
          record.enqueued = true;
          record.created = result.created;
          record.duplicate = result.duplicate;
          if (result.created) counts.created += 1; else counts.deduplicated += 1;
        } catch (error) {
          record.classification = error.code === 'CAPTURE_SOURCE_UNAUTHORIZED' ? 'needs_initialization_review' : 'invalid';
          record.reason = error.message;
          record.enqueued = false;
          counts.capture_ready -= 1;
        }
      }
    }
    if (record.classification in counts && record.classification !== 'capture_ready') counts[record.classification] += 1;
    items.push(record);
  }

  const report = {
    schemaVersion: 1,
    kind: 'gwy-zhenti-observation-import-report',
    importedAt: nowIso(now()),
    dryRun: Boolean(dryRun),
    handoffDigest: digest(JSON.stringify(handoff)),
    producer: { agent: producer },
    allowlist: { source: authorization.source, missing: Boolean(authorization.missing), count: authorization.ids.size },
    counts,
    items,
  };
  if (!dryRun) {
    const paths = queuePaths(config.dataDir);
    await ensurePrivateDir(paths.state);
    const importsDir = path.join(paths.state, 'observation-imports');
    await ensurePrivateDir(importsDir);
    await atomicWriteJson(path.join(importsDir, `${report.handoffDigest}.json`), report);
    const catalogFile = path.join(paths.state, 'observed-catalog.json');
    const catalog = await readJson(catalogFile, { schemaVersion: 1, entries: {} });
    if (!catalog.entries || typeof catalog.entries !== 'object' || Array.isArray(catalog.entries)) catalog.entries = {};
    for (const item of items) {
      if (!item.sourceId) continue;
      const key = `${item.sourceId}@${item.version ?? item.urlDigest ?? 'unknown'}`;
      catalog.entries[key] = {
        sourceId: item.sourceId,
        title: item.title,
        version: item.version,
        urlDigest: item.urlDigest,
        classification: item.classification,
        reason: item.reason,
        contentStatus: item.contentStatus,
        effectiveRedistribution: item.effectiveRedistribution,
        jobId: item.jobId ?? null,
        importedAt: report.importedAt,
        producer: report.producer.agent,
      };
    }
    catalog.updatedAt = report.importedAt;
    await atomicWriteJson(catalogFile, catalog);
    report.catalogFile = catalogFile;
    report.reportFile = path.join(importsDir, `${report.handoffDigest}.json`);
  }
  return report;
}
