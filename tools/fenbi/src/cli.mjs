#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { createInterface } from 'node:readline/promises';
import { setTimeout as sleep } from 'node:timers/promises';
import { DEFAULTS, REPO, WORK, ensurePrivateWork, loadConfig, publicUrl, safeChild } from './config.mjs';
import { acquireLock, digest, jobKey, readJson, resumeBundle, writeJson } from './store.mjs';
import { createDocument, absorbPayload, collectAssetUrls } from './model.mjs';
import { validateDocument } from './validate.mjs';
import { openSession, observeReadResponses, captureDom, downloadAssets } from './browser.mjs';
import { makePlan, parseInventory } from './plan.mjs';
import { exportCandidate } from './render.mjs';
import { observedReadUrl, replayReads } from './reads.mjs';
import { sanitizeHtml } from './privacy.mjs';
import { normalizeCatalogPayload, mergeCatalog } from './catalog.mjs';

const HELP = `Fenbi capture (local persistent Chrome/Edge; no model or cloud-browser calls)
  node src/cli.mjs init
  node src/cli.mjs doctor
  node src/cli.mjs login
  node src/cli.mjs catalog              # browse categories manually, then Enter
  node src/cli.mjs inspect --url URL    # discover observed JSON field shapes
  node src/cli.mjs plan [--all]         # compare observed catalog with repository
  node src/cli.mjs add --id ID --title TITLE --subject xingce|shenlun
      --area AREA --year YEAR --variant VARIANT --url OBSERVED_URL [--questions N]
  node src/cli.mjs capture --job KEY [--manual] [--force] [--headless]
  node src/cli.mjs capture --all        # ready URLs only, one browser session
  node src/cli.mjs validate --job KEY
  node src/cli.mjs export --job KEY     # fresh candidate folder only
Options: --config FILE, --wait-seconds N, --materials N
Private profile/data/output: <repository>/work/fenbi/
Unknown totals or unmapped fields remain partial. Nothing writes formal papers.
`;

function args() {
  return parseArgs({ allowPositionals: true, options: Object.fromEntries([
    ...['config', 'url', 'job', 'id', 'title', 'subject', 'area', 'year', 'variant', 'questions', 'materials', 'wait-seconds'].map(x => [x, { type: 'string' }]),
    ...['all', 'manual', 'force', 'headless', 'help'].map(x => [x, { type: 'boolean', default: false }]),
  ]) });
}

async function pause(message, values) {
  if (values['wait-seconds'] !== undefined) {
    const seconds = Number(values['wait-seconds']);
    if (!Number.isInteger(seconds) || seconds < 1 || seconds > 300) throw new Error('wait-seconds must be 1..300');
    await sleep(seconds * 1000); return;
  }
  if (!process.stdin.isTTY) throw new Error('Interactive commands need a terminal; use --wait-seconds for bounded observation');
  const terminal = createInterface({ input: process.stdin, output: process.stdout });
  try { await terminal.question(`${message}\n按 Enter 保存并继续：`); } finally { terminal.close(); }
}

function fieldShapes(value, prefix = '', out = [], depth = 0) {
  if (depth > 5 || out.length >= 100 || !value || typeof value !== 'object') return out;
  for (const [key, child] of Object.entries(value)) {
    if (/token|cookie|password|phone|mobile|user|member|auth|sign|secret/i.test(key)) continue;
    const route = prefix ? `${prefix}.${key}` : key;
    out.push({ path: route, type: Array.isArray(child) ? 'array' : typeof child, ...(Array.isArray(child) ? { observedLength: child.length } : {}) });
    if (Array.isArray(child)) fieldShapes(child.find(x => x && typeof x === 'object'), `${route}[]`, out, depth + 1);
    else if (child && typeof child === 'object') fieldShapes(child, route, out, depth + 1);
    if (out.length >= 100) break;
  }
  return out;
}

async function readRegistry(config) {
  const filename = path.join(WORK, `observed-reads-${config.profileName}.json`);
  const saved = await readJson(filename, null);
  // v2 distinguishes exact observed requests from older redacted diagnostic URLs.
  return new Set(saved?.schemaVersion === 2 && saved.profileName === config.profileName && Array.isArray(saved.urls) ? saved.urls.map(observedReadUrl) : []);
}

async function saveRegistry(config, urls) {
  await writeJson(path.join(WORK, `observed-reads-${config.profileName}.json`), {
    schemaVersion: 2, profileName: config.profileName, urls: [...urls],
  });
}

async function navigate(page, url, config) {
  await page.goto(publicUrl(url), { waitUntil: 'domcontentloaded', timeout: config.timeoutMs });
  await sleep(config.settleMs);
}

async function browserCommand(command, config, values) {
  const session = await openSession(config, { mode: command === 'login' ? 'login' : 'capture', headless: values.headless });
  const catalogPath = path.join(WORK, 'catalog.json');
  const catalog = await readJson(catalogPath, { schemaVersion: 1, complete: false, papers: [], labels: [], links: [] });
  const shapes = [];
  const registeredReads = await readRegistry(config);
  const observer = observeReadResponses(session.page, (payload, meta) => {
    mergeCatalog(catalog, normalizeCatalogPayload(payload, meta));
    if (meta.replayUrl) registeredReads.add(meta.replayUrl);
    if (command === 'inspect') shapes.push({ url: meta.url, subject: meta.subject, fields: fieldShapes(payload) });
  });
  try {
    await navigate(session.page, config.entryUrl, config);
    if (values.url) await navigate(session.page, values.url, config);
    console.log(command === 'login' ? '请在专用浏览器窗口完成粉笔短信登录，账号信息不会写入报告。' : '请在窗口进入需要核对的分类或试卷；采集模式会拦截写操作。');
    await pause(command === 'login' ? '登录成功并进入题库目录后返回终端。' : '完成分类浏览或打开需要采集的题目后返回终端。', values);
    await observer.flush();
    const dom = await captureDom(session.page, command === 'inspect' ? config.contentSelector : null);
    catalog.links = [...new Map([...catalog.links, ...dom.links].map(x => [x.url, x])).values()];
    catalog.observedAt = new Date().toISOString(); catalog.complete = false;
    // Match only actually observed links; never synthesize private SPA routes from IDs.
    for (const paper of catalog.papers) {
      const link = catalog.links.find(x => x.text === paper.title);
      if (link) paper.url = link.url;
    }
    await writeJson(catalogPath, catalog);
    await saveRegistry(config, registeredReads);
    const receipt = { command, capturedAt: new Date().toISOString(), auth: session.auth,
      observed: { papers: catalog.papers.length, labels: catalog.labels.length }, network: observer.stats, guard: session.guardStats,
      scopeComplete: false, page: { url: dom.url, title: dom.title, blocked: dom.blocked } };
    if (command === 'inspect') {
      await writeJson(path.join(WORK, 'inspect.json'), { ...receipt, responseShapes: shapes, contentHtml: sanitizeHtml(dom.html).html, images: dom.images });
      console.log('已保存字段结构与配置选定的题目容器；不会保存原始响应、请求头或账号资料。');
    }
    await writeJson(path.join(WORK, `${command}-receipt.json`), receipt);
    console.log(JSON.stringify(receipt, null, 2));
    if (command === 'login' && session.auth.status !== 'authenticated') {
      console.log('登录尚未由认证请求确认。请检查是否进入正常题库入口，不能仅凭登录按钮判断。');
      process.exitCode = 2;
    }
  } finally { observer.stop(); await observer.flush(); await session.close(); }
}

function countOption(value, name) {
  if (value === undefined) return null;
  const count = Number(value);
  if (!Number.isInteger(count) || count < (name === 'materials' ? 0 : 1)) throw new Error(`Invalid ${name} total`);
  return count;
}

async function addJob(values) {
  const identity = Object.fromEntries(['id', 'title', 'subject', 'area', 'variant'].map(key => [key, values[key]]));
  identity.year = Number(values.year);
  if (Object.values(identity).some(x => x === undefined || x === '' || x === null) ||
      !['xingce', 'shenlun'].includes(identity.subject) || !Number.isInteger(identity.year) || identity.year < 2016 || identity.year > new Date().getFullYear()) throw new Error('Provide a complete observed paper identity');
  const job = { identity, url: publicUrl(values.url),
    expected: { questions: countOption(values.questions, 'questions'), materials: countOption(values.materials, 'materials'), questionNumbers: null, materialIds: null },
    expectedBasis: 'operator_verified_source', reason: 'explicit_target', status: 'ready' };
  const planPath = path.join(WORK, 'plan.json');
  const plan = await readJson(planPath, { schemaVersion: 1, generatedAt: new Date().toISOString(), jobs: [], excluded: [] });
  const key = jobKey(job);
  const old = plan.jobs.find(x => jobKey(x) === key);
  if (old) throw new Error('Job already exists; review and edit the local plan instead of overwriting it');
  plan.jobs.push(job); await writeJson(planPath, plan);
  console.log(JSON.stringify({ job: key, status: job.status, identity }, null, 2));
}

async function getJobs(values) {
  const plan = await readJson(path.join(WORK, 'plan.json'));
  const jobs = plan.jobs.filter(job => values.all ? job.status === 'ready' : jobKey(job) === values.job || String(job.identity.id) === values.job);
  if (!jobs.length) throw new Error('No matching ready job. Run plan/add and inspect work/fenbi/plan.json');
  if (!values.all && jobs.length !== 1) throw new Error('Ambiguous source ID; use the printed unique job key');
  return jobs;
}

async function captureJob(session, job, config, values) {
  if (!job.url || job.status !== 'ready') throw new Error('Job needs an observed paper URL and reviewed identity');
  const configFingerprint = digest({ contentSelector: config.contentSelector, nextQuestionSelector: config.nextQuestionSelector,
    explanationSelector: config.explanationSelector, fieldMap: config.fieldMap });
  const resumed = !values.force && await resumeBundle(WORK, job, configFingerprint, validateDocument);
  if (resumed) { console.log(`${jobKey(job)}: verified complete checkpoint, skipped`); return; }
  const directory = safeChild(WORK, `papers/${jobKey(job)}`);
  await fs.mkdir(directory, { recursive: true });
  const runId = `${Date.now()}-${process.pid}`;
  const document = createDocument(job.identity, { url: publicUrl(job.url), capturedAt: new Date().toISOString() });
  Object.assign(document.expected, job.expected);
  document.evidence.push({ type: 'expected-counts-basis', basis: job.expectedBasis, expected: job.expected });
  const shapes = [];
  const registeredReads = await readRegistry(config);
  const accept = (payload, meta) => {
    if (meta.subject !== job.identity.subject) return;
    absorbPayload(document, payload, { ...meta, fieldMap: config.fieldMap });
    shapes.push({ url: meta.url, fields: fieldShapes(payload) });
    if (meta.replayUrl) registeredReads.add(meta.replayUrl);
  };
  const observer = observeReadResponses(session.page, accept);
  let failure = null;
  try {
    await navigate(session.page, job.url, config);
    if (values.manual) await pause('请进入本卷完整题目或解析页面，避免开始新练习、交卷或购买。', values);
    await observer.flush();
    const replay = await replayReads(session.context, job.readUrls || [], [...registeredReads], accept, { delayMs: config.delayMs });
    document.evidence.push(...replay.map(item => ({ type: 'observed-read-replay', ...item })));
    for (const item of replay) if (item.outcome !== 'accepted') document.conflicts.push({ scope: 'replay', url: item.url, outcome: item.outcome });
    const seen = new Set();
    for (let index = 0; index < config.maxPages; index++) {
      await observer.flush();
      if (config.explanationSelector) {
        const explain = session.page.locator(config.explanationSelector);
        if (await explain.count() === 1 && await explain.isVisible()) { await explain.click(); await sleep(config.delayMs); await observer.flush(); }
      }
      const dom = await captureDom(session.page, config.contentSelector);
      if (dom.blocked && !['content_selector_required', 'selector_not_found'].includes(dom.blocked.reason)) {
        document.evidence.push({ type: 'blocked', reason: dom.blocked.reason }); break;
      }
      const fingerprint = digest({ html: dom.html, questions: document.questions, materials: document.materials });
      if (seen.has(fingerprint)) { document.evidence.push({ type: 'pagination-stalled', page: index + 1 }); break; }
      seen.add(fingerprint);
      if (dom.html) {
        // DOM is evidence, not a guessed question parser. Map real JSON fields first.
        const cleaned = sanitizeHtml(dom.html);
        if (cleaned.rejected) document.conflicts.push({ scope: 'privacy', field: 'dom-references', rejectedReferences: cleaned.rejected });
        await writeJson(path.join(directory, `dom-${runId}-${index + 1}.json`), { source: dom.url, contentHtml: cleaned.html });
      }
      if (!config.nextQuestionSelector) break;
      const next = session.page.locator(config.nextQuestionSelector);
      if (await next.count() !== 1 || !await next.isVisible() || !await next.isEnabled()) break;
      if (index === config.maxPages - 1) { document.evidence.push({ type: 'page-limit-reached', limit: config.maxPages }); break; }
      await next.click(); await sleep(config.delayMs + config.settleMs);
    }
    await observer.flush();
  } catch (error) {
    failure = error.code || error.name || 'capture_failed';
    document.evidence.push({ type: 'capture-failed', reason: failure });
  } finally { observer.stop(); await observer.flush(); }
  await saveRegistry(config, registeredReads);
  if (observer.stats.unauthorized || session.auth.status === 'unauthenticated') document.evidence.push({ type: 'authentication-required', status: 401 });
  if (observer.stats.captcha) document.evidence.push({ type: 'captcha' });
  for (const key of ['oversized', 'failed', 'nonJson']) if (observer.stats[key]) document.conflicts.push({ scope: 'capture', field: key, count: observer.stats[key] });
  if (document.evidence.some(x => ['pagination-stalled', 'page-limit-reached', 'capture-failed'].includes(x.type))) document.conflicts.push({ scope: 'capture', field: 'incomplete-navigation' });
  document.assets = collectAssetUrls(document).map(url => ({ url, status: 'pending' }));
  try { await downloadAssets(session.page, document, path.join(directory, 'assets')); }
  catch { document.conflicts.push({ scope: 'capture', field: 'image-download-interrupted' }); }
  const verdict = await validateDocument(document, { assetRoot: path.join(directory, 'assets') });
  const documentFile = `document-${runId}.json`;
  await writeJson(path.join(directory, documentFile), document);
  await writeJson(path.join(directory, `validation-${runId}.json`), verdict);
  await writeJson(path.join(directory, `shapes-${runId}.json`), shapes);
  await writeJson(path.join(directory, 'checkpoint.json'), {
    schemaVersion: 1, status: verdict.status, configFingerprint, jobFingerprint: digest(job), documentFile,
    sha256: digest(await fs.readFile(path.join(directory, documentFile))), updatedAt: new Date().toISOString(),
    network: observer.stats, guard: session.guardStats, failure,
  });
  console.log(JSON.stringify({ job: jobKey(job), title: job.identity.title, status: verdict.status, observed: verdict.observed, issueCodes: verdict.issues.map(x => x.code) }, null, 2));
  if (verdict.status !== 'complete') process.exitCode = 2;
}

async function bundleCommand(command, job) {
  const directory = safeChild(WORK, `papers/${jobKey(job)}`);
  const checkpoint = await readJson(path.join(directory, 'checkpoint.json'));
  if (path.basename(checkpoint.documentFile || '') !== checkpoint.documentFile) throw new Error('Invalid checkpoint document path');
  const bytes = await fs.readFile(path.join(directory, checkpoint.documentFile));
  if (digest(bytes) !== checkpoint.sha256) throw new Error('Capture document changed after checkpoint');
  const document = JSON.parse(bytes.toString('utf8'));
  const verdict = await validateDocument(document, { assetRoot: path.join(directory, 'assets') });
  await writeJson(path.join(directory, 'validation-current.json'), verdict);
  if (command === 'export') {
    const destination = safeChild(WORK, `candidates/${jobKey(job)}-${Date.now()}`);
    await exportCandidate(document, verdict, directory, destination);
    console.log(`候选稿已导出：${destination}`);
  } else console.log(JSON.stringify(verdict, null, 2));
  if (verdict.status !== 'complete') process.exitCode = 2;
}

async function main() {
  const { values, positionals } = args(); const command = positionals[0];
  if (values.help || !command) { console.log(HELP); return; }
  await ensurePrivateWork();
  const defaultConfig = path.join(WORK, 'config.json');
  const configPath = values.config || (await fs.access(defaultConfig).then(() => defaultConfig).catch(() => null));
  const config = await loadConfig(configPath);
  if (command === 'init') {
    await fs.writeFile(defaultConfig, JSON.stringify(DEFAULTS, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    console.log(`本地配置已创建：${defaultConfig}`); return;
  }
  if (command === 'doctor') {
    const { chromium } = await import('playwright-core');
    let context;
    try {
      context = await chromium.launch({ headless: true, ...(config.executablePath ? { executablePath: config.executablePath } : config.channel !== 'chromium' ? { channel: config.channel } : {}) });
      console.log(JSON.stringify({ status: 'passed', node: process.version, channel: config.channel,
        browserVersion: context.version(), workDir: WORK, profileDir: config.profileDir, modelCalls: 0, cloudBrowserCalls: 0 }, null, 2));
    } finally { await context?.close(); }
    return;
  }
  if (command === 'plan') {
    const catalog = await readJson(path.join(WORK, 'catalog.json'));
    const inventory = parseInventory(await fs.readFile(path.join(REPO, 'catalog/manifest.jsonl'), 'utf8'));
    const plan = makePlan(catalog, inventory, config.scope, values);
    for (const job of plan.jobs) job.key = jobKey(job);
    const filename = path.join(WORK, `plan-${Date.now()}.json`);
    await writeJson(filename, plan);
    // Preserve any manually reviewed plan; the generated plan is always independently reviewable.
    try { await fs.writeFile(path.join(WORK, 'plan.json'), JSON.stringify(plan, null, 2) + '\n', { flag: 'wx' }); }
    catch (error) { if (error.code !== 'EEXIST') throw error; }
    console.log(JSON.stringify({ file: filename, jobs: plan.jobs.length, excluded: plan.excluded.length, catalogComplete: false }, null, 2)); return;
  }
  const release = await acquireLock(WORK);
  let session;
  try {
    if (command === 'add') return await addJob(values);
    if (['login', 'catalog', 'inspect'].includes(command)) return await browserCommand(command, config, values);
    if (['capture', 'validate', 'export'].includes(command)) {
      const jobs = await getJobs(values);
      if (command === 'capture') {
        session = await openSession(config, { mode: 'capture', headless: values.headless });
        await navigate(session.page, config.entryUrl, config);
        for (const job of jobs) { await captureJob(session, job, config, values); if (session.auth.status === 'unauthenticated') break; }
      } else for (const job of jobs) await bundleCommand(command, job);
      return;
    }
    throw new Error('Unknown command; use --help');
  } finally { try { await session?.close(); } finally { await release(); } }
}

main().catch(error => {
  // Playwright/network exceptions may embed URLs or page fragments. Do not dump raw errors.
  console.error(`Fenbi command failed (${error.code || error.name || 'ERROR'}).`);
  if (!(error.name || '').includes('Timeout') && !/https?:|cookie|token|password|authorization/i.test(error.message || '')) console.error(error.message);
  process.exitCode = 1;
});
