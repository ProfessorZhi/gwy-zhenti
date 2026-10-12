#!/usr/bin/env python3
"""Bounded source discovery; downloaded data are temporary and never committed."""
import concurrent.futures, hashlib, json, os, pathlib, re, urllib.parse, urllib.request
from html.parser import HTMLParser
OUT=pathlib.Path(os.environ.get('EVIDENCE_DIR','/tmp/priority-evidence'));OUT.mkdir(parents=True,exist_ok=True)
def get(url,limit=45000000):
    request=urllib.request.Request(url,headers={'User-Agent':'gwy-zhenti-source-review/1.0'})
    with urllib.request.urlopen(request,timeout=40) as r:data=r.read(limit+1)
    if len(data)>limit:raise ValueError('source exceeds byte limit')
    return data
class Links(HTMLParser):
    def __init__(self):super().__init__();self.current=None;self.text=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.current=dict(attrs).get('href');self.text=[]
    def handle_data(self,data):
        if self.current:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.current:self.links.append((self.current,''.join(self.text)));self.current=None
jobs=[];identities=[]
for page in ['https://www.chinagwy.net/zjsk/317178.jhtml','https://www.chinagwy.net/zjsk/202250.jhtml']:
    raw=get(page);parser=Links();parser.feed(raw.decode('utf-8',errors='replace'))
    for url,title in parser.links:
        if '.pdf' not in url.lower() or '申论' not in title or re.search('模考|模拟|素材|小题海',title):continue
        years=re.findall(r'20\d{2}',title)
        if not years or not 2016<=int(years[0])<=2026:continue
        url=urllib.parse.urljoin(page,url);name='pdf/'+hashlib.sha256(url.encode()).hexdigest()[:16]+'.pdf'
        jobs.append((name,url));identities.append({'file':name,'title':title,'listing':page,'url':url})
for area in ['江苏','浙江','北京','广州']:
    index=json.loads(get('https://gwy.gkzhenti.cn/api/json?'+urllib.parse.urlencode({'cls':'申论','province':area})))
    for entry in index:
        title=entry['Title'];years=re.findall(r'20\d{2}',title)
        if not years or not 2016<=int(years[0])<=2026 or re.search('模考|模拟|选调生考试|定向选调',title):continue
        if area not in ('江苏','浙江') and not (area=='广州' and '2017' in title):continue
        url=entry['No'];name='online/'+url.rsplit('/',1)[-1]+'.html'
        jobs.append((name,url));identities.append({'file':name,'title':title,'url':url})
extra=[
 ('zj-shenlun-collection.pdf','https://static.32xueyuan.com/zq//u/cms/zj/202411/20204753h6td.pdf'),
 ('zj-shenlun-collection2.pdf','https://static.32xueyuan.com/zq//u/cms/zj/202411/07163022hqbt.pdf'),
 ('zj-xingce-collection.pdf','https://static.32xueyuan.com/zq/u/cms/www/202411/081140208uqn.pdf'),
 ('gz2017-xc.html','https://gwy.gkzhenti.cn/paper/1509439949092'),
 ('js2026-a-discussion.html','https://www.yeyulingfeng.com/a/1110030.html'),
 ('js2026-b-discussion.html','https://www.yeyulingfeng.com/a/1134499.html'),
 ('zj2022-official.html','https://www.zjzzgz.gov.cn/art/2022/6/12/art_1413011_58890982.html'),
 ('js2026-official.html','https://www.jsxf.gov.cn/tzgg/art/2025/art_4b4f6c1ef283b21741ec26bc3c0ecc30.html')]
jobs+=extra;jobs=list(dict(jobs).items())
def fetch(job):
    name,url=job
    try:
        b=get(url)
        if name.endswith('.pdf') and not b.startswith(b'%PDF'):raise ValueError('not a PDF')
        p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        return {'file':name,'url':url,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    except Exception as e:return {'file':name,'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:results=list(ex.map(fetch,jobs))
(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'identities.json').write_text(json.dumps(identities,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'candidates':len(results),'downloaded':sum('error' not in x for x in results)},ensure_ascii=False))
