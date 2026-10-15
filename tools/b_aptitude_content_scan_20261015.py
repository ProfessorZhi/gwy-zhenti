"""Read-only content-gap candidates, independent of image byte readability."""
from pathlib import Path
import collections,html,json,re
import cloud_quality as c
ROOT=Path(__file__).resolve().parents[1]
PRIORITY={'国考','北京','天津','江苏','浙江','上海','广东','广州','深圳','福建'}
OPT=re.compile(r'(?m)^\s*(?:[-*]\s+)?(?:\*\*)?([A-G])(?:\*\*)?\s*[.．、:：](?:\*\*)?\s*')
def clean(s):
 s=re.sub(r'!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>','',s,flags=re.I)
 s=re.sub(r'<[^>]+>','',s);s=re.sub(r'<!--.*?-->','',s,flags=re.S)
 return re.sub(r'\s|[*`#]','',html.unescape(s))
def main():
 paths=sorted([*ROOT.glob('国考/*/行测*.md'),*ROOT.glob('省考/*/*/行测*.md')]);zero=[];rows=[];allstats=[]
 for p in paths:
  rel=p.relative_to(ROOT).as_posix();t=p.read_text(encoding='utf8');fm=c.meta(t);area='国考' if rel.startswith('国考/') else str(fm.get('地区',''));priority=area in PRIORITY or '广州市考' in str(fm.get('考试系列',''))
  imgs=c.image_refs(t);blocks=list(c.QBLOCK.finditer(t));stats={'path':rel,'area':area,'priority':priority,'questions':len(blocks),'image_references':len(imgs),'graph_questions':[],'data_questions':[],'explicit_image_dependent_questions':[]};allstats.append(stats)
  for block in blocks:
   n=int(block[1]);raw=block[2];body=raw.split('<details>',1)[0].split('**答案**',1)[0];localimgs=c.image_refs(body);plain=clean(body);kind=re.search(r'<sub>(.*?)</sub>',block[0][:200]);kind=kind[1] if kind else ''
   if '图形推理' in kind:stats['graph_questions'].append(n)
   if '资料分析' in kind:stats['data_questions'].append(n)
   dependent=bool(re.search(r'如[下右左上]?图|图[中示]|下(?:面|列)的?图形|图形规律|四个选项中选出最恰当的|问号处|方框[内中]|折叠.*立方|立方体.*展开图|根据[下右左上]?图|根据[下右左上]?表|表中数据',body))
   if dependent:stats['explicit_image_dependent_questions'].append(n)
   def add(rule,evidence,confidence='candidate'):rows.append({'path':rel,'area':area,'priority':priority,'number':n,'kind':kind,'rule':rule,'confidence':confidence,'local_image_references':len(localimgs),'paper_image_references':len(imgs),'evidence':evidence[:500]})
   if not imgs and ('图形推理' in kind or dependent):add('zero_image_paper_with_visual_dependency',body[:420],'high' if '图形推理' in kind else 'candidate')
   if dependent and not localimgs and len(plain)<220:add('visual_dependency_without_local_image_short_stem',body[:420])
   options=list(OPT.finditer(body))
   for i,m in enumerate(options):
    s=body[m.end():options[i+1].start() if i+1<len(options) else len(body)].strip();s=s.split('\n## ',1)[0]
    ss=clean(s)
    if not ss and not c.image_refs(s):add('empty_option',m.group(1)+': '+repr(s),'high')
    elif re.fullmatch(r'(?:[%％‰°度元万元亿元人户个件倍吨千克克米厘米千米平方公里平方米立方米小时分钟秒年月日]|cm|km|kg|m|m²|m³|\d?\s*\[\]){1,12}',ss) and not c.image_refs(s):add('unit_only_option',m.group(1)+': '+s,'high')
   for m in re.finditer(r'(?:=[ \t]*[，。；]|[（(][ \t]*[）)]\s*[×÷=]|\\frac\s*\{\s*\}|\$\s*\$|(?:计算可得|代入可得|计算得|计算得到|公式为|公式可得)[：:]?[ \t\r\n]*[，。；])',raw):
    context=raw[max(0,m.start()-100):m.end()+120]
    if not c.image_refs(context):add('possible_missing_formula',context)
  if not imgs:zero.append(stats)
 out={'scope':'All current aptitude MD text. Candidates require human source/context review; zero images alone is not a defect. Shared preceding materials may legitimately serve multiple question blocks.','paper_files':len(paths),'zero_image_papers':zero,'candidates':rows,'paper_stats':allstats,'candidate_counts':dict(collections.Counter(r['rule'] for r in rows))}
 (ROOT/'reports/FULL-REPAIR-B-APTITUDE-CONTENT-SCAN-20261015.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'paper_files':len(paths),'zero_image_papers':zero,'candidate_counts':out['candidate_counts'],'priority_candidates':[r for r in rows if r['priority']]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
