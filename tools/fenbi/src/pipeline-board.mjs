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
import { better, identityKey, readManifestIdentities } from './identity.mjs';

const HOUR = 3600e3, IDLE_GAP_MS = 120e3;
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const readJson = f => fs.readFile(f, 'utf8').then(JSON.parse).catch(() => null);
const dirs = async root => (await fs.readdir(root, { withFileTypes: true }).catch(() => [])).filter(e => e.isDirectory()).map(e => e.name);
const text = h => String(h ?? '').replace(/<[^>]*>/g, '').trim();
// Require an explicit UTC offset: naive local times vary with the host timezone.
// Neither a backfill checkpoint creation time nor a document mtime proves first capture.
const firstCaptureTimestamp = (raw, now) => {
  if (typeof raw !== 'string' || !/(?:Z|[+-]\\d{2}:\\d{2})$/iu.test(raw.trim())) return null;
  const t = Date.parse(raw);
  return Number.isFinite(t) && t <= now ? t : null;
};

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

export async function buildBoard({ workDir, repoRoot, papersDir, papersRoot = papersDir || path.join(workDir, 'papers'), ingestRoot = path.join(workDir, 'batch-ingest'), now = Date.now() }) {
  const times = [], regions = {}, seenSources = new Map();
  let questions = 0, answered = 0, countedPapers = 0, captureTimeUnknown = 0;
  let duplicateSourceDirs = 0, crossAreaIdentityConflicts = 0;
  for (const name of (await dirs(papersRoot)).sort()) {
    const base = path.join(papersRoot, name);
    const cp = await readJson(path.join(base, 'checkpoint.json'));
    const runSummary = await readJson(path.join(base, 'run-summary.json'));
    const documentFile = cp?.documentFile ? path.join(base, cp.documentFile) : path.join(base, 'document.json');
    const doc = await readJson(documentFile);
    if (!doc?.identity || !Array.isArray(doc.questions)) continue;
    const id = doc.identity;
    const area = id.area || 'unknown';
    const sourceId = id.id ?? id.sourceId;
    if (sourceId != null && String(sourceId).trim()) {
      const sourceKey = String(id.subject ?? 'unknown') + ':' + String(sourceId);
      if (seenSources.has(sourceKey)) {
        duplicateSourceDirs++;
        if (seenSources.get(sourceKey) !== area) crossAreaIdentityConflicts++;
        continue;
      }
      seenSources.set(sourceKey, area);
    }
    countedPapers++;
    // Backfill can change checkpoint timestamps and the file mtime. Ignore both.
    // A first-capture timestamp is usable only with an explicit timezone and no future skew.
    const firstCapture = [doc.source?.capturedAt, runSummary?.startedAt, runSummary?.at]
      .map(x => firstCaptureTimestamp(x, now)).find(x => x !== null);
    if (firstCapture !== undefined) times.push(firstCapture);
    else captureTimeUnknown++;
    const r = regions[area] ||= { captured: 0, withAnswers: 0, A: 0, C: 0, promoted: 0 };
    r.captured++;
    const qs = doc?.questions || [];
    questions += qs.length;
    const a = qs.filter(q => text(q.answerHtml)).length;
    answered += a;
    if (qs.length && a === qs.length) r.withAnswers++;
  }
  let A = 0, C = 0, promoted = 0;
  const manifest = await readManifestIdentities(repoRoot);
  const aTargets = [];
  for (const name of await dirs(ingestRoot)) {
    const rc = await readJson(path.join(ingestRoot, name, 'receipt.json'));
    if (!rc) continue;
    const r = regions[rc.area] ||= { captured: 0, withAnswers: 0, A: 0, C: 0, promoted: 0 };
    if (rc.grade === 'A') { A++; r.A++; } else { C++; r.C++; continue; }
    // Resolve the published target exactly as promote-all does: a direct path wins, otherwise a
    // UNIQUE manifest identity names the canonical path. Ambiguity is never guessed.
    const direct = rc.path ? await fs.readFile(path.join(repoRoot, rc.path)).catch(() => null) : null;
    if (direct) { aTargets.push({ receipt: rc, targetPath: rc.path, prior: direct }); continue; }
    const paths = rc.path ? (manifest.get(identityKey(rc)) || []) : [];
    if (paths.length !== 1) continue;
    const prior = await fs.readFile(path.join(repoRoot, paths[0])).catch(() => null);
    if (prior) aTargets.push({ receipt: rc, targetPath: paths[0], prior });
  }
  // Several sources can target one paper. Count the target once and pick the same winner as
  // promote-all, so the board can never disagree with what was actually published.
  const byTarget = new Map();
  for (const item of aTargets) {
    const list = byTarget.get(item.targetPath) || [];
    list.push(item); byTarget.set(item.targetPath, list);
  }
  for (const list of byTarget.values()) {
    const winner = list.reduce((w, c) => better(c.receipt, w.receipt) ? c : w);
    if (sha(winner.prior) !== winner.receipt.markdownSha256) continue;
    promoted++;
    (regions[winner.receipt.area] ||= { captured: 0, withAnswers: 0, A: 0, C: 0, promoted: 0 }).promoted++;
  }
  const stop = await fs.readFile(path.join(workDir, 'STOP'), 'utf8').then(() => true).catch(() => false);
  const captureSpeed = { ...speed(times, now), captured: countedPapers, captureTimeUnknown,
    duplicateSourceDirs, crossAreaIdentityConflicts };
  return { generatedAt: new Date(now).toISOString(), stopped: stop, speed: captureSpeed,
    questions, answered, A, C, promoted, regions };
}

export function renderBoard(b) {
  const s = b.speed, lines = [
    `# 粉笔流水线看板（${b.generatedAt}）`, '',
    `| 指标 | 数值 |`, `|---|---:|`,
    `| 状态 | ${b.stopped ? '**已停止（STOP）**' : '运行中'} |`,
    `| 最近 1 小时首次采集（有来源时间证据） | ${s.lastHourPapers} 卷 |`,
    `| 首次采集时间未知 | ${s.captureTimeUnknown ?? 0} 卷 |`,
    `| 重复来源目录（已去重） | ${s.duplicateSourceDirs ?? 0} 个 |`,
    `| 跨地区来源ID冲突（待人工归属） | ${s.crossAreaIdentityConflicts ?? 0} 个 |`,
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
  const args = process.argv.slice(2);
  const positional = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1] === '--papers-root') && !(i > 0 && args[i - 1] === '--ingest-root'));
  const [workDir, repoRoot, papersDir] = positional;
  const papersIndex = args.indexOf('--papers-root'), ingestIndex = args.indexOf('--ingest-root');
  const papersRoot = papersIndex >= 0 ? args[papersIndex + 1] : papersDir;
  const ingestRoot = ingestIndex >= 0 ? args[ingestIndex + 1] : undefined;
  if (!workDir || !repoRoot) throw Error('usage: pipeline-board.mjs WORK_DIR REPO_ROOT [PAPERS_DIR] [--papers-root DIR] [--ingest-root DIR]');
  buildBoard({ workDir, repoRoot, papersDir, papersRoot, ingestRoot }).then(async b => {
    await fs.writeFile(path.join(workDir, 'board.json'), JSON.stringify(b, null, 2) + '\n');
    await fs.writeFile(path.join(workDir, 'BOARD.md'), renderBoard(b));
    console.log(JSON.stringify({ lastHourPapers: b.speed.lastHourPapers, captured: b.speed.captured, A: b.A, C: b.C, promoted: b.promoted, stopped: b.stopped }));
  }).catch(e => { console.error(e.message); process.exitCode = 1; });
}
