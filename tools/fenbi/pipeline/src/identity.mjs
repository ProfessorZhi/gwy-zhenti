import path from 'node:path';
import { digest } from './fsutil.mjs';
import { STAGES, SCHEMA_VERSION } from './constants.mjs';

export const SOURCE_CATEGORIES = Object.freeze(['observed_ui', 'official', 'licensed_donor']);
export const REDISTRIBUTION = Object.freeze(['local_only', 'allowed']);

const SAFE_QUERY = new Set(['labelId', 'paperId', 'id', 'toPage', 'pageSize', 'type', 'categoryId']);
export const SENSITIVE_QUERY = /token|key|secret|auth|session|cookie|signature|sign|credential|password|phone|mobile|code/i;
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
 * This mirrors tools/fenbi/src/config.mjs#publicUrl so the queue cannot persist credentials that
 * the capture framework itself would have stripped.
 */
export function sanitizeSourceUrl(value, { allowedHosts = ['fenbi.com'] } = {}) {
  let url;
  try { url = new URL(value); } catch { throw fail('Source URL is not a valid URL'); }
  if (url.protocol !== 'https:' || url.username || url.password) throw fail('Source URL must be HTTPS without credentials');
  if (!hostAllowed(url.hostname, allowedHosts)) throw fail('Source URL host is not an authorised practice host');
  if ([...url.searchParams.keys()].some((key) => SENSITIVE_QUERY.test(key))) {
    // The source may legitimately have been observed with such a parameter, but it must never
    // enter the queue, a lease, a handoff or a log. Callers that need the page can re-open it.
    throw fail('Source URL contains credential-like query parameters; re-observe a clean URL');
  }
  for (const key of [...url.searchParams.keys()]) if (!SAFE_QUERY.has(key)) url.searchParams.delete(key);
  url.hash = '';
  return url.toString();
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
  if (sourceCategory === 'observed_ui' && !evidence.some((item) => item.type === 'observed_ui' || item.type === 'observed_catalog')) {
    throw fail('observed_ui sources need an observed_ui/observed_catalog evidence entry');
  }
  if (sourceCategory !== 'observed_ui' && !evidence.length) throw fail('This source category needs a written source/permission reference');

  const urlObserved = Boolean(input.urlObserved ?? input.observedUrl ?? false);
  let url = null;
  let allowCapture = false;
  if (input.url !== undefined && input.url !== null && input.url !== '') {
    url = sanitizeSourceUrl(String(input.url), { allowedHosts: config.allowedCaptureHosts });
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
  if (typeof relative !== 'string' || !relative || path.isAbsolute(relative) || relative.includes('\0')) throw fail('Artifact path must be relative');
  const normal = path.posix.normalize(relative.replaceAll('\\', '/'));
  if (normal === '..' || normal.startsWith('../') || normal.includes('/../')) throw fail('Artifact path escapes its stage directory');
  return normal;
}
