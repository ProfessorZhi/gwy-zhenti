import { mkdir, open, readFile, stat, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { load } from 'cheerio';
import { observedReadUrl } from './reads.mjs';
import { ROUTE_PARAM_VALUE, normalizeRouteParams, sanitizeHashRoute } from './config.mjs';

const SAFE_QUERY = new Set(['labelId', 'toPage', 'page', 'pageSize', 'paperId', 'year', 'categoryId', 'provinceId', 'id', 'type']);
const SENSITIVE_QUERY = /token|key|secret|auth|session|cookie|signature|sign|credential|password|phone|mobile|code/i;
const ACCOUNT_PATH = /(?:^|\/)(?:user[^/]*|history|member\w*|auth\w*|login|logout|current|selected|submit|records?|favorites?|category-exercises-unfinished)(?:\/|$)/i;
// The only non-account `data-*` attributes that may survive DOM capture. Kept as an explicit
// list so a newly observed attribute cannot start persisting account or session state by default.
// `data-question-key` carries Fenbi's composite question key (for example `3_1_beq2d`) and is what
// the verified DOM adapter selects on; without it every `app-ti` is invisible to that adapter.
const STRUCTURAL_DATA_ATTRIBUTES = ['data-latex', 'data-math', 'data-formula', 'data-src', 'data-original', 'data-question-key'];
// A question key is a bare identifier. Anything else — a URL, a query string, a token, an
// over-long value — is dropped like any other unrecognised attribute rather than persisted.
const QUESTION_KEY = /^[A-Za-z0-9_-]{1,80}$/u;
const MAX_ASSET_BYTES = 12 * 1024 * 1024;
const MAX_ASSETS = 256;
const MAX_TOTAL_ASSET_BYTES = 128 * 1024 * 1024;

function parsedUrl(value) { try { return new URL(value); } catch { return null; } }
function isFenbiHost(host) { return host === 'fenbi.com' || host.endsWith('.fenbi.com'); }
function allowedHost(host) { return isFenbiHost(host) || host === 'fbstatic.cn' || host.endsWith('.fbstatic.cn'); }
function allowedResource(url) {
  // Additional image host actually referenced by the authenticated Fenbi exam DOM.
  return allowedHost(url.hostname) || (url.hostname === 'fb.fenbike.cn' && /^\/api\/(?:tarzan\/images\/|planet\/accessories\/formulas\/?$)/.test(url.pathname));
}
export function isAllowedSourceUrl(value) {
  const url = parsedUrl(value);
  return Boolean(url && url.protocol === 'https:' && allowedResource(url) && !url.username && !url.password && ![...url.searchParams.keys()].some(key => SENSITIVE_QUERY.test(key)));
}
function safeAssetUrl(value) {
  if (!isAllowedSourceUrl(value)) return null;
  const url = new URL(value);
  url.hash = '';
  return url.toString();
}
/** Persisted page URL: keeps only the parameters this framework recognises, or null off-domain. */
export function safePageUrl(value, routeParams = []) { return safeUrl(value, routeParams); }

/**
 * Decide whether the page we hold is actually the paper this job targets.
 *
 * Returns null when the capture may proceed, or a reason string when it must be blocked. It is
 * deliberately conservative: it blocks only the cases that are unambiguously wrong — the page left
 * the Fenbi origin, or it is still sitting on the catalogue while the job asked for a deeper route,
 * which is exactly what a link that opened in a new tab looks like. It never guesses that some
 * other page is "probably" the paper; a page this framework did not open is only ever named.
 */
export function landingMismatch({ landed, expected, entry, strayUrls = [] }) {
  if (!landed) return 'page-not-on-fenbi';
  if (landed === entry && expected && expected !== entry) {
    // Prefer the more specific diagnosis: the paper is open, just not in the page we are holding.
    return strayUrls.some((url) => url !== entry) ? 'paper-opened-in-another-page' : 'stayed-on-entry-page';
  }
  return null;
}
function safeUrl(value, routeParams = []) {
  const url = parsedUrl(value);
  if (!url || url.username || url.password || !allowedHost(url.hostname)) return null;
  // Keep an in-app fragment route so a page on `#/exam/...` does not look like the bare catalogue;
  // every other fragment, including credential ones, is dropped.
  url.hash = sanitizeHashRoute(url.hash);
  const declared = new Set(normalizeRouteParams(routeParams));
  for (const [key, val] of [...url.searchParams.entries()]) {
    const safe = SAFE_QUERY.has(key) && /^[\w,.-]{0,100}$/.test(val);
    const route = declared.has(key) && ROUTE_PARAM_VALUE.test(val);
    if (!safe && !route) url.searchParams.delete(key);
  }
  return url.toString();
}
function error(code, message) { return Object.assign(new Error(message), { code }); }

/** Evaluate a request before any network access. Authentication writes are only allowed in login mode. */
export function requestPolicy({ url: value, method = 'GET', navigation = false }, mode = 'capture') {
  const url = parsedUrl(value);
  if (!url || !['https:', 'http:'].includes(url.protocol) || url.username || url.password) return 'blockedUrl';
  if (url.protocol !== 'https:') return 'blockedUrl';
  if (navigation && !isFenbiHost(url.hostname)) return 'blockedNavigation';
  if (!allowedResource(url)) return 'blockedHost';
  if (['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) return null;
  if (mode === 'login' && url.hostname === 'login.fenbi.com' && /^\/api\/(?:users|sms|login|auth|passport)(?:\/|$)/i.test(url.pathname)) return null;
  return 'blockedWrites';
}

/** Dedicated persistent profile; an existing framework lock is never removed or reused. */
export async function openSession(config, { mode = 'capture', headless = false, launcher } = {}) {
  if (!['capture', 'login'].includes(mode)) throw error('INVALID_MODE', 'Unsupported browser mode.');
  if (!config.profileDir || !path.isAbsolute(config.profileDir)) throw error('INVALID_PROFILE', 'An absolute dedicated profile directory is required.');
  const entry = parsedUrl(config.entryUrl ?? 'https://www.fenbi.com/spa/tiku');
  if (!entry || entry.protocol !== 'https:' || !isFenbiHost(entry.hostname) || entry.username || entry.password) throw error('INVALID_ENTRY', 'Entry URL must be an HTTPS Fenbi page.');
  const channel = config.channel ?? 'chrome';
  if (!['chrome', 'msedge', 'chromium'].includes(channel)) throw error('INVALID_CHANNEL', 'Choose chrome, msedge, or an installed chromium executable.');
  await mkdir(config.profileDir, { recursive: true });
  const lockPath = path.join(config.profileDir, '.fenbi-framework.lock');
  const owner = `${process.pid}:${randomUUID()}`;
  let lock;
  try { lock = await open(lockPath, 'wx'); }
  catch (cause) {
    if (cause.code === 'EEXIST') throw error('PROFILE_LOCKED', 'This profile is locked. Close its owner; stale locks require manual inspection.');
    throw error('PROFILE_LOCK_FAILED', 'Unable to lock the dedicated browser profile.');
  }
  const created = await lock.stat();
  try { await lock.writeFile(owner, 'utf8'); }
  catch {
    await lock.close();
    // A failed initial write must not strand our newly-created lock or remove a replacement lock.
    try { const current = await stat(lockPath); if (current.dev === created.dev && current.ino === created.ino) await unlink(lockPath); } catch { /* Leave ambiguous ownership for manual inspection. */ }
    throw error('PROFILE_LOCK_FAILED', 'Unable to initialize the dedicated profile lock.');
  }
  await lock.close();
  let released = false;
  async function release() {
    if (released) return;
    released = true;
    try { if (await readFile(lockPath, 'utf8') === owner) await unlink(lockPath); }
    catch (cause) { if (cause.code !== 'ENOENT') throw error('PROFILE_UNLOCK_FAILED', 'Profile lock could not be released; inspect it manually.'); }
  }
  let context;
  const auth = { status: 'unknown', evidence: [] };
  const guardStats = { blockedWrites: 0, blockedNavigation: 0, blockedHost: 0, blockedUrl: 0 };
  try {
    const chromium = launcher ?? (await import('playwright-core')).chromium;
    context = await chromium.launchPersistentContext(config.profileDir, {
      headless,
      ...(config.executablePath ? { executablePath: config.executablePath } : channel !== 'chromium' ? { channel } : {}),
      serviceWorkers: 'block',
      acceptDownloads: false,
      viewport: { width: 1440, height: 1000 },
    });
    context.setDefaultTimeout(config.timeoutMs ?? 45000);
    await context.route('**/*', async route => {
      const request = route.request();
      const reason = requestPolicy({ url: request.url(), method: request.method(), navigation: request.isNavigationRequest() }, mode);
      if (reason) { guardStats[reason] += 1; await route.abort('blockedbyclient'); }
      else await route.continue();
    });
    context.on('response', response => {
      const url = parsedUrl(response.url());
      if (url?.hostname !== 'login.fenbi.com' || url.pathname !== '/api/users/info' || response.request().method() !== 'GET') return;
      const status = response.status();
      if (status === 200 || status === 401 || status === 403) {
        auth.status = status === 200 ? 'authenticated' : 'unauthenticated';
        auth.evidence.push({ source: 'users/info HTTP status only', status });
      }
    });
    const page = await context.newPage();
    let closed = false;
    return { context, page, auth, guardStats, stats: guardStats, async close() {
      if (closed) return;
      closed = true;
      try { await context.close(); } finally { await release(); }
    } };
  } catch (cause) {
    try { if (context) await context.close(); } catch { /* Release our own lock even after a browser failure. */ }
    await release();
    if (cause.code === 'PROFILE_UNLOCK_FAILED') throw cause;
    throw error('BROWSER_START_FAILED', 'Could not open the installed browser and Fenbi entry. Verify browser installation, profile ownership, and connectivity.');
  }
}

function observationTarget(response) {
  const url = parsedUrl(response.url());
  if (!url || url.protocol !== 'https:' || url.hostname !== 'tiku.fenbi.com' || response.request().method() !== 'GET') return null;
  const match = /^\/api\/(xingce|shenlun)\//.exec(url.pathname);
  if (!match || ACCOUNT_PATH.test(url.pathname)) return null;
  if (/\/(?:exercises?)(?:\/|$)/i.test(url.pathname) && !/^\/api\/(?:xingce|shenlun)\/exercises\/(?:\d+|[a-f0-9-]{16,})(?:\/(?:questions|answers|answercard))?\/?$/i.test(url.pathname)) return null;
  let replayUrl = null;
  // Never register a redacted/modified URL as if the page had requested it.
  try { replayUrl = observedReadUrl(url.toString()); } catch {}
  return { url: safeUrl(url.toString()), replayUrl, subject: match[1] };
}

/** Observe only read requests the page actually makes; never retain raw response envelopes. */
export function observeReadResponses(page, onPayload, { maxResponseBytes = 8 * 1024 * 1024 } = {}) {
  if (!Number.isSafeInteger(maxResponseBytes) || maxResponseBytes < 1) throw error('INVALID_RESPONSE_LIMIT', 'Response byte limit must be a positive integer.');
  const pending = new Set();
  const stats = { observed: 0, accepted: 0, oversized: 0, unauthorized: 0, captcha: 0, rateLimited: 0, failed: 0, nonJson: 0 };
  let stopped = false;
  async function inspect(response) {
    const meta = observationTarget(response);
    if (!meta) return;
    stats.observed += 1;
    const status = response.status();
    if (status === 401 || status === 403) { stats.unauthorized += 1; return; }
    // Counted separately from generic failures so a scheduler can back off instead of only retrying.
    if (status === 429 || status === 503) { stats.rateLimited += 1; return; }
    if (/captcha|verifycode|verification/i.test(parsedUrl(response.url()).pathname)) { stats.captcha += 1; return; }
    if (status < 200 || status >= 300) { stats.failed += 1; return; }
    const headers = response.headers();
    if (!/\b(?:application\/json|[\w.+-]+\/[^;]*\+json)\b/i.test(headers['content-type'] ?? '')) { stats.nonJson += 1; return; }
    const declared = Number(headers['content-length']);
    if (Number.isFinite(declared) && declared > maxResponseBytes) { stats.oversized += 1; return; }
    const body = await response.body();
    if (body.length > maxResponseBytes) { stats.oversized += 1; return; }
    const payload = JSON.parse(body.toString('utf8'));
    const challenge = payload && typeof payload === 'object' && [payload.code, payload.error, payload.message, payload.msg].some(value => typeof value === 'string' && /captcha|验证码|人机验证/i.test(value));
    if (challenge) { stats.captcha += 1; return; }
    await onPayload(payload, meta);
    stats.accepted += 1;
  }
  function listener(response) {
    if (stopped) return;
    const operation = inspect(response).catch(() => { stats.failed += 1; }).finally(() => pending.delete(operation));
    pending.add(operation);
  }
  page.on('response', listener);
  return { stats, async flush() { while (pending.size) await Promise.all([...pending]); }, stop() { stopped = true; page.off('response', listener); } };
}

function paperLinks($, base) {
  const result = [];
  $('a[href]').each((_, element) => {
    let url;
    try { url = new URL($(element).attr('href'), base); } catch { return; }
    if (!isFenbiHost(url.hostname) || url.protocol !== 'https:' || !/paper|catalog|xingce|shenlun|试卷/i.test(url.pathname + $(element).text())) return;
    const clean = safeUrl(url.toString());
    if (clean) result.push({ url: clean, text: $(element).text().trim() });
  });
  return [...new Map(result.map(item => [item.url, item])).values()];
}

/** A configured content selector is mandatory for body capture; otherwise return a catalog summary only. */
export async function captureDom(page, selector, { routeParams = [] } = {}) {
  const current = page.url();
  const url = parsedUrl(current);
  if (!url || url.protocol !== 'https:' || !isFenbiHost(url.hostname)) throw error('UNSAFE_PAGE', 'DOM capture is limited to Fenbi pages.');
  const title = await page.title();
  if (!selector) {
    const links = await page.locator('a[href]').evaluateAll(elements => elements.map(element => ({ href: element.getAttribute('href'), text: element.textContent ?? '' })));
    const $ = load('<section></section>');
    for (const link of links) $('<a>').attr('href', link.href ?? '').text(link.text).appendTo('section');
    return { url: safeUrl(current, routeParams), title, html: '', links: paperLinks($, current), images: [], blocked: { reason: 'content_selector_required' } };
  }
  // Never allow an unrestricted document/body capture containing account navigation or personal data.
  if (/(?:^|[\s,>+~])(?:html|body|\*|:root)(?:$|[\s,>+~.:#\[])/i.test(selector)) throw error('UNSAFE_SELECTOR', 'Choose a specific question or material container.');
  const locator = page.locator(selector);
  const count = await locator.count();
  if (!count) return { url: safeUrl(current, routeParams), title, html: '', links: [], images: [], blocked: { reason: 'selector_not_found' } };
  const fragments = await locator.evaluateAll(elements => elements.map(element => {
    const clone = element.cloneNode(true);
    const originals = [...element.querySelectorAll('img')];
    const copies = [...clone.querySelectorAll('img')];
    if (element.tagName === 'IMG') { originals.unshift(element); copies.unshift(clone); }
    originals.forEach((image, index) => {
      const actual = image.currentSrc || image.getAttribute('src') || image.getAttribute('data-src') || image.getAttribute('data-original');
      if (actual) copies[index].setAttribute('src', actual);
    });
    return clone.outerHTML;
  }));
  const $ = load(fragments.join('\n'), null, false);
  $('script,style,form,input,button,header,nav,footer,iframe,object,embed,[contenteditable], [data-account], [data-user], .user-info, .user-avatar, .account-info').remove();
  $('*').each((_, element) => {
    for (const name of Object.keys(element.attribs ?? {})) {
      if (/^on/i.test(name) || /token|secret|password|cookie|authorization/i.test(name) || name === 'style'
          || (name.startsWith('data-') && !STRUCTURAL_DATA_ATTRIBUTES.includes(name))
          || (name === 'data-question-key' && !QUESTION_KEY.test($(element).attr(name) ?? ''))) $(element).removeAttr(name);
    }
  });
  const text = $.root().text();
  let blocked = /验证码|人机验证|安全验证|captcha/i.test(text) ? { reason: 'verification_required' } : null;
  const images = [];
  let missingImages = 0;
  $('img').each((_, element) => {
    try {
      const source = $(element).attr('src') || $(element).attr('data-src') || $(element).attr('data-original') || $(element).attr('srcset')?.split(',')[0].trim().split(/\s+/)[0];
      const image = source ? new URL(source, current) : null;
      const clean = image ? safeAssetUrl(image.toString()) : null;
      if (clean) {
        images.push({ url: clean, alt: $(element).attr('alt') ?? '' });
        $(element).attr('src', clean);
      } else { $(element).removeAttr('src'); missingImages += 1; }
    } catch { $(element).removeAttr('src'); missingImages += 1; }
    $(element).removeAttr('data-src').removeAttr('data-original');
  });
  if (missingImages) blocked = { ...(blocked ?? { reason: 'image_source_unavailable' }), missingImages };
  $('a[href]').each((_, element) => {
    try { const clean = safeUrl(new URL($(element).attr('href'), current).toString()); if (clean) $(element).attr('href', clean); else $(element).removeAttr('href'); }
    catch { $(element).removeAttr('href'); }
  });
  $('[srcset]').removeAttr('srcset');
  return { url: safeUrl(current, routeParams), title, html: $.html(), links: paperLinks($, current), images, blocked };
}

function assetCandidates(document) {
  const values = [...(document.assets ?? []), ...(document.images ?? [])].map(item => typeof item === 'string' ? item : item.url);
  if (document.html) {
    const $ = load(document.html, null, false);
    $('img[src]').each((_, element) => values.push($(element).attr('src')));
  }
  return [...new Set(values.filter(Boolean))];
}

/** Download only actually referenced images from Fenbi domains, verifying pixels before committing files. */
export async function downloadAssets(page, document, assetDir) {
  if (!path.isAbsolute(assetDir)) throw error('INVALID_ASSET_DIR', 'Asset directory must be absolute.');
  await mkdir(assetDir, { recursive: true });
  const result = [];
  let totalBytes = 0;
  const candidates = assetCandidates(document);
  // A 401/403/429/503 ends this batch at once: the rest stay pending for a later authorized pass,
  // and the failing record carries httpStatus so the caller can count it as a risk signal.
  let halted = false;
  for (const [index, value] of candidates.entries()) {
    let url;
    try { url = new URL(value, document.url); } catch { result.push({ status: 'rejected_url' }); continue; }
    if (url.protocol !== 'https:' || !allowedResource(url) || url.username || url.password || [...url.searchParams.keys()].some(key => SENSITIVE_QUERY.test(key))) {
      result.push({ status: 'rejected_url' }); continue;
    }
    const record = { url: safeAssetUrl(url.toString()), status: 'pending' };
    result.push(record);
    if (halted) continue;
    if (index >= MAX_ASSETS || totalBytes >= MAX_TOTAL_ASSET_BYTES) { record.status = 'limit_exceeded'; continue; }
    let response;
    try {
      response = await page.context().request.get(url.toString(), { maxRedirects: 0, timeout: 45000 });
      if (response.status() === 401 || response.status() === 403) { record.status = 'unauthorized'; record.httpStatus = response.status(); halted = true; continue; }
      if (response.status() === 429 || response.status() === 503) { record.status = 'http_error'; record.httpStatus = response.status(); halted = true; continue; }
      if (response.status() < 200 || response.status() >= 300) { record.status = 'http_error'; continue; }
      const headers = response.headers();
      const type = (headers['content-type'] ?? '').split(';')[0].toLowerCase();
      const extensions = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp', 'image/svg+xml': 'svg', 'image/avif': 'avif', 'image/bmp': 'bmp' };
      if (!extensions[type]) { record.status = 'not_image'; continue; }
      if (Number(headers['content-length']) > MAX_ASSET_BYTES) { record.status = 'oversized'; continue; }
      const bytes = await response.body();
      if (bytes.length > MAX_ASSET_BYTES || totalBytes + bytes.length > MAX_TOTAL_ASSET_BYTES) { record.status = 'oversized'; continue; }
      if (type === 'image/svg+xml' && /<\s*(?:script|foreignObject|iframe|object|embed)\b|\bon\w+\s*=|<!DOCTYPE|(?:href|src)\s*=\s*["']\s*(?:https?:|\/\/|javascript:)/i.test(bytes.toString('utf8'))) { record.status = 'unsafe_svg'; continue; }
      const dimensions = await page.evaluate(async ({ encoded, type: mime }) => {
        const source = `data:${mime};base64,${encoded}`;
        const image = new Image();
        image.src = source;
        await image.decode();
        if (!image.naturalWidth || !image.naturalHeight) throw new Error('Invalid image');
        return { width: image.naturalWidth, height: image.naturalHeight };
      }, { encoded: bytes.toString('base64'), type });
      if (!Number.isInteger(dimensions.width) || !Number.isInteger(dimensions.height) || dimensions.width < 1 || dimensions.height < 1) { record.status = 'decode_failed'; continue; }
      const sha256 = createHash('sha256').update(bytes).digest('hex');
      const localPath = `${sha256}.${extensions[type]}`;
      await writeFile(path.join(assetDir, localPath), bytes, { flag: 'wx' }).catch(async cause => {
        if (cause.code !== 'EEXIST') throw cause;
        if (createHash('sha256').update(await readFile(path.join(assetDir, localPath))).digest('hex') !== sha256) throw error('ASSET_COLLISION', 'Existing asset content does not match its hash.');
      });
      totalBytes += bytes.length;
      Object.assign(record, { localPath, sha256, bytes: bytes.length, ...dimensions, decoded: true,
        decode: { method: 'browser-image-decode', sha256, ...dimensions }, status: 'downloaded' });
    } catch { record.status = 'download_failed'; }
    finally { if (response?.dispose) await response.dispose().catch(() => {}); }
  }
  document.assets = result;
  return result;
}
