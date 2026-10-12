#!/usr/bin/env python3
"""Validate actual delivered bytes and independently reconstruct the R4 baseline."""
import json,shutil
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round5_delivery import body_text
from round4_delivery import is_missing

def records(root):
 p=Path(root)/'reports'/b.RECEIPT
 return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def reverse(text,r):
 if g.digest(text)!=r['after_sha256']:raise ValueError('R5 current hash mismatch '+r['path'])
 cursor=0;parts=[]
 for o in r['operations']:
  if o['new_start']<cursor or text[o['new_start']:o['new_end']]!=o['new']:raise ValueError('Invalid reversible operation')
  parts.extend([text[cursor:o['new_start']],o['old']]);cursor=o['new_end']
 parts.append(text[cursor:]);old=''.join(parts)
 if g.digest(old)!=r['before_sha256']:raise ValueError('R5 before hash mismatch')
 return old

def verify(root):
 root=Path(root).resolve();rr=records(root);by={r['path']:r for r in rr};cache={};count=0;oldanswers=0;questions=0
 if len(by)!=len(rr):raise ValueError('Duplicate receipt paths')
 def prior(rel):
  p=(root/rel).resolve()
  if not p.is_relative_to(root) or not p.is_file():raise ValueError('Unsafe or absent file')
  if rel not in cache:
   t=p.read_text(encoding='utf-8');cache[rel]=reverse(t,by[rel]) if rel in by else t
  return cache[rel]
 for r in rr:
  rel=r['path'];old=prior(rel);new=(root/rel).read_text(encoding='utf-8');od=b.parse(old,rel);nd=b.parse(new,rel)
  if body_text(old)!=body_text(new) or g.digest(body_text(old))!=r['body_sha256']:raise ValueError('Task or material mutation')
  if set(od['questions'])!=set(nd['questions']) or len(nd['questions'])!=r['question_count']:raise ValueError('Question count changed')
  questions+=len(od['questions'])
  for n,a in od['answers'].items():
   if not is_missing(a):
    if nd['answers'].get(n)!=a:raise ValueError('Existing answer changed')
    oldanswers+=1
  for a in r['added_answers']:
   n=a['number']
   if not is_missing(od['answers'].get(n,'')) or g.digest(od['questions'][n])!=a['target_question_sha256']:raise ValueError('Addition target was not empty')
   if g.digest(nd['answers'][n])!=a['delivered_answer_sha256']:raise ValueError('Added answer bytes changed')
   if a['kind'].startswith('repository_'):
    d=b.parse(prior(a['donor_path']),a['donor_path']);dn=a['donor_number']
    if g.digest(d['text'])!=a['donor_sha256'] or g.digest(d['answers'][dn])!=a['donor_answer_sha256'] or g.digest(d['questions'][dn])!=a['donor_question_sha256']:raise ValueError('Donor provenance changed')
    if d['identity'][1]!=od['identity'][1]:raise ValueError('Year mismatch')
    if not nd['answers'][n].startswith(d['answers'][dn]+'\n\n'):raise ValueError('Source answer not preserved')
    joint=d['identity'][0]!=od['identity'][0]
    if joint!=(a['kind']=='repository_joint_exam_question'):raise ValueError('Joint exam label mismatch')
    k=b.qkey(od['questions'][n]);dk=b.qkey(d['questions'][dn]);sim=1. if k==dk else __import__('difflib').SequenceMatcher(None,k,dk,autojunk=False).ratio()
    gg=b.shingles(d['materials'][dn]);tm=b.norm(od['materials'][n]);cov=sum(x in tm for x in gg)/max(1,len(gg))
    if sim<.97 or (joint and sim!=1) or len(gg)<35 or cov<(.985 if joint else .95):raise ValueError('Evidence below threshold')
   else:raise ValueError('Unknown answer source kind')
   count+=1
 return {'status':'passed','papers':len(rr),'added_answers':count,'original_question_blocks_preserved':questions,'existing_answers_preserved':oldanswers,'boundary':'Source matching and byte preservation, not official answer certification.'}

def snapshot(root,dest,receipt_names):
 root=Path(root);dest=Path(dest)
 shutil.copytree(root/'reports',dest/'reports')
 for top in ('国考','省考'):
  if (root/top).is_dir():shutil.copytree(root/top,dest/top)
 for r in records(root):
  p=dest/r['path'];p.write_text(reverse(p.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
 for name in receipt_names:
  p=root/'reports'/name
  if not p.exists():continue
  for line in p.read_text(encoding='utf-8').splitlines():
   if not line.strip():continue
   rel=json.loads(line)['path'];out=dest/rel
   if not out.exists():out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/rel,out)
 (dest/'reports'/b.RECEIPT).unlink()
if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parents[1]),ensure_ascii=False))
