#!/usr/bin/env python3
"""Verify R4 and reconstruct a temporary read-only baseline for prior receipt checks."""
from __future__ import annotations
import json,re,shutil
from pathlib import Path
from round4_gap_repair import parse_text,digest,match,key,grams,plain
from round4_delivery import is_missing,body_without_inserted_headers,RECEIPT

def records(root):
 f=Path(root)/'reports'/RECEIPT
 return [json.loads(x) for x in f.read_text(encoding='utf-8').splitlines() if x.strip()] if f.exists() else []
def reverse(text,r):
 if digest(text)!=r['after_sha256']:raise ValueError('R4 current file hash mismatch: '+r['path'])
 previous_end=0
 for op in r['operations']:
  a,b=op['new_start'],op['new_end']
  if not 0<=a<=b<=len(text) or a<previous_end:raise ValueError('Overlapping/invalid reverse operation')
  if text[a:b]!=op['new']:raise ValueError('Changed replacement bytes')
  previous_end=b
 for op in reversed(r['operations']):text=text[:op['new_start']]+op['old']+text[op['new_end']:]
 if digest(text)!=r['before_sha256']:raise ValueError('R4 baseline reconstruction mismatch')
 return text

def verify(root):
 root=Path(root).resolve();rs=records(root);by={r['path']:r for r in rs}
 if len(by)!=len(rs):raise ValueError('Duplicate R4 path')
 cache={}
 def before(rel):
  if rel not in cache:
   p=(root/rel).resolve()
   if not p.is_relative_to(root) or p.suffix!='.md' or not p.is_file():raise ValueError('Unsafe/missing paper path')
   txt=p.read_text(encoding='utf-8');cache[rel]=reverse(txt,by[rel]) if rel in by else txt
  return cache[rel]
 answers=0;joint=0;kept=0;questions=0
 for r in rs:
  rel=r['path'];old=before(rel);current=(root/rel).read_text(encoding='utf-8')
  a=parse_text(old,rel);b=parse_text(current,rel)
  if not a or not b or set(a['questions'])!=set(b['questions']):raise ValueError('Question identity set changed')
  if len(a['questions'])!=r['question_count']:raise ValueError('Question count changed')
  originalbody=body_without_inserted_headers(old,r['old_mode']);newbody=body_without_inserted_headers(current,r['old_mode'])
  if originalbody!=newbody or digest(originalbody)!=r['body_sha256']:raise ValueError('Question/material bytes changed')
  complete=set()
  for n,answer in a['answers'].items():
   if not is_missing(answer):
    if b['answers'].get(n)!=answer or r['preserved_answers'].get(str(n))!=digest(answer):raise ValueError('Existing answer lost')
    kept+=1;complete.add(n)
  seen=set()
  for x in r['added_answers']:
   n=x['number']
   if n in seen or n not in a['questions'] or not is_missing(a['answers'].get(n,'')):raise ValueError('Invalid answer addition')
   seen.add(n);complete.add(n);d=parse_text(before(x['donor_path']),x['donor_path']);dn=x['donor_number']
   if digest(d['text'])!=x['donor_sha256'] or digest(d['answers'][dn])!=x['donor_answer_sha256']:raise ValueError('Donor source changed')
   if d['identity'][1]!=a['identity'][1]:raise ValueError('Cross-year source')
   proof,why=match(a,n,[(d,dn)])
   if not proof or proof['donor_number']!=dn:raise ValueError('Source mapping no longer proves same question: '+str(why))
   if x['kind']=='repository_joint_exam_question':
    if proof['stem_similarity']!=1 or proof['material_coverage']<.98:raise ValueError('Unproved joint-exam reuse')
    joint+=1
   elif d['identity']!=a['identity']:raise ValueError('Cross-region source not declared')
   answer=b['answers'].get(n,'')
   if digest(answer)!=x['delivered_answer_sha256'] or not answer.startswith(d['answers'][dn]+'\n\n'):raise ValueError('New answer differs from recorded source')
   if x['source_url'] not in answer:raise ValueError('Attribution missing')
   answers+=1
  missing=[n for n in b['questions'] if is_missing(b['answers'].get(n,''))]
  if missing!=r['remaining_answer_ids'] or set(missing)!=set(b['questions'])-complete:raise ValueError('False completeness claim')
  questions+=len(a['questions'])
 return {'status':'passed','papers':len(rs),'added_existing_source_answers':answers,'joint_exam_answers':joint,'original_answers_preserved':kept,'original_question_blocks_preserved':questions,'boundary':'Reference answer reuse with same-question evidence; not official answer or complete-corpus certification.'}

def historical_snapshot(root,destination,receipt_names):
 root=Path(root);dest=Path(destination);dest.mkdir(parents=True,exist_ok=True)
 shutil.copytree(root/'reports',dest/'reports',dirs_exist_ok=True)
 r4={r['path']:r for r in records(root)};paths=set()
 for name in receipt_names:
  for line in (root/'reports'/name).read_text(encoding='utf-8').splitlines():
   if line.strip():paths.add(json.loads(line)['path'])
 for rel in paths:
  src=(root/rel).resolve();target=(dest/rel).resolve()
  if not src.is_relative_to(root.resolve()) or not target.is_relative_to(dest.resolve()):raise ValueError('Unsafe historical path')
  target.parent.mkdir(parents=True,exist_ok=True)
  if rel in r4:target.write_text(reverse(src.read_text(encoding='utf-8'),r4[rel]),encoding='utf-8',newline='\n')
  else:shutil.copyfile(src,target)
 return paths
if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parents[1]),ensure_ascii=False,sort_keys=True))
