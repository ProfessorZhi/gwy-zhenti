"""Compare actual named-paper task counts against already retrieved real catalogs.

Never applies a universal four-question rule; old mixed buckets are not papers.
Read-only apart from the independent report.
"""
import sys,json,re,hashlib
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as parser
from priority_essay_inventory_six_regions_20261015 import inventory
AREA={218:'上海',219:'天津',199:'广东',197:'福建',226:'深圳'}
cats=json.loads((R/'tools/data/priority-six-catalog-question-counts-20261015.json').read_text(encoding='utf8'))
def variant(text):
 if '滨海' in text:return '滨海'
 if '行政执法' in text:return '行政执法'
 for x in ['省市','县镇','县级','县乡','乡镇','区级','区县','市区','街镇','市级','公安','通用']:
  if x in text:return x
 for x in ['A','B','一','二']:
  if x in text:return x
 return '单卷'
for x in cats:
 x['area']=AREA[int(parse_qs(urlsplit(x['url']).query)['cid'][0])]
 x['year']=int(x['title'][:4]);x['variant']=variant(x['title'].split('【含解析】')[-1])
rows=[];issues=[]
for x in inventory():
 t=(R/x['path']).read_text(encoding='utf8');d=parser.parse(t,x['path']);n=len(d['questions'])
 v=variant(x['vol']);bucket=x['vol']=='统考'
 if x['area']=='天津' and x['year']==2022 and v=='县级':v='区级'
 if x['area']=='天津' and x['year']==2017 and '__t443' in x['path']:v='滨海';bucket=False
 unique_bucket=(x['area'],x['year']) in {('上海',2026),('广东',2018),('天津',2016),('天津',2017),('天津',2018),('天津',2019),('福建',2016),('福建',2017)}
 if bucket and unique_bucket:v='单卷'
 eligible=not bucket or unique_bucket
 candidates=[c for c in cats if c['area']==x['area'] and c['year']==x['year'] and c['variant']==v] if eligible else []
 counts=sorted(set(c['question_count'] for c in candidates))
 points=[]
 for q in d['questions'].values():
  first=q.split('要求')[0];p=re.findall(r'[（(]\s*(\d+)\s*分\s*[）)]',first);points.append(int(p[-1]) if p else None)
 row={'path':x['path'],'area':x['area'],'year':x['year'],'variant':x['vol'],'actual_question_count':n,'parsed_task_points':points,'parsed_points_sum':sum(points) if all(p is not None for p in points) else None,'catalog_count':counts,'catalog_sources':candidates,'status':'same_count' if counts==[n] else 'catalog_count_mismatch' if counts else 'mixed_bucket_not_compared' if not eligible else 'no_direct_catalog_match','sha256':hashlib.sha256(t.encode()).hexdigest(),'question_keys':{str(k):parser.qkey(v) for k,v in d['questions'].items()}}
 rows.append(row)
 if counts and counts!=[n]:issues.append(row)
out={'date':'2026-10-15','papers_scanned':len(rows),'catalog_entries':len(cats),'confirmed_count_discrepancies':issues,'rows':rows,'method':'Only actual same-year, same-region, same-variant catalog counts. No universal four-question rule; mixed buckets not equated with a complete paper. Matching task counts alone does not certify raw materials or question order.'}
(R/'reports/PRIORITY-ESSAY-QUESTION-COUNT-AUDIT-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'papers':len(rows),'discrepancies':[{'path':x['path'],'actual':x['actual_question_count'],'catalog':x['catalog_count'],'points':x['parsed_points_sum']} for x in issues]},ensure_ascii=False,indent=2))
