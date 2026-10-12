#!/usr/bin/env python3
"""Audit every essay document by answer type and text completeness, not authority."""
from __future__ import annotations
import collections, hashlib, json, re
from pathlib import Path
from difflib import SequenceMatcher
import round5_bulk as b
from round4_delivery import is_missing
ROOT=b.ROOT

def clean_answer(a):
 a=re.split(r'\n> 来源说明[：:]|\n\[本题(?:既有)?来源记录\]',a,1)[0]
 a=re.split(r'文章分析|【标题的优点|参考答案说明[：:]|【参考答案说明',a,1)[0]
 a=re.sub(r'^\s*(?:\*\*[^\n]+\*\*|【参考答案】|【参考例文】|参考答案[：:]?)\s*\n','',a)
 return a.strip()

def task_type(q):
 q=b.g.clean_q(q)
 ranges=re.findall(r'(\d{3,4})\s*[-—～~至]\s*(\d{3,4})\s*字',q)
 nums=[int(x) for x in re.findall(r'(\d{3,4})\s*字',q)]
 minimum=int(ranges[-1][0]) if ranges else (max(nums) if nums else 0)
 essay=minimum>=800 or bool(re.search(r'自拟题目|议论性文章|议论文|对策性文章',q))
 if re.search(r'短评|提纲|讲话稿|发言稿|汇报材料|公开信|倡议书|建议书|招聘启事',q) and minimum<800:essay=False
 return ('大作文' if essay else '小题参考作答'),minimum

def classify(q,a):
 typ,words=task_type(q)
 if is_missing(a):return {'kind':typ,'status':'缺完整参考作答','text_chars':0,'requested_words':words}
 text=clean_answer(a);chars=len(b.norm(text));flags=[]
 if re.search(r'\ufffd|!\[[^\]]*\]\(\)|(?:本题|答案)暂缺',text):flags.append('异常字符或占位')
 if typ=='大作文' and chars<max(600,int(words*.78)):flags.append('作文长度明显不足，须核对原文尾部')
 if not re.search(r'[。！？!?…）)】\d\.]$',text):flags.append('末尾非正常收束，须核对')
 return {'kind':typ,'status':'需复核正文完整性' if flags else '已有参考作答','text_chars':chars,'requested_words':words,'flags':flags}

def read_all():
 papers=[];failed=[]
 for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]):
  rel=p.relative_to(ROOT).as_posix()
  try:
   d=b.parse(p.read_text(encoding='utf-8'),rel)
   if d:papers.append(d)
  except Exception as e:failed.append({'path':rel,'reason':str(e),'tail':p.read_text(encoding='utf-8')[-650:]})
 return papers,failed

def inspect():
 papers,failed=read_all();rows=[];year=collections.defaultdict(list)
 for p in papers:
  for n,q in p['questions'].items():
   row={'path':p['path'],'number':n,'stem':q.split('要求')[0][:200],**classify(q,p['answers'].get(n,''))}
   rows.append(row)
   if row['status']=='已有参考作答' and len(b.qkey(q))>=24:year[p['identity'][1]].append((p,n,row))
 candidates=[];unmatched=[]
 for p in papers:
  for n,q in p['questions'].items():
   if not is_missing(p['answers'].get(n,'')):continue
   key=b.qkey(q);tm=b.norm(p['materials'][n]);tg=b.shingles(p['materials'][n]);hits=[]
   if len(key)<24:unmatched.append({'path':p['path'],'number':n,'reason':'题干信息过短'});continue
   for d,dn,dr in year[p['identity'][1]]:
    if d['path']==p['path']:continue
    other=b.qkey(d['questions'][dn]);same=p['identity'][0]==d['identity'][0]
    sim=1.0 if key==other else (SequenceMatcher(None,key,other,autojunk=False).ratio() if same else 0)
    if sim<.97:continue
    dg=b.shingles(d['materials'][dn]);dm=b.norm(d['materials'][dn]);a=sum(x in tm for x in dg)/max(1,len(dg));c=sum(x in dm for x in tg)/max(1,len(tg))
    shared=min(len(tm),len(dm))
    if shared<600 or max(a,c)<.97:continue
    if b.g.SCORE.findall(q.split('要求')[0]) and b.g.SCORE.findall(d['questions'][dn].split('要求')[0]) and b.g.SCORE.findall(q.split('要求')[0])!=b.g.SCORE.findall(d['questions'][dn].split('要求')[0]):continue
    targettype,targetwords=task_type(q);dt,dw=task_type(d['questions'][dn])
    if targettype!=dt:continue
    if targetwords and dw and targetwords!=dw:continue
    hits.append({'donor':d['path'],'donor_number':dn,'similarity':sim,'material_directional_coverage':[a,c],'cross_province':not same,'answer_chars':dr['text_chars']})
   if hits:candidates.append({'path':p['path'],'number':n,'candidates':sorted(hits,key=lambda x:(-x['similarity'],-max(x['material_directional_coverage'])))[:3]})
   else:unmatched.append({'path':p['path'],'number':n,'stem':q.split('要求')[0][:160]})
 out={'papers':len(papers)+len(failed),'parsed':len(papers),'unparsed':len(failed),'answer_slots':len(rows),'status_counts':dict(collections.Counter(r['status'] for r in rows)),'essay_status_counts':dict(collections.Counter(r['status'] for r in rows if r['kind']=='大作文')),'candidate_additions':len(candidates),'candidates':candidates,'unmatched':unmatched,'unparsed_files':failed,'rows':rows}
 target=ROOT/'reports/R7-ESSAY-AUDIT-20261013.json';target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('R7_STATUS',json.dumps({k:v for k,v in out.items() if k not in ('candidates','unmatched','unparsed_files','rows')},ensure_ascii=False),flush=True)
 print('R7_CANDIDATES',json.dumps(candidates[:25],ensure_ascii=False),flush=True)
 print('R7_INCOMPLETE_SAMPLES',json.dumps([r for r in rows if r['status']=='需复核正文完整性'][:12],ensure_ascii=False),flush=True)
 print('R7_UNMATCHED_SAMPLE',json.dumps(unmatched[:25],ensure_ascii=False),flush=True)
 print('R7_UNPARSED',json.dumps(failed,ensure_ascii=False),flush=True)
 return out
if __name__=='__main__':inspect()
