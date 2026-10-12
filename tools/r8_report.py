#!/usr/bin/env python3
"""Report independently verifiable R8 content; do not overstate 738-paper progress."""
import json,re,subprocess
from pathlib import Path
from urllib.parse import quote
from round4_gap_repair import ROOT
from verify_round8_priority import verify,records
def main():
 stat=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
 rs=records(ROOT);v=verify(ROOT)
 by={r['path']:r for r in rs}
 if len(by)!=len(rs) or len(rs)!=4 or v['original_illustrative_answers']!=7:raise ValueError('R8 unexpected write count')
 lines=['# 第八轮：江苏2026B与浙江2025/2026重点申论参考练习稿','',
 '本轮确实写入原有四份Markdown，共7个原先留空的参考作答位置。它们是依据本卷材料独立撰写的练习稿，非外部机构原文、非实考高分答卷，也不代替原卷真实性审计。','',
 '## 实际新增','',
 '| 试卷 | 新补题号 | 作答性质 |','|---|---|---|']
 for r in rs:
  p=r['path'];label='、'.join(str(a['number']) for a in r['new_study_answers'])
  lines.append('| ['+p+'](../'+quote(p,safe='/')+') | '+label+' | AI辅助原创练习参考作答，附可访问的同题机构/网传来源对照链接 |')
 lines+=['','## 参考答案和高分范文的区分','',
 '有公开参考范文不等于有实考成绩证明。本批原稿既不署名为机构标准答文，也不声称获真实考场评分。来源链接帮助复核同题和比较不同论证，不能被当作本批原创文字的逐字发表来源。',
 '',
 '江苏2026B四题涵盖概括、AI城管评析、街区治理对策和融合执法议论文，浙江2025A和浙江2026A/C补的是指定题号的短评。材料引用、写作任务和字数约束已在写入前检查。',
 '',
 '## 验收和剩余','',
 f"R8回读验收通过：{v['original_question_blocks_preserved']}个原题块保持不变，{v['existing_reference_answers_preserved']}份已有非空答案未被覆盖；七份新增答文SHA与明示来源链接可复核。",
 f"当前共 {stat['paper_files']} 份试卷文件。机器告警 {stat['files_with_machine_flags']} 份；仍存在此前报告标记的行测原题缺号、年度/科目覆盖空白、参考答案与范文缺口。本轮不把个人练习稿误计为机构高分范文。",
 '',
 '源码与凭据：tools/data/r8-priority-reference-drafts.json、reports/ROUND8-PRIORITY-ESSAY-20261013.jsonl、tools/verify_round8_priority.py。',
 '']
 (ROOT/'reports/QUALITY-REPAIR-20261013-R8.md').write_text('\n'.join(lines),encoding='utf-8')
 progress=ROOT/'PROGRESS.md';t=progress.read_text(encoding='utf-8')
 base=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True,encoding='utf-8')
 marker=re.search(r'(?m)^## 第三轮：',base)
 t=re.sub(r'\n## 第三轮：[\s\S]*\Z','',t).rstrip()+'\n'
 if marker:t+='\n'+base[marker.start():].rstrip()+'\n'
 t+='\n## 第八轮：重点同题参考作答（2026-10-13）\n\n'
 t+='江苏2026申论B类四题、浙江2025申论A类第2题、浙江2026申论A/C类第2题共7处空位，增补独立原创练习参考作答，并附机构/网传同题原文阅读入口；不冒充高分实考卷或机构范文原文。原题及已有答案保持。\n\n'
 t+='[实际新增逐卷明细](reports/QUALITY-REPAIR-20261013-R8.md)；全库其他未解决缺项继续保留，不能宣称738份全部参考答案已齐。\n'
 progress.write_text(t,encoding='utf-8')
 print('R8_REPORTED',json.dumps({'papers':len(rs),'answers':v['original_illustrative_answers'],'machine_flags':stat['files_with_machine_flags']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
