#!/usr/bin/env python3
"""Write the fifth-round factual report from delivered receipt bytes."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
from urllib.parse import quote
import round5_bulk as b
from verify_round5_repairs import verify, records

ROOT=b.ROOT
def main():
    checked=verify(ROOT)
    rows=records(ROOT)
    summary_path=ROOT/'reports/REPAIR-SUMMARY-20261012-R5.json'
    info=json.loads(summary_path.read_text(encoding='utf-8'))
    unresolved=json.loads((ROOT/'reports/ROUND5-UNRESOLVED-20261012.json').read_text(encoding='utf-8'))
    stats=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
    assert checked['status']=='passed'
    assert len(rows)==info['modified_papers']
    assert checked['added_answers']==info['answers_added']
    assert checked['added_answers']==102 and len(rows)==41, 'Do not silently widen the audited scope'
    assert info['recognized_missing_slots_before']==901
    assert info['recognized_missing_slots_before']-checked['added_answers']==len(unresolved['parsed_missing'])
    assert len(unresolved['unparsed'])==9
    assert stats['confirmed_missing_original_questions']==25
    info.update({
        'status':'verified', 'verification':checked, 'corpus_papers':stats['paper_files'],
        'machine_flagged_files':stats['files_with_machine_flags'],
        'unparsed_documents_not_certified':len(unresolved['unparsed']),
        'remaining_recognized_slots':len(unresolved['parsed_missing'])
    })
    summary_path.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=[
        '# 第五轮：库内固定版本同题答案补录（2026-10-13）','',
        '本轮仅采用已在 gwy-zhenti 中存在的同题参考答案，按原题题干、给定材料、分值和字数要求匹配，不使用不完整原始资料候选包。不是官方标准答案的真实性认证。','',
        '## 实际改动','',
        '| 已有申论 MD | 补入答案题号 | 仍缺参考答案题号 |',
        '|---|---|---|'
    ]
    for r in rows:
        rel=r['path']
        ids=[a['number'] for a in r['added_answers']]
        lines.append('| ['+rel+'](../'+quote(rel,safe='/')+') | '+str(ids)+' | '+str(r['remaining_answer_ids'])+' |')
    lines += [
        '', '## 本轮已确认的数量','',
        '- 修改既有申论文件 '+str(len(rows))+' 份；补录已存在来源参考答案 '+str(checked['added_answers'])+' 处；不新增试卷，也不改行测。',
        '- 严格与扩展解析器合计识别到 '+str(info['parsed_essays'])+' 份申论，原有缺答案位置 '+str(info['recognized_missing_slots_before'])+'，补录后仍缺 '+str(len(unresolved['parsed_missing']))+'；另有 '+str(len(unresolved['unparsed']))+' 份暂不能安全解析。第四轮仅解析670份，记录676个缺答案位置并有68份未解析；第五轮扩展至729份可解析、9份未解析，新口径原有901个缺位，补102后剩799个。统计基数扩大不代表旧答案被删。',
        '- 已识别内容包括历史重叠卷，不能据此推断唯一真题数量。',
        '- 前四轮修复凭据保持原有字节，逆向还原 R5 修订后连续验证。既有答案 '+str(checked['existing_answers_preserved'])+' 处保持、题目 '+str(checked['original_question_blocks_preserved'])+' 处保持。',
        '- 行测已登记缺题 '+str(stats['confirmed_missing_original_questions'])+' 道（江苏浙江18、广东7），重点年度科目空白 '+str(len(json.loads((ROOT/'reports/PRIORITY-MISSING.json').read_text())))+' 格，另有 '+str(stats['placeholder_files'])+' 个缺失或待核实占位，本轮未消除。',
        '', '## 来源与验收边界','',
        '资料源固定为本仓主分支第四轮提交 69929cdd 的同年同题已有答案，禁止不满足内容和材料高度一致条件的混卷。跨省联考需归一化题干完全相同且材料相似度达到更严门槛；来源不代表官方答案。',
        '每个新增答案均有原卷与来源卷、定位题号、前后哈希、题目及材料匹配凭据。'
        '原有材料/题面保持；原本缺标题者只添加可逆定位标题。',
        '逐项凭据在 reports/ROUND5-ANSWERS-20261012.jsonl；仍缺及9份不能严格解析的目录在 reports/ROUND5-UNRESOLVED-20261012.json。',
        '原始资料镜像 ProfessorZhi/gwy-material-ops 的转写不是官方真题认证来源，且第五轮旧实验分支资料包不完整，因此没有参与本次102处修复。',
        '全库验收状态以 PR 对应的 GitHub Actions 成功日志为准；结构校验、图片可解码不等于已将所有原件逐字核实。',''
    ]
    (ROOT/'reports/QUALITY-REPAIR-20261013-R5.md').write_text('\n'.join(lines),encoding='utf-8')
    old_progress=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True)
    progress_path=ROOT/'PROGRESS.md'
    current=progress_path.read_text(encoding='utf-8')
    current=current.split('\n## 第三轮：',1)[0].split('\n## 第五轮：',1)[0].rstrip()+'\n'
    if '\n## 第三轮：' in old_progress:
        current+='\n## 第三轮：'+old_progress.split('\n## 第三轮：',1)[1].split('\n## 第五轮：',1)[0].rstrip()+'\n'
    current+='\n## 第五轮：已验证同题参考答案补录（2026-10-13）\n\n'
    current+=(str(len(rows))+'份原有申论补入'+str(checked['added_answers'])+'份同题来源参考答案；第1—4轮的正文、旧答案与来源哈希链经逆向验证。'
              '本轮不是官方原件逐字核对。\n\n'
              +str(len(unresolved['parsed_missing']))+'处已识别完整参考答案仍缺，另'+str(len(unresolved['unparsed']))+'份申论尚待解析。'
              '行测原题缺号25、重点年度科目空白10格、其他占位'+str(stats['placeholder_files'])+'项不变。\n\n'
              '[逐卷修复与来源限制](reports/QUALITY-REPAIR-20261013-R5.md) · '
              '[实际验收结果](reports/REPAIR-SUMMARY-20261012-R5.json)\n')
    progress_path.write_text(current,encoding='utf-8')
    priority=ROOT/'reports/PRIORITY-QUALITY-20261012.md'
    text=priority.read_text(encoding='utf-8')
    banner='> 第五轮答题参考答案修补已接续，具体补录以[第五轮逐卷报告](QUALITY-REPAIR-20261013-R5.md)为准；未修试卷不视为完整。'
    if banner not in text:
        pos=text.find('\n')
        text=text[:pos+1]+'\n'+banner+'\n'+text[pos+1:]
        priority.write_text(text,encoding='utf-8')
    print('R5_FINAL_VERIFIED',json.dumps(info,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
