import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MAX_CONCURRENCY } from './schedule.mjs';

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
export const WORK = path.join(REPO, 'work', 'fenbi');
export const DEFAULTS = Object.freeze({
  profileName: 'fenbi-main', channel: 'chrome', executablePath: null,
  entryUrl: 'https://www.fenbi.com/spa/tiku', timeoutMs: 45000,
  delayMs: 800, settleMs: 1500, maxPages: 250,
  // Pages inside the single persistent context. 1 = the original strictly sequential behaviour.
  concurrency: 1,
  contentSelector: null, nextQuestionSelector: null, explanationSelector: null,
  domAdapter: null,
  fieldMap: {}, scope: { fromYear: 2016, toYear: new Date().getFullYear(),
    areas: ['国考', '浙江', '江苏', '上海', '北京', '天津', '广东', '福建', '广州', '深圳'] },
});

export function safeChild(root, relative) {
  if (typeof relative !== 'string' || !relative || path.isAbsolute(relative) || relative.includes('\0')) throw new Error('Invalid relative path');
  const result = path.resolve(root, relative);
  if (!result.startsWith(path.resolve(root) + path.sep)) throw new Error('Path escapes its work directory');
  return result;
}

export async function ensurePrivateWork(work = WORK) {
  // Do not let a junction or symbolic link redirect account files into a tracked tree.
  const resolved = path.resolve(work);
  await fs.mkdir(resolved, { recursive: true, mode: 0o700 });
  let current = resolved;
  while (true) {
    if ((await fs.lstat(current)).isSymbolicLink()) throw new Error('Work directories must not contain symbolic links or junctions');
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return resolved;
}

// Query names that look like account state. Reused for the fragment query of an in-app route.
const SECRET_PARAMETER = /token|key|secret|auth|session|cookie|signature|credential|password|phone|mobile|verification/i;

/**
 * A single-page app may carry its route in the fragment. Keep only a strict in-app route shape,
 * and inside it only short non-secret parameters; every other fragment — including credential
 * fragments such as `#access_token=…` — is dropped exactly as before.
 */
/** Exported so every URL normaliser in this framework applies the identical fragment rule. */
export function sanitizeHashRoute(hash) {
  // `(?!\/)` keeps a protocol-relative-looking fragment such as `#//host` from being treated as an
  // in-app route; it is not one, so it is dropped like any other unrecognised fragment.
  const match = /^#!?(\/(?!\/)[A-Za-z0-9/_.-]*)(?:\?(.*))?$/u.exec(String(hash ?? ''));
  if (!match) return '';
  const kept = new URLSearchParams();
  for (const [key, value] of new URLSearchParams(match[2] ?? '')) {
    if (!SECRET_PARAMETER.test(key) && /^[\w,.-]{0,200}$/u.test(value)) kept.append(key, value);
  }
  const query = kept.toString();
  return `#${match[1]}${query ? `?${query}` : ''}`;
}

export function publicUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || !/(^|\.)fenbi\.com$/i.test(url.hostname)) throw new Error('Only HTTPS Fenbi page URLs are allowed');
  const keep = new Set(['labelId', 'paperId', 'id', 'toPage', 'pageSize', 'type', 'categoryId']);
  for (const key of [...url.searchParams.keys()]) if (!keep.has(key)) url.searchParams.delete(key);
  url.hash = sanitizeHashRoute(url.hash);
  return url.toString();
}

/**
 * What `publicUrl` would drop from an observed URL. A dropped fragment or path changes where the
 * browser lands, so a caller must refuse such a URL instead of navigating somewhere else and
 * capturing whatever happens to be there.
 */
export function urlRouteLoss(value) {
  const observed = new URL(value), normalized = new URL(publicUrl(value));
  const dropped = [...observed.searchParams.keys()].filter((key) => !normalized.searchParams.has(key));
  const secret = dropped.filter((key) => SECRET_PARAMETER.test(key));
  // A credential parameter is stripped on purpose; any *other* dropped parameter means this
  // framework cannot reproduce the URL it observed, so navigation to it is not verified.
  return { path: observed.pathname !== normalized.pathname,
    hash: Boolean(observed.hash) && !normalized.hash,
    params: dropped, secretParams: secret,
    routeParams: dropped.filter((key) => !SECRET_PARAMETER.test(key)) };
}

/** True when navigating to this URL would not reproduce the URL that was actually observed. */
export function urlIsReproducible(value) {
  const loss = urlRouteLoss(value);
  return !loss.path && !loss.hash && !loss.routeParams.length;
}

export async function loadConfig(filename) {
  const raw = filename ? JSON.parse(await fs.readFile(filename, 'utf8')) : {};
  for (const key of Object.keys(raw)) if (!(key in DEFAULTS)) throw new Error(`Unknown configuration field: ${key}`);
  const config = { ...DEFAULTS, ...raw, scope: { ...DEFAULTS.scope, ...raw.scope } };
  if (!/^[a-z0-9][a-z0-9_-]{0,50}$/i.test(config.profileName)) throw new Error('Invalid profileName');
  if (!['chrome', 'msedge', 'chromium'].includes(config.channel)) throw new Error('Unsupported browser channel');
  if (config.domAdapter !== null && config.domAdapter !== 'fenbi-xingce-v1') throw new Error('Unsupported DOM adapter');
  if (config.executablePath !== null && (typeof config.executablePath !== 'string' || !path.isAbsolute(config.executablePath))) throw new Error('executablePath must be an absolute installed browser path');
  for (const [key, min, max] of [['timeoutMs', 1000, 120000], ['delayMs', 200, 60000], ['settleMs', 100, 30000], ['maxPages', 1, 1000],
    ['concurrency', 1, MAX_CONCURRENCY]]) {
    if (!Number.isInteger(config[key]) || config[key] < min || config[key] > max) throw new Error(`Invalid ${key}`);
  }
  for (const key of ['contentSelector', 'nextQuestionSelector', 'explanationSelector']) {
    if (config[key] !== null && (typeof config[key] !== 'string' || !config[key].trim())) throw new Error(`Invalid ${key}`);
  }
  if (!config.fieldMap || Array.isArray(config.fieldMap) || typeof config.fieldMap !== 'object') throw new Error('fieldMap must be an object');
  if (!Array.isArray(config.scope.areas) || config.scope.areas.some(x => typeof x !== 'string') ||
      !Number.isInteger(config.scope.fromYear) || !Number.isInteger(config.scope.toYear) ||
      config.scope.fromYear < 2016 || config.scope.toYear < config.scope.fromYear) throw new Error('Invalid scope');
  config.entryUrl = publicUrl(config.entryUrl);
  config.workDir = WORK;
  config.profileDir = safeChild(WORK, `profiles/${config.profileName}`);
  return config;
}
