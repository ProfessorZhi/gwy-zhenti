"""Second bounded read: whole-paper candidate inspection, no corpus mutation."""
import concurrent.futures,json,os,re
from pathlib import Path
from priority_r3_sources import get_source
URLS={
 'js16a_iget':'https://iget100.com/gongkao/shengkao/jiangsu/2016/shenlun-a',
 'js16b_iget':'https://iget100.com/gongkao/shengkao/jiangsu/2016/shenlun-b',
 'js16a_ref':'https://www.yjbys.com/edu/gongwuyuankaoshi/125956.html',
 'js16a_doc':'https://www.yeyulingfeng.com/wendang/379405.html',
 'js18a':'https://iget100.com/gongkao/shengkao/jiangsu/2018/shenlun-a',
 'zj16a1':'https://gwysydw.com/bs/dqgwy/news_88726.html',
 'zj16a2':'https://gwysydw.com/bs/dqgwy/news_88726.html?page=1',
 'zj16cat':'https://www.gwysydw.com/bs/dqgwy/22-7-2016/',
 'zj16b':'https://new.zbgwy.com/index.php/essay/detail.html?id=8920',
 'gk16d':'https://m.jinbiaochi.com/qggk/news_80741.html',
 'gk16s':'https://www.kkgwy.com/sl/zt/2015/11/30/125415.html',
 'gk16d_eol':'https://www.eol.cn/gongwuyuan/guojia/zhenti/201512/t20151203_1344635.shtml',
 'gk17d_eol':'https://www.eol.cn/gongwuyuan/guojia/zhenti/201611/t20161128_1471191.shtml',
 'gk16s_ref':'https://www.hqwx.com/gjgwy-kaoshi/news/14488505595293.html',
}

def main():
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:summaries=list(pool.map(get_source,URLS.items()))
 cache=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'priority-r3-sources'
 sources=[]
 for s in summaries:
  p=cache/(s['key']+'.json')
  if p.exists():
   full=json.loads(p.read_text());full['paragraphs']=[{'i':i,'text':t} for i,t in enumerate(full['paragraphs'])]
   if s['key']=='js18a':full['paragraphs']=full['paragraphs'][155:]
   if s['key']=='js16a_doc':full['paragraphs']=[x for x in full['paragraphs'] if x['i']>175]
   sources.append(full)
  else:sources.append(s)
 Path('reports/R3-SOURCE-PROBE2.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 # Existing per-question source identity and exactly preserved answer availability.
 a=Path('省考/江苏/2016/申论-A类.md').read_text();b=Path('省考/江苏/2016/申论-B类.md').read_text()
 def mats(s):
  out={}
  for m in re.finditer(r'^## 给定资料 (\d+)\n(.*?)(?=^## |\Z)',s,re.M|re.S):out[m[1]]=re.sub(r'\s+','',m[2])
  return out
 ma,mb=mats(a),mats(b)
 print(json.dumps({'same_2016_AB_materials':{i:ma[i]==mb.get(i) for i in ma},'sources':[{k:v for k,v in s.items() if k not in ['markers','head']} for s in summaries]},ensure_ascii=False))
if __name__=='__main__':main()
