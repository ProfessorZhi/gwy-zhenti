#!/usr/bin/env python3
"""Truthful after-R8 readout for the whole essay library; R7 guides do not count as answers."""
from __future__ import annotations
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
import round4_gap_repair as g
from r7_reference_audit import audit
from verify_round8_reference import verify,records
from round8_reference_delivery import ROOT,SUMMARY

def main():
    rr=records(ROOT);result=verify(ROOT)
    rows,failed,requests,counts=audit()
    total=sum(v for key,v in counts.items() if key.endswith('/待补'))
    full=sum(v for key,v in counts.items() if key.endswith('/已收录'))
    flagged=sum(v for key,v in counts.items() if '待复核' in key)
    if len(rows)!=729 or len(failed)!=9 or total!=585:
        raise ValueError('Unexpected full-corpus coverage; refuse false completion statistics: '+str((len(rows),len(failed),total)))
    stat=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
    old=json.loads((ROOT/'reports/REPAIR-SUMMARY-20261013-R7.json').read_text(encoding='utf-8'))
    if old['actual_coverage']['missing_reference_answer_positions']!=592:
        raise ValueError('R7 source baseline mismatched')
    summary=json.loads((ROOT/'reports'/SUMMARY).read_text(encoding='utf-8'))
    summary.update({'status':'verified',
      'baseline':'d6b42d7eff085a01288e4c62514a06bedfeff3de',
      'previous_round7_newly_filled_answers':old['newly_filled_answer_positions'],
      'recognizable_answer_positions':old['actual_coverage']['answer_slots'],
      'readable_answer_positions_after':full,
      'missing_answer_positions_before':592,
      'missing_answer_positions_after':total,
      'other_warning_positions_after':flagged,
      'unparsed_exam_files':len(failed),
      'source_distinction':'AI-authored examples are not reproductions of institutions or scored exam papers',
      'machine_flagged_files':stat['files_with_machine_flags'],
      'round8_verification':result})
    (ROOT/'reports'/SUMMARY).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    locations=collections.defaultdict(collections.Counter)
    for row in rows:
        area=row['identity'][0]
        locations[area]['papers']+=1
        for task in row['tasks']:
            locations[area][task['kind']+'/'+task['status']]+=1
    report=ROOT/'reports/QUALITY-REPAIR-20261013-R8.md'
    lines=[
      '# 第八轮：首批原创示范作答补录与738份申论当前缺口','',
      '基于已合并第七轮738份试卷和阅读导引的最新main，补录不存在参考答案的7个题目位置。',
      '这七处是独立撰写、AI辅助的备考示范答案，不是从同题机构页面复制，也不是有实际成绩证明的考生高分卷。',
      '',
      '| 指标 | 当前验收数 |','|---|---:|',
      '| 全库申论Markdown | 738 |',
      '| 当前可识别题目与答案结构 | 729 |',
      '| 待修题目结构 | 9 |',
      '| 新增完整原创示范作答 | '+str(result['answers_added'])+' |',
      '| 原已有答案/范文可读位置（按最新分类） | '+str(full)+' |',
      '| 缺完整参考答案/范文位置 | 592 → '+str(total)+' |',
      '| 篇幅或布局需复核位置 | '+str(flagged)+' |',
      '| 全库机器告警文件 | '+str(stat['files_with_machine_flags'])+' |',
      '',
      '## 实际完成的试卷与原题号','',
      '| 试卷 | 新增题号 | 同题对照入口性质 |','|---|---|---|'
    ]
    for r in rr:
        path=r['path'];nums=[str(a['number']) for a in r['added_answers']]
        lines.append('| ['+path+'](../'+quote(path,safe='/')+') | '+','.join(nums)+
          ' | 原创学习示范 + 同题机构参考链接（链接内容未复制） |')
    lines+=['','## 仍有缺答案的地区分布（按当前文件而非独立套卷计）','',
            '| 地区 | 可读参考位置 | 仍缺 |','|---|---:|---:|']
    for area,c in sorted(locations.items(),
        key=lambda x:(-sum(v for k,v in x[1].items() if k.endswith('/待补')),x[0])):
        missing=sum(v for k,v in c.items() if k.endswith('/待补'))
        present=sum(v for k,v in c.items() if k.endswith('/已收录'))
        if missing:lines.append('| '+area+' | '+str(present)+' | '+str(missing)+' |')
    lines+=['','## 接续要求','',
      '下阶段优先补齐现有585处答案空位，特别是作文题；已经有答案的作文再寻找不同机构或教学作者的第二份优质范文以供比较。',
      '全部参考答案与范文必须记录题号、同题材料、出处和作者性质；对公开机构网页的受保护正文，只保留核实链接与可允许的简短摘要，或提供独立原创作答，不擅自批量全文转载。',
      '本轮保留R1-R7所有可逆历史记录，新增R8按单卷验收。原有正文及既有答案保持。',
      '第七轮已有完整738份逐卷台账；当前新增R8逐卷参考为本次4份完成项与全库缺项统计，并非宣称全部738份已完成。',
      '',
      '对应机器结果：reports/REPAIR-SUMMARY-20261013-R8.json；校验凭据：reports/ROUND8-ORIGINAL-ANSWERS-20261013.jsonl。','']
    report.write_text('\n'.join(lines),encoding='utf-8')
    original=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True)
    progress=ROOT/'PROGRESS.md';t=progress.read_text(encoding='utf-8')
    hist=re.search(r'(?m)^## 第三轮：',original)
    t=re.sub(r'\n## 第三轮：[\s\S]*\Z','',t).rstrip()+'\n'
    if hist:t+='\n'+original[hist.start():].rstrip()+'\n'
    t+=('\n## 第八轮：补充7处缺失的参考作答（2026-10-13）\n\n'
       '承接第七轮已归档的738卷导引与15处来源参考答文，在江苏2026B和浙江2025A、2026A/C新增7处AI辅助原创示范答案，保留第三方同题对照链接并明确注明未经实考评分。'
       '全库当前可识别的缺完整参考答案/范文位置592→'+str(total)+'，另有9份题目结构待核。'
       '这些是文档内答案位置，不等于独立真题数量。\n\n'
       '[第八轮验收和剩余地区分布](reports/QUALITY-REPAIR-20261013-R8.md) · '
       '[精确数据](reports/REPAIR-SUMMARY-20261013-R8.json)\n')
    progress.write_text(t,encoding='utf-8')
    print('ROUND8_ALL_738',json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
