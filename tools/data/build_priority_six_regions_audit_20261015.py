"""Read-only annual essay-type audit, 2016–2026. Does not add or alter exam content."""
from pathlib import Path
import json,hashlib,collections
from priority_essay_inventory_six_regions_20261015 import inventory,R
STOCK=inventory();ROWS=[]
SHMAP_PATH=R/'reports/FULL-REPAIR-SHANGHAI-BUCKET-MAP-A-20261015.json'
SHMAP=json.loads(SHMAP_PATH.read_text(encoding='utf8')) if SHMAP_PATH.exists() else {}
SHMAP_BY_YEAR={x['year']:x for x in SHMAP.get('rows',[])}
CAT={a:f'https://www.kkgwy.com/e/extend/exam/index.php?cid={c}' for a,c in {'上海':218,'天津':219,'广东':199,'福建':197,'深圳':226}.items()}
SH_SPECIAL={2016:'http://www.shgkw.org/2016/0926/9462.html',2021:'http://www.shgkw.org/2021/0820/40645.html',2022:'https://cgzf.sh.gov.cn/channel_8/20220819/1a689b735cb248ddbe238c9f4e03d319.html',2024:'https://www.shqp.gov.cn/shqp/ggfw/bmts/20240820/1183054.html',2025:'https://www.lysrsks.com/index/news/detail.html?id=2009'}
TJ26='https://www.tj.gov.cn/zwgk/zfxxgkzl/fdzdgknr/zkly/zk/202511/t20251105_7170794.html'
TJ24='http://www.tjgwyw.org/2024/0122/46154.html'
TJ25='https://ah.huatu.com/2024/1107/2948494.html'
FJ26='http://fj.huatu.com/2026/0116/2509896.html'
def row(area,year,expected,missing=None,pending=None,notes='',sources=None,status=None):
 stock=[{k:x[k] for k in ['vol','path','title']} for x in STOCK if x['area']==area and x['year']==year]
 ROWS.append(dict(area=area,year=year,expected_types=expected,stock=stock,confirmed_missing_types=missing or [],identity_pending=pending or [],status=status or ('confirmed_missing' if missing else 'identity_pending' if pending else 'catalog_types_present'),notes=notes,source_urls=sources or [CAT.get(area,'')],scope_boundary='卷型库存审计；不以文件数、首材料相同或答案覆盖率作为原卷完整认证。'))
for y in range(2016,2027):
 # Shanghai conventional A/B categories; independent enforcement exams are tracked separately.
 ex=['A','B'] if y<2026 else ['常规单卷'];miss=[];pending=[];urls=[CAT['上海']]
 if y in [2016,2021,2022,2024,2025]:ex+=['行政执法专项'];miss+=['行政执法专项'];urls+=[SH_SPECIAL[y]]
 if 2017<=y<=2020:ex+=['行政执法专项']
 if y==2022:
  miss+=['A'];urls+=['https://www.eoffcn.com/kszx/detail/1229673.html']
  if not SHMAP_BY_YEAR.get(y):pending+=['B整卷恢复与桶题逐项映射待最终报告']
 if y in [2018,2019,2020,2021]:
  mapping=SHMAP_BY_YEAR.get(y)
  if not mapping:pending+=['统考桶与同年分卷题目映射待最终报告']
  elif mapping.get('unmapped_tasks'):pending+=['统考桶任务'+str(mapping['unmapped_tasks'])+'尚未映射；B完整4题已恢复，不能将剩余任务另造卷']
 if y==2023:
  miss+=['B'];urls+=['https://www.jfdaily.com/wx/detail.do?id=784997','https://www.eoffcn.com/kszx/detail/1229673.html']
  if not SHMAP_BY_YEAR.get(y):pending+=['A整卷恢复与桶第4题映射待最终报告']
 if y==2026:urls+=['http://sh.xinhuanet.com/20251101/3d8662ea46834c758e48193886f6ecd7/c.html','https://shacs.gov.cn/gwyj/api/files/fetch?fid=ea6c24ce-420c-4f3f-ad4f-483f83cf2c4b']
 row('上海',y,ex,miss,pending,'2023行政执法专项停招有同期媒体依据；2026取消AB分类。2024/2025统考桶8题全部逐题映射至AB各4题，不能覆盖专项。2026是否另办专项尚未取得证据。',urls)
 if y in SHMAP_BY_YEAR:ROWS[-1]['question_material_mapping_evidence']={'report':'reports/FULL-REPAIR-SHANGHAI-BUCKET-MAP-A-20261015.json','tasks':SHMAP_BY_YEAR[y].get('tasks',[]),'unmapped_tasks':SHMAP_BY_YEAR[y].get('unmapped_tasks',[]),'restoration_receipts':['reports/FULL-REPAIR-SHANGHAI-2022B-A-20261015.json','reports/FULL-REPAIR-SHANGHAI-HISTORICAL-A-20261015.jsonl']}
for y in range(2016,2027):
 ex=['常规单卷'];miss=[];pending=[];urls=[CAT['天津']]
 if y==2017:ex+=['滨海新区等单位专项（12月23日）'];urls+=['http://www.tjgwyw.org/2018/1220/24369.html','http://download.tjgwyw.org/20180411145819_14866.pdf','https://www.eol.cn/gongwuyuan/difang/skzx/201711/t20171127_1569596.shtml']
 if y==2020:ex=['A/市级','B/区县']
 if y==2021:ex=['市级','区县/区级','行政执法']
 if y==2022:
  ex=['综合管理市级','综合管理区级以下','行政执法'];miss=['行政执法'];urls+=['http://www.tjgwyw.org/2022/0224/38404.html','https://www.eoffcn.com/kszx/detail/1275187.html']
 if y>=2023:ex=['综合市区','综合街镇','行政执法']
 if y==2024:miss=['综合街镇','行政执法'];urls+=[TJ24]
 if y==2025:miss=['行政执法'];urls+=[TJ25]
 if y==2026:miss=['综合市区','综合街镇'];urls+=[TJ26]
 tj_note='2025统考8题逐题映射至市区4题+街镇4题；2026统考4题逐题映射至执法4题（题序1→1、2→3、3→2、4→4），并非以共享材料推断整卷相同。'
 if y==2022:tj_note='据FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json：原四文件为两完整三题卷+两个倒序两题片段；区级卷片段1→县级完整2、2→1，市级卷片段1→市级完整2、2→1；四题qkey均1.0，材料14gram覆盖99.4—99.5%。县级完整材料与用户区级以下题本规范化全文相同。两片段归档后不能计独立卷；第三类行政执法真实缺卷。'
 row('天津',y,ex,miss,pending,tj_note,urls)
 if y==2022:ROWS[-1]['identity_evidence_report']='reports/FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json'
 if y==2017:
  ROWS[-1]['identity_evidence_report']='reports/FULL-REPAIR-TIANJIN-2017-BINHAI-IDENTITY-20261015.json'
  ROWS[-1]['notes']='__t443为2017-12-23滨海新区等单位专项，六段材料6367规范字与当年真实试卷网页、PDF逐字相同；四道题干、要求、分值均对应。不是普通4月卷补充，不另造试卷。'
for y in range(2016,2027):
 ex=['县级','乡镇'] if y<2024 else ['省市','县镇','行政执法','公安']
 if y==2018:ex=['县级与珠三角乡镇统一卷']
 urls=[CAT['广东']]
 if y==2018:urls+=['https://zhuanlan.zhihu.com/p/438641741','https://fenbi.com/page/fenxiaozixundetail/7/164/413686194537472']
 row('广东',y,ex,notes='2018未组织独立粤东西北乡镇卷，不能沿用相邻年两卷推算漏卷；2024起四类均有明确分卷文件。统考桶为混合/未分类来源，不额外计一套真实卷。',sources=urls)
for y in range(2016,2027):
 ex=['统一卷'] if y<2018 else ['县级','乡镇'] if y<=2021 else ['省市','县乡','行政执法'] if y<=2024 else ['省市综合管理','通用']
 urls=[CAT['福建'],'https://fj.huatu.com/zt/fzfb/']
 if y==2026:urls+=[FJ26]
 row('福建',y,ex,['省市综合管理'] if y==2026 else [],notes='2018增设乡镇，2022为省市/县乡/执法，2025合并县乡与执法为通用。2026华图当年职位分析证实A类省市综合管理与A类通用并存；网页大纲仍称三类者与改革表冲突，不采用。',sources=urls)
for y in range(2016,2027):
 if y<=2018:
  ex=['单卷'] if y==2016 else ['单考区','双考区'] if y==2017 else ['3月24日','3月25日']
  row('广州',y,ex,notes='2017单/双考区与2018两天两套原卷独立核对，不能统按每年一卷。',sources=['https://www.xinhuanet.com/politics/2018-03/25/c_1122586574.htm'])
 else:
  row('广州',y,[],pending=['未取得本年度独立市考重启及独立试卷证据，不能计作已确认缺卷'],notes='2019起停考有二手回顾报道；2020同期报道明确很多广州岗位并入广东省考。此证据不等于逐年官方永久停考证明，保留未证实状态。',sources=['https://zhuanlan.zhihu.com/p/669874062','https://cn.chinadaily.com.cn/a/202007/03/WS5efeb5d9a310a859d09d5d86.html'],status='separate_exam_unconfirmed')
for y in range(2016,2027):
 if y in [2021,2026]:
  row('深圳',y,[],pending=['未取得以本年度为招录年度的独立公告/试卷；2022公告于2021年不能再造2021卷，广东2026公告不能冒深圳独立2026卷'],sources=['https://www.eoffcn.com/kszx/detail/1208330.html','https://hrss.sz.gov.cn/szksy/ztzl/gwyks/'],status='separate_exam_unconfirmed')
 else:
  row('深圳',y,['A','B'] if y<=2018 else ['Ⅰ','Ⅱ'],['Ⅰ'] if y==2024 else [],notes='2024官方招录公告明确市直/定向港澳考Ⅰ，市直驻区/区街/执法/警察考Ⅱ；现有库存仅Ⅱ。原材料即使共用也不能复制Ⅱ题目冒充Ⅰ。已查用户私有历年目录与公开机构目录，均仅取得2024Ⅱ，未取得Ⅰ完整题面。',sources=[CAT['深圳']]+(['https://www.szgm.gov.cn/xxgk/xqgwhxxgkml/rsxx/gwyzk/content/post_11029041.html'] if y==2024 else []))
missing=[{'area':x['area'],'year':x['year'],'type':v,'source_urls':x['source_urls']} for x in ROWS for v in x['confirmed_missing_types']]
data={'audit_date':'2026-10-15','read_only':True,'area_year_rows':len(ROWS),'stock_files':len(STOCK),'confirmed_missing_count':len(missing),'confirmed_missing':missing,'rows':ROWS,'source_evidence':'tools/data/priority-six-regions-source-evidence-20261015.json','question_level_mapping':'reports/PRIORITY-ESSAY-SIX-REGIONS-QUESTION-MAPS-20261015.json','limits':['这不是原卷全文逐字验真结果；目录存在不保证文件内所有原题都齐全。','未证实独立开考年份不计作已确认缺卷，也不伪称确定停考。','上海专项额外频次只有确证的一次年度考试，未以短视频标题推造上半年第二套。']}
(R/'reports/PRIORITY-ESSAY-SIX-REGIONS-AUDIT-20261015.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
md=['# 六地区2016—2026申论真实卷型与库存审计','',f'只读审计66个地区年度格、{len(STOCK)}份现有文件，确认另缺{len(missing)}套真实卷型。没有新增空白卷或修改原题。答案缺口清零不等于卷型库存齐全。','','| 地区 | 年份 | 已确认缺卷 |','|---|---|---|']
for x in ROWS:
 if x['confirmed_missing_types']:md.append(f"| {x['area']} | {x['year']} | {'、'.join(x['confirmed_missing_types'])} |")
md+=['','## 关键口径纠正','','- 上海2026取消AB分类，不能虚报B卷缺失；2023行政执法专项停招有同期报道。','- 广东2018为县级与珠三角乡镇统一卷，不能凭两端年份双卷补造另一套。','- 福建2025由旧县乡/执法合为通用，库存省市、通用两类均有；2026另缺省市综合管理。','- 广州2019—2026及深圳2021、2026未取得独立年度开考证据，单列未证实，不按日历空格凑缺卷。','- 上海2024/2025统考各8题全部逐题匹配AB，天津2025统考8题匹配市区/街镇；天津2026统考4题按1→1、2→3、3→2、4→4匹配行政执法。因此这些桶不覆盖另缺类别。','- 天津2022四文件身份仍待复核；上海2022B/2023B等统考桶需逐题比公开完整题本，不能按桶名宣称整卷齐。','','## 逐年结果','','| 地区 | 年份 | 实际已证卷型 | 库存卷型 | 确认缺卷 | 待核 |','|---|---|---|---|---|']
md=[line.replace('天津2022四文件身份仍待复核；上海2022B/2023B等统考桶需逐题比公开完整题本，不能按桶名宣称整卷齐。','天津2022已核清两套完整三题卷+两份倒序两题重复片段，行政执法真实另缺；当年类名是综合管理市级/综合管理区级以下/行政执法，不套后年市区/街镇。上海2023统考作文属A第4题，科创中心B卷另缺。') for line in md]
for x in ROWS:md.append('| '+' | '.join([x['area'],str(x['year']),'、'.join(x['expected_types']) or '独立开考未证实','、'.join(s['vol'] for s in x['stock']) or '无','、'.join(x['confirmed_missing_types']) or '无已确认项','；'.join(x['identity_pending']) or '无本轮新增身份待核；全文核验范围见证据'])+' |')
md+=['','各条来源URL、库存完整路径、开考未证实边界见同名JSON。公开目录只作为存在及类别证据，未将付费预览等同完整题本。来源摘录见 tools/data/priority-six-regions-source-evidence-20261015.json。','']
(R/'reports/PRIORITY-ESSAY-SIX-REGIONS-AUDIT-20261015.md').write_text('\n'.join(md),encoding='utf8')
print(json.dumps({'rows':len(ROWS),'stock':len(STOCK),'confirmed_missing_count':len(missing),'missing':missing},ensure_ascii=False))
