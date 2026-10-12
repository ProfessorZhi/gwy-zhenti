#!/usr/bin/env python3
"""Generate factual 738-paper study coverage and donor provenance from actual R7 output."""
from __future__ import annotations
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
import round4_gap_repair as g
import r7_reference_audit as audit
import r7_delivery as delivery
from verify_round7_repairs import verify,records

ROOT=g.ROOT
def main():
 validation=verify(ROOT);rr=records(ROOT);summary_path=ROOT/'reports/REPAIR-SUMMARY-20261013-R7.json'
 summary=json.loads(summary_path.read_text(encoding='utf-8'))
 paper_rows=[];tasks=[];count=collections.Counter();region=collections.Counter()
 for r in rr:
  rel=r['path'];t=(ROOT/rel).read_text(encoding='utf-8')
  parsed=None
  try:parsed=delivery.parse(t,rel)
  except Exception as exc:
   if r['parsed']:raise ValueError('Previously parsed paper became unparseable: '+rel) from exc
  entries=[]
  if parsed:
   for n,q in parsed['questions'].items():
    s=audit.assess(q,parsed['answers'].get(n,''));kind=s['kind'];status=s['status']
    rec={'path':rel,'number':n,'type':kind,'status':status,'answer_characters':s['characters'],
      'target_words':s.get('question_word_range',[0,0])}
    entries.append(rec);tasks.append(rec);count[kind+'/'+status]+=1
  else:count['未解析文档']+=1
  if r['added_references']:region[rel.split('/')[1]]+=len(r['added_references'])
  paper_rows.append({'path':rel,'title':(re.search(r'(?m)^# ([^\n]+)',t) or [None,rel])[1],
    'parsed':bool(parsed),'tasks':entries,'new_answers':[a['number'] for a in r['added_references']],
    'added_example_essays':[a['number'] for a in r['added_references'] if a['type']=='作文范文']})
 missing=sum(v for k,v in count.items() if k.endswith('/待补'))
 short=sum(v for k,v in count.items() if k.endswith('/正文偏短待复核') or k.endswith('/正文或图像待复核'))
 full=sum(v for k,v in count.items() if k.endswith('/已收录'))
 if full+missing+short!=len(tasks):raise ValueError('Coverage accounting mismatch')
 stats={'status':'verified','papers':len(rr),'parsed_papers':sum(p['parsed'] for p in paper_rows),
  'unparsed_papers':sum(not p['parsed'] for p in paper_rows),'answer_slots':len(tasks),
  'available_full_or_readable':full,'missing_reference_answer_positions':missing,
  'length_or_layout_warning_positions':short,
  'essay_missing':count['作文范文/待补'],'essay_short_or_layout_warning':count['作文范文/正文偏短待复核']+count['作文范文/正文或图像待复核'],
  'added_sourced_reference_blocks':validation['new_reference_blocks'],
  'newly_filled_answer_positions':validation['newly_filled_answer_positions'],
  'new_exemplar_essays':validation['new_example_essays'],
  'guide_only_files':validation['guide_only_documents'],
  'source_references_by_region':dict(sorted(region.items())), 'classification':dict(count),
  'scope':'All 738 existing MD papers. Length/structure classification only; quality and exam scores are not certified.'}
 if len(rr)!=738 or stats['newly_filled_answer_positions']<10:
  raise ValueError('Unexpected corpus coverage')
 (ROOT/'reports/ROUND7-COVERAGE-20261013.json').write_text(
  json.dumps({'summary':stats,'papers':paper_rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (ROOT/'reports/REPAIR-SUMMARY-20261013-R7.json').write_text(
  json.dumps({**summary,'status':'verified','actual_coverage':stats,'verification':validation},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 lines=['# 全库申论参考答案与范文逐卷验收（第七轮）','',
  '> 当前仓库共738份申论MD。此报告按题目实际可读取参考作答分类，不把机构范文等同于考试机关标准答案，不凭“高分”标题声称真实得分。','',
  '| 项目 | 实际状态 |','|---|---:|',
  '| 申论试卷 | 738 |',
  '| 已可靠解析题目 | '+str(stats['parsed_papers'])+' |',
  '| 题目结构待核 | '+str(stats['unparsed_papers'])+' |',
  '| 已识别作答位置 | '+str(stats['answer_slots'])+' |',
  '| 有可读取参考作答位置 | '+str(full)+' |',
  '| 缺完整答案/范文位置 | '+str(missing)+' |',
  '| 已收录但篇幅/正文待核位置 | '+str(short)+' |',
  '| 作文范文缺项 | '+str(stats['essay_missing'])+' |',
  '| 新增来源参考作答文本 | '+str(validation['new_reference_blocks'])+' |',
  '| 其中补此前缺答案位置 | '+str(validation['newly_filled_answer_positions'])+' |',
  '| 其中新作文范文 | '+str(validation['new_example_essays'])+' |',
  '',
  '**重要：** 完整来源答案才计入新增作答；纯阅读导引不计作新增答案。当前数据不代表所有作文达到高分水平，评分质量需基于立意、材料覆盖、论据真实性和成文质量逐题判断。','',
  '## 逐卷状态（所有738份）','',
  '| 试卷 | 已识别题目 | 现缺参考作答 | 现待复核 | 本次新增全文 |','|---|---:|---:|---:|---:|']
 for p in sorted(paper_rows,key=lambda z:z['path']):
  ts=p['tasks'];m=sum(x['status']=='待补' for x in ts)
  warn=sum(x['status'] not in ('待补','已收录') for x in ts)
  path=p['path']
  lines.append('| ['+path+'](../'+quote(path,safe='/')+') | '+str(len(ts) if p['parsed'] else '未解析')+
    ' | '+str(m)+' | '+str(warn)+' | '+str(len(p['new_answers']))+' |')
 lines+=['','## 追溯与交付边界','',
  '每次新增正文需保留原题、材料、既有非空答案，记录题号、答案类别、来源、内容哈希及可逆改动；材料、原题不完整的另立质量项目。机构/教师/考生的文字均为参考版本，未经实际评分认证不称考场高分。',
  '未找到可确证同题的全文时维持待补，不用通用套话或摘要伪装完成。仅目录/网页来源或AI新写的示范稿不能假冒原机构范文。',
  '',
  '[可机读的738份逐题状态](ROUND7-COVERAGE-20261013.json) · [逐文档修复凭据](ROUND7-REFERENCES-20261013.jsonl) · [验收数字](REPAIR-SUMMARY-20261013-R7.json)','','']
 (ROOT/'reports/QUALITY-REPAIR-20261013-R7.md').write_text('\n'.join(lines),encoding='utf-8')
 p=ROOT/'PROGRESS.md';before=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True,encoding='utf-8')
 cur=p.read_text(encoding='utf-8')
 m=re.search(r'(?m)^## 第三轮：',before)
 if m:cur=re.sub(r'\n## 第三轮：[\s\S]*\Z','',cur).rstrip()+'\n\n'+before[m.start():].rstrip()+'\n'
 cur+='\n## 第七轮：全库申论参考作答与范文导读（2026-10-13）\n\n'
 cur+='对现有738份申论建立逐卷、逐题收录状态与阅读入口；'+str(validation['new_reference_blocks'])+'处加入同题来源参考全文，其中'+str(validation['newly_filled_answer_positions'])+'处是此前缺答案，'+str(validation['new_example_essays'])+'处为作文范文。纯导航不算答案。\n\n'
 cur+='目前识别到'+str(missing)+'处仍缺完整作答、'+str(short)+'处需核查篇幅或文本，'+str(stats['unparsed_papers'])+'份未可靠识别题目。此为统计与阶段交付，不宣称738份均拥有完整参考答案。\n\n'
 cur+='[逐卷状态和内容限制](reports/QUALITY-REPAIR-20261013-R7.md) · [机器逐题台账](reports/ROUND7-COVERAGE-20261013.json)\n'
 p.write_text(cur,encoding='utf-8')
 print('R7_ACTUAL_COVERAGE',json.dumps(stats,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
