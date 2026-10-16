import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
export const WORK = path.join(REPO, 'work', 'fenbi');
export const DEFAULTS = Object.freeze({
  profileName: 'fenbi-main', channel: 'chrome', executablePath: null,
  entryUrl: 'https://www.fenbi.com/spa/tiku', timeoutMs: 45000,
  delayMs: 800, settleMs: 1500, maxPages: 250,
  contentSelector: null, nextQuestionSelector: null, explanationSelector: null,
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

export function publicUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || !/(^|\.)fenbi\.com$/i.test(url.hostname)) throw new Error('Only HTTPS Fenbi page URLs are allowed');
  const keep = new Set(['labelId', 'paperId', 'id', 'toPage', 'pageSize', 'type', 'categoryId']);
  for (const key of [...url.searchParams.keys()]) if (!keep.has(key)) url.searchParams.delete(key);
  // Fenbi's verified entry uses pathname routes. Never persist arbitrary fragment credentials.
  url.hash = '';
  return url.toString();
}

export async function loadConfig(filename) {
  const raw = filename ? JSON.parse(await fs.readFile(filename, 'utf8')) : {};
  for (const key of Object.keys(raw)) if (!(key in DEFAULTS)) throw new Error(`Unknown configuration field: ${key}`);
  const config = { ...DEFAULTS, ...raw, scope: { ...DEFAULTS.scope, ...raw.scope } };
  if (!/^[a-z0-9][a-z0-9_-]{0,50}$/i.test(config.profileName)) throw new Error('Invalid profileName');
  if (!['chrome', 'msedge', 'chromium'].includes(config.channel)) throw new Error('Unsupported browser channel');
  if (config.executablePath !== null && (typeof config.executablePath !== 'string' || !path.isAbsolute(config.executablePath))) throw new Error('executablePath must be an absolute installed browser path');
  for (const [key, min, max] of [['timeoutMs', 1000, 120000], ['delayMs', 200, 60000], ['settleMs', 100, 30000], ['maxPages', 1, 1000]]) {
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
