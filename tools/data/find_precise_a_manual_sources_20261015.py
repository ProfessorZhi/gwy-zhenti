import json,re,sys
from pathlib import Path
from difflib import SequenceMatcher
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'));sys.path.insert(0,str(Path(__file__).parent))
from confirm_priority_count_gaps_mops_20261015 import extract
from full_repair_precise_answer_audit_20261015 import word_rules
import round5_bulk as b
D=json.loads((R/'tools/data/precise-a-review-packets-20261015.json').read_text(encoding='utf8'));base=Path('D:/projects/gwy-material-ops/knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf');cache={};out=[]
for i,r in enumerate(D):
 if r['word_rules']['kind']!='unspecified':continue
 area,year=r['path'].split('/')[1:3];group=(area,year)
 if group not in cache:
  zs=[]
  for folder in base.iterdir():
   if area not in folder.name:continue
   for p in folder.rglob(year+'*申论*.md'):
    raw=p.read_text(encoding='utf8');e=extract(raw)
    for q in e.get('questions',[]):
     rules=word_rules(q['text'])
     if rules['kind']!='unspecified':zs.append(dict(source_path=str(p),source_question=q['text'],rules=rules,number=q['number'],question_key=b.qkey(q['text'])))
  cache[group]=zs
 key=b.qkey(r['question']);matches=sorted(((SequenceMatcher(None,key,z['question_key'],autojunk=False).ratio(),z) for z in cache[group]),key=lambda z:z[0],reverse=True)[:2]
 row=dict(index=i,path=r['path'],number=r['question_number'],question=r['question'],matches=[dict(similarity=s,**z) for s,z in matches if s>.75]);out.append(row);print(i,r['path'],r['question_number'],[(x['similarity'],Path(x['source_path']).name,x['number'],x['rules']) for x in row['matches']],flush=True)
(R/'tools/data/precise-a-manual-owned-matches-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
