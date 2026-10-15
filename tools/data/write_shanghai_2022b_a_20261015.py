import json,re,sys,hashlib,os,uuid
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
d=next(x for x in json.loads((ROOT/'tools/data/shanghai-b-full-source-packets-a-20261015.json').read_text(encoding='utf8')) if x['year']==2022)
url='https://github.com/ProfessorZhi/gwy-material-ops/blob/95676de3a494730fdcacd43416fd51d6bed48ab6/'+quote(d['source_relative_path'],safe='/')
text='''---
考试: "省考"
地区: "上海"
年份: "2022"
科目: "申论"
卷型: "B类"
真题性质: "机构整理/考生回忆真题，非官方原件"
命题形式: "单独命题"
来源: ["用户已有原始资料"]
题号口径: "按完整B卷作答要求顺序恢复4题；不是旧统考桶源序"
实有题数: 4
对照题本题量: 4
给定材料段数: 15
题目分值: [20, 20, 20, 40]
缺失原题号: []
已收录参考答案题号: [1, 2, 3, 4]
缺参考答案题号: []
校验状态: "2026-10-15据用户已有同年B卷完整资料恢复材料15则及4题；机构同题网页交叉核对；不代表官方原件逐字认证"
恢复凭据: "reports/FULL-REPAIR-SHANGHAI-2022B-A-20261015.json"
---
# 2022年上海市公务员考试申论（B类）

> 本卷以用户已有完整B卷转录为题面依据，补全旧“统考”桶未收录的第1—3题。机构参考版本不是官方标准答案，也未经实考评分。

'''
text+='[原始资料（固定版本）]('+url+')\n\n[同年同卷题面交叉对照](https://www.aipta.com/article/3663.html)\n\n'
for m in d['materials']:text+='## 给定资料 '+str(m['number'])+'\n\n'+m['text']+'\n\n'
text+='## 作答要求\n\n'
for n,q in d['questions'].items():text+='## 第 '+str(n)+' 题\n\n'+q+'\n\n'
text+='## 答案与解析\n\n';metrics=[]
for n,q in d['questions'].items():
 a=d['source_answers'][n]
 if n=='4':a=a.replace('推进一体化建设，引领高质量发展习近平总书记','推进一体化建设，引领高质量发展\n\n习近平总书记')
 e=dict(answer=a,attribution_kind='owned_source',author='原资料未署名；本次仅作页码、材料编号及段落校勘',sources=[dict(title='用户已有同题参考资料（固定版本）',url=url)])
 count=validate_answer(q,e);metrics.append(dict(number=int(n),characters=count,answer_sha256=hashlib.sha256(a.encode()).hexdigest()))
 text+='<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+render_answer(e)+'\n\n</details>\n\n'
text=text.replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷')
text,_=format_essay(text,d['path']);check=b.parse(text,d['path']);assert len(check['questions'])==4 and len(check['answers'])==4
p=ROOT/d['path'];assert not p.exists(),str(p)
tmp=p.with_name(p.name+'.new-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(text.encode('utf8'));assert not p.exists();os.replace(tmp,p)
receipt=dict(path=d['path'],source_path=d['source_path'],source_sha256=d['source_sha256'],after_sha256=hashlib.sha256(text.encode()).hexdigest(),materials=len(d['materials']),questions=4,score_sum=100,answers=metrics,old_bucket=d['old_bucket_path'],bucket_matching_tasks=d['bucket_matching_tasks'],old_bucket_preserved=True,source_cleaning=d['cleaning'],cross_source='https://www.aipta.com/article/3663.html')
(ROOT/'reports/FULL-REPAIR-SHANGHAI-2022B-A-20261015.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(receipt,ensure_ascii=False))
