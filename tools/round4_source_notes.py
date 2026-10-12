#!/usr/bin/env python3
"""Attach bounded source notes, explicitly not full answers; fail closed per source."""
import json,re
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup,UnicodeDammit
import round4_gap_repair as g
from round4_delivery import receipt,is_missing,RECEIPT
ROOT=g.ROOT
SPECS=[
 {'path':'省考/浙江/2016/申论-A类.md','url':'https://www.gzu521.net/gwy/2016/04/72826.htm','variant':'A','notes':{3:'来源范文把创业比作持续攀登：先讨论获得财富与社会认可的吸引力，再转向个人成长和社会贡献，最后提醒创业者正视风险，避免只追逐金钱，以理想和坚持支撑行动。此处只整理文章脉络，不是符合题目字数要求的完整作文。'}},
 {'path':'省考/浙江/2016/申论-B类.md','url':'https://www.gzu521.net/gwy/2016/04/72803.htm','variant':'B','notes':{2:'来源要点可归为四个方面：汇集出资、人才与行业资源；使出资者同时参与消费和传播；利用合作关系拓展后续项目；校园众筹结合专业运营、创业交流和股权流转安排。这是来源要点摘要，不是原答案全文。',3:'来源范文从创业带来的机会、自我成长与社会价值展开，并以风险意识和持续奋斗收束。此处提供阅读线索，不把短摘要当作完整议论文。'}}
]
def main():
 p=ROOT/'reports'/RECEIPT
 records=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x]
 seen={r['path'] for r in records};notes=[];rejected=[];ready=[]
 for s in SPECS:
  try:
   if s['path'] in seen:raise ValueError('Already repaired; no overwrite')
   with urlopen(Request(s['url'],headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as response:raw=response.read(1000000)
   soup=BeautifulSoup(UnicodeDammit(raw,is_html=True).unicode_markup,'html.parser')
   for x in soup(['script','style','noscript']):x.decompose()
   title=soup.title.get_text('',strip=True) if soup.title else '';source_text=soup.get_text('',strip=True)
   if not all(x in title for x in ['浙江','2016','申论',s['variant']]) or '第三题' not in source_text or '创业者心中的山' not in source_text:raise ValueError('Source identity changed: '+title)
   target=ROOT/s['path'];old=target.read_text(encoding='utf-8');paper=g.parse_text(old,s['path'])
   for n in s['notes']:
    if n not in paper['questions'] or not is_missing(paper['answers'].get(n,'')):raise ValueError('Not a pending answer')
   if 2 in s['notes'] and not all(word in source_text for word in ['众筹','资源','校园']):raise ValueError('Wrong crowdfunding source')
   def sub(m):
    n=int(m[2])
    if n not in s['notes']:return m[0]
    return m[1]+m[3].rstrip()+'\n\n**已找到的外部参考资料（摘要，不计作完整答案）**\n\n'+s['notes'][n]+'\n\n[阅读来源参考答案全文]('+s['url']+')（非官方标准答案）。\n\n'+m[4]
   new=g.DETAIL.sub(sub,old)
   new=g.set_fields(new,{'已定位外部答案来源题号':sorted(s['notes']),'外部答案收录形式':'来源链接与有限摘要；完整答案缺项保持','第四轮修复凭据':'reports/'+RECEIPT},'2026-10-12第四轮：补充外部答案入口与摘要；不将摘要计为完整参考答案')
   r=receipt(old,new,paper,[]);r['kind']='answer_source_notes';r['source_notes']={'url':s['url'],'sha256':g.digest(raw),'title':title,'question_ids':sorted(s['notes']),'counted_as_full_answers':False}
   ready.append((target,new,r));notes.append({'path':s['path'],**r['source_notes']})
  except Exception as e:rejected.append({'path':s['path'],'url':s['url'],'reason':str(e)})
 for target,new,r in ready:
  if g.digest(target.read_text(encoding='utf-8'))!=r['before_sha256']:raise ValueError('Concurrent note target change')
  target.write_text(new,encoding='utf-8',newline='\n')
  if g.digest(target.read_bytes())!=r['after_sha256']:raise ValueError('Note readback mismatch')
  records.append(r)
 p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
 (ROOT/'reports/ROUND4-EXTERNAL-SOURCES-20261012.json').write_text(json.dumps({'added':notes,'not_added':rejected},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('SOURCE_NOTES',json.dumps({'papers':len(notes),'question_slots':sum(len(x['question_ids']) for x in notes),'full_answers_added':0,'not_added':rejected},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
