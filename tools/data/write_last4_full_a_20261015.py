import json,re,sys,os,uuid,hashlib
from pathlib import Path
from difflib import SequenceMatcher
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as b
from priority_b_fullpaper_restore_20261015 import old_segments,mainbody,norm
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
from paper_integrity_repair import set_fields
sha=lambda x:hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
D=json.loads((R/'tools/data/last4-full-source-packets-a-20261015.json').read_text(encoding='utf8'));rp=R/'reports/FULL-REPAIR-LAST4-PRIORITY-A-20261015.jsonl';assert not rp.exists();ready=[]
for d in D:
 rel=d['path'];p=R/rel;before=p.read_bytes();old=before.decode();parsed=b.parse(old,rel);assert d['source_git_blob_verified'];qs={q['number']:q['text'] for q in d['questions']};cnt=len(qs);assert sum(d['points'])==100
 oldraw=dict(before_text=old,parsed=parsed);candidates=old_segments(oldraw);materials=[];alignment=[]
 for i,m in enumerate(d['materials']):
  n=m['number'];src=m['text'];public=next((z['text'] for z in d['public_materials'] if z['number']==n),None);base=public or src
  if public:
   sim=SequenceMatcher(None,norm(src),norm(public),autojunk=False).ratio();assert sim>.85,(rel,n,sim)
  else:sim=None
  best=max(((SequenceMatcher(None,norm(base),norm(z),autojunk=False).ratio(),z) for z in candidates),default=(0,''))
  keep=best[0]>=.98 and len(norm(best[1]))>=len(norm(base))*.99;selected=best[1] if keep else base
  selected=re.sub(r'(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])','',selected);selected=re.sub(r'\n{3,}','\n\n',selected).strip()
  if '行政执法' in rel and n==4:selected=selected.replace('抗战文化、抗战文化','抗战文化')
  materials.append(f'### 材料{n}\n\n'+selected)
  alignment.append(dict(number=n,source_text=src,public_text=public,source_public_similarity=sim,selected_text=selected,selected_kind='preserved_existing_readable' if keep else 'same_paper_public_corrected_transcript' if public else 'complete_owned_source',existing_best_similarity=best[0],source_sha256=sha(src),selected_sha256=sha(selected)))
 assert [m['number'] for m in d['materials']]==list(range(1,len(materials)+1))
 header=old[:old.index('\n---',4)+4]+'\n';header=set_fields(header,{'对照题本题量':cnt,'实有题数':cnt,'缺失原题号':[],'给定材料段数':len(materials),'题目分值':d['points'],'已收录参考答案题号':list(qs),'缺参考答案题号':[],'完整题本固定来源':d['source_url'],'完整题本SHA256':d['source_sha256'],'原题完整性核实凭据':'reports/FULL-REPAIR-LAST4-PRIORITY-A-20261015.jsonl'},'2026-10-15据固定同卷完整原稿恢复全部材料、真实任务序与分值字数要求；天津以同题公开全文校正OCR，参考作答保留或明确标注AI修订/原创。')
 title=re.search(r'(?m)^# [^\n]+',old)[0];out=[header,title,'',f'> 按[同年同卷完整原稿]({d["source_url"]})恢复材料和全部作答要求；原稿固定Git blob已核验。原库题号按完整任务顺序回接。旧材料、任务、参考及所有校勘异文完整保存在恢复凭据。','']
 if d['public_url']:out += [f'> 题面与材料OCR交叉校勘：[同题完整公开整理]({d["public_url"]})。公开校正文与固定原稿分别存证，不将校正文冒充原Git blob或官方题本。','']
 if '广东' in rel:out += ['> 任务异文：第2题原库/公开预览写“谈谈”，完整原稿写“分析说明”，均指向资料7青年人才的重要作用，本次按完整原稿保留“分析说明”；原稿材料一粘在页首标题后，现已独立恢复，实际共9段材料。','']
 out+=['## 给定材料','','\n\n'.join(materials),'','## 作答要求','']
 for n,q in qs.items():out += [f'## 第 {n} 题','',q,'']
 out+=['## 答案与解析',''];metrics=[]
 for n,q in qs.items():
  a=d['reviewed_answers'][str(n)];kind=a['kind'];answer=a['answer'];count=validate_answer(q,dict(answer=answer,attribution_kind='owned_source' if kind=='preserved_existing' else kind,author='已有同题参考'))
  if kind=='preserved_existing':
   on=next(m['old_number'] for m in d['mapping'] if m['new_number']==n);oldwhole=parsed['answers'][on]
   if '<!-- full-repair-answer-20261015 -->' in oldwhole:rendered=oldwhole
   else:rendered='**同题来源参考作答（原库保留）**\n\n<!-- full-repair-answer-20261015 -->\n'+answer+'\n<!-- /full-repair-answer-20261015 -->\n\n> 来源说明：原库已收录的同题参考，未署个人作者；原参考及全部解析保存在恢复凭据。不是官方答案，未经实考评分。'
  else:
   entry=dict(answer=answer,attribution_kind=kind,author='AI辅助原创示范；依据本卷完整材料独立编写' if kind=='ai_original' else 'AI辅助修订示范；所据原稿未署个人作者，不冒称原作者原文',sources=[dict(title='用户已有同题完整原稿（固定Git版本）',url=d['source_url'])],replace_reason=a['reason']);rendered=render_answer(entry)
  out += [f'<a id="r7-reference-{n}"></a>','<details>',f'<summary>第 {n} 题</summary>','',rendered,'','</details>',''];metrics.append(dict(number=n,characters=count,kind=kind,body_sha256=sha(answer)))
 new='\n'.join(out).replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷');new,layout=format_essay(new,rel);nd=b.parse(new,rel);assert len(nd['questions'])==len(nd['answers'])==cnt
 rec=dict(path=rel,status='prepared',before_text=old,before_sha256=sha(before),after_sha256=sha(new),source={k:v for k,v in d.items() if k not in ['source_full_text','reviewed_answers','materials','public_materials']},materials=alignment,questions=cnt,points=d['points'],answers=metrics,layout=layout)
 ready.append((p,before,new,rec));print('READY',rel,len(materials),cnt,metrics)
for p,before,new,rec in ready:
 with rp.open('a',encoding='utf8') as f:f.write(json.dumps(rec,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 tmp=p.with_name(p.name+'.last4-a-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());assert p.read_bytes()==before;os.replace(tmp,p);assert sha(p.read_bytes())==rec['after_sha256']
 with rp.open('a',encoding='utf8') as f:f.write(json.dumps(dict(path=rec['path'],status='applied',after_sha256=rec['after_sha256']),ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
print('APPLIED',len(ready))
