#!/usr/bin/env python3
"""Add sourced reference text and a per-paper guide, preserving every old source byte."""
from __future__ import annotations
import argparse,collections,json,re
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing,operations
from round5_delivery import body_text as prior_body
from r7_reference_audit import assess,task_type,word_range
import r7_reference_matching as matcher
import r7_owned_matching as owned
ROOT=b.ROOT
BASE=matcher.BASE
RECEIPT='ROUND7-REFERENCES-20261013.jsonl'
GUIDE=re.compile(r'\n<!-- R7 reading guide -->\n[\s\S]*?\n<!-- /R7 reading guide -->\n')
ANCHOR=re.compile(r'\n<a id="r7-reference-\d+"></a>\n')
NAV=re.compile(r'\n<!-- R7 question anchor (\d+) -->\n## 第 \1 题\n\n')
PENDING='本题尚未收录可核对的完整参考作答；保留题面，继续查找同题版本。'

def strip_guide(t):return GUIDE.sub('',t)
def base_body(t):return prior_body(NAV.sub('',ANCHOR.sub('',strip_guide(t))))
def parse(t,rel):return b.parse(strip_guide(t),rel)
def status_label(s):return {'已收录':'已有参考版本','待补':'待补同题全文','正文偏短待复核':'范文篇幅偏短，待补完整版本','正文或图像待复核':'需检查正文或图像'}.get(s,s)

def reading_guide(d,reason=None):
 lines=['<!-- R7 reading guide -->','', '## 参考作答与范文导读','',
  '> 小题看要点与文种，大作文看立意、结构和论证。机构、教师、考生的同题作答可作为不同版本对照；未经核实的实考得分不作高分承诺。','']
 if d is None:
  lines+=['**题号结构待核对。** 当前排版尚不能可靠对应全部题目与作答。下方原文完整保留，不凭文件名或旧摘要补造题号，也不将本页计入作答齐全。','']
 else:
  ss=[(n,assess(q,d['answers'].get(n,''))) for n,q in d['questions'].items()]
  have=sum(s['status']=='已收录' for _,s in ss)
  lines+=[f"文内识别 {len(ss)} 道作答题；其中 {have} 题已有可读取的参考版本。该统计是收录与篇幅检查，不代表分数鉴定或原卷完整认证。",'',
          '| 题号 | 阅读类型 | 当前收录情况 | 入口 |','|---|---|---|---|']
  for n,s in ss:
   entry=f'[查看第{n}题作答](#r7-reference-{n})' if n in d['answers'] else '暂未收录'
   lines.append(f"| {n} | {s['kind']} | {status_label(s['status'])} | {entry} |")
  lines+=['','**范文使用方式：** 先自行作答，再对照材料覆盖、论证展开与表达。来源中的参考例文不是唯一写法；原文附带的解析和其他版本一并保留。','']
 lines+=['<!-- /R7 reading guide -->']
 return '\n'+'\n'.join(lines)+'\n'

def insert_guide(text,d=None,reason=None):
 if GUIDE.search(text):raise ValueError('R7 guide already present')
 h=re.search(r'(?m)^# [^\n]+\n',text)
 if not h:raise ValueError('Missing paper title')
 return text[:h.end()]+reading_guide(d,reason)+text[h.end():]

def render(old,rel,paper,adds,reason=None):
 byid={a['number']:a for a in adds}
 if len(byid)!=len(adds):raise ValueError('Duplicate addition')
 if paper is None and adds:raise ValueError('Cannot map answers in an unparsed paper')
 new=old
 for a in adds:
  n=a['number']
  if n not in paper['questions'] or g.digest(paper['questions'][n])!=a['target_question_sha256']:
   raise ValueError('Stale target question')
  if g.digest(a['answer'])!=a['answer_sha256'] or not matcher.source_usable(paper['questions'][n],a['answer']):
   raise ValueError('Incomplete or changed reference text')
  if assess(paper['questions'][n],paper['answers'].get(n,''))['status']=='已收录':
   raise ValueError('Do not replace an existing usable reference')
 def reference(n):
  a=byid[n];kind=task_type(paper['questions'][n]);source=a['source_title'].replace('\n',' ').replace('|','／')
  heading='同题作文范文' if kind=='作文范文' else '同题参考作答'
  content='**'+heading+'**\n\n<!-- R7 reference text -->\n'+a['answer']+'\n<!-- /R7 reference text -->\n\n'
  content+='> 来源说明：'+source+'。按同题题干、年份及给定材料核对后收录；属于参考版本，不作为唯一答文或实考分数证明。'
  if a.get('cross_province'):content+=' 此题使用跨省共用题来源，不将来源整卷视为本卷。'
  content+='\n\n[查看本题来源]('+a['source_url']+')'
  previous=paper['answers'].get(n,'')
  if not is_missing(previous):
   content+='\n\n---\n\n**此前收录版本（原文保留，用于对照）**\n\n'+previous
  return content
 if adds:
  if paper['answer_heading']:
   def replace(m):
    n=int(m[2]);return m[1]+'\n\n'+reference(n)+'\n\n'+m[4] if n in byid else m[0]
   new=g.DETAIL.sub(replace,new)
   if any(n not in paper['answers'] for n in byid):raise ValueError('Missing required answer slot')
  else:
   if paper['mode']=='unstructured':
    for n,at in sorted(paper['question_spans'].items(),key=lambda x:x[1],reverse=True):
     new=new[:at]+f'\n<!-- R7 question anchor {n} -->\n## 第 {n} 题\n\n'+new[at:]
   blocks=['## 答案与解析','> 各题参考版本注明来源。未找到同题完整作答的题继续留缺，不以摘要充当范文。']
   for n in paper['questions']:
    blocks.append(f'<details>\n<summary>第 {n} 题</summary>\n\n'+(reference(n) if n in byid else PENDING)+'\n\n</details>')
   new=new.rstrip()+'\n\n'+'\n\n'.join(blocks)+'\n'
 # Add stable reading anchors before answer containers, without changing their original text.
 if paper is not None:
  new=g.DETAIL.sub(lambda m:'\n<a id="r7-reference-'+m[2]+'"></a>\n'+m[0],new)
 before_g=parse(new,rel) if paper is not None else None
 if paper is not None:
  if set(before_g['questions'])!=set(paper['questions']):raise ValueError('Question ids changed')
  if base_body(old)!=base_body(new):raise ValueError('Original paper body changed')
  for n,a in paper['answers'].items():
   if not is_missing(a):
    if n not in byid and before_g['answers'].get(n)!=a:raise ValueError('Old answer was modified')
    if n in byid and not before_g['answers'][n].endswith(a):raise ValueError('Old version was not preserved')
 new=insert_guide(new,before_g,reason)
 if paper is not None and base_body(old)!=base_body(new):raise ValueError('Guide altered underlying paper')
 receipt={'path':rel,'before_sha256':g.digest(old),'after_sha256':g.digest(new),
   'parsed':paper is not None,'parse_issue':reason,'guide_only':not bool(adds),
   'body_sha256':g.digest(base_body(old)) if paper is not None else None,
   'questions_before':list(paper['questions']) if paper else [],
   'preserved_answers':{str(n):g.digest(a) for n,a in (paper['answers'].items() if paper else []) if not is_missing(a)},
   'added_references':[{**{k:v for k,v in a.items() if k!='answer'},
      'type':task_type(paper['questions'][a['number']]),
      'delivered_block_sha256':g.digest(before_g['answers'][a['number']])} for a in adds],
   'operations':operations(old,new)}
 return new,receipt

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 papers,bad=matcher.read_all();ip,_,_=matcher.find_internal(papers);plans,source_stats=owned.match(papers,ip)
 bypath={t['path']:(t,a) for t,a in plans};known={p['path']:p for p in papers};issues={r['path']:r['reason'] for r in bad}
 ready=[];errors=[]
 paths=sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')])
 for p in paths:
  rel=p.relative_to(ROOT).as_posix();old=p.read_text(encoding='utf-8');paper=known.get(rel);adds=bypath.get(rel,(None,[]))[1]
  try:
   new,r=render(old,rel,paper,adds,issues.get(rel));ready.append((p,new,r))
  except Exception as e:errors.append({'path':rel,'error':str(e)})
 added=[a for _,_,r in ready for a in r['added_references']]
 summary={'baseline':BASE,'all_essay_files':len(paths),'updated_documents':len(ready),'guide_only_documents':sum(r['guide_only'] for _,_,r in ready),
  'documents_with_new_reference_text':sum(not r['guide_only'] for _,_,r in ready),'new_reference_blocks':len(added),
  'newly_filled_answer_positions':sum(a['was_missing'] for a in added),'expanded_existing_examples':sum(not a['was_missing'] for a in added),
  'new_example_essays':sum(a['type']=='作文范文' for a in added),'new_short_task_references':sum(a['type']!='作文范文' for a in added),
  'source_candidates_processed':source_stats,'unparsed_documents':bad,'errors':errors,'apply':args.apply,
  'boundary':'Per-document guides are not newly completed answers. Only actual inserted full reference text is counted as an answer addition.'}
 print('R7_DELIVERY_PREVIEW',json.dumps(summary,ensure_ascii=False),flush=True)
 if not args.apply:return
 receipt=ROOT/'reports'/RECEIPT
 if receipt.exists() or errors or len(ready)!=738:raise ValueError('Incomplete/previously-applied delivery; nothing committed')
 for p,new,r in ready:
  if g.digest(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent source change')
 for p,new,r in ready:
  p.write_text(new,encoding='utf-8',newline='\n')
  if g.digest(p.read_bytes())!=r['after_sha256']:raise ValueError('MD writeback mismatch')
 receipt.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in ready),encoding='utf-8')
 (ROOT/'reports/REPAIR-SUMMARY-20261013-R7.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
