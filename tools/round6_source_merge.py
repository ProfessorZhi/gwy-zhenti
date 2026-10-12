#!/usr/bin/env python3
"""Import only 190 independently sourced answers; never re-apply the 102 already merged."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round5_delivery import render,body_text
from round4_delivery import operations,is_missing

ROOT=b.ROOT
OLD_HEAD='53c4646b3b63b1661e2dca41bc6437d46bc7254a'
BASE='95de886482d2982cc9a7671dd56a9c562f4fdd84'
SOURCE_REPO='ProfessorZhi/gwy-material-ops'
SOURCE_REV='710cb9f85b9ae5e4167cbdd5172c59309a51c80e'
RECEIPT='ROUND6-OWNED-ANSWERS-20261013.jsonl'

def from_original(path):
 import os
 if not os.environ.get('GH_TOKEN'):raise ValueError('Authenticated read-only source required')
 helper='!f() { echo username=x-access-token; echo password=$GH_TOKEN; }; f'
 return subprocess.check_output(['git','-c','credential.helper='+helper,'show',OLD_HEAD+':'+path]).decode('utf-8')
def assemble():
 old_receipts=[json.loads(x) for x in from_original('reports/ROUND5-ANSWERS-20261012.jsonl').splitlines() if x]
 out=[];errors=[];seen=set()
 for r in old_receipts:
  selected=[a for a in r['added_answers'] if a.get('kind')=='user_owned_transcript']
  if not selected:continue
  rel=r['path']
  if rel in seen:raise ValueError('Duplicate original source path '+rel)
  seen.add(rel)
  original=from_original(rel)
  if g.digest(original)!=r['after_sha256']:raise ValueError('Original source SHA mismatch '+rel)
  od=b.parse(original,rel)
  from verify_round5_repairs import reverse
  before_original=reverse(original,r)
  bod=b.parse(before_original,rel)
  target=ROOT/rel
  if not target.is_file():raise ValueError('Missing new target '+rel)
  t=b.parse(target.read_text(encoding='utf-8'),rel)
  additions=[]
  for a in selected:
   n=a['number'];length=a['source_answer_chars'];source=od['answers'][n][:length]
   if (a.get('source_repository')!=SOURCE_REPO or a.get('source_revision')!=SOURCE_REV or
      len(source)<60 or g.digest(source)!=a['source_answer_sha256'] or
      not od['answers'][n][length:].startswith('\n\n')):
    raise ValueError('Original private source answer/identity mismatch '+rel+':'+str(n))
   if (n not in t['questions'] or not is_missing(t['answers'].get(n,'')) or
       n not in bod['questions'] or g.digest(bod['questions'][n])!=a['target_question_sha256'] or
       b.qkey(bod['questions'][n])!=b.qkey(t['questions'][n])):
    raise ValueError('Pre-existing or mismatched GitHub-main target '+rel+':'+str(n))
   if body_text(t['text'])!=body_text(original):
    raise ValueError('Original document material/task body moved since first verification '+rel)
   additions.append({**a,'answer':source,
                    'original_round5_target_question_sha256':a['target_question_sha256'],
                    'target_question_sha256':g.digest(t['questions'][n])})
  try:
   new,pre=render(t,additions)
   if not re.search(r'(?m)^第五轮修复凭据:',t['text']):
    new=re.sub(r'(?m)^第五轮修复凭据:.*\n','',new)
   new=g.set_fields(new,{'第六轮原始资料补答案凭据':'reports/'+RECEIPT},
                    '2026-10-13第六轮：仅补尚缺的私人来源答案；保留第五轮全部原题及已收录答案')
   nd=b.parse(new,rel)
   if body_text(new)!=body_text(t['text']):raise ValueError('Material/task body changed')
   for n,oldans in t['answers'].items():
    if not is_missing(oldans) and nd['answers'][n]!=oldans:
     raise ValueError('Existing reference answer changed '+str(n))
   rr={'path':rel,'before_sha256':g.digest(t['text']),'after_sha256':g.digest(new),
       'kind':'owned_answer_only','question_count':len(t['questions']),
       'body_sha256':g.digest(body_text(t['text'])),'previous_round5_receipt':r['after_sha256'],
       'added_answers':[{**{k:v for k,v in a.items() if k!='answer'},
        'delivered_answer_sha256':g.digest(nd['answers'][a['number']])} for a in additions],
       'preserved_answers':{str(n):g.digest(ans) for n,ans in t['answers'].items() if not is_missing(ans)},
       'remaining_answer_ids':nd['missing'],'operations':operations(t['text'],new)}
   out.append((t,new,rr))
  except Exception as e:errors.append({'path':rel,'error':str(e)})
 return out,errors

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 ready,errors=assemble()
 answers=sum(len(r['added_answers']) for _,_,r in ready)
 summary={'baseline':BASE,'old_transcript_result':OLD_HEAD,'modified_papers':len(ready),
    'new_reference_answers':answers,'r5_existing_answers_untouched':102,
    'refused':errors,'apply':args.apply,'known_original_question_gaps_still_missing':25,
    'boundary':'Only reference-answer positions: not independent question or official-paper certification'}
 print('R6_SOURCE_MERGE',json.dumps(summary,ensure_ascii=False),flush=True)
 if errors or answers!=190:raise ValueError('Safe import requires exactly 190 verified non-overlapping source answers')
 if not args.apply:return
 receipt=ROOT/'reports'/RECEIPT
 if receipt.exists():raise ValueError('Already applied')
 for t,new,r in ready:
  p=ROOT/r['path']
  if g.digest(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent input change')
 for t,new,r in ready:
  p=ROOT/r['path'];p.write_text(new,encoding='utf-8',newline='\n')
  if g.digest(p.read_bytes())!=r['after_sha256']:raise ValueError('Writeback mismatch')
 receipt.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in ready),encoding='utf-8')
 (ROOT/'reports/REPAIR-SUMMARY-20261013-R6.json').write_text(
   json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
