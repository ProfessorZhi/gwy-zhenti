// 目录巡检（只读、有界）：按真实地区标签页 + footer.question-list-pager/.houpage 翻页，
// 采集每个地区的 sourceId/year/标题与行级会员标记；不点进试卷、不创建练习、不交卷。
// 环境：REGIONS="山东,河南" （必填，逗号分隔，取 span.categories-item 文本）
//       DISCOVERY_OUT=<目录>（默认 work/fenbi/catalog-live-20261019）
//       MAX_PAGES_PER_REGION=8
// 风控：验证码/401/403/429/503 立即写 STOP 并停止。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';

const B = process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const WORK = B + '/work/fenbi';
const OUT = process.env.DISCOVERY_OUT || WORK + '/catalog-live-20261019';
const ENTRY = 'https://www.fenbi.com/spa/tiku/guide/realTest/xingce/xingce';
const GAP = 2500;
const STOP = WORK + '/STOP';
const REGIONS = (process.env.REGIONS || '').split(',').map(s => s.trim()).filter(Boolean);
const MAX_PAGES = Number(process.env.MAX_PAGES_PER_REGION || 8);
if (!REGIONS.length) { console.log(JSON.stringify({ ok: false, code: 'NO_REGIONS' })); process.exit(2); }

const { loadConfig } = await import(B + '/tools/fenbi/src/config.mjs');
const { observeReadResponses } = await import(B + '/tools/fenbi/src/browser.mjs');
const { normalizeCatalogPayload } = await import(B + '/tools/fenbi/src/catalog.mjs');
const { chromium } = await import(B + '/tools/fenbi/node_modules/playwright-core/index.mjs');

const base = await loadConfig(path.join(WORK, 'config.json'));
const config = { ...base, workDir: WORK, profileDir: path.join(WORK, 'profiles', base.profileName) };
await fs.mkdir(OUT, { recursive: true, mode: 0o700 });
const lockPath = path.join(config.profileDir, '.fenbi-framework.lock');
const owner = `${process.pid}:${randomUUID()}`;
try { const lf = await fs.open(lockPath, 'wx'); await lf.writeFile(owner, 'utf8'); await lf.close(); }
catch { console.log(JSON.stringify({ ok: false, code: 'PROFILE_LOCKED' })); process.exit(0); }

const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
let ctx, observer, last = 0, bucket = [];
const throttle = async () => { const w = GAP - (Date.now() - last); if (w > 0) await sleep(w); last = Date.now(); };
const out = { schemaVersion: 1, at: new Date().toISOString(), throttleMs: GAP, regions: {}, entries: [],
  risk: { captcha: 0, unauthorized: 0, rateLimited: 0, stopWritten: false }, lockReleased: false };

// 绑定：API entry ↔ 目录行（标题前缀优先；等长时按序回退），只用于读会员/锁定标记
function bindRows(rows, entries) {
  const used = new Set(), outRows = [];
  entries.forEach((e, i) => {
    const t = norm(e.title);
    let idx = rows.findIndex((r, j) => !used.has(j) && r.text.startsWith(t));
    if (idx < 0) idx = rows.findIndex((r, j) => !used.has(j) && r.text.includes(t));
    if (idx < 0 && rows.length === entries.length && !used.has(i)) idx = i;
    if (idx >= 0) used.add(idx);
    outRows.push({ ...e, rowMatched: idx >= 0, member: idx >= 0 ? rows[idx].member : null,
      locked: idx >= 0 ? rows[idx].locked : null });
  });
  return outRows;
}

try {
  ctx = await chromium.launchPersistentContext(config.profileDir, {
    headless: false, executablePath: config.executablePath,
    serviceWorkers: 'block', acceptDownloads: false, viewport: { width: 1440, height: 1000 },
  });
  ctx.setDefaultTimeout(45000);
  await ctx.route('**/*', async route => {
    const m = route.request().method().toUpperCase();
    if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') return route.continue();
    return route.abort('blockedbyclient');
  });
  const page = await ctx.newPage();
  observer = observeReadResponses(page, (payload, meta) => {
    const n = normalizeCatalogPayload(payload, meta);
    for (const p of n.papers || []) bucket.push({ id: String(p.id), title: p.title, year: p.year ?? null });
  });

  await throttle();
  await page.goto(ENTRY, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await sleep(3500);
  await observer.flush();

  for (const region of REGIONS) {
    try { await fs.access(STOP); out.risk.stopWritten = true; break; } catch {}
    const rec = { status: 'observed', pages: [], entries: [], total: null, rows: 0, memberRows: 0, boundary: 0 };
    const tab = page.locator('span.categories-item', { hasText: region }).first();
    if (!await tab.count()) { rec.status = 'label-not-found'; out.regions[region] = rec; continue; }
    bucket = [];
    await throttle();
    await tab.click().catch(() => {});
    await sleep(3500);
    await observer.flush();

    const total = Number(await page.evaluate(() => ((document.body.innerText || '').match(/共\s*(\d+)\s*[套题卷]/) || [])[1] || 0));
    rec.total = total || null;
    const maxPages = total ? Math.min(MAX_PAGES, Math.ceil(total / 15) + 1) : MAX_PAGES;
    const seen = new Set();
    for (let pg = 1; pg <= maxPages; pg++) {
      const snap = await page.evaluate(() => {
        const rows = [...document.querySelectorAll('div.paper-item')].map(el => {
          const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
          const cls = [el, ...el.querySelectorAll('*')].map(x => String(x.className || '')).join(' ');
          return { text: t, member: /会员|VIP|付费|购买|开通|试看|解锁|专享/.test(t), locked: /vip|member|pay|lock/i.test(cls) };
        });
        const pager = document.querySelector('footer.question-list-pager');
        return { rows, pagerActive: pager ? (pager.innerText || '').replace(/\s+/g, ' ').trim() : null };
      });
      const entries = [...new Map(bucket.map(e => [e.id, e])).values()].filter(e => !seen.has(e.id));
      for (const e of entries) seen.add(e.id);
      const bound = bindRows(snap.rows, entries);
      rec.pages.push({ page: pg, rows: snap.rows.length, entries: entries.length,
        memberRows: snap.rows.filter(r => r.member).length, pager: snap.pagerActive });
      rec.entries.push(...bound.map(b => ({ id: b.id, title: b.title, year: b.year, page: pg,
        rowMatched: b.rowMatched, member: b.member, locked: b.locked })));
      rec.rows += snap.rows.length;
      rec.memberRows += snap.rows.filter(r => r.member).length;
      if (!entries.length && !snap.rows.length) break;
      if (total && rec.rows >= total) break;
      const next = page.locator('footer.question-list-pager .houpage').first();
      if (!await next.count()) break;
      const disabled = await next.evaluate(e => !e.offsetParent || /disabled/i.test(String(e.className || ''))).catch(() => true);
      if (disabled) break;
      bucket = [];
      await throttle();
      await next.click({ timeout: 10000 }).catch(() => {});
      await sleep(3500);
      await observer.flush();
    }
    rec.entries = [...new Map(rec.entries.map(e => [e.id, e])).values()];
    rec.boundary = rec.entries.filter(e => !e.rowMatched).length;
    // 有界覆盖：显式记录是否因页数上限/翻页失败而未取全，不把部分覆盖当全量。
    rec.expectedPages = total ? Math.ceil(total / 15) : null;
    rec.pageLimit = rec.expectedPages ? Math.min(MAX_PAGES, rec.expectedPages) : MAX_PAGES;
    rec.pageLimitApplied = !!(rec.expectedPages && rec.expectedPages > MAX_PAGES);
    rec.coverage = total ? (rec.rows >= total ? 'full' : 'partial') : 'unknown';
    out.regions[region] = rec;
    out.entries.push(...rec.entries.map(e => ({ ...e, region })));
    const stats = observer.stats;
    out.risk.captcha = stats.captcha; out.risk.unauthorized = stats.unauthorized; out.risk.rateLimited = stats.rateLimited;
    console.log(`${region} total=${rec.total} rows=${rec.rows} entries=${rec.entries.length} memberRows=${rec.memberRows} unbound=${rec.boundary} pages=${rec.pages.length} coverage=${rec.coverage}${rec.pageLimitApplied ? ' page-limit-applied' : ''}`);
    if (stats.captcha || stats.unauthorized || stats.rateLimited) {
      await fs.writeFile(STOP, JSON.stringify({ at: new Date().toISOString(), by: 'p0-discover-regions', region,
        risk: { captcha: stats.captcha, unauthorized: stats.unauthorized, rateLimited: stats.rateLimited } }) + '\n', { mode: 0o600 });
      out.risk.stopWritten = true;
      break;
    }
  }
} catch (e) {
  out.error = (e.code || e.name) + ' :: ' + String(e.message || e).slice(0, 160);
} finally {
  try { observer?.stop(); } catch {} try { await observer?.flush(); } catch {}
  try { if (ctx) await ctx.close(); } catch {}
  try { if ((await fs.readFile(lockPath, 'utf8')) === owner) await fs.unlink(lockPath); } catch {}
}
out.lockReleased = !(await fs.access(lockPath).then(() => true).catch(() => false));
await fs.writeFile(path.join(OUT, 'catalog-' + REGIONS[0] + '-' + REGIONS[REGIONS.length - 1] + '.json'), JSON.stringify(out, null, 2) + '\n', { mode: 0o600 });
console.log(JSON.stringify({ ok: !out.error, error: out.error || null, regions: Object.fromEntries(Object.entries(out.regions).map(([k, v]) => [k, { total: v.total, rows: v.rows, entries: v.entries.length, memberRows: v.memberRows, unbound: v.boundary, coverage: v.coverage, pageLimitApplied: v.pageLimitApplied }])), risk: out.risk, lockReleased: out.lockReleased }));
