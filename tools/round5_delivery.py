#!/usr/bin/env python3
"""Apply only validated source-backed answer additions. No generated answers."""
import argparse,json,re
from pathlib import Path
from urllib.parse import quote
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing,operations
ROOT=b.ROOT
ANCHOR=re.compile(r'\n<!-- R5 question anchor (\d+) -->\n## 第 \1 题\n\n')
PENDING='未收录同卷同题的完整参考答案；不以自动生成内容冒充来源答案。'

def body_text(t):
 m=g.AH.search(t);front=t[:m.start()] if m else t
 if not front.startswith('---'):raise ValueError('Missing metadata')
 return ANCHOR.sub('',front.split('---',2)[2]).rstrip()

def render(paper,adds):
 old=paper['text'];new=old;byid={x['number']:x for x in adds}
 if len(byid)!=len(adds):raise ValueError('Duplicate addition')
 for n,a in byid.items():
  if n not in paper['questions'] or not is_missing(paper['answers'].get(n,'')):raise ValueError('Refuse existing answer overwrite')
  if not g.suitable_answer(a['answer']) or a['target_question_sha256']!=g.digest(paper['questions'][n]):raise ValueError('Unsafe answer or stale target')
 def answer(n):
  a=byid[n]
  note='> 来源说明：第五轮按同年同题及给定材料匹配；字形等价处理仅用于比对，不改写原始题面。此为来源参考答案，不是官方标准答案。'
  if a['kind']=='repository_joint_exam_question':note+=' 本题采用跨省联考共用题来源，不将来源整卷视为本卷。'
  elif a['kind']=='user_owned_transcript':note+=' 完整答案取自你已保存的原始资料转录，源文件与行号另列。'
  if a.get('source_variant')!=paper['variant']:note+=' 原记录卷型为“'+a.get('source_variant','未明确')+'”，仅依据同题证据对应。'
  return a['answer']+'\n\n'+note+'\n\n[本题来源记录]('+a['source_url']+')'
 if paper['answer_heading']:
  def sub(m):
   n=int(m[2]);return m[1]+'\n\n'+answer(n)+'\n\n'+m[4] if n in byid else m[0]
  new=g.DETAIL.sub(sub,new)
  if any(n not in paper['answers'] for n in byid):raise ValueError('Missing answer block id')
 else:
  if paper['mode']=='unstructured':
   for n,at in sorted(paper['question_spans'].items(),key=lambda x:x[1],reverse=True):new=new[:at]+f'\n<!-- R5 question anchor {n} -->\n## 第 {n} 题\n\n'+new[at:]
  chunks=['## 答案与解析','> 参考答案逐题注明来源；没有可靠来源的题继续明确留缺。']
  for n in paper['questions']:chunks.append(f'<details>\n<summary>第 {n} 题</summary>\n\n'+(answer(n) if n in byid else PENDING)+'\n\n</details>')
  new=new.rstrip()+'\n\n'+'\n\n'.join(chunks)+'\n'
 complete=sorted(n for n in paper['questions'] if n in byid or not is_missing(paper['answers'].get(n,'')))
 new=g.set_fields(new,{'已收录参考答案题号':complete,'缺参考答案题号':sorted(set(paper['questions'])-set(complete)),'第五轮修复凭据':'reports/'+b.RECEIPT},'2026-10-12第五轮：按同题来源补入缺失参考答案；题面保持，不代表官方原件逐字认证')
 result=b.parse(new,paper['path'])
 if body_text(old)!=body_text(new):raise ValueError('Original material/task body changed')
 if set(result['questions'])!=set(paper['questions']):raise ValueError('Task id set changed')
 for n,a in paper['answers'].items():
  if not is_missing(a) and result['answers'].get(n)!=a:raise ValueError('Existing real answer altered')
 rr={'path':paper['path'],'before_sha256':g.digest(old),'after_sha256':g.digest(new),'kind':'answer_gap_fill','old_mode':paper['mode'],'body_sha256':g.digest(body_text(old)),'question_count':len(paper['questions']),'added_answers':[{**{k:v for k,v in a.items() if k!='answer'},'delivered_answer_sha256':g.digest(result['answers'][a['number']])} for a in adds],'preserved_answers':{str(n):g.digest(a) for n,a in paper['answers'].items() if not is_missing(a)},'remaining_answer_ids':result['missing'],'operations':operations(old,new)}
 return new,rr

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 papers,bad,plans,unresolved,diagnosis=b.scan();ready=[];errors=[]
 for t,a in plans:
  try:new,r=render(t,a);ready.append((t,new,r))
  except Exception as e:errors.append({'path':t['path'],'error':str(e)})
 summary={'baseline':b.BASE,'parsed_essays':len(papers),'unparsed_essays':len(bad),'recognized_missing_slots_before':sum(len(t['missing']) for t in papers),'modified_papers':len(ready),'answers_added':sum(len(r['added_answers']) for _,_,r in ready),'rejected':errors,'apply':args.apply,'boundary':'Counts are recognized document answer positions, not unique questions or proof of complete papers.'}
 print('R5_DELIVERY',json.dumps(summary,ensure_ascii=False),flush=True)
 if args.apply:
  rp=ROOT/'reports'/b.RECEIPT
  if rp.exists() or errors or not ready:raise ValueError('Already applied or validation failure')
  for t,new,r in ready:
   p=ROOT/t['path']
   if g.digest(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent change')
   p.write_text(new,encoding='utf-8',newline='\n')
   if g.digest(p.read_bytes())!=r['after_sha256']:raise ValueError('Write verification failed')
  rp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in ready),encoding='utf-8')
  summary['remaining_recognized_slots']=summary['recognized_missing_slots_before']-summary['answers_added']
  (ROOT/'reports/REPAIR-SUMMARY-20261012-R5.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
  (ROOT/'reports/ROUND5-UNRESOLVED-20261012.json').write_text(json.dumps({'parsed_missing':unresolved,'unparsed':bad},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
