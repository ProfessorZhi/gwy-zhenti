"""Restore proved constraints only, retaining exact old task stems and materials."""
import sys,json,re,hashlib,copy
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,'tools');import round5_bulk as p,full_repair_precise_answer_audit_20261015 as a,full_repair_answers_20261015 as app
R=Path('.');sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
rows=json.loads(Path('reports/PRECISE-SH-GD-TJ-CONSTRAINT-MAPPINGS-20261015.json').read_text(encoding='utf-8'))
plans=[]
for r in rows:
 if not r['matches']:continue
 m=r['matches'][0];assert m['material_coverage']>=.97,(r,m)
 old=(R/r['path']).read_text(encoding='utf-8');d=p.parse(old,r['path']);q=d['questions'][r['number']]
 req=re.split(r'要求\s*[：:]',m['question'],maxsplit=1)[1];req=re.sub(r'<!--.*?-->','',req,flags=re.S).strip()
 assert a.word_rules('要求：'+req)['kind']!='unspecified'
 plans.append({**r,'source':m,'requirements':'要求：\n'+req,'before_text':old,'question_before':q})
base=Path(r'D:\projects\gwy-material-ops\knowledge\gwy');src=base/'001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【05】广东公务员考试真题pdf版/广东公务员考试真题——申论03-24/2018年广东公务员考试《申论》真题及答案.pdf.md'
s=src.read_text(encoding='utf-8');req='要求：\n1.主题鲜明，对策合理、有针对性；\n2.条理清晰，论证严密、合乎逻辑；\n3.结构完整，表达准确，行文流畅；\n4.篇幅在800—1000字。'
assert '篇幅在800—1000 字' in s and '人才在推动经济社会发展' in s
rel='省考/广东/2018/申论-统考.md';old=Path(rel).read_text(encoding='utf-8');d=p.parse(old,rel);q=d['questions'][1]
assert '人才在推动经济社会发展' in q and '国以才立' in s and '国以才立' in old
plans.append({'path':rel,'number':1,'requirements':req,'before_text':old,'question_before':q,'source':{'path':str(src),'sha256':sha(s),'pinned_commit':'95676de3a494730fdcacd43416fd51d6bed48ab6','url':'https://github.com/ProfessorZhi/gwy-material-ops/blob/95676de3a494730fdcacd43416fd51d6bed48ab6/'+quote(src.relative_to(base.parent.parent).as_posix(),safe='/'),'identity_note':'同题主题、同年卷别、给定材料首段国以才立及技工教育/技工世赛/人才短缺段落对应；源为3题，当前桶是原题3的独立位置。'}})
rel='省考/上海/2026/申论-统考.md';old=Path(rel).read_text(encoding='utf-8');d=p.parse(old,rel);q=d['questions'][4];ev=json.loads(Path('tools/data/shanghai-2026-essay-requirements-evidence-20261015.json').read_text(encoding='utf-8'))
assert '高水平开放，高质量发展' in q and '总字数800-1000字' in ev['question_and_requirements']
plans.append({'path':rel,'number':4,'requirements':'要求：\n（1）自选角度，自拟题目；\n（2）观点明确，联系实际，分析具体，条理清楚，语言流畅；\n（3）总字数800-1000字。','before_text':old,'question_before':q,'source':ev})
pre={x['path']:x['before_text'] for x in plans};out={}
for rel,old in pre.items():
 text=old;d=p.parse(old,rel)
 for item in sorted([x for x in plans if x['path']==rel],key=lambda x:d['question_spans'][x['number']],reverse=True):
  n=item['number'];at=d['question_spans'][n];end=min([x for x in d['question_spans'].values() if x>at]+[d['answer_heading'] if isinstance(d['answer_heading'],int) and d['answer_heading']>at else len(old)])
  # Scope replacement to exact task string, preserving heading/anchors and every stem character.
  q=item['question_before'];assert text.count(q)==1
  newq=re.sub(r'要求\s*[：:]\s*$',item['requirements'],q)
  assert newq!=q and p.qkey(newq)==p.qkey(q),(rel,n,q)
  text=text.replace(q,newq,1);item['question_after']=newq
 before=p.parse(old,rel);after=p.parse(text,rel)
 assert before['materials']==after['materials'];assert before['answers']==after['answers']
 out[rel]=text
# Persist all preimages before writing any paper.
Path('reports/PRECISE-SH-GD-TJ-CONSTRAINT-REPAIRS-20261015.json').write_text(json.dumps({'status':'prepared','plans':plans},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for rel,text in out.items():
 assert Path(rel).read_text(encoding='utf-8')==pre[rel];Path(rel).write_text(text.rstrip()+'\n',encoding='utf-8',newline='')
report={'status':'passed','restored_tasks':len(plans),'papers':len(out),'plans':plans,'checks':[{'path':rel,'before_sha256':sha(pre[rel]),'after_sha256':sha(Path(rel).read_text(encoding='utf-8')),'materials_and_answers_unchanged':True} for rel in out]}
Path('reports/PRECISE-SH-GD-TJ-CONSTRAINT-REPAIRS-20261015.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('CONSTRAINTS',len(plans),len(out))
