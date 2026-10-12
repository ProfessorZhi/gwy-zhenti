#!/usr/bin/env python3
"""Verify only 190 new externally source-backed answer positions and undo R6."""
import hashlib,json,shutil
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round5_delivery import body_text
from round4_delivery import is_missing
from verify_round5_repairs import reverse

RECEIPT='ROUND6-OWNED-ANSWERS-20261013.jsonl'
REPO='ProfessorZhi/gwy-material-ops'
REV='710cb9f85b9ae5e4167cbdd5172c59309a51c80e'

def records(root):
 return [json.loads(x) for x in (Path(root)/'reports'/RECEIPT).read_text(encoding='utf-8').splitlines() if x.strip()]

def verify(root):
 root=Path(root).resolve();rr=records(root);seen=set();count=0;qa=0;held=0
 for r in rr:
  rel=r['path'];p=(root/rel).resolve()
  if rel in seen or not p.is_relative_to(root) or not p.is_file():raise ValueError('Unsafe/duplicate R6 file path')
  seen.add(rel)
  new=p.read_text(encoding='utf-8');old=reverse(new,r)
  od=b.parse(old,rel);nd=b.parse(new,rel)
  if body_text(old)!=body_text(new) or g.digest(body_text(old))!=r['body_sha256']:
   raise ValueError('Original materials or question body changed '+rel)
  if set(od['questions'])!=set(nd['questions']) or len(od['questions'])!=r['question_count']:
   raise ValueError('Original questions lost '+rel)
  qa+=len(od['questions'])
  for n,a in od['answers'].items():
   if not is_missing(a):
    if nd['answers'][n]!=a:raise ValueError('Pre-existing non-empty answer altered')
    held+=1
  for a in r['added_answers']:
   n=a['number']
   if (a.get('kind')!='user_owned_transcript' or
       a.get('source_repository')!=REPO or a.get('source_revision')!=REV):
    raise ValueError('Unapproved source for new R6 answer')
   if not is_missing(od['answers'].get(n,'')) or g.digest(od['questions'][n])!=a['target_question_sha256']:
    raise ValueError('Answer was inserted over non-empty or changed question')
   provided=nd['answers'][n];length=a.get('source_answer_chars')
   if not isinstance(length,int) or length<60 or length>15000:
    raise ValueError('Missing source length bound')
   if (g.digest(provided[:length])!=a['source_answer_sha256'] or
       not provided[length:].startswith('\n\n') or
       g.digest(provided)!=a['delivered_answer_sha256']):
    raise ValueError('Source answer mismatch '+rel+':'+str(n))
   if len(a.get('source_sha256',''))!=64 or len(a.get('source_blob',''))!=40 or len(a.get('previous_round5_receipt','')) not in (0,64):
    raise ValueError('Missing source file identity')
   proof=a.get('proof') or {}
   if (proof.get('stem_similarity',0)<.97 or proof.get('material_sample_hits',0)<10 or
       proof.get('material_sample_hits',0)>proof.get('material_samples_total',0)):
    raise ValueError('Insufficient original source matching receipt')
   count+=1
 if count!=190:raise ValueError('Expected 190 additional source answers, got '+str(count))
 return {'status':'passed','papers':len(rr),'new_reference_answers':count,
         'original_question_blocks_preserved':qa,'previous_real_answers_preserved':held,
         'boundary':'Integrity and fixed-source receipt verification, not official answer certification.'}

def snapshot(root,dest):
 root=Path(root);dest=Path(dest)
 shutil.copytree(root/'reports',dest/'reports')
 for top in ('国考','省考'):
  if (root/top).is_dir():shutil.copytree(root/top,dest/top)
 for r in records(root):
  p=dest/r['path']
  p.write_text(reverse(p.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
 # Earlier repair receipts include a small number of image crops. The original
 # R1-R5 verifiers require those exact bytes in a reconstructed baseline.
 from verify_repair_receipts import RECEIPTS
 for name in RECEIPTS+('ROUND4-ANSWERS-20261012.jsonl','ROUND5-ANSWERS-20261012.jsonl'):
  rp=root/'reports'/name
  if not rp.is_file():continue
  for line in rp.read_text(encoding='utf-8').splitlines():
   if not line.strip():continue
   rec=json.loads(line);rel=rec['path'];src=(root/rel).resolve()
   if not src.is_relative_to(root) or not src.is_file():raise ValueError('Unsafe older receipt path')
   out=(dest/rel).resolve()
   if not out.is_relative_to(dest):raise ValueError('Unsafe historical copy')
   if not out.exists():
    out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,out)
 (dest/'reports'/RECEIPT).unlink()

if __name__=='__main__':
 print(json.dumps(verify(Path(__file__).resolve().parents[1]),ensure_ascii=False))
