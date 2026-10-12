#!/usr/bin/env python3
"""Audit every essay file and derive scoped source requests without inventing answers."""
import collections,hashlib,json,re
from pathlib import Path
import round5_bulk as b
from round4_delivery import is_missing
ROOT=b.ROOT

def main_answer(a):
 a=re.split(r'\n\s*>\s*来源说明[:：]|\n\s*\[本题(?:既有)?来源记录\]',a,1)[0]
 a=re.split(r'参考答案说明[：:]|文章分析|【(?:题目精析|审题及答题思路|解析|试题解析)】',a,1)[0]
 a=re.sub(r'<[^>]+>','',a)
 a=re.sub(r'!\[[^\]]*\]\([^)]*\)','',a)
 return a.strip()
def word_range(q):
 nums=[]
 for x,y in re.findall(r'(\d{2,4})\s*(?:[-—~～至]\s*(\d{2,4}))?\s*字',q):
  nums.append((int(x),int(y) if y else int(x)))
 return nums[-1] if nums else (0,0)
def task_type(q):
 lo,hi=word_range(q)
 if hi>=700 and re.search(r'文章|作文|议论|题目|自拟|命题',q):return '作文范文'
 if re.search(r'讲话稿|发言稿|倡议书|建议书|汇报|报告|简报|信息|启事|短评|导言|提纲|材料',q):return '小题参考作答'
 return '小题参考作答'
def assess(q,a):
 if is_missing(a):return {'status':'待补','kind':task_type(q),'characters':0}
 text=main_answer(a);count=len(re.sub(r'\s','',text));lo,hi=word_range(q);kind=task_type(q)
 state='已收录'
 if kind=='作文范文' and count<max(500,int(lo*.75)):state='正文偏短待复核'
 elif count<35:state='正文或图像待复核'
 return {'status':state,'kind':kind,'characters':count,'question_word_range':[lo,hi]}
def fingerprint(q):
 k=b.qkey(q);v=[0]*64
 for gram in {k[i:i+3] for i in range(max(0,len(k)-2))}:
  h=int.from_bytes(hashlib.sha256(gram.encode()).digest()[:8],'big')
  for j in range(64):v[j]+=1 if h>>j&1 else -1
 return format(sum(1<<j for j,x in enumerate(v) if x>=0),'016x')
def audit():
 rows=[];requests={};counts=collections.Counter();failed=[]
 paths=sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')])
 for p in paths:
  rel=p.relative_to(ROOT).as_posix();text=p.read_text(encoding='utf-8')
  try:
   d=b.parse(text,rel)
   if not d:raise ValueError('Not classified as essay')
   row={'path':rel,'identity':d['identity'],'tasks':[]}
   for n,q in d['questions'].items():
    s=assess(q,d['answers'].get(n,''));s.update({'number':n,'question_key':b.qkey(q),'question_excerpt':q.split('要求')[0][:180]})
    row['tasks'].append(s);counts[s['kind']+'/'+s['status']]+=1
    if s['status']!='已收录':
     area,year=d['identity'];requests.setdefault(year,{}).setdefault(area,set()).add(fingerprint(q))
   row['status']='已收录' if all(x['status']=='已收录' for x in row['tasks']) else '需补录或复核'
   rows.append(row)
  except Exception as e:
   failed.append({'path':rel,'reason':str(e)})
 return rows,failed,{y:{a:sorted(v) for a,v in aa.items()} for y,aa in requests.items()},counts

def main():
 rows,bad,requests,counts=audit()
 summary={'papers_total':len(rows)+len(bad),'parsed_papers':len(rows),'unparsed_papers':len(bad),'papers_with_all_recognized_answers':sum(r['status']=='已收录' for r in rows),'question_classifications':counts,'unparsed':bad,'boundary':'Content/length triage only; quality review still considers argument and relevance.'}
 print('ALL_ESSAYS_AUDIT',json.dumps(summary,ensure_ascii=False),flush=True)
 for y,aa in sorted(requests.items()):print('SOURCE_REQUESTS_'+y,json.dumps(aa,ensure_ascii=False,separators=(',',':')),flush=True)
 # Current source-backed additions may now unlock other same-exam records.
 papers,unparsed,plans,left,diag=b.scan()
 print('NEW_INTERNAL_SOURCE_MATCHES',json.dumps({'papers':len(plans),'answers':sum(len(a) for _,a in plans),'sample':[{'path':t['path'],'n':[x['number'] for x in a]} for t,a in plans[:12]]},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
