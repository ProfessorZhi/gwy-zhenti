"""Inspect only 2016-2023 national essay papers and 2016 Zhejiang A/B."""
from __future__ import annotations
import concurrent.futures,hashlib,json,os,re,unicodedata
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
BASE='https://gwy.gkzhenti.cn'
CACHE=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'priority-r3-whole'

def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKC',s) if c.isalnum())
def read(url):
 r=requests.get(url,timeout=(8,35));r.raise_for_status();r.encoding='utf-8'
 soup=BeautifulSoup(r.text,'html.parser')
 if len(r.content)<100:raise ValueError('Empty or invalid source')
 return r,soup

def extract(soup):
 out={'instructions':[],'materials':[],'requirements':[],'images':[]};phase=None
 for tag in soup.find_all(['h2','p','img']):
  txt=re.sub(r'\s+',' ',tag.get_text()).strip()
  if tag.name=='h2':
   if '注意事项' in txt:phase='instructions'
   elif '给定材料' in txt or '给定资料' in txt:phase='materials'
   elif '作答要求' in txt or '答题要求' in txt:phase='requirements'
   else:phase=None
   continue
  if phase and tag.name=='img':out['images'].append({'phase':phase,'src':tag.get('src'),'alt':tag.get('alt')});continue
  if phase and txt and '欢迎使用公开真题库' not in txt:out[phase].append(txt)
 return out

def inspect(item):
 path,url,title=item
 try:
  r,soup=read(url);parts=extract(soup)
  materials=[]
  for p in parts['materials']:
   m=re.fullmatch(r'(?:给定)?(?:材料|资料)\s*(\d+)\s*[:：]?',p)
   if m:materials.append({'number':int(m[1]),'paragraphs':[]})
   elif materials:materials[-1]['paragraphs'].append(p)
  if not materials:raise ValueError('No explicit material numbers')
  if [x['number'] for x in materials]!=list(range(1,len(materials)+1)):raise ValueError('Discontinuous source materials')
  old=Path(path).read_text(encoding='utf-8')
  oq=[]
  for m in re.finditer(r'^## 第\s*(\d+)\s*题[^\n]*\n(.*?)(?=^## 第\s*\d+\s*题|^## 答案与解析|\Z)',old,re.M|re.S):
   body=m[2];req=body.split('### 作答要求',1)[-1].strip();oq.append({'number':int(m[1]),'requirements':req,'local_materials':[{'local_number':z[1],'head':z[2][:80],'chars':len(z[2])} for z in re.finditer(r'材料(\d+)\s*\n(.*?)(?=材料\d+\s*\n|### 作答要求|\Z)',body,re.S)]})
  d={'path':path,'url':url,'title':title,'raw_sha256':hashlib.sha256(r.content).hexdigest(),'before_sha256':sha(old),'instructions':parts['instructions'],'materials':materials,'requirements':parts['requirements'],'images':parts['images'],'old_questions':oq}
  CACHE.mkdir(exist_ok=True);(CACHE/(sha(path)+'.json')).write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
  return {k:v for k,v in d.items() if k not in ['instructions','materials']}|{'materials':[{'number':m['number'],'chars':sum(map(len,m['paragraphs'])),'head':m['paragraphs'][0][:60] if m['paragraphs'] else ''} for m in materials]}
 except Exception as e:return {'path':path,'url':url,'error':str(e)}

def main():
 r,soup=read(BASE+'/paper?cls=%E7%94%B3%E8%AE%BA')
 tasks={}
 for a in soup.select('a[href]'):
  t=a.get_text().strip();m=re.match(r'(20\d\d)年(?:国家|国考)',t)
  if not m or not 2016<=int(m[1])<=2023 or '申论' not in t or '模考' in t:continue
  variant='副省级' if '副省' in t or '省部' in t else '地市级' if '地市' in t else '行政执法' if '行政执法' in t else None
  if not variant:continue
  path=f'国考/{m[1]}/申论-{variant}.md'
  if Path(path).exists():tasks[path]=(path,urljoin(BASE,a['href']),t)
 # Explicit published counterparts, not guessed cross-year sources.
 tasks['zj16a']=('省考/浙江/2016/申论-A类.md',BASE+'/paper/20160802100920','2016年浙江公务员考试《申论》A卷')
 # Discover the B source from the source index; only same-year explicit B.
 try:
  _,zs=read(BASE+'/paper?cls=%E7%94%B3%E8%AE%BA&province=%E6%B5%99%E6%B1%9F')
  for a in zs.select('a[href]'):
   t=a.get_text().strip()
   if re.search(r'^2016年浙江.*申论.*B',t):tasks['zj16b']=('省考/浙江/2016/申论-B类.md',urljoin(BASE,a['href']),t)
 except Exception:pass
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:out=list(pool.map(inspect,tasks.values()))
 Path('reports/R3-WHOLE-PROBE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps([{'path':x['path'],'url':x['url'],'materials':len(x.get('materials',[])),'images':len(x.get('images',[])),'error':x.get('error')} for x in out],ensure_ascii=False))
if __name__=='__main__':main()
