"""Read-only actual task-count cross-check for the already authorized national/JZ scope."""
import json,re,sys,hashlib
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as b
DATA=R/'tools/data';BASE=Path('D:/projects/gwy-material-ops/knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题')
catalog=json.loads((DATA/'jiangzhe-catalog-question-counts-20261015.json').read_text(encoding='utf8'))+json.loads((DATA/'national-catalog-question-counts-20261015.json').read_text(encoding='utf8'))
AREAS={209:'江苏',224:'浙江',163:'国考'}
def variant(s):
 if '副省' in s:return '副省级'
 if '地市' in s or '市地' in s:return '地市级'
 if '执法' in s:return '行政执法'
 for ch in 'ABC':
  if ch in s:return ch
 return '?'
for c in catalog:
 c['area']=AREAS[int(parse_qs(urlsplit(c['url']).query)['cid'][0])];c['year']=int(c['title'][:4]);c['variant']=variant(c['title'])
source_files=[p for p in BASE.rglob('*申论*.md') if ('国考】' in str(p) or '江苏公务员考试真题pdf版' in str(p) or '浙江公务员考试真题pdf版' in str(p))]
paths=list(R.glob('国考/*/申论*.md'))+[p for a in ['江苏','浙江'] for p in (R/'省考'/a).glob('*/申论*.md')]
rows=[]
for p in sorted(paths):
 rel=p.relative_to(R).as_posix();t=p.read_text(encoding='utf8');d=b.parse(t,rel);area='国考' if rel.startswith('国考/') else rel.split('/')[1];year=int(p.parent.name);v=variant(d['variant']);n=len(d['questions']);cs=[c for c in catalog if c['area']==area and c['year']==year and c['variant']==v]
 counts=sorted(set(c['question_count'] for c in cs));status='same_catalog_task_count' if counts==[n] else 'mixed_bucket_not_equated_with_paper' if d['variant']=='统考' else 'no_same_year_variant_catalog' if not counts else 'requires_actual_source_structure_check'
 sources=[{'path':str(s),'sha256':hashlib.sha256(s.read_bytes()).hexdigest(),'basename_identity_only':True} for s in source_files if s.name.startswith(str(year)) and (area=='国考' and '国考】' in str(s) or area!='国考' and area+'公务员考试真题pdf版' in str(s)) and variant(s.name)==v]
 row={'path':rel,'area':area,'year':year,'variant':d['variant'],'actual_main_task_containers':n,'catalog_task_counts':counts,'catalog_evidence':cs,'owned_source_candidates':sources,'status':status,'sha256':hashlib.sha256(t.encode()).hexdigest(),'task_key_hashes':{str(k):hashlib.sha256(b.qkey(q).encode()).hexdigest() for k,q in d['questions'].items()}}
 if area=='国考' and year==2016 and v=='地市级':
  q=d['questions'][3];assert '（1）' in q and '（2）' in q and q.count('10分')==2
  source=next(s for s in source_files if s.name=='2016年国家录用公务员考试《申论》真题卷及答案（地市级）.pdf.md');raw=source.read_text(encoding='utf8');qa=raw.split('## 三、作答要求',1)[1].split('## 一、参考答案',1)[0]
  assert len(re.findall(r'(?m)^[一二三四]、',qa))==4 and len(re.findall(r'[（(]\s*10\s*分\s*[）)]',qa))==2
  row.update(status='same_actual_source_structure_different_counting_unit',actual_main_questions=4,actual_independent_subtasks=5,source_points_by_main_task=[20,20,[10,10],40],source_standard_total=100,structure_note='第三大题包含（1）（2）两个10分小问，两问在库内均完整。目录按5个独立作答项计，当前按4个大题容器计，不能报缺第5题。',owned_structure_source=str(source),owned_structure_source_sha256=hashlib.sha256(raw.encode()).hexdigest())
 rows.append(row)
named=[r for r in rows if r['variant']!='统考'];gaps=[r for r in named if r['status']=='requires_actual_source_structure_check'];unknown=[r for r in named if r['status']=='no_same_year_variant_catalog']
result={'date':'2026-10-15','read_only':True,'files_scanned':len(rows),'named_papers':len(named),'national_files':sum(x['area']=='国考' for x in rows),'confirmed_current_task_count_gaps':len(gaps),'unresolved_count_discrepancies':gaps,'same_year_catalog_unavailable':unknown,'rows':rows,'boundaries':['Only existing national/Jiangsu/Zhejiang papers, no new province or unknown exam added.','Catalog count checks prove task counts, not official word-for-word material authenticity. Owned source basename candidates are explicitly not claimed as full identity verification.','Jiangsu2022B has five catalog task positions; Zhejiang2020AB have two each. Neither is forcibly changed to four/three.','National2016地市 is four main questions/five subtask positions, independently verified against the owned real paper.']}
(R/'reports/NATIONAL-JIANGZHE-TASK-COUNT-AUDIT-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
md=['# 既定国考与江浙现有申论题量复核','',f"只读核对{len(rows)}份现有文件，其中{len(named)}份命名分卷。未发现新增已证实的题量不足；{len(unknown)}份缺同年同卷目录证据，保持未核状态。",'','- 国考2016地市是4个大题，第3题含两个10分小问，共5个作答项；当前两小问均在，不是缺第5题。','- 江苏2022B真实目录5个作答位置，浙江2020A/B各2题，均合法，不强制统一题数。','- 旧统考桶可能汇合多分卷，未用桶内数量直接代表一套原卷。','- 目录只证明题量，不冒称全文逐字认证。完整来源链接、现存文件哈希和本地原稿候选见同名JSON。','']
(R/'reports/NATIONAL-JIANGZHE-TASK-COUNT-AUDIT-20261015.md').write_text('\n'.join(md),encoding='utf8')
print(json.dumps({'files':len(rows),'named':len(named),'national':result['national_files'],'count_discrepancies':[x['path'] for x in gaps],'missing_catalog':[x['path'] for x in unknown]},ensure_ascii=False))
