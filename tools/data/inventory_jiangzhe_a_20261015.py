"""Read-only Jiangsu/Zhejiang variant and bucket inventory; no exam content edit."""
import sys,json,re,hashlib
from pathlib import Path
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as g
rows=[]
for region in ['江苏','浙江']:
 for year in range(2016,2027):
  ds=[]
  for p in sorted((ROOT/'省考'/region/str(year)).glob('申论*.md')):
   txt=p.read_text(encoding='utf8');d=g.parse(txt,p.relative_to(ROOT).as_posix())
   ds.append((p,d,txt))
  named=[(p,d,t) for p,d,t in ds if '统考' not in p.stem]
  files=[]
  for p,d,t in ds:
   matches=[]
   if '统考' in p.stem:
    for n,q in d['questions'].items():
     key=g.qkey(q);cand=[]
     for pp,dd,tt in named:
      for nn,qq in dd['questions'].items():
       kk=g.qkey(qq);sim=1 if key==kk else SequenceMatcher(None,key,kk,autojunk=False).ratio()
       if sim>=.80:
        bs=g.shingles(d['materials'][n]);ns=g.shingles(dd['materials'][nn])
        cand.append({'path':pp.relative_to(ROOT).as_posix(),'number':nn,'similarity':round(sim,4),'bucket_material_shingle_coverage':round(len(bs&ns)/max(1,len(bs)),4)})
     matches.append({'bucket_number':n,'question_excerpt':q[:220],'matching_named_tasks':sorted(cand,key=lambda x:-x['similarity'])[:3]})
   field=lambda key:next(iter(re.findall(r'(?m)^'+re.escape(key)+r':\s*(.+)$',t)),None)
   files.append({'path':p.relative_to(ROOT).as_posix(),'variant':d['variant'],'questions':len(d['questions']),'missing_answers':d['missing'],'sha256':hashlib.sha256(t.encode()).hexdigest(),'source_title':field('源标题'),'source_url':field('来源整卷') or field('源链接') or field('题源链接'),'source':field('来源'),'bucket_comparison':matches})
  expected=['A','B','C'] if region=='江苏' or year>=2021 else ['A','B']
  present=[]
  for pp,dd,tt in named:
   for v in expected:
    if re.search(r'(?:申论-|[（(])'+v,pp.stem):present.append(v)
  rows.append({'region':region,'year':year,'expected_variants':expected,'present_named_variants':sorted(set(present)),'missing_named_variants':sorted(set(expected)-set(present)),'files':files})
evidence={
 '江苏2016':{'url':'http://www.jsgkw.org/2016/0314/12379.html','kind':'同年公共科目大纲转载','finding':'A/B/C三类每类均考行测与申论；选调借用A或C不另计省考卷'},
 '江苏2026':{'url':'https://www.suzhou.gov.cn/szsrmzf/gwyjsydwklxx/202510/5db8eab43b324856be70dc743b7fa4c6.shtml','kind':'市政府发布同年官方考试大纲','finding':'A/B/C三类均有申论；乡镇选调同A不新增第四张卷'},
 '浙江2016':{'url':'http://zjgzks.com/news/113.html','kind':'2016-03-01三部门大纲转载','finding':'申论只有A/B；行政执法考综合应用能力(一)，不能因行测C存在而制造申论C'},
 '浙江2021':{'url':'http://www.zggwy.org/zjgwy/448052.html','kind':'2022-11-18历史考情回溯，与库中2021ABC整卷互证','finding':'明述2017–2020申论A/B，2021新增行政执法C；优秀村干部D实考综合应用能力'},
 '浙江2022':{'url':'https://gx.huatu.com/2021/1101/1772759.html','kind':'浙江省公务员局2021-11-01同年大纲机构转载','finding':'综合A、基层B、执法C为申论；D为行测D+综合应用能力'}
}
for r in rows:
 for f in r['files']:
  if '统考' not in f['path'] and f['source_url']:
   f['variant_identity_basis']='文件指向的同年同卷整卷机构来源；非官方逐字认证'
 r['year_identity_basis']=[evidence[k] for k in (['江苏2016','江苏2026'] if r['region']=='江苏' else ['浙江2016','浙江2021','浙江2022'])]
 r['year_identity_limitation']='中间年度卷型同时据现有同年分卷来源映射；未逐年取得全部官方原始纸卷。桶仅按题干相似与材料片段覆盖映射，不能替代真实分卷完整性认证。'
out={'date':'2026-10-15','scope':'2016–2026 江苏浙江真实省考申论分卷；优秀村干部综合应用能力不冒称申论D','method':'读取每年全部分卷和统考桶；逐题比较题干与12字材料片段；保留文件哈希和原始卷型标签','expected_real_variants':61,'named_variant_files':sum(len(r['present_named_variants']) for r in rows),'missing_real_variants':sum(len(r['missing_named_variants']) for r in rows),'bucket_files':sum('统考' in f['path'] for r in rows for f in r['files']),'rows':rows}
(ROOT/'reports/FULL-REPAIR-JIANGZHE-VARIANT-INVENTORY-A-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for r in rows:
 print(r['region'],r['year'],'expected',r['expected_variants'],'missing',r['missing_named_variants'])
 for f in r['files']:
  if f['bucket_comparison']:
   print(' BUCKET',f['questions'],[(x['bucket_number'],[(z['path'].split('/')[-1],z['number'],z['similarity']) for z in x['matching_named_tasks']]) for x in f['bucket_comparison']])
