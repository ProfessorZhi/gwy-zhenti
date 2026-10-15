from pathlib import Path
import sys,json,re,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
import r7_reference_audit as r
targets={'e314955c7be0ba5b','f60d072d7f85e549'}
found=[]
for year in (2019,2022):
 for p in sorted((ROOT/'省考/江苏'/str(year)).glob('申论*.md')):
  d=b.parse(p.read_text(encoding='utf8'),p.relative_to(ROOT).as_posix())
  for n,q in d['questions'].items():
   fp=r.fingerprint(q)
   if fp not in targets:continue
   a=d['answers'].get(n,'')
   if r.assess(q,a)['status']=='已收录':continue
   entry={'path':d['path'],'number':n,'fingerprint':fp,'question':q,'materials':d['materials'][n],'old_answer':a}
   found.append(entry)
   print(json.dumps({'path':d['path'],'number':n,'question':q,'answer':a,'materials':d['materials'][n]},ensure_ascii=False))
snapshot=ROOT/'reports/FULL-REPAIR-SHORT-ESSAY-A-BEFORE-20261015.json'
if not snapshot.exists():snapshot.write_text(json.dumps(found,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
