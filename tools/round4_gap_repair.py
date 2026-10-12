#!/usr/bin/env python3
"""Conservative answer-gap discovery with same-year/area identity and material proof."""
from __future__ import annotations
import argparse, collections, hashlib, json, re, unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
BASE='3b2c9aa91813b97b80231f2055d5bfab7eb96173'
RECEIPT='ROUND4-ANSWERS-20261012.jsonl'
DETAIL=re.compile(r'(<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>)(.*?)(</details>)',re.S)
QH=re.compile(r'(?m)^#{2,3}\s+第\s*(\d+)\s*题[^\n]*\n')
AH=re.compile(r'(?m)^##\s+(?:答案与解析|参考答案|参考答案与解析|答案解析)\s*$')
SCORE=re.compile(r'[（(]\s*(\d+)\s*分\s*[）)]')
EMPTY=re.compile(r'^[>*\s]*(?:未收录|尚未|未取得|暂无|暂缺|(?:答案|本题|参考答案)[：:]?\s*(?:略|暂无|暂缺))')
def digest(t):return hashlib.sha256(t.encode() if isinstance(t,str) else t).hexdigest()
def plain(t):return ''.join(c for c in unicodedata.normalize('NFKC',t) if c.isalnum())
def field(t,k):
 m=re.search(r'^'+re.escape(k)+r':\s*(.*?)\s*$',t,re.M)
 if not m:return ''
 try:return json.loads(m[1])
 except (ValueError,TypeError):return m[1].strip('"\'')
def empty(a):return not a.strip() or bool(EMPTY.match(a))
def clean_q(q):
 for h in ['### 作答要求','### 答题要求']:
  if h in q:q=q.split(h,1)[1];break
 return q.strip()
def key(q):
 q=clean_q(q).split('要求')[0]
 q=re.sub(r'^(?:问题[一二三四五六七八九十\d]+[：:]|第[一二三四五六七八九十\d]+题[：:]?|[（(]?[一二三四五六七八九十\d]+[）)、.．])\s*','',q)
 q=SCORE.sub('',q)
 q=re.sub(r'给定(?:资料|材料)\s*[一二三四五六七八九十\d\-—～~、至和与及]*','给定资料',q)
 return plain(q)
def grams(t):
 p=plain(t);return {p[i:i+12] for i in range(0,max(0,len(p)-11),4)}
def parse_text(text,rel):
 if field(text,'科目')!='申论':return None
 ident=(str(field(text,'地区')),str(field(text,'年份')))
 if not all(ident):raise ValueError('Missing year/area')
 ah=list(AH.finditer(text))
 if len(ah)>1:raise ValueError('Ambiguous answer section')
 front=text[:ah[0].start()] if ah else text
 ans={}
 if ah:
  for m in DETAIL.finditer(text[ah[0].end():]):
   n=int(m[2])
   if n in ans:raise ValueError('Duplicate answer number')
   ans[n]=m[3].strip()
  if not ans:raise ValueError('Answer heading exists but unrecognized answer layout')
 elif '<details>' in text or re.search(r'(?m)^#{1,3}.*(?:答案|解析)',text):raise ValueError('Unrecognized existing answers; do not append')
 qh=list(QH.finditer(front));qs={};mats={};spans={}
 if qh:
  mode='details' if ah else 'headings'
  for j,h in enumerate(qh):
   n=int(h[1]);end=qh[j+1].start() if j+1<len(qh) else len(front)
   if n in qs:raise ValueError('Duplicate question')
   raw=front[h.end():end];qs[n]=clean_q(raw);spans[n]=h.start()
   mats[n]=raw.split('### 作答要求')[0] if '### 作答要求' in raw else front[:qh[0].start()]
 else:
  mode='unstructured'
  boundaries=list(re.finditer(r'(?m)^\s*(?:#{1,3}\s*)?(?:[一二三四五][、.．]\s*)?(?:作答要求|答题要求|申论要求)\s*[：:]?\s*$',front))
  start=boundaries[-1].end() if boundaries else 0
  # Require scored task paragraphs and complete requirements; never infer from filenames.
  ps=[m for m in re.finditer(r'\S[\s\S]*?(?=\n\s*\n|\Z)',front[start:]) if m[0].strip()]
  starts=[]
  for i,m in enumerate(ps):
   t=m[0].strip();s=SCORE.search(t)
   explicit=bool(re.match(r'^(?:问题|第[一二三四五六七八九十\d]+题|[（(]?[一二三四五六七八九十\d]+[）)、.．])',t))
   if s and not t.startswith('要求') and (boundaries or explicit) and len(t.split('要求')[0])>15:starts.append((i,int(s[1])))
  if not 2<=len(starts)<=6 or sum(s for _,s in starts)!=100:raise ValueError('Cannot prove complete scored task boundaries')
  first=start+ps[starts[0][0]].start();material=front[:first]
  for j,(i,_) in enumerate(starts):
   a=start+ps[i].start();b=start+ps[starts[j+1][0]].start() if j+1<len(starts) else len(front)
   q=front[a:b].strip()
   if not re.search(r'\d+\s*(?:[-—～~]\s*\d+\s*)?字',q) or '要求' not in q:raise ValueError('Missing requirement or word limit')
   qs[j+1]=q;mats[j+1]=material;spans[j+1]=a
 if not qs or set(ans)-set(qs):raise ValueError('Unmatched answers/questions')
 return {'path':rel,'text':text,'identity':ident,'variant':str(field(text,'卷型')),'questions':qs,'answers':ans,'materials':mats,'mode':mode,'question_spans':spans,'answer_heading':ah[0][0] if ah else None,'missing':[n for n in qs if empty(ans.get(n,''))]}
def read_paper(p):return parse_text(p.read_text(encoding='utf-8'),p.relative_to(ROOT).as_posix())
def suitable_answer(a):
 return not empty(a) and len(plain(a))>=50 and '\ufffd' not in a and not re.search(r'<img|!\[|data:|javascript:',a,re.I)
def match(target,n,donors):
 a=key(target['questions'][n]);rank=[]
 if len(a)<18:return None,'short_stem'
 targetmat=plain(target['materials'][n])
 for d,k in donors:
  if d['path']==target['path']:continue
  b=key(d['questions'][k]);sm=SequenceMatcher(None,a,b,autojunk=False);similarity=sm.ratio()
  if similarity<.93 or sm.find_longest_match().size<18:continue
  g=grams(d['materials'][k])
  if len(g)<35:continue
  overlap=sum(x in targetmat for x in g)/len(g)
  if overlap<.90:continue
  ts=SCORE.findall(target['questions'][n]);ds=SCORE.findall(d['questions'][k])
  if ts and ds and ts!=ds:continue
  tw=re.findall(r'(\d+)\s*(?:[-—～~]\s*\d+\s*)?字',target['questions'][n]);dw=re.findall(r'(\d+)\s*(?:[-—～~]\s*\d+\s*)?字',d['questions'][k])
  if tw and dw and tw!=dw:continue
  rank.append((similarity,overlap,d['path'],k,d))
 if not rank:return None,'no_matching_answer_with_material_evidence'
 rank.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True);best=rank[0]
 if any(r[0]>=best[0]-.01 and plain(r[4]['answers'][r[3]])!=plain(best[4]['answers'][best[3]]) for r in rank[1:]):return None,'conflicting_supported_answers'
 s,o,path,k,d=best
 return {'number':n,'kind':'repository_same_question','donor_path':path,'donor_number':k,'answer':d['answers'][k],'stem_similarity':round(s,6),'material_coverage':round(o,6),'donor_sha256':digest(d['text']),'donor_answer_sha256':digest(d['answers'][k]),'donor_question_sha256':digest(d['questions'][k]),'target_question_sha256':digest(target['questions'][n]),'source_url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+quote(path,safe='/')+'#第-'+str(k)+'-题','target_variant':target['variant'],'source_variant':d['variant']},None

def discover():
 papers=[];unparsed=[]
 for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md'),*ROOT.glob('市考/*/*/申论*.md')]):
  try:
   r=read_paper(p)
   if r:papers.append(r)
  except Exception as e:unparsed.append({'path':p.relative_to(ROOT).as_posix(),'reason':str(e)})
 donors=collections.defaultdict(list)
 for d in papers:
  for n,a in d['answers'].items():
   if suitable_answer(a):donors[d['identity']].append((d,n))
 plans=[];unresolved=[]
 for t in papers:
  adds=[]
  for n in t['missing']:
   m,reason=match(t,n,donors[t['identity']])
   if m:adds.append(m)
   else:unresolved.append({'path':t['path'],'number':n,'reason':reason,'stem':t['questions'][n][:240]})
  if adds:plans.append((t,adds))
 return papers,unparsed,plans,unresolved

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inspect',action='store_true');ap.parse_args()
 papers,unparsed,plans,unresolved=discover()
 print('SUMMARY',json.dumps({'parsed':len(papers),'unparsed':len(unparsed),'papers_with_missing_answers':sum(bool(p['missing']) for p in papers),'missing_answers':sum(len(p['missing']) for p in papers),'internal_candidate_papers':len(plans),'internal_candidate_answers':sum(len(a) for _,a in plans)},ensure_ascii=False),flush=True)
 for t,a in plans:print('CANDIDATE',json.dumps({'path':t['path'],'mode':t['mode'],'additions':[{'n':x['number'],'donor':x['donor_path'],'dn':x['donor_number'],'stem':x['stem_similarity'],'material':x['material_coverage']} for x in a]},ensure_ascii=False),flush=True)
 print('UNPARSED',json.dumps(unparsed,ensure_ascii=False),flush=True)
 print('PRIORITY_MISSING',json.dumps([x for x in unresolved if x['path'].startswith(('国考/','省考/江苏/','省考/浙江/'))],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
