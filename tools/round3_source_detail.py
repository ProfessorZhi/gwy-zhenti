#!/usr/bin/env python3
from round3_source_probe import fetch
from bs4 import BeautifulSoup,UnicodeDammit
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from pathlib import Path
import re,json,hashlib
SOURCES={
 'national_index':'https://www.aipta.com/zt/gk/sl/',
 'gk16ds':'https://www.aipta.com/article/179.html',
 'zj16a':'https://gwysydw.com/bs/dqgwy/news_88726.html/',
 'zj16ap2':'https://gwysydw.com/bs/dqgwy/news_88726.html?page=1',
 'zj16b':'http://new.zbgwy.com/index.php/essay/detail.html?id=8920',
 'js16b':'http://www.jsgkw.org/2016/0315/12414.html',
 'js16aiget':'https://iget100.com/gongkao/shengkao/jiangsu/2016/shenlun-a',
 'js16biget':'https://iget100.com/gongkao/shengkao/jiangsu/2016/shenlun-b',
 'js18a':'https://iget100.com/gongkao/shengkao/jiangsu/2018/shenlun-a',
 'zj16ba':'https://www.gzu521.net/gwy/2016/04/72803.htm',
 'zj16kap':'https://www.kangaroo.top/question_bank/essay_papers/zhejiang/zhejiang_2016_shenlun_b_2'
}
def run(item):
 k,u=item
 try:
  raw,ls,_,final=fetch(u);s=BeautifulSoup(UnicodeDammit(raw,is_html=True).unicode_markup,'html.parser')
  out=[f'DETAIL {k} {len(raw)} {hashlib.sha256(raw).hexdigest()}']
  if k=='national_index':
   for a in s.select('a[href]'):
    t=a.get_text('',strip=True)
    if re.search('201[6-9]|202[0-3]',t) and '申论' in t:out.append(json.dumps({'title':t,'url':urljoin(u,a['href'])},ensure_ascii=False))
   return '\n'.join(out)
  if 'iget' in k or k=='js18a':
   for e in s.find_all(string=re.compile('完整试卷与参考答案|^第 [1-5] 题：|^参考答案：')):
    out.append('DOM '+str(e.parent)[:1100]+' PARENT '+str(e.parent.parent.attrs))
   if k=='js18a':
    for i,l in enumerate(ls):
     if i>=159:out.append(f'{i}: {l}')
   else:
    for i,l in enumerate(ls):
     if '社会风气' in l or '参考答案' in l or l.startswith(('积极影响','消极影响','1.','一、')):out.append(f'{i}: {l[:3000]}')
  elif k=='zj16kap':
   for sc in s.find_all('script'):
    t=sc.get_text();out.append('SCRIPT '+str(sc.attrs)+' '+t[:12000])
   for e in s.find_all(string=re.compile('创业成功是|展板|1000|创业者心中')):out.append('TARGET '+str(e.parent)[:4000])
  else:
   for i,p in enumerate(s.find_all(['p','h1','h2','h3','h4'])):
    t=p.get_text('',strip=True)
    if not t:continue
    if k=='gk16ds' and len(t)>400:t=t[:80]+'...'+t[-80:]
    out.append(f'{i}: '+t+' PARENT='+str(p.parent.attrs)[:160])
  return '\n'.join(out)
 except Exception as e:return 'ERROR '+k+' '+str(e)
if __name__=='__main__':
 root=Path(__file__).resolve().parents[1]
 a=(root/'省考/江苏/2016/申论-A类.md').read_text();b=(root/'省考/江苏/2016/申论-B类.md').read_text()
 for n,t in [('A',a),('B',b)]:
  chunks=re.findall(r'^## 给定资料 (\d+)\n(.*?)(?=^## |\Z)',t,re.S|re.M)
  print('JS16_MATERIALS',n,json.dumps([(i,len(re.sub(r'\s','',x)),hashlib.sha256(re.sub(r'\s','',x).encode()).hexdigest()) for i,x in chunks],ensure_ascii=False))
 with ThreadPoolExecutor(max_workers=6) as ex:
  for r in ex.map(run,SOURCES.items()):print(r,flush=True)
