#!/usr/bin/env node
/**
 * Promote a local structural-A candidate to a NON-main integration worktree.
 * No cloud APIs, no bypass of rights; Git publication is a separate reviewed action.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { RENDERED_COLLECTION_STUB } from './collection-stub.mjs';

const APP_ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const inside=(root,full)=>full.startsWith(root+path.sep);
const writeAtomic=async(file,bytes)=>{
  const temp=file+'.'+crypto.randomUUID()+'.tmp';
  try{await fs.writeFile(temp,bytes,{mode:0o600});await fs.rename(temp,file)}
  finally{await fs.rm(temp,{force:true})}
};

export function manifestEntry(receipt,bytes,oldRecord=null){
  const numbers=receipt.answerNumbers||[],count=receipt.counts.sourceQuestions,sourceMissing=receipt.sourceMissingNumbers||[];
  if(!Number.isInteger(count)||count<1||!Array.isArray(numbers))throw Error('bad-ingest-metadata');
  return {
    path:receipt.path,sha256:hash(bytes),bytes:bytes.length,
    area:receipt.area,year:String(receipt.year),
    subject:receipt.subject==='xingce'?'行测':'申论',paper_type:receipt.variant,
    declared_questions:count,question_anchors:count,reference_question_count:count,
    answer_blocks:numbers.length,has_answer_content:numbers.length>0,
    missing_answer_numbers:Array.from({length:count},(_,i)=>i+1).filter(n=>!numbers.includes(n)),
    image_references:(bytes.toString('utf8').match(/!\[[^\]]*\]\([^)]+\)|<img\b/gu)||[]).length,
    issues:[...(numbers.length<count?['有答案未取得（保留unknown）']:[]),...(sourceMissing.length?['粉笔与本库均缺题（题位保留并标注）']:[])],
    notes:['粉笔优先、本地结构A候选；不等同官方原卷认证','其他来源旧版本在 Git 历史及本地 legacy-original.md 保留'],
    review_scope:'structural_A_pending_publication_review',
    sequence_basis:'Fenbi observed source numbering',
    missing_original_numbers:sourceMissing,missing_option_numbers:[],missing_shared_condition_numbers:[],
    known_material_gaps:null,source_analysis_disagreement_numbers:[],
    missing_stem_figure_numbers:[],missing_stem_condition_numbers:[],
    historical_truncated_questions:oldRecord?.current_truncated_questions??null,
    current_truncated_questions:null,source_validation:'Fenbi-priority structural check',
    whole_paper_acceptance:'not_officially_certified',
    completeness:sourceMissing.length?'PARTIAL_SOURCE_MISSING':'COMPLETE',
  };
}

function validateProof(proof,receipt){
  if(proof?.schemaVersion!==1||proof.allowGitHubStorage!==true||typeof proof.evidence!=='string'||proof.evidence.trim().length<8||
     !Array.isArray(proof.sourceIds)||!proof.sourceIds.map(String).includes(String(receipt.sourceId)))
    throw Error('explicit-publication-permission-required');
}
function validateReceipt(receipt,md){
  if(receipt.grade!=='A')throw Error('only-grade-A-can-promote');
  if(!/^(?:国考|省考\/[^/]+)\/20\d\d\/(?:行测|申论)-[^/]+\.md$/u.test(receipt.path)||
     !/^\d{1,15}$/u.test(String(receipt.sourceId)))throw Error('invalid-target-path');
  if(receipt.markdownSha256!==hash(md))throw Error('candidate-sha-mismatch');
  const count=receipt.counts?.sourceQuestions;
  const q=[...md.toString('utf8').matchAll(/^#{2,3}\s+第\s*(\d+)\s*题/gmu)].map(m=>Number(m[1]));
  if(q.length!==count||q.some((n,i)=>n!==i+1))throw Error('candidate-question-anchors-invalid');
  if(RENDERED_COLLECTION_STUB.test(md.toString('utf8')))throw Error('source-collection-stub-remains');
}

async function candidateImages(candidate,receipt,md){
  const prefix='assets-fenbi-'+receipt.sourceId+'/';
  const out=new Map();
  for(const match of md.toString('utf8').matchAll(/!\[[^\]]*\]\(([^)\s]+)\)|<img\b[^>]*\bsrc=["']([^"']+)["']/gmu)){
    const ref=match[1]||match[2];
    if(!ref.startsWith(prefix)||ref.includes('..')||ref.includes('\\'))throw Error('unapproved-image-path');
    const full=path.resolve(candidate,ref),real=await fs.realpath(full);
    if(!inside(candidate,real))throw Error('candidate-image-path-escape');
    const bytes=await fs.readFile(real);
    out.set(ref,{bytes,sha256:hash(bytes)});
  }
  return out;
}

export async function preparePromotion({candidateDir,repoRoot=APP_ROOT,rightsFile}={}){
  const repo=await fs.realpath(repoRoot);
  const branch=execFileSync('git',['-C',repo,'branch','--show-current'],{encoding:'utf8'}).trim();
  if(!branch||branch==='main'||branch==='master')throw Error('integration-worktree-branch-required');
  const candidate=await fs.realpath(candidateDir),receipt=JSON.parse(await fs.readFile(path.join(candidate,'receipt.json'),'utf8'));
  const bytes=await fs.readFile(path.join(candidate,'paper.md'));
  validateReceipt(receipt,bytes);
  if(!rightsFile)throw Error('explicit-publication-permission-required');
  validateProof(JSON.parse(await fs.readFile(rightsFile,'utf8')),receipt);
  const dest=path.resolve(repo,receipt.path);
  if(!inside(repo,dest))throw Error('publication-path-escape');
  const prior=await fs.readFile(dest).catch(e=>e.code==='ENOENT'?null:Promise.reject(e));
  if(prior && hash(prior)!==receipt.oldSha256)throw Error('repository-paper-changed-since-candidate');
  if(!prior && receipt.oldSha256)throw Error('old-paper-not-found-in-integration-branch');
  // Replacement must not reduce effective (non-stub) or total question positions.
  if(prior){
    const {loadPolicy,assertReplacementAllowed}=await import('./policy.mjs');
    const policy=await loadPolicy();
    const verdict=assertReplacementAllowed(policy,{priorMarkdown:prior.toString('utf8'),newMarkdown:bytes.toString('utf8')});
    if(!verdict.allowed)throw Error('replacement-blocked:'+verdict.reasons.join(','));
  }
  const images=await candidateImages(candidate,receipt,bytes);
  for(const [rel,{sha256}] of images){
    const target=path.resolve(path.dirname(dest),rel);
    if(!inside(repo,target))throw Error('image-target-path-escape');
    const existing=await fs.readFile(target).catch(e=>e.code==='ENOENT'?null:Promise.reject(e));
    if(existing&&hash(existing)!==sha256)throw Error('image-name-collision');
  }
  const manifestPath=path.join(repo,'catalog/manifest.jsonl');
  const original=await fs.readFile(manifestPath,'utf8');
  const records=original.split(/\r?\n/u).filter(Boolean).map(x=>JSON.parse(x));
  const matches=records.filter(x=>x.path===receipt.path);
  if(matches.length>1)throw Error('duplicate-manifest-path');
  const row=manifestEntry(receipt,bytes,matches[0]);
  const index=records.findIndex(x=>x.path===receipt.path);
  if(index<0)records.push(row);else records[index]=row;
  records.sort((a,b)=>String(a.path).localeCompare(String(b.path),'zh-CN'));
  return {repo,branch,candidate,receipt,dest,images,bytes,manifestPath,
    newManifest:records.map(x=>JSON.stringify(x)).join('\n')+'\n',
    oldManifestSha256:hash(original),oldPaperSha256:prior?hash(prior):null};
}

export async function promoteOne(config,{apply=false,allowReplace=false}={}){
  const plan=await preparePromotion(config);
  const metadata={path:plan.receipt.path,sourceId:plan.receipt.sourceId,branch:plan.branch,
    images:plan.images.size,grade:plan.receipt.grade,apply};
  if(!apply)return metadata;
  if(plan.oldPaperSha256&&!allowReplace)throw Error('explicit-allow-replace-required');
  for(const [rel,{bytes}] of plan.images){
    const target=path.resolve(path.dirname(plan.dest),rel);
    await fs.mkdir(path.dirname(target),{recursive:true,mode:0o700});
    const existing=await fs.readFile(target).catch(e=>e.code==='ENOENT'?null:Promise.reject(e));
    if(!existing)await writeAtomic(target,bytes);
  }
  await fs.mkdir(path.dirname(plan.dest),{recursive:true,mode:0o700});
  await writeAtomic(plan.dest,plan.bytes);
  const presentManifest=await fs.readFile(plan.manifestPath);
  if(hash(presentManifest)!==plan.oldManifestSha256)throw Error('manifest-concurrently-modified');
  await writeAtomic(plan.manifestPath,plan.newManifest);
  return metadata;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2),options={apply:false,allowReplace:false};
  for(let i=0;i<args.length;i++){
    const a=args[i];if(a==='--apply')options.apply=true;
    else if(a==='--allow-replace')options.allowReplace=true;
    else if(['--candidate-dir','--repo-root','--rights-file'].includes(a))options[a.slice(2).replaceAll('-','')]=args[++i];
    else throw Error('unknown-option:'+a);
  }
  const cfg={candidateDir:options.candidatedir,repoRoot:options.reporoot||APP_ROOT,rightsFile:options.rightsfile};
  promoteOne(cfg,options).then(x=>console.log(JSON.stringify(x))).catch(e=>{console.error(e.code||e.message);process.exitCode=2});
}
