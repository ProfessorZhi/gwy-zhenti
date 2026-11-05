/** One command for a queue of observed analysis URLs; no agent-generated scraping code. */
import {readFile,mkdir,appendFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {runQueue} from './archive-queue.mjs';
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
let failed=0;
const started=Date.now();
await runQueue(jobs,concurrency,async job=>{
 const args=[path.join(here,'archive-loaded.mjs'),'--provider',job.provider,'--session',job.session,'--key',job.key,'--expected-title',job.title,'--expected-count',String(job.expectedCount),'--url',job.url,'--require-answers'];
 try{const {stdout}=await exec(process.execPath,args,{encoding:'utf8',timeout:240000,maxBuffer:1024*1024});console.log(stdout.trim())}
 catch(e){failed++;const result={provider:job.provider,key:job.key,status:'needs_attention',exitCode:e.code||null};
  // Successful partial captures already have a detailed manifest; never echo arbitrary stderr.
  if(e.stdout){try{result.capture=JSON.parse(e.stdout.trim())}catch{}}
  await appendFile(path.join(dir,'queue-failures.jsonl'),JSON.stringify(result)+'\n');console.log(JSON.stringify(result));
 }
});
console.log(JSON.stringify({jobs:jobs.length,failed,concurrency,elapsedMs:Date.now()-started}));if(failed)process.exitCode=2;
