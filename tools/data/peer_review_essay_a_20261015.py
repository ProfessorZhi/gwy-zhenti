"""Read-only independent review of ten authored tasks and Beijing figure evidence."""
import sys,json,hashlib,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_repair_answers_20261015 import validate_answer
from full_repair_essay_a_20261015 import ROOT
import round5_bulk
targets={'省考/陕西/2024/申论-B类.md':set(range(1,6)),'省考/黑龙江/2017/申论-统考.md':set(range(1,5)),'省考/江西/2026/申论-县乡卷.md':{4}}
comments={
('省考/陕西/2024/申论-B类.md',1):'177字，满足150—200；覆盖医养框架、资源整合、家庭医生、长护险与专业服务，均有资料1依据。',
('省考/陕西/2024/申论-B类.md',2):'228字，满足200—250；分别回答特点与作用，信贷、技术营销、信用文明与青年下沉均对应资料2。',
('省考/陕西/2024/申论-B类.md',3):'308字，满足300—350；五类问题与建议逐项对应，未把改造前问题替代改造后物业、维修、资金及个性需求。',
('省考/陕西/2024/申论-B类.md',4):'418字，满足400—500；发言提纲具称谓、经验、成效和下一步，数据97%、98%、100%与资料4一致。',
('省考/陕西/2024/申论-B类.md',5):'1089字，满足1000—1100；同时讨论创新风险、不创新风险及科学控险，果醋数字化、存量用地、能源与柿子例证对应资料5。',
('省考/黑龙江/2017/申论-统考.md',1):'150字，不超200；分表现/危害，谣言、网络暴力、直播失序及个体现实伤害均对应资料2。',
('省考/黑龙江/2017/申论-统考.md',2):'226字，不超250；从刺激诱惑、虚拟角色、匿名约束弱、碎片化解释成因，未仅重复危害替代原因。',
('省考/黑龙江/2017/申论-统考.md',3):'336字，不超400；建议紧扣资料5—6的教育、文化内涵、数字传播、受众态度与长期养成，未错写成一般监管执法题。',
('省考/黑龙江/2017/申论-统考.md',4):'1064字，满足1000—1200；约束与自觉关系明确，后续论述落实教化、文化滋养和个人养成，外在规则未完全取代道德主题。',
('省考/江西/2026/申论-县乡卷.md',4):'892字，满足800—1000；选路与增强能力两条逻辑完整，小提琴、蜜瓜、机构整合和全周期服务对应资料4；引用全卷竹产业/传统制造符合参考给定资料的开放要求。',
}
entries=json.loads((ROOT/'tools/data/full-repair-essay-b-20261015.json').read_text(encoding='utf8'));review=[]
for e in entries:
 if e['path'] not in targets or e['number'] not in targets[e['path']]:continue
 p=ROOT/e['path'];text=p.read_text(encoding='utf8');d=round5_bulk.parse(text,e['path']);q=d['questions'][e['number']]
 n=validate_answer(q,e)
 # Root's Unicode/layout normalization may change paragraph whitespace. Compare
 # substantive text, retaining a separate current-file hash for review context.
 plain=lambda s:re.sub(r'\s','',s)
 assert plain(e['answer']) in plain(d['answers'][e['number']]),(e['path'],e['number'])
 review.append({'path':e['path'],'number':e['number'],'characters':n,'result':'pass_within_review_scope','assessment':comments[(e['path'],e['number'])],'question_sha256':hashlib.sha256(q.encode()).hexdigest(),'reviewed_file_sha256':hashlib.sha256(text.encode()).hexdigest(),'authorship':e.get('attribution_kind'),'material_scope_reviewed':True})
assert len(review)==10
figroot=ROOT/'图片/省考-北京-2025-行测-统考/题目图'
from PIL import Image
im=Image.open(figroot/'2827896.png').convert('RGB');pts=[(q,r) for q in range(-2,3) for r in range(-2,3) if abs(q+r)<=2]
centers=[('g1a',54,54),('g1b',162,54),('g1c',270,54),('g2a',408,54),('g2b',516,54),('A',177,209),('B',285,209),('C',393,209),('D',501,209)]
from itertools import combinations
samples=[]
for name,x,y in centers:
 s={(q,r):sum(im.getpixel((round(x+15.2*q),round(y+17.5*r+8.75*q))))<384 for q,r in pts};todo={p for p in pts if s[p]};groups=[]
 while todo:
  seed=todo.pop();stack=[seed];g={seed}
  while stack:
   q,r=stack.pop()
   for dq,dr in [(1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1)]:
    pp=q+dq,r+dr
    if pp in todo:todo.remove(pp);g.add(pp);stack.append(pp)
  pairdist=[]
  for (q,r),(qq,rr) in combinations(g,2):a,b=q-qq,r-rr;pairdist.append(a*a+a*b+b*b)
  groups.append({'size':len(g),'squared_pair_distances':sorted(pairdist)})
 samples.append({'figure':name,'black':sum(s.values()),'white':19-sum(s.values()),'black_components':groups,'rotation_120_invariant':all(v==s[(-q-r,q)] for (q,r),v in s.items())})
result={'date':'2026-10-15','role':'independent_peer_review','mutated_existing_MD':False,'essay_tasks_reviewed':review,'essay_actionable_findings':[],
 'source_identity_note':{'path':'省考/陕西/2024/申论-B类.md','finding':'5题合计150分曾触发混卷疑点；同年中公县乡级解读明确第五题创新风险作文，华图大纲解读明确B/C类5题，故不凭100分惯例删除第五题。','sources':['https://www.eoffcn.com/kszx/detail/1303181.html','https://sn.huatu.com/2024/0201/1205544.html','https://www.aipta.com/article/10244.html']},
 'beijing_53':{'answer':'D','confidence':'high','proof':'两套均黑9白10，每图黑圆分3组三圆；第一套组形依次直线、等边小三角、V形折线。第二套前2图对应直线与三角，故第三应V形，只有D。第二套还具120°旋转对称。A同为三角，B每组4黑，C黑白反转、黑圆连为整体。','pitfall':'仅黑9+120°旋转不足排A；A也满足二者，须用三圆组形对应顺序。','source_image':'图片/省考-北京-2025-行测-统考/题目图/2827896.png','method':'Native local-image inspection plus 19-center hex-lattice sampling; no image modification','circle_sampling':samples},
 'beijing_56_58':{'result':'unresolved_missing_shared_operation_definitions','figures':[{ 'number':n,'path':str(figroot/f),'sha256':hashlib.sha256((figroot/f).read_bytes()).hexdigest()} for n,f in [(56,'2827901.png'),(57,'2827905.png'),(58,'2827909.png')]],'finding':'现有MD各题仅通用问句，图片仅初图、三符号和选项，未见符号与具体操作的定义/总图例。不能因候选字母或符号外形倒推规则。','source_leads':[{'url':'https://www.33iq.com/question/588737.html','status':'TinyFish同句搜索命中，fetch_content回503，尚未见图例正文'},{'url':'https://gwy.dtiku.cn/paper/51836','status':'TinyFish fetch_content timeout，已交根代查'}]},
 'beijing_62':{'answer_supported':'B','confidence':'medium','image':'D:/artifacts/gwy-quality-audit-20261015/beijing-q62-large.png','assessment':'独立看原图支持B：切平面含顶部水平整边AB，各水平面截线与AB平行，须反映阶梯间凹口。A斜折角、C缺凹口、D多顶凸台均不符。该判断为图形拓扑复核，未取得精确尺寸或机构同题解析。'},
 'boundary':'10题已对照当前题面、材料与正文，不等同全库逐字官方原卷认证，也不鉴定实考分数。'}
(ROOT/'reports/FULL-REPAIR-PEER-REVIEW-A-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'essay_tasks':len(review),'essay_actionable_findings':0,'beijing53':'D verified','beijing56_58':'missing rules, unresolved','beijing62':'supports B, topology only'},ensure_ascii=False))
