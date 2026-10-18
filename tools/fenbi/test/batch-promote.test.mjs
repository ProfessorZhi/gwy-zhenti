import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { manifestEntry, preparePromotion, promoteOne } from '../src/batch-promote.mjs';

const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const json=x=>JSON.stringify(x,null,2)+'\n';
async function fixture(t,{old=false,branch='ingest-staging'}={}){
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'fenbi-promote-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const repo=path.join(root,'repo'),candidateDir=path.join(root,'candidate');
  await fs.mkdir(repo);await fs.mkdir(candidateDir);
  execFileSync('git',['init','-q','-b',branch,repo]);
  await fs.mkdir(path.join(repo,'catalog'));
  await fs.writeFile(path.join(repo,'catalog/manifest.jsonl'),'');
  const rel='省考/浙江/2026/行测-C类.md';
  const oldMd='旧版内容，不可静默覆盖。\n';
  if(old){await fs.mkdir(path.dirname(path.join(repo,rel)),{recursive:true});await fs.writeFile(path.join(repo,rel),oldMd);}
  const md='# 合成卷\n\n## 题目\n\n### 第 1 题\n\n测试题干。\n\n- A. 测试\n\n![图](assets-fenbi-123/q.png)\n';
  const bytes=Buffer.from('synthetic-image'),imgRoot=path.join(candidateDir,'assets-fenbi-123');
  await fs.mkdir(imgRoot);await fs.writeFile(path.join(imgRoot,'q.png'),bytes);
  const receipt={name:'synthetic',sourceId:'123',path:rel,area:'浙江',year:2026,subject:'xingce',variant:'C类',
    grade:'A',counts:{sourceQuestions:1},answerNumbers:[],markdownSha256:sha(md),oldSha256:old?sha(oldMd):null};
  await fs.writeFile(path.join(candidateDir,'paper.md'),md);
  await fs.writeFile(path.join(candidateDir,'receipt.json'),json(receipt));
  const rightsFile=path.join(root,'rights.json');
  await fs.writeFile(rightsFile,json({schemaVersion:1,allowGitHubStorage:true,evidence:'synthetic authorized fixture',sourceIds:['123']}));
  return {root,repo,candidateDir,rightsFile,rel,md,receipt};
}
test('manifest row has accurate question and missing-answer counts',()=>{
  const receipt={path:'国考/2026/行测-地市级.md',area:'国考',year:2026,subject:'xingce',variant:'地市级',
    counts:{sourceQuestions:3},answerNumbers:[2]};
  const r=manifestEntry(receipt,Buffer.from('abc'));
  assert.equal(r.question_anchors,3);
  assert.equal(r.answer_blocks,1);
  assert.deepEqual(r.missing_answer_numbers,[1,3]);
  assert.equal(r.whole_paper_acceptance,'not_officially_certified');
});
test('dry-run checks candidate, images, rights and never changes repository',async t=>{
  const f=await fixture(t);
  const result=await promoteOne(f);
  assert.equal(result.apply,false);
  assert.equal(result.images,1);
  await assert.rejects(fs.access(path.join(f.repo,f.rel)));
  assert.equal(await fs.readFile(path.join(f.repo,'catalog/manifest.jsonl'),'utf8'),'');
});
test('requires explicit rights proof and refuses main branch',async t=>{
  const f=await fixture(t);
  await assert.rejects(preparePromotion({...f,rightsFile:null}),/permission-required/);
  const g=await fixture(t,{branch:'main'});
  await assert.rejects(preparePromotion(g),/integration-worktree-branch-required/);
});
test('verified promotion writes candidate and manifest to isolated branch',async t=>{
  const f=await fixture(t);
  const r=await promoteOne(f,{apply:true});
  assert.equal(r.apply,true);
  assert.equal(await fs.readFile(path.join(f.repo,f.rel),'utf8'),f.md);
  const rows=(await fs.readFile(path.join(f.repo,'catalog/manifest.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
  assert.equal(rows.length,1);
  assert.equal(rows[0].sha256,sha(f.md));
  assert.deepEqual(rows[0].missing_answer_numbers,[1]);
  assert.equal((await fs.readFile(path.join(f.repo,'省考/浙江/2026/assets-fenbi-123/q.png'))).toString(),'synthetic-image');
});
test('existing paper refuses destructive replacement until explicitly allowed',async t=>{
  const f=await fixture(t,{old:true});
  await assert.rejects(promoteOne(f,{apply:true}),/explicit-allow-replace-required/);
  assert.equal(await fs.readFile(path.join(f.repo,f.rel),'utf8'),'旧版内容，不可静默覆盖。\n');
  await promoteOne(f,{apply:true,allowReplace:true});
  assert.equal(await fs.readFile(path.join(f.repo,f.rel),'utf8'),f.md);
});
test('wrong prior hash and altered candidate are rejected',async t=>{
  const f=await fixture(t,{old:true});
  await fs.writeFile(path.join(f.repo,f.rel),'changed by someone else');
  await assert.rejects(preparePromotion(f),/paper-changed-since-candidate/);
  const g=await fixture(t);
  await fs.writeFile(path.join(g.candidateDir,'paper.md'),'altered');
  await assert.rejects(preparePromotion(g),/candidate-sha-mismatch/);
});
