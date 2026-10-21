#!/usr/bin/env node
// 申论落盘：已采集的申论卷（shenlun-capture-panes 的输出目录）→ Markdown + 图片 → 覆盖写进本库同一卷 → 闸门 → 推 main。
// 和行测共用候选目录、promoteAll 和 publish：授权看 RIGHTS_FILE（coverAllCapturedSources），不看采集时写死的 cloudStorageBlocked。
// 缺参考答案、缺文字解析的题照常发布，页面里标"来源未提供"；缺题、缺材料、图片下载失败的卷判 C，不落地。
//
//   CAPTURES_DIR=<采集输出的上级目录> FENBI_WORK_DIR=… INTEG_REPO=… RIGHTS_FILE=… PUSH=1 AUTO_MERGE=1 node worker/land-shenlun.mjs
// 最后一行打印 JSON 回执。
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { loadShenlunCapture, parseShenlunCapture } from '../src/shenlun.mjs';
import { renderCandidate } from '../src/render.mjs';
import { paperLabel, labelsIn } from '../src/paper-label.mjs';
import { promoteAll } from '../src/promote-all.mjs';
import { candidateRootOf, publish } from './publish.mjs';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const EXT = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp', 'image/svg+xml': 'svg', 'image/bmp': 'bmp', 'image/avif': 'avif' };
const RISK = new Set([401, 403, 429, 503]);

// 本卷的问题（任何一条都判 C）。
export function shenlunBlockers(doc) {
  const s = doc.shenlun || {}, out = [];
  if (!doc.questions.length) out.push('no-questions');
  if (s.missingQuestionNumbers?.length) out.push('question-missing:' + s.missingQuestionNumbers.join(','));
  if (!doc.materials.length) out.push('no-materials');
  if (s.unresolvedMaterialReferences?.length) out.push('material-not-stored:' + s.unresolvedMaterialReferences.length);
  if (Number.isInteger(s.materialTabs) && s.materialTabs > doc.materials.length) out.push(`material-tabs:${doc.materials.length}/${s.materialTabs}`);
  if (doc.evidence.some(e => e.type === 'rejected-paper-mismatch')) out.push('paper-id-mismatch');
  if (!String(doc.identity.title || '').trim()) out.push('title-missing');
  if (!/^\d{1,15}$/u.test(String(doc.identity.id))) out.push('bad-source-id');
  return out;
}

// 图片下载到候选目录的 assets-fenbi-<id>/<sha>.<ext>；遇到风控状态码立即停。
async function downloadImages(doc, dir, fetchImpl) {
  for (const asset of doc.assets) {
    const res = await fetchImpl(asset.url, { signal: AbortSignal.timeout(30000) });
    if (RISK.has(res.status)) { const e = Error('image-risk-' + res.status); e.risk = res.status; throw e; }
    if (!res.ok) throw Error('image-http-' + res.status);
    const bytes = Buffer.from(await res.arrayBuffer());
    const ext = EXT[(res.headers.get('content-type') || '').split(';')[0].trim()] || (asset.url.match(/\.(png|jpe?g|gif|webp|svg|bmp|avif)(?:$|\?)/iu)?.[1] || '').toLowerCase().replace('jpeg', 'jpg');
    if (!ext) throw Error('image-type-unknown');
    const name = `${sha(bytes)}.${ext}`;
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(path.join(dir, name), bytes);
    Object.assign(asset, { status: 'downloaded', localPath: name, sha256: sha(bytes) });
  }
}

// 一份采集 → 候选（paper.md、receipt.json、图片）。返回回执。
export async function shenlunCandidate({ captureDir, repo, dest, fetchImpl = fetch }) {
  const name = 'shenlun-' + path.basename(captureDir);
  const { doc } = parseShenlunCapture(await loadShenlunCapture(captureDir));
  const id = doc.identity, area = id.area === '国考' ? '国考' : '省考/' + id.area;
  const files = await fs.readdir(path.join(repo, area, String(id.year))).catch(() => []);
  const label = paperLabel({ title: id.title, variant: id.variant, existing: labelsIn(files, '申论') });
  doc.identity = { ...id, paperLabel: label };
  const rel = path.posix.join(area, String(id.year), `申论-${label}.md`);
  const row = { name, sourceId: String(id.id), area: id.area, year: Number(id.year), variant: id.variant, subject: 'shenlun', path: rel,
    grade: 'C', issues: shenlunBlockers(doc), counts: { sourceQuestions: doc.questions.length } };
  const out = path.join(dest, name);
  await fs.rm(out, { recursive: true, force: true });
  if (row.issues.length) return row;
  const prefix = 'assets-fenbi-' + id.id;
  try { await downloadImages(doc, path.join(out, prefix), fetchImpl); }
  catch (e) { if (e.risk) throw e; row.issues.push(e.message); await fs.rm(out, { recursive: true, force: true }); return row; }
  const md = renderCandidate(doc, { status: 'complete' }, { imagePrefix: prefix });
  const prior = await fs.readFile(path.join(repo, rel)).catch(() => null);
  Object.assign(row, { grade: 'A', answerNumbers: doc.questions.filter(q => String(q.answerHtml || '').trim()).map(q => q.number),
    sourceMissingNumbers: [], completeness: 'complete', markdownSha256: sha(md), oldSha256: prior ? sha(prior) : null,
    explanations: doc.questions.filter(q => String(q.explanationHtml || '').trim()).length });
  await fs.mkdir(out, { recursive: true });
  await fs.writeFile(path.join(out, 'paper.md'), md);
  await fs.writeFile(path.join(out, 'receipt.json'), JSON.stringify(row, null, 2) + '\n');
  return row;
}

export async function landShenlun({ captures, repo, rightsFile, push = false, autoMerge = false, fetchImpl = fetch }) {
  const started = Date.now(), dest = candidateRootOf(await fs.realpath(repo));
  const out = { captures: 0, A: 0, C: 0, cReasons: {}, risk: null };
  for (const e of (await fs.readdir(captures, { withFileTypes: true }).catch(() => [])).sort((a, b) => a.name.localeCompare(b.name))) {
    const dir = path.join(captures, e.name);
    if (!e.isDirectory() || !(await fs.access(path.join(dir, 'document.json')).then(() => true, () => false))) continue;
    out.captures++;
    try {
      const r = await shenlunCandidate({ captureDir: dir, repo, dest, fetchImpl });
      if (r.grade === 'A') out.A++;
      else { out.C++; for (const i of r.issues) { const k = i.split(':')[0]; out.cReasons[k] = (out.cReasons[k] || 0) + 1; } }
    } catch (err) {
      if (err.risk) { out.risk = err.message; break; }
      out.C++; const k = 'error:' + String(err.message).slice(0, 60); out.cReasons[k] = (out.cReasons[k] || 0) + 1;
    }
  }
  const promote = out.A ? await promoteAll({ candidateRoot: dest, repoRoot: repo, rightsFile, allowReplace: true, apply: true }) : null;
  const p = await publish({ repo, rightsFile, push, autoMerge, message: `integrate(fenbi): land shenlun ${new Date().toISOString().slice(0, 16)}Z` });
  return { ...out, promoted: promote?.promoted ?? 0, replaced: promote?.replaced ?? 0,
    blocked: Object.fromEntries(Object.entries(promote?.blocked || {}).map(([k, v]) => [k, v.length])),
    committed: p.committed, pushedBranch: p.pushedBranch, pushedMain: p.pushedMain, error: p.error || null,
    gate: p.gate ? { ok: p.gate.ok, papers: p.gate.papers, reasons: p.gate.reasons.slice(0, 10) } : null,
    seconds: Math.round((Date.now() - started) / 1000) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { CAPTURES_DIR, INTEG_REPO, RIGHTS_FILE } = process.env;
  if (!CAPTURES_DIR || !INTEG_REPO || !RIGHTS_FILE) { console.log(JSON.stringify({ error: 'CAPTURES_DIR, INTEG_REPO and RIGHTS_FILE required' })); process.exit(1); }
  landShenlun({ captures: path.resolve(CAPTURES_DIR), repo: path.resolve(INTEG_REPO), rightsFile: RIGHTS_FILE,
    push: process.env.PUSH === '1', autoMerge: process.env.AUTO_MERGE === '1' })
    .then(s => console.log(JSON.stringify(s)))
    .catch(e => { console.log(JSON.stringify({ error: String(e.stderr || e.message).slice(0, 300) })); process.exitCode = 1; });
}
