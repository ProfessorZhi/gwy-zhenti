"""Read-only parsing of actual answer details, not just the question region."""
from pathlib import Path
import collections,json,re
import cloud_quality as c
from b_aptitude_content_scan_20261015 import OPT,clean,PRIORITY
ROOT=Path(__file__).resolve().parents[1]
def main():
 rows=[];label=[];paths=sorted([*ROOT.glob('国考/*/行测*.md'),*ROOT.glob('省考/*/*/行测*.md')])
 for p in paths:
  rel=p.relative_to(ROOT).as_posix();t=p.read_text(encoding='utf8');area='国考' if rel.startswith('国考/') else str(c.meta(t).get('地区',''));priority=area in PRIORITY
  for n,raw in c.DETAIL.findall(t):
   text=re.sub(r'!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>','［图片公式］',raw,flags=re.I);text=re.sub(r'<[^>]+>','',text)
   pats=[r'(?<![<>=])(?:=|＝)\s*[，。；]',r'(?:计算可得|代入可得|计算得到|计算得|解得|公式为|结果为|约为|占比为|比重为|增长率为|效率为)[：:]?\s*[，。；]',r'\\frac\s*\{\s*\}|\\frac\s*\{[^}]*\}\s*\{\s*\}',r'\$\s*\$']
   for pattern in pats:
    for m in re.finditer(pattern,text):rows.append({'path':rel,'area':area,'priority':priority,'number':int(n),'pattern':pattern,'evidence':text[max(0,m.start()-150):m.end()+230]})
  for b in c.QBLOCK.finditer(t):
   body=b[2].split('<details>',1)[0].split('**答案**',1)[0];opts=list(OPT.finditer(body));n=int(b[1]);imgs=c.image_refs(body)
   if len(opts)<4 and not imgs:label.append({'path':rel,'area':area,'priority':priority,'number':n,'option_labels':[x[1] for x in opts],'evidence':body[:1200]})
 out={'scope':'453 actual aptitude MD; separately parse answer details and option labels; candidate patterns alone do not establish source loss.','paper_files':len(paths),'formula_candidates':rows,'less_than_four_options_without_local_image':label}
 (ROOT/'reports/FULL-REPAIR-B-APTITUDE-ANSWER-FORMULA-20261015.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'formula_candidates':rows,'less_than_four_options_without_local_image':label},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
