"""Compare every historical bucket task to full named papers, including materials."""
import json,sys,hashlib,re
from pathlib import Path
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
rows=[]
for year in [2016,2017,2018,2019,2020,2021,2022,2023]:
 bucket=ROOT/'省考/上海'/str(year)/'申论-统考.md';source=bucket
 if not source.exists():source=ROOT/'docs/来源校勘'/('上海'+str(year)+'申论-原统考混合或重复来源.md')
 text=source.read_text(encoding='utf8');d=b.parse(text,bucket.relative_to(ROOT).as_posix());named=[]
 for p in bucket.parent.glob('申论*.md'):
  if p==bucket:continue
  t=p.read_text(encoding='utf8');named.append(b.parse(t,p.relative_to(ROOT).as_posix()))
 tasks=[]
 for n,q in d['questions'].items():
  kk=b.qkey(q);c=[];grams=b.shingles(d['materials'][n])
  for other in named:
   for nn,qq in other['questions'].items():
    sim=SequenceMatcher(None,kk,b.qkey(qq),autojunk=False).ratio()
    if sim<.9:continue
    nt=b.norm(other['materials'][nn]);coverage=sum(g in nt for g in grams)/max(1,len(grams))
    c.append(dict(path=other['path'],number=nn,question_similarity=round(sim,6),bucket_material_12gram_coverage=round(coverage,6),named_material_sha256=hashlib.sha256(other['materials'][nn].encode()).hexdigest()))
  tasks.append(dict(bucket_number=n,question=q,bucket_material_sha256=hashlib.sha256(d['materials'][n].encode()).hexdigest(),candidates=sorted(c,key=lambda x:(-x['question_similarity'],-x['bucket_material_12gram_coverage']))))
 rows.append(dict(year=year,bucket_path=d['path'],read_source_path=source.relative_to(ROOT).as_posix(),already_archived=source!=bucket,read_source_sha256=hashlib.sha256(text.encode()).hexdigest(),bucket_tasks=len(tasks),tasks=tasks,unmapped_tasks=[t['bucket_number'] for t in tasks if not t['candidates']]))
out=dict(date='2026-10-15',method='全部任务题干相似度和逐任务材料12字片段覆盖，未用首句替代全卷对照',old_bucket_mutated=False,rows=rows,note='A/B/执法混题桶不是单独真实分卷。归档必须保留源文与可审计逐题去向；该文件不执行归档。2023旧桶唯一作文只映射A第4题，不能充B覆盖。')
(ROOT/'reports/FULL-REPAIR-SHANGHAI-BUCKET-MAP-A-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for r in rows:
 print(r['year'],'unmapped',r['unmapped_tasks'])
 for t in r['tasks']:print(t['bucket_number'],[(x['path'].split('/')[-1],x['number'],x['question_similarity'],x['bucket_material_12gram_coverage']) for x in t['candidates']])
