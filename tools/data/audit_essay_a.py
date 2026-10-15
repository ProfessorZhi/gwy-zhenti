import sys,json,re,hashlib,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_repair_essay_a_20261015 import ROOT,OUT
from full_repair_answers_20261015 import pending,validate_answer
import round5_bulk
areas='上海 云南 内蒙古 吉林 四川 天津 宁夏 安徽 山东 山西 广东 广西 新疆 海南 西藏 重庆 福建'.split()
rows=json.loads(OUT.read_text(encoding='utf8'));missing=[];bad=[];checked=[];count=0
for area in areas:
 for p in (ROOT/'省考'/area).glob('*/申论*.md'):
  t=p.read_text(encoding='utf8');rel=p.relative_to(ROOT).as_posix()
  try:
   d=round5_bulk.parse(t,rel)
   for n,q in d['questions'].items():
    count+=1
    if pending(d['answers'].get(n,'')):missing.append({'path':rel,'number':n,'question':q})
  except Exception as e:bad.append({'path':rel,'reason':str(e)})
for e in rows:
 t=(ROOT/e['path']).read_text(encoding='utf8');d=round5_bulk.parse(t,e['path'])
 n=validate_answer(d['questions'][e['number']],e)
 e['answer_characters']=n
 assert e['answer'] in d['answers'][e['number']],(e['path'],e['number'])
 checked.append({'path':e['path'],'number':e['number'],'characters':n,'attribution_kind':e['attribution_kind'],'answer_sha256':hashlib.sha256(e['answer'].encode()).hexdigest()})
result={'scope_areas':areas,'answers_delivered':len(rows),'delivered_papers':len({e['path'] for e in rows}),'authorship_counts':dict(collections.Counter(e['attribution_kind'] for e in rows)),'parsed_task_positions':count,'missing':missing,'unparsed':bad,'answers':checked}
(ROOT/'reports/FULL-REPAIR-ESSAY-A-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='answers'},ensure_ascii=False,indent=2))
