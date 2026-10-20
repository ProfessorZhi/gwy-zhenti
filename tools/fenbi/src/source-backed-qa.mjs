#!/usr/bin/env node
// Source(Fenbi cache) -> PR88 archive per-question QA, metadata only.
// Reads local caches read-only and PR markdown via `git show` in memory. No network, no browser.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';

const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');
export const sha12 = (s) => sha256(s).slice(0, 12);
const strip = (h) => String(h ?? '')
  .replace(/<img\b[^>]*>/giu, ' ')
  .replace(/<(?:br|\/p|\/div|\/li|\/tr)\b[^>]*>/giu, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;/gu, ' ').replace(/&amp;/gu, '&').replace(/&lt;/gu, '<').replace(/&gt;/gu, '>')
  .replace(/\s+/g, ' ').trim();
export const norm = (s) => String(s ?? '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
const PH = /题目正在全力以赴征集|网友未回忆起|题目缺失/u;
const imgCount = (s) => (String(s ?? '').match(/<img\b|!\[[^\]]*\]\([^)]*\)/giu) || []).length;
const canonAnswer = (s) => {
  const x = strip(s).replace(/\s+/g, '');
  if (/^[A-D]$/u.test(x)) return x;
  if (/^(正确|对)$/u.test(x)) return '正确';
  if (/^(错误|错)$/u.test(x)) return '错误';
  const m = /(?:答案|选)\s*[:：]?\s*([A-D])/u.exec(x);
  return m ? m[1] : null;
};

export function variantKey(v) {
  const x = String(v ?? '').trim().toLowerCase();
  const map = { tongkao: 'tongkao', '统考': 'tongkao', county: 'county', '县级': 'county', xianji: 'county',
    fushengji: 'fushengji', '副省级': 'fushengji', dishiji: 'dishiji', '地市级': 'dishiji',
    xingzheng: 'xingzheng', '行政执法': 'xingzheng', a: 'a', 'a类': 'a', 'a卷': 'a', b: 'b', 'b类': 'b', 'b卷': 'b',
    c: 'c', 'c类': 'c', 'c卷': 'c', township: 'township', '乡镇': 'township' };
  return map[x] ?? x.replace(/类|卷$/u, '');
}

// ---- PR markdown parser: two house schemas ----
export function parsePrMarkdown(md) {
  const answerAt = md.search(/^##\s*答案与解析\s*$/mu);
  const qRegion = answerAt >= 0 ? md.slice(0, answerAt) : md;
  const detailRegion = answerAt >= 0 ? md.slice(answerAt) : md;
  const heads = [...qRegion.matchAll(/^#{2,4}\s*第\s*(\d+)\s*题[^\n]*$/gmu)]
    .map((m) => ({ n: Number(m[1]), start: m.index + m[0].length, index: m.index }));
  const OPT = /^\s{0,3}(?:[-*]\s+)?(?:\*\*)?([A-D])(?:\*\*)?\s*[.、．)．]\s*(.+)$/gmu;
  const questions = heads.map((h, i) => {
    const body = qRegion.slice(h.start, heads[i + 1]?.index ?? qRegion.length);
    const optAt = body.search(OPT);
    const stem = (optAt >= 0 ? body.slice(0, optAt) : body).trim();
    const opts = [...body.matchAll(OPT)].map((m) => ({ label: m[1], text: strip(m[2]) }));
    return { number: h.n, stem: strip(stem), opts, stub: PH.test(strip(stem)) || strip(stem).length === 0,
      img: imgCount(body) };
  });
  const answers = new Map();
  for (const m of detailRegion.matchAll(/<details>\s*<summary>\s*第\s*(\d+)\s*题[\s\S]*?<\/summary>([\s\S]*?)<\/details>/gmu)) {
    const n = Number(m[1]); const body = m[2];
    let ans = null;
    let mm = /\*\*答案\s*[（(]\s*([A-D])\s*[）)]\s*\*\*/u.exec(body) || /\*\*答案\*\*\s*[:：]?\s*([A-D])/u.exec(body);
    if (mm) ans = mm[1];
    else { const line = /^\s*([A-D])\s*$/mu.exec(body); if (line) ans = line[1]; }
    const expM = /\*\*(?:官方解析|参考解析|解析)\*\*\s*[:：]?\s*([\s\S]*?)(?=\n\s*\n\s*<\/details>|$)/u.exec(body);
    const explanation = expM ? strip(expM[1]) : '';
    answers.set(n, { ans, explanation, rawLen: body.length });
  }
  return { questions, answers, materials: (md.match(/^##\s*材料\s*\d+/gmu) || []).length,
    hasAnswerSection: answerAt >= 0, detailsBlocks: answers.size };
}

export function readSource(dir) {
  const doc = JSON.parse(fs.readFileSync(path.join(dir, 'document.json'), 'utf8'));
  const assets = Array.isArray(doc.assets) ? doc.assets : [];
  const questions = doc.questions.map((q) => {
    const opts = (q.options ?? []).map((o) => ({ label: String(o.label ?? ''), text: strip(o.contentHtml), raw: String(o.contentHtml ?? '') }));
    const stem = strip(q.contentHtml);
    return { number: Number(q.number), id: String(q.id ?? ''), stem, opts,
      answer: canonAnswer(q.answerHtml), explanation: strip(q.explanationHtml),
      stub: PH.test(stem) || stem.length === 0, img: imgCount(q.contentHtml) + (q.options ?? []).reduce((a, o) => a + imgCount(o.contentHtml), 0),
      materialIds: Array.isArray(q.materialIds) ? q.materialIds.length : 0 };
  });
  return { doc, questions, assets, materials: Array.isArray(doc.materials) ? doc.materials.length : 0 };
}

// ---- fingerprints ----
export function fingerprint(q) {
  const stem = norm(q.stem);
  const opts = q.opts.map((o) => norm(o.text));
  return { keyExact: sha256(stem + '||' + opts.join('|')), keySet: sha256(stem + '||' + [...opts].sort().join('|')),
    stemKey: sha256(stem), optSetKey: sha256([...opts].sort().join('|')), normStem: stem, normOpts: opts };
}
function uniqueIndex(list) {
  const m = new Map();
  for (const x of list) { const k = x.fp.keyExact; if (!m.has(k)) m.set(k, []); m.get(k).push(x); }
  return m;
}

function answerText(side, letter) {
  if (!letter || !/^[A-D]$/u.test(letter)) return null;
  const o = side.opts.find((x) => x.label === letter);
  return o ? norm(o.text) : null;
}

export function comparePaper({ sourceDir, prMarkdown, prPath, sourceId, expected = {} }) {
  const src = readSource(sourceDir);
  const pr = parsePrMarkdown(prMarkdown);
  const identity = src.doc.identity || {};
  const out = { schemaVersion: 1, evidenceSchema: 's3.source-pr-qa.v1', metadataOnly: true,
    sourceId: String(sourceId ?? identity.id), prPath, area: identity.area, year: identity.year,
    subject: identity.subject, variant: identity.variant,
    sourceDocSha12: sha12(fs.readFileSync(path.join(sourceDir, 'document.json'))), prBlobSha12: sha12(prMarkdown),
    sourceQ: src.questions.length, prQ: pr.questions.length, sourceStubQ: src.questions.filter((q) => q.stub).length,
    prStubQ: pr.questions.filter((q) => q.stub).length, prDetailsBlocks: pr.detailsBlocks,
    prHasAnswerSection: pr.hasAnswerSection, sourceMaterials: src.materials, prMaterials: pr.materials,
    assetsTotal: src.assets.length, assetsWithSha: src.assets.filter((a) => a.sha256).length,
    sourceNumbers: src.questions.map((q) => q.number),
    sourceStubNumbers: src.questions.filter((q) => q.stub).map((q) => q.number),
    strictMatches: [], prefixCandidates: [], prefixRejected: [],
    stemSameOptionDiff: [], ambiguous: [], unmatchedSource: [], unmatchedPr: [],
    answerSameStrict: [], answerConflictStrict: [], answerUnknownStrict: [],
    answerSameCandidate: [], answerConflictCandidate: [], answerUnknownCandidate: [],
    explanationSame: [], explanationDiff: [], explanationMissing: [],
    optionOrderChanged: [], imageQuestions: [], reasons: [],
    stubContentMatched: [], prStemExtraChars: {} };

  const sIdx = uniqueIndex(src.questions.map((q) => ({ side: 'src', q, fp: fingerprint(q) })));
  const prIdx = uniqueIndex(pr.questions.map((q) => ({ side: 'pr', q, fp: fingerprint(q) })));
  const sSetIdx = new Map(); const prSetIdx = new Map();
  const push = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
  for (const x of sIdx.values()) for (const y of x) push(sSetIdx, y.fp.keySet, y);
  for (const x of prIdx.values()) for (const y of x) push(prSetIdx, y.fp.keySet, y);

  // A prefix relation is only a *candidate*: archive markdown can append material or
  // instruction text after a short generic stem, which would otherwise inflate coverage.
  // The candidate never enters strict counts and its answer comparison is reported apart.
  const MIN_PREFIX = 12;
  const GENERIC = /^(下列说法|下列判断|下列选项|以下说法|以下哪项|由此可以推出|根据上述材料|根据这段文字|根据以上材料|上述文字|这段文字)/u;
  const eligibility = (fp, extra) => {
    if (fp.normStem.length < MIN_PREFIX) return 'stem-too-short';
    if (fp.normOpts.length !== 4) return 'option-count-not-4';
    if (fp.normOpts.some((x) => !x)) return 'empty-option-text';
    if (new Set(fp.normOpts).size !== fp.normOpts.length) return 'duplicate-option-text';
    if (GENERIC.test(fp.normStem) && fp.normStem.length < 24) return 'generic-stem';
    if (extra > 3 * fp.normStem.length + 20) return 'suffix-dominates-stem';
    return null;
  };
  const prByNumber = new Map(pr.questions.map((p) => [p.number, fingerprint(p)]));
  const srcExact = new Set(src.questions.map((q) => fingerprint(q).keyExact));
  const exactPrNumbers = new Set(pr.questions.filter((p) => srcExact.has(prByNumber.get(p.number).keyExact)).map((p) => p.number));
  const prefixCand = new Map(); // srcNumber -> [prNumber]
  const reverseCand = new Map(); // prNumber -> [srcNumber]
  for (const q of src.questions) {
    const fp = fingerprint(q);
    if (fp.normOpts.length !== 4 || fp.normOpts.some((x) => !x)) continue;
    const hits = [];
    for (const p of pr.questions) {
      if (exactPrNumbers.has(p.number)) continue;
      const pf = prByNumber.get(p.number);
      if (pf.normOpts.length !== fp.normOpts.length) continue;
      if (pf.normOpts.some((o, i) => o !== fp.normOpts[i])) continue;
      const ps = pf.normStem; const ss = fp.normStem;
      if (Math.min(ps.length, ss.length) < MIN_PREFIX) continue;
      if (ps.startsWith(ss) || ss.startsWith(ps)) hits.push(p.number);
    }
    if (hits.length) { prefixCand.set(q.number, hits); for (const n of hits) push(reverseCand, n, q.number); }
  }

  const usedPr = new Set();
  const compareAnswer = (q, prQ, bucket) => {
    const sTxt = answerText(q, q.answer); const pTxt = answerText(prQ, pr.answers.get(prQ.number)?.ans ?? null);
    if (sTxt && pTxt) out[bucket === 'strict' ? (sTxt === pTxt ? 'answerSameStrict' : 'answerConflictStrict')
      : (sTxt === pTxt ? 'answerSameCandidate' : 'answerConflictCandidate')].push(q.number);
    else out[bucket === 'strict' ? 'answerUnknownStrict' : 'answerUnknownCandidate'].push(q.number);
  };
  for (const q of src.questions) {
    const fp = fingerprint(q);
    const exact = sIdx.get(fp.keyExact) ?? [];
    const setHits = sSetIdx.get(fp.keySet) ?? [];
    let prHit = null; let orderChanged = false; let status = null;
    if (exact.length === 1 && (prIdx.get(fp.keyExact) ?? []).length === 1) { prHit = (prIdx.get(fp.keyExact) ?? [])[0]; status = 'exact_unique'; }
    else if (setHits.length === 1 && (prSetIdx.get(fp.keySet) ?? []).length === 1 && !usedPr.has((prSetIdx.get(fp.keySet) ?? [])[0]?.q.number)) {
      prHit = (prSetIdx.get(fp.keySet) ?? [])[0]; orderChanged = true; status = 'option_diff';
    }
    if (!prHit) {
      const cands = prefixCand.get(q.number) ?? [];
      const only = cands.length === 1 ? cands[0] : null;
      if (only != null && (reverseCand.get(only) ?? []).length === 1 && !usedPr.has(only)) {
        const prEntry = pr.questions.find((p) => p.number === only);
        const ps = prByNumber.get(only).normStem; const ss = fp.normStem;
        const why = eligibility(fp, ps.length - ss.length);
        if (!why) {
          prHit = { side: 'pr', q: prEntry, fp: prByNumber.get(only) };
          status = 'prefix_candidate';
          out.prStemExtraChars[q.number] = ps.length - ss.length;
        } else out.prefixRejected.push({ number: q.number, reason: why });
      }
    }
    if (!prHit) {
      if (q.stub) continue;
      const stemHits = pr.questions.filter((p) => fingerprint(p).stemKey === fp.stemKey);
      if (stemHits.length === 1) { out.stemSameOptionDiff.push(q.number); status = 'option_diff'; }
      else { out.unmatchedSource.push(q.number); status = 'unmatched'; }
      continue;
    }
    if (usedPr.has(prHit.q.number)) { out.ambiguous.push(q.number); continue; }
    usedPr.add(prHit.q.number);
    if (q.stub) { out.stubContentMatched.push(q.number); continue; }
    if (status === 'exact_unique') out.strictMatches.push(q.number);
    else if (status === 'prefix_candidate') out.prefixCandidates.push(q.number);
    else if (orderChanged) out.optionOrderChanged.push(q.number);
    compareAnswer(q, prHit.q, status === 'exact_unique' ? 'strict' : 'candidate');
    // explanations are only scoped to strict exact matches
    if (status === 'exact_unique') {
      const sExp = norm(q.explanation); const pExp = norm(pr.answers.get(prHit.q.number)?.explanation ?? '');
      if (!sExp || !pExp) out.explanationMissing.push(q.number);
      else if (sExp === pExp) out.explanationSame.push(q.number);
      else out.explanationDiff.push(q.number);
    }
    if (q.img || prHit.q.img) out.imageQuestions.push(q.number);
  }
  out.unmatchedPr = pr.questions.filter((p) => !usedPr.has(p.number)).map((p) => p.number);
  const strict = out.strictMatches.length;
  out.strictMatchCount = strict;
  out.prefixCandidateCount = out.prefixCandidates.length;
  out.optionDiffCount = out.stemSameOptionDiff.length + out.optionOrderChanged.length;
  out.unmappedQuestionCount = out.unmatchedSource.length;
  out.sourceStubCount = src.questions.filter((q) => q.stub).length;
  out.matchStatusCounts = { exact_unique: strict, prefix_candidate: out.prefixCandidates.length,
    option_diff: out.optionDiffCount, unmatched: out.unmatchedSource.length,
    source_stub: out.sourceStubCount, ambiguous: out.ambiguous.length };
  out.partitionSum = strict + out.prefixCandidates.length + out.optionDiffCount + out.unmatchedSource.length + out.sourceStubCount + out.ambiguous.length;
  out.partitionConsistent = out.partitionSum === src.questions.length;
  out.matchStrength = 'strict-exact';
  out.legacyStrongMatchesInclusive = strict + out.prefixCandidates.length + out.optionDiffCount;
  out.coverageClaimEligible = false;
  out.strictAnswerComparable = out.answerSameStrict.length + out.answerConflictStrict.length;
  out.candidateAnswerComparable = out.answerSameCandidate.length + out.answerConflictCandidate.length;
  out.explanationScope = 'strict-exact';
  out.qaComplete = strict === src.questions.length && src.questions.length === pr.questions.length &&
    out.answerConflictStrict.length === 0 && out.answerUnknownStrict.length === 0 &&
    out.explanationMissing.length === 0 && out.stemSameOptionDiff.length === 0 && out.optionOrderChanged.length === 0 &&
    out.prefixCandidates.length === 0 && out.ambiguous.length === 0 && out.sourceStubCount === 0;
  out.qaVerdict = out.qaComplete ? 'PENDING_REVIEW_STRONG_MATCH' : 'PENDING_REVIEW';
  out.structuralOnly = !out.qaComplete;
  out.imageShaEvidence = out.imageQuestions.length === 0 ? 'not-applicable'
    : (src.assets.length > 0 && src.assets.every((a) => a.sha256) ? 'source-side-sha-present' : 'insufficient');
  out.rightsStatus = 'unverified';
  out.publishable = false;
  out.independentQa = 0;
  if (expected.docSha12 && expected.docSha12 !== out.sourceDocSha12) out.reasons.push('stale-source-sha');
  out.revision = sha12(JSON.stringify({ doc: out.sourceDocSha12, pr: out.prBlobSha12,
    strict: out.answerSameStrict.length, conflicts: out.answerConflictStrict.length, matched: strict }));
  return out;
}

export function selectPrPath(manifest, identity) {
  const rows = manifest.filter((r) => r.area === identity.area && String(r.year) === String(identity.year) &&
    r.subject === '行测' && variantKey(r.paper_type) === variantKey(identity.variant));
  if (rows.length !== 1) return { ok: false, reason: rows.length ? 'AMBIGUOUS_PR_PATH' : 'NO_PR_MATCH', candidates: rows.map((r) => r.path) };
  return { ok: true, path: rows[0].path, declaredQ: rows[0].declared_questions };
}

export function findSourceDir(papersDir, sourceId) {
  const d = fs.readdirSync(papersDir).find((x) => x.endsWith('-' + sourceId));
  return d ? path.join(papersDir, d) : null;
}
export function gitShow(repo, sha, rel) {
  return execFileSync('git', ['-C', repo, 'show', `${sha}:${rel}`], { maxBuffer: 64 * 1024 * 1024 }).toString('utf8');
}
