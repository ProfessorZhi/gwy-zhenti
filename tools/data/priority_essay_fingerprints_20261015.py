"""Read-only material/question fingerprints; do not treat bucket names as exam types."""
from pathlib import Path
import json,re,unicodedata,difflib,hashlib
from priority_essay_inventory_six_regions_20261015 import inventory,R
def norm(s):
 return re.sub(r'[^\u3400-\u9fffA-Za-z0-9]','',unicodedata.normalize('NFKC',s))
rows=inventory()
for x in rows:
 t=(R/x['path']).read_text(encoding='utf8');part=re.split(r'### 给定材料\s*',t,maxsplit=1)
 m=part[1].split('### 作答要求')[0] if len(part)>1 else (t[re.search(r'(?m)^材料\s*[1一]',t).start():].split('## 作答要求')[0] if re.search(r'(?m)^材料\s*[1一]',t) else '')
 x['material_prefix']=norm(m)[:350];x['material_sha256']=hashlib.sha256(norm(m).encode()).hexdigest()
 x['material_length']=len(norm(m));x['question_count']=len(re.findall(r'(?m)^## 第\s*\d+\s*题',t))
 x['body_sha256']=hashlib.sha256(t.encode()).hexdigest();x.pop('source_meta',None)
for x in rows:
 peers=[y for y in rows if y['area']==x['area'] and y['year']==x['year'] and y['path']!=x['path']]
 x['same_year_material_similarities']=[{'path':y['path'],'prefix_ratio':round(difflib.SequenceMatcher(None,x['material_prefix'],y['material_prefix']).ratio(),3),'identical_material':y['material_sha256']==x['material_sha256']} for y in peers]
(R/'reports/PRIORITY-ESSAY-SIX-REGIONS-FINGERPRINTS-20261015.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for x in rows:
 if x['vol']=='统考':print(x['area'],x['year'],x['path'],x['question_count'],x['material_prefix'][:90],x['same_year_material_similarities'])
