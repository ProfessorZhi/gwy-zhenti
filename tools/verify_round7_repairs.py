#!/usr/bin/env python3
"""R7 independently verifies all 738 updated essays, new sourced references and reversible bytes."""
from __future__ import annotations
import json,shutil,re
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing
from r7_reference_audit import assess
from r7_reference_matching import source_usable
from r7_delivery import RECEIPT,base_body,strip_guide
from verify_round5_repairs import reverse

def records(root):
 p=Path(root)/'reports'/RECEIPT
 return [json.loads(z) for z in p.read_text(encoding='utf-8').splitlines() if z.strip()]

def verify(root):
 root=Path(root).resolve();rr=records(root)
 expected=list(sorted([*root.glob('国考/*/申论*.md'),*root.glob('省考/*/*/申论*.md')]))
 if len(rr)!=len(expected) or len(rr)!=738:raise ValueError('Not all essay documents covered')
 expected_paths={p.relative_to(root).as_posix() for p in expected}
 if {r['path'] for r in rr}!=expected_paths:raise ValueError('Missing/duplicated essay paths')
 added=0;filled=0;essays=0;guideonly=0;unchanged_answers=0;questions=0
 for r in rr:
  path=r['path'];p=(root/path).resolve()
  if not p.is_relative_to(root) or not p.is_file():raise ValueError('Unsafe or absent path')
  new=p.read_text(encoding='utf-8')
  old=reverse(new,r)
  if r['guide_only']!=(not bool(r['added_references'])):raise ValueError('Mismatched additions flag')
  if new.count('<!-- R7 reading guide -->')!=1 or new.count('<!-- /R7 reading guide -->')!=1:
   raise ValueError('Reading guide missing or repeated')
  if r['parsed']:
   if g.digest(base_body(old))!=r['body_sha256'] or base_body(old)!=base_body(new):
    raise ValueError('Question or materials body changed')
   before=b.parse(old,path);after=b.parse(strip_guide(new),path)
   if set(before['questions'])!=set(after['questions']) or set(before['questions'])!=set(r['questions_before']):
    raise ValueError('Task id changed')
   questions+=len(before['questions'])
   for n,ans in before['answers'].items():
    if not is_missing(ans):
     if n not in {a['number'] for a in r['added_references']} and after['answers'][n]!=ans:
      raise ValueError('Old nonempty reference overwritten')
     if n in {a['number'] for a in r['added_references']} and not after['answers'][n].endswith(ans):
      raise ValueError('Old alternative not retained')
     unchanged_answers+=1
   for a in r['added_references']:
    n=a['number'];block=after['answers'][n];src=a['answer_sha256']
    if g.digest(before['questions'][n])!=a['target_question_sha256']:
     raise ValueError('Wrong target task hash')
    if g.digest(block)!=a['delivered_block_sha256']:
     raise ValueError('Delivered answer changed')
    fragment=re.search(r'<!-- R7 reference text -->\n(.*?)\n<!-- /R7 reference text -->',block,re.S)
    if not fragment or g.digest(fragment[1])!=src or len(fragment[1])!=a['answer_length']:
     raise ValueError('Source reference answer mismatch')
    if not source_usable(before['questions'][n],fragment[1]):
     raise ValueError('Proposed reference is incomplete')
    if a['kind']=='repository_reference':
     donor=root/a['donor_path']
     if not donor.is_file():raise ValueError('No donor file')
     # R7 may modify the donor as well: verify its previous version via receipts.
     bypath=cache_by_path
     donor_text=reverse(donor.read_text(encoding='utf-8'),bypath[a['donor_path']]) if a['donor_path'] in bypath else donor.read_text(encoding='utf-8')
     d=b.parse(donor_text,a['donor_path']);dn=a['donor_number']
     if (g.digest(d['text'])!=a['donor_file_sha256'] or
         g.digest(d['questions'][dn])!=a['donor_question_sha256'] or
         g.digest(d['answers'][dn])!=a['donor_answer_sha256']):
      raise ValueError('Donor identity/hash mismatch')
    elif a['kind']=='owned_reference':
     if (a.get('source_repository')!='ProfessorZhi/gwy-material-ops' or
         a.get('source_revision')!='710cb9f85b9ae5e4167cbdd5172c59309a51c80e' or
         len(a.get('source_file_sha256',''))!=64 or len(a.get('source_blob',''))!=40):
      raise ValueError('Original private source metadata wrong')
    else:raise ValueError('Unrecognized source kind')
    if a['was_missing']!=is_missing(before['answers'].get(n,'')):raise ValueError('Wrong before-answer status')
    if a['was_missing']:filled+=1
    if a['type']=='作文范文':essays+=1
    added+=1
  else:
   if r['added_references'] or r['questions_before']:raise ValueError('Unparsed paper must not add guessed answers')
  if r['guide_only']:guideonly+=1
 cache_by_path  # validate dictionary presence at function entry
 if added<10 or filled<9:raise ValueError('Unexpected low reference count')
 return {'status':'passed','documents':len(rr),'guide_only_documents':guideonly,'new_reference_blocks':added,
         'newly_filled_answer_positions':filled,'new_example_essays':essays,'question_blocks_preserved':questions,
         'nonempty_old_answer_blocks_preserved':unchanged_answers,
         'boundary':'Guides do not count as answers; sourced reference hashes and old bytes are checked, not scoring authority.'}

def snapshot(root,dest):
 root=Path(root);dest=Path(dest)
 shutil.copytree(root/'reports',dest/'reports')
 for top in ('国考','省考'):
  shutil.copytree(root/top,dest/top)
 for r in records(root):
  p=dest/r['path'];p.write_text(reverse(p.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
 from verify_repair_receipts import RECEIPTS
 for name in RECEIPTS+('ROUND4-ANSWERS-20261012.jsonl','ROUND5-ANSWERS-20261012.jsonl','ROUND6-OWNED-ANSWERS-20261013.jsonl'):
  rp=root/'reports'/name
  if not rp.exists():continue
  for line in rp.read_text(encoding='utf-8').splitlines():
   if not line.strip():continue
   rel=json.loads(line)['path'];src=(root/rel).resolve();out=(dest/rel).resolve()
   if not src.is_relative_to(root) or not out.is_relative_to(dest) or not src.exists():
    raise ValueError('Unsafe older receipt file')
   if not out.exists():
    out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,out)
 (dest/'reports'/RECEIPT).unlink()

def main():
 global cache_by_path
 root=Path(__file__).resolve().parents[1];rr=records(root);cache_by_path={r['path']:r for r in rr}
 print(json.dumps(verify(root),ensure_ascii=False))
if __name__=='__main__':main()
