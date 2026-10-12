#!/usr/bin/env python3
"""Read-only source probe for the specifically authorized third repair round.
No local-device agent, no corpus writes and no credentials in output.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin
import hashlib,json,re
from bs4 import BeautifulSoup, UnicodeDammit

SOURCES={
 'js16a':'https://www.yjbys.com/edu/gongwuyuankaoshi/125956.html',
 'js16b':'https://www.jsgkw.org/2016/0315/12414.html',
 'js16b2':'https://www.sanlianbook.com/public/index.php/shows/6/469.html',
 'js16b3':'https://edu.newdu.com/Official/Class944/Class966/201708/211087_5.html',
 'js18a':'https://iget100.com/gongkao/shengkao/jiangsu/2018/shenlun-a',
 'js18a2':'https://www.zwguohua.com/question-bank/26',
 'zj16a':'https://gwysydw.com/bs/dqgwy/news_88726.html/',
 'zj16pdf':'https://www.chinagwy.org/files/20180503150627_39246.pdf',
 'zj16b':'https://new.zbgwy.com/index.php/essay/detail.html?id=8920',
 'zj16b2':'https://www.kangaroo.top/question_bank/essay_papers/zhejiang/zhejiang_2016_shenlun_b_2',
 'gk16ds':'https://www.gwysk.cn/guokao/zhenti/1000.html',
 'gk16fs':'https://m.gwysk.cn/guokao/zhenti/1001.html',
 'gk16ds2':'https://www.aipta.com/article/179.html',
 'gk16pdf':'https://www.chinagwy.org/files/20180411143526_17117.pdf'
}

def fetch(url):
 req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; exam-source-verification)'})
 with urlopen(req,timeout=35) as r:
  data=r.read(15_000_001)
  if len(data)>15_000_000:raise ValueError('Oversized source')
  final=r.url
 if data.startswith(b'%PDF'):
  import fitz
  with fitz.open(stream=data,filetype='pdf') as doc:
   lines=[f'PDF_PAGE {i+1} '+p.get_text() for i,p in enumerate(doc)]
  return data,lines,[],final
 soup=BeautifulSoup(UnicodeDammit(data,is_html=True).unicode_markup,'html.parser')
 for n in soup(['script','style','noscript']):n.decompose()
 links=[(a.get_text(' ',strip=True),urljoin(final,a['href'])) for a in soup.select('a[href]') if re.search(r'下一页|^[2345]$|\.pdf|\.docx|2016|2017|2018',a.get_text(' ',strip=True)+' '+a['href'],re.I)]
 lines=[x.strip() for x in soup.get_text('\n').splitlines() if x.strip()]
 return data,lines,links,final

def probe(item):
 key,url=item
 try:
  b,ls,links,final=fetch(url)
  record={'source':key,'url':url,'final_url':final,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'lines':len(ls),'links':links[:45]}
  out=['SOURCE '+json.dumps(record,ensure_ascii=False)]
  if b.startswith(b'%PDF'):
   for i,l in enumerate(ls):
    out.append(f'{key} [{i}] '+l[:15000])
  else:
   for i,l in enumerate(ls):
    if re.search(r'申论|第一题|问题[一二三四五]|作答要求|答题要求|参考答案|答案[一二三四]|第\s*[1-5]\s*题|^[（(]?[一二三四五][）)、]|^材料[0-9一二三四五六七八九十]|给定资料|积极影响|消极影响|众筹|创业者心中的山',l):
     out.append(f'{key} [{i}] '+l[:2300])
  return '\n'.join(out)
 except Exception as e:return 'SOURCE_ERROR '+key+' '+type(e).__name__+' '+str(e)

def main():
 root=Path(__file__).resolve().parents[1]
 paths=['省考/江苏/2016/申论-A类.md','省考/江苏/2016/申论-B类.md','省考/江苏/2018/申论-A类.md','省考/浙江/2016/申论-A类.md','省考/浙江/2016/申论-B类.md']
 paths += [str(p.relative_to(root)) for p in sorted((root/'国考').glob('20*/申论-*.md')) if int(p.parent.name)<=2023]
 for rel in paths:
  t=(root/rel).read_text(encoding='utf-8');front=t.split('## 答案与解析')[0]
  questions=[]
  for m in re.finditer(r'^## 第 (\d+) 题[^\n]*\n(.*?)(?=^## 第 \d+ 题|\Z)',front,re.S|re.M):
   body=m[2];stem=body.split('### 作答要求')[-1].strip()
   questions.append({'n':int(m[1]),'stem':stem[:1600],'material_chars':len(body)-len(stem)})
  print('ORIGINAL '+json.dumps({'path':rel,'sha256':hashlib.sha256(t.encode()).hexdigest(),'questions':questions,'metadata':t.split('---',2)[1],'details':[(int(n),len(a),a[:80]) for n,a in re.findall(r'<summary>第 (\d+) 题</summary>(.*?)</details>',t,re.S)]},ensure_ascii=False))
 with ThreadPoolExecutor(max_workers=6) as ex:
  for output in ex.map(probe,SOURCES.items()):print(output,flush=True)
if __name__=='__main__':main()
