import sys,re,json,difflib,hashlib
from pathlib import Path
sys.path.insert(0,'tools');import round5_bulk as p
R=Path('.');rows=json.loads(Path('reports/PRECISE-SH-GD-TJ-POSTCHECK-20261015.json').read_text(encoding='utf-8'));out=[]
def material(s):
 s=re.sub(r'<!--.*?-->','',s,flags=re.S)
 m=re.search(r'(?m)^(?:#{1,6}\s*)?(?:给定材料|材料[一1][：:]?)',s)
 return s[m.start():].split('## 第')[0].split('### 作答要求')[0] if m else s
for r in rows:
 if '统考' not in r['path']:continue
 d=p.parse(Path(r['path']).read_text(encoding='utf-8'),r['path']);q=d['questions'][r['question_number']];m=material(d['materials'][r['question_number']]);key=p.qkey(q);matches=[]
 for f in Path(r['path']).parent.glob('申论*.md'):
  if f.name=='申论-统考.md':continue
  sd=p.parse(f.read_text(encoding='utf-8'),f.as_posix())
  for n,sq in sd['questions'].items():
   ratio=difflib.SequenceMatcher(None,key,p.qkey(sq),autojunk=False).ratio()
   if ratio<.86:continue
   sm=material(sd['materials'][n]);mn=p.norm(m);sn=p.norm(sm);grams={mn[i:i+12] for i in range(0,max(0,len(mn)-11),16)};sg={sn[i:i+12] for i in range(max(0,len(sn)-11))}
   coverage=len(grams&sg)/max(1,len(grams));matches.append({'path':f.as_posix(),'number':n,'question_ratio':ratio,'material_coverage':coverage,'question':sq,'source_file_sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
 out.append({'path':r['path'],'number':r['question_number'],'question':q,'matches':sorted(matches,key=lambda x:(-x['question_ratio'],-x['material_coverage']))})
Path('reports/PRECISE-SH-GD-TJ-CONSTRAINT-MAPPINGS-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for r in out:print(r['path'],r['number'],[(m['path'],m['number'],round(m['question_ratio'],3),round(m['material_coverage'],3)) for m in r['matches']])
