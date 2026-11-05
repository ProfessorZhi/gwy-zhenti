import concurrent.futures,datetime,hashlib,html,json,re,sys,urllib.request,urllib.parse
import argparse,os,queue,shutil,subprocess,threading
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[3]

def validate(data,expected,title):
 if re.sub(r"\s+","",data.get('name',''))!=re.sub(r"\s+","",title):raise ValueError('title_mismatch')
 solutions=data.get('solutions',[]);ids=[q.get('globalId') for q in solutions];order=[]
 def walk(n):
  if n.get('nodeType')==2:order.append(n)
  for child in n.get('children',[]):walk(child)
 walk(data.get('card',{}))
 keys=[x['key'] for x in order]
 if len(ids)!=expected or len(keys)!=expected or len(set(ids))!=expected or len(set(keys))!=expected or set(ids)!=set(keys):raise ValueError('question_ids_or_count_mismatch')
 if any(q.get('correctAnswer') is None for q in solutions):raise ValueError('answers_missing')
 materials={m['globalId'] for m in data.get('materials',[])}
 if any(k not in materials for n in order for k in n.get('materialKeys',[])):raise ValueError('material_missing')
 return order

def capture(url,title):
 u=urllib.parse.urlsplit(url)
 if u.scheme!='https' or u.hostname!='spa.fenbi.com' or not u.path.startswith('/ti/exam/solution/'):raise ValueError('solution_url_required')
 if not os.environ.get('PLAYWRIGHT_MCP_EXTENSION_TOKEN'):raise ValueError('extension_token_environment_missing')
 cli=shutil.which('playwright.cmd') or shutil.which('playwright')
 if not cli:raise ValueError('playwright_cli_missing')
 p=subprocess.Popen([cli,'mcp','--extension','--caps','devtools','--output-dir',str(ROOT/'work/mcp-output')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf8',bufsize=1)
 messages=queue.Queue()
 def reader():
  for line in p.stdout:
   try:messages.put(json.loads(line))
   except json.JSONDecodeError:pass
  messages.put(None)
 threading.Thread(target=reader,daemon=True).start()
 def call(i,method,params):
  p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n');p.stdin.flush()
  while True:
   msg=messages.get(timeout=100)
   if msg is None:raise ValueError('mcp_disconnected')
   if msg.get('id')==i:
    if msg.get('error') or msg.get('result',{}).get('isError'):raise ValueError('browser_action_failed')
    return msg.get('result',{})
 try:
  call(1,'initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'gwy-full-archive','version':'1'}})
  p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
  call(2,'tools/call',{'name':'browser_navigate','arguments':{'url':url}})
  code="""async(page)=>{const records=[],pending=[];const listener=r=>{const u=new URL(r.url());if(!u.hostname.endsWith('.fenbi.com')||u.pathname!=='/combine/static/solution')return;pending.push((async()=>{try{const body=await r.json();if(Array.isArray(body.solutions)&&body.card)records.push(body)}catch{}})())};page.context().on('response',listener);try{await page.reload({waitUntil:'domcontentloaded',timeout:60000});await page.waitForTimeout(10000);await Promise.allSettled(pending);return records}finally{page.context().off('response',listener)}}"""
  result=call(3,'tools/call',{'name':'browser_run_code_unsafe','arguments':{'code':code}})
  for content in result.get('content',[]):
   text=content.get('text','')
   if '### Result\n' not in text:continue
   result_text=text.split('### Result\n',1)[1].split('### Ran Playwright code')[0].strip()
   try:records=json.loads(result_text)
   except json.JSONDecodeError:raise ValueError('mcp_payload_truncated_or_invalid')
   matches=[d for d in records if re.sub(r'\s+','',d.get('name',''))==re.sub(r'\s+','',title)]
   if matches:return matches[-1]
  raise ValueError('full_solution_response_not_observed')
 finally:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill()

def archive(data,key,expected,title,source_url=None):
 validate(data,expected,title)
 questions={q['globalId']:q for q in data['solutions']};order=[]
 def visit(node):
  if node.get('nodeType')==2:order.append(node)
  for child in node.get('children',[]):visit(child)
 visit(data['card'])
 assert len(order)==len(questions)==expected and len({n['key'] for n in order})==expected
 assert set(questions)=={n['key'] for n in order}
 ordered=[dict(questions[n['key']],materialKeys=n.get('materialKeys',[])) for n in order]
 assert all(q.get('correctAnswer') is not None for q in ordered)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
 out=ROOT/'work/source-papers-v1/fenbi'/key/('full-json-'+stamp);(out/'images').mkdir(parents=True)
 (out/'raw-solution.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
 (out/'ordered-questions.json').write_text(json.dumps(ordered,ensure_ascii=False,indent=2),encoding='utf8')
 parts=['<!doctype html><meta charset="utf-8"><title>'+html.escape(data['name'])+'</title><h1>'+html.escape(data['name'])+'</h1>']
 for m in data.get('materials',[]):parts.append('<h2>材料 '+html.escape(m.get('globalId',str(m['id'])))+'</h2>'+m['content'])
 for i,q in enumerate(ordered,1):
  parts.append('<hr><h2>第 '+str(i)+' 题</h2><p>关联材料：'+html.escape(', '.join(q['materialKeys']))+'</p>'+q['content'])
  for a in q.get('accessories',[]):
   for j,o in enumerate(a.get('options',[])):parts.append('<p>'+chr(65+j)+'. '+o+'</p>')
  parts.append('<h3>平台参考答案</h3><pre>'+html.escape(json.dumps(q['correctAnswer'],ensure_ascii=False))+'</pre><h3>解析</h3>'+q.get('solution',''))
 page='\n'.join(parts)
 class Images(HTMLParser):
  def __init__(self):super().__init__();self.urls=set()
  def handle_starttag(self,tag,attrs):
   if tag=='img':
    src=dict(attrs).get('src')
    if src:self.urls.add(src)
 p=Images();p.feed(page)
 def download(url):
  if url.startswith('data:image/'):return {'url':url,'status':'embedded'}
  try:
   full=urllib.parse.urljoin('https://spa.fenbi.com',url)
   if urllib.parse.urlsplit(full).scheme not in ('http','https'):raise ValueError('scheme')
   with urllib.request.urlopen(full,timeout=30) as r:body=r.read();ct=r.headers.get_content_type()
   if not ct.startswith('image/'):raise ValueError('not_image')
   ext={'image/png':'png','image/jpeg':'jpg','image/gif':'gif','image/svg+xml':'svg','image/webp':'webp'}.get(ct,'bin')
   rel='images/'+hashlib.sha256(url.encode()).hexdigest()+'.'+ext;(out/rel).write_bytes(body)
   return {'url':url,'file':rel,'sha256':hashlib.sha256(body).hexdigest(),'status':'saved'}
  except Exception as e:return {'url':url,'status':'failed','error':type(e).__name__}
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:images=list(pool.map(download,sorted(p.urls)))
 for image in images:
  if 'file' in image:
   page=page.replace(image['url'],image['file']).replace(html.escape(image['url'],quote=True),image['file'])
 (out/'whole-paper.html').write_text(page,encoding='utf8')
 failed=sum(i['status']=='failed' for i in images)
 manifest={'schemaVersion':1,'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceUrl':(urllib.parse.urlunsplit((*urllib.parse.urlsplit(source_url)[:3],'','')) if source_url else None),'rawSha256':hashlib.sha256((out/'raw-solution.json').read_bytes()).hexdigest(),'provider':'fenbi','archiveKey':key,'title':data['name'],'method':'captured /combine/static/solution JSON response','questionCount':len(ordered),'expectedQuestionCount':expected,'answerBlockCount':sum(q.get('correctAnswer') is not None for q in ordered),'materialCount':len(data.get('materials',[])),'sourcePlaceholderCount':sum(bool(re.search('征集|暂未收录|占位题',q['content'])) for q in ordered),'status':'archived' if not failed else 'images_incomplete','images':images,'limitations':['Source placeholders/default answers preserved','Not matched to repository or filled into papers']}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 summary={k:manifest[k] for k in ['provider','title','questionCount','answerBlockCount','materialCount','sourcePlaceholderCount','status']};summary.update(key=key,dir=str(out.resolve()),images=len(images),failedImages=failed)
 with (ROOT/'work/source-papers-v1/runs.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(summary,ensure_ascii=False)+'\n')
 print(json.dumps(summary,ensure_ascii=False))

 return summary

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--url');ap.add_argument('--title',required=True);ap.add_argument('--key',required=True);ap.add_argument('--expected-count',required=True,type=int);ap.add_argument('--input-response')
 opts=ap.parse_args()
 if not re.fullmatch(r'[\w-]+',opts.key) or opts.expected_count<1:raise ValueError('invalid_job')
 if opts.input_response:
  obj=json.loads(Path(opts.input_response).read_text(encoding='utf8'));data=obj.get('body',obj)
 else:data=capture(opts.url,opts.title)
 return archive(data,opts.key,opts.expected_count,opts.title,opts.url)

if __name__=='__main__':
 try:
  result=main()
  if result['status']!='archived':sys.exit(2)
 except Exception as e:
  print(json.dumps({'status':'needs_attention','errorType':type(e).__name__,'reason':str(e) if isinstance(e,ValueError) and re.fullmatch(r'[a-z_]+',str(e)) else 'capture_or_validation_failed'}))
  sys.exit(1)
