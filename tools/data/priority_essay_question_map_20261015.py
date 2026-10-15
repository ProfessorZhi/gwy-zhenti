"""Read-only question-level correspondence; shared material never implies identical tasks."""
import sys,json,hashlib,difflib
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as p
from priority_essay_inventory_six_regions_20261015 import inventory
papers=[];errors=[]
for x in inventory():
 try:
  d=p.parse((R/x['path']).read_text(encoding='utf8'),x['path'])
  x['questions']=[{'number':n,'key':p.qkey(q),'text':q[:700],'sha256':hashlib.sha256(p.qkey(q).encode()).hexdigest()} for n,q in d['questions'].items()]
  x.pop('source_meta',None);papers.append(x)
 except Exception as e:errors.append({'path':x['path'],'error':str(e)})
matches=[]
for x in papers:
 if x['vol']!='统考':continue
 peers=[y for y in papers if y['year']==x['year'] and y['area']==x['area'] and y['path']!=x['path']]
 for q in x['questions']:
  best=[]
  for y in peers:
   for s in y['questions']:
    score=difflib.SequenceMatcher(None,q['key'],s['key'],autojunk=False).ratio()
    if score>=.90:best.append({'path':y['path'],'number':s['number'],'ratio':round(score,4),'key':s['key']})
  matches.append({'path':x['path'],'number':q['number'],'key':q['key'],'matched_named_questions':best})
out={'papers':papers,'parser_errors':errors,'question_mappings':matches,'warning':'Candidate mappings require material and source identity review; a shared material prefix alone is never a whole-paper equivalence proof.'}
(R/'reports/PRIORITY-ESSAY-SIX-REGIONS-QUESTION-MAPS-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for x in matches:
 if ('上海/2024' in x['path'] or '上海/2025' in x['path'] or '天津/2025' in x['path'] or '天津/2026' in x['path']):print(x['path'],x['number'],[(m['path'],m['number'],m['ratio']) for m in x['matched_named_questions']])
print('PAPERS',len(papers),'ERRORS',errors)
