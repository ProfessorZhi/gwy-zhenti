/** Export an already opened analysis/practice tab. Never logs credentials or changes the page. */
import { load } from 'cheerio';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, writeFile, readFile, access } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const exec = promisify(execFile);
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const norm=s=>s.replace(/\s+/g,'');
const selectors={huatu:'.question-wrap,.exercise-main-topic[id^="question"]',fenbi:'app-ti'};
export function contentStatus(a,expected,requireAnswers){
 if(!Number.isInteger(expected)||expected<1)throw new Error('Invalid expected count');
 if(a.questionCount!==expected)return 'questions_incomplete';
 if(requireAnswers&&!a.answerBlockCount)return 'answers_missing';
 if(requireAnswers&&a.answerBlockCount<a.questionCount)return 'answers_incomplete';
 return 'archived';
}

export function prepareArchive(raw,provider,expectedTitle){
 if(!selectors[provider])throw new Error('Unsupported provider');
 if(norm(raw.title)!==norm(expectedTitle))throw new Error('Unexpected paper title; capture rejected');
 const u=new URL(raw.url);
 if(!(provider==='huatu'?u.hostname.endsWith('.huatu.com'):u.hostname.endsWith('.fenbi.com')))throw new Error('Unexpected provider host');
 const $=load(raw.html,null,false);
 $('script,iframe,video,input,button,app-solution-note,app-solution-video,.videoAnalysis,.main-topic-letters').remove();
 $('*').each((_,el)=>{for(const name of Object.keys(el.attribs||{}))if(/^on|token|cookie|authorization|data-opencli-ref/i.test(name))$(el).removeAttr(name)});
 const questions=$(selectors[provider]);
 if(!questions.length)throw new Error('No questions; capture rejected');
 const placeholderCount=questions.toArray().filter(el=>/占位题|题目正在.*征集|粉笔暂未收录/.test($(el).text())).length;
 const answerBlockCount=provider==='huatu'?$('.jiexi-answers').length:$('app-solution-overall').length;
 return {url:u.origin+u.pathname,title:raw.title,html:$.html(),questionCount:questions.length,
  answerBlockCount,placeholderCount,answerStatus:answerBlockCount?'blocks_present_not_semantically_verified':'not_present',
  imageUrls:[...new Set($('img[src]').map((_,el)=>$(el).attr('src')).get())]};
}

async function opencliEntry(override){
 if(override){await access(override);return override}
 const {stdout}=await exec(process.platform==='win32'?'where.exe':'which',['opencli']);
 for(const p of stdout.trim().split(/\r?\n/)){
  const candidate=path.join(path.dirname(p),'node_modules','@jackwener','opencli','dist','src','main.js');
  try{await access(candidate);return candidate}catch{}
 }
 throw new Error('Cannot locate OpenCLI entry; supply --opencli-entry path/to/main.js');
}
async function main(){
 const opts={};for(let i=2;i<process.argv.length;i++){
  const k=process.argv[i];if(k==='--require-answers')opts.requireAnswers=true;
  else if(['--provider','--session','--tab','--url','--key','--expected-title','--expected-count','--opencli-entry'].includes(k))opts[k.slice(2)]=process.argv[++i];
  else throw new Error('Unknown argument: '+k);
 }
 for(const k of ['provider','session','key','expected-title'])if(!opts[k])throw new Error('Missing --'+k);
 if(!opts.tab&&!opts.url)throw new Error('Supply --url or --tab');
 const expected=Number(opts['expected-count']);
 if(!Number.isInteger(expected)||expected<1)throw new Error('Supply valid --expected-count from source directory');
 if(!/^[\w-]+$/.test(opts.key)||!selectors[opts.provider])throw new Error('Invalid archive key/provider');
 const entry=await opencliEntry(opts['opencli-entry']);
 if(opts.url){
  const u=new URL(opts.url);if(u.protocol!=='https:'||!(opts.provider==='huatu'?u.hostname.endsWith('.huatu.com'):u.hostname.endsWith('.fenbi.com')))throw new Error('Invalid source URL');
  const {stdout}=await exec(process.execPath,[entry,'browser',opts.session,'open',opts.url,'--window','background'],{encoding:'utf8',timeout:90000});
  opts.tab=JSON.parse(stdout).page;if(!opts.tab)throw new Error('No background tab');
 }
 const js=`(function(){const provider=${JSON.stringify(opts.provider)};const root=provider==='fenbi'?'app-tis':'.question-box,.exercise-main-topics';const nodes=[...document.querySelectorAll(root)];let title=document.title;if(provider==='huatu'){const h=[...document.querySelectorAll('span,div')].find(x=>x.childElementCount===0&&/年.*考试.*[行申]/.test(x.textContent)&&x.textContent.length<140);if(h)title=h.textContent.trim()}const html=nodes.map(n=>{const c=n.cloneNode(true);c.querySelectorAll('script,iframe,video,input,button,app-solution-note,app-solution-video,.videoAnalysis,.main-topic-letters').forEach(x=>x.remove());c.querySelectorAll('*').forEach(x=>{for(const a of [...x.attributes])if(/^on|token|cookie|authorization|data-opencli-ref/i.test(a.name))x.removeAttribute(a.name)});return c.outerHTML}).join('');return JSON.stringify({title,url:location.origin+location.pathname,html})})()`;
 const started=Date.now();
 let archive,lastError;
 for(let attempt=0;attempt<10;attempt++){
  const {stdout}=await exec(process.execPath,[entry,'browser',opts.session,'eval',js,'--tab',opts.tab],{encoding:'utf8',timeout:90000,maxBuffer:32*1024*1024});
  let raw=JSON.parse(stdout);if(typeof raw==='string')raw=JSON.parse(raw);
  try{archive=prepareArchive(raw,opts.provider,opts['expected-title']);if(contentStatus(archive,expected,opts.requireAnswers)==='archived')break}catch(e){lastError=e}
  await new Promise(r=>setTimeout(r,1000));
 }
 if(!archive)throw lastError;
 const stamp=new Date().toISOString().replace(/[:.]/g,'-');
 const dir=path.join(ROOT,'work','source-papers-v1',opts.provider,opts.key,stamp);
 await mkdir(path.join(dir,'images'),{recursive:true});
 const bytes=Buffer.from(archive.html);await writeFile(path.join(dir,'content.html'),bytes);
 const urls=archive.imageUrls,images=new Array(urls.length);let next=0;
 async function worker(){while(next<urls.length){const i=next++,url=urls[i];
  if(url.startsWith('data:image/')){images[i]={url,status:'embedded'};continue}
  try{const absolute=new URL(url,archive.url);if(!['https:','http:'].includes(absolute.protocol))throw new Error('Unsupported image scheme');
   const response=await fetch(absolute,{signal:AbortSignal.timeout(30000)});if(!response.ok)throw new Error('HTTP '+response.status);
   const mime=(response.headers.get('content-type')||'').split(';')[0];if(!mime.startsWith('image/'))throw new Error('Not an image');
   const body=Buffer.from(await response.arrayBuffer());const ext={'image/png':'png','image/jpeg':'jpg','image/gif':'gif','image/webp':'webp','image/svg+xml':'svg'}[mime]||'bin';
   const file='images/'+createHash('sha256').update(url).digest('hex')+'.'+ext;await writeFile(path.join(dir,file),body);
   images[i]={url,file,sha256:createHash('sha256').update(body).digest('hex'),bytes:body.length,status:'saved'};
  }catch(e){images[i]={url,status:'failed',reason:e.message.replace(/https?:\/\/\S+/g,'[url]')}}
 }}
 await Promise.all(Array.from({length:4},()=>worker()));
 const failed=images.filter(x=>x.status==='failed').length;
 const manifest={schemaVersion:1,provider:opts.provider,archiveKey:opts.key,title:archive.title,url:archive.url,capturedAt:new Date().toISOString(),
  method:'loaded question DOM; no network JSON claim',expectedQuestionCount:expected,questionCount:archive.questionCount,answerBlockCount:archive.answerBlockCount,
  sourcePlaceholderCount:archive.placeholderCount,answerStatus:archive.answerStatus,images,
  contentSha256:createHash('sha256').update(bytes).digest('hex'),elapsedMs:Date.now()-started,
  status:failed?'images_incomplete':contentStatus(archive,expected,opts.requireAnswers),
  limitations:['source identity and answers not independently verified','source placeholders retained','no repository gap filled']};
 await writeFile(path.join(dir,'manifest.json'),JSON.stringify(manifest,null,2));
 const log=path.join(ROOT,'work','source-papers-v1','runs.jsonl');
 const {appendFile}=await import('node:fs/promises');
 const summary={provider:opts.provider,key:opts.key,title:archive.title,dir,status:manifest.status,questionCount:manifest.questionCount,answerBlockCount:manifest.answerBlockCount,images:images.length,failedImages:failed,elapsedMs:manifest.elapsedMs};
 await appendFile(log,JSON.stringify(summary)+'\n');console.log(JSON.stringify(summary));
 if(manifest.status!=='archived')process.exitCode=2;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(()=>{console.error('Archive failed: validate title, session/tab, dependencies and loaded question content. No credentials were logged.');process.exitCode=1});
