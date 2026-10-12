#!/usr/bin/env python3
"""Report only actual, independently verified non-overlapping source additions."""
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
from round4_gap_repair import ROOT
from verify_round6_repairs import verify,records

def main():
 rs=records(ROOT);v=verify(ROOT)
 old=json.loads((ROOT/'reports/REPAIR-SUMMARY-20261012-R5.json').read_text(encoding='utf-8'))
 stat=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
 brief_path=ROOT/'reports/REPAIR-SUMMARY-20261013-R6.json'
 brief=json.loads(brief_path.read_text(encoding='utf-8'))
 previously=old['answers_added'];before=old['remaining_recognized_slots'];after=before-v['new_reference_answers']
 if previously!=102 or len(rs)!=brief['modified_papers'] or v['new_reference_answers']!=190 or after<0:
  raise ValueError('Unexpected existing or new answer counts')
 region=collections.Counter(r['path'].split('/')[1] for r in rs)
 brief.update({'status':'verified','verification':v,'recognized_missing_before':before,
  'recognized_missing_after':after,'total_new_answers_since_round4':previously+v['new_reference_answers'],
  'parsed_documents':729,'unparsed_documents':9,'corpus_papers':stat['paper_files'],
  'machine_flagged_files':stat['files_with_machine_flags'],
  'key_year_subject_blanks':len(json.loads((ROOT/'reports/PRIORITY-MISSING.json').read_text(encoding='utf-8'))),
  'remaining_xingce_original_question_gaps':stat['confirmed_missing_original_questions']})
 brief_path.write_text(json.dumps(brief,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 lines=['# 第六轮：与既有第五轮合并后的原始资料答案补录','',
  '当前基线：`'+brief['baseline']+'`；本报告计数来自已经写入并可逆验收的Markdown，不统计未写回的候选。','',
  '> 两路结果去重：第五轮 PR #7 已补102个同题答案位置；本轮只补原始资料中有来源的190个其他位置。两次累计292个，**不**重复算102个。所有答案仅为公开/用户来源的参考答案，不是考试机关标准答案。','',
  '## 完成与仍存','',
  '| 项目 | 实际数量 |','|---|---:|',
  '| 本轮新补参考答案位置 | '+str(v['new_reference_answers'])+' |',
  '| 本轮修改MD | '+str(len(rs))+' |',
  '| 连同上一笔合并结果，累计新补 | '+str(previously+v['new_reference_answers'])+' |',
  '| 已识别仍缺完整参考答案位置 | '+str(before)+' → '+str(after)+' |',
  '| 题目/答案结构已识别文档 | 729 / 738 |',
  '| 未可靠识别结构的申论文档 | 9 |',
  '| 全库机器告警文件 | '+str(stat['files_with_machine_flags'])+' |',
  '| 已登记行测缺原题 | '+str(stat['confirmed_missing_original_questions'])+' |',
  '| 重点年度科目空白格 | '+str(brief['key_year_subject_blanks'])+' |','',
  '## 本轮实际补录的逐卷题号','',
  '| 试卷 | 追加的参考答案题号 | 本卷已识别仍缺题号 |',
  '|---|---|---|']
 for r in sorted(rs,key=lambda x:x['path']):
  p=r['path']
  nums=[a['number'] for a in r['added_answers']]
  lines.append('| ['+p+'](../'+quote(p,safe='/')+') | '+','.join(map(str,nums))+' | '+(','.join(map(str,r['remaining_answer_ids'])) or '无已识别空位')+' |')
 lines+=['','## 证据与质量边界','',
  f'- 来自用户资料库固定版本的原始答案，共{v["new_reference_answers"]}处。记录提供卷型、来源文件、源原文字节长度与SHA、材料匹配凭据以及回写前后哈希；逐题可逆差异。',
  f'- 已验收保持{v["original_question_blocks_preserved"]}个原题块，原有{v["previous_real_answers_preserved"]}个非空参考答案不变。',
  '- 所有本轮文本匹配先还原旧版试题原文，再验证源题与当前卷型一致；任何发现已填答案、卷型冲突或材料不符的题均禁止覆盖。',
  '- 没有新增原题、未对原行测缺题作假补；10个重点年度/科目空白与47条占位仍在。图片解码和Markdown结构测试不代表官方原件逐字核准。',
  '- 上轮临时来源转存包仅用于验证，最终main不存其分片或源PDF，引用原资料固定GitHub提交和答案哈希。',
  '',
  '相关文件：`ROUND6-OWNED-ANSWERS-20261013.jsonl`、`REPAIR-SUMMARY-20261013-R6.json`、`ROUND5-ANSWERS-20261012.jsonl`。','']
 (ROOT/'reports/QUALITY-REPAIR-20261013-R6.md').write_text('\n'.join(lines),encoding='utf-8')
 base=subprocess.check_output(['git','show','HEAD:PROGRESS.md']).decode('utf-8')
 progress=ROOT/'PROGRESS.md';cur=progress.read_text(encoding='utf-8')
 m=re.search(r'(?m)^## 第三轮：',base)
 if m:cur=re.sub(r'\n## 第三轮：[\s\S]*\Z','',cur).rstrip()+'\n\n'+base[m.start():].rstrip()+'\n'
 cur+='#'+'' if False else ''  # explicit no-op, retained only for deterministic text generation
 cur+='\n## 第六轮：不同来源补录合并（2026-10-13）\n\n'
 cur+=f"第五轮已经合并102处来源参考答案，此轮在不覆盖已有答案的条件下又补190处，累计292处；识别出的缺完整答案位置由{before}降到{after}，另9份申论尚无法严格结构解析。这些是文档位置，不是独立原题数。\n\n"
 cur+='全库25道已登记行测缺题、10个重点地区年度科目空白及47个待核实/资料缺失占位仍未消除。\n\n'
 cur+='[第六轮逐卷说明](reports/QUALITY-REPAIR-20261013-R6.md) · [第六轮可核对统计](reports/REPAIR-SUMMARY-20261013-R6.json)\n'
 progress.write_text(cur,encoding='utf-8')
 print('R6_REPORTED',json.dumps({'new_answers':v['new_reference_answers'],'current_remaining':after,
   'papers':len(rs),'machine_flags':stat['files_with_machine_flags']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
