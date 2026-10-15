import sys,json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
import r7_reference_audit as r
regions=set('上海 云南 内蒙古 吉林 四川 天津 宁夏 安徽 山东 山西 广东 广西 新疆 海南 西藏 重庆 福建 江苏 浙江 深圳'.split())
rows=[]
for top in ('省考','国考'):
 for p in sorted((ROOT/top).rglob('申论*.md')):
  path=p.relative_to(ROOT).as_posix()
  if top=='省考' and p.parts[-3] not in regions:continue
  text=p.read_text(encoding='utf8')
  if '原参考正文' not in text:continue
  d=b.parse(text,path)
  for n,a in d['answers'].items():
   if '原参考正文' not in a:continue
   q=d['questions'][n]
   rows.append(dict(path=path,number=n,question=q,answer=a,main_characters=len(re.sub(r'\s','',r.main_answer(a))),requirement=r.word_range(q),materials=d['materials'][n],before_sha256=hashlib.sha256(text.encode()).hexdigest()))
snapshot=ROOT/'reports/FULL-REPAIR-DECLARED-LENGTH-A-BEFORE-20261015.json'
if not snapshot.exists():snapshot.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for x in rows:print(json.dumps({k:v for k,v in x.items() if k not in ('materials','before_sha256')},ensure_ascii=False))
print('TOTAL',len(rows))
