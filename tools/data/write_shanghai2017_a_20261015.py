import json,re,sys,hashlib,uuid,os
from pathlib import Path
from urllib.parse import quote
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
sha=lambda t:hashlib.sha256(t.encode()).hexdigest();ds=json.loads((ROOT/'tools/data/shanghai-2017-full-source-packets-a-20261015.json').read_text(encoding='utf8'))
rp=ROOT/'reports/FULL-REPAIR-SHANGHAI-2017AB-A-20261015.jsonl'
for d in ds:
 p=ROOT/d['path'];old=p.read_text(encoding='utf8');op=b.parse(old,d['path'])
 if len(op['questions'])==4 and 'FULL-REPAIR-SHANGHAI-2017AB-A' in old:print('Already applied',d['path']);continue
 before_dir=ROOT/'reports/FULL-REPAIR-SHANGHAI-2017AB-A-BEFORE-20261015';before_dir.mkdir(exist_ok=True);bp=before_dir/(d['variant']+'.md')
 if not bp.exists():bp.write_bytes(old.encode())
 url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+d['source_revision']+'/'+quote(d['source_relative_path'],safe='/')
 text='---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in {'考试':'省考','地区':'上海','年份':'2017','科目':'申论','卷型':d['variant']+'类','真题性质':'机构整理/考生回忆真题，非官方原件','命题形式':'单独命题','来源':['用户已有同年完整原始资料'],'来源整卷':url,'来源整卷SHA256':d['source_sha256'],'实有题数':4,'对照题本题量':4,'给定材料段数':len(d['materials']),'题目分值':[20,20,20,40],'已收录参考答案题号':[1,2,3,4],'缺参考答案题号':[],'缺失原题号':[],'题号口径':'按同年完整分卷原题序恢复；旧源序题号不作为卷内原号','校验状态':'2026-10-15据用户已有完整题本恢复材料与4道原题及完整参考正文；非官方逐字认证','恢复凭据':'reports/FULL-REPAIR-SHANGHAI-2017AB-A-20261015.jsonl'}.items())+'---\n# 2017年上海市公务员考试申论（'+d['variant']+'类）\n\n'
 text+='> 本卷以用户已有完整同年分卷原稿恢复。参考答文为原稿所附版本，未署名；本次仅做页码、标题和段落校勘，不声称官方标准或实考高分。\n\n[原稿（固定版本）]('+url+')\n\n'
 if d['instructions']:text+='## 考试注意事项\n\n'+d['instructions']+'\n\n'
 for m in d['materials']:text+='## 给定资料 '+str(m['number'])+'\n\n'+m['text']+'\n\n'
 text+='## 作答要求\n\n'
 for n,q in d['questions'].items():text+='## 第 '+n+' 题\n\n'+q+'\n\n'
 text+='## 答案与解析\n\n';metrics=[]
 for n,q in d['questions'].items():
  a=d['source_answers'][n]
  a=a.replace('公共服务补短板群众满意是追求近年来','公共服务补短板 群众满意是追求\n\n近年来').replace('弘扬工匠精神实现民族复兴中国曾','弘扬工匠精神 实现民族复兴\n\n中国曾')
  e=dict(answer=a,attribution_kind='owned_source',author='原资料未署名；本次仅作出版页码、标题及段落校勘',sources=[dict(title='用户已有同题原参考资料（固定版本）',url=url)])
  nc=validate_answer(q,e);metrics.append(dict(number=int(n),characters=nc,kind='owned_source',answer_sha256=sha(a)));text+='<details>\n<summary>第 '+n+' 题</summary>\n\n'+render_answer(e)+'\n\n</details>\n\n'
 text=text.replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷');text,layout=format_essay(text,d['path']);nd=b.parse(text,d['path']);assert len(nd['questions'])==4 and len(nd['answers'])==4
 mapped=[]
 for on,oq in op['questions'].items():
  nn,sim=max(((nn,SequenceMatcher(None,b.qkey(oq),b.qkey(qq),autojunk=False).ratio()) for nn,qq in nd['questions'].items()),key=lambda x:x[1]);assert sim>.9,(d['variant'],on,sim);mapped.append(dict(old_number=on,new_number=nn,similarity=sim))
 tmp=p.with_name(p.name+'.2017-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(text.encode());assert sha(p.read_text(encoding='utf8'))==sha(old);os.replace(tmp,p);assert sha(p.read_text(encoding='utf8'))==sha(text)
 rec=dict(path=d['path'],before_sha256=sha(old),before_text=old,after_sha256=sha(text),source_path=d['source_path'],source_revision=d['source_revision'],source_sha256=d['source_sha256'],source_git_blob_verified=True,materials=len(d['materials']),questions=4,answers=metrics,old_to_real_numbers=mapped,layout=layout)
 prior=rp.read_text(encoding='utf8') if rp.exists() else '';rp.write_text(prior+json.dumps(rec,ensure_ascii=False)+'\n',encoding='utf8');print(d['path'],metrics,mapped)
