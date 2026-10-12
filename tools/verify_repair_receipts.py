#!/usr/bin/env python3
"""Verify current and historical source-preservation receipts without weakening checks."""
from __future__ import annotations
import argparse,hashlib,json,tempfile
from pathlib import Path
from paper_integrity_repair import split_paper
from verify_essay_transcripts import verify as verify_essays
from verify_round3_repairs import verify as verify_round3

RECEIPTS = (
 'REFERENCE-SEQUENCE-20261012.jsonl','ESSAY-REPAIR-20261012.jsonl',
 'ESSAY-WHOLE-20261012.jsonl','NEW-PAPERS-20261012.jsonl',
 'LAYOUT-FOLLOWUP-20261012.jsonl','IMAGE-CROP-FOLLOWUP-20261012.jsonl',
 'WHITESPACE-FOLLOWUP-20261012.jsonl','ROUND2-ESSAY-20261012.jsonl',
 'ROUND2-LAYOUT-20261012.jsonl','ROUND3-ESSAY-20261012.jsonl',
 'ROUND3-LAYOUT-FOLLOWUP-20261012.jsonl',
)
def verify_prior(root:Path)->dict:
 root=root.resolve();latest={};records=[];questions=[]
 for name in RECEIPTS:
  f=root/'reports'/name
  if not f.is_file():raise ValueError('Missing receipt: '+name)
  for line_no,line in enumerate(f.read_text(encoding='utf-8').splitlines(),1):
   if not line.strip():continue
   r=json.loads(line);path=r['path'];p=(root/path).resolve()
   if not p.is_relative_to(root) or Path(path).is_absolute():raise ValueError('Unsafe receipt path')
   if not p.is_file():raise ValueError('Missing delivered file: '+path)
   if path in latest and latest[path]!=r.get('before_sha256'):raise ValueError('Broken superseding hash chain: '+path+' in '+name)
   after=r['after_sha256']
   if len(after)!=64 or any(c not in '0123456789abcdef' for c in after):raise ValueError('Invalid receipt hash')
   latest[path]=after;records.append((name,line_no,r))
   if name.startswith('REFERENCE-SEQUENCE'):questions.extend((path,a) for a in r.get('additions',[]))
 for path,expected in latest.items():
  if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Delivered bytes differ from latest receipt: '+path)
 cache={}
 for path,a in questions:
  d=cache.setdefault(path,split_paper((root/path).read_text(encoding='utf-8')));n=a['number']
  if n not in d['qs'] or n not in d['answers']:raise ValueError('Added question or answer lost: '+path+':'+str(n))
  for text,key in [(d['qs'][n]['text'],'question_sha256'),(d['answers'][n],'answer_sha256')]:
   if hashlib.sha256(text.encode()).hexdigest()!=a[key]:raise ValueError('Added question/answer body changed: '+path+':'+str(n))
 return {**verify_essays(root),'round3':verify_round3(root),'receipt_records':len(records),'distinct_delivered_files':len(latest),'paper_files':sum(p.endswith('.md') for p in latest),'image_files':sum(not p.endswith('.md') for p in latest),'added_question_answer_pairs_checked':len(questions),'status':'passed','boundary':'Hash, identity and preservation verification; not source factual certification.'}

def verify_to_round4(root:Path)->dict:
 root=Path(root).resolve()
 if not (root/'reports/ROUND4-ANSWERS-20261012.jsonl').exists():return verify_prior(root)
 from verify_round4_repairs import verify as verify_round4, historical_snapshot,records
 fourth=verify_round4(root)
 with tempfile.TemporaryDirectory(prefix='gwy-receipt-baseline-') as tmp:
  original_paths=historical_snapshot(root,Path(tmp),RECEIPTS)
  result=verify_prior(Path(tmp))
 r4=records(root);paths=original_paths|{r['path'] for r in r4}
 result.update({'round4':fourth,'receipt_records':result['receipt_records']+len(r4),'distinct_delivered_files':len(paths),'paper_files':sum(p.endswith('.md') for p in paths)})
 return result

def verify(root:Path)->dict:
 root=Path(root).resolve()
 if (root/'reports/ROUND8-PRIORITY-ESSAY-20261013.jsonl').exists():
  from verify_round8_priority import verify as verify_r8, snapshot as snapshot_r8, records as records_r8
  eighth=verify_r8(root)
  with tempfile.TemporaryDirectory(prefix='gwy-r8-original-baseline-') as tmp:
   snapshot_r8(root,Path(tmp))
   result=verify(Path(tmp))
  result['round8']=eighth
  result['receipt_records']+=len(records_r8(root))
  return result
 if (root/'reports/ROUND6-OWNED-ANSWERS-20261013.jsonl').exists():
  from verify_round6_repairs import verify as verify_round6, snapshot as snapshot_r6, records as r6_records
  sixth=verify_round6(root)
  with tempfile.TemporaryDirectory(prefix='gwy-r6-prior-') as tmp:
   snapshot_r6(root,Path(tmp))
   result=verify(Path(tmp))
  result['round6']=sixth
  result['receipt_records']+=len(r6_records(root))
  return result
 if not (root/'reports/ROUND5-ANSWERS-20261012.jsonl').exists():return verify_to_round4(root)
 from verify_round5_repairs import verify as verify_round5,snapshot,records
 fifth=verify_round5(root)
 with tempfile.TemporaryDirectory(prefix='gwy-r5-baseline-') as tmp:
  snapshot(root,Path(tmp),RECEIPTS+('ROUND4-ANSWERS-20261012.jsonl',))
  result=verify_to_round4(Path(tmp))
 result['round5']=fifth;result['receipt_records']+=len(records(root))
 return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=ap.parse_args()
 print(json.dumps(verify(args.root),ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
