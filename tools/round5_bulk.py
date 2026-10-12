#!/usr/bin/env python3
"""Evidence-based bulk matching of the user's existing corpus. No generated answers."""
from __future__ import annotations
import argparse,collections,json,re,unicodedata
from difflib import SequenceMatcher
from pathlib import Path
import round4_gap_repair as g
from round4_delivery import is_missing
ROOT=g.ROOT
BASE='69929cdd0b198ad498832552d1249f36f1cff715'
FOLD=str.maketrans({'⺠':'民','⻔':'门','⻛':'风','⻓':'长','⻅':'见','⻆':'角','⻋':'车','⻢':'马','⻜':'飞','⻝':'食','⻟':'食','⻤':'鬼','⻥':'鱼','⻩':'黄','⻬':'齐','⻰':'龙','⻳':'龟','⻨':'麦','⻚':'页','⻙':'韦','⻘':'青','⻄':'西','⻣':'骨','⻧':'卤','⻦':'鸟'})
CN={c:i for i,c in enumerate('一二三四五六七八九十',1)}
RECEIPT='ROUND5-ANSWERS-20261012.jsonl'

def norm(t):return ''.join(c for c in unicodedata.normalize('NFKC',t).translate(FOLD) if c.isalnum())
def qkey(q):
 q=g.clean_q(q).split('要求')[0]
 q=re.sub(r'^(?:问题[一二三四五六七八九十\d]+[：:]|题目[一二三四五六七八九十\d]+[：:]|第[一二三四五六七八九十\d]+题[：:]?|[（(]?[一二三四五六七八九十\d]+[）)、.．])\s*','',q)
 q=g.SCORE.sub('',q)
 q=re.sub(r'[“"「]?\s*(?:给定)?(?:资料|材料)\s*[一二三四五六七八九十\d\-—～~、至和与及]*\s*[”"」]?','材料',q)
 return norm(q)
def shingles(t,n=12):
 t=norm(t);return {t[i:i+n] for i in range(0,max(0,len(t)-n+1),4)}
def parse(text,rel):
 try:return g.parse_text(text,rel)
 except ValueError as original:
  ident=(str(g.field(text,'地区')),str(g.field(text,'年份')))
  if g.field(text,'科目')!='申论' or not all(ident):raise original
  ah=list(g.AH.finditer(text))
  if len(ah)>1:raise original
  front=text[:ah[0].start()] if ah else text;answers={}
  if ah:
   for m in g.DETAIL.finditer(text[ah[0].end():]):
    n=int(m[2])
    if n in answers:raise ValueError('Duplicate answer id')
    answers[n]=m[3].strip()
   if not answers:raise original
  elif '<details>' in text:raise original
  elif re.search(r'(?m)^##\s+参考答案收录情况\s*$',front):
   mark=re.search(r'(?m)^##\s+参考答案收录情况\s*$',front)
   if not re.fullmatch(r'\s*4道题的参考答案均尚未核实取得。本文件只收录题面，不生成或冒充发布方答案。\s*',front[mark.end():]):raise original
   front=front[:mark.start()]
  qh=list(g.QH.finditer(front));qs={};spans={};mats={}
  if qh:
   for j,h in enumerate(qh):
    n=int(h[1]);end=qh[j+1].start() if j+1<len(qh) else len(front)
    if n in qs:raise ValueError('Duplicate question id')
    raw=front[h.end():end];qs[n]=g.clean_q(raw);spans[n]=h.start();mats[n]=front[:qh[0].start()]
   mode='headings' if not ah else 'details'
  else:
   markers=list(re.finditer(r'(?:作答要求|答题要求|题目及要求|题目和要求|申论要求)',front))
   start=markers[-1].end() if markers else max(0,len(front)-7000)
   region=front[start:]
   pat=re.compile(r'(?:问题|题目)([一二三四五六七八九十\d]+)[：:、.．]|第([一二三四五六七八九十\d]+)题[：:、.．]|(?m:^[ \t\u3000]*)(?:[（(]([一二三四五六七八九十]+)[）)]|([一二三四五六七八九十\d]+)[、．.])')
   hh=[]
   for m in pat.finditer(region):
    s=next(x for x in m.groups() if x);n=int(s) if s.isdigit() else CN.get(s)
    end=region.find('\n\n',m.end());line=region[m.end():end if end>=0 else None]
    if n and 1<=n<=6 and len(norm(line))>=12:hh.append((start+m.start(),start+m.end(),n))
   if [n for _,_,n in hh]!=list(range(1,len(hh)+1)) or not 2<=len(hh)<=6:raise ValueError('No unambiguous explicit task sequence')
   for i,(at,end,n) in enumerate(hh):
    stop=hh[i+1][0] if i+1<len(hh) else len(front);q=front[at:stop].strip()
    if '要求' not in q or not re.search(r'\d+[^\n]{0,30}字',q):raise ValueError('Missing explicit requirements')
    qs[n]=q;spans[n]=at;mats[n]=front[:hh[0][0]]
   mode='unstructured'
  if not qs or set(answers)-set(qs):raise ValueError('Unmatched answer ids')
  return {'path':rel,'text':text,'identity':ident,'variant':str(g.field(text,'卷型')),'questions':qs,'answers':answers,'materials':mats,'mode':mode,'question_spans':spans,'answer_heading':ah[0][0] if ah else None,'missing':[n for n in qs if is_missing(answers.get(n,''))],'parser':'explicit_label_fallback'}

def scan():
 papers=[];bad=[]
 for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]):
  try:
   t=parse(p.read_text(encoding='utf-8'),p.relative_to(ROOT).as_posix())
   if t:t['missing']=[n for n in t['questions'] if is_missing(t['answers'].get(n,''))];papers.append(t)
  except Exception as e:bad.append({'path':p.relative_to(ROOT).as_posix(),'reason':str(e)})
 byyear=collections.defaultdict(list);bykey=collections.defaultdict(list);elig=collections.Counter()
 for d in papers:
  for n,a in d['answers'].items():
   if is_missing(a):continue
   if not g.suitable_answer(a):elig['ineligible_answer']+=1;continue
   k=qkey(d['questions'][n]);row=(k,d,n);byyear[d['identity'][1]].append(row);bykey[(d['identity'][1],k)].append(row)
 plans=[];unresolved=[];counts=collections.Counter()
 for t in papers:
  tm={n:norm(v) for n,v in t['materials'].items()};adds=[]
  for n in t['missing']:
   k=qkey(t['questions'][n]);pool=bykey.get((t['identity'][1],k),[])
   pool=pool+[(kk,d,dn) for kk,d,dn in byyear[t['identity'][1]] if d['identity'][0]==t['identity'][0] and kk!=k]
   rank=[];why='no_same_question_source'
   for kk,d,dn in pool:
    if d['path']==t['path']:continue
    sim=1. if k==kk else SequenceMatcher(None,k,kk,autojunk=False).ratio()
    if len(k)<18 or sim<.97:continue
    gg=shingles(d['materials'][dn]);coverage=sum(x in tm[n] for x in gg)/max(1,len(gg))
    joint=d['identity'][0]!=t['identity'][0]
    if len(gg)<35 or coverage<(.985 if joint else .95):why='material_not_sufficient';continue
    ts=g.SCORE.findall(t['questions'][n]);ds=g.SCORE.findall(d['questions'][dn])
    if ts and ds and ts!=ds:why='different_scoring';continue
    tw=re.findall(r'(\d+)\s*(?:[-—～~]\s*\d+\s*)?字',t['questions'][n]);dw=re.findall(r'(\d+)\s*(?:[-—～~]\s*\d+\s*)?字',d['questions'][dn])
    if tw and dw and tw!=dw:why='different_word_limit';continue
    rank.append((sim,coverage,d,dn,joint))
   if rank:
    rank.sort(key=lambda x:(x[0],x[1],x[2]['path']),reverse=True);sim,cov,d,dn,joint=rank[0]
    if any(norm(r[2]['answers'][r[3]])!=norm(d['answers'][dn]) for r in rank[1:] if r[0]>=sim-.005):why='conflicting_existing_answers'
    else:
     a={'number':n,'donor_path':d['path'],'donor_number':dn,'source_url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+__import__('urllib.parse',fromlist=['quote']).quote(d['path'],safe='/')+'#第-'+str(dn)+'-题','source_variant':d['variant'],'answer':d['answers'][dn],'kind':'repository_joint_exam_question' if joint else 'repository_same_question','stem_similarity':sim,'material_coverage':cov,'donor_sha256':g.digest(d['text']),'donor_question_sha256':g.digest(d['questions'][dn]),'donor_answer_sha256':g.digest(d['answers'][dn]),'target_question_sha256':g.digest(t['questions'][n])}
     adds.append(a);counts['joint' if joint else 'same_region']+=1;continue
   counts[why]+=1;unresolved.append({'path':t['path'],'number':n,'reason':why,'stem':t['questions'][n].split('要求')[0][:180]})
  if adds:plans.append((t,adds))
 return papers,bad,plans,unresolved,counts

def main():
 p,b,plans,u,c=scan()
 print('R5_BULK',json.dumps({'parsed':len(p),'unparsed':len(b),'missing_before':sum(len(t['missing']) for t in p),'candidate_papers':len(plans),'candidate_answers':sum(len(a) for _,a in plans),'diagnosis':c},ensure_ascii=False),flush=True)
 print('R5_PLANS',json.dumps([{'path':t['path'],'numbers':[x['number'] for x in a],'sources':[x['donor_path'] for x in a]} for t,a in plans],ensure_ascii=False),flush=True)
 print('R5_UNPARSED',json.dumps(b,ensure_ascii=False),flush=True)
 print('R5_PRIORITY',json.dumps([x for x in u if x['path'].startswith(('国考/','省考/江苏/','省考/浙江/'))],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
