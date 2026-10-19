#!/usr/bin/env node
/** Deterministic local-only Fenbi cache -> Markdown candidate pipeline. */
import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseRepositoryPaper, normalizeComparisonText } from './align.mjs';
import { isCollectionStub, validateDocument } from './validate.mjs';
import { renderCandidate } from './render.mjs';

const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const subjectName = q => q === 'xingce' ? '行测' : q === 'shenlun' ? '申论' : null;
const safeName = v => /^[\w\p{Script=Han}-]{1,70}$/u.test(String(v));
const text = html => normalizeComparisonText(html).strict;
const core = value => text(value).replace(/\s*⟦IMAGE⟧\s*/gu, '').trim();
const fp = q => [text(q.contentHtml), ...(q.options || []).flatMap(o => [o.label, text(o.contentHtml)])].join('\u0000');
const isStub = q => isCollectionStub(text(q.contentHtml));
const isUsable = q => q && !isStub(q) && (core(q.contentHtml).length >= 12 || /<(?:img|image)\b/iu.test(q.contentHtml || '') || (core(q.contentHtml).length > 0 && (q.options || []).filter(o => text(o.contentHtml)).length >= 2));
const flat = value => typeof value === 'string' ? value.trim() : '';

/**
 * Load a source answer shard written by the collector, keyed by the STABLE question id.
 * Accepted shapes (all metadata-tolerant, but never number-addressed):
 *   { answers: [{ questionId, answerHtml|answer, explanationHtml|explanation }] }
 *   { items:   [ ...same... ] }
 *   { "<stableQuestionId>": { answerHtml|answer, explanationHtml|explanation } }
 * A shard that carries no usable id-keyed entries is reported, not guessed at.
 */
export function loadAnswerShard(entries) {
  const map = new Map();
  const push = (id, value) => {
    const key = flat(id);
    if (!key || !value || typeof value !== 'object') return;
    const answerHtml = flat(value.answerHtml ?? value.answer ?? value.answerText);
    const explanationHtml = flat(value.explanationHtml ?? value.explanation ?? value.analysis);
    if (!answerHtml && !explanationHtml) return;
    map.set(key, { answerHtml, explanationHtml, source: flat(value.source) || 'fenbi-explanation-page' });
  };
  if (Array.isArray(entries)) {
    for (const entry of entries) push(entry?.questionId ?? entry?.qid ?? entry?.id, entry);
  } else if (entries && typeof entries === 'object') {
    const list = Array.isArray(entries.answers) ? entries.answers : Array.isArray(entries.items) ? entries.items : null;
    if (list) for (const entry of list) push(entry?.questionId ?? entry?.qid ?? entry?.id, entry);
    else for (const [key, value] of Object.entries(entries)) push(key, value);
  }
  return map;
}

/** Read the first `answers*.json` shard in a paper cache directory. Absent is a normal state. */
export async function readAnswerShard(cacheDir, fsImpl = fs) {
  let names;
  try { names = (await fsImpl.readdir(cacheDir)).filter(n => /^answers.*\.json$/iu.test(n)).sort(); }
  catch { return { map: new Map(), file: null, sha256: null }; }
  if (!names.length) return { map: new Map(), file: null, sha256: null };
  const file = names[0];
  const raw = await fsImpl.readFile(path.join(cacheDir, file));
  let parsed;
  try { parsed = JSON.parse(raw); } catch { return { map: new Map(), file, sha256: sha(raw), invalid: 'answer-shard-not-json' }; }
  return { map: loadAnswerShard(parsed), file, sha256: sha(raw) };
}
const hasExternalImage = value => /<(?:img|image)\b|!\[[^\]]*\]\(/iu.test(flat(value));

/**
 * Option labels are normalised only when the evidence itself is checkable:
 *   1. the matched legacy question holds the same options in the same order and already carries
 *      valid distinct A–Z labels → adopt those labels (content identity is the evidence);
 *   2. a two-option judgement question that the repository block declares as 判断题 → A/B, which is
 *      the presentation convention for the 正确/错误 pair, not a content claim.
 * Anything else is left untouched and reported as unverified. Labels are never invented for a
 * four-option question just because four options usually mean A–D.
 */
export function normalizeOptionLabels(question, ancestor, legacyBlockText = '') {
  const options = Array.isArray(question?.options) ? question.options : [];
  const isLabels = labels => labels.length === options.length && labels.every(l => /^[A-Z]$/u.test(l))
    && new Set(labels).size === labels.length;
  const current = options.map(o => flat(o.label));
  if (!options.length || isLabels(current)) return { labels: current, evidence: null };
  if (ancestor && Array.isArray(ancestor.options) && ancestor.options.length === options.length) {
    const sameContent = ancestor.options.every((o, i) => text(o.contentHtml) === text(options[i].contentHtml));
    const inherited = ancestor.options.map(o => flat(o.label));
    if (sameContent && isLabels(inherited)) return { labels: inherited, evidence: 'legacy-content-match' };
  }
  // The option contents themselves can declare the question type: a two-option 正确/错误 pair is a
  // true/false question, and A/B is only its presentation convention. This is checkable text, not a
  // guess, and it does not touch four-option questions.
  const pair = options.map(o => text(o.contentHtml)).sort().join('\u0000');
  if (options.length === 2 && pair === ['正确', '错误'].sort().join('\u0000')) {
    return { labels: ['A', 'B'], evidence: 'judgement-option-pair' };
  }
  const judgement = /判断题|判断下列|说法是否正确/u.test(String(legacyBlockText || ''))
    || /判断题/u.test(String(ancestor?.contentHtml || ''));
  if (options.length === 2 && judgement) return { labels: ['A', 'B'], evidence: 'judgement-question-convention' };
  return { labels: current, evidence: null };
}

/**
 * Source images referenced by the captured document but not present as a downloaded, hashed asset.
 * A missing source image cannot be rendered and must be reported per question, not thrown as a
 * generic renderer failure.
 */
export function unresolvedSourceImages(document) {
  const assets = new Set((document?.assets ?? [])
    .filter(a => a.status === 'downloaded' && a.localPath && a.sha256).map(a => String(a.url)));
  const numbers = [];
  let count = 0;
  const base = document?.source?.url;
  const scan = (html, number) => {
    for (const ref of normalizeComparisonText(html).images) {
      let absolute;
      try { absolute = new URL(ref, base).toString(); } catch { absolute = null; }
      if (!absolute || !assets.has(absolute)) { count++; if (!numbers.includes(number)) numbers.push(number); }
    }
  };
  for (const q of document?.questions ?? []) {
    for (const key of ['contentHtml', 'answerHtml', 'explanationHtml', 'requirementsHtml']) scan(q?.[key] || '', q?.number);
    for (const option of q?.options ?? []) scan(option?.contentHtml || '', q?.number);
  }
  return { count, numbers };
}

export function assemble(document, oldMarkdown = '', answerShard = new Map()) {
  const issues = [];
  if (document?.schemaVersion !== 1 || !Array.isArray(document.questions) || !Array.isArray(document.assets)) throw Error('invalid-source-document');
  const id = document.identity || {};
  if (!safeName(id.area) || !safeName(id.id) || !safeName(id.variant) || !subjectName(id.subject) || !Number.isInteger(Number(id.year))) throw Error('invalid-paper-identity');
  const expected = document.expected?.questions;
  if (!Number.isInteger(expected) || expected < 1 || expected !== document.questions.length) issues.push('question-count-mismatch');
  const sorted = [...document.questions].sort((a,b) => a.number-b.number);
  if (sorted.some((q,i) => q.number !== i+1)) issues.push('question-numbers-not-contiguous');
  const old = oldMarkdown ? parseRepositoryPaper(oldMarkdown).questions : [];
  const byFp = new Map();
  for (const candidate of old) {
    const key = fp(candidate);
    if (!byFp.has(key)) byFp.set(key, []);
    byFp.get(key).push(candidate);
  }
  const map = new Map(), legacyUsed = new Set();
  for (const q of sorted) {
    if (isStub(q) || !isUsable(q)) continue;
    const candidates = byFp.get(fp(q)) || [];
    if (candidates.length === 1 && !legacyUsed.has(candidates[0])) {
      map.set(q, candidates[0]); legacyUsed.add(candidates[0]);
    }
  }
  const direct = [...map].filter(([a,b]) => a.number === b.number).length;
  const numberingStable = direct >= Math.max(3, Math.ceil(sorted.length * .6)) && direct / Math.max(1,map.size) >= .85;
  const merged = [];
  const counters = {sourceQuestions:sorted.length,stubSlots:0,inheritedStubs:0,unresolvedStubs:0,oldAnswersInherited:0,oldExplanationsInherited:0,sourceAnswers:0,sourceAnswersFromShard:0,sourceExplanationsFromShard:0,answerUnknown:0,oldAnswersUnmapped:0,mappedQuestions:map.size,optionsNormalized:0};
  for (const q of sorted) {
    let current={...q,options:(q.options || []).map(o=>({...o})),answerOrigin:flat(q.answerHtml)?'fenbi':'unknown',explanationOrigin:flat(q.explanationHtml)?'fenbi':'unknown'};
    // Source answers arrive keyed by the stable question id. A number is never used as a key here:
    // an id that does not match stays unmatched and visible instead of silently attaching.
    const shard = answerShard instanceof Map ? answerShard.get(flat(q.id)) : null;
    if (shard) {
      if (!flat(current.answerHtml) && shard.answerHtml) { current.answerHtml=shard.answerHtml; current.answerOrigin=shard.source; counters.sourceAnswersFromShard++; }
      if (!flat(current.explanationHtml) && shard.explanationHtml) { current.explanationHtml=shard.explanationHtml; current.explanationOrigin=shard.source; counters.sourceExplanationsFromShard++; }
    }
    let ancestor = map.get(q);
    if (isStub(q)) {
      counters.stubSlots++;
      const exactNumber = old.filter(x => x.number === q.number && isUsable(x));
      if (numberingStable && exactNumber.length === 1 && !legacyUsed.has(exactNumber[0])) {
        ancestor=exactNumber[0];legacyUsed.add(ancestor);counters.inheritedStubs++;
        current.legacyFallbackNumber=ancestor.number;
        current.legacyFallbackMarkdown=true;
      } else {
        counters.unresolvedStubs++;issues.push('source-stub-no-safe-legacy-fallback:'+q.number);
      }
    }
    if (!isStub(q) && !isUsable(q)) issues.push('question-body-empty:'+q.number);
    if (!Array.isArray(q.options) || (id.subject==='xingce' && q.options.length<2)) issues.push('options-missing:'+q.number);
    if (current.legacyFallbackMarkdown) {
      // Original repository Markdown blocks cannot be passed through an HTML-only renderer.
      current.contentHtml='';current.options=[];current.answerHtml='';current.explanationHtml='';
    }
    const labelFix = normalizeOptionLabels(current, ancestor, extractLegacyBlock(oldMarkdown, q.number) || '');
    if (labelFix.evidence) {
      current.options = current.options.map((o, i) => ({ ...o, label: labelFix.labels[i] }));
      current.optionLabelEvidence = labelFix.evidence;
      counters.optionsNormalized++;
    } else if (current.options.length && labelFix.labels.some(l => !/^[A-Z]$/u.test(l))) {
      issues.push('option-labels-unverified:' + q.number);
    }
    if (flat(current.answerHtml)) counters.sourceAnswers++;
    else if (ancestor && flat(ancestor.answerHtml) && !hasExternalImage(ancestor.answerHtml)) {
      current.answerHtml=ancestor.answerHtml;current.answerOrigin='original-repository';counters.oldAnswersInherited++;
    } else counters.answerUnknown++;
    if (!flat(current.explanationHtml) && ancestor && flat(ancestor.explanationHtml) && !hasExternalImage(ancestor.explanationHtml)) {
      current.explanationHtml=ancestor.explanationHtml;current.explanationOrigin='original-repository';counters.oldExplanationsInherited++;
    }
    merged.push(current);
  }
  counters.oldAnswersUnmapped = old.filter(q=>!legacyUsed.has(q) && flat(q.answerHtml)).length;
  if (answerShard instanceof Map && answerShard.size) {
    const captured = new Set(sorted.map(q => flat(q.id)));
    counters.answerShardEntries = answerShard.size;
    counters.answerShardUnmatched = [...answerShard.keys()].filter(id => !captured.has(id)).length;
    if (counters.answerShardUnmatched) issues.push('answer-shard-ids-unmatched:'+counters.answerShardUnmatched);
  }
  if (counters.oldAnswersUnmapped) issues.push('unmapped-legacy-answers-retained-separately');
  const prepared={...document,questions:merged};
  return {prepared,legacy:old,numberingStable,issues:[...new Set(issues)],counters};
}

function extractLegacyBlock(oldMarkdown, number) {
  const body = oldMarkdown.split(/^#{1,6}\s+答案与解析\s*$/mu)[0];
  const heads=[...body.matchAll(/^#{1,6}\s+第\s*(\d+)\s*题[^\n]*$/gmu)];
  const found=heads.filter(h=>Number(h[1])===number);
  if(found.length!==1)return null;
  const h=found[0], next=heads.find(x=>x.index>h.index);
  return body.slice(h.index,next?.index ?? body.length).trim();
}

const MD_IMAGE = /!\[([^\]]*)\]\((?:<([^>]+)>|([^\s)]+))(?:\s+["'][^"']*["'])?\)/gu;
const HTML_IMAGE = /<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["'][^>]*>/giu;

/** Find the image references inside one legacy block, in document order. */
export function legacyImageRefs(block) {
  const refs = [];
  for (const m of String(block || '').matchAll(MD_IMAGE)) refs.push({ kind: 'markdown', ref: m[2] || m[3] });
  for (const m of String(block || '').matchAll(HTML_IMAGE)) refs.push({ kind: 'html', ref: m[1] });
  return refs;
}

/**
 * Rewrite the image references of an inherited legacy block so they point at copies held beside the
 * candidate. `rebase` decides what each reference becomes; when it cannot resolve one, the block is
 * left as-is and the number is reported instead of pretending the image passed.
 */
export function rebaseLegacyBlock(block, rebase) {
  let unresolved = 0;
  const replaced = new Map();
  const next = String(block || '').replace(MD_IMAGE, (whole, alt, a, b) => {
    const hit = rebase(a || b);
    if (!hit?.href) { unresolved++; return whole; }
    replaced.set(a || b, hit.href);
    return `![${alt}](${hit.href})`;
  }).replace(HTML_IMAGE, (whole, src) => {
    const hit = rebase(src);
    if (!hit?.href) { unresolved++; return whole; }
    replaced.set(src, hit.href);
    return whole.replace(src, hit.href);
  });
  return { block: next, unresolved, images: [...replaced.values()] };
}

export function renderIngest(assembly, oldMarkdown='', imagePrefix='assets', options={}) {
  const draft=assembly.prepared;
  const markers=draft.questions.filter(q=>q.legacyFallbackMarkdown);
  const renderDocument={...draft, questions:draft.questions.map(q=>q.legacyFallbackMarkdown?{...q,contentHtml:'LEGACYFALLBACK'+q.number,options:[]} : q)};
  let md=renderCandidate(renderDocument,{status:'complete'}, { imagePrefix });
  for(const q of markers){
    const rawBlock=extractLegacyBlock(oldMarkdown,q.number);
    if(!rawBlock) throw Error('legacy-block-not-extractable:'+q.number);
    let block=rawBlock;
    if(/!\[[^\]]*\]\(|<img\b/iu.test(rawBlock)){
      if(typeof options.rebaseImage!=='function'){
        // No resolver supplied: keep the reference and say so rather than claiming it passed.
        assembly.issues.push('legacy-image-references-need-rebase:'+q.number);
      }else{
        const rebased=rebaseLegacyBlock(rawBlock, ref=>options.rebaseImage(ref,q.number));
        if(rebased.unresolved){assembly.issues.push('legacy-image-missing:'+q.number+':'+rebased.unresolved);}
        else{block=rebased.block;(assembly.legacyImages ||= []).push(...rebased.images);(assembly.counters.legacyImagesRebound ??= 0);assembly.counters.legacyImagesRebound+=rebased.images.length;}
      }
    }
    const headingRe=new RegExp('^### 第 '+q.number+' 题\\s*\\n\\s*LEGACYFALLBACK'+q.number+'\\s*$','mu');
    if(!headingRe.test(md))throw Error('legacy-fallback-heading-not-found:'+q.number);
    md=md.replace(headingRe,block+'\n\n> 本题来源：原库（粉笔暂未征集）');
  }
  if(assembly.counters.oldAnswersUnmapped) md += '\n\n## 未自动迁移的旧版答案\n\n旧版完整内容保留在本地候选目录中的 legacy-original.md。因题目身份未唯一确认，这些答案没有按旧题号附加到新题目。\n';
  return md+'\n';
}

export function structureGrade(assembly, markdownText, validation) {
  const blockers=assembly.issues.filter(x=>!x.startsWith('unmapped-legacy-answers-retained-separately'));
  const doc=assembly.prepared, q=doc.questions;
  if(!q.length)blockers.push('no-questions');
  if(q.some(x=>isStub(x) && !x.legacyFallbackMarkdown))blockers.push('unremoved-source-stub');
  if(doc.assets.some(x=>x.status!=='downloaded'||!x.localPath||!x.sha256))blockers.push('asset-not-ready');
  if(validation?.dimensions?.images?.status !== 'complete')blockers.push('image-validation-not-complete');
  for(const issue of validation?.issues || []) if(['questions','materials'].includes(issue.dimension) && !((issue.code==='question-body-empty'||issue.code==='question-body-placeholder'||issue.code==='options-missing') && q.some(item=>item.legacyFallbackMarkdown && item.number===issue.number))) blockers.push('source-structure:'+issue.code);
  if(!markdownText.includes('## 题目'))blockers.push('missing-questions-heading');
  if(!markdownText.includes('### 第 1 题') && !/^## 第 1 题/mu.test(markdownText))blockers.push('missing-first-question');
  if(q.some(x=>x.legacyFallbackMarkdown) && !markdownText.includes('本题来源：原库'))blockers.push('legacy-fallback-not-rendered');
  return {grade:blockers.length?'C':'A',blockers:[...new Set(blockers)],counts:assembly.counters,
    answerCompleteness:'per-question; unknown does not claim correctness',
    note:'A=local structural candidate only; not official truth or permission to publish'};
}

const REASON_CODES = Object.freeze({
  'question-count-mismatch':'E_COUNT_MISMATCH',
  'question-numbers-not-contiguous':'E_NUMBER_NOT_CONTIGUOUS',
  'unmapped-legacy-answers-retained-separately':'W_LEGACY_ANSWERS_UNMAPPED',
  'unremoved-source-stub':'E_STUB_UNRESOLVED',
  'asset-not-ready':'E_ASSET_NOT_READY',
  'image-validation-not-complete':'E_IMAGE_VALIDATION',
  'no-questions':'E_NO_QUESTIONS',
  'missing-questions-heading':'E_RENDER_HEADING',
  'missing-first-question':'E_RENDER_FIRST',
  'legacy-fallback-not-rendered':'E_LEGACY_NOT_RENDERED',
});

/** Map an internal issue string to a stable, machine-readable reason code. */
export function reasonCode(issue) {
  const [head, ...rest] = String(issue).split(':');
  switch (head) {
    case 'source-stub-no-safe-legacy-fallback': return 'E_STUB_NO_SAFE_FALLBACK';
    case 'question-body-empty': return 'E_QUESTION_BODY_EMPTY';
    case 'question-body-placeholder': return 'E_QUESTION_BODY_PLACEHOLDER';
    case 'options-missing': return 'E_OPTIONS_MISSING';
    case 'option-labels-unverified': return 'E_OPTION_LABELS_UNVERIFIED';
    case 'legacy-image-references-need-rebase': return 'E_LEGACY_IMAGE_NOT_REBASED';
    case 'legacy-image-missing': return 'E_LEGACY_IMAGE_MISSING';
    case 'source-image-unresolved': return 'E_SOURCE_IMAGE_UNRESOLVED';
    case 'answer-shard-ids-unmatched': return 'W_ANSWER_SHARD_UNMATCHED';
    case 'source-structure': return 'E_SOURCE_STRUCTURE_' + rest.join(':').toUpperCase().replace(/[^A-Z0-9]+/gu, '_');
    default: return REASON_CODES[head] || ('E_' + head.toUpperCase().replace(/[^A-Z0-9]+/gu, '_'));
  }
}

function parseCli(argv) {
  const opts={write:false,limit:100};
  for(let i=0;i<argv.length;i++){
    const k=argv[i];
    if(k==='--write')opts.write=true;
    else if(['--source-root','--repo-root','--limit','--only','--prior-ref'].includes(k)){
      if(!argv[++i])throw Error('missing-value:'+k);
      opts[k.slice(2).replaceAll('-','_')]=argv[i];
    }else throw Error('unknown-option:'+k);
  }
  opts.limit=Number(opts.limit);
  // `--only` restricts a run to named papers, so an incremental batch never re-processes work that
  // already has a candidate. Names are matched exactly; an empty selection is an error, not "all".
  if(opts.only!==undefined){
    opts.only=String(opts.only).split(',').map(x=>x.trim()).filter(Boolean);
    if(!opts.only.length)throw Error('empty-only');
  }
  if(!Number.isInteger(opts.limit)||opts.limit<1||opts.limit>1000)throw Error('invalid-limit');
  return opts;
}

export async function runBatch({sourceRoot,repoRoot=APP_ROOT,limit=100,write=false,only=null,priorRef=null}={}){
  const source=await fs.realpath(sourceRoot||path.join(repoRoot,'work/fenbi/papers'));
  const repo=await fs.realpath(repoRoot);
  const dest=path.join(repo,'work/fenbi/batch-ingest');
  const wanted=Array.isArray(only)&&only.length?new Set(only):null;
  const folders=(await fs.readdir(source,{withFileTypes:true})).filter(x=>x.isDirectory()&&safeName(x.name)&&(!wanted||wanted.has(x.name))).map(x=>x.name).sort().slice(0,limit);
  const receipts=[];
  for(const name of folders){
    try{
      const base=path.join(source,name),real=await fs.realpath(base);
      if(!real.startsWith(source+path.sep))throw Error('source-path-escape');
      const raw=await fs.readFile(path.join(base,'document.json'));
      const doc=JSON.parse(raw);
      const shard=await readAnswerShard(base);
      const id=doc.identity||{},area=id.area==='国考'?'国考':'省考/'+id.area;
      const sub=subjectName(id.subject);
      if(!sub||!safeName(id.id)||!safeName(id.variant)||!Number.isInteger(Number(id.year)))throw Error('bad-identity');
      const rel=path.posix.join(area,String(id.year),sub+'-'+id.variant+'.md');
      const priorFile=path.join(repo,rel);
      let prior='';try{prior=await fs.readFile(priorFile,'utf8')}catch(e){if(e.code!=='ENOENT')throw e}
      // A sparse worktree silently omits tracked files. The prior Markdown is a rendering input, so
      // it is never substituted from Git here — but the *old file digest* that the release gate needs
      // is exact either way, so it is taken from the Git object and the gap is reported explicitly.
      let gitPriorSha256=null;
      if(!prior && priorRef){
        try{
          const blob=execFileSync('git',['-C',repo,'cat-file','blob',`${priorRef}:${rel}`],{maxBuffer:64*1024*1024,stdio:['ignore','pipe','ignore']});
          gitPriorSha256=sha(blob);
        }catch{/* absent in the ref too: the target is a new file, not a replacement. */}
      }
      const assembly=assemble(doc,prior,shard.map);
      const verdict=await validateDocument(assembly.prepared,{assetRoot:path.join(base,'assets')});
      const prefix='assets-fenbi-'+id.id;
      // Rebase inherited legacy images onto copies held beside this candidate. Every copy is
      // verified against the SHA of the bytes actually read from the repository tree.
      const pendingImages=new Map();
      const rebaseImage=(ref)=>{
        let abs;
        try{abs=path.resolve(path.dirname(priorFile),decodeURI(ref));}catch{return null;}
        if(!abs.startsWith(repo+path.sep))return null;
        let bytes;
        try{bytes=fsSync.readFileSync(abs);}catch{return null;}
        const digest=sha(bytes),name=digest.slice(0,16)+path.extname(abs).toLowerCase();
        const href=prefix+'-legacy/'+name;
        pendingImages.set(href,{bytes,sha256:digest,from:abs});
        return {href};
      };
      // Report unresolved source images before rendering: the renderer cannot place them, and a bare
      // "Unresolved image" exception would lose both the question numbers and the reason code.
      const unresolved=unresolvedSourceImages(doc);
      if(unresolved.count)assembly.issues.push('source-image-unresolved:'+unresolved.count+':'+unresolved.numbers.slice(0,8).join(','));
      const md=unresolved.count?'':renderIngest(assembly,prior,prefix,{rebaseImage});
      const grade=structureGrade(assembly,md,verdict);
      const answerNumbers=assembly.prepared.questions.filter(q=>flat(q.answerHtml)).map(q=>q.number);
      const inputFingerprint=sha(JSON.stringify({source:sha(raw),prior:prior?sha(prior):null,answers:shard.sha256??null}));
      // A warning, never a blocker: the candidate is still structurally A, but the operator must know
      // that the prior body was not available on disk, so inheritance could not be applied.
      const warnings=[];
      if(!prior && gitPriorSha256)warnings.push('W_PRIOR_MISSING_FROM_WORKTREE:'+rel);
      const oldSha256=prior?sha(prior):gitPriorSha256;
      const row={name,sourceId:String(id.id),area:id.area,year:Number(id.year),variant:id.variant,subject:id.subject,path:rel,grade:grade.grade,issues:grade.blockers,reasonCodes:[...new Set(grade.blockers.map(reasonCode))],counts:grade.counts,answerNumbers,markdownSha256:sha(md),oldSha256,warnings,oldSha256Source:prior?'worktree':gitPriorSha256?'git-blob:'+priorRef:null,sourceSha256:sha(raw),answerShard:shard.file,inputFingerprint};
      if(write){
        const out=path.join(dest,name);await fs.mkdir(out,{recursive:true,mode:0o700});
        // Incremental: an unchanged input whose previous candidate was already A is not re-verified.
        const prevReceipt=JSON.parse(await fs.readFile(path.join(out,'receipt.json'),'utf8').catch(()=>'null'));
        // Skip only when the inputs AND the candidate on disk are unchanged; a tampered or missing
        // paper.md must fall through to the immutability check instead of being skipped.
        const prevMd=await fs.readFile(path.join(out,'paper.md'),'utf8').catch(()=>null);
        if(prevReceipt?.grade==='A' && prevReceipt.inputFingerprint===inputFingerprint
           && prevReceipt.markdownSha256===row.markdownSha256
           && prevMd!==null && sha(prevMd)===prevReceipt.markdownSha256){
          receipts.push({...prevReceipt,skipped:'unchanged-input'});continue;
        }
        const existing=await fs.readFile(path.join(out,'paper.md')).catch(e=>e.code==='ENOENT'?null:Promise.reject(e));
        if(existing){
          if(sha(existing)!==sha(md))throw Error('existing-candidate-differs');
        }else{
          const assetOut=path.join(out,prefix);await fs.mkdir(assetOut,{recursive:true,mode:0o700});
          const copied=new Set();
          for(const asset of doc.assets){
            // A not-downloaded asset is already a structural blocker (C) via structureGrade; copying is
            // simply skipped here so the candidate still records the precise reason instead of throwing.
            if(!asset.localPath || !asset.sha256 || asset.status!=='downloaded')continue;
            const root=path.resolve(base,'assets');
            const checked=await fs.realpath(path.resolve(root,asset.localPath));
            if(!checked.startsWith(root+path.sep))throw Error('asset-path-escape');
            const img=asset.localPath.replaceAll('\\','/');
            if(img.startsWith('/') || img.split('/').includes('..'))throw Error('asset-path-invalid');
            if(copied.has(img))continue;
            const bytes=await fs.readFile(checked);
            if(sha(bytes)!==asset.sha256)throw Error('asset-sha-mismatch');
            const target=path.join(assetOut,img);await fs.mkdir(path.dirname(target),{recursive:true,mode:0o700});
            await fs.writeFile(target,bytes,{flag:'wx',mode:0o600});copied.add(img);
          }
          for(const [href,img] of pendingImages){
            const target=path.join(out,href);
            await fs.mkdir(path.dirname(target),{recursive:true,mode:0o700});
            await fs.writeFile(target,img.bytes,{flag:'wx',mode:0o600});
            if(sha(await fs.readFile(target))!==img.sha256)throw Error('legacy-image-sha-mismatch');
          }
          await fs.writeFile(path.join(out,'paper.md'),md,{flag:'wx',mode:0o600});
          if(prior)await fs.writeFile(path.join(out,'legacy-original.md'),prior,{flag:'wx',mode:0o600});
          await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(row,null,2)+'\n',{flag:'wx',mode:0o600});
        }
      }
      receipts.push(row);
    }catch(e){receipts.push({name,grade:'C',error:e.code||e.message||'error'});}
  }
  return {papers:receipts.length,A:receipts.filter(x=>x.grade==='A').length,C:receipts.filter(x=>x.grade==='C').length,receipts};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const opts=parseCli(process.argv.slice(2));
  runBatch({sourceRoot:opts.source_root,repoRoot:opts.repo_root,limit:opts.limit,write:opts.write,only:opts.only,priorRef:opts.prior_ref}).then(r=>{
    for(const row of r.receipts)console.log(JSON.stringify(row));
    console.log(JSON.stringify({papers:r.papers,A:r.A,C:r.C}));
    if(r.C)process.exitCode=2;
  }).catch(e=>{console.error(e.code||e.message);process.exitCode=1});
}
