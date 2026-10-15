"""Add clear authorship notices outside unchanged primary body markers."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'tools');import round5_bulk as p,round4_gap_repair as g,full_repair_precise_answer_audit_20261015 as a
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
plans={
'省考/上海/2019/申论-行政执法卷.md':{n:'> 来源说明：既有AI辅助原创示范，原收录稿注明AI辅助编写；本轮仅明确正文与写作依据的边界，未改正文。不是官方答案，未经实考评分，也不是所链接机构作者的原稿。原写作依据及同题核对入口保持。' for n in [1,2,3]},
'省考/广东/2025/申论-县镇.md':{3:'> 来源说明：既有同题来源参考作文，原作者署名未核实；本轮仅分开完整作文正文与重复附解析，未改正文。不是官方答案，实考得分未核实；原有来源链接及点评完整保留。'},
'省考/广东/2025/申论-统考.md':{11:'> 来源说明：既有同题来源参考作文，原作者署名未核实；本轮仅分开完整作文正文与重复附解析，未改正文。不是官方答案，实考得分未核实；原有来源信息及点评完整保留。'},
'省考/江苏/2017/申论-A类.md':{3:'> 来源说明：既有同题来源参考作答，原作者署名未核实；本轮仅标记239字实际正文，未改正文，不将附加字数说明与来源标题计入作答。不是官方答案，实考得分未核实；原有公开来源链接保留。'},
'省考/江苏/2017/申论-B类.md':{3:'> 来源说明：既有同题来源参考作答，原作者署名未核实；本轮仅标记239字实际正文，未改正文，不将附加字数说明与来源标题计入作答。不是官方答案，实考得分未核实；原有公开来源链接保留。'}
}
receipts=[]
for rel,items in plans.items():
 old=Path(rel).read_text(encoding='utf-8');d=p.parse(old,rel)
 def sub(m):
  n=int(m[2])
  return m[1]+'\n\n'+d['answers'][n]+'\n\n'+items[n]+'\n\n'+m[4] if n in items else m[0]
 new=g.DETAIL.sub(sub,old);nd=p.parse(new,rel);assert d['questions']==nd['questions'] and d['materials']==nd['materials']
 for n,ans in d['answers'].items():
  if n in items:
   assert [v['body'] for v in a.extract_versions(ans)]==[v['body'] for v in a.extract_versions(nd['answers'][n])]
   assert '来源说明' in nd['answers'][n] and '不是官方答案' in nd['answers'][n]
  else:assert ans==nd['answers'][n]
 Path(rel).write_text(new.rstrip()+'\n',encoding='utf-8',newline='');receipts.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(Path(rel).read_text(encoding='utf-8')),'before_text':old,'notices':items,'all_main_bodies_unchanged':True})
Path('reports/PRECISE-BOUNDARY-AUTHORSHIP-NOTICES-20261015.json').write_text(json.dumps({'status':'passed','tasks':sum(len(x) for x in plans.values()),'receipts':receipts},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('passed',len(receipts),sum(len(x) for x in plans.values()))
