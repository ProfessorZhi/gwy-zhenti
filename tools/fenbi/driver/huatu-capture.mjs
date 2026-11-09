// 华图解析页整卷抓取：在专用浏览器配置中打开解析页，监听页面自己发出的数据请求，
// 把 JSON 响应体与图片原样落到 work/huatu/<paperId>/raw/，供转换为 paper.json。
//
// 用法（在 tools/fenbi 目录下）：
//   首次登录：node driver/huatu-capture.mjs --login
//             在弹出的浏览器里登录华图，完成后回到终端按回车。登录状态保存在 work/profiles/huatu-main/。
//   抓取一卷：node driver/huatu-capture.mjs --paper-id 4056552 --url "<解析页地址>"
//
//   连接自己启动的 Chrome：用调试端口和单独的配置目录启动 Chrome，在这个窗口里照常手动登录华图，
//   再让脚本连上它抓取：
//     "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=D:\huatu-chrome
//     node driver/huatu-capture.mjs --cdp http://127.0.0.1:9222 --paper-id 4056552 --url "<解析页地址>"
//   Chrome 136 起不允许在默认配置上开调试端口，所以 --user-data-dir 须是单独目录；登录一次后长期复用。
//   脚本只新开一个标签页抓取，结束时关闭该标签页并断开连接，不关闭你的浏览器。
//
// 设计要点：
// - 监听器在打开页面之前注册，并挂在整个浏览器上下文，页面跳转、刷新不会丢事件。
// - 只保存响应体，不保存任何请求头或响应头；记录的 JSON 地址去掉查询参数，避免带出令牌。
// - 不登录、不提交、不点击：只打开给定地址、滚动到底触发懒加载，然后等待网络空闲。
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import readline from 'node:readline/promises';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const WORK = path.join(REPO, 'work');
const QUESTION_HINTS = ['stem', 'content', 'question', 'option', 'choice', 'answer', 'analysis', 'material', 'questionList', 'resolve'];

export function args(argv) {
  const out = { profile: 'huatu-main', wait: 20, login: false };
  for (let i = 0; i < argv.length; i += 1) {
    const k = argv[i];
    if (k === '--login') out.login = true;
    else if (k === '--paper-id') out.paperId = argv[++i];
    else if (k === '--url') out.url = argv[++i];
    else if (k === '--profile') out.profile = argv[++i];
    else if (k === '--wait') out.wait = Number(argv[++i]);
    else if (k === '--executable') out.executable = argv[++i];
    else if (k === '--headless') out.headless = true;
    else if (k === '--cdp') out.cdp = argv[++i];
    else throw new Error(`未知参数 ${k}`);
  }
  if (!out.login && (!/^[A-Za-z0-9_-]+$/.test(out.paperId ?? '') || !out.url)) throw new Error('需要 --paper-id <字母数字编号> 与 --url <解析页地址>，或 --login');
  if (out.cdp && !/^https?:\/\/(127\.0\.0\.1|localhost):\d+\/?$/.test(out.cdp)) throw new Error('--cdp 只接受本机地址，如 http://127.0.0.1:9222');
  if (out.login && out.cdp) throw new Error('--cdp 模式请直接在自己启动的 Chrome 里登录，不需要 --login');
  if (!/^[\w-]+$/.test(out.profile)) throw new Error('--profile 只能含字母、数字、下划线和连字符');
  return out;
}

/** 记录用的地址：去掉查询参数和片段，避免把令牌写进文件。 */
export function bareUrl(raw) {
  const u = new URL(raw);
  return `${u.origin}${u.pathname}`;
}

/** 粗略判断一个 JSON 是否像题目数据：统计含题目关键词的键。 */
export function questionScore(value) {
  let score = 0;
  const walk = (v, depth) => {
    if (depth > 8 || v === null || typeof v !== 'object') return;
    for (const [k, child] of Object.entries(v)) {
      const key = k.toLowerCase();
      if (QUESTION_HINTS.some((h) => key.includes(h.toLowerCase()))) score += 1;
      walk(child, depth + 1);
    }
  };
  walk(value, 0);
  return score;
}

function slug(text) {
  return text.replace(/^https?:\/\//, '').replace(/[^\w.-]+/g, '_').slice(0, 80);
}

/** 返回 { ctx, done }：done() 结束时调用。--cdp 时连接用户自己启动的 Chrome，只断开不关闭。 */
async function open(opts) {
  const { chromium } = await import('playwright-core');
  if (opts.cdp) {
    const browser = await chromium.connectOverCDP(opts.cdp);
    const ctx = browser.contexts()[0];
    if (!ctx) throw new Error('连上了 Chrome，但没有可用的浏览器窗口');
    return { ctx, done: async (page) => { await page?.close().catch(() => {}); await browser.close(); } };
  }
  const ctx = await launch(opts);
  return { ctx, done: async () => { await ctx.close(); } };
}

async function launch(opts) {
  const { chromium } = await import('playwright-core');
  const profileDir = path.join(WORK, 'profiles', opts.profile);
  await mkdir(profileDir, { recursive: true });
  return chromium.launchPersistentContext(profileDir, {
    headless: Boolean(opts.headless),
    ...(opts.executable ? { executablePath: opts.executable } : { channel: 'chrome' }),
    serviceWorkers: 'block',
    acceptDownloads: false,
    viewport: { width: 1440, height: 1000 },
  });
}

async function login(opts) {
  const ctx = await launch(opts);
  const page = ctx.pages()[0] ?? await ctx.newPage();
  await page.goto('https://www.huatu.com/', { waitUntil: 'domcontentloaded' }).catch(() => {});
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  await rl.question('请在浏览器中登录华图，完成后回到这里按回车（不要把密码或验证码发给任何人）…');
  rl.close();
  await ctx.close();
  console.log(`登录状态已保存到 work/profiles/${opts.profile}/`);
}

async function capture(opts) {
  const dir = path.join(WORK, 'huatu', opts.paperId, 'raw');
  await mkdir(path.join(dir, 'images'), { recursive: true });
  const { ctx, done } = await open(opts);
  const index = [];
  const images = [];
  const pending = new Set();
  let seq = 0;
  ctx.on('response', (response) => {
    const job = (async () => {
      const req = response.request();
      const type = req.resourceType();
      const ctype = (await response.headerValue('content-type').catch(() => null)) ?? '';
      if (response.status() !== 200) return;
      if (type === 'image') {
        const body = await response.body().catch(() => null);
        if (!body) return;
        const fromPath = path.extname(new URL(response.url()).pathname).slice(1).toLowerCase();
        const fromType = ctype.startsWith('image/') ? ctype.slice(6).split(/[;+]/)[0] : '';
        const ext = (fromType || fromPath || 'bin').replace('jpeg', 'jpg');
        const file = `images/${createHash('sha1').update(response.url()).digest('hex').slice(0, 16)}.${ext}`;
        await writeFile(path.join(dir, file), body);
        images.push({ url: response.url(), file });
        return;
      }
      // xhr/fetch 不看 content-type（有的接口返回 octet-stream），能解析成 JSON 就保存；脚本只收 JSONP。
      if (!(['xhr', 'fetch'].includes(type) || (type === 'script' && /javascript|json/.test(ctype)))) return;
      const text = await response.text().catch(() => null);
      if (!text) return;
      let data;
      try { data = JSON.parse(text.trim().replace(/^[\w$.]+\(([\s\S]*)\);?$/, '$1')); } catch { return; }
      seq += 1;
      const file = `${String(seq).padStart(3, '0')}-${slug(bareUrl(response.url()))}.json`;
      await writeFile(path.join(dir, file), JSON.stringify(data, null, 2));
      index.push({ seq, file, url: bareUrl(response.url()), method: req.method(), bytes: text.length, score: questionScore(data) });
    })();
    pending.add(job);
    job.finally(() => pending.delete(job));
  });
  const page = await ctx.newPage();
  await page.goto(opts.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  // 逐屏滚动到底，触发懒加载的题目与图片。
  for (let i = 0; i < 200; i += 1) {
    const done = await page.evaluate(() => {
      window.scrollBy(0, window.innerHeight * 0.9);
      return window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 4;
    });
    await page.waitForTimeout(400);
    if (done) break;
  }
  await page.waitForTimeout(opts.wait * 1000);
  await Promise.allSettled([...pending]);
  const html = await page.content();
  await writeFile(path.join(dir, 'page.html'), html);
  await done(page);
  await writeFile(path.join(dir, 'index.json'), JSON.stringify({ paperId: opts.paperId, url: bareUrl(opts.url),
    capturedAt: new Date().toISOString(), responses: index, images }, null, 2));
  const top = [...index].sort((a, b) => b.score - a.score).slice(0, 5);
  console.log(`已保存 ${index.length} 个 JSON 响应、${images.length} 张图片到 work/huatu/${opts.paperId}/raw/`);
  console.log('最像题目数据的响应（score 越高越像）：');
  for (const r of top) console.log(`  ${r.file}  score=${r.score}  bytes=${r.bytes}  ${r.method} ${r.url}`);
  if (!top.length || top[0].score === 0) console.log('没有识别到题目数据：确认地址是解析页且已登录（先运行 --login）。');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const opts = args(process.argv.slice(2));
  await (opts.login ? login(opts) : capture(opts));
}
