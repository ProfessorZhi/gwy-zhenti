// T2 资产补下载：只对 document.assets 中 pending/未下载的 URL 逐个 GET，
// 单请求串行且间隔 ≥2500ms；只读，不写站点。输出仅计数。
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const PAPERS = WORK + '/papers';
const GAP_MS = Number(process.env.ASSET_GAP_MS || 2500);
const MAX_BYTES = 12 * 1024 * 1024;

const { loadConfig } = await import(B + '/tools/fenbi/src/config.mjs');
const { collectAssetUrls } = await import(B + '/tools/fenbi/src/model.mjs');
const { isAllowedSourceUrl } = await import(B + '/tools/fenbi/src/browser.mjs');
const { validateDocument } = await import(B + '/tools/fenbi/src/validate.mjs');
const { chromium } = await import(B + '/tools/fenbi/node_modules/playwright-core/index.mjs');

const extOf = t => ({ 'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp', 'image/svg+xml': 'svg', 'image/avif': 'avif', 'image/bmp': 'bmp' })[t] || null;

// 找出需要补下载的卷
const targets = [];
for (const d of await fs.readdir(PAPERS)) {
  const p = path.join(PAPERS, d, 'document.json');
  let doc; try { doc = JSON.parse(await fs.readFile(p, 'utf8')); } catch { continue; }
  const known = new Map((doc.assets || []).map(a => [a.url, a]));
  const pending = collectAssetUrls(doc).filter(u => known.get(u)?.status !== 'downloaded');
  if (pending.length) targets.push({ d, p, doc, known, pending });
}
console.log(JSON.stringify({ papers: targets.length, pending: targets.reduce((a, t) => a + t.pending.length, 0) }));
if (!targets.length) { console.log(JSON.stringify({ requested: 0, downloaded: 0, skipped: 'nothing_pending' })); process.exit(0); }

const base = await loadConfig(path.join(WORK, 'config.json'));
const config = { ...base, workDir: WORK, profileDir: path.join(WORK, 'profiles', base.profileName) };
const lockPath = path.join(config.profileDir, '.fenbi-framework.lock');
const owner = `${process.pid}:${randomUUID()}`;
const stats = { requested: 0, downloaded: 0, unauthorized: 0, httpError: 0, failed: 0, rejected: 0, bytes: 0, risk: { s401: 0, s403: 0, s429_503: 0 } };
let ctx = null;
try {
  const lf = await fs.open(lockPath, 'wx'); await lf.writeFile(owner, 'utf8'); await lf.close();
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
  const req = ctx.request;

  for (const t of targets) {
    const assetDir = path.join(PAPERS, t.d, 'assets');
    await fs.mkdir(assetDir, { recursive: true });
    for (const url of t.pending) {
      stats.requested++;
      if (!isAllowedSourceUrl(url)) { t.known.set(url, { url, status: 'rejected_url' }); stats.rejected++; continue; }
      let res = null;
      try {
        await sleep(GAP_MS);
        res = await req.get(url, { maxRedirects: 0, timeout: 45000 });
        const st = res.status();
        // 401 means the session is gone: stop requesting at once. A 403 counts toward the hourly limit.
        if (st === 401) { stats.risk.s401++; t.known.set(url, { url, status: 'unauthorized' }); stats.unauthorized++; stats.stopReason = 'unauthorized'; break; }
        // A first 403/429/503 ends this asset batch so the parent can back off immediately.
        // The remaining assets stay pending; the next authorized cycle may retry them.
        if (st === 403) { stats.risk.s403++; t.known.set(url, { url, status: 'unauthorized' }); stats.unauthorized++; stats.stopReason = 'http403'; break; }
        if (st === 429 || st === 503) { stats.risk.s429_503++; t.known.set(url, { url, status: 'http_error' }); stats.httpError++; stats.stopReason = 'http429_or_503'; break; }
        if (st < 200 || st >= 300) { t.known.set(url, { url, status: 'http_error' }); stats.httpError++; continue; }
        const h = res.headers();
        const type = (h['content-type'] || '').split(';')[0].toLowerCase();
        const ext = extOf(type);
        if (!ext) { t.known.set(url, { url, status: 'not_image' }); stats.failed++; continue; }
        if (Number(h['content-length']) > MAX_BYTES) { t.known.set(url, { url, status: 'oversized' }); stats.failed++; continue; }
        const bytes = await res.body();
        if (bytes.length > MAX_BYTES) { t.known.set(url, { url, status: 'oversized' }); stats.failed++; continue; }
        const dim = await page.evaluate(async ({ encoded, mime }) => {
          const img = new Image(); img.src = `data:${mime};base64,${encoded}`; await img.decode();
          return { width: img.naturalWidth, height: img.naturalHeight };
        }, { encoded: bytes.toString('base64'), mime: type });
        const sha256 = createHash('sha256').update(bytes).digest('hex');
        const localPath = `${sha256}.${ext}`;
        await fs.writeFile(path.join(assetDir, localPath), bytes, { flag: 'wx' }).catch(e => { if (e.code !== 'EEXIST') throw e; });
        t.known.set(url, { url, localPath, sha256, bytes: bytes.length, ...dim, decoded: true, status: 'downloaded' });
        stats.downloaded++; stats.bytes += bytes.length;
      } catch { t.known.set(url, { url, status: 'download_failed' }); stats.failed++; }
      finally { if (res?.dispose) await res.dispose().catch(() => {}); }
    }
    const urls = collectAssetUrls(t.doc);
    const prevMap = new Map((t.doc.assets || []).map(a => [a.url, a]));
    for (const [u, a] of t.known) if (!urls.includes(u)) prevMap.delete(u);
    t.doc.assets = urls.map(u => t.known.get(u) || prevMap.get(u) || { url: u, status: 'pending' });
    const verdict = await validateDocument(t.doc, { assetRoot: assetDir });
    const tmp = t.p + '.tmp';
    await fs.writeFile(tmp, JSON.stringify(t.doc), { mode: 0o600 });
    await fs.rename(tmp, t.p);
    await fs.writeFile(path.join(PAPERS, t.d, 'validation.json'), JSON.stringify(verdict, null, 2) + '\n', { mode: 0o600 });
    const pend = t.doc.assets.filter(a => a.status !== 'downloaded').length;
    console.log(`${t.d} pending=${pend}/${t.doc.assets.length} verdict=${verdict.status}`);
    if (stats.stopReason) break;
  }
} catch (e) {
  stats.error = (e.code || e.name) + ' :: ' + String(e.message || e).slice(0, 160);
} finally {
  try { if (ctx) await ctx.close(); } catch {}
  try { if ((await fs.readFile(lockPath, 'utf8')) === owner) await fs.unlink(lockPath); } catch {}
}
stats.lockReleased = !(await fs.access(lockPath).then(() => true).catch(() => false));
console.log(JSON.stringify(stats));
