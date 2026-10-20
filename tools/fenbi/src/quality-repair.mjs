#!/usr/bin/env node
/**
 * Offline quality-repair workflow: gaps -> legal donor matching -> isolated patch plan
 * -> local QC receipt -> promotion handoff.
 *
 * Default OFF and purely local. No network access is implemented; an optional provider
 * interface exists but is never called unless the caller passes an explicit allowlisted
 * provider. Nothing here overwrites published files, the promote root, or the publisher.
 *
 * Hard rules:
 *  - a collection stub never becomes grade A; empty stems are never matched by number;
 *  - a donor must be an independent sourceId with an explicit rights basis, an evidence
 *    sha256, an independent QA pass and matching asset shas;
 *  - matching must be bidirectionally unique on the normalized stem; otherwise REVIEW_REQUIRED;
 *  - answer-only donors, missing per-question textual explanations, shenlun sub-question
 *    merges, conflicting donors, missing assets and unlicensed donors are refused;
 *  - the output is a candidate for S1, never a publication decision.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { isCollectionStub } from './validate.mjs';
import { normalizeComparisonText } from './align.mjs';

const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const ALLOWED_BASIS = new Set(['copyright-holder-license', 'copyright-holder-written-permission', 'official-public-release', 'public-domain']);
const FORBIDDEN_BASIS = new Set(['user-self-authorization', 'private-repo-preference', 'user-chose-a']);
const HEX64 = /^[0-9a-f]{64}$/u;
const GAP_KINDS = ['missing-question', 'missing-options', 'missing-answer', 'missing-explanation', 'missing-image-sha', 'shenlun-multi-part', 'rights-unverified'];

function scratch (text) {
  const cleaned = String(text ?? '')
    .replace(/!\[[^\]]*\]\([^)]*\)/gu, ' ')
    .replace(/<img\b[^>]*>/giu, ' ')
    .replace(/<[^>]+>/gu, ' ');
  return normalizeComparisonText(cleaned).strict.replace(LEFTOVER_IMAGE, ' ')
    .replace(/[\s\p{P}\p{S}]+/gu, '')
    .toLowerCase();
}
const LEFTOVER_IMAGE = /⟦IMAGE⟧|\bimage\b/giu;

function parsePaper (markdown) {
  const md = String(markdown ?? '');
  const detailsStart = md.search(/^<details\b/mu);
  const answerHeading = md.search(/^##\s*(?:参考答案|答案与解析|答案)\s*$/mu);
  const ends = [detailsStart, answerHeading].filter(x => x >= 0);
  const regionEnd = ends.length ? Math.min(...ends) : md.length;
  const qHeading = md.search(/^##\s*题目\s*$/mu);
  const region = md.slice(qHeading >= 0 ? qHeading : 0, regionEnd);
  const heads = [...region.matchAll(/^#{2,3}\s*第\s*(\d+)\s*题[^\n]*$/gmu)]
    .map(m => ({n: Number(m[1]), qid: m[0].match(/qid\s+([\w-]+)/u)?.[1] ?? null, index: m.index, start: m.index + m[0].length}));
  const details = new Map();
  for (const m of md.matchAll(/^<details>\s*<summary>\s*第\s*(\d+)\s*题[\s\S]*?<\/summary>([\s\S]*?)^<\/details>/gmu)) {
    details.set(Number(m[1]), m[2]);
  }
  const questions = heads.map((h, i) => {
    const body = region.slice(h.start, heads[i + 1]?.index ?? region.length);
    const optRe = /^\s*(?:[-*]\s*\*\*([A-D])\*\*|([A-D])[.、．)])\s*(.+)$/gmu;
    const opts = [...body.matchAll(optRe)].map(m => ({label: m[1] || m[2], text: m[3].trim()}));
    const optionAt = body.search(optRe);
    const answerAt = body.search(/【答案】|(?:\*\*)?答案(?:\*\*)?\s*[:：]|(?:\*\*)?参考答案/u);
    const ends = [optionAt, answerAt].filter(i => i >= 0);
    const stem = (ends.length ? body.slice(0, Math.min(...ends)) : body).trim();
    const own = details.get(h.n) ?? body;
    const answer = /(?:【答案】|(?:\*\*)?参考答案[^\n]*|(?:\*\*)?答案(?:\*\*)?\s*[:：])\s*([\s\S]*?)(?=\n\s*(?:【解析】|\*\*解析\*\*|(?:\*\*)?来源参考解析|解析\s*[:：])|$)/u.exec(own)?.[1]?.trim() ?? '';
    const explanation = /(?:【解析】|\*\*解析\*\*|(?:\*\*)?来源参考解析\s*[:：]?|解析\s*[:：])\s*([\s\S]*)/u.exec(own)?.[1]?.trim() ?? '';
    return {number: h.n, qid: h.qid, stem, options: opts, answer, explanation,
      stub: isCollectionStub(scratch(stem)) || isCollectionStub(stem.trim()),
      multiPart: /(?:[（(][1-9１-９][）)]|[一二三四五]、)/u.test(body)};
  });
  return {questions, details};
}

export function detectQualityGaps (paper, {rightsStatus = 'unverified'} = {}) {
  const parsed = parsePaper(paper.markdown);
  const rows = [];
  for (const q of parsed.questions) {
    const gaps = [];
    if (q.stub || !q.stem) gaps.push('missing-question');
    else if (q.options.length < 2) gaps.push('missing-options');
    if (!q.answer) gaps.push('missing-answer');
    if (!q.explanation) gaps.push('missing-explanation');
    if (q.multiPart) gaps.push('shenlun-multi-part');
    if (gaps.length) rows.push({number: q.number, qid: q.qid, gaps});
  }
  for (const asset of paper.assets ?? []) {
    if (!HEX64.test(asset.sha256 ?? '')) rows.push({number: null, asset: asset.path ?? null, gaps: ['missing-image-sha']});
  }
  if (parsed.questions.length === 0) rows.push({number: null, gaps: ['no-question-blocks']});
  if (rightsStatus !== 'cleared') rows.push({number: null, gaps: ['rights-unverified']});
  return {
    sourceId: paper.sourceId, path: paper.path, area: paper.area, year: paper.year, subject: paper.subject,
    structuralGrade: rows.some(r => r.gaps.some(g => g !== 'rights-unverified')) ? 'C' : 'A',
    qa: paper.qa?.verdict === 'pass' ? 'pass' : 'unknown',
    questions: parsed.questions.length, gaps: rows, kinds: [...new Set(rows.flatMap(r => r.gaps))]
  };
}

async function verifyTrustedFile (trustedRoot, relPath, expectedSha, label) {
  if (!trustedRoot) return [`${label}-trusted-root-missing`];
  if (typeof relPath !== 'string' || relPath.startsWith('/') || relPath.split(/[\\/]/u).includes('..')) return [`${label}-path-invalid`];
  let rootReal, real;
  try { rootReal = await fs.realpath(trustedRoot); } catch { return [`${label}-root-unreadable`]; }
  try { real = await fs.realpath(path.resolve(rootReal, relPath)); } catch { return [`${label}-unreadable`]; }
  if (!real.startsWith(rootReal + path.sep)) return [`${label}-escape`];
  const stat = await fs.lstat(real);
  if (stat.isSymbolicLink() || !stat.isFile()) return [`${label}-not-regular-file`];
  if (sha(await fs.readFile(real)) !== expectedSha) return [`${label}-sha-mismatch`];
  return [];
}

export async function buildDonorRegistry (donors = [], {trustedRoot = null} = {}) {
  const accepted = [], rejected = [];
  for (const donor of donors) {
    const reasons = [];
    if (!donor?.donorId || !donor?.sourceId) reasons.push('donor-id-missing');
    if (donor?.rights?.basis && FORBIDDEN_BASIS.has(donor.rights.basis)) reasons.push('donor-rights-forbidden');
    if (!ALLOWED_BASIS.has(donor?.rights?.basis)) reasons.push('donor-rights-missing');
    if (!HEX64.test(donor?.rights?.evidenceSha256 ?? '')) reasons.push('donor-rights-evidence-missing');
    if (donor?.qa?.verdict !== 'pass') reasons.push('donor-qa-not-passed');
    if (!HEX64.test(donor?.qa?.reportSha256 ?? '')) reasons.push('donor-qa-report-missing');
    reasons.push(...await verifyTrustedFile(trustedRoot, donor?.qa?.reportPath, donor?.qa?.reportSha256, 'donor-qa-report'));
    reasons.push(...await verifyTrustedFile(trustedRoot, donor?.rights?.evidencePath, donor?.rights?.evidenceSha256, 'donor-rights-evidence'));
    const parsed = parsePaper(donor?.markdown);
    if (!parsed.questions.length) reasons.push('donor-no-questions');
    if (reasons.length) { rejected.push({donorId: donor?.donorId ?? null, sourceId: donor?.sourceId ?? null, reasons}); continue; }
    accepted.push({...donor, questions: parsed.questions});
  }
  return {accepted, rejected};
}

function uniqueIndex (donors, targetStem) {
  const hits = [];
  for (const donor of donors) {
    for (const q of donor.questions) {
      if (scratch(q.stem) === targetStem && targetStem) hits.push({donor, q});
    }
  }
  return hits;
}

function donorIndexFor (donors, donorQuestionStem) {
  // Bidirectional uniqueness: the donor stem must also point at exactly one target question.
  const hits = [];
  for (const donor of donors) {
    for (const q of donor.questions) if (scratch(q.stem) === donorQuestionStem && donorQuestionStem) hits.push({donor, q});
  }
  return hits;
}

/**
 * Build an isolated repair plan. `outDir` is only written when apply=true and QC passes;
 * a QC failure may store a metadata-only PARTIAL_REVIEW receipt, never a publishable patch.
 */
export async function buildRepairPlan ({target, donors = [], reviewedPairs = [], outDir = null, apply = false, trustedRoot = null}) {
  const registry = await buildDonorRegistry(donors, {trustedRoot});
  const reasons = [];
  const reviewQueue = [];
  const targetParsed = parsePaper(target.markdown);
  const targetByNo = new Map(targetParsed.questions.map(q => [q.number, q]));
  const gaps = detectQualityGaps(target, {rightsStatus: target.rightsStatus ?? 'unverified'});
  const structural = gaps.gaps.filter(g => !g.gaps.includes('rights-unverified'));
  const plan = {sourceId: target.sourceId, path: target.path, beforeSha: sha(target.markdown), repairs: [], review: [], donorsUsed: []};
  const identity = donor => donor.area === target.area && Number(donor.year) === Number(target.year) &&
    donor.subject === target.subject && (donor.variant ?? null) === (target.variant ?? null);
  const stemCount = new Map();
  for (const q of targetParsed.questions) { const k = scratch(q.stem); if (k) stemCount.set(k, (stemCount.get(k) ?? 0) + 1); }
  const donorStemCount = new Map();
  for (const donor of registry.accepted) for (const q of donor.questions) {
    const k = scratch(q.stem); if (k) donorStemCount.set(k, (donorStemCount.get(k) ?? 0) + 1);
  }

  for (const gap of structural) {
    if (gap.number === null) { reasons.push(`unfixable-gap:${gap.gaps.join('+')}`); continue; }
    const tq = targetByNo.get(gap.number);
    if (!tq) continue;
    const targetStem = scratch(tq.stem);
    if (tq.stub || !targetStem) {
      const reviewed = reviewedPairs.find(p => Number(p.targetNumber) === Number(tq.number) &&
        typeof p.signedBy === 'string' && p.signedBy && HEX64.test(p.approvalSha256 ?? '') &&
        p.reviewerScope === 's1-owner' && p.humanReviewedBy);
      if (!reviewed) { reviewQueue.push({number: tq.number, reason: 'signed-review-required', action: 'REVIEW_REQUIRED'}); continue; }
      const donor = registry.accepted.find(d => d.donorId === reviewed.donorId);
      if (!donor) { reviewQueue.push({number: tq.number, reason: 'reviewed-donor-untrusted', action: 'REVIEW_REQUIRED'}); continue; }
      if (!identity(donor)) { reviewQueue.push({number: tq.number, reason: 'donor-identity-mismatch', action: 'REVIEW_REQUIRED'}); continue; }
      if (donor.sourceId === target.sourceId) { reviewQueue.push({number: tq.number, reason: 'donor-not-independent', action: 'REVIEW_REQUIRED'}); continue; }
      const dq = donor.questions.find(q => q.number === Number(reviewed.donorNumber));
      if (!dq || dq.stub || dq.options.length < 2 || !dq.answer || !dq.explanation) {
        reviewQueue.push({number: tq.number, reason: 'donor-incomplete', action: 'REVIEW_REQUIRED'}); continue;
      }
      plan.repairs.push({
        number: tq.number, donorId: donor.donorId, donorSourceId: donor.sourceId, donorNumber: dq.number,
        matchedBy: 'signed-human-review', reviewer: reviewed.signedBy,
        replacement: {stem: dq.stem, options: dq.options, answer: dq.answer, explanation: dq.explanation}
      });
      continue;
    }
    if ((stemCount.get(targetStem) ?? 0) !== 1) {
      reviewQueue.push({number: tq.number, reason: 'duplicate-target-stem', action: 'REVIEW_REQUIRED'}); continue;
    }
    const hits = [];
    for (const donor of registry.accepted) {
      if (!identity(donor)) continue;
      for (const q of donor.questions) if (scratch(q.stem) === targetStem) hits.push({donor, q});
    }
    if (hits.length === 0) { reviewQueue.push({number: tq.number, reason: 'no-donor-match', action: 'REVIEW_REQUIRED'}); continue; }
    if (hits.length > 1) { reviewQueue.push({number: tq.number, reason: 'conflicting-donors', action: 'REVIEW_REQUIRED'}); continue; }
    const {donor, q: dq} = hits[0];
    if (donor.sourceId === target.sourceId) { reviewQueue.push({number: tq.number, reason: 'donor-not-independent', action: 'REVIEW_REQUIRED'}); continue; }
    // Bidirectional uniqueness over both sides, not just one donor id.
    if ((donorStemCount.get(scratch(dq.stem)) ?? 0) !== 1 || (stemCount.get(scratch(dq.stem)) ?? 0) !== 1) {
      reviewQueue.push({number: tq.number, reason: 'not-bidirectionally-unique', action: 'REVIEW_REQUIRED'}); continue;
    }
    if (dq.stub || dq.options.length < 2 || !dq.answer) { reviewQueue.push({number: tq.number, reason: 'donor-answer-without-question', action: 'REVIEW_REQUIRED'}); continue; }
    if (!dq.explanation) { reviewQueue.push({number: tq.number, reason: 'no-verbatim-explanation', action: 'REVIEW_REQUIRED'}); continue; }
    if (target.subject === 'shenlun' && /(?:[（(][1-9１-９][）)]|[一二三四五]、)/u.test(dq.stem + dq.answer)) {
      reviewQueue.push({number: tq.number, reason: 'shenlun-subquestion-merge', action: 'REVIEW_REQUIRED'}); continue;
    }
    const refs = [...String(dq.stem + dq.options.map(o => o.text).join(' ')).matchAll(/!\[[^\]]*\]\(([^)\s]+)\)|<img\b[^>]*\bsrc=["']([^"']+)["']/giu)].map(m => m[1] || m[2]);
    const assetMap = new Map((donor.assets ?? []).map(a => [a.path, a.sha256]));
    let assetOk = true;
    for (const ref of refs) {
      if (/^[a-z][a-z0-9+.-]*:/iu.test(ref) || ref.includes('..') || ref.startsWith('/')) { assetOk = false; break; }
      if (!HEX64.test(assetMap.get(ref) ?? '')) { assetOk = false; break; }
    }
    if (!assetOk) { reviewQueue.push({number: tq.number, reason: 'donor-asset-missing-or-sha', action: 'REVIEW_REQUIRED'}); continue; }
    plan.repairs.push({
      number: tq.number, donorId: donor.donorId, donorSourceId: donor.sourceId, donorNumber: dq.number,
      matchedBy: 'unique-stem', replacement: {stem: dq.stem, options: dq.options, answer: dq.answer, explanation: dq.explanation}
    });
  }

  if (!plan.repairs.length) {
    return {ok: false, reasons: [...new Set(reasons.length ? reasons : ['no-repairable-gaps'])], plan, reviewQueue, review: reviewQueue, eligible: 0};
  }

  const afterMarkdown = renderRepaired(target.markdown, plan.repairs);
  plan.afterSha = sha(afterMarkdown);
  plan.repairs = plan.repairs.map(r => ({...r, beforeSha: plan.beforeSha, afterSha: plan.afterSha}));
  plan.donorsUsed = [...new Set(plan.repairs.map(r => r.donorId))];
  plan.review = reviewQueue;
  const post = detectQualityGaps({...target, markdown: afterMarkdown}, {rightsStatus: target.rightsStatus});
  const postStructural = post.gaps.filter(g => !g.gaps.includes('rights-unverified'));
  const targetRightsFile = await verifyTrustedFile(trustedRoot, target.rightsEvidencePath, target.rightsEvidenceSha256, 'target-rights-evidence');
  plan.checks = {
    structurePreserved: parsePaper(afterMarkdown).questions.length === targetParsed.questions.length,
    allOriginalGapsResolved: postStructural.length === 0,
    zeroUnreviewedStructural: reviewQueue.length === 0,
    everyRepairComplete: plan.repairs.every(r => r.replacement.options.length >= 2 && r.replacement.answer && r.replacement.explanation),
    donorIndependent: plan.repairs.every(r => r.donorSourceId !== target.sourceId),
    donorIdentityMatch: plan.repairs.every(r => registry.accepted.some(d => d.donorId === r.donorId && identity(d))),
    targetRightsVerified: target.rightsStatus === 'cleared' && HEX64.test(target.rightsEvidenceSha256 ?? '') && targetRightsFile.length === 0,
    rightsBasisPresent: plan.donorsUsed.length > 0 && plan.donorsUsed.every(id => registry.accepted.some(d => d.donorId === id))
  };
  const pass = Object.values(plan.checks).every(Boolean);
  const qc = {targetSourceId: target.sourceId, path: target.path, beforeSha: plan.beforeSha, afterSha: plan.afterSha,
    repairs: plan.repairs.length, checks: plan.checks, verdict: pass ? 'pass' : 'PARTIAL_REVIEW',
    postGaps: postStructural, review: reviewQueue,
    note: 'local structural QC only; S1 must verify rights and independent QA'};
  plan.qc = qc;

  if (apply) {
    if (!outDir) return {ok: false, reasons: ['out-dir-required-for-apply'], plan, reviewQueue, eligible: 0};
    await fs.mkdir(outDir, {recursive: true, mode: 0o700});
    const stat = await fs.stat(outDir);
    if ((stat.mode & 0o077) !== 0) return {ok: false, reasons: ['out-dir-not-private'], plan, reviewQueue, eligible: 0};
    if (!pass) {
      const partial = path.join(outDir, `partial-${target.sourceId}-${plan.afterSha.slice(0, 12)}.json`);
      await fs.writeFile(partial, JSON.stringify({verdict: 'PARTIAL_REVIEW', ...qc}, null, 2), {mode: 0o600, flag: 'wx'});
      plan.partialReceipt = partial;
      return {ok: false, reasons: ['qc-reject'], plan, reviewQueue, eligible: 0, qc};
    }
    const patchFile = path.join(outDir, `repair-${target.sourceId}-${plan.afterSha.slice(0, 12)}.md`);
    await fs.writeFile(patchFile, afterMarkdown, {mode: 0o600, flag: 'wx'});
    await fs.writeFile(path.join(outDir, `repair-${target.sourceId}-${plan.afterSha.slice(0, 12)}.receipt.json`), JSON.stringify(qc, null, 2), {mode: 0o600, flag: 'wx'});
    plan.patchFile = patchFile;
  }
  return {ok: pass, reasons: pass ? [] : ['qc-reject'], plan, reviewQueue, eligible: pass ? plan.repairs.length : 0, qc};
}

function renderRepaired (markdown, repairs) {
  let out = String(markdown);
  for (const repair of repairs) {
    const r = repair.replacement;
    const block = [`### 第 ${repair.number} 题`, r.stem, ...r.options.map(o => `${o.label}. ${o.text}`), '【答案】' + r.answer, '【解析】' + r.explanation].join('\n');
    const re = new RegExp(`^#{2,3}\\s*第\\s*${repair.number}\\s*题[^\\n]*$`, 'mu');
    const m = re.exec(out);
    if (!m) continue;
    const start = m.index + m[0].length;
    const tail = out.slice(start);
    const nextQ = tail.search(/^#{2,3}\s*第\s*\d+\s*题/mu);
    let end;
    if (nextQ >= 0) end = start + nextQ;
    else {
      // Never run to EOF: stop at the independent answer area or details block.
      const boundary = tail.search(/^<details\b|^##\s*(?:参考答案|答案与解析|答案)\s*$/mu);
      end = boundary >= 0 ? start + boundary : out.length;
    }
    const replacement = '\n' + block.split('\n').slice(1).join('\n') + '\n';
    out = out.slice(0, start) + replacement + out.slice(end);
  }
  return out;
}

/** Promotion handoff descriptor; nothing is pushed or promoted here. */
export function handoffCandidate (result) {
  if (!result?.ok || !result.plan?.qc) return {ok: false, reason: 'not-repairable'};
  return {
    ok: true, kind: 'quality-repair-candidate', sourceId: result.plan.sourceId, path: result.plan.path,
    patchFile: result.plan.patchFile ?? null, beforeSha: result.plan.beforeSha, afterSha: result.plan.afterSha,
    qcVerdict: result.plan.qc.verdict, requires: ['S1-rights-verification', 'independent-QA-pass']
  };
}

/**
 * Pluggable evidence fetcher. Disabled unless a provider AND an explicit allowlist are given.
 * The provider is caller-supplied (S1 may wire an authorized UI/official API); this module
 * never reads cookies, bypasses controls, or performs any network I/O by itself.
 */
export async function collectEvidence ({provider = null, requests = [], allowlist = [], maxPerCall = 10} = {}) {
  if (!provider || typeof provider.fetch !== 'function') return {ok: false, reason: 'fetch-disabled', fetched: [], queued: []};
  if (!Array.isArray(allowlist) || allowlist.length === 0) return {ok: false, reason: 'allowlist-required', fetched: [], queued: []};
  const allowed = new Set(allowlist.map(String));
  const fetched = [], queued = [];
  for (const request of requests.slice(0, maxPerCall)) {
    if (!allowed.has(String(request.sourceId))) { queued.push({sourceId: request.sourceId, reason: 'not-allowlisted'}); continue; }
    try {
      const evidence = await provider.fetch(request);
      if (!evidence?.markdown || !evidence?.license) { queued.push({sourceId: request.sourceId, reason: 'incomplete-evidence'}); continue; }
      fetched.push({sourceId: request.sourceId, sha256: sha(evidence.markdown), license: evidence.license});
    } catch (e) { queued.push({sourceId: request.sourceId, reason: e.code || e.message || 'fetch-error'}); }
  }
  return {ok: fetched.length > 0, reason: fetched.length ? null : 'no-evidence-fetched', fetched, queued};
}

export const __test = {parsePaper, scratch, sha, renderRepaired, GAP_KINDS};
