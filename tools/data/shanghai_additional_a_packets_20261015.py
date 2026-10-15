import re,json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
BASE=Path(r'D:\projects\gwy-material-ops\knowledge\gwy\001【公务员国省考】\资料包\【000】历年国省考真题\【省考】2000-2025真题pdf\【24】上海公务员考试真题pdf版\上海公务员考试真题——申论03-24')
out=[]
for year in [2018,2019,2020,2021]:
 p=next(p for p in BASE.glob(str(year)+'*.md') if re.search(r'A[卷类]',p.name));raw=p.read_text(encoding='utf8');t=re.sub(r'<!-- page: (\d+) -->\s*(?:\1(?!\d))?',lambda m:'\n\n',raw)
 if year==2020:t=t.replace('管理模式。材料7','管理模式。\n\n### 材料7')
 qhead=re.search(r'(?m)^##\s*三、作答要求\s*$',t);tail=t[qhead.end():]
 ast=re.search(r'(?m)^\s*20\d\d\s*年上海[^\n]*(?:答案|解析)[^\n]*',tail);assert ast,year
 qtext=tail[:ast.start()];ans=tail[ast.start():]
 if year==2019:qtext=qtext.replace('字问题2','字\n\n问题2')
 qh=list(re.finditer(r'(?m)^(?:（[一二三四]）|[1-4]、|问题[1-4]|##\s*[一二三四]、\s*$)',qtext));assert len(qh)==4,(year,len(qh))
 qs={str(i+1):re.sub(r'^问题[1-4][:：]?','',qtext[m.start():qh[i+1].start() if i+1<4 else len(qtext)].replace('**','').strip()) for i,m in enumerate(qh)}
 mr=t[:qhead.start()];mh=list(re.finditer(r'(?m)^(?:#{1,4}\s*)?(?:给定)?材料\s*(\d+)(?:\(\d+\))?\s*',mr));assert [int(m[1]) for m in mh]==list(range(1,len(mh)+1)),(year,[int(m[1]) for m in mh])
 mats=[dict(number=i+1,text=mr[m.end():mh[i+1].start() if i+1<len(mh) else len(mr)].strip()) for i,m in enumerate(mh)]
 if year in (2018,2019):am=list(re.finditer(r'第([一二三四])题(?:[:：]参考答案|[（(【]参考答案[）)】])',ans));num=lambda m:'一二三四'.index(m[1])+1
 elif year==2021:am=list(re.finditer(r'(?m)^##\s*([一二三四])、参考答案（F）\s*',ans));num=lambda m:'一二三四'.index(m[1])+1
 else:am=list(re.finditer(r'(?:^|(?<=\n)|(?<=）)|(?<=案))\s*(?:#{1,4}\s*)?([1-4])、参考答案[:：]?\s*',ans));num=lambda m:int(m[1])
 aa={}
 for i,m in enumerate(am):
  a=ans[m.end():am[i+1].start() if i+1<len(am) else len(ans)]
  a=re.split(r'(?m)^###\s*参考答案(?:说明[:：]|（H）)',a,1)[0]
  a=re.split(r'(?:#{1,4}\s*)?参考答案（H）',a,1)[0].split('文章分析')[0].strip();a=re.sub(r'(?m)^#{1,4}\s*','',a)
  aa[str(num(m))]=a
 assert sorted(aa)==['1','2','3','4'],(year,list(aa))
 notice=re.search(r'(?s)##\s*一、注意事项\s*(.*?)\s*##\s*二、给定材料',mr)
 d=dict(year=year,variant='A',path='省考/上海/'+str(year)+'/申论-A类.md',source_path=str(p),source_relative_path=p.relative_to(Path(r'D:\projects\gwy-material-ops')).as_posix(),source_sha256=hashlib.sha256(raw.encode()).hexdigest(),instructions=notice[1].strip() if notice else '',materials=mats,questions=qs,source_answers=aa)
 out.append(d);print(year,'materials',len(mats),'answers',[(n,len(re.sub(r'\s','',a))) for n,a in aa.items()])
(ROOT/'tools/data/shanghai-additional-a-full-source-packets-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
