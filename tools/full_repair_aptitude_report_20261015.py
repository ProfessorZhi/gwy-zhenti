#!/usr/bin/env python3
"""Summarize factual repairs and documented source limitations without clearing gaps."""
from pathlib import Path
import csv,json,hashlib
R=Path(__file__).resolve().parents[1]
def write_reports(audit_root):
 issues=json.loads((audit_root/'results/issues-final.json').read_text(encoding='utf8'));lex=[]
 for x in issues:
  if x['code']=='placeholder_option' and x['path'].endswith('.md') and '/2020/' in x['path'] and '业内专家建议建立国家营养日' in (R/x['path']).read_text(encoding='utf8'):
   if any(y['path']==x['path'] and y['question']==x['question'] for y in lex):continue
   lex.append({'path':x['path'],'question':x['question'],'classification':'false_positive','reason':'A选项“缺失”是与薄弱/不力/缺乏并列的完整词语，不是题面占位。','sources':['https://www.chinagwy.org/files/20240109103656_86849.pdf','https://www.chinagwy.org/files/20211111144841_16731.pdf','https://www.chinagwy.org/files/20200822200015_81477.pdf']})
 (R/'reports/FULL-REPAIR-APTITUDE-LEXICAL-20261015.json').write_text(json.dumps(lex,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 rows=list(csv.DictReader((audit_root/'missing-papers.csv').open(encoding='utf-8-sig',newline='')))
 west={2020:'https://hrss.xizang.gov.cn/xwzx/tzgg/202006/t20200610_244822.html',2022:'https://hrss.xizang.gov.cn/xwzx/tzgg/202206/t20220607_301794.html',2023:'https://hrss.xizang.gov.cn/xwzx/tzgg/202302/t20230208_340777.html',2024:'https://hrss.xizang.gov.cn/xwzx/tzgg/202403/t20240329_409829.html',2025:'https://hrss.xizang.gov.cn/xwzx/tzgg/202501/t20250124_459355.html',2026:'https://hrss.xizang.gov.cn/xwzx/tzgg/202512/t20251202_512168.html'}
 for row in rows:
  row.update(repair_state='原卷全文尚未取得；未新增虚构原题',evidence_url='',note='已查现有GitHub上游目录与用户真题素材；不能据邻年或另一科目推定具体分卷。')
  if row['area']=='河南' and row['year']=='2018':
   row.update(repair_state='不适用：该年度未招录（同年既有申论身份另待核）',evidence_url='https://henan.china.com.cn/m/2020-06/11/content_41181181.html',note='中国网转载大河网/河南商报报道明示2018年未招录；华图历年表同证。不能伪造2018行测。现有2018河南申论须独立核真实年份。')
  elif row['area']=='西藏' and int(row['year']) in west:
   row.update(repair_state='已确认该年该科开考；仍缺可靠原卷全文',evidence_url=west[int(row['year'])],note='官方公告列行政职业能力测验和申论；不能把公开卷缺失改为未开考。2025定向公告明确使用同年公开考录A卷；2026常规申论有A/B/C分卷，不能只以一个覆盖格代替全卷型目录。')
  elif row['area']=='江苏' and row['year']=='2026':
   row.update(evidence_url='https://ah.huatu.com/zhaokao/list/guokao/chuzhou/jiangsu-2025.html',note='华图公告汇总列2025-12-07考试，对应2026招录年度；网盘目录显示A卷候选但未取得可核验正文。文库55题“真题”明显不合真实卷结构，未导入。')
  elif row['area']=='深圳' and row['year'] in ['2021','2026']:
   row.update(repair_state='单独开考证据未取得；年度口径待核，不计已确认缺卷',evidence_url='https://www.eoffcn.com/kszx/detail/1208330.html ; https://hrss.sz.gov.cn/szksy/ztzl/gwyks/',note='中公历年表列2020/2022/2023；2022招录公告于2021-11-05发布，日历年不等于招录年度。官方当前列表尚未发现独立深圳2026招录，不从邻年或广东统考推造市考卷。')
  elif row['area']=='西藏' and row['year']=='2016':
   row.update(evidence_url='https://www.kkgwy.com/sl/zt/2016/04/25/142206.html',note='检索题为2016西藏申论的页面仅为考后更新预告，未给材料和题面；不能以导航页面计补卷。')
  elif row['area']=='浙江' and row['year']=='2022':
   row.update(evidence_url='https://static.32xueyuan.com/zq/u/cms/zj/202212/07183022bn59.pdf',note='标题虽称2022，正文却把2020年科学家座谈会日期改为2022，且内容对应既有2021A。作为年份污染候选排除，不可复制成新真题卷。')
 with (R/'reports/FULL-REPAIR-MISSING-PAPERS-20261015.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 (R/'reports/FULL-REPAIR-MISSING-PAPERS-20261015.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 pending=[{'path':'省考/广东/2020/行测-县级卷.md','questions':[69,70,71,72,73,74,75],'sources':['https://upload.xingguanggongkao.com/pdf/2020年广东省公务员录用考试《行测》真题（县级卷-考生回忆版）.pdf'],'finding':'星光卷为100题版，但69—75仍逐题写“本题暂无收集到”，默认答案A不可当原题。用户题本文件名也明确“7道题暂缺”。'}, {'path':'省考/江苏/2024/行测-A类.md','questions':[76,96,110,111],'sources':['https://www.chinagwy.org/files/20240925145840_94072.pdf','https://static.32xueyuan.com/zq//u/cms/zj/202411/221409378lxq.pdf'],'finding':'公考通/展鸿的原题本对应题位仍缺；不同版本另有题干差异，不能从其他年度同号套入。'}, {'path':'省考/江苏/2025/行测-C类.md','questions':[27,29,35,36,37,42,75,77,78,80,81,85],'sources':['https://ah.huatu.com/tiku/dfgwy/2024jsskgfc/','https://www.gwyeasy.com/archives/20285','https://iget100.wuhoushu.com/gongkao/shengkao/jiangsu/2025/xingce-c'],'finding':'华图独立同C卷网页逐题均为“题目缺失”，杨柳同卷亦暂缺。该网页考试日2024-12-08，对应2025招录年度，不能按URL年号误填2024卷。'}, {'path':'省考/浙江/2020/行测-A类.md','questions':[49,50],'sources':['https://static.32xueyuan.com/upload/images/2021/11/04/1636024826627.pdf'],'finding':'展鸿题本和解析明示“49-50.缺”，用户同卷文件名也为“缺2题”。'}]
 (R/'reports/FULL-REPAIR-APTITUDE-PENDING-20261015.json').write_text(json.dumps({'missing_original_questions':pending,'remaining_options':[{'path':'省考/山东/2023/行测-统考.md','question':42,'options':['A','C','D'],'source':'https://www.gcyls.cn/file/upload/202403/14/144508891.pdf','source_page':16,'finding':'本机取得的29页PDF第16页正文为A略/B40毫克/C略/D略，确认并非公式或图片未抽取。'}],'beijing_missing_materials':{'path':'省考/北京/2025/行测-统考.md','questions':[22,23,24,25,26,27,28,29,30,31,79,80],'finding':'基线93题文件与源HTML无共用材料；已交根agent用四海自有题本同题恢复，不应以整体字母减1代替人工解题。'},'new_source_conflicts':[{'path':'省考/江西/2019/行测-法检.md','question':41,'finding':'题面每日300元、2017-10-01至07并称10-04中秋；原解析计算5400元却标A6300，四项均无5400。用户同卷原题也如此，待取得可靠原卷解决。'},{'path':'省考/黑龙江/2019/行测-边境县.md','question':5,'finding':'来源把单选题判B、D均正确；补录时已显著保留争议，未冒称官方唯一答案。'}]},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 report='''# 2026-10-15 行测修复与缺卷查证

本轮以PR #19基线为工作底稿；尚未解决的原卷缺题仍保留，不以模拟题或猜造原题清零。

## 已写回的行测修复

- 江西2019法检补3处、河南2019司法所补16处、黑龙江2018公检法补2处、黑龙江2019边境县补120处，共141处参考答案，标注用户提供的同卷资料及SHA-256。
- 19道新增图形题逐图核对。38处公式/数据分析解析按既有题面、公式图与统计图重新演算，写成完整原创解析，修正PDF提取的空算式与单位误差。
- 国考2024副省级第12题：补C，纠正B“出资”为“融资”，依完整题本及《预备役人员法》将答案联动校核为C。西藏2016第96题补回空白A，原参考答案A不变。
- 江苏2024C第110题补完整A—D选项原图并独立分析为B；旧缺题默认B已撤销后按完整题面重判。新增图位于`图片/修复-20261015/`，未覆盖既有图。
- 449份行测共52,734个“官方解析”标签改为“来源参考解析（非官方标准答案）”；此项仅更正来源性质，不代表52,734道答案逐题验真。
- 更正12份2020联考“食育进农村”题的审计误报：A选项“缺失”是正常词语，与“薄弱/不力/缺乏”并列，原词保留。

## 仍待取得原文的范围

25道原题分布于4卷，独立原题本仍写缺失；逐题记录见`FULL-REPAIR-APTITUDE-PENDING-20261015.json`。山东2023第42题仍缺A/C/D三个原选项，独立金标尺PDF也写“略”，不能伪造。

57个年度科目覆盖格没有新增虚构试卷。其中河南2018经中国网转载大河网报道及华图历年表确认当年未招录，应从真缺卷调整为不适用，同时必须另核既有“河南2018申论”真实年份。其他格仍保留未收录/待证状态；西藏2020、2022—2026的官方公告明确存在两科，不能以资料难取得为由改成未开考。逐格证据见`FULL-REPAIR-MISSING-PAPERS-20261015.csv`。

北京2025的12道共用材料缺失已交根agent另行恢复。江西2019法检第41题题面与参考答案冲突、黑龙江2019边境县第5题单选多解争议亦显式列出。历史365卷模块题序缺乏原卷证据，不做无证据重排，不删待核告警。

## 证据与复现

`FULL-REPAIR-APTITUDE-ANSWERS-20261015.json`记录141处补答；`...-MATH-...json`记录38处独立校核；`...-OPTIONS-...json`、`...-BOAN-...json`记录实质题面修复；`...-LABELS-...json`记录来源标签改名；`...-LEXICAL-...json`记录12个误报纠正。每份改文提供前后SHA-256。

重放依次运行`tools/full_repair_aptitude_20261015.py --plan tools/data/full-repair-aptitude-20261015/answer-plan.json --apply`、`tools/full_repair_aptitude_options_20261015.py`、`tools/full_repair_aptitude_math_20261015.py`、`tools/full_repair_aptitude_boan_20261015.py --source-image <已核验原图>`。脚本要求对应前置版本，不应在已变更正文上重复应用。

来源参考答案、机构/个人整理与原创校核解析均不等于官方公布标准答案，不宣称真实考生高分。缺卷身份、题序、旧答案正确性与材料图语义仍各自独立验收。
'''
 pending_path=R/'reports/FULL-REPAIR-APTITUDE-PENDING-20261015.json'
 current=json.loads(pending_path.read_text(encoding='utf8'))
 current['remaining_options']=[]
 current['public_supplement_not_official_original']=[{'path':'省考/山东/2023/行测-统考.md','question':42,'source':'https://zhuanlan.zhihu.com/p/642333448','finding':'已据2023-08-27公开补充版补齐A60～100/B40～100/C40～80/D50～130，原创等比解析选B；原官方印刷卷尚未取得，版本边界在题面显著保留。'}]
 pending_path.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 report=report.replace('山东2023第42题仍缺A/C/D三个原选项，独立金标尺PDF也写“略”，不能伪造。','山东2023第42题已据2023-08-27知乎公开补充版本填入四个区间选项，原创等比推导选B；原金标尺转录的B40毫克是下界且不完整。本卷显式标为公开补充版，未冒称已取得官方印刷原卷。')
 report=report.replace('其他格仍保留未收录/待证状态；','深圳2021/2026的四格另标单独开考证据未取得与年度口径待核，不计作已确认缺卷。其他格仍保留未收录/待证状态；')
 report=report.replace('`...-LABELS-...json`记录来源标签改名；','`...-SHANDONG-...json`记录公开补充版本；`...-LABELS-...json`记录来源标签改名；')
 (R/'reports/FULL-REPAIR-APTITUDE-20261015.md').write_text(report,encoding='utf8',newline='\n')
 return {'lexical_false_positives':len(lex),'missing_grid_rows':len(rows),'non_exam_year':sum('不适用' in x['repair_state'] for x in rows),'known_missing_original_questions':sum(len(x['questions']) for x in pending)}
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--audit-root',type=Path,required=True);a=ap.parse_args();print(json.dumps(write_reports(a.audit_root),ensure_ascii=False))
