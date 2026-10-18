import path from 'node:path';
import { digest } from './fsutil.mjs';
import { STAGES, SCHEMA_VERSION } from './constants.mjs';
import { CREDENTIAL_QUERY_NAME, ROUTE_PARAM_VALUE } from './config.mjs';

export const SOURCE_CATEGORIES = Object.freeze(['observed_ui', 'official', 'licensed_donor']);
export const REDISTRIBUTION = Object.freeze(['local_only', 'allowed']);

/**
 * Positive observation evidence accepted by both the observation importer and the enqueue
 * gate. The Owner's 2026-10-18 re-observation uses a dated marker; only that shape is accepted.
 * Metadata-only markers such as `needs_owner_reobservation` are deliberately excluded.
 */
export function isPositiveObservationEvidence(type) {
  return ['observed_ui', 'observed_catalog', 'offline_fetchability', 'url_stable_across_reads', 'owner_fast10_shard'].includes(type)
    || /^route_reobserved_\d{8}$/.test(String(type));
}

const SAFE_QUERY = new Set(['labelId', 'paperId', 'id', 'toPage', 'pageSize', 'type', 'categoryId']);
const SENSITIVE_QUERY = CREDENTIAL_QUERY_NAME;
// Tracking/attribution parameters do not select a route; dropping them cannot change the page.
const IGNORABLE_QUERY = /^(?:utm_|spm$|ref$|from$|source$|share|fbclid$|gclid$)/i;
// The importer only ever stores a landing URL. It must not accept a write/initialise endpoint
// merely because the owner called it "observed".
const WRITE_ROUTE = /\/(?:submit|initialize|init|create|start|finish|save)(?:\/|$)/i;
const PLACEHOLDER = /^(?:暂无(?:解析|答案)?|待(?:补充|完善|填写)|查看(?:答案|解析)|答案略|解析略|略|TODO|PLACEHOLDER|参考答案|参考解析|点击查看)$/iu;
// PR36/PR45: a not-yet-collected question still renders an ID, a number and four options, with
// this boilerplate where the stem belongs. The live page adds a courteous tail whose wording
// varies; the bounded generic tail (no sentence-ending punctuation, <=24 chars) covers it without
// swallowing a genuine stem that merely quotes the marker and keeps talking.
const COLLECTION_STUB = new RegExp('^(?:题目正在全力以赴征集|正在搜集中|本题暂无收集到|暂无收集到|网友未回忆起|题目缺失'
  + '|非客观题，请交卷后查看参考解析估分)'
  + '(?:[，,。.；;]?\\s*(?:请稍后再试|请稍后|敬请期待|感谢您的关注|谢谢|稍后重试'
  + '|将会(?:在征集到后)?第一时间上传|[^。！？!?]{0,24}))?$', 'u');
const STUB_BODY_MAX_CHARS = 120;

function fail(message, code = 'INVALID_INPUT') {
  return Object.assign(new Error(`[${code}] ${message}`), { code });
}

function text(value, label, { max = 500, pattern } = {}) {
  if (typeof value !== 'string') throw fail(`${label} must be a string`);
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > max) throw fail(`Invalid ${label}`);
  if (pattern && !pattern.test(trimmed)) throw fail(`Invalid ${label}`);
  return trimmed;
}

function hostAllowed(hostname, allowedHosts) {
  return allowedHosts.some((host) => hostname === host || hostname.endsWith(`.${host}`));
}

/**
 * Keep only a Fenbi/authorised HTTPS page URL, drop fragment and unlisted query parameters.
 * Routing parameters such as `routecs` must be declared in `routeParams`; an unlisted
 * non-tracking parameter is dropped and `urlMatchesObserved` then rejects the URL as
 * non-reproducible. Credential-shaped names are rejected even when declared.
 */
export function sanitizeSourceUrl(value, { allowedHosts = ['fenbi.com'], routeParams = [] } = {}) {
  let url;
  try { url = new URL(value); } catch { throw fail('Source URL is not a valid URL'); }
  if (url.protocol !== 'https:' || url.username || url.password) throw fail('Source URL must be HTTPS without credentials');
  if (!hostAllowed(url.hostname, allowedHosts)) throw fail('Source URL host is not an authorised practice host');
  if ([...url.searchParams.keys()].some((key) => SENSITIVE_QUERY.test(key))) {
    // The source may legitimately have been observed with such a parameter, but it must never
    // enter the queue, a lease, a handoff or a log. Callers that need the page can re-open it.
    throw fail('Source URL contains credential-like query parameters; re-observe a clean URL');
  }
  const declared = new Set(routeParams);
  const kept = new Map();
  for (const [key, value] of url.searchParams) {
    if (kept.has(key)) continue; // duplicate parameters collapse to the first observed value
    if (!SAFE_QUERY.has(key) && !declared.has(key)) continue;
    if (!ROUTE_PARAM_VALUE.test(value)) continue; // unsafe values are dropped, then reproducibility fails
    kept.set(key, value);
  }
  url.search = '';
  for (const [key, value] of kept) url.searchParams.append(key, value);
  url.hash = '';
  return url.toString();
}

export function isWriteRoute(pathname) {
  return /^\/api(?:\/|$)/i.test(pathname) || WRITE_ROUTE.test(pathname);
}

/**
 * PR54-compatible bidirectional check: the sanitized URL may not gain a parameter, and every
 * observed parameter must survive unless it is credential-shaped or purely tracking metadata.
 */
export function urlMatchesObserved(observedValue, sanitizedValue, { routeParams = [] } = {}) {
  let observed, sanitized;
  try { observed = new URL(observedValue); sanitized = new URL(sanitizedValue); }
  catch { return false; }
  if (observed.origin !== sanitized.origin || observed.pathname !== sanitized.pathname) return false;
  if (observed.username || observed.password || sanitized.username || sanitized.password) return false;
  if (sanitized.hash) return false;
  // Two values for the same route key have no guaranteed server-side precedence.
  // sanitizeSourceUrl keeps only the first, so a duplicate could silently change
  // the observed practice identity. Even duplicate identical values need review.
  const seenObservedRouteKeys = new Set();
  for (const [key] of observed.searchParams) {
    if (IGNORABLE_QUERY.test(key)) continue; // tracking is intentionally discarded
    if (seenObservedRouteKeys.has(key)) return false;
    seenObservedRouteKeys.add(key);
  }
  const declared = new Set(routeParams);
  const observedParams = new Map();
  for (const [key, value] of observed.searchParams) if (!observedParams.has(key)) observedParams.set(key, value);
  const sanitizedParams = new Map();
  for (const [key, value] of sanitized.searchParams) if (!sanitizedParams.has(key)) sanitizedParams.set(key, value);
  for (const [key, value] of sanitizedParams) {
    if (observedParams.get(key) !== value) return false; // sanitisation invented/changed a value
  }
  for (const [key, value] of observedParams) {
    if (SENSITIVE_QUERY.test(key) || IGNORABLE_QUERY.test(key)) continue;
    if (!SAFE_QUERY.has(key) && !declared.has(key)) return false; // lost a routing parameter
    if (sanitizedParams.get(key) !== value) return false;
  }
  return true;
}

/** Image references keep their static host and non-credential query, never a fragment. */
export function sanitizeImageUrl(value, { allowedHosts = ['fenbi.com', 'fbstatic.cn', 'fb.fenbike.cn'] } = {}) {
  let url;
  try { url = new URL(value); } catch { throw fail('Image URL is not a valid URL'); }
  if (url.protocol !== 'https:' || url.username || url.password) throw fail('Image URL must be HTTPS without credentials');
  if (!hostAllowed(url.hostname, allowedHosts)) throw fail('Image URL host is not an authorised static host');
  if ([...url.searchParams.keys()].some((key) => SENSITIVE_QUERY.test(key))) throw fail('Image URL contains credential-like query parameters');
  url.hash = '';
  return url.toString();
}

function normalizeImages(images, config) {
  if (images === undefined || images === null) return [];
  if (!Array.isArray(images)) throw fail('images must be an array');
  if (images.length > 1000) throw fail('Too many image references');
  const seen = new Set();
  return images.map((image, index) => {
    if (!image || typeof image !== 'object' || Array.isArray(image)) throw fail(`images[${index}] must be an object`);
    const ref = assertArtifactRelative(String(image.ref ?? ''));
    if (seen.has(ref)) throw fail(`Duplicate image reference: ${ref}`);
    seen.add(ref);
    const result = { ref };
    if (image.sourceUrl !== undefined && image.sourceUrl !== null && image.sourceUrl !== '') {
      result.sourceUrl = sanitizeImageUrl(String(image.sourceUrl), { allowedHosts: config.allowedImageHosts });
    }
    if (image.sha256 !== undefined) {
      if (!/^[a-f0-9]{64}$/i.test(String(image.sha256))) throw fail('image.sha256 must be a SHA-256');
      result.sha256 = String(image.sha256).toLowerCase();
    }
    return result;
  });
}

export function sanitizeEvidence(evidence) {
  if (evidence === undefined || evidence === null) return [];
  const items = Array.isArray(evidence) ? evidence : [evidence];
  return items.map((item) => {
    if (typeof item === 'string') return { type: 'operator_note', ref: item.slice(0, 500) };
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw fail('Evidence must be a string or object');
    for (const key of Object.keys(item)) {
      if (/cookie|token|password|secret|session|authorization/i.test(key)) throw fail('Evidence must not contain credentials');
    }
    const type = text(item.type ?? 'operator_note', 'evidence.type', { max: 80, pattern: /^[\w.-]+$/ });
    const ref = text(String(item.ref ?? item.note ?? ''), 'evidence.ref', { max: 500 });
    const result = { type, ref };
    if (item.digest !== undefined) {
      if (!/^[a-f0-9]{64}$/i.test(String(item.digest))) throw fail('evidence.digest must be a SHA-256');
      result.digest = String(item.digest).toLowerCase();
    }
    return result;
  });
}

export function placeholderVerdict(value) {
  const body = String(value ?? '').replace(/<[^>]*>/gu, '').replace(/\s+/gu, '').trim();
  if (!body) return { placeholder: false, kind: null, text: body };
  if (PLACEHOLDER.test(body)) return { placeholder: true, kind: 'explicit-placeholder', text: body };
  if (body.length <= STUB_BODY_MAX_CHARS && COLLECTION_STUB.test(body)) return { placeholder: true, kind: 'collection-stub', text: body };
  return { placeholder: false, kind: null, text: body };
}

/**
 * Normalise an explicit enqueue request. There is deliberately no catalog crawler here: a caller
 * must name the source, the version, the observed title and the URL. Unknown/partial identities
 * are rejected rather than guessed into a job.
 */
export function normalizeEnqueueInput(input = {}, config, now = Date.now()) {
  const paperSourceId = text(String(input.paperSourceId ?? input.sourceId ?? ''), 'paperSourceId', { max: 120, pattern: /^[A-Za-z0-9_.:-]+$/ });
  const version = text(String(input.version ?? ''), 'version', { max: 64, pattern: /^[A-Za-z0-9_.:-]+$/ });
  const title = text(input.title, 'title', { max: 200 });
  const subject = input.subject;
  if (!['xingce', 'shenlun'].includes(subject)) throw fail('subject must be xingce or shenlun');
  const area = text(input.area, 'area', { max: 40 });
  const year = Number(input.year);
  if (!Number.isInteger(year) || year < 2016 || year > new Date(now).getFullYear()) throw fail('year is outside the supported range');
  const variant = input.variant === undefined || input.variant === null || input.variant === '' ? null : text(String(input.variant), 'variant', { max: 40 });

  const sourceCategory = input.sourceCategory ?? 'observed_ui';
  if (!SOURCE_CATEGORIES.includes(sourceCategory)) throw fail('sourceCategory must be observed_ui, official or licensed_donor');
  const redistribution = input.redistribution ?? 'local_only';
  if (!REDISTRIBUTION.includes(redistribution)) throw fail('redistribution must be local_only or allowed');
  const license = input.license === undefined || input.license === null || input.license === '' ? null : text(String(input.license), 'license', { max: 200 });
  if (sourceCategory === 'licensed_donor' && !license) throw fail('licensed_donor sources require an explicit license');
  if (redistribution === 'allowed' && sourceCategory === 'licensed_donor' && !license) throw fail('Redistribution permission requires a license');
  const evidence = sanitizeEvidence(input.evidence);
  if (sourceCategory === 'observed_ui' && !evidence.some((item) => isPositiveObservationEvidence(item.type))) {
    throw fail('observed_ui sources need positive re-observation evidence (observed_ui/observed_catalog/route_reobserved_YYYYMMDD/offline_fetchability/url_stable_across_reads)');
  }
  if (sourceCategory !== 'observed_ui' && !evidence.length) throw fail('This source category needs a written source/permission reference');

  const urlObserved = Boolean(input.urlObserved ?? input.observedUrl ?? false);
  let url = null;
  let allowCapture = false;
  if (input.url !== undefined && input.url !== null && input.url !== '') {
    const observedUrl = String(input.url);
    url = sanitizeSourceUrl(observedUrl, {
      allowedHosts: config.allowedCaptureHosts,
      routeParams: config.routeParams,
    });
    if (!urlMatchesObserved(observedUrl, url, { routeParams: config.routeParams })) {
      throw fail('Source URL loses an undeclared routing parameter; declare it in routeParams or re-observe a clean URL', 'URL_NOT_REPRODUCIBLE');
    }
    if (isWriteRoute(new URL(url).pathname)) throw fail('Only an observed GET landing page may enter capture_ready, never an initialise/submit route', 'URL_NOT_GET_ONLY');
    if (config.requireObservedUrl && !urlObserved) throw fail('A URL may only enter capture_ready after it was explicitly observed');
    allowCapture = sourceCategory !== 'licensed_donor' && urlObserved;
  }
  if (sourceCategory === 'licensed_donor' && allowCapture) throw fail('Licensed donor artifacts are imported offline, never captured through Fenbi');

  if (allowCapture && !url) throw fail('capture_ready requires an observed URL');
  if (allowCapture && config.authorizedSourceIds !== null && !config.authorizedSourceIds.includes(paperSourceId)) {
    throw fail(`Paper source ${paperSourceId} is not on the authorised capture allowlist`, 'CAPTURE_SOURCE_UNAUTHORIZED');
  }
  const images = normalizeImages(input.images, config);
  const expectedQuestions = input.expectedQuestions ?? null;
  if (expectedQuestions !== null && (!Number.isInteger(Number(expectedQuestions)) || Number(expectedQuestions) < 1)) throw fail('expectedQuestions must be a positive integer');
  const expectedMaterials = input.expectedMaterials ?? null;
  if (expectedMaterials !== null && (!Number.isInteger(Number(expectedMaterials)) || Number(expectedMaterials) < 0)) throw fail('expectedMaterials must be a non-negative integer');

  return {
    schemaVersion: SCHEMA_VERSION,
    paperSourceId,
    version,
    title,
    subject,
    area,
    year,
    variant,
    url,
    urlObserved,
    allowCapture,
    images,
    startingOffline: Boolean(input.offline),
    source: { category: sourceCategory, license, redistribution, evidence },
    expected: {
      questions: expectedQuestions === null ? null : Number(expectedQuestions),
      materials: expectedMaterials === null ? null : Number(expectedMaterials),
    },
    permissions: {
      browserProfile: false,
      cookies: false,
      tokens: false,
      redistribution,
      localOnly: redistribution === 'local_only',
    },
  };
}

export function jobIdFor({ paperSourceId, version }) {
  return digest(`job\u0000${paperSourceId}\u0000${version}`).slice(0, 24);
}

/** The dedupe primary key required for every claimable unit. */
export function taskKeyFor({ paperSourceId, version }, stage) {
  if (!STAGES.includes(stage)) throw fail(`Unknown stage: ${stage}`);
  return digest(`task\u0000${paperSourceId}\u0000${version}\u0000${stage}`).slice(0, 32);
}

export function identityFingerprint(job) {
  return digest(JSON.stringify({
    paperSourceId: job.paperSourceId,
    version: job.version,
    title: job.title,
    subject: job.subject,
    area: job.area,
    year: job.year,
    variant: job.variant,
    url: job.url,
    source: job.source,
    expected: job.expected,
    images: job.images ?? [],
    permissions: job.permissions,
  }));
}

export function assertArtifactRelative(relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\0')) throw fail('Artifact path must be relative');
  // PR #68 F10: an asset/artifact reference is a path, never a URL or a rooted path. Reject
  // schemes, UNC and protocol-relative refs explicitly instead of relying on a later hash/open.
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(relative)) {
    throw fail('Asset/artifact references must be plain relative paths, never URLs', 'UNSAFE_ASSET_REF');
  }
  if (relative.replaceAll('\\', '/').startsWith('/')) {
    throw fail('Asset/artifact references must be plain relative paths, never absolute/UNC/protocol-relative refs', 'UNSAFE_ASSET_REF');
  }
  const normal = path.posix.normalize(relative.replaceAll('\\', '/'));
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(normal) || normal.startsWith('//')) {
    throw fail('Asset/artifact references must be plain relative paths, never URLs', 'UNSAFE_ASSET_REF');
  }
  if (normal === '..' || normal.startsWith('../') || normal.includes('/../')) throw fail('Artifact path escapes its stage directory');
  if (normal === '.' || normal === '') throw fail('Artifact path must name a file');
  return normal;
}
