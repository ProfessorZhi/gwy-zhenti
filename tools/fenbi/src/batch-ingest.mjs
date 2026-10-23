#!/usr/bin/env node
/** Deterministic local-only Fenbi cache -> Markdown candidate pipeline. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseRepositoryPaper, normalizeComparisonText } from './align.mjs';
import { isCollectionStub, validateDocument } from './validate.mjs';
import { RENDERED_COLLECTION_STUB } from './collection-stub.mjs';
import { renderCandidate } from './render.mjs';
import { paperVariantLabel } from './labels.mjs';

// 粉笔与本库都缺的题在 Markdown 里的固定标注。policy.mjs 的有效题计数认这句话，替换判断因此不会把它当成有效题。
export const SOURCE_MISSING_NOTE = '粉笔暂未收录本题（来源缺题，题位保留）';
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
const hasExternalImage = value => /<(?:img|image)\b|!\[[^\]]*\]\(/iu.test(flat(value));

export function assemble(document, oldMarkdown = '') {
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
  const counters = {sourceQuestions:sorted.length,stubSlots:0,inheritedStubs:0,unresolvedStubs:0,oldAnswersInherited:0,oldExplanationsInherited:0,sourceAnswers:0,answerUnknown:0,oldAnswersUnmapped:0,mappedQuestions:map.size};
  for (const q of sorted) {
    let current={...q,options:(q.options || []).map(o=>({...o})),answerOrigin:flat(q.answerHtml)?'fenbi':'unknown',explanationOrigin:flat(q.explanationHtml)?'fenbi':'unknown'};
    let ancestor = map.get(q);
    if (isStub(q)) {
      counters.stubSlots++;
      const exactNumber = old.filter(x => x.number === q.number && isUsable(x));
      if (numberingStable && exactNumber.length === 1 && !legacyUsed.has(exactNumber[0])) {
        ancestor=exactNumber[0];legacyUsed.add(ancestor);counters.inheritedStubs++;
        current.legacyFallbackNumber=ancestor.number;
        current.legacyFallbackMarkdown=true;
      } else {
        // 粉笔与本库都没有这道题：按既定规则保留题位、明确标注"来源缺题"，整卷照常发布（不是完整卷，清单里列出缺题号）。
        counters.unresolvedStubs++;current.sourceMissing=true;
      }
    }
    if (!isStub(q) && !isUsable(q)) issues.push('question-body-empty:'+q.number);
    // 行测里的论述/辨析题源站本就不给选项，不按「选项缺失」处理。
    const subjective=/论述题|主观题|简答题|辨析题/u.test(String(q.typeName??''));
    if (!current.sourceMissing && !subjective && (!Array.isArray(q.options) || (id.subject==='xingce' && q.options.length<2))) issues.push('options-missing:'+q.number);
    if (current.sourceMissing) { current.contentHtml='';current.options=[];current.answerHtml='';current.explanationHtml=''; }
    if (current.legacyFallbackMarkdown) {
      // Original repository Markdown blocks cannot be passed through an HTML-only renderer.
      current.contentHtml='';current.options=[];current.answerHtml='';current.explanationHtml='';
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

export function renderIngest(assembly, oldMarkdown='', imagePrefix='assets') {
  const draft=assembly.prepared;
  const markers=draft.questions.filter(q=>q.legacyFallbackMarkdown);
  const renderDocument={...draft, questions:draft.questions.map(q=>q.legacyFallbackMarkdown?{...q,contentHtml:'LEGACYFALLBACK'+q.number,options:[]}
    : q.sourceMissing?{...q,contentHtml:'<p>'+SOURCE_MISSING_NOTE+'</p>',options:[]} : q)};
  let md=renderCandidate(renderDocument,{status:'complete'}, { imagePrefix });
  for(const q of markers){
    const block=extractLegacyBlock(oldMarkdown,q.number);
    if(!block) throw Error('legacy-block-not-extractable:'+q.number);
    // Legacy image links must be rebased in a separate, verified step; never claim those images passed.
    if(/!\[[^\]]*\]\(|<img\b/iu.test(block)) assembly.issues.push('legacy-image-references-need-rebase:'+q.number);
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
  const exempt=n=>q.some(item=>(item.legacyFallbackMarkdown||item.sourceMissing) && item.number===n);
  if(!q.length)blockers.push('no-questions');
  if(q.some(x=>isStub(x) && !x.legacyFallbackMarkdown))blockers.push('unremoved-source-stub');
  if(doc.assets.some(x=>x.status!=='downloaded'||!x.localPath||!x.sha256))blockers.push('asset-not-ready');
  if(validation?.dimensions?.images?.status !== 'complete')blockers.push('image-validation-not-complete');
  // advisory 是「源内容本身的形态」（申论范文超字数、作答要求写在题干里）造成的提示，重采也改不了，
  // 不能当作结构不达标：否则整卷被降成 C 而进不了仓库。
  for(const issue of validation?.issues || []) if(!issue.advisory && ['questions','materials'].includes(issue.dimension) && !((issue.code==='question-body-empty'||issue.code==='question-body-placeholder'||issue.code==='options-missing') && exempt(issue.questionNumber ?? issue.number))) blockers.push('source-structure:'+issue.code);
  // Grade A must describe the rendered bytes, not just the pre-render source object.
  // A legacy fallback can reintroduce a stub after document validation.
  if(RENDERED_COLLECTION_STUB.test(markdownText))blockers.push('rendered-collection-stub-remains');
  if(!markdownText.includes('## 题目'))blockers.push('missing-questions-heading');
  if(!markdownText.includes('### 第 1 题') && !/^## 第 1 题/mu.test(markdownText))blockers.push('missing-first-question');
  if(q.some(x=>x.legacyFallbackMarkdown) && !markdownText.includes('本题来源：原库'))blockers.push('legacy-fallback-not-rendered');
  const sourceMissingNumbers=q.filter(x=>x.sourceMissing).map(x=>x.number);
  if(sourceMissingNumbers.length && sourceMissingNumbers.length*2>q.length)blockers.push('source-missing-majority');
  return {grade:blockers.length?'C':'A',blockers:[...new Set(blockers)],counts:assembly.counters,sourceMissingNumbers,
    answerCompleteness:'per-question; unknown does not claim correctness',
    note:'A=local structural candidate only; not official truth or permission to publish'};
}

function parseCli(argv) {
  const opts={write:false,limit:100};
  for(let i=0;i<argv.length;i++){
    const k=argv[i];
    if(k==='--write')opts.write=true;
    else if(['--source-root','--repo-root','--limit'].includes(k)){
      if(!argv[++i])throw Error('missing-value:'+k);
      opts[k.slice(2).replaceAll('-','_')]=argv[i];
    }else throw Error('unknown-option:'+k);
  }
  opts.limit=Number(opts.limit);
  if(!Number.isInteger(opts.limit)||opts.limit<1||opts.limit>1000)throw Error('invalid-limit');
  return opts;
}

// One cache folder -> one candidate (paper.md, receipt.json, copied assets). Returns the receipt row.
// The worker calls this right after a paper is captured; runBatch calls it for every folder.
// `variant`：落地用的卷型名，默认由标题推导。仓库（origin/main）的卷型来自它自己的目录引擎
// （旗县卷/市县卷/一卷/二卷…比这里的规则细），合并进仓库时要显式传入仓库认的卷型名，
// 否则同一份卷会在库里落成两个路径。
// `relPath`：目标路径覆盖。同路径已有另一份**不同的**卷时，改写到带源试卷 ID 的唯一路径。
// `ignorePrior`：不从目标仓库的同名文件继承答案。以粉笔为准重新落地时用它，避免旧源内容回流。
export async function ingestFolder({source,repo,dest,name,write=false,variant=null,relPath=null,ignorePrior=false}){
  const base=path.join(source,name),real=await fs.realpath(base);
  if(!real.startsWith(source+path.sep))throw Error('source-path-escape');
  const raw=await fs.readFile(path.join(base,'document.json'));
  const parsed=JSON.parse(raw);
  // 卷型用中文名（副省级/行政执法/A类/乡镇卷…），与仓库既有文件的命名一致；
  // 采集库里的英文 slug 是内部标识，不进文件名也不进 frontmatter。
  const variantName=variant??paperVariantLabel(parsed.identity?.title,parsed.identity?.area);
  const doc={...parsed,identity:{...(parsed.identity||{}),variant:variantName}};
  const id=doc.identity,area=id.area==='国考'?'国考':'省考/'+id.area;
  const sub=subjectName(id.subject);
  if(!sub||!safeName(id.id)||!safeName(id.variant)||!Number.isInteger(Number(id.year)))throw Error('bad-identity');
  const rel=relPath?path.posix.normalize(String(relPath)):path.posix.join(area,String(id.year),sub+'-'+id.variant+'.md');
  if(path.posix.isAbsolute(rel)||rel.startsWith('..'))throw Error('bad-target-path');
  const priorFile=path.join(repo,rel);
  let prior='';
  if(!ignorePrior)try{prior=await fs.readFile(priorFile,'utf8')}catch(e){if(e.code!=='ENOENT')throw e}
  // Neither the source nor the repository paper changed since the last candidate: reuse it.
  const known=write?await fs.readFile(path.join(dest,name,'receipt.json'),'utf8').then(JSON.parse).catch(()=>null):null;
  const knownMd=known?await fs.readFile(path.join(dest,name,'paper.md')).catch(()=>null):null;
  if(known&&knownMd&&sha(knownMd)===known.markdownSha256&&known.sourceSha256===sha(raw)&&known.oldSha256===(prior?sha(prior):null))return known;
  const assembly=assemble(doc,prior);
  const verdict=await validateDocument(assembly.prepared,{assetRoot:path.join(base,'assets')});
  const prefix='assets-fenbi-'+id.id;
  const md=renderIngest(assembly,prior,prefix);
  const grade=structureGrade(assembly,md,verdict);
  const answerNumbers=assembly.prepared.questions.filter(q=>flat(q.answerHtml)).map(q=>q.number);
  const row={name,sourceId:String(id.id),area:id.area,year:Number(id.year),variant:id.variant,subject:id.subject,path:rel,grade:grade.grade,issues:grade.blockers,counts:grade.counts,answerNumbers,sourceMissingNumbers:grade.sourceMissingNumbers,completeness:grade.sourceMissingNumbers.length?'partial-source-missing':'complete',markdownSha256:sha(md),oldSha256:prior?sha(prior):null,sourceSha256:sha(raw)};
  if(write){
    const out=path.join(dest,name);await fs.mkdir(out,{recursive:true,mode:0o700});
    let existing=await fs.readFile(path.join(out,'paper.md')).catch(e=>e.code==='ENOENT'?null:Promise.reject(e));
    if(existing&&sha(existing)!==sha(md)){
      // The source (e.g. answers backfilled) or the repository paper changed: rebuild instead of
      // blocking forever. The superseded candidate is kept outside the candidate root.
      const stale=path.join(path.dirname(dest),'batch-ingest-stale',`${name}-${Date.now()}`);
      await fs.mkdir(path.dirname(stale),{recursive:true,mode:0o700});
      await fs.rename(out,stale);await fs.mkdir(out,{recursive:true,mode:0o700});existing=null;
    }
    if(existing){
      // Same paper, but the base it would replace may have moved; keep the receipt current.
      await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(row,null,2)+'\n',{mode:0o600});
    }else{
      const assetOut=path.join(out,prefix);await fs.mkdir(assetOut,{recursive:true,mode:0o700});
      const copied=new Set();
      for(const asset of doc.assets){
        if(!asset.localPath || !asset.sha256 || asset.status!=='downloaded')throw Error('asset-not-available');
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
      await fs.writeFile(path.join(out,'paper.md'),md,{flag:'wx',mode:0o600});
      if(prior)await fs.writeFile(path.join(out,'legacy-original.md'),prior,{flag:'wx',mode:0o600});
      await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(row,null,2)+'\n',{flag:'wx',mode:0o600});
    }
  }
  return row;
}

export async function runBatch({sourceRoot,repoRoot=APP_ROOT,limit=100,write=false}={}){
  const source=await fs.realpath(sourceRoot||path.join(repoRoot,'work/fenbi/papers'));
  const repo=await fs.realpath(repoRoot);
  const dest=path.join(repo,'work/fenbi/batch-ingest');
  const folders=(await fs.readdir(source,{withFileTypes:true})).filter(x=>x.isDirectory()&&safeName(x.name)).map(x=>x.name).sort().slice(0,limit);
  const receipts=[];
  for(const name of folders){
    try{receipts.push(await ingestFolder({source,repo,dest,name,write}));}
    catch(e){receipts.push({name,grade:'C',error:e.code||e.message||'error'});}
  }
  return {papers:receipts.length,A:receipts.filter(x=>x.grade==='A').length,C:receipts.filter(x=>x.grade==='C').length,receipts};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const opts=parseCli(process.argv.slice(2));
  runBatch({sourceRoot:opts.source_root,repoRoot:opts.repo_root,limit:opts.limit,write:opts.write}).then(r=>{
    for(const row of r.receipts)console.log(JSON.stringify(row));
    console.log(JSON.stringify({papers:r.papers,A:r.A,C:r.C}));
    if(r.C)process.exitCode=2;
  }).catch(e=>{console.error(e.code||e.message);process.exitCode=1});
}
