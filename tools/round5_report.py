#!/usr/bin/env python3
"""Publish actual round-five verification and retain earlier progress history."""
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
from verify_round5_repairs import verify,records
from round4_gap_repair import ROOT

def main():
 result=verify(ROOT);rr=records(ROOT)
 summary_path=ROOT/'reports/REPAIR-SUMMARY-20261012-R5.json'
 summary=json.loads(summary_path.read_text(encoding='utf-8'))
 stat=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
 if len(rr)!=summary['modified_papers'] or result['added_answers']!=summary['answers_added']:
  raise ValueError('Current delivery does not agree with report counts')
 before=summary['recognized_missing_slots_before'];after=before-result['added_answers']
 if after!=summary['remaining_recognized_slots']:raise ValueError('Missing-answer arithmetic is not reproducible')
 if stat['confirmed_missing_original_questions']!=25:raise ValueError('Unexpected tracked objective question count')
 summary.update({'status':'verified','verification':result,
  'files_with_machine_flags':stat['files_with_machine_flags'],
  'priority_year_subject_blanks_remaining':len(json.loads((ROOT/'reports/PRIORITY-MISSING.json').read_text(encoding='utf-8'))),
  'corpus_papers':stat['paper_files']})
 summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 region=collections.Counter(r['path'].split('/')[1] for r in rr)
 lines=['# 第五轮：来源核实后批量补录申论参考答案','',
  '验收批次：2026-10-13（新加坡时间）；起点 `'+summary['baseline']+'`。',
  '',
  '> 本报告统计的是“文档中的参考答案空位”，不是独立真题数。参考答案来自已有来源、并非官方标准答案；题面和材料保持，不以答案存在证明原卷真实性。','',
  '## 实际结果','',
  '| 指标 | 已验收结果 |','|---|---:|',
  f"| 改动的申论文件 | {len(rr)} |",
  f"| 新增来源参考答案位置 | {result['added_answers']} |",
  f"| 用户原始资料转录补入 | {summary['user_sources']['added_user_source_answers']} |",
  f"| 库内同题来源补入 | {result['added_answers']-summary['user_sources']['added_user_source_answers']} |",
  f"| 可解析申论文件 | {summary['parsed_essays']} / 738 |",
  f"| 已识别空答案位置（补前→补后） | {before} → {after} |",
  f"| 未解析申论文件 | {summary['unparsed_essays']} |",
  f"| 全库仍缺行测原题 | {stat['confirmed_missing_original_questions']} |",
  f"| 重点地区年度科目空白 | {summary['priority_year_subject_blanks_remaining']} |",
  f"| 质量机器告警文件 | {stat['files_with_machine_flags']} |",
  '',
  '## 改动文档（逐卷证据见 ROUND5-ANSWERS-20261012.jsonl）','',
  '| 文档 | 已补参考答案题号 | 本卷仍缺题号 |','|---|---|---|']
 for r in sorted(rr,key=lambda x:x['path']):
  p=r['path'];link='../'+quote(p,safe='/')
  lines.append('| ['+p+']('+link+') | '+','.join(str(a['number']) for a in r['added_answers'])+' | '+(','.join(map(str,r['remaining_answer_ids'])) or '无已识别空位')+' |')
 lines+=['','## 地区分布','',
  ', '.join(f'{area} {v}份' for area,v in sorted(region.items(),key=lambda x:(-x[1],x[0]))),'',
  '## 证据边界与下一批次','',
  '- 同年同题：对题干、材料、分值及字数要求分别校验；跨省共用题适用更严格的材料和题干匹配，不把任意省份同年题目直接视为同题。',
  '- 既有材料不改写；所有修复提供可逆差异、固定来源版本与原文哈希。原有答案与题目保留性接受独立验证。',
  '- 原始来源文字是数据，不执行来源嵌入命令。私人来源材料按事先指定的固定GitHub提交版本定位；完整源临时分片不纳入最终main。',
  f"- 仍有 {after} 个识别出的答案位置、{summary['unparsed_essays']} 份尚无法证明结构完整。不得将它们直接换算成独立真题缺失数量。",
  '- 江苏/浙江18道与广东7道行测缺题、重点年度科目缺卷、非重点地区缺卷占位继续保留；没有取得完整同卷题面不补造。',
  '- 对于曾经存在的历史重复记录，“统考”与分卷文件的互相引用需要继续人工复核；每条来源答案只属于参考解读，并不代表考试机关的标准答案。',
  '',
  '验证入口：`reports/REPAIR-SUMMARY-20261012-R5.json`、`reports/ROUND5-ANSWERS-20261012.jsonl`、`reports/ROUND5-UNRESOLVED-20261012.json`。结构和像素校验通过不等于全部试卷逐字认证。','']
 (ROOT/'reports/QUALITY-REPAIR-20261013-R5.md').write_text('\n'.join(lines),encoding='utf-8')
 baseline=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True,encoding='utf-8')
 first=re.search(r'(?m)^## 第三轮：',baseline)
 hist=baseline[first.start():] if first else ''
 # The quality generator owns the earlier overview; restore R3/R4 from the checked-out baseline.
 progress=ROOT/'PROGRESS.md';t=progress.read_text(encoding='utf-8')
 t=re.sub(r'\n## 第三轮：[\s\S]*\Z','',t).rstrip()+'\n'
 if hist:t+='\n'+hist.rstrip()+'\n'
 t+='\n## 第五轮：来源补答案批次（2026-10-13）\n\n'
 t+=f"本轮对 {len(rr)} 份申论补入 {result['added_answers']} 个有来源的完整参考答案位置；补前识别 {before} 个空位，补后仍有 {after} 个，另 {summary['unparsed_essays']} 份无法证明题目/答案结构完整。此为文档位置，不是独立真题数。\n\n"
 t+='行测已标记25题仍缺、重点区年度科目空白10格及47条缺失/待核实占位继续保留，不虚报整卷收录完成。\n\n'
 t+='[第五轮详细逐卷记录](reports/QUALITY-REPAIR-20261013-R5.md) · [第五轮机器结果](reports/REPAIR-SUMMARY-20261012-R5.json)\n'
 progress.write_text(t,encoding='utf-8')
 print('R5_REPORT',json.dumps({'papers':len(rr),'answers':result['added_answers'],'remaining':after,'unparsed':summary['unparsed_essays']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
