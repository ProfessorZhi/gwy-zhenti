/** One command for a queue of observed analysis URLs; no agent-generated scraping code. */
import {readFile,mkdir,appendFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {runQueue} from './archive-queue.mjs';
import {createHash} from 'node:crypto';
const exec=promisify(execFile),here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../../..');
const jobs=JSON.parse(await readFile(process.argv[2],'utf8'));
if(!Array.isArray(jobs))throw new Error('Expected a JSON array');
const concurrencyIndex=process.argv.indexOf('--concurrency');
const concurrency=concurrencyIndex<0?2:Number(process.argv[concurrencyIndex+1]);
for(const job of jobs){
 if(!['provider','session','key','title','url'].every(k=>typeof job[k]==='string'&&job[k]))throw new Error('Each job needs provider, session, key, title, url');
 if(!Number.isInteger(job.expectedCount)||job.expectedCount<1)throw new Error('Each job needs expectedCount from source directory');
 if(!['huatu','fenbi'].includes(job.provider)||!/^\w[\w-]*$/.test(job.key)||!/^\w[\w-]*$/.test(job.session))throw new Error('Invalid provider, key or session');
}
const dir=path.join(root,'work','source-papers-v1');await mkdir(dir,{recursive:true});
let failed=0,skipped=0;
const previous=[];
try{for(const line of (await readFile(path.join(dir,'runs.jsonl'),'utf8')).split('\n').filter(Boolean))previous.push(JSON.parse(line))}catch(e){if(e.code!=='ENOENT')throw e}
const force=process.argv.includes('--force');
const started=Date.now();
await runQueue(jobs.map(j=>({...j,originalSession:j.session,session:j.provider==='fenbi'?'fenbi-mcp-extension':j.session})),concurrency,async job=>{
 if(!force){
  const candidate=previous.findLast(r=>r.provider===job.provider&&r.key===job.key&&r.title===job.title&&r.status==='archived'&&r.questionCount===job.expectedCount&&r.answerBlockCount>=job.expectedCount);
  if(candidate?.dir&&path.resolve(candidate.dir).startsWith(path.resolve(dir)+path.sep)){
   try{const m=JSON.parse(await readFile(path.join(candidate.dir,'manifest.json'),'utf8'));
    let intact=m.questionCount===job.expectedCount&&m.answerBlockCount>=job.expectedCount;
    const raw=await readFile(path.join(candidate.dir,job.provider==='fenbi'?'raw-solution.json':'content.html'));
    const expectedHash=job.provider==='fenbi'?m.rawSha256:m.contentSha256;
    if(expectedHash&&createHash('sha256').update(raw).digest('hex')!==expectedHash)intact=false;
    for(const image of m.images||[]){
     if(image.status==='embedded')continue;
     if(!image.file||!image.sha256){intact=false;break}
     const file=path.resolve(candidate.dir,image.file);
     if(!file.startsWith(path.resolve(candidate.dir)+path.sep)||createHash('sha256').update(await readFile(file)).digest('hex')!==image.sha256){intact=false;break}
    }
    if(intact&&(job.provider!=='fenbi'||m.method?.includes('/combine/static/solution'))){skipped++;console.log(JSON.stringify({provider:job.provider,key:job.key,status:'already_archived',dir:candidate.dir}));return}
   }catch{}
  }
 }
 const args=[path.join(here,'archive-loaded.mjs'),'--provider',job.provider,'--session',job.session,'--key',job.key,'--expected-title',job.title,'--expected-count',String(job.expectedCount),'--url',job.url,'--require-answers'];
 const command=job.provider==='fenbi'?(process.env.PYTHON||'python'):process.execPath;
 const actual=job.provider==='fenbi'?['-X','utf8',path.join(here,'fenbi-full.py'),'--url',job.url,'--title',job.title,'--key',job.key,'--expected-count',String(job.expectedCount)]:args;
 try{const {stdout}=await exec(command,actual,{encoding:'utf8',timeout:240000,maxBuffer:1024*1024});console.log(stdout.trim())}
 catch(e){failed++;const result={provider:job.provider,key:job.key,status:'needs_attention',exitCode:e.code||null};
  // Successful partial captures already have a detailed manifest; never echo arbitrary stderr.
  if(e.stdout){try{result.capture=JSON.parse(e.stdout.trim())}catch{}}
  await appendFile(path.join(dir,'queue-failures.jsonl'),JSON.stringify(result)+'\n');console.log(JSON.stringify(result));
 }
});
console.log(JSON.stringify({jobs:jobs.length,failed,skipped,concurrency,elapsedMs:Date.now()-started}));if(failed)process.exitCode=2;
