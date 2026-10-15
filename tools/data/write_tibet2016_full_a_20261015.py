"""Restore the explicit owned 125-task reference; reuse only matched original visuals."""
import json,re,sys,hashlib,uuid,os
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from cloud_quality import HEAD_Q,DETAIL,image_refs,resolve_image
from paper_identity import reference_number_issues
from paper_integrity_repair import set_fields
sha=lambda x:hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
D=json.loads((R/'tools/data/tibet2016-complete-owned-source-a-20261015.json').read_text(encoding='utf8'));p=R/D['path'];raw=p.read_bytes();assert sha(raw)==D['before_sha256'];old=raw.decode();newmap={m['original_number']:m['old_number'] for m in D['mapping']};Q={int(n):q for n,q in D['questions'].items()};S={int(n):a for n,a in D['source_answers'].items()}
imgprefix='../../../图片/修复-20261015/西藏2016-MOPS';imagebase='图片/修复-20261015/西藏2016-MOPS';reused=[]
def img(name,alt):
 rel=imagebase+name;f=R/rel;assert f.exists();reused.append(dict(path=rel,sha256=sha(f.read_bytes()),purpose=alt));return '!['+alt+']('+imgprefix+name+')'
def existing(rel,alt):
 f=R/rel;assert f.exists();reused.append(dict(path=rel,sha256=sha(f.read_bytes()),purpose=alt));return '!['+alt+'](../../../'+rel+')'
def clean_source_question(q):
 q=re.sub(r'(?m)^\s*\d{1,2}\s*$','',q)
 q=re.sub(r'(?<![A-Za-z])([A-D])[、．.]',lambda m:'\n\n- **'+m[1]+'**. ',q)
 return re.sub(r'\n{3,}','\n\n',q).strip()
qs={};notes=[]
for n in range(1,126):
 if n in newmap:
  q=D['old_questions'][str(newmap[n])];q=re.sub(r'^\s*<sub>[^<]+</sub>\s*','',q)
 else:q=clean_source_question(Q[n])
 if n==16:q+='\n\n'+img('16-地貌.jpeg','原题地貌照片')
 if n==62:
  stem=re.split(r'(?m)^- \*\*A\*\*',q)[0].strip();q=stem+'\n\n'+'\n\n'.join('- **'+a+'**. '+img('62-选项'+a+'.jpeg','选项'+a+'原根号公式')+' 米' for a in 'ABCD');notes.append(dict(number=62,change='原四项均只剩米；以同题PDF四原公式图恢复，独立几何验证50√3米=选项B，旧键B保留。'))
 if n==69:q+='\n\n'+img('69-题干图.jpeg','正方形与蚂蚁位置原图')+'\n\n'+'\n\n'.join('- **'+a+'**. '+img('69-选项'+a+'.jpeg','面积随时间变化图选项'+a) for a in 'ABCD')
 if n in [71,72,75]:q+='\n\n'+img(str(n)+'-题图与选项.jpeg','完整原图与A至D选项')
 if n==73:q+='\n\n'+img('73-六图分类.jpeg','六个待分类原图')
 if n==74:q+='\n\n'+existing('图片/省考-湖北-2016-行测-统考/题目图/1546a306368bbfc.png','同题原九宫格与四选项')
 if n==85:
  donor=R/'省考/江西/2016/行测-统考.md';s=donor.read_text(encoding='utf8');hs=list(HEAD_Q.finditer(s));i,m=next((i,m) for i,m in enumerate(hs) if int(m[1])==90);z=s[m.end():hs[i+1].start()].strip();z=re.sub(r'^\s*<sub>[^<]+</sub>\s*','',z)
  assert '化学中的自发反应' in z and '维持“给定条件”' in z
  q=z;notes.append(dict(number=85,donor='省考/江西/2016/行测-统考.md',donor_number=90,donor_qid=1797866,donor_sha256=sha(donor.read_bytes()),change='完全同题四选项8种原公式图回接，保持催化/加热/通电/光合顺序；选非答案C保留。'))
  for path in set(re.findall(r'src="\.\./\.\./\.\./([^"]+)"',q)):assert (R/path).exists();reused.append(dict(path=path,sha256=sha((R/path).read_bytes()),purpose='自发反应原公式'))
 if n in [115,120]:
  q=clean_source_question(Q[n]);notes.append(dict(number=n,change='原D选项混入下一组共用材料/页码，按同卷原题分离；被混入的快递文字和租赁标题完整移至共用资料3/4。'))
 qs[n]=q.strip()
materials={}
for m in D['materials']:
 n=m['number'];text=m['text'];text=re.sub(r'(?<=\d)\s+(?=[年月日亿万%])','',text)
 if n==1:text+='\n\n'+img('106-国企资料原文.png','国企资料原页裁区，含全部增长率')
 elif n==2:text='2014年1—11月我国货物运输量及货物周转量统计，供第111—115题使用。\n\n'+img('111-运输资料原表.jpeg','货物运输量及周转量原表')
 elif n==3:text+='\n\n'+existing('图片/省考-浙江-2016-行测-A类/题目图/163388a8bbdeff6.png','2015年2月四企每百万件快递业务有效申诉量原表')+'\n\n'+existing('图片/省考-浙江-2016-行测-A类/题目图/1633883acaad97e.png','四企有效申诉分项环比增长率原表')
 else:text+='\n\n'+img('121-租赁贸易资料原图.jpeg','2014年4月至2015年4月租赁贸易进出口额及增速原图')
 materials[m['before_question']]=dict(number=n,text=text,source_label=m['source_label'],tasks=list(range(m['before_question'],m['before_question']+5)))
header=old[:old.index('\n---',4)+4]+'\n';header=set_fields(header,{'真题性质':'机构整理/考生回忆参考，非官方原件','题号口径':'用户完整125题题本（原稿标来源H）版本顺序；不认证官方原号','对照题本题量':125,'实有题数':125,'缺失原题号':[],'已收录参考答案题号':list(range(1,126)),'缺参考答案题号':[],'缺失选项题号':[],'现仍缺失共用条件题号':[],'新增有据原题号':[69,71,72,74,75],'原卷题号映射记录':'reports/FULL-REPAIR-TIBET2016-COMPLETE-A-20261015.json','题序证据':D['sources'][0]['source_url'],'整卷核验状态':'125题机构参考版本：任务、选项图、4组共用资料和全部参考已核对恢复；与另一120题整理版存在排序及收录差异，非官方题本逐字认证'},'2026-10-15依据完整125题同卷原稿重接120个旧任务与全部旧答案，补回5道有据漏题；逐题匹配原图、原公式与4组共用资料。历史无图/120题声明和全部旧全文保存在恢复凭据。')
out=[header,'# 2016年4月23日西藏公务员考试行测（125题机构整理参考版）','',f'> 题面与参考解析据[用户已有完整题本]({D["sources"][0]["source_url"]})和[同卷参考解析]({D["sources"][1]["source_url"]})恢复；原稿仅标来源H，未明确个人作者，不推定为官方或实考高分资料。','', '> 图像逐题取自同题公开原PDF或库内已存原图。政华公开整理版止于120题，题序和资料收录与本125题原稿不同；仅复用实际匹配的图，不把另一版题号套作本版原号。原旧编号→本版编号、来源SHA、原图凭据及版本差异见恢复报告。','', '> 行测 · 125 题 · 西藏 2016 · 已恢复全部原图及4组共用资料；所有答案为第三方来源参考，非官方标准答案。','']
for n,q in qs.items():
 if n in materials:
  m=materials[n];out += [f'## 共用资料 {m["number"]}（第{m["tasks"][0]}—{m["tasks"][-1]}题）','',m['text'],'']
 out += [f'## 第 {n} 题','',q,'']
out+=['## 答案与解析',''];answer_checks=[]
own69='''固定AD为底，三角形AED的面积等于AD乘E到直线AD的垂直距离再除以2。E沿AB移动时，垂直距离随时间均匀增加，面积从0线性增大；沿BC移动时，高不变，面积保持不变；沿CD向D移动时，高均匀减小，面积线性降至0。三段路程均为10厘米且速度相同，所占时间相等，故应为先上升、再水平、最后下降的梯形折线，对应A。'''
for n in range(1,126):
 if n in newmap:
  body=D['old_answers'][str(newmap[n])]
  # The old inner body is retained exactly; only its enclosing task ID changes.
  letter=re.search(r'\*\*答案\*\*[：:]\s*([A-D])',body)[1];assert letter==S[n]['letter'];kind='preserved_existing_reference'
 else:
  letter=S[n]['letter'];a=S[n]['text'];a=re.sub(r'^\s*[，,]全站正确率[^\n]*','',a).strip();a=re.sub(r'(?m)^\s*\d{1,2}\s*$','',a);a=re.sub(r'\n{3,}','\n\n',a).strip()
  if n==69:a=own69;kind='ai_supplemented_explanation'
  else:kind='owned_complete_same_task_reference'
  body='**答案**：'+letter+'\n\n**'+('AI辅助补足解析' if n==69 else '来源参考解析（非官方）')+'**\n\n'+a+'\n\n> 来源说明：原题及原解析据用户已有同题完整原稿，未署个人作者；新图按实际内容核对，未由答案反推作图。不是官方答案，未经实考评分。第69题独立补足原转录丢失的面积计算关系，未冒称来源作者原文。'
 answer_checks.append(dict(number=n,old_number=newmap.get(n),letter=letter,source_reference_letter=S[n]['letter'],kind=kind,body_sha256=sha(body)))
 out+=['<details>',f'<summary>第 {n} 题</summary>','',body,'','</details>','']
out += ['> 原稿资料编号异文：国企标材料1、运输标材料2、快递又标材料2、租赁标材料3；本次按四个实际题组顺序统一展示为共用资料1—4，原标签及全文仍保存在来源包和恢复凭据。','']
new='\n'.join(out).rstrip()+'\n';ids=list(map(int,HEAD_Q.findall(new)));assert ids==list(range(1,126));assert len(DETAIL.findall(new))==125;assert not reference_number_issues(ids,{'对照题本题量':125,'实有题数':125,'缺失原题号':[]})
refs=image_refs(new);resolved=[resolve_image(D['path'],x) for x in refs];assert None not in resolved;assert all((R/x).exists() for x in resolved),[x for x in resolved if not (R/x).exists()]
rp=R/'reports/FULL-REPAIR-TIBET2016-COMPLETE-A-20261015.json';assert not rp.exists();record=dict(path=D['path'],status='prepared',before_text=old,before_sha256=sha(raw),after_sha256=sha(new),sources=D['sources'],old_to_reference_mapping=D['mapping'],minimum_question_similarity=min(m['question_similarity'] for m in D['mapping']),source_reference_count=125,previous_count=120,restored_tasks=D['missing_original_numbers'],source_version_boundary='Source H 125-task reference retained; Zhenghua120 differs in order/selection and has no courier group. Reused images individually identified, not a whole-paper identity claim.',material_groups=[dict(number=m['number'],source_label=m['source_label'],tasks=m['tasks']) for m in materials.values()],answer_checks=answer_checks,corrections=notes,images=reused,unique_resolved_images=len(set(resolved)),image_references=len(refs),source_visual_receipts=['reports/FULL-REPAIR-TIBET2016-ORIGINAL-IMAGE-EXTRACTION-20261015.json','reports/FULL-REPAIR-TIBET2016-MATH-OPTIONS-20261015.json'],verification=dict(question_ids=ids,answers=125,all_old_answer_letters_preserved=True,source_reference_keys_all_matched=True,broken_image_references=[],native_number_issues=[]))
rp.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp=p.with_name(p.name+'.125-a-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());assert p.read_bytes()==raw;os.replace(tmp,p);assert sha(p.read_bytes())==sha(new);record['status']='applied';rp.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:record[k] for k in ['status','after_sha256','previous_count','source_reference_count','restored_tasks','unique_resolved_images','image_references','material_groups','verification']},ensure_ascii=False))
