"""Read-only stock inventory for six priority local exam series."""
from pathlib import Path
import re,json
R=Path(__file__).resolve().parents[2]
def inventory():
 out=[]
 for area in ['上海','天津','广东','福建','广州','深圳']:
  for p in (R/'省考'/area).rglob('申论*.md'):
   if not 2016<=int(p.parent.name)<=2026:continue
   t=p.read_text(encoding='utf8');fm=t.split('---',2)[1];vol=re.search(r'(?m)^卷型:\s*(.*)',fm);v=vol[1].strip().strip('"') if vol else '?'
   city='广州' if '广州' in p.name else '深圳' if '深圳' in p.name else area
   out.append({'area':city,'year':int(p.parent.name),'vol':v,'path':p.relative_to(R).as_posix(),'title':next((x.removeprefix('# ') for x in t.splitlines() if x.startswith('# ')),''),'source_meta':fm})
 return sorted(out,key=lambda x:(x['area'],x['year'],x['vol']))
if __name__=='__main__':
 out=inventory()
 print('\n'.join('{area} {year} {vol} | {path}'.format(**x) for x in out))
 (R/'reports/PRIORITY-ESSAY-SIX-REGIONS-STOCK-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
