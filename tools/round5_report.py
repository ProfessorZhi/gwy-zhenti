#!/usr/bin/env python3
"""Generate an auditable Round 5 delivery report from verified GitHub files."""
from __future__ import annotations
import json,re,subprocess
from pathlib import Path
from urllib.parse import quote
import round5_bulk as b
from verify_round5_repairs import verify,records

ROOT=b.ROOT
def main():
 result=verify(ROOT)
 if result['status']!='passed':raise ValueError('Unverified Round 5 receipts')
 rs=records(ROOT)
 paper_paths={r['path'] for r in rs}
 if len(paper_paths)!=len(rs):raise ValueError('Duplicate target papers')
 summary_path=ROOT/'reports/REPAIR-SUMMARY-20261012-R5.json'
 s=json.loads(summary_path.read_text(encoding='utf-8'))
 papers,bad,plans,left,diag=b.scan()
 remaining=sum(len(p['missing']) for p in papers)
 if s['answers_added']!=result['added_answers'] or s['modified_papers']!=len(rs):raise ValueError('Delivery counts do not match receipts')
 if s['recognized_missing_slots_before']-result['added_answers']!=remaining:raise ValueError('Missing-answer position arithmetic drift')
 s.update({'status':'verified','unparsed_essays_after':len(bad),'parsed_essays_after':len(papers),'remaining_recognized_answer_slots':remaining,'remaining_unparsed_files':len(bad),'verification':result,'documented_supplement':'reports/QUALITY-REPAIR-20261013-R5.md','official_original_certification':False})
 summary_path.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
 rows=['# 第五轮：同题可靠来源参考答案补全与剩余缺口','',
       '全部操作在GitHub仓库及GitHub托管运行器完成。只搬运本库既有来源答案，不制造答案或补上缺失的原题。',
       '',
       '| 项目 | 结果 |','|---|---:|',
       f"| 实际修改申论MD | {len(rs)} 份 |",
       f"| 实际补入来源参考答案 | {result['added_answers']} 份 |",
       f"| 保留旧答案 | {result['existing_answers_preserved']} 份 |",
       f"| 保持作答题块结构 | {result['original_question_blocks_preserved']} 块 |",
       f"| 可识别申论文档 | {len(papers)} 份 |",
       f"| 尚未严格解析 | {len(bad)} 份 |",
       f"| 当前已识别、但缺完整答案的文档题位 | {remaining} 个 |",
       '',
       '以上缺答案数量是**文档中可识别的答案位置**，含历史重复/分卷记录，不是独立原题个数，也不等于整卷真实性已认证。',
       '','## 实际修改的题目','',
       '| 文档 | 补入题号 | 本卷剩余缺答案题号 |','|---|---|---|']
 for r in rs:
  rel=r['path']
  additions=[a['number'] for a in r['added_answers']]
  rows.append('| ['+rel+'](../'+quote(rel,safe='/')+') | '+str(additions)+' | '+str(r['remaining_answer_ids'])+' |')
 rows+=['','## 可追溯性与限定',
        '',
        '- 每份答案保留原有固定提交版本链接及同题、材料相似度、分值/字数限制对照。',
        '- 跨省联考共用题需更严格匹配；只复用同一题的参考答案，不把其他省试卷拼成本省试卷。',
        '- 每个MD都有更改前后SHA-256及可逆差异；验证器先还原本轮修改，再执行历史第一至第四轮验收。',
        '- 完整题干、给定材料和先前已有答案保持不变；原本不带答题标题的资料只额外增加可逆导航。',
        '- 数据来自已有公开/机构整理参考答案，不是官方标准答案，亦不保证官方原卷逐字完整。',
        '',
        '## 尚存缺口',
        '',
        f"- 仍有 {remaining} 个当前可识别的申论缺答案题位，另有 {len(bad)} 份申论文档需要逐个核实结构。",
        '- 25道已知缺失行测原题仍未修复（江苏/浙江18道、广东7道）。',
        '- 10个重点地区年度科目空白及47条非重点地区缺失/待核实登记本轮未消除。',
        '- 此轮没有取得足以可靠恢复上述缺失原题或整卷的独立材料，因此不以占位、跨卷题替代。',
        '',
        '## 凭据',
        '',
        '- `ROUND5-ANSWERS-20261012.jsonl`：逐卷原内容、目标题号及来源答案哈希的可逆记录。',
        '- `ROUND5-UNRESOLVED-20261012.json`：逐题缺答案原因和解析异常。',
        '- `REPAIR-SUMMARY-20261012-R5.json`：从当前实际文件及凭据计算的数据。',
        '- GitHub Actions 的运行日志：单元测试、机器内容检查、历史修复凭据及全量图片解码。',
        '']
 (ROOT/'reports/QUALITY-REPAIR-20261013-R5.md').write_text('\n'.join(rows),encoding='utf-8',newline='\n')
 progress=ROOT/'PROGRESS.md';cur=progress.read_text(encoding='utf-8')
 old=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True,encoding='utf-8')
 history_marker='## 第三轮：'
 if history_marker in old and history_marker not in cur:
  cur=cur.rstrip()+'\n\n'+old[old.index(history_marker):].rstrip()+'\n'
 cur=re.sub(r'\n## 第五轮：[\s\S]*\Z','',cur)
 cur=cur.rstrip()+'\n\n## 第五轮：申论同题答案补全（2026-10-13）\n\n'
 cur+=f"已实际修改 {len(rs)} 份申论，补入 {result['added_answers']} 份仓库内同题可靠来源参考答案；不制造原题。\n\n"
 cur+=f"当前识别 {len(papers)} 份申论及 {remaining} 个仍缺完整答案的文档题位；另有 {len(bad)} 份结构未严格解析。这些数字不是独立原题缺口或整卷验真。\n\n"
 cur+='25道已确认行测缺题、10个重点年度科目空白和47条占位本轮继续保留。\n\n'
 cur+='[第五轮逐卷实际结果](reports/QUALITY-REPAIR-20261013-R5.md) · [当前机器清单](reports/REPAIR-SUMMARY-20261012-R5.json)\n'
 cur=cur.replace('更新批次：2026-10-12。','更新批次：2026-10-13。',1)
 progress.write_text(cur,encoding='utf-8',newline='\n')
 p=ROOT/'reports/PRIORITY-QUALITY-20261012.md'
 if p.exists():
  lines=p.read_text(encoding='utf-8').splitlines()
  relevant={r['path']:r for r in rs if r['path'].startswith(('国考/','省考/江苏/','省考/浙江/'))}
  new=[]
  for line in lines:
   matches=[r for path,r in relevant.items() if line.startswith('| ['+path+'](')]
   if matches:
    r=matches[0];cols=line.split('|')
    if len(cols)>=6:
     cols[-3]=' 第五轮补答案 '+str([a['number'] for a in r['added_answers']])+' '
     cols[-2]=' 剩余缺答案 '+str(r['remaining_answer_ids'])+'；仍未官方逐字认证 '
     line='|'.join(cols)
   new.append(line)
  if '> 第五轮补答案' not in '\n'.join(new):new.insert(2,'> 第五轮补答案的已核实范围见[最新逐卷报告](QUALITY-REPAIR-20261013-R5.md)，其余质量限定继续保留。')
  p.write_text('\n'.join(new)+'\n',encoding='utf-8',newline='\n')
 print('R5_FINAL_REPORT',json.dumps({'papers':len(rs),'answers':result['added_answers'],'remaining_slots':remaining,'unparsed':len(bad)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
