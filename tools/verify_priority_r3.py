"""Offline verification of R3 delivered task/material/answer bodies and receipts."""
import hashlib,json,re
from pathlib import Path
from priority_r3_answers import DETAIL,digest

def verify(root=Path('.')):
 whole=root/'reports/ROUND3-WHOLE-20261012.jsonl';count=0;materials=0;answers=0
 for line in whole.read_text(encoding='utf-8').splitlines():
  r=json.loads(line);s=(root/r['path']).read_text(encoding='utf-8')
  if digest(s)!=r['after_sha256']:raise ValueError('File changed: '+r['path'])
  mats={int(m[1]):m[2].strip() for m in re.finditer(r'^## 给定资料 (\d+)\n(.*?)(?=^## |\Z)',s,re.M|re.S)}
  if list(mats)!=list(range(1,r['original_material_count']+1)):raise ValueError('Material coverage lost')
  for m in r['material_mapping']:
   t=mats[m['original_number']]
   if digest(t)!=m['delivered_sha256']:raise ValueError('Material body changed')
   if m['type']=='preserved_existing_material' and digest(re.sub(r'\s+','',t))!=m['non_whitespace_sha256']:raise ValueError('Preserved source text changed')
  qs={int(m[1]):m[2].split('### 作答要求',1)[-1].strip() for m in re.finditer(r'^## 第 (\d+) 题\n(.*?)(?=^## |\Z)',s,re.M|re.S)}
  if list(qs)!=list(range(1,r['original_task_count']+1)):raise ValueError('Task order changed')
  for n,t in qs.items():
   if digest(t)!=r['question_sha256'][str(n)] or not re.search(r'\d+\s*字',t):raise ValueError('Task requirements changed')
  if sum(r['task_scores'])!=100:raise ValueError('Score total changed')
  actual={int(m[1]):m[2].strip() for m in DETAIL.finditer(s)}
  for a in r['preserved_answers']:
   if digest(actual[a['original_number']])!=a['delivered_sha256']:raise ValueError('Answer body changed')
   if a['unchanged'] and a['old_sha256']!=a['delivered_sha256']:raise ValueError('False preservation claim')
  if any(x in s for x in ['气瓶气管里面找','马洛里斯去了']):raise ValueError('Known corrupt transcription')
  count+=1;materials+=len(mats);answers+=len(r['preserved_answers'])
 for line in (root/'reports/ROUND3-ANSWERS-20261012.jsonl').read_text().splitlines():
  r=json.loads(line);s=(root/r['path']).read_text();actual={str(int(m[1])):digest(m[2].strip()) for m in DETAIL.finditer(s)}
  if digest(s)!=r['after_sha256']:raise ValueError('Answer-repair bytes changed')
  for n,h in (r['preserved_answers']|r['delivered_answer_sha256']).items():
   if actual.get(n)!=h:raise ValueError('Answer preservation failed')
  if digest(s.split('---',2)[2].split('## 答案与解析')[0])!=r['body_sha256']:raise ValueError('Question body changed during answer repair')
 return {'R3_whole_papers_verified':count,'R3_material_bodies_verified':materials,'R3_prior_answer_bodies_verified':answers,'status':'passed'}
if __name__=='__main__':print(json.dumps(verify(),ensure_ascii=False))
