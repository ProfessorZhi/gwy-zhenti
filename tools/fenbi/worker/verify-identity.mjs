#!/usr/bin/env node
// 已缓存卷的身份核对（离线，只读本地文件，不开浏览器）。
// 对 work/fenbi/papers/<key>：在该卷练习页/解析页当时保存的 JSON（t2-20261019/payloads/<key>/、solution.json）里找 paperId，
// 与目录 sourceId 比对；再看页面标题是否包含完整卷名、同地区同年是否有标题互相包含的卷（可能被误选）。
//
//   node worker/verify-identity.mjs            只出报告：work/fenbi/identity-report.json，最后一行打印汇总
//   node worker/verify-identity.mjs --write    另外：paperId 一致的卷写入 source-paper-identity 证据；
//                                              paperId 不一致、或标题有歧义且页面标题对不上的卷写进 identity-quarantine.json（不落地、不重抓）
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { collectPaperIds, bindingStatus, ambiguousTitles } from './identity.mjs';

const B = path.resolve(process.env.FENBI_BASE || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));
const PAPERS = WORK + '/papers', RUN = WORK + '/t2-20261019';
const WRITE = process.argv.includes('--write');
const readJson = async p => { try { return JSON.parse(await fs.readFile(p, 'utf8')); } catch { return null; } };
const norm = s => String(s || '').replace(/\s+/g, '').replace(/[（]/g, '(').replace(/[）]/g, ')');

async function jsonFiles(dir) {
  const out = [];
  for (const f of await fs.readdir(dir).catch(() => [])) if (f.endsWith('.json')) out.push(path.join(dir, f));
  return out;
}

export async function verifyAll({ write = false } = {}) {
  const rows = [], docs = [];
  for (const key of (await fs.readdir(PAPERS).catch(() => [])).sort()) {
    const doc = await readJson(path.join(PAPERS, key, 'document.json'));
    if (!doc?.identity) continue;
    docs.push({ key, doc, run: await readJson(path.join(PAPERS, key, 'run-summary.json')) });
  }
  const cand = (await readJson(WORK + '/candidates-live.json'))?.candidates || [];
  const ambiguous = ambiguousTitles([...docs.map(d => ({ id: d.doc.identity.id, title: d.doc.identity.title, area: d.doc.identity.area, year: d.doc.identity.year })),
    ...cand.map(c => ({ id: c.id, title: c.title, area: c.area, year: c.year }))]);
  for (const { key, doc, run } of docs) {
    const sid = String(doc.identity.id);
    const ids = new Set();
    for (const f of [...await jsonFiles(path.join(RUN, 'payloads', key)), path.join(PAPERS, key, 'solution.json')]) collectPaperIds(await readJson(f), ids);
    const pageTitle = run?.pageTitle || '';
    const row = { key, sourceId: sid, binding: bindingStatus(ids, sid), paperIds: [...ids].slice(0, 5),
      titleInPage: pageTitle ? norm(pageTitle).includes(norm(doc.identity.title)) : null,
      ambiguousWith: (ambiguous.get(sid) || []).filter(x => x !== sid) };
    row.verdict = row.binding === 'verified' ? 'verified'
      : row.binding === 'mismatch' || row.binding === 'mixed' ? 'quarantine'
      : row.ambiguousWith.length && row.titleInPage !== true ? 'quarantine' : 'unverified';
    rows.push(row);
    if (write && row.verdict === 'verified' && !(doc.evidence || []).some(e => e.type === 'source-paper-identity' && String(e.paperId) === sid)) {
      doc.evidence = [...(doc.evidence || []), { type: 'source-paper-identity', paperId: sid, observedAt: new Date().toISOString(), via: 'paperId in saved exercise/analysis JSON' }];
      const file = path.join(PAPERS, key, 'document.json');
      await fs.writeFile(file + '.tmp', JSON.stringify(doc), { mode: 0o600 }); await fs.rename(file + '.tmp', file);
    }
  }
  if (write) {
    const q = (await readJson(RUN + '/identity-quarantine.json')) || {};
    for (const r of rows.filter(r => r.verdict === 'quarantine')) q[r.sourceId] ||= { at: new Date().toISOString(), key: r.key, by: 'verify-identity', binding: r.binding, paperIds: r.paperIds, ambiguousWith: r.ambiguousWith };
    await fs.mkdir(RUN, { recursive: true });
    await fs.writeFile(RUN + '/identity-quarantine.json', JSON.stringify(q, null, 2) + '\n', { mode: 0o600 });
  }
  await fs.writeFile(WORK + '/identity-report.json', JSON.stringify(rows, null, 2) + '\n', { mode: 0o600 });
  const count = f => rows.filter(f).length;
  return { papers: rows.length, verified: count(r => r.verdict === 'verified'), quarantine: count(r => r.verdict === 'quarantine'),
    unverified: count(r => r.verdict === 'unverified'), paperIdMismatch: count(r => r.binding === 'mismatch' || r.binding === 'mixed'),
    paperIdUnobserved: count(r => r.binding === 'unobserved'), ambiguousTitle: count(r => r.ambiguousWith.length),
    titleInPage: count(r => r.titleInPage === true), titleNotInPage: count(r => r.titleInPage === false), written: write };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  verifyAll({ write: WRITE }).then(s => console.log(JSON.stringify(s))).catch(e => { console.error(e.message); process.exitCode = 1; });
}
