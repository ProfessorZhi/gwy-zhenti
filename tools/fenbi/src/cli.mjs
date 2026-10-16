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
import { makePlan, parseInventory, inferIdentity } from './plan.mjs';
import { exportCandidate } from './render.mjs';
import { observedReadUrl, replayReads } from './reads.mjs';
import { sanitizeHtml } from './privacy.mjs';
import { normalizeCatalogPayload, mergeCatalog } from './catalog.mjs';
import { parseFenbiExamDom } from './dom.mjs';
import { comparePaper, alignmentExitCode } from './align.mjs';
import { MAX_CONCURRENCY, clampConcurrency, createControl, createHostThrottle, createSerialQueue, runBounded } from './schedule.mjs';

const HELP = `Fenbi capture (local persistent Chrome/Edge; no model or cloud-browser calls)
  node src/cli.mjs init
  node src/cli.mjs doctor
  node src/cli.mjs login
  node src/cli.mjs catalog              # browse categories manually, then Enter
  node src/cli.mjs inspect --url URL    # discover observed JSON field shapes
  node src/cli.mjs plan [--all]         # compare observed catalog with repository
  node src/cli.mjs add --id ID --title TITLE --subject xingce|shenlun
      --area AREA --year YEAR --variant VARIANT --url OBSERVED_URL [--questions N]
  node src/cli.mjs capture --job KEY [--manual] [--force] [--headless] [--concurrency N]
  node src/cli.mjs capture --all        # ready URLs only, one browser session
                                        # N = pages inside that one session (1..3, default 1)
  node src/cli.mjs validate --job KEY
  node src/cli.mjs export --job KEY     # fresh candidate folder only
  node src/cli.mjs normalize-dom --document WORK_JSON
  node src/cli.mjs align --document WORK_JSON --paper REPO_PAPER_MD [--asset-root WORK_DIR]
Options: --config FILE, --wait-seconds N, --materials N
Private profile/data/output: <repository>/work/fenbi/
Unknown totals or unmapped fields remain partial. Nothing writes formal papers.
`;

function args() {
  return parseArgs({ allowPositionals: true, options: Object.fromEntries([
    ...['config', 'url', 'job', 'id', 'title', 'subject', 'area', 'year', 'variant', 'questions', 'materials', 'wait-seconds', 'document', 'paper', 'asset-root', 'concurrency'].map(x => [x, { type: 'string' }]),
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
  const urls = saved?.schemaVersion === 2 && saved.profileName === config.profileName && Array.isArray(saved.urls) ? saved.urls : [];
  const allowed = [];
  for (const value of urls) { try { allowed.push(observedReadUrl(value)); } catch { /* Retired account/unsupported routes are never replayed. */ } }
  return new Set(allowed);
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

/**
 * One paper, one dedicated page inside the single persistent context. `runtime` carries the pieces
 * the scheduler owns — the page this task is pinned to, the shared host throttle, the shared stop
 * flag and the shared serial write queue — so that nothing shared is mutated concurrently.
 */
async function captureJob(session, job, config, values, runtime = {}) {
  if (!job.url || job.status !== 'ready') throw new Error('Job needs an observed paper URL and reviewed identity');
  const page = runtime.page ?? session.page;
  const slot = runtime.slot ?? 0;
  const throttle = runtime.throttle ?? null;
  const control = runtime.control ?? null;
  const serialize = runtime.serialize ?? ((task) => task());
  const host = new URL(publicUrl(job.url)).hostname;
  const configFingerprint = digest({ contentSelector: config.contentSelector, nextQuestionSelector: config.nextQuestionSelector,
    explanationSelector: config.explanationSelector, fieldMap: config.fieldMap, domAdapter: config.domAdapter });
  const resumed = !values.force && await resumeBundle(WORK, job, configFingerprint, validateDocument);
  if (resumed) { console.log(`${jobKey(job)}: verified complete checkpoint, skipped`); return; }
  const directory = safeChild(WORK, `papers/${jobKey(job)}`);
  await fs.mkdir(directory, { recursive: true });
  const runId = `${Date.now()}-${process.pid}`;
  const document = createDocument(job.identity, { url: publicUrl(job.url), capturedAt: new Date().toISOString() });
  Object.assign(document.expected, job.expected);
  document.evidence.push({ type: 'expected-counts-basis', basis: job.expectedBasis, expected: job.expected });
  const shapes = [];
  // A shared registry is merged in memory (`Set.add` is atomic) and only ever written through the
  // serial queue, so two pages finishing together cannot lose each other's registrations.
  const registeredReads = runtime.registry ?? await readRegistry(config);
  const accept = (payload, meta) => {
    if (meta.subject !== job.identity.subject) return;
    if (!config.domAdapter) absorbPayload(document, payload, { ...meta, fieldMap: config.fieldMap });
    shapes.push({ url: meta.url, fields: fieldShapes(payload) });
    if (meta.replayUrl) registeredReads.add(meta.replayUrl);
  };
  const observer = observeReadResponses(page, accept);
  // Authentication loss, a captcha or a rate limit stops *new* work without killing what is in
  // flight. Nothing here retries past a block, changes profile, or looks for another route in.
  let seenRateLimits = 0;
  const observeSignals = () => {
    if (observer.stats.captcha) control?.stop('captcha');
    if (observer.stats.unauthorized || session.auth.status === 'unauthenticated') control?.stop('authentication-required');
    if (throttle && observer.stats.rateLimited > seenRateLimits) {
      seenRateLimits = observer.stats.rateLimited;
      throttle.penalize(host, 429);
      if (throttle.saturated()) control?.stop('rate-limited');
    }
  };
  let failure = null;
  try {
    if (throttle) await throttle.acquire(host);
    await navigate(page, job.url, config);
    if (values.manual) await pause('请进入本卷完整题目或解析页面，避免开始新练习、交卷或购买。', values);
    await observer.flush();
    observeSignals();
    const replay = await replayReads(session.context, job.readUrls || [], [...registeredReads], accept, { delayMs: config.delayMs });
    document.evidence.push(...replay.map(item => ({ type: 'observed-read-replay', ...item })));
    for (const item of replay) if (item.outcome !== 'accepted') document.conflicts.push({ scope: 'replay', url: item.url, outcome: item.outcome });
    const seen = new Set();
    for (let index = 0; index < config.maxPages; index++) {
      await observer.flush();
      observeSignals();
      if (config.explanationSelector) {
        const explain = page.locator(config.explanationSelector);
        if (await explain.count() === 1 && await explain.isVisible()) { await explain.click(); await sleep(config.delayMs); await observer.flush(); }
      }
      const dom = await captureDom(page, config.contentSelector);
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
        if (config.domAdapter === 'fenbi-xingce-v1') {
          const parsed = parseFenbiExamDom(cleaned.html, job.identity, { url: dom.url, capturedAt: new Date().toISOString() });
          document.identity.questionIdNamespace = parsed.identity.questionIdNamespace;
          document.source.url = parsed.source.url;
          for (const key of ['questions', 'materials']) {
            const expected = parsed.expected[key];
            if (expected !== null && document.expected[key] !== null && document.expected[key] !== expected) document.conflicts.push({ scope: 'expected', field: key, source: expected, previous: document.expected[key] });
            else if (expected !== null) document.expected[key] = expected;
          }
          document.chapters = parsed.chapters;
          document.evidence.push(...parsed.evidence);
          document.conflicts.push(...parsed.conflicts);
          absorbPayload(document, { questions: parsed.questions, materials: parsed.materials }, { url: dom.url });
          for (const question of parsed.questions) {
            const target = document.questions.find(item => item.id === question.id);
            if (target) target.materialIdsObserved = question.materialIdsObserved;
          }
        }
      }
      if (!config.nextQuestionSelector) break;
      const next = page.locator(config.nextQuestionSelector);
      if (await next.count() !== 1 || !await next.isVisible() || !await next.isEnabled()) break;
      if (index === config.maxPages - 1) { document.evidence.push({ type: 'page-limit-reached', limit: config.maxPages }); break; }
      await next.click(); await sleep(config.delayMs + config.settleMs);
    }
    await observer.flush();
  } catch (error) {
    failure = error.code || error.name || 'capture_failed';
    document.evidence.push({ type: 'capture-failed', reason: failure });
  } finally { observer.stop(); await observer.flush(); }
  observeSignals();
  await serialize(() => saveRegistry(config, registeredReads));
  if (observer.stats.unauthorized || session.auth.status === 'unauthenticated') document.evidence.push({ type: 'authentication-required', status: 401 });
  if (observer.stats.captcha) document.evidence.push({ type: 'captcha' });
  for (const key of ['oversized', 'failed', 'nonJson']) if (observer.stats[key]) document.conflicts.push({ scope: 'capture', field: key, count: observer.stats[key] });
  if (document.evidence.some(x => ['pagination-stalled', 'page-limit-reached', 'capture-failed'].includes(x.type))) document.conflicts.push({ scope: 'capture', field: 'incomplete-navigation' });
  document.assets = collectAssetUrls(document).map(url => ({ url, status: 'pending' }));
  try {
    // Coarse gate: one further same-host slot before the image burst starts.
    if (throttle) await throttle.acquire(host);
    await downloadAssets(page, document, path.join(directory, 'assets'));
  } catch { document.conflicts.push({ scope: 'capture', field: 'image-download-interrupted' }); }
  const verdict = await validateDocument(document, { assetRoot: path.join(directory, 'assets') });
  const documentFile = `document-${runId}.json`;
  await writeJson(path.join(directory, documentFile), document);
  await writeJson(path.join(directory, `validation-${runId}.json`), verdict);
  await writeJson(path.join(directory, `shapes-${runId}.json`), shapes);
  await writeJson(path.join(directory, 'checkpoint.json'), {
    schemaVersion: 1, status: verdict.status, configFingerprint, jobFingerprint: digest(job), documentFile,
    sha256: digest(await fs.readFile(path.join(directory, documentFile))), updatedAt: new Date().toISOString(),
    network: observer.stats, guard: session.guardStats, failure, pageSlot: slot,
  });
  // sourceId is stated explicitly so a concurrent run can be told apart per paper, not per slot.
  console.log(JSON.stringify({ job: jobKey(job), sourceId: job.identity.id, pageSlot: slot, title: job.identity.title,
    status: verdict.status, observed: verdict.observed, issueCodes: verdict.issues.map(x => x.code) }, null, 2));
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
  if (command === 'normalize-dom' || command === 'align') {
    const checkedPath = async (value, root) => {
      if (!value) throw new Error('A local input path is required');
      const absolute = await fs.realpath(path.resolve(REPO, value));
      const canonicalRoot = await fs.realpath(root);
      const relative = path.relative(canonicalRoot, absolute);
      if (!relative || relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error('Input path escapes its allowed directory');
      return absolute;
    };
    const filename = await checkedPath(values.document, WORK);
    const input = await readJson(filename);
    if (command === 'normalize-dom') {
      const inferred = inferIdentity({ id: values.id || input.sourcePaperId, title: values.title || input.sourceTitle, subject: values.subject || input.identity?.subject || 'xingce' });
      const identity = { ...(input.identity || inferred), ...(values.year ? { year: Number(values.year) } : {}), ...(values.area ? { area: values.area } : {}), ...(values.variant ? { variant: values.variant } : {}) };
      const html = input.html || input.contentHtml;
      if (!identity?.id || identity.id === 'undefined' || !html) throw new Error('DOM snapshot requires HTML and observed source identity/title metadata');
      const document = parseFenbiExamDom(html, identity, { url: publicUrl(values.url || input.sourceUrl || input.source?.url || input.page?.url), capturedAt: input.capturedAt || input.source?.capturedAt });
      const output = safeChild(WORK, `normalized-dom-${Date.now()}.json`);
      await writeJson(output, document);
      console.log(JSON.stringify({ status: 'normalized_unverified', output, questions: document.questions.length, materials: document.materials.length, expected: document.expected }, null, 2));
      return;
    }
    const paperPath = await checkedPath(values.paper, REPO);
    const relative = path.relative(REPO, paperPath).replaceAll('\\', '/');
    if (!/^(?:国考|省考)\/.+\.md$/u.test(relative)) throw new Error('Choose a formal repository examination Markdown file');
    const assetRoot = values['asset-root'] ? await checkedPath(values['asset-root'], WORK) : undefined;
    const report = await comparePaper(input, await fs.readFile(paperPath, 'utf8'), { repoRoot: REPO, paperPath, assetRoot });
    const output = safeChild(WORK, `alignment-${Date.now()}.json`);
    await writeJson(output, report);
    console.log(JSON.stringify({ output, verdict: report.verification.verdict, unverified: report.verification.unverified,
      notApplicable: report.verification.notApplicable, paper: report.paper, summary: report.summary }, null, 2));
    // 2 = 验收不完整. Anything short of a fully verified alignment must not exit 0.
    process.exitCode = alignmentExitCode(report);
    return;
  }
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
        // One profile, one persistent context, one owner process. Extra pages live *inside* that
        // context, so the read-only route guard, the cookie jar and the profile lock stay single.
        const concurrency = clampConcurrency(values.concurrency ?? config.concurrency);
        if (values.concurrency !== undefined && Number(values.concurrency) > MAX_CONCURRENCY) {
          console.log(`并发上限为 ${MAX_CONCURRENCY}，已收敛到 ${concurrency}。`);
        }
        const throttle = createHostThrottle({ minIntervalMs: config.delayMs });
        const control = createControl();
        const serialize = createSerialQueue();
        const registry = await readRegistry(config);
        // Slot 0 is the entry page; further slots are fresh pages from the same context.
        const pages = [session.page];
        for (let slot = 1; slot < concurrency; slot++) pages.push(await session.context.newPage());
        // A page the site opens by itself is never driven; it is recorded so an unobserved read
        // cannot be mistaken for part of a task's evidence.
        const strayPages = [];
        session.context.on('page', (opened) => { if (!pages.includes(opened)) strayPages.push(opened.url()); });
        const run = await runBounded(jobs, (job, { slot }) => captureJob(session, job, config, values,
          { page: pages[slot], slot, throttle, control, serialize, registry }), { concurrency, control });
        if (strayPages.length) console.log(JSON.stringify({ strayPages, note: '页面自行打开的标签页未被驱动，也未计入任何任务的证据' }, null, 2));
        console.log(JSON.stringify({ command: 'capture', concurrency: run.concurrency, completed: run.results.filter(r => r?.ok).length,
          failed: run.failures.length, skipped: run.skipped.length, stopped: run.stopped, reason: run.reason, throttle: throttle.state() }, null, 2));
        for (const failure of run.failures) console.log(`任务失败（不影响其它卷）：${failure.item?.identity?.id ?? failure.index} ${failure.error?.code ?? failure.error?.name ?? 'ERROR'}`);
        for (const index of run.skipped) console.log(`未启动（已停止）：${jobs[index]?.identity?.id ?? index}`);
        for (const page of pages.slice(1)) await page.close().catch(() => {});
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
