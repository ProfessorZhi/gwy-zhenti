#!/usr/bin/env node
/**
 * Wall-clock pipeline board: real papers per hour (idle time included), idle gaps between
 * captures, answer coverage, A/C, promotion and stop state. Reads only local metadata
 * (checkpoint/receipt/document identity and answer presence); writes BOARD.md and board.json.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const HOUR = 3600e3, IDLE_GAP_MS = 120e3;
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const readJson = f => fs.readFile(f, 'utf8').then(JSON.parse).catch(() => null);
const dirs = async root => (await fs.readdir(root, { withFileTypes: true }).catch(() => [])).filter(e => e.isDirectory()).map(e => e.name);
const text = h => String(h ?? '').replace(/<[^>]*>/g, '').trim();

export function speed(timestamps, now) {
  const t = timestamps.filter(Number.isFinite).sort((a, b) => a - b);
  const lastHour = t.filter(x => x > now - HOUR).length;
  const gaps = t.slice(1).map((x, i) => x - t[i]);
  const idle = gaps.filter(g => g > IDLE_GAP_MS);
  const busy = gaps.filter(g => g <= IDLE_GAP_MS);
  const hourly = {};
  for (const x of t.filter(x => x > now - 24 * HOUR)) {
    const key = new Date(Math.floor(x / HOUR) * HOUR).toISOString().slice(0, 13);
    hourly[key] = (hourly[key] || 0) + 1;
  }
  return {
    captured: t.length, lastHourPapers: lastHour,
    lastCaptureMinutesAgo: t.length ? Math.round((now - t.at(-1)) / 60e3) : null,
    activeSecondsPerPaper: busy.length ? Math.round(busy.reduce((a, b) => a + b, 0) / busy.length / 1000) : null,
    idleGaps: idle.length, idleMinutesTotal: Math.round(idle.reduce((a, b) => a + b, 0) / 60e3),
    hourly,
  };
}

export async function buildBoard({ workDir, repoRoot, now = Date.now() }) {
  const papersRoot = path.join(workDir, 'papers'), ingestRoot = path.join(workDir, 'batch-ingest');
  const times = [], regions = {};
  let questions = 0, answered = 0;
  for (const name of await dirs(papersRoot)) {
    const cp = await readJson(path.join(papersRoot, name, 'checkpoint.json'));
    if (cp?.updatedAt) times.push(Date.parse(cp.updatedAt));
    const doc = await readJson(path.join(papersRoot, name, 'document.json')) ||
      (cp?.documentFile ? await readJson(path.join(papersRoot, name, cp.documentFile)) : null);
    const area = doc?.identity?.area || 'unknown';
    const r = regions[area] ||= { captured: 0, withAnswers: 0, A: 0, C: 0, promoted: 0 };
    r.captured++;
    const qs = doc?.questions || [];
    questions += qs.length;
    const a = qs.filter(q => text(q.answerHtml)).length;
    answered += a;
    if (qs.length && a === qs.length) r.withAnswers++;
  }
  let A = 0, C = 0, promoted = 0;
  for (const name of await dirs(ingestRoot)) {
    const rc = await readJson(path.join(ingestRoot, name, 'receipt.json'));
    if (!rc) continue;
    const r = regions[rc.area] ||= { captured: 0, withAnswers: 0, A: 0, C: 0, promoted: 0 };
    if (rc.grade === 'A') { A++; r.A++; } else { C++; r.C++; }
    const cur = rc.path ? await fs.readFile(path.join(repoRoot, rc.path)).catch(() => null) : null;
    if (cur && sha(cur) === rc.markdownSha256) { promoted++; r.promoted++; }
  }
  const stop = await fs.readFile(path.join(workDir, 'STOP'), 'utf8').then(() => true).catch(() => false);
  return { generatedAt: new Date(now).toISOString(), stopped: stop, speed: speed(times, now),
    questions, answered, A, C, promoted, regions };
}

export function renderBoard(b) {
  const s = b.speed, lines = [
    `# 粉笔流水线看板（${b.generatedAt}）`, '',
    `| 指标 | 数值 |`, `|---|---:|`,
    `| 状态 | ${b.stopped ? '**已停止（STOP）**' : '运行中'} |`,
    `| 最近 1 小时抓取（含空等的真实速度） | ${s.lastHourPapers} 卷 |`,
    `| 连续抓取时平均每卷 | ${s.activeSecondsPerPaper ?? '—'} 秒 |`,
    `| 卷间空等 >2 分钟 | ${s.idleGaps} 次，共 ${s.idleMinutesTotal} 分钟 |`,
    `| 距上一卷 | ${s.lastCaptureMinutesAgo ?? '—'} 分钟 |`,
    `| 累计已抓 | ${s.captured} 卷 |`,
    `| 答案覆盖 | ${b.answered} / ${b.questions} 题 |`,
    `| 转换 A / C | ${b.A} / ${b.C} |`,
    `| 已进集成分支 | ${b.promoted} 卷 |`, '',
    '| 地区 | 已抓 | 答案齐 | A | C | 已进分支 |', '|---|---:|---:|---:|---:|---:|',
    ...Object.entries(b.regions).sort().map(([k, r]) => `| ${k} | ${r.captured} | ${r.withAnswers} | ${r.A} | ${r.C} | ${r.promoted} |`),
    '', '| 小时 (UTC) | 抓取卷数 |', '|---|---:|',
    ...Object.entries(s.hourly).map(([h, n]) => `| ${h} | ${n} |`), ''];
  return lines.join('\n');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [workDir, repoRoot] = [process.argv[2], process.argv[3]];
  if (!workDir || !repoRoot) throw Error('usage: pipeline-board.mjs WORK_DIR REPO_ROOT');
  buildBoard({ workDir, repoRoot }).then(async b => {
    await fs.writeFile(path.join(workDir, 'board.json'), JSON.stringify(b, null, 2) + '\n');
    await fs.writeFile(path.join(workDir, 'BOARD.md'), renderBoard(b));
    console.log(JSON.stringify({ lastHourPapers: b.speed.lastHourPapers, captured: b.speed.captured, A: b.A, C: b.C, promoted: b.promoted, stopped: b.stopped }));
  }).catch(e => { console.error(e.message); process.exitCode = 1; });
}
