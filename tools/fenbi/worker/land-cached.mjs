#!/usr/bin/env node
// 一条命令把已交卷的缓存卷落盘进仓库（不开浏览器、不碰登录 Profile，可与采集服务同时运行）：
// 缓存 → 转换（A/C）→ 发布进集成工作树（粉笔为准覆盖同一卷）→ 提交 → 闸门 → 推集成分支 →（AUTO_MERGE=1 且闸门通过）推 main。
// 最后一行打印 JSON 回执，直接贴进回报。
//
//   FENBI_WORK_DIR=… INTEG_REPO=… RIGHTS_FILE=… PUSH=1 AUTO_MERGE=1 node worker/land-cached.mjs
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { landMany, publish } from './publish.mjs';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const INTEG = process.env.INTEG_REPO ? path.resolve(process.env.INTEG_REPO) : null;
const RIGHTS = process.env.RIGHTS_FILE || null;
const readJson = async (p, d = null) => { try { return JSON.parse(await fs.readFile(p, 'utf8')); } catch { return d; } };

export async function landCached({ work = WORK, repo = INTEG, rightsFile = RIGHTS, push = false, autoMerge = false } = {}) {
  const started = Date.now(), PAPERS = work + '/papers';
  const ledger = (await readJson(work + '/t2-20261019/ledger.json')) || { papers: {} };
  const names = (await fs.readdir(PAPERS).catch(() => [])).sort()
    .filter(k => ['complete', 'submitted_partial'].includes(ledger.papers[k]?.status));
  const r = await landMany({ papersDir: PAPERS, names, repo, rightsFile });
  const blocked = Object.fromEntries(Object.entries(r.promote?.blocked || {}).map(([k, v]) => [k, v.length]));
  const p = await publish({ repo, rightsFile, push, autoMerge,
    message: `integrate(fenbi): land cached ${new Date().toISOString().slice(0, 16)}Z` });
  return { papers: names.length, A: r.A, C: r.C, errors: r.errors, promoted: r.promote?.promoted ?? 0, blocked,
    committed: p.committed, pushedBranch: p.pushedBranch, pushedMain: p.pushedMain, error: p.error || null,
    gate: p.gate ? { ok: p.gate.ok, papers: p.gate.papers, reasons: p.gate.reasons.slice(0, 10) } : null,
    seconds: Math.round((Date.now() - started) / 1000) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!INTEG || !RIGHTS) { console.log(JSON.stringify({ error: 'INTEG_REPO and RIGHTS_FILE required' })); process.exit(1); }
  landCached({ push: process.env.PUSH === '1', autoMerge: process.env.AUTO_MERGE === '1' })
    .then(s => console.log(JSON.stringify(s)))
    .catch(e => { console.log(JSON.stringify({ error: String(e.stderr || e.message).slice(0, 300) })); process.exitCode = 1; });
}
