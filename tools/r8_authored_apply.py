#!/usr/bin/env python3
"""Add explicitly AI-original study answers; keep all exam text and existing references."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import operations,is_missing
import r7_delivery as r7
from r7_reference_audit import assess
ROOT=g.ROOT
DATA=ROOT/'tools/data/r8-authored-references.json'
RECEIPT='ROUND8-AUTHORED-20261013.jsonl'
SECTION=re.compile(r'(?m)^## 参考答案收录情况\n\n4道题的参考答案均尚未核实取得。本文件只收录题面，不生成或冒充发布方答案。\s*

def inner(item):
 typ=item['type']
 heading='原创示范范文' if typ=='作文范文' else '原创参考作答'
 return ('**'+heading+'（依据本卷给定资料编写；非机构原文、非真实考场分数认证）**\n\n'
   '<!-- R8 authored answer -->\n'+item['text'].strip()+'\n<!-- /R8 authored answer -->\n\n'
   '> 文字来源说明：本答案为AI原创学习示范，按该试卷题干与给定资料组织，不冒充互联网上其他机构的原文。'
   '\n\n[同题公开参考页面（对照阅读；不是本段文字的作者）]('+item['public_reference']+')')

def apply_text(old,rel,items):
 if len({x['number'] for x in items})!=len(items):raise ValueError('Duplicate answer target')
 paper=r7.parse(old,rel)
 assert paper is not None
 if any(x['number'] not in paper['questions'] for x in items):raise ValueError('Wrong question id')
 if any(x['path']!=rel for x in items):raise ValueError('Unrelated question path')
 for item in items:
  n=item['number'];state=assess(paper['questions'][n],paper['answers'].get(n,''))
  if item['mode']=='fill':
   if not is_missing(paper['answers'].get(n,'')):raise ValueError('Refuse to overwrite existing answer '+rel+':'+str(n))
  elif item['mode']=='alternative':
   if is_missing(paper['answers'].get(n,'')) or state['status']!='已收录':
    raise ValueError('Alternative only after readable pre-existing answer')
  else:raise ValueError('Unexpected authored mode')
  length=len(re.sub(r'\s','',item['text']))
  if item['type']=='作文范文':
   if not 950<=length<=1230:raise ValueError('Essay draft length outside permitted range')
  elif not 150<=length<=580:raise ValueError('Short answer length outside supported range')
  if (not item['public_reference'].startswith('https://') or
      '<script' in item['text'] or '![' in item['text'] or '\ufffd' in item['text']):
   raise ValueError('Invalid authored text')
 new=old;byid={x['number']:x for x in items}
 if paper['answer_heading']:
  def sub(m):
   n=int(m[2])
   if n not in byid:return m[0]
   item=byid[n];original=m[3].strip();ans=inner(item)
   if item['mode']=='alternative':
    ans=original+'\n\n---\n\n**第二参考版本（原创）**\n\n'+ans
   return m[1]+'\n\n'+ans+'\n\n'+m[4]
  new=g.DETAIL.sub(sub,new)
 else:
  # Jiangsu 2026B previously had a truthful old 'no answer' note, not a
  # source question. Replace exactly that note with real answer blocks.
  if not SECTION.search(new):raise ValueError('No recognized old no-answer section')
  all_numbers=set(paper['questions'])
  if set(byid)!=all_numbers:raise ValueError('Require full Jiangsu 2026B coverage for first answer section')
  blocks=['## 答案与解析','> 以下为根据本卷材料原创的示范参考作答及作文，不是转载机构全文，也没有真实阅卷分数。']
  for n in sorted(paper['questions']):
   blocks.append('<a id="r7-reference-'+str(n)+'"></a>\n<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+inner(byid[n])+'\n\n</details>')
  new=SECTION.sub('\n\n'.join(blocks),new)
 new=g.set_fields(new,{'已收录参考答案题号':sorted(paper['questions']),'缺参考答案题号':[],
  '第八轮原创示范凭据':'reports/'+RECEIPT},
  '2026-10-13第八轮：原创参考作答与范文仅供练习；外部同题资料仅用于对照，不冒充来源原文')
 # Rebuild the previously created reading guide as an actual live index.
 fresh=r7.parse(new,rel)
 if set(fresh['questions'])!=set(paper['questions']):raise ValueError('Original task set changed')
 for n,q in paper['questions'].items():
  if b.qkey(q)!=b.qkey(fresh['questions'][n]):raise ValueError('Task stem changed')
 for n,ans in paper['answers'].items():
  if not is_missing(ans):
   current=fresh['answers'][n]
   if n not in byid and current!=ans:raise ValueError('Old answer unexpectedly changed')
   if n in byid and not current.startswith(ans):raise ValueError('Prior full answer not preserved')
  if n in byid:
   item=byid[n]
   if item['text'] not in fresh['answers'][n]:raise ValueError('Authored content absent from destination')
 old_guide=r7.GUIDE.search(new)
 if not old_guide:raise ValueError('R7 guide must already exist')
 new=new[:old_guide.start()]+r7.reading_guide(fresh)+new[old_guide.end():]
 final=r7.parse(new,rel)
 if set(final['questions'])!=set(paper['questions']):raise ValueError('Guide damaged task parsing')
 receipt={'path':rel,'before_sha256':g.digest(old),'after_sha256':g.digest(new),
  'old_question_keys':{str(n):b.qkey(q) for n,q in paper['questions'].items()},
  'preserved_nonempty_answers':{str(n):g.digest(a) for n,a in paper['answers'].items() if not is_missing(a)},
  'added_answers':[{'number':x['number'],'mode':x['mode'],'type':x['type'],'original_sha256':g.digest(x['text']),
   'original_characters':len(re.sub(r'\s','',x['text'])),'source_class':'AI原创示范，外部页面仅对照',
   'comparison_url':x['public_reference'],'delivered_answer_sha256':g.digest(final['answers'][x['number']])} for x in items],
  'operations':operations(old,new)}
 return new,receipt

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 data=json.loads(DATA.read_text(encoding='utf-8'));items=data['items']
 plans={}
 for x in items:plans.setdefault(x['path'],[]).append(x)
 if len(plans)!=4 or len(items)!=9:raise ValueError('Unexpected authored source inventory')
 result=[];errors=[]
 for rel,aa in sorted(plans.items()):
  try:
   p=ROOT/rel
   old=p.read_text(encoding='utf-8');new,rec=apply_text(old,rel,aa)
   result.append((p,new,rec))
  except Exception as e:errors.append({'path':rel,'error':str(e)})
 summary={'papers':len(result),'authored_answer_versions':sum(len(r['added_answers']) for _,_,r in result),
  'newly_filled':sum(a['mode']=='fill' for _,_,r in result for a in r['added_answers']),
  'new_full_essay_versions':sum(a['type']=='作文范文' for _,_,r in result for a in r['added_answers']),
  'errors':errors,'apply':args.apply}
 print('R8_AUTHORED_PREVIEW',json.dumps(summary,ensure_ascii=False),flush=True)
 if errors or len(result)!=4:raise ValueError('Authored delivery guard refused incomplete batch')
 if not args.apply:return
 receipt=ROOT/'reports'/RECEIPT
 if receipt.exists():raise ValueError('Already delivered')
 for p,new,r in result:
  if g.digest(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent source modification')
 for p,new,r in result:
  p.write_text(new,encoding='utf-8',newline='\n')
  if g.digest(p.read_bytes())!=r['after_sha256']:raise ValueError('Authored output hash mismatch')
 receipt.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in result),encoding='utf-8')
 (ROOT/'reports/REPAIR-SUMMARY-20261013-R8.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
)

def inner(item):
 typ=item['type']
 heading='原创示范范文' if typ=='作文范文' else '原创参考作答'
 return ('**'+heading+'（依据本卷给定资料编写；非机构原文、非真实考场分数认证）**\n\n'
   '<!-- R8 authored answer -->\n'+item['text'].strip()+'\n<!-- /R8 authored answer -->\n\n'
   '> 文字来源说明：本答案为AI原创学习示范，按该试卷题干与给定资料组织，不冒充互联网上其他机构的原文。'
   '\n\n[同题公开参考页面（对照阅读；不是本段文字的作者）]('+item['public_reference']+')')

def apply_text(old,rel,items):
 if len({x['number'] for x in items})!=len(items):raise ValueError('Duplicate answer target')
 paper=r7.parse(old,rel)
 assert paper is not None
 if any(x['number'] not in paper['questions'] for x in items):raise ValueError('Wrong question id')
 if any(x['path']!=rel for x in items):raise ValueError('Unrelated question path')
 for item in items:
  n=item['number'];state=assess(paper['questions'][n],paper['answers'].get(n,''))
  if item['mode']=='fill':
   if not is_missing(paper['answers'].get(n,'')):raise ValueError('Refuse to overwrite existing answer '+rel+':'+str(n))
  elif item['mode']=='alternative':
   if is_missing(paper['answers'].get(n,'')) or state['status']!='已收录':
    raise ValueError('Alternative only after readable pre-existing answer')
  else:raise ValueError('Unexpected authored mode')
  length=len(re.sub(r'\s','',item['text']))
  if item['type']=='作文范文':
   if not 950<=length<=1230:raise ValueError('Essay draft length outside permitted range')
  elif not 150<=length<=580:raise ValueError('Short answer length outside supported range')
  if (not item['public_reference'].startswith('https://') or
      '<script' in item['text'] or '![' in item['text'] or '\ufffd' in item['text']):
   raise ValueError('Invalid authored text')
 new=old;byid={x['number']:x for x in items}
 if paper['answer_heading']:
  def sub(m):
   n=int(m[2])
   if n not in byid:return m[0]
   item=byid[n];original=m[3].strip();ans=inner(item)
   if item['mode']=='alternative':
    ans=original+'\n\n---\n\n**第二参考版本（原创）**\n\n'+ans
   return m[1]+'\n\n'+ans+'\n\n'+m[4]
  new=g.DETAIL.sub(sub,new)
 else:
  # Jiangsu 2026B previously had a truthful old 'no answer' note, not a
  # source question. Replace exactly that note with real answer blocks.
  if not SECTION.search(new):raise ValueError('No recognized old no-answer section')
  all_numbers=set(paper['questions'])
  if set(byid)!=all_numbers:raise ValueError('Require full Jiangsu 2026B coverage for first answer section')
  blocks=['## 答案与解析','> 以下为根据本卷材料原创的示范参考作答及作文，不是转载机构全文，也没有真实阅卷分数。']
  for n in sorted(paper['questions']):
   blocks.append('<a id="r7-reference-'+str(n)+'"></a>\n<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+inner(byid[n])+'\n\n</details>')
  new=SECTION.sub('\n\n'.join(blocks),new)
 new=g.set_fields(new,{'已收录参考答案题号':sorted(paper['questions']),'缺参考答案题号':[],
  '第八轮原创示范凭据':'reports/'+RECEIPT},
  '2026-10-13第八轮：原创参考作答与范文仅供练习；外部同题资料仅用于对照，不冒充来源原文')
 # Rebuild the previously created reading guide as an actual live index.
 fresh=r7.parse(new,rel)
 if set(fresh['questions'])!=set(paper['questions']):raise ValueError('Original task set changed')
 for n,q in paper['questions'].items():
  if b.qkey(q)!=b.qkey(fresh['questions'][n]):raise ValueError('Task stem changed')
 for n,ans in paper['answers'].items():
  if not is_missing(ans):
   current=fresh['answers'][n]
   if n not in byid and current!=ans:raise ValueError('Old answer unexpectedly changed')
   if n in byid and not current.startswith(ans):raise ValueError('Prior full answer not preserved')
  if n in byid:
   item=byid[n]
   if item['text'] not in fresh['answers'][n]:raise ValueError('Authored content absent from destination')
 old_guide=r7.GUIDE.search(new)
 if not old_guide:raise ValueError('R7 guide must already exist')
 new=new[:old_guide.start()]+r7.reading_guide(fresh)+new[old_guide.end():]
 final=r7.parse(new,rel)
 if set(final['questions'])!=set(paper['questions']):raise ValueError('Guide damaged task parsing')
 receipt={'path':rel,'before_sha256':g.digest(old),'after_sha256':g.digest(new),
  'old_question_keys':{str(n):b.qkey(q) for n,q in paper['questions'].items()},
  'preserved_nonempty_answers':{str(n):g.digest(a) for n,a in paper['answers'].items() if not is_missing(a)},
  'added_answers':[{'number':x['number'],'mode':x['mode'],'type':x['type'],'original_sha256':g.digest(x['text']),
   'original_characters':len(re.sub(r'\s','',x['text'])),'source_class':'AI原创示范，外部页面仅对照',
   'comparison_url':x['public_reference'],'delivered_answer_sha256':g.digest(final['answers'][x['number']])} for x in items],
  'operations':operations(old,new)}
 return new,receipt

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 data=json.loads(DATA.read_text(encoding='utf-8'));items=data['items']
 plans={}
 for x in items:plans.setdefault(x['path'],[]).append(x)
 if len(plans)!=4 or len(items)!=9:raise ValueError('Unexpected authored source inventory')
 result=[];errors=[]
 for rel,aa in sorted(plans.items()):
  try:
   p=ROOT/rel
   old=p.read_text(encoding='utf-8');new,rec=apply_text(old,rel,aa)
   result.append((p,new,rec))
  except Exception as e:errors.append({'path':rel,'error':str(e)})
 summary={'papers':len(result),'authored_answer_versions':sum(len(r['added_answers']) for _,_,r in result),
  'newly_filled':sum(a['mode']=='fill' for _,_,r in result for a in r['added_answers']),
  'new_full_essay_versions':sum(a['type']=='作文范文' for _,_,r in result for a in r['added_answers']),
  'errors':errors,'apply':args.apply}
 print('R8_AUTHORED_PREVIEW',json.dumps(summary,ensure_ascii=False),flush=True)
 if errors or len(result)!=4:raise ValueError('Authored delivery guard refused incomplete batch')
 if not args.apply:return
 receipt=ROOT/'reports'/RECEIPT
 if receipt.exists():raise ValueError('Already delivered')
 for p,new,r in result:
  if g.digest(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent source modification')
 for p,new,r in result:
  p.write_text(new,encoding='utf-8',newline='\n')
  if g.digest(p.read_bytes())!=r['after_sha256']:raise ValueError('Authored output hash mismatch')
 receipt.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in result),encoding='utf-8')
 (ROOT/'reports/REPAIR-SUMMARY-20261013-R8.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
