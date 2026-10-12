"""Source-to-existing material and task mapping review; read-only corpus."""
from __future__ import annotations
import concurrent.futures,difflib,hashlib,json,os,re,subprocess,shutil
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from priority_r3_whole import read,norm,sha
from priority_r3_answers import get_prompt
CACHE=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'priority-r3-reviewed'
FOOT=re.compile(r'欢迎使用公开真题库|备案编号|网络数据相关投诉|浙ICP备')
MAT=re.compile(r'(?:给定)?(?:材料|资料)\s*(\d+)(?:[（(]\d+[)）])?\s*[:：]?\s*$')

def parts(soup):
 out={'instructions':[],'materials':[],'requirements':[],'images':[]};phase=None
 for tag in soup.find_all(['h2','h3','h4','p','img']):
  t=re.sub(r'\s+',' ',tag.get_text()).strip()
  if tag.name=='h2':
   phase='instructions' if '注意事项' in t else 'materials' if '给定材料' in t or '给定资料' in t else 'requirements' if '作答要求' in t else None
   continue
  if phase and tag.name=='img':out['images'].append({'phase':phase,'src':tag.get('src'),'alt':tag.get('alt')});continue
  if not phase or not t:continue
  if FOOT.search(t):phase=None;continue
  out[phase].append(t)
 return out

def oldblocks(s):
 qs=[];blocks=[]
 for m in re.finditer(r'^## 第\s*(\d+)\s*题[^\n]*\n(.*?)(?=^## 第\s*\d+\s*题|^## 答案与解析|\Z)',s,re.M|re.S):
  n=int(m[1]);req=m[2].split('### 作答要求',1)[-1].strip();qs.append({'number':n,'requirements':req})
  mt=m[2].split('### 作答要求',1)[0].split('### 给定材料',1)[-1]
  for z in re.finditer(r'(?:^|\n)材料\s*(\d+)\s*[:：]?\s*\n(.*?)(?=\n材料\s*\d+\s*[:：]?\s*\n|\Z)',mt,re.S):
   text=z[2].strip()
   if text:blocks.append({'old_question':n,'local_number':int(z[1]),'text':text,'normalized':norm(text)})
 return qs,blocks

def assess(item):
 path,url=item['path'],item['url']
 try:
  r,soup=read(url);d=parts(soup);materials=[]
  for p in d['materials']:
   m=MAT.fullmatch(p)
   if m:materials.append({'number':int(m[1]),'paragraphs':[]})
   elif materials:materials[-1]['paragraphs'].append(p)
  if [m['number'] for m in materials]!=list(range(1,len(materials)+1)) or not materials:raise ValueError('Unresolved material headings')
  s=Path(path).read_text();qs,old=oldblocks(s)
  mappings=[]
  for m in materials:
   text='\n\n'.join(m['paragraphs']);nn=norm(text);rank=[]
   for b in old:
    seq=difflib.SequenceMatcher(None,b['normalized'],nn,autojunk=False)
    size=sum(x.size for x in seq.get_matching_blocks())
    rank.append({'old_question':b['old_question'],'local_number':b['local_number'],'old_chars':len(b['normalized']),'source_chars':len(nn),'ratio':round(seq.ratio(),5),'old_coverage':round(size/max(1,len(b['normalized'])),5),'source_coverage':round(size/max(1,len(nn)),5),'head':b['text'][:55]})
   rank.sort(key=lambda x:(x['ratio'],x['old_chars']),reverse=True)
   mappings.append({'original_number':m['number'],'source_head':text[:60],'matches':rank[:2]})
  data={'path':path,'url':url,'title':soup.title.get_text() if soup.title else item.get('title'),'raw_sha256':hashlib.sha256(r.content).hexdigest(),'before_sha256':sha(s),'instructions':d['instructions'],'materials':materials,'requirements':d['requirements'],'images':d['images'],'old_questions':qs,'material_matches':mappings}
  CACHE.mkdir(exist_ok=True);(CACHE/(sha(path)+'.json')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
  dom='';h=next((h for h in soup.find_all('h2') if '作答要求' in h.get_text()),None)
  if h:
   dom=str(h)
   for sib in h.next_siblings:
    dom+=str(sib)
    if len(dom)>2000:break
  return {k:v for k,v in data.items() if k not in ['instructions','materials','old_questions']}|{'source_material_count':len(materials),'old_tasks':qs,'task_dom_head':dom[:2200]}
 except Exception as e:return {'path':path,'url':url,'error':str(e)}

def pdf_probe():
 url='https://www.chinagwy.org/files/20180503150627_39246.pdf'
 try:
  r=requests.get(url,timeout=(8,35));r.raise_for_status()
  if not r.content.startswith(b'%PDF'):raise ValueError('Not a PDF')
  CACHE.mkdir(exist_ok=True);p=CACHE/'zj2016b.pdf';p.write_bytes(r.content)
  if not shutil.which('pdftotext'):return {'url':url,'raw_sha256':hashlib.sha256(r.content).hexdigest(),'error':'pdftotext unavailable'}
  subprocess.run(['pdftotext','-layout',str(p),str(p.with_suffix('.txt'))],check=True,timeout=20)
  text=p.with_suffix('.txt').read_text();pages=text.split('\f')
  return {'url':url,'raw_sha256':hashlib.sha256(r.content).hexdigest(),'pages':len(pages),'text':text}
 except Exception as e:return {'url':url,'error':str(e)}

def main():
 tasks=json.loads(Path('reports/R3-WHOLE-PROBE.json').read_text())
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:out=list(pool.map(assess,tasks))
 Path('reports/R3-MAPPING-REVIEW.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 p=pdf_probe();snap=json.loads(Path('reports/R3-SOURCE-PROBE2.json').read_text())
 extra=[x for x in snap if x.get('key') in ['zj16b','gk16d','gk16d_eol','gk17d_eol']]
 Path('reports/R3-INDEPENDENT-REVIEW.json').write_text(json.dumps({'pdf':p,'secondary':extra},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps([{'path':x['path'],'materials':x.get('source_material_count'),'unmatched':[m['original_number'] for m in x.get('material_matches',[]) if not m['matches'] or m['matches'][0]['source_coverage']<.95],'error':x.get('error')} for x in out],ensure_ascii=False))
if __name__=='__main__':main()
