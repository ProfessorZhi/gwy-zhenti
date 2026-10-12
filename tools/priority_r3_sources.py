"""Bounded source inspection on a GitHub-hosted runner; no corpus writes."""
from __future__ import annotations
import concurrent.futures, hashlib, json, os, re
from pathlib import Path
import requests
from bs4 import BeautifulSoup

SOURCES = {
 'js16a': 'https://www.jsgkw.org/2016/0315/12413.html',
 'js16b': 'https://www.jsgkw.org/2016/0315/12414.html',
 'js18a': 'https://iget100.com/gongkao/shengkao/jiangsu/2018/shenlun-a',
 'zj16a1': 'https://gwysydw.com/bs/dqgwy/news_88726.html',
 'zj16a2': 'https://gwysydw.com/bs/dqgwy/news_88726.html?page=1',
 'zj16a_alt': 'https://www.gzu521.net/gwy/2016/04/72826.htm',
 'zj16b_alt': 'https://www.gzu521.net/gwy/2016/04/72803.htm',
 'js24a': 'https://iget100.com/gongkao/shengkao/jiangsu/2024/xingce-a',
 'js25c': 'https://iget100.com/gongkao/shengkao/jiangsu/2025/xingce-c',
 'zj20a': 'https://gwysydw.com/bs/dqgwy/news_72984.html?page=2',
 'gk16s': 'https://m.gwysk.cn/guokao/zhenti/1001.html',
 'gk16d': 'https://www.gwysk.cn/guokao/zhenti/1000.html',
}

def get_source(item):
 key,url=item
 try:
  r=requests.get(url,timeout=(8,25),headers={'User-Agent':'Mozilla/5.0 (compatible; private exam source review)'})
  r.raise_for_status();raw=r.content
  if b'%PDF' in raw[:10]:raise ValueError('PDF requires separate visual review')
  if b'charset=gb' in raw[:3000].lower():enc='gb18030'
  else:
   try:raw.decode('utf-8');enc='utf-8'
   except UnicodeDecodeError:enc=r.apparent_encoding
  soup=BeautifulSoup(raw.decode(enc,errors='strict'),'html.parser')
  for t in soup(['script','style','nav','header','footer']):t.decompose()
  ps=[re.sub(r'\s+',' ',s).strip() for s in soup.get_text('\n').splitlines() if s.strip()]
  d={'key':key,'url':url,'final_url':r.url,'sha256':hashlib.sha256(raw).hexdigest(),'encoding':enc,'title':soup.title.get_text() if soup.title else '', 'paragraphs':ps}
  cache=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'priority-r3-sources';cache.mkdir(exist_ok=True)
  (cache/(key+'.json')).write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
  hits=[]
  pat=re.compile(r'参考答案|作答要求|答题要求|问题[一二三四五]|第\s*[12345]\s*题|第一题|第二题|第三题|第四题|第五题|^\s*[（(][一二三四五][)）]')
  for i,p in enumerate(ps):
   if pat.search(p):hits.append({'i':i,'text':p[:180],'next':ps[i+1:i+3] if len(p)<30 else []})
  if key in ['js24a','js25c']:
   nums=[76,96,110,111] if key=='js24a' else [27,29,35,36,37,42,75,77,78,80,81,85]
   hits=[]
   for n in nums:
    ix=next((i for i,p in enumerate(ps) if re.search(r'^第\s*'+str(n)+r'\s*题',p)),None)
    if ix is not None:hits.append({'q':n,'paragraphs':ps[ix:ix+6]})
  return {k:v for k,v in d.items() if k!='paragraphs'}|{'characters':sum(map(len,ps)),'paragraph_count':len(ps),'head':ps[:8],'markers':hits[:70]}
 except Exception as e:return {'key':key,'url':url,'error':str(e)}

def main():
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:out=list(pool.map(get_source,SOURCES.items()))
 selected=['省考/江苏/2016/申论-A类.md','省考/江苏/2016/申论-B类.md','省考/江苏/2018/申论-A类.md','省考/浙江/2016/申论-A类.md','省考/浙江/2016/申论-B类.md']
 selected += [str(p) for p in sorted(Path('国考').glob('20*/申论-*.md')) if int(p.parent.name)<=2023]
 papers=[]
 for path in selected:
  s=Path(path).read_text(encoding='utf-8');head=s.split('---',2)[1];body=s.split('## 答案与解析')[0]
  qs=[]
  for m in re.finditer(r'^## 第\s*(\d+)\s*题.*?\n(.*?)(?=^## 第\s*\d+\s*题|\Z)',body,re.M|re.S):
   q=m[2];req=q.split('### 作答要求',1)[-1].strip();qs.append({'number':int(m[1]),'requirements':req[-1200:]})
  papers.append({'path':path,'sha256':hashlib.sha256(s.encode()).hexdigest(),'metadata':head,'questions':qs})
 report={'baseline':'74cd629e6318af0a30c77c0a3f0c8b0befaf4d22','mode':'source inspection only; no truth claims','sources':out,'existing_papers':papers}
 Path('reports/R3-SOURCE-SCOUT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'sources':[{k:v for k,v in s.items() if k not in ['markers','head']} for s in out],'papers':len(papers)},ensure_ascii=False))
if __name__=='__main__':main()
