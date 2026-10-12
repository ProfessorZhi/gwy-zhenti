#!/usr/bin/env python3
"""R9 delivery summary from actual MD references, never count guide-only entries."""
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
from r7_reference_audit import audit
from round9_reference_delivery import ROOT,SUMMARY
from verify_round9_reference import verify,records

def main():
    proof=verify(ROOT);rs=records(ROOT)
    rows,failed,requests,counts=audit()
    remaining=sum(num for key,num in counts.items() if key.endswith('/待补'))
    present=sum(num for key,num in counts.items() if key.endswith('/已收录'))
    flagged=sum(num for key,num in counts.items() if '待复核' in key)
    if len(rows)!=729 or len(failed)!=9 or remaining!=574:
        raise ValueError('Current actual answer statuses no longer match R8 baseline: '+str((len(rows),len(failed),remaining)))
    old=json.loads((ROOT/'reports/REPAIR-SUMMARY-20261013-R8.json').read_text(encoding='utf-8'))
    if old['missing_answer_positions_after']!=585:
        raise ValueError('Unexpected prior answer coverage')
    sum_path=ROOT/'reports'/SUMMARY
    s=json.loads(sum_path.read_text(encoding='utf-8'))
    stats=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
    s.update({'status':'verified','baseline':'8c23683610441d82836b907e20c586f2b4622646',
       'missing_answers_before':585,'missing_answers_after':remaining,'all_essay_MD':738,
       'parsed_exam_MD':len(rows),'unparsed_exam_MD':len(failed),
       'now_readable_reference_positions':present,'body_or_layout_warnings':flagged,
       'new_full_length_example_essays':3,'new_short_question_references':8,
       'machine_flagged_files':stats['files_with_machine_flags'],
       'verification':proof,'scope':'Original AI-assisted training answers only, with public same-paper comparison links.'})
    sum_path.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    md=['# 第九轮：上海、重庆、安徽申论整卷答案补全','',
        '以R8已验收的738份申论资料为基线。三份此前所有识别题目均未收录完整作答的试卷，本轮每题单独写作备考参考答案；包括3篇按原卷字数要求完成的议论文范文。此处不把原创写作伪称机构原文或有真实分数证明的考场高分卷。','',
        '| 验收事项 | 数量 |','|---|---:|',
        '| 本次完整参考作答和范文 | 11 |',
        '| 其中作文范文 | 3 |',
        '| 实际修改既有试卷MD | 3 |',
        '| 已识别全库仍缺完整参考答案 | 585 → '+str(remaining)+' |',
        '| 尚需核实题目结构 | 9份 |',
        '| 仍需复核已收录参考篇幅／布局 | '+str(flagged)+'处 |',
        '| 全库机器质量告警 | '+str(stats['files_with_machine_flags'])+'份 |',
        '',
        '## 逐卷实得','',
        '| 试卷 | 本轮补入 | 原卷字数和历史来源保护 |','|---|---|---|']
    for r in rs:
        rel=r['path'];link='../'+quote(rel,safe='/')
        md.append('| ['+rel+']('+link+') | '+', '.join('第'+str(a['number'])+'题' for a in r['added_answers'])+
            ' | 原材料和题面原字保留；完整来源、作者性质和字数经过校验 |')
    md+=['','## 重要界限','',
         '题本与机构同题网页链接仅用于交叉核验考试身份、题目和答题思路，本轮正文是独立AI辅助原创学习稿，未经机构或考试机关阅卷。',
         '新增作文一律符合本轮定义的字数范围（上海800—1000字，重庆与安徽1000—1200字），不代表真实得分。',
         '每份MD的R7阅读导引按新的已收录状态刷新，支持第1至各题答案锚点；旧材料、给定资料和既有参考答案均未重写。',
         '后续仍需为剩余缺项查找机构优质同题答案与范文，同时重点关注重庆、安徽、深圳、江西等缺项密集地区；没有真实来源的实考高分声称一律不使用。',
         '逐题前后哈希和可逆记录：reports/ROUND9-ORIGINAL-ANSWERS-20261013.jsonl；机器验收：reports/REPAIR-SUMMARY-20261013-R9.json。','']
    (ROOT/'reports/QUALITY-REPAIR-20261013-R9.md').write_text('\n'.join(md),encoding='utf-8')
    prog=ROOT/'PROGRESS.md';t=prog.read_text(encoding='utf-8');original=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True)
    marker=original.find('## 第三轮：')
    if marker!=-1:
        t=re.sub(r'\n## 第三轮：[\s\S]*\Z','',t).rstrip()+'\n\n'+original[marker:].rstrip()+'\n'
    t+='\n## 第九轮：三份此前无参考答案的申论整卷补录（2026-10-13）\n\n'
    t+='上海2019行政执法卷、重庆2024一卷、安徽2026A卷，每卷每题补有据的AI辅助原创完整示范，合计11份参考作答（其中3篇完整议论文），同题机构网页与题本仅作核对来源。'
    t+='本轮全库识别缺完整答案从585降至'+str(remaining)+'；另有9份题目结构待核，当前答卷参考答案可用率不代表官方阅卷认证。\n\n'
    t+='[第九轮逐卷修复](reports/QUALITY-REPAIR-20261013-R9.md) · [可复核修复数据](reports/REPAIR-SUMMARY-20261013-R9.json)\n'
    prog.write_text(t,encoding='utf-8')
    print('R9_REPORTED',json.dumps(s,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
