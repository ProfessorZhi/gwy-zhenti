#!/usr/bin/env python3
"""Generate current report from actual verified records, preserving prior milestones."""
import json,re
from pathlib import Path
from urllib.parse import quote
from verify_round4_repairs import verify,records
from round4_gap_repair import ROOT

def main():
 result=verify(ROOT);rs=records(ROOT)
 summary_path=ROOT/'reports/REPAIR-SUMMARY-20261012-R4.json'
 summary=json.loads(summary_path.read_text(encoding='utf-8'))
 full=[r for r in rs if r['added_answers']];notes=[r for r in rs if r.get('source_notes')]
 unresolved=json.loads((ROOT/'reports/ROUND4-UNRESOLVED-ANSWERS-20261012.json').read_text(encoding='utf-8'))
 stats=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
 summary.update({'status':'verified','modified_papers':len(rs),'papers_with_answers_added':len(full),'source_note_papers':len(notes),'source_note_question_slots':sum(len(r['source_notes']['question_ids']) for r in notes),'complete_reference_answers_added':result['added_existing_source_answers'],'remaining_recognized_answer_slots':len(unresolved['parsed_missing']),'unparsed_documents_not_certified':len(unresolved['unparsed']),'known_xingce_questions_fixed':0,'known_xingce_questions_still_missing':stats['confirmed_missing_original_questions'],'priority_year_subject_blanks_remaining':len(json.loads((ROOT/'reports/PRIORITY-MISSING.json').read_text())),'corpus_papers':stats['paper_files'],'machine_flagged_files':stats['files_with_machine_flags'],'verification':result})
 summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 lines=['# 第四轮：已验证的答案补录与剩余缺口','',f"基线：`{summary['baseline']}`。实际修改{len(rs)}份已有申论，其中{len(full)}份补入{result['added_existing_source_answers']}份已有来源参考答案；另{len(notes)}份仅补外部来源入口及摘要，不计作完整答案。没有新增试卷，没有补入机器生成的范文。",'',
 '## 实际补入的答案','',
 '| 试卷 | 本轮补入题号 | 仍缺完整答案题号 |','|---|---|---|']
 for r in full:lines.append('| ['+r['path']+'](../'+quote(r['path'],safe='/')+') | '+str([a['number'] for a in r['added_answers']])+' | '+str(r['remaining_answer_ids'])+' |')
 lines+=['','答案来自本库已收录的固定版本：同年、同地区、题干、材料、分值与字数限制逐项匹配。跨省联考共用题采用更严格的相同题干及材料覆盖校验，并在正文明确说明来源地区/卷型。这里只补同题答案，不把其他卷型整体视为本卷，不重新声称来源答案必然正确。','',
 '## 找到来源但未按完整答案计数','']
 for r in notes:lines.append('- '+r['path']+'：第'+str(r['source_notes']['question_ids'])+'题已加入来源入口和有限摘要；完整答案缺项仍保留。')
 lines+=['','江苏2026B另定位到[公开参考答案候选](https://sjds.net/595993.html)，该页题干与已收录融合治理题面相应；本轮未将其全文复制入库，也未据此取消该卷来源真实性和答案缺项。','',
 '## 本轮不能宣称已经补齐的部分','',
 f"当前识别了{summary['parsed_essays']}份申论的题目与答案结构；其中修复前识别到{summary['missing_answer_slots_before']}个完整答案缺项，补录后剩余{len(unresolved['parsed_missing'])}个。另有{len(unresolved['unparsed'])}份未通过严格结构解析，不能宣称这些文件完整，也不能把它们全部当作缺答案。上述是文档内答案位置数量，含历史重叠记录，不是独立真题数量。",'',
 f"全库仍有{stats['confirmed_missing_original_questions']}道已经登记的行测原题缺失：江苏/浙江18题、广东7题。本轮行测试卷未改，不能把申论答案补录计作行测补题。10个重点地区年度科目空白及47个缺失/待核实占位没有在本轮消除。",'',
 '本轮继续检查的江苏2024A公开PDF仍包含缺题占位；浙江2020A另一PDF读取超时。目录、文件标题写完整，不是可补入原题的证据。浙江2022申论、江苏2026缺少分卷等仍需可靠题本，不以重复文件或其他年份试题冒充。','',
 '## 验证与追溯','',
 '每个改动都有来源固定版本、同题匹配证据、前后SHA-256、旧答案保持校验及可逆文本差异。正文材料和原题保持；对原来无题目标题的文件，只插入可逆导航标题，保留中文缩进和全部原字句。旧轮次凭据不改写，在临时还原快照中继续验证。','',
 '`ROUND4-ANSWERS-20261012.jsonl` 为逐文件凭据；`ROUND4-UNRESOLVED-ANSWERS-20261012.json` 为仍缺答案及未解析文件；`REPAIR-SUMMARY-20261012-R4.json` 为实际验证统计。全库测试、图片解码、最终提交/合并状态以相应GitHub Actions和PR为准，结构测试不替代逐卷原件认证。','']
 (ROOT/'reports/QUALITY-REPAIR-20261012-R4.md').write_text('\n'.join(lines),encoding='utf-8')
 # cloud_quality.py --build historically generates only R1/R2 sections. Restore the
 # latest R3 summary as an explicit historical milestone before appending R4.
 progress=ROOT/'docs/PROGRESS.md';text=progress.read_text(encoding='utf-8')
 if '## 第三轮：' not in text:text+='\n## 第三轮：已合并申论修复（2026-10-12）\n\n23份申论恢复材料/作答结构，新增3题和5份参考答案；此前早期章节的相应缺项是历史状态。详见[第三轮报告](reports/QUALITY-REPAIR-20261012-R3.md)。\n'
 text=re.sub(r'\n## 第四轮：[\s\S]*\Z','',text)
 text+='\n## 第四轮：当前答案补录（2026-10-12）\n\n'+f"{len(full)}份既有申论补入{result['added_existing_source_answers']}份同题来源参考答案，另{len(notes)}份增加来源入口和摘要（不计完整答案）。本轮未新增行测试题或新试卷。"+'\n\n'+f"仍有{len(unresolved['parsed_missing'])}个已识别完整答案缺项，另{len(unresolved['unparsed'])}份待解析/复核；这不是完整率认证。行测已登记25题、重点年度科目10格、其他47个占位未消除。"+'\n\n[实际逐卷结果](reports/QUALITY-REPAIR-20261012-R4.md) · [当前机器明细](reports/REPAIR-SUMMARY-20261012-R4.json)\n'
 progress.write_text(text,encoding='utf-8')
 priority=ROOT/'reports/PRIORITY-QUALITY-20261012.md';p=priority.read_text(encoding='utf-8')
 replacements={r['path']:r for r in full}
 new=[]
 for line in p.splitlines():
  match=next((r for path,r in replacements.items() if line.startswith('| ['+path+'](')),None)
  if match:
   cols=line.split('|');cols[-3]=' 第四轮：按同题题干及材料证据补入参考答案 '+str([a['number'] for a in match['added_answers']])+' ';cols[-2]=' 仍缺完整参考答案 '+str(match['remaining_answer_ids'])+'；不是官方逐字认证 ';line='|'.join(cols)
  new.append(line)
 if '> 第四轮已接续' not in p:new.insert(2,'> 第四轮已接续实际答案补录；其他未修范围继续保留。详见[第四轮报告](QUALITY-REPAIR-20261012-R4.md)。')
 priority.write_text('\n'.join(new)+'\n',encoding='utf-8')
 print('R4_VERIFIED_SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
