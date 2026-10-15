#!/usr/bin/env python3
"""Replace a demonstrably inconsistent single-choice key with a transparent result."""
from pathlib import Path
import re,json,hashlib
R=Path(__file__).resolve().parents[1];sha=lambda s:hashlib.sha256(s.encode('utf8')).hexdigest()
p=R/'省考/江西/2019/行测-法检.md';old=p.read_text(encoding='utf8');m=re.search(r'(<details>\s*<summary>第 41 题</summary>)(.*?)(</details>)',old,re.S)
assert m and '**答案**：A' in m[2] and '5400' in m[2]
body='''\n\n**参考作答**：按本卷现有题面计算为5400元；四个现有选项均不匹配，不能给出有效单选字母。

**原创校核解析（AI辅助整理，非官方标准答案）**

题面给出2017年10月1日至7日每日工资300元且均上班、未补休；其中10月1、2、3日为国庆法定假日，10月4日为中秋法定假日，其余3日按题设作为休息调假日。按原题采用的法定假日三倍、休息日二倍工资口径，计算为300×4×3+300×3×2=5400元。原选项6300、5100、4500、4800元均与该计算不符。

**来源分歧与纠错**：旧库解析本已算出5400元，却把答案写成A（6300元），存在内部矛盾。用户提供的《2019年江西省法检统一考录公务员笔试〈行测〉真题答案及解析》同题也先标B，随后明确注明“本题出题不严谨，正确答案应当为5400”。本次撤销错误字母A，保留四个来源原选项，未擅自把任何选项改写为5400，也不把不匹配的B（5100元）当成正确答案。

**来源与使用方式**：用户提供的同卷原题PDF转录及同卷答案解析第41题（资料标记“来源：F，整理：杨柳”，机构全称未明确）。本题宜作为计算口径与题源瑕疵辨析题练习；取得可靠原卷或勘误前，不用于单选自动判分。以上只处理本题设定的历史考试计算口径。

'''
new=old[:m.start()]+m[1]+body+m[3]+old[m.end():];p.write_text(new,encoding='utf8',newline='\n')
receipt={'path':p.relative_to(R).as_posix(),'question':41,'before_sha256':sha(old),'after_sha256':sha(new),'old_invalid_key':'A','answer_kind':'题源选项与计算冲突；完整数值参考作答','reference_value':'5400元','original_options_preserved':True,'source':'用户同卷题本与答案解析第41题；来源F，整理杨柳','source_exact_short_note':'本题出题不严谨，正确答案应当为5400','unresolved_boundary':'未取得官方原题/勘误，不伪造一个新的原选项，不给错误单选字母。'}
(R/'reports/FULL-REPAIR-APTITUDE-JIANGXI41-20261015.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(receipt,ensure_ascii=False))
