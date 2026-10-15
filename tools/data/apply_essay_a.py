import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_repair_essay_a_20261015 import ROOT,OUT
from full_repair_answers_20261015 import apply_entries,validate_answer
from r7_reference_audit import word_range
import round5_bulk
rows=json.loads(OUT.read_text(encoding='utf8'));pending=[];errors=[]
for e in rows:
 t=(ROOT/e['path']).read_text(encoding='utf8');d=round5_bulk.parse(t,e['path']);q=d['questions'][e['number']]
 if not e.get('question'):e['question']=q
 e['target_word_range']=list(word_range(q))
 try:validate_answer(q,e)
 except Exception as x:errors.append({'path':e['path'],'number':e['number'],'error':str(x)})
 if e['answer'] not in d['answers'].get(e['number'],''):pending.append(e)
OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
if errors:print(json.dumps(errors,ensure_ascii=False,indent=2));raise SystemExit(1)
check='--check' in sys.argv
result,receipts=apply_entries(ROOT,pending,write=not check)
if not check and result['status']=='passed':
 rp=ROOT/'reports/FULL-REPAIR-ESSAY-A-20261015.jsonl'
 old=rp.read_text(encoding='utf8') if rp.exists() else ''
 rp.write_text(old+''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in receipts),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(result['status']!='passed')
