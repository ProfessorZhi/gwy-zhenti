"""Prepare explicit full-source Shanghai B packets, preserving supplied transcripts."""
import json,re,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer
BASE=Path(r'D:\projects\gwy-material-ops\knowledge\gwy\001【公务员国省考】\资料包\【000】历年国省考真题\【省考】2000-2025真题pdf\【24】上海公务员考试真题pdf版\上海公务员考试真题——申论03-24')
packets=[]
for year in [2018,2019,2020,2021,2022,2023]:
 variant='A' if year==2023 else 'B'
 source=next(p for p in BASE.glob(str(year)+'*.md') if re.search(variant+r'[卷类]',p.name));raw=source.read_text(encoding='utf8');t=raw
 # The extracted PDF page number, when present, directly follows its page marker.
 t=re.sub(r'<!-- page: (\d+) -->\s*(?:\1(?!\d))?',lambda m:'\n\n',t)
 t=re.sub(r'上岸真题库更多真题：https://www\.saztk\.com/61_80\.html\s*9','',t)
 if year==2019:t=t.replace('先河.材料3','先河。\n\n### 材料3')
 if year==2023:t=t.replace('材料1(346680)总括材料','## 总括资料\n\n')
 qhead=re.search(r'(?m)^##\s*[二三]、作答要求\s*$',t);assert qhead,year
 tail=t[qhead.end():];astart=re.search(r'(?m)^\s*20\d\d\s*年上海[^\n]*(?:答案|解析)[^\n]*',tail);assert astart,year
 qs=tail[:astart.start()].strip();at=tail[astart.start():]
 if year==2023:qh=list(re.finditer(r'(?m)^##\s*[一二三四]、\s*$',qs))
 elif year==2022:qh=list(re.finditer(r'(?m)^(?:结合给定资料|阅读但不拘泥于给定资料)',qs))
 elif year==2019:qh=list(re.finditer(r'(?m)^问题[1-4]：',qs))
 else:qh=list(re.finditer(r'(?m)^（[一二三四]）',qs))
 assert len(qh)==4,(year,len(qh))
 questions={i+1:qs[m.start():qh[i+1].start() if i+1<4 else len(qs)].replace('**','').strip() for i,m in enumerate(qh)}
 if year==2023:questions={n:re.sub(r'^##\s*[一二三四]、\s*','',q).strip() for n,q in questions.items()}
 if year==2019:questions[4]=questions[4].replace('海纳百川是上海城市精神内容','海纳百川是上海城市精神的重要内容').replace('“契约精神与海纳”','“契约精神与海纳百川”').replace('语音流程','语言流畅')
 material_region=t[:qhead.start()]
 mids=list(re.finditer(r'(?m)^(?:#{1,4}\s*)?(?:给定)?材料\s*(\d+)(?:\(\d+\))?\s*',material_region))
 assert [int(m[1]) for m in mids]==list(range(1,len(mids)+1)),year
 mats=[]
 for i,m in enumerate(mids):
  end=mids[i+1].start() if i+1<len(mids) else len(material_region)
  mats.append(dict(number=i+1,text=material_region[m.end():end].strip()))
 if year==2023:
  am=list(re.finditer(r'【试题([一二三四])】参考答案',at));getnum=lambda m:'一二三四'.index(m[1])+1
 elif year==2019:
  am=list(re.finditer(r'第([一二三四])题【参考答案】',at))
  getnum=lambda m:'一二三四'.index(m[1])+1
 elif year==2021:
  am=list(re.finditer(r'(?m)^##\s*([一二三四])、参考答案（F）\s*',at));getnum=lambda m:'一二三四'.index(m[1])+1
 elif year==2022:
  am=list(re.finditer(r'(?m)^##\s*([一二三四])、参考答案：\s*',at));getnum=lambda m:'一二三四'.index(m[1])+1
 else:
  am=list(re.finditer(r'(?:^|(?<=\n)|(?<=）))\s*(?:#{1,4}\s*)?([1-4])、参考答案：\s*',at));getnum=lambda m:int(m[1])
 answers={}
 for i,m in enumerate(am):
  a=at[m.end():am[i+1].start() if i+1<len(am) else len(at)]
  a=re.split(r'(?m)^###\s*参考答案(?:说明：|（H）)',a,1)[0].strip()
  a=a.split('文章分析')[0].strip()
  a=re.sub(r'(?m)^#{1,4}\s*','',a)
  answers[getnum(m)]=a
 oldpath='省考/上海/'+str(year)+'/申论-统考.md';old=b.parse((ROOT/oldpath).read_text(encoding='utf8'),oldpath)
 matches=[]
 for on,oq in old['questions'].items():
  for n,q in questions.items():
   from difflib import SequenceMatcher
   similarity=SequenceMatcher(None,b.qkey(oq),b.qkey(q),autojunk=False).ratio()
   if similarity>.85:matches.append(dict(bucket_number=on,source_number=n,question_similarity=similarity))
 total=re.search(r'(?s)## 总括资料\s*(.*?)\s*### 材料1',material_region)
 notice=re.search(r'(?s)##\s*一、注意事项\s*(.*?)\s*##\s*二、给定材料',material_region)
 packet=dict(year=year,variant=variant,path='省考/上海/'+str(year)+'/申论-'+variant+'类.md',source_path=str(source),source_relative_path=source.relative_to(Path(r'D:\projects\gwy-material-ops')).as_posix(),source_sha256=hashlib.sha256(raw.encode()).hexdigest(),instructions=notice[1].strip() if notice else '',unnumbered_intro=total[1].strip() if total else '',materials=mats,questions=questions,source_answers=answers,old_bucket_path=oldpath,bucket_matching_tasks=matches,cleaning='移除PDF页标和紧随的独立页码、页9推广栏与材料内部数据库编号；其余题面按源保留。2019材料3粘连及作文漏字以同年厚职全文对照校正。2023保留总括资料为未编号前言，原资料1—5编号不变。')
 packets.append(packet)
 print(year,'materials',len(mats),'questions',len(questions),'answers',[(n,len(re.sub(r'\s','',a))) for n,a in answers.items()],'bucket',matches)
(ROOT/'tools/data/shanghai-b-full-source-packets-a-20261015.json').write_text(json.dumps(packets,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
