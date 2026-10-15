import json,re,sys,hashlib,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
BASE=Path(r'D:\projects\gwy-material-ops\knowledge\gwy\001【公务员国省考】\资料包\【000】历年国省考真题\【省考】2000-2025真题pdf\【24】上海公务员考试真题pdf版\上海公务员考试真题——申论03-24');REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
out=[]
for v in ['A','B']:
 p=next(p for p in BASE.glob('2017*.md') if re.search(v+r'[卷类]',p.name));raw=p.read_text(encoding='utf8');rel=p.relative_to(Path(r'D:\projects\gwy-material-ops')).as_posix();blob=subprocess.run(['git','-C',r'D:\projects\gwy-material-ops','show',REV+':'+rel],capture_output=True,check=True).stdout;assert blob==raw.encode(),v
 t=re.sub(r'<!-- page: (\d+) -->\s*(?:\1(?!\d))?',lambda m:'\n\n',raw);qh=re.search(r'(?m)^## 三、作答要求\s*$',t);tail=t[qh.end():];ast=re.search(r'(?m)^2017\s*年上海.*答案.*$',tail);assert ast
 qreg=tail[:ast.start()];ans=tail[ast.start():];hs=list(re.finditer(r'(?m)^（([一二三四])）',qreg));assert len(hs)==4
 qs={str(i+1):qreg[m.start():hs[i+1].start() if i+1<4 else None].replace('**','').strip() for i,m in enumerate(hs)}
 mr=t[:qh.start()];ms=list(re.finditer(r'(?m)^### 材料(\d+)\s*$',mr));assert [int(m[1]) for m in ms]==list(range(1,len(ms)+1));mats=[dict(number=i+1,text=mr[m.end():ms[i+1].start() if i+1<len(ms) else None].strip()) for i,m in enumerate(ms)]
 am=list(re.finditer(r'(?m)^## ([一二三四])、参考答案\s*$',ans));assert len(am)==4;aa={}
 for i,m in enumerate(am):
  a=ans[m.end():am[i+1].start() if i+1<4 else None].strip();a=re.split(r'文章分析|参考答案说明[:：]',a,1)[0];aa[str(i+1)]=a.strip()
 notice=re.search(r'(?s)## 一、注意事项\s*(.*?)\s*## 二、给定材料',mr)
 out.append(dict(year=2017,variant=v,path='省考/上海/2017/申论-'+v+'类.md',source_path=str(p),source_relative_path=rel,source_revision=REV,source_sha256=hashlib.sha256(blob).hexdigest(),instructions=notice[1].strip() if notice else '',materials=mats,questions=qs,source_answers=aa))
 print(v,'materials',len(mats),'answers',[(n,len(re.sub(r'\s','',a))) for n,a in aa.items()])
 for n,a in aa.items():
  if (n!='4' and len(re.sub(r'\s','',a))>300) or n=='4':print(n,a)
(ROOT/'tools/data/shanghai-2017-full-source-packets-a-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
