import sys,json,re,hashlib,subprocess,uuid,os
from pathlib import Path
from urllib.parse import quote
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as b
from paper_integrity_repair import set_fields
from full_repair_answers_20261015 import validate_answer
sha=lambda x:hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
records=[]
base=Path('D:/projects/gwy-material-ops');sp=next((base/'knowledge/gwy').rglob('2018年联考《申论》真题（福建县级卷）及答案.pdf.md'))
rev='95676de3a494730fdcacd43416fd51d6bed48ab6';sr=sp.relative_to(base).as_posix();raw=sp.read_bytes();blob=subprocess.run(['git','show',rev+':'+sr],cwd=base,stdout=subprocess.PIPE,check=True).stdout;assert raw==blob
source=raw.decode('utf8');url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+rev+'/'+quote(sr,safe='/')
rel='省考/福建/2018/申论-县级卷.md';p=R/rel;before=p.read_bytes();old=before.decode('utf8');d=b.parse(old,rel);assert len(d['questions'])==3
sm={int(m.group(1)):m.group(2) for m in re.finditer(r'(?ms)^### 材料([1-5])[^\n]*\n(.*?)(?=^### 材料[1-5]|^作答要求)',source)}
cm={int(m.group(1)):m.group(2) for m in re.finditer(r'(?ms)^材料([1-5])\s*\n(.*?)(?=^材料[1-5]|^## 第 1 题)',old)}
assert len(sm)==5 and len(cm)==5,(sm.keys(),cm.keys())
coverage=[]
for n,t in sm.items():
 t=re.sub(r'<!--.*?-->','',t,flags=re.S);grams=b.shingles(t);norm=b.norm(cm[n]);score=sum(g in norm for g in grams)/max(1,len(grams));assert score>.95,(n,score);coverage.append(dict(number=n,source_material_12gram_coverage=score))
assert old.count('我们才还会')==1 and '我们才不会' in sm[5] and '我们才不会' in source[source.index('### 3、参考答案'):]
new=old.replace('我们才还会','我们才不会')
new=set_fields(new,{'实有题数':3,'对照题本题量':3,'缺失原题号':[],'给定材料段数':5,'题量校核来源':url,'题量校核凭据':'reports/FULL-REPAIR-FUJIAN2018-AND-SHANGHAI-COUNTS-A-20261015.json','分值口径说明':'所据原稿题面未逐题印分值，未据总分反推作文分值。'},'2026-10-15核对完整同卷原稿5材料3任务与字数要求；按材料及同稿解析校勘题干“我们才还会”为“我们才不会”，非官方题本逐字认证。')
new+='\n> 题干异文校勘：原稿任务区与旧录文作“我们才还会”，同卷资料5及作文解析均作“我们才不会”；本次按后两者校正。原异文及全文见校勘凭据。\n'
metrics=[]
for n,q in b.parse(new,rel)['questions'].items():
 a=d['answers'][n];m=re.search(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',a,re.S);assert m;metrics.append(dict(number=n,characters=validate_answer(q,dict(answer=m.group(1),attribution_kind='ai_original',author='AI辅助原创示范',sources=[]))))
records.append(dict(path=rel,before_sha256=sha(before),before_text=old,after_sha256=sha(new),source_commit=rev,source_path=str(sp),source_url=url,source_sha256=sha(raw),source_git_blob_verified=True,material_crosscheck=coverage,questions=3,answers=metrics,changes=['仅校勘题干一个否定词异文和核实题量元数据；5段现有材料、3份完整原创作答及字数要求全部保留'],old_question_variant='我们才还会',verified_material_and_analysis_variant='我们才不会'))
ready=[(p,before,new)]
for year in [2017,2019,2020]:
 rel=f'省考/上海/{year}/申论-行政执法卷.md';p=R/rel;before=p.read_bytes();old=before.decode('utf8');d=b.parse(old,rel);assert len(d['questions'])==3 and len(d['answers'])==3
 url='https://www.kkgwy.com/e/extend/exam/index.php?page='+('2' if year==2017 else '0')+'&cid=218'
 new=set_fields(old,{'实有题数':3,'对照题本题量':3,'缺失原题号':[],'题量校核来源':url,'题量校核凭据':'tools/data/priority-six-catalog-question-counts-20261015.json'},'2026-10-15以同年行政执法真实整卷目录核对共3题；本次仅认证题量相符，不冒称完整官方题本逐字认证。')
 records.append(dict(path=rel,before_sha256=sha(before),before_text=old,after_sha256=sha(new),catalogue_url=url,expected_question_count=3,actual_question_count=3,missing_original_numbers=[],changes=['仅增加已取得真实整卷目录支持的题量保护元数据；题面、材料、答案均不变'],verification_limit='目录证实合法3题；不将3题目测或解析器输出冒充官方全文认证。'))
 ready.append((p,before,new))
for p,before,new in ready:
 tmp=p.with_name(p.name+'.final-a-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());assert p.read_bytes()==before;os.replace(tmp,p);assert sha(p.read_bytes())==sha(new)
out=R/'reports/FULL-REPAIR-FUJIAN2018-AND-SHANGHAI-COUNTS-A-20261015.json';assert not out.exists();out.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps([{k:v for k,v in r.items() if k not in ['before_text']} for r in records],ensure_ascii=False))
