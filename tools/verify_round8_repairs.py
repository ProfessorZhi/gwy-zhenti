#!/usr/bin/env python3
"""Audit the truthful authored examples and recover exact R7 input bytes."""
from __future__ import annotations
import json,re,shutil
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing
from verify_round5_repairs import reverse
import r7_delivery as r7
from r8_authored_apply import RECEIPT

def records(root):
 return [json.loads(z) for z in (Path(root)/'reports'/RECEIPT).read_text(encoding='utf-8').splitlines() if z.strip()]

def verify(root):
 root=Path(root).resolve();rs=records(root);count=0;filled=0;essays=0;held=0
 if len(rs)!=4 or len({r['path'] for r in rs})!=len(rs):raise ValueError('Unexpected R8 paper inventory')
 for r in rs:
  rel=r['path'];p=(root/rel).resolve()
  if not p.is_relative_to(root) or not p.is_file():raise ValueError('Unsafe paper path')
  after=p.read_text(encoding='utf-8');before=reverse(after,r)
  old=r7.parse(before,rel);new=r7.parse(after,rel)
  if set(old['questions'])!=set(new['questions']):raise ValueError('Task set mutated')
  for n,q in old['questions'].items():
   if b.qkey(q)!=b.qkey(new['questions'][n]) or b.qkey(q)!=r['old_question_keys'][str(n)]:
    raise ValueError('Original question stem changed')
  for n,oldans in old['answers'].items():
   if not is_missing(oldans):
    if str(n) not in r['preserved_nonempty_answers'] or g.digest(oldans)!=r['preserved_nonempty_answers'][str(n)]:
     raise ValueError('Old answer receipt failed')
    if n not in {a['number'] for a in r['added_answers']} and new['answers'][n]!=oldans:
     raise ValueError('Original answer changed')
    if n in {a['number'] for a in r['added_answers']} and not new['answers'][n].startswith(oldans):
     raise ValueError('Pre-existing answer not preserved')
    held+=1
  for a in r['added_answers']:
   n=a['number'];cur=new['answers'][n]
   match=re.search(r'<!-- R8 authored answer -->\n(.*?)\n<!-- /R8 authored answer -->',cur,re.S)
   if not match or g.digest(match[1])!=a['original_sha256'] or g.digest(cur)!=a['delivered_answer_sha256']:
    raise ValueError('Generated example changed')
   if len(re.sub(r'\s','',match[1]))!=a['original_characters']:
    raise ValueError('Example character count changed')
   if '原创' not in cur or '非真实考场分数认证' not in cur or a['source_class']!='AI原创示范，外部页面仅对照':
    raise ValueError('Authorship or score disclaimer missing')
   if a['mode']=='fill':
    if not is_missing(old['answers'].get(n,'')):raise ValueError('Filled nonempty answer')
    filled+=1
   elif a['mode']!='alternative' or is_missing(old['answers'].get(n,'')):
    raise ValueError('Invalid alternative mode')
   if a['type']=='作文范文':essays+=1
   count+=1
 if count!=9 or filled!=7 or essays!=3:
  raise ValueError('Unexpected exact batch sizes')
 return {'status':'passed','papers':len(rs),'new_original_versions':count,'newly_filled_positions':filled,
   'new_full_essay_versions':essays,'previous_nonempty_answers_preserved':held,
   'boundary':'Original AI study examples only; no certified examination scores.'}

def snapshot(root,dest):
 root=Path(root).resolve();dest=Path(dest).resolve()
 shutil.copytree(root/'reports',dest/'reports')
 for top in ('国考','省考'):shutil.copytree(root/top,dest/top)
 for r in records(root):
  p=dest/r['path'];p.write_text(reverse(p.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
 from verify_repair_receipts import RECEIPTS
 older=RECEIPTS+('ROUND4-ANSWERS-20261012.jsonl','ROUND5-ANSWERS-20261012.jsonl',
   'ROUND6-OWNED-ANSWERS-20261013.jsonl','ROUND7-REFERENCES-20261013.jsonl')
 for name in older:
  f=root/'reports'/name
  if not f.exists():continue
  for line in f.read_text(encoding='utf-8').splitlines():
   if not line.strip():continue
   rel=json.loads(line)['path'];src=(root/rel).resolve();destfile=(dest/rel).resolve()
   if not src.is_relative_to(root) or not src.is_file() or not destfile.is_relative_to(dest):
    raise ValueError('Invalid older receipt path')
   if not destfile.is_file():
    destfile.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,destfile)
 (dest/'reports'/RECEIPT).unlink()

if __name__=='__main__':
 print(json.dumps(verify(Path(__file__).resolve().parents[1]),ensure_ascii=False))
