"""Read-only preservation/limit checks on the six-paper reviewed repair."""
import sys,json,re,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as parser
from full_repair_guangdong_township_constraints_20261015 import active_body
from full_repair_answers_20261015 import validate_answer
rows=[json.loads(x) for x in (R/'reports/FULL-REPAIR-GUANGDONG-TOWNSHIP-CONSTRAINTS-20261015.jsonl').read_text(encoding='utf8').splitlines()]
out=[]
for row in rows:
 old=parser.parse(row['before_text'],row['path']);newtext=(R/row['path']).read_text(encoding='utf8');new=parser.parse(newtext,row['path']);year=int((R/row['path']).parent.name)
 assert hashlib.sha256(newtext.encode()).hexdigest()==row['after_sha256']
 checked=[]
 for oldn,newn in row['old_to_original_task_map'].items():
  oldn=int(oldn);newn=int(newn);material=old['materials'][oldn].strip()
  if year in [2016,2017,2019]:
   label=('1—2（合并展示）' if newn==1 else str(newn+1)) if year==2019 else str(newn)
   material=re.sub(r'(?m)^材料\s*1\s*$','资料'+label,material,count=1)
  assert new['materials'][newn].strip()==material,(row['path'],oldn,newn,'material body changed')
  revised=next(x for x in row['metrics'] if x['original_number']==newn)['answer_revised']
  if not revised:assert new['answers'][newn]==old['answers'][oldn]
  else:assert old['answers'][oldn] in newtext
  count=validate_answer(new['questions'][newn],{'answer':active_body(new['answers'][newn]),'author':'来源/修订性质已标注','attribution_kind':'retained_reference'})
  checked.append({'original_number':newn,'answer_characters':count,'material_preserved_except_explicit_range_label':True,'unrevised_answer_preserved_or_legacy_retained':True})
 assert sum(row['source_points'])==100
 out.append({'path':row['path'],'status':'passed','source_points':row['source_points'],'tasks':checked})
result={'status':'passed','papers':len(out),'questions':sum(len(x['tasks']) for x in out),'ai_revised_answers':sum(x['answer_revised'] for r in rows for x in r['metrics']),'results':out,'scope':'Every pre-existing material body preserved except explicitly proven material reference labels; existing nonrevised answers byte-preserved within their moved task containers; all seven revised drafts remain in source appendix; current active answers meet actual source word limits.'}
(R/'reports/FULL-REPAIR-GUANGDONG-TOWNSHIP-CONSTRAINTS-VERIFICATION-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ['status','papers','questions','ai_revised_answers']},ensure_ascii=False))
