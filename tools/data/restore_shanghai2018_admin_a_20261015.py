import re,json,sys,hashlib,uuid,os
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
sha=lambda t:hashlib.sha256(t.encode()).hexdigest()
src=json.loads((ROOT/'tools/data/shanghai2018-administrative-crosscheck-20261015.json').read_text(encoding='utf8'));t=src['text'];at=t.rfind('三、作答要求');assert at>1000
mr=t[:at];qh=list(re.finditer(r'(?m)^([1-3])\.',t[at:]));assert len(qh)==3
qs={int(m[1]):t[at:][m.start():qh[i+1].start() if i+1<3 else None].split('注：篇幅有限')[0].strip() for i,m in enumerate(qh)}
mh=list(re.finditer(r'(?m)^材料([1-5])\s*$',mr));assert [int(x[1]) for x in mh]==[1,2,3,4,5]
mats=[mr[m.end():mh[i+1].start() if i+1<5 else None].strip() for i,m in enumerate(mh)]
rel='省考/上海/2018/申论-行政执法.md';p=ROOT/rel;old=p.read_text(encoding='utf8');d=b.parse(old,rel)
bucketrel='省考/上海/2018/申论-统考.md';bucket=b.parse((ROOT/bucketrel).read_text(encoding='utf8'),bucketrel)
def main(a):
 a=re.split(r'文章分析|参考答案说明[:：]|\n\s*>\s*(?:出处|来源说明)|\n\s*\[本题(?:既有)?来源记录\]',a,1)[0].strip()
 return a.translate(b.FOLD)
answers={1:main(d['answers'][2]),2:main(d['answers'][1]),3:main(bucket['answers'][1])}
answers[3]=answers[3].replace('建立长效机制 提升社会治理能力\n','建立长效机制 提升社会治理能力\n\n').replace('上海是中国人口规模最大的城市','上海是一座人口规模巨大的超大城市')
text='---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in {'考试':'省考','地区':'上海','年份':'2018','科目':'申论','卷型':'行政执法','真题性质':'机构整理/考生回忆真题，非官方原件','命题形式':'单独命题','来源':['爱真题同年完整题面','库内已有同题参考版本'],'来源整卷':src['url'],'来源整卷SHA256':sha(t),'实有题数':3,'对照题本题量':3,'给定材料段数':5,'题目分值':[25,25,50],'已收录参考答案题号':[1,2,3],'缺参考答案题号':[],'缺失原题号':[],'题号口径':'按同年完整执法卷题序恢复；旧源第1/2题颠倒、作文在统考桶','校验状态':'2026-10-15同年完整题面交叉核对并恢复3题，非官方逐字认证','恢复凭据':'reports/FULL-REPAIR-SHANGHAI-2018ADMIN-A-20261015.json'}.items())+'---\n# 2018年上海市公务员考试申论（行政执法）\n\n[同年完整题面来源]('+src['url']+')\n\n'
text+='## 考试注意事项\n\n'+mr[:mh[0].start()].replace('二、给定材料','').strip()+'\n\n'
for i,mat in enumerate(mats,1):text+='## 给定资料 '+str(i)+'\n\n'+mat+'\n\n'
text+='## 作答要求\n\n'
for n,q in qs.items():text+='## 第 '+str(n)+' 题\n\n'+q+'\n\n'
text+='## 答案与解析\n\n';metrics=[]
for n,q in qs.items():
 donor=rel if n<3 else bucketrel
 e=dict(answer=answers[n],attribution_kind='owned_source' if n<3 else 'ai_revision',author='库内原参考版本未署名；本次仅重排原题号并校勘字形' if n<3 else 'AI辅助修订示范；所据库内原稿未署名',sources=[dict(title='库内原有同题参考稿（固定Git基线）',url='https://github.com/ProfessorZhi/gwy-zhenti/blob/f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab/'+quote(donor,safe='/'))])
 if n==3:e['replace_reason']='作文从混题统考桶归入真实执法卷第3题，正文与解析分离、常见部首字形等价校正，修订城市人口表述避免未经区分口径的最大值断言。'
 count=validate_answer(q,e);metrics.append(dict(number=n,characters=count,kind=e['attribution_kind'],donor_path=donor,donor_number=2 if n==1 else 1,answer_sha256=sha(answers[n])))
 text+='<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+render_answer(e)+'\n\n</details>\n\n'
text=text.replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷');text,layout=format_essay(text,rel)
nd=b.parse(text,rel);assert len(nd['questions'])==3 and len(nd['answers'])==3
before_file=ROOT/'reports/FULL-REPAIR-SHANGHAI-2018ADMIN-A-BEFORE-20261015.md'
if not before_file.exists():before_file.write_bytes(old.encode())
tmp=p.with_name(p.name+'.admin-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(text.encode());assert sha(p.read_text(encoding='utf8'))==sha(old);os.replace(tmp,p)
receipt=dict(path=rel,before_sha256=sha(old),before_text=old,after_sha256=sha(text),source_url=src['url'],source_sha256=sha(t),materials=5,questions=3,scores=[25,25,50],old_question_to_real=[dict(old_number=1,new_number=2),dict(old_number=2,new_number=1)],bucket_to_real=dict(path=bucketrel,old_number=1,new_number=3),answers=metrics,layout=layout)
(ROOT/'reports/FULL-REPAIR-SHANGHAI-2018ADMIN-A-20261015.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in receipt.items() if k!='before_text'},ensure_ascii=False))
