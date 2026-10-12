#!/usr/bin/env python3
"""Check R8 study drafts against immutable target questions and exact original bytes."""
import json,shutil,re
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing
from r7_delivery import base_body as body_text, parse as r7_parse, strip_guide
from verify_round5_repairs import reverse
ROOT=Path(__file__).resolve().parents[1]
NAME='ROUND8-PRIORITY-ESSAY-20261013.jsonl'

def records(root):
 return [json.loads(x) for x in (Path(root)/'reports'/NAME).read_text(encoding='utf-8').splitlines() if x.strip()]

def verify(root):
 root=Path(root).resolve();rs=records(root);data=json.loads((root/'tools/data/r8-priority-reference-drafts.json').read_text(encoding='utf-8'))
 bypath={t['path']:t for t in data}
 if len(rs)!=4 or len(bypath)!=4:raise ValueError('Expected four paper repair receipts')
 inserted=0;preserved=0;questions=0
 for r in rs:
  rel=r['path'];p=(root/rel).resolve()
  if not p.is_relative_to(root) or rel not in bypath:raise ValueError('Unknown or unsafe path')
  new=p.read_text(encoding='utf-8');old=reverse(new,r);od=r7_parse(old,rel);nd=r7_parse(new,rel)
  if body_text(old)!=body_text(new) or g.digest(body_text(old))!=r['body_sha256']:raise ValueError('Paper body changed')
  if set(od['questions'])!=set(nd['questions']) or len(od['questions'])!=r['question_count']:raise ValueError('Question set changed')
  questions+=len(od['questions'])
  for n,a in od['answers'].items():
   if not is_missing(a):
    if a!=nd['answers'][n]:raise ValueError('Preexisting reference answer overwritten')
    preserved+=1
  if len(r['new_study_answers'])!=len(bypath[rel]['answers']):raise ValueError('Expected target count differs')
  for row in r['new_study_answers']:
   n=row['number'];orig=bypath[rel]['answers'][str(n)]
   ans=nd['answers'][n]
   if not is_missing(od['answers'].get(n,'')) or g.digest(od['questions'][n])!=row['target_question_sha256']:
    raise ValueError('Added answer was not truly missing')
   if g.digest(orig)!=row['original_text_sha256'] or g.digest(ans)!=row['answer_sha256']:raise ValueError('Reference SHA mismatch')
   if not ans.startswith('**原创练习参考作答（AI辅助撰写、未经过实考评分）**'):
    raise ValueError('Authorship disclosure lost')
   if bypath[rel]['source_url'] not in ans or row['comparison_source_url']!=bypath[rel]['source_url']:
    raise ValueError('Comparison source URL missing')
   inserted+=1
 if inserted!=7:raise ValueError('Incomplete R8 additions')
 return {'status':'passed','changed_papers':len(rs),'original_illustrative_answers':inserted,
   'original_question_blocks_preserved':questions,'existing_reference_answers_preserved':preserved,
   'boundary':'AI-assisted authored practice drafts, NOT externally scored essays or verbatim institutional model answers.'}

def snapshot(root,dest):
 root=Path(root).resolve();dest=Path(dest).resolve()
 shutil.copytree(root/'reports',dest/'reports')
 for top in ('国考','省考'):
  if (root/top).is_dir():shutil.copytree(root/top,dest/top)
 for r in records(root):
  p=dest/r['path'];p.write_text(reverse(p.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
 from verify_repair_receipts import RECEIPTS
 older=RECEIPTS+('ROUND4-ANSWERS-20261012.jsonl','ROUND5-ANSWERS-20261012.jsonl','ROUND6-OWNED-ANSWERS-20261013.jsonl','ROUND7-REFERENCES-20261013.jsonl')
 for name in older:
  source=root/'reports'/name
  if not source.is_file():continue
  for line in source.read_text(encoding='utf-8').splitlines():
   if not line.strip():continue
   rec=json.loads(line);rel=rec['path'];orig=(root/rel).resolve();out=(dest/rel).resolve()
   if not orig.is_relative_to(root) or not out.is_relative_to(dest):raise ValueError('Unsafe earlier receipt path')
   if not out.is_file():
    if not orig.is_file():raise ValueError('Missing earlier referenced artifact '+rel)
    out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(orig,out)
 (dest/'reports'/NAME).unlink()

if __name__=='__main__':print(json.dumps(verify(ROOT),ensure_ascii=False))
