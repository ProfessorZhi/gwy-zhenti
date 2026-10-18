import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createDocument } from '../src/model.mjs';
import { runBatch } from '../src/batch-ingest.mjs';

test('local batch writes a single immutable candidate, no formal paper mutation',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'fenbi-batch-io-'));
 t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const repoRoot=path.join(root,'repo'),sourceRoot=path.join(root,'cached');
 await fs.mkdir(repoRoot);await fs.mkdir(sourceRoot);
 const folder=path.join(sourceRoot,'zj-2026-xingce-c-123');await fs.mkdir(folder);
 const doc=createDocument({id:'123',title:'合成卷',area:'浙江',year:2026,subject:'xingce',variant:'C类'},
  {url:'https://www.fenbi.com/spa/tiku',capturedAt:'2026-10-18T00:00:00Z'});
 doc.questions=[{id:'f1',number:1,contentHtml:'这是一道明确且没有图片的合成测试题目。',
   options:[{label:'A',contentHtml:'正确描述'},{label:'B',contentHtml:'错误描述'}],
   materialIds:[],materialIdsObserved:true,answerHtml:'A',explanationHtml:'合成解析。'}];
 doc.expected.questions=1;doc.expected.materials=0;
 await fs.writeFile(path.join(folder,'document.json'),JSON.stringify(doc));
 await fs.mkdir(path.join(folder,'assets'));
 const dry=await runBatch({sourceRoot,repoRoot,write:false});
 assert.equal(dry.A,1);
 await assert.rejects(fs.access(path.join(repoRoot,'work/fenbi/batch-ingest')));
 const real=await runBatch({sourceRoot,repoRoot,write:true});
 assert.equal(real.A,1);
 const out=path.join(repoRoot,'work/fenbi/batch-ingest/zj-2026-xingce-c-123');
 const md=await fs.readFile(path.join(out,'paper.md'),'utf8');
 assert.match(md,/第 1 题/u);
 assert.match(md,/参考答案（粉笔/u);
 const receipt=JSON.parse(await fs.readFile(path.join(out,'receipt.json'),'utf8'));
 assert.equal(receipt.sourceId,'123');
 assert.deepEqual(receipt.answerNumbers,[1]);
 const repeat=await runBatch({sourceRoot,repoRoot,write:true});
 assert.equal(repeat.A,1);
 assert.equal(await fs.readFile(path.join(out,'paper.md'),'utf8'),md);
 await assert.rejects(fs.access(path.join(repoRoot,'省考/浙江/2026/行测-C类.md')));
 await fs.writeFile(path.join(out,'paper.md'),'tampered');
 const altered=await runBatch({sourceRoot,repoRoot,write:true});
 assert.equal(altered.C,1);
 assert.match(altered.receipts[0].error,/existing-candidate-differs/u);
});
