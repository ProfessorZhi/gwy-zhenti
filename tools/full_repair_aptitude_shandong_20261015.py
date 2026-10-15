#!/usr/bin/env python3
"""Use an explicitly attributed published completion, never claim an official original."""
from pathlib import Path
import re,json,hashlib
R=Path(__file__).resolve().parents[1];sha=lambda s:hashlib.sha256(s.encode('utf8')).hexdigest()
p=R/'省考/山东/2023/行测-统考.md';old=p.read_text(encoding='utf8');front,ans=old.split('## 答案与解析',1)
m=re.search(r'(^## 第 42 题[^\n]*\n)(.*?)(?=^## )',front,re.S|re.M);assert m and '- **A**. 缺失' in m[2]
stem=m[2].split('- **A**.',1)[0].rstrip()
body=stem+'''\n\n> **选项版本说明**：以下采用知乎公开作者2023-08-27讨论文章提供的补充版本。原库及金标尺转录题本的A/C/D写“缺失/略”，B只余“40毫克”，并非完整选项。本补充版可供练习，尚未取得官方印刷原卷逐字认证；作者署名未明确，主页标识为`jing-ye-si-3000`。

- **A**. 60～100毫克
- **B**. 40～100毫克
- **C**. 40～80毫克
- **D**. 50～130毫克

**补充来源**：[知乎公开同题讨论](https://zhuanlan.zhihu.com/p/642333448)，2023-08-27；本库于2026-10-15据公开补充版校对。保留来源性质，不将文章作者的补充内容冒称官方原件。

'''
front=front[:m.start()]+m[1]+body+front[m.end():]
m=re.search(r'(<details>\s*<summary>第 42 题</summary>)(.*?)(</details>)',ans,re.S);assert m
oldbody=m[2];assert '**答案**：B' in oldbody
oldbody=oldbody.replace('**答案**：B','',1).replace('**来源参考解析（非官方标准答案）**','**旧来源转录解析（历史比对）**',1).strip()
body='''\n\n**答案**：B（上述公开补充选项版本）

**原创校核解析（AI辅助整理，非官方标准答案）**

按题设的离散代谢模型，每8小时剩余比例为0.4。设第n次服药刚结束时含药量为Xₙ，则Xₙ₊₁=0.4Xₙ+60，初始X₁=60，因此Xₙ=60(1+0.4+…+0.4ⁿ⁻¹)=100(1−0.4ⁿ)。服药后含药量趋近100毫克，下次服药前为0.4Xₙ，趋近40毫克。

10天约有30个给药周期，0.4³⁰约为1.15×10⁻¹²，与稳态的差已可忽略。相邻两次服药之间的近似含药量范围为40～100毫克，选B。单独的“40毫克”只反映服药前的近似下界，不能表达题目所问的范围。

**推导边界**：这里使用题设的简化数学模型与近似范围，有限次数的精确端点会略低于稳态端点。补充版选项源自上述公开同题文章，解析为本库独立演算。

> 以下旧来源转录仅用于比对：旧题本选项残缺，其末尾将服药前的等比残留近似量当成单一作答值。公式图原样保留，不作为完整范围的替代答案。

'''+oldbody+'\n\n'
ans=ans[:m.start()]+m[1]+body+m[3]+ans[m.end():];new=front+'## 答案与解析'+ans
p.write_text(new,encoding='utf8',newline='\n')
receipt={'path':p.relative_to(R).as_posix(),'question':42,'before_sha256':sha(old),'after_sha256':sha(new),'restored_options':['A','B','C','D'],'source_url':'https://zhuanlan.zhihu.com/p/642333448','source_date':'2023-08-27','source_author':'署名未明确；主页标识jing-ye-si-3000','source_kind':'公开作者补充选项版本，未取得官方原卷逐字认证','answer':'B','original_source_conflict':'金标尺29页PDF第16页A略/B40毫克/C略/D略；原库同样残缺。补充版显式标注版本，不伪装原件。','old_formula_images_preserved':True}
(R/'reports/FULL-REPAIR-APTITUDE-SHANDONG-20261015.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(receipt,ensure_ascii=False))
