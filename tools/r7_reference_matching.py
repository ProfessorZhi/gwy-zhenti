#!/usr/bin/env python3
"""Find complete same-question references; alternative answers need not be identical."""
from __future__ import annotations
import collections,hashlib,json,re
from difflib import SequenceMatcher
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing
from r7_reference_audit import assess,main_answer,word_range,task_type
ROOT=b.ROOT
BASE='1ee302b18cb864cadc6bf7cfb0376a9da018e203'

def qkey(q):
 q=re.sub(r'<!--.*?-->','',q,flags=re.S)
 q=re.sub(r'(?m)^\s*#+\s*','',q).replace('**','')
 return b.qkey(q)
def plain(t):return b.norm(t)
def source_usable(q,a):
 if is_missing(a):return False
 text=main_answer(a)
 if len(plain(text))<45 or '\ufffd' in text or re.search(r'javascript:|<script|!\[|<img',text,re.I):return False
 if re.search(r'正文(?:省略|略)|此题暂缺|答案暂未|略去|待补充',text):return False
 return assess(q,a)['status']=='已收录'
def read_all():
 papers=[];bad=[]
 for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]):
  rel=p.relative_to(ROOT).as_posix()
  try:
   d=b.parse(p.read_text(encoding='utf-8'),rel)
   if d:papers.append(d)
  except Exception as e:bad.append({'path':rel,'reason':str(e)})
 return papers,bad

def material_evidence(target,source):
 a=plain(target);z=plain(source)
 if len(a)<300 or len(z)<300:return None
 # Both direction ratios are recorded; an individual question may use only one of the shared materials.
 src={z[i:i+16] for i in range(0,len(z)-15,8)}
 dst={a[i:i+16] for i in range(0,len(a)-15,8)}
 hit=sum(v in a for v in src);reverse=sum(v in z for v in dst)
 return {'source_coverage':hit/max(1,len(src)),'target_coverage':reverse/max(1,len(dst)),'matching_source_fragments':hit,'source_fragments':len(src),'target_fragments':len(dst)}
def limits_ok(q,s):
 _,top=word_range(q);_,stop=word_range(s)
 return not top or not stop or abs(top-stop)<=max(100,top*.2)

def find_internal(papers):
 pool=collections.defaultdict(list)
 for d in papers:
  for n,a in d['answers'].items():
   if n in d['questions'] and source_usable(d['questions'][n],a):
    pool[d['identity'][1]].append((qkey(d['questions'][n]),d,n))
 plans=[];left=[];reason=collections.Counter()
 for target in papers:
  adds=[]
  for n,q in target['questions'].items():
   old=target['answers'].get(n,'');state=assess(q,old)
   if state['status']=='已收录':continue
   k=qkey(q);rank=[];seen_stage='no_same_question'
   for sk,d,dn in pool[target['identity'][1]]:
    if d['path']==target['path']:continue
    samearea=d['identity'][0]==target['identity'][0]
    if len(k)<20:continue
    sim=1. if k==sk else (SequenceMatcher(None,k,sk,autojunk=False).ratio() if samearea else 0.)
    if sim<.97:continue
    seen_stage='material_mismatch'
    proof=material_evidence(target['materials'][n],d['materials'][dn])
    if not proof:continue
    coverage=max(proof['source_coverage'],proof['target_coverage'])
    threshold=.85 if samearea else .98
    if coverage<threshold or proof['matching_source_fragments']<25:continue
    if not samearea and k!=sk:continue
    seen_stage='word_limit_or_completeness'
    if not limits_ok(q,d['questions'][dn]) or not source_usable(q,d['answers'][dn]):continue
    count=len(re.sub(r'\s','',main_answer(d['answers'][dn])))
    rank.append((sim,coverage,samearea,count,d,dn,proof))
   if not rank:
    reason[seen_stage]+=1;left.append({'path':target['path'],'number':n,'reason':seen_stage,'state':state['status']});continue
   rank.sort(key=lambda x:(x[0],x[1],x[2],min(x[3],1500)),reverse=True)
   sim,cov,samearea,count,d,dn,proof=rank[0]
   answer=main_answer(d['answers'][dn])
   # Independent references may disagree in wording; select one complete same-question version and keep provenance.
   adds.append({'number':n,'answer':answer,'kind':'repository_reference','donor_path':d['path'],'donor_number':dn,
     'donor_file_sha256':g.digest(d['text']),'donor_answer_sha256':g.digest(d['answers'][dn]),'donor_question_sha256':g.digest(d['questions'][dn]),
     'target_question_sha256':g.digest(q),'answer_sha256':g.digest(answer),'answer_length':len(answer),
     'stem_similarity':sim,'material_proof':proof,'cross_province':not samearea,'alternative_versions':len(rank),
     'was_missing':is_missing(old),'source_title':d['path'],'source_revision':BASE,
     'source_url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+__import__('urllib.parse',fromlist=['quote']).quote(d['path'],safe='/')})
   reason['candidate']+=1
  if adds:plans.append((target,adds))
 return plans,left,reason

def main():
 papers,bad=read_all();plans,left,diag=find_internal(papers)
 print('R7_REFERENCE_MATCH',json.dumps({'papers':len(papers),'unparsed':len(bad),'candidate_papers':len(plans),'candidate_answers':sum(len(a) for _,a in plans),'missing_filled':sum(x['was_missing'] for _,aa in plans for x in aa),'diagnosis':diag},ensure_ascii=False),flush=True)
 print('R7_REFERENCE_CANDIDATES',json.dumps([{'path':t['path'],'n':[a['number'] for a in adds],'versions':[a['alternative_versions'] for a in adds]} for t,adds in plans],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
