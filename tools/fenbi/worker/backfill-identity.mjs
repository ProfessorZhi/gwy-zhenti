#!/usr/bin/env node
// 行测身份证据回填（只读）。
//
// 行测练习页的 URL 里没有试卷 ID（…/ti/exam/exercise/1_1_3u8n015?routecs=xingce），
// 试卷 ID 只出现在页面加载的 /combine/exercise/getReport 响应 JSON（"paperId":75898）里。
// 早期批次没有把这条记成 source-paper-identity 证据，于是整批卡在 paper-binding-unverified，
// 答案与解析维度虽然 complete，却过不了落地闸门。
//
// 本脚本对已交卷的卷重新打开解析页（纯 GET：不建练习、不交卷、不点击），从 getReport 取 paperId，
// 一致时补证据并重校验。用法：
//   FENBI_WORK_DIR=... node worker/backfill-identity.mjs [--apply] [--limit=N]
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright-core';
import { collectPaperIds, bindingStatus } from './identity.mjs';
import { validateDocument } from '../src/validate.mjs';

const WORK = path.resolve(process.env.FENBI_WORK_DIR || '');
if (!WORK || !path.isAbsolute(WORK)) { console.error('需要 FENBI_WORK_DIR'); process.exit(1); }
const args = process.argv.slice(2);
const APPLY = args.includes('--apply');
const LIMIT = Number((args.find(a => a.startsWith('--limit=')) || '').split('=')[1] || 0);
const GAP_MS = Math.max(1200, Number(process.env.BACKFILL_GAP_MS || 1500));
const WAIT_MS = Number(process.env.BACKFILL_WAIT_MS || 5000);
const REPORT = path.join(WORK, 'backfill-identity.jsonl');

const readJson = async p => { try { return JSON.parse(await fs.readFile(p, 'utf8')); } catch { return null; } };
const writeJson = async (p, o) => { const t = p + '.tmp'; await fs.writeFile(t, JSON.stringify(o)); await fs.rename(t, p); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = o => fs.appendFile(REPORT, JSON.stringify({ at: new Date().toISOString(), ...o }) + '\n');

const base = await readJson(path.join(WORK, 'config.json'));
if (!base) { console.error('缺少 config.json'); process.exit(1); }
const profileDir = path.join(WORK, 'profiles', base.profileName);

// 候选：身份维度未 complete、行测、有页面地址、已交卷。
const papersDir = path.join(WORK, 'papers');
const targets = [];
for (const name of (await fs.readdir(papersDir)).sort()) {
  const dir = path.join(papersDir, name);
  const verdict = await readJson(path.join(dir, 'validation.json'));
  if (!verdict || verdict.dimensions?.identity?.status === 'complete') continue;
  const doc = await readJson(path.join(dir, 'document.json'));
  const run = await readJson(path.join(dir, 'run-summary.json'));
  if (!doc?.identity?.id || !run?.pageUrl || !/^https?:\/\//.test(run.pageUrl)) continue;
  if (String(doc.identity.subject) === 'shenlun') continue;
  targets.push({ name, dir, doc, run });
}
console.log(`待回填 ${targets.length} 卷${LIMIT ? `（上限 ${LIMIT}）` : ''}，apply=${APPLY}`);

const risk = { loginLost: 0, http403: 0, http429: 0 };
const stat = { verified: 0, unobserved: 0, mismatch: 0, complete: 0, partial: 0, error: 0 };
const ctx = await chromium.launchPersistentContext(profileDir, { headless: false, executablePath: base.executablePath,
  serviceWorkers: 'block', acceptDownloads: false, viewport: { width: 1440, height: 1000 } });
ctx.setDefaultTimeout(45000);
const page = await ctx.newPage();
let n = 0;
try {
  for (const target of targets) {
    if (LIMIT && n >= LIMIT) break;
    if (risk.loginLost || risk.http403 || risk.http429) { console.log('风控信号，停止'); break; }
    const sid = String(target.doc.identity.id);
    const ids = new Set();
    const onResponse = async response => {
      try {
        const status = response.status();
        if (status === 401) risk.loginLost++;
        else if (status === 403) risk.http403++;
        else if (status === 429 || status === 503) risk.http429++;
        if (!/json/i.test(response.headers()['content-type'] || '')) return;
        const body = (await response.body()).toString('utf8');
        if (!/paperId/.test(body)) return;
        for (const id of collectPaperIds(JSON.parse(body))) ids.add(id);
      } catch {}
    };
    ctx.on('response', onResponse);
    try {
      await page.goto(target.run.pageUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await sleep(WAIT_MS);
      const binding = bindingStatus(ids, sid);
      if (binding !== 'verified') { stat[binding === 'mismatch' ? 'mismatch' : 'unobserved']++; await log({ name: target.name, sid, binding, observed: [...ids] }); continue; }
      stat.verified++;
      target.doc.evidence = Array.isArray(target.doc.evidence) ? target.doc.evidence : [];
      if (!target.doc.evidence.some(e => e.type === 'source-paper-identity' && String(e.paperId) === sid)) {
        target.doc.evidence.push({ type: 'source-paper-identity', paperId: sid, observedAt: new Date().toISOString(),
          via: 'paperId in /combine/exercise/getReport JSON on the reopened analysis page (read-only backfill)' });
      }
      const verdict = await validateDocument(target.doc, { assetRoot: path.join(target.dir, 'assets') });
      verdict.status === 'complete' ? stat.complete++ : stat.partial++;
      if (APPLY) {
        await writeJson(path.join(target.dir, 'document.json'), target.doc);
        await writeJson(path.join(target.dir, 'validation.json'), verdict);
      }
      await log({ name: target.name, sid, binding, verdict: verdict.status,
        issues: [...new Set((verdict.issues || []).map(i => i.dimension + ':' + i.code))] });
    } catch (e) {
      stat.error++;
      await log({ name: target.name, sid, error: String(e.message || e).slice(0, 120) });
    } finally { ctx.off('response', onResponse); }
    n++;
    if (n % 20 === 0) console.log(`进度 ${n}/${targets.length}`, JSON.stringify(stat));
    await sleep(GAP_MS);
  }
} finally {
  await ctx.close();
  console.log('完成', JSON.stringify(stat), 'risk', JSON.stringify(risk), '报告', REPORT);
}
