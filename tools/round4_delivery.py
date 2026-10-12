#!/usr/bin/env python3
"""Fill proved answer gaps using the existing corpus; never generate answers."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from difflib import SequenceMatcher
import round4_gap_repair as g
ROOT=g.ROOT
RECEIPT='ROUND4-ANSWERS-20261012.jsonl'
PENDING='未收录同卷同题的完整参考答案；不以自动生成内容冒充来源答案。'
ANCHOR=re.compile(r'\n<!-- R4 question anchor (\d+) -->\n## 第 \1 题\n\n')

def is_missing(a):
 s=re.sub(r'^[\s>*]+','',a)
 return g.empty(a) or bool(re.match(r'^(?:本题)?参考答案(?:尚未|未|暂缺)',s))
def add_proved_answers(paper,adds):
 old=paper['text'];new=old;byid={a['number']:a for a in adds}
 if len(byid)!=len(adds):raise ValueError('Duplicate added answer')
 for n,a in byid.items():
  if n not in paper['questions'] or not is_missing(paper['answers'].get(n,'')):raise ValueError('Not a proved empty answer')
  if not g.suitable_answer(a['answer']):raise ValueError('Unsafe/incomplete donor answer')
  if a['target_question_sha256']!=g.digest(paper['questions'][n]):raise ValueError('Target changed')
 def body(n):
  a=byid[n]
  if a['kind']=='repository_joint_exam_question':note='> 来源说明：同年联考共用题参考答案。题干归一化完全相同，相关材料逐段核对；仅证明本题匹配，不把来源地区的整卷当成本卷。'
  else:note='> 来源说明：从本库固定版本的同年、同地区同题记录补入，按题干、相关材料及作答限制匹配，不按旧题号直接搬运。'
  if a.get('source_variant')!=paper['variant']:note+=' 原记录卷型标记为“'+a.get('source_variant','未标')+'”，并非本卷的独立官方答案。'
  return a['answer']+'\n\n'+note+'\n\n[本题既有来源记录]('+a['source_url']+')'
 if paper['answer_heading']:
  def sub(m):
   n=int(m[2]);return m[1]+'\n\n'+body(n)+'\n\n'+m[4] if n in byid else m[0]
  new=g.DETAIL.sub(sub,new)
  if any(n not in paper['answers'] for n in byid):raise ValueError('Unmatched existing answer block')
 else:
  if paper['mode']=='unstructured':
   for n,at in sorted(paper['question_spans'].items(),key=lambda v:v[1],reverse=True):new=new[:at]+f'\n<!-- R4 question anchor {n} -->\n## 第 {n} 题\n\n'+new[at:]
  sections=['## 答案与解析','> 本轮只补已有同题来源答案。题面、材料和原作答要求保持原文；尚未取得的答案逐题保留缺项。']
  for n in paper['questions']:sections.append(f'<details>\n<summary>第 {n} 题</summary>\n\n'+(body(n) if n in byid else PENDING)+'\n\n</details>')
  new=new.rstrip()+'\n\n'+'\n\n'.join(sections)+'\n'
 complete=sorted(n for n in paper['questions'] if n in byid or not is_missing(paper['answers'].get(n,'')))
 new=g.set_fields(new,{'已收录参考答案题号':complete,'缺参考答案题号':sorted(set(paper['questions'])-set(complete)),'第四轮修复凭据':'reports/'+RECEIPT},'2026-10-12第四轮：按同年同题及材料证据补入既有参考答案；题面保持，不代表官方答案认证')
 return new

def nonmetadata(t):
 if not t.startswith('---'):raise ValueError('Missing frontmatter')
 return t.split('---',2)[2]
def body_without_inserted_headers(t,original_mode):
 m=g.AH.search(t);front=t[:m.start()] if m else t;b=nonmetadata(front)
 if original_mode=='unstructured':b=ANCHOR.sub('',b)
 return b.rstrip()
def operations(old,new):
 a=old.splitlines(keepends=True);b=new.splitlines(keepends=True);ai=[0];bi=[0]
 for s in a:ai.append(ai[-1]+len(s))
 for s in b:bi.append(bi[-1]+len(s))
 return [{'old_start':ai[i],'old_end':ai[j],'new_start':bi[k],'new_end':bi[l],'old':old[ai[i]:ai[j]],'new':new[bi[k]:bi[l]]} for kind,i,j,k,l in SequenceMatcher(None,a,b,autojunk=False).get_opcodes() if kind!='equal']
def receipt(old,new,paper,adds):
 result=g.parse_text(new,paper['path'])
 if set(result['questions'])!=set(paper['questions']):raise ValueError('Question set changed')
 if body_without_inserted_headers(new,paper['mode'])!=body_without_inserted_headers(old,paper['mode']):raise ValueError('Original material/question content changed')
 for n,a in paper['answers'].items():
  if not is_missing(a) and result['answers'].get(n)!=a:raise ValueError('Existing answer was altered')
 return {'path':paper['path'],'kind':'answer_gap_fill','before_sha256':g.digest(old),'after_sha256':g.digest(new),'old_mode':paper['mode'],'question_count':len(paper['questions']),'body_sha256':g.digest(body_without_inserted_headers(old,paper['mode'])),'added_answers':[{**{k:v for k,v in x.items() if k!='answer'},'delivered_answer_sha256':g.digest(result['answers'][x['number']])} for x in adds],'preserved_answers':{str(n):g.digest(a) for n,a in paper['answers'].items() if not is_missing(a)},'remaining_answer_ids':[n for n in result['questions'] if is_missing(result['answers'].get(n,''))],'operations':operations(old,new)}

def scan():
 papers=[];unparsed=[]
 for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md'),*ROOT.glob('市考/*/*/申论*.md')]):
  try:
   d=g.read_paper(p)
   if d:d['missing']=[n for n in d['questions'] if is_missing(d['answers'].get(n,''))];papers.append(d)
  except Exception as e:unparsed.append({'path':p.relative_to(ROOT).as_posix(),'reason':str(e)})
 donors={};joint={}
 for d in papers:
  for n,a in d['answers'].items():
   if not is_missing(a) and g.suitable_answer(a):
    donors.setdefault(d['identity'],[]).append((d,n));joint.setdefault((d['identity'][1],g.key(d['questions'][n])),[]).append((d,n))
 plans=[];unresolved=[]
 for t in papers:
  adds=[]
  for n in t['missing']:
   a,why=g.match(t,n,donors.get(t['identity'],[]))
   if not a and why!='conflicting_supported_answers':
    same=[(d,k) for d,k in joint.get((t['identity'][1],g.key(t['questions'][n])),[]) if d['identity'][0]!=t['identity'][0]]
    a,why=g.match(t,n,same)
    if a:
     if a['stem_similarity']!=1 or a['material_coverage']<.98:a=None;why='joint_exam_material_proof_insufficient'
     else:a['kind']='repository_joint_exam_question'
   if a:adds.append(a)
   else:unresolved.append({'path':t['path'],'number':n,'reason':why,'stem':t['questions'][n].split('要求')[0][:220]})
  if adds:plans.append((t,adds))
 return papers,unparsed,plans,unresolved

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args();rp=ROOT/'reports'/RECEIPT
 if rp.exists():raise ValueError('Round4 already applied; do not overwrite receipts')
 papers,unparsed,plans,unresolved=scan();ready=[];rejected=[]
 for t,adds in plans:
  try:new=add_proved_answers(t,adds);r=receipt(t['text'],new,t,adds);ready.append((t,new,r))
  except Exception as e:
   rejected.append({'path':t['path'],'error':str(e)})
   if 'content changed' in str(e):
    a=body_without_inserted_headers(t['text'],t['mode']);b=body_without_inserted_headers(new,t['mode']);i=next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)))
    print('BODY_DIFF',t['path'],i,repr(a[max(0,i-25):i+75]),repr(b[max(0,i-25):i+75]),flush=True)
 summary={'baseline':g.BASE,'parsed_essays':len(papers),'unparsed_essays':len(unparsed),'missing_answer_slots_before':sum(len(t['missing']) for t in papers),'candidate_papers':len(plans),'modified_papers':len(ready),'answers_added':sum(len(r['added_answers']) for _,_,r in ready),'joint_exam_answers':sum(a['kind']=='repository_joint_exam_question' for _,_,r in ready for a in r['added_answers']),'rejected':rejected,'apply':args.apply}
 print('ROUND4_SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
 for t,_,r in ready:print('ROUND4_READY',json.dumps({'path':t['path'],'added':[a['number'] for a in r['added_answers']],'joint':[a['number'] for a in r['added_answers'] if a['kind']=='repository_joint_exam_question']},ensure_ascii=False),flush=True)
 print('ROUND4_PRIORITY_REMAINING',json.dumps([u for u in unresolved if u['path'].startswith(('国考/','省考/浙江/','省考/江苏/'))],ensure_ascii=False),flush=True)
 if args.apply:
  if rejected:raise ValueError('Candidate validation failed; nothing will be written')
  if not ready:raise ValueError('No validated answers')
  for t,new,r in ready:
   path=ROOT/t['path']
   if g.digest(path.read_text())!=r['before_sha256']:raise ValueError('Concurrent target mutation')
   path.write_text(new,encoding='utf-8',newline='\n')
   if g.digest(path.read_bytes())!=r['after_sha256']:raise ValueError('Read-back hash mismatch')
  rp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in ready),encoding='utf-8')
  (ROOT/'reports/ROUND4-UNRESOLVED-ANSWERS-20261012.json').write_text(json.dumps({'parsed_missing':unresolved,'unparsed':unparsed,'boundary':'Unparsed documents are not declared complete; counts cover recognized source answer slots only.'},ensure_ascii=False,indent=2)+'\n')
  (ROOT/'reports/REPAIR-SUMMARY-20261012-R4.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
