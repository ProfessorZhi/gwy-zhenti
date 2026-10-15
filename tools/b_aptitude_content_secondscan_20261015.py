"""Read-only second pass for visual type and common-data dependencies."""
from pathlib import Path
import collections,json,re
import cloud_quality as c
from b_aptitude_content_scan_20261015 import OPT,clean,PRIORITY
ROOT=Path(__file__).resolve().parents[1]
def main():
 paths=sorted([*ROOT.glob('国考/*/行测*.md'),*ROOT.glob('省考/*/*/行测*.md')]);rows=[]
 for idx,p in enumerate(paths):
  rel=p.relative_to(ROOT).as_posix();t=p.read_text(encoding='utf8');fm=c.meta(t);area='国考' if rel.startswith('国考/') else str(fm.get('地区',''));priority=area in PRIORITY or '广州市考' in str(fm.get('考试系列',''));blocks=list(c.QBLOCK.finditer(t))
  for i,block in enumerate(blocks):
   n=int(block[1]);raw=block[2];body=raw.split('<details>',1)[0].split('**答案**',1)[0];localimgs=c.image_refs(body);kind=re.search(r'<sub>(.*?)</sub>',block[0][:200]);kind=kind[1] if kind else '';opts=list(OPT.finditer(body));stem=body[:opts[0].start()] if opts else body
   def add(rule,evidence):rows.append({'path':rel,'area':area,'priority':priority,'number':n,'kind':kind,'rule':rule,'local_image_references':len(localimgs),'evidence':evidence[:900]})
   if re.search(r'图形推理|图形判断',kind) and not localimgs:add('graph_type_no_local_image',body)
   if '资料分析' in kind and not localimgs and len(clean(stem))<170:
    add('data_short_question_no_local_material',body)
   for m in re.finditer(r'(?:[（(]\s*[）)]|[，。：:；]\s*(?:×|÷|=)|(?:=|约为|计算可得|代入可得|计算得到|应为)[：:]?\s*(?:[，。；]|</p>))',raw):
    context=raw[max(0,m.start()-85):m.end()+100]
    if '![img]' in context or c.image_refs(context):continue
    if re.search(r'得到|计算|解得|可得|方程|公式|代入|\d\s*[=×÷]|^\s*[=×÷]|比重|增长率',context):add('formula_context_needs_review',context)
   # Explicit known / unknown loss notices, including sources' own textual gaps.
   for m in re.finditer(r'(?:图[片形表]|题[干面图]|资料|条件|选项|公式)[^。\n]{0,18}(?:缺失|残缺|暂缺|未提供|无法(?:显示|辨认)|识别失败)|(?:缺失|残缺|暂缺)[^。\n]{0,18}(?:图[片形表]|题[干面图]|资料|条件|选项|公式)',body):add('explicit_content_gap_notice',body[max(0,m.start()-100):m.end()+180])
  if idx%50==0:print('read',idx+1,rel,flush=True)
 out={'scope':'Second text-only candidate pass; shared data must be checked in preceding blocks/section headers. No files changed.','paper_files':len(paths),'candidate_counts':dict(collections.Counter(r['rule'] for r in rows)),'candidates':rows}
 (ROOT/'reports/FULL-REPAIR-B-APTITUDE-CONTENT-SECOND-20261015.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'counts':out['candidate_counts'],'priority_candidates':[r for r in rows if r['priority']]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
