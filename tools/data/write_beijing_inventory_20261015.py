import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import round5_bulk as p
R=Path(__file__).resolve().parents[2]
S=[
 {'id':'contemporary_2022','title':'北京青年报：昨日4.8万余人参加京考（人民日报转载）','url':'http://bj.people.com.cn/n2/2021/1213/c82840-35047589.html','finding':'2022考试恢复区级与乡镇同卷，下午申论同样为一类试卷；对照应急管理四题一致。','scope':[2022]},
 {'id':'history_2023','title':'高顿：北京申论考情沿革（2023-05-11）','url':'https://m.gwy.com/bjgwy/275807.html','finding':'2019及以前一套，2020–2021区县与乡镇两套，2022–2023恢复一套。标题含2024，发布日期与正文证据只支持截至2023的沿革。','scope':list(range(2016,2024))},
 {'id':'outline_2024','title':'2024北京公共科目笔试大纲（陕西科技大学转载北京组工网）','url':'http://jiuye.www.sust.edu.cn/info/1140/25734.htm','finding':'大纲申论介绍为共同四项能力，无区乡分别描述；与公开2024统一题本交叉印证。单靠无分级文字不作为真实卷型的充分证明。','scope':[2024]},
 {'id':'paper_2024','title':'考考公务员2024北京市申论题本预览','url':'https://www.kkgwy.com/e/extend/exam/paper.php?id=10965','finding':'4题；眼低手高、小题大做、线上盲道题面与现文件相符，无新增乡镇分卷证据。','scope':[2024]},
 {'id':'outline_2025','title':'中公：2025北京公务员申论大纲解读（2024-11-12）','url':'http://www.eoffcn.com/kszx/detail/1509001.html','finding':'明确指出2025申论大纲介绍没有分级分类设定。','scope':[2025]},
 {'id':'paper_2025','title':'考考公务员2025北京市申论题本预览','url':'https://www.kkgwy.com/e/extend/exam/paper.php?id=10966','finding':'4题；三新经济、沙盒监管、幸福广场首发经济、尝新到常新与现文件相符。','scope':[2025]},
 {'id':'notice_2026','title':'北京市公务员局2026年度考录公告','url':'https://www.bjdj.gov.cn/article/3000206044.html','finding':'官方确认申论于2025-12-07下午考试，未给出真实试题全文；不能将未找到解释为未考试。','scope':[2026]},
 {'id':'outline_2026','title':'华图2026京考申论大纲解读','url':'https://bj.huatu.com/2025/1110/1250304.html','finding':'按4道题统一介绍。与官方公告相互参照，只支持统一卷工作假设，不代替原题核验。','scope':[2026]},
 {'id':'wrong_province','title':'北京公务员考试网2026A类深度解读','url':'http://www.bjsgwy.org/2025/1209/25217.html','finding':'正文明确为江苏A卷标准与品牌，并非北京。排除。','scope':[2026]},
 {'id':'marketing','title':'高顿2026北京真题领取页','url':'https://m.gwy.com/dfgwy/395860.html','finding':'需咨询领取，已提取正文未提供完整材料和题目。不能计为已取得原卷。','scope':[2026]},
]
rows=[]
for y in range(2016,2027):
 files=sorted((R/f'省考/北京/{y}').glob('申论*.md'))
 row={'year':y,'real_variants':['区级及以上','乡镇'] if y in [2020,2021] else ['统一试卷'],'variant_status':'2026工作假设，待真实题本确认' if y==2026 else '已核对卷型证据与现题本','files':[],'evidence':[s['id'] for s in S if y in s['scope']]}
 for f in files:
  d=p.parse(f.read_text(encoding='utf-8'),f.relative_to(R).as_posix())
  row['files'].append({'path':f.relative_to(R).as_posix(),'questions':[{'number':n,'question':q} for n,q in d['questions'].items()],'readable_answers':len(d['answers'])})
 row['missing_full_papers']=1 if y==2026 else 0;rows.append(row)
report={'date':'2026-10-15','scope':'北京2016–2026公务员公开招考申论，不包括遴选/选调/事业单位','existing_independent_papers':sum(len(x['files']) for x in rows),'missing_full_papers':1,'missing_independent_township_variants_2022_2025':0,'missing_2026':'确已考试但未取得可核实完整题本；不伪造材料、题面或新卷。','annual_inventory':rows,'evidence':S,'reconstruction_receipts':['reports/FULL-REPAIR-BEIJING-ESSAY-RECONSTRUCTION-20261015.json','reports/FULL-REPAIR-BEIJING-2023-20261015.json'],'archive_disposition':'root统一移档2020/2021混合统考桶及2022倒序重复统考桶；2022正确区级卷重命名统考。所有原文保留在凭据或归档。'}
(R/'reports/FULL-REPAIR-BEIJING-ESSAY-INVENTORY-20261015.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
md=['# 北京2016–2026申论卷型与全文库存核实','', '已核对的2016–2025独立试卷共12套；2026确已举行考试，但尚未取得可核实完整题本。2020、2021每年两套，2022起恢复统一卷，2022–2025不再虚列缺乡镇卷。2026统一卷为依据大纲连续性作出的工作假设，仍需题本确认。','','| 年度 | 真实卷型／待核状态 | 当前正文 |','|---|---|---|']
for r in rows:md += [f'| {r["year"]} | {"、".join(r["real_variants"])}'+('（待题本确认）' if r['year']==2026 else '')+f' | {len(r["files"])}套'+('，未取得全文' if r['year']==2026 else '，均有可读取作答')+' |']
md += ['', '2020–2021原“统考”汇编分别混入区级、乡镇各两题，不能当作第三套独立卷。已依据同年同卷完整PDF转录恢复四套真实分卷的全部材料、题序、分值、要求及16份原创主作答，逐题题干规范化相似度均为1，原文和原参考全部存证。2023已按同卷完整题本恢复六段材料编号和四题顺序，保留原有四份参考作答。', '', '2022原“区级”与“统考”为同一套应急管理题：前者题序、分值和材料齐全，后者四题顺序颠倒。由root归档重复桶并把完整卷命名为统考。','', '证据与判断边界：','']
for s in S:md += [f'- [{s["title"]}]({s["url"]})：{s["finding"]}']
md += ['', '公开机构范文未批量转载；修复主作答明确标为AI辅助原创示范、非官方、未经实考评分。完整题本只有来源与题面核实后才入库，不以广告页、栏目标题或外省题本充数。','']
(R/'reports/FULL-REPAIR-BEIJING-ESSAY-INVENTORY-20261015.md').write_text('\n'.join(md),encoding='utf-8');print(report['existing_independent_papers'],report['missing_full_papers'])
