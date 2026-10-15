"""Restore matched complete Fujian papers; retain each immediate pre-image."""
import json,re,sys,hashlib,uuid,os
from pathlib import Path
from difflib import SequenceMatcher
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
sha=lambda s:hashlib.sha256(s.encode()).hexdigest();ds=json.loads((R/'tools/data/fujian-full-restore-packets-a-20261015.json').read_text(encoding='utf8'))
rp=R/'reports/FULL-REPAIR-FUJIAN-FULL-SOURCE-A-20261015.jsonl';ready=[]
for d in ds:
 rel=d['target_path'];p=R/rel;old=p.read_text(encoding='utf8');op=b.parse(old,rel);year=rel.split('/')[2];variant=op['variant'];count=d['standard_question_count']
 assert d.get('source_git_blob_verified') and sum(d['points'])==100,(rel,'source verification')
 qs={q['number']:q['text'] for q in d['questions']};assert list(qs)==list(range(1,count+1))
 text='---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in {'考试':'省考','地区':'福建','年份':year,'科目':'申论','卷型':variant,'真题性质':'机构整理/考生回忆真题，非官方原件','命题形式':'多省联考','来源':['用户已有完整同年同卷原稿'],'来源整卷':d['source_url'],'来源整卷SHA256':d['source_sha256'],'题号口径':'按完整同年题本作答要求顺序；校准源序旧号','实有题数':count,'对照题本题量':count,'题目分值':d['points'],'缺失原题号':[],'给定材料段数':len(d['materials']),'已收录参考答案题号':list(qs),'缺参考答案题号':[],'校验状态':'2026-10-15据用户已有完整同卷原稿恢复材料、全部任务和字数要求；机构原稿与AI修订/原创分别标明；非官方逐字认证','恢复凭据':'reports/FULL-REPAIR-FUJIAN-FULL-SOURCE-A-20261015.jsonl'}.items())+'---\n# '+year+'年福建省公务员考试申论（'+variant+'）\n\n'
 text+='> 本卷以完整同年同卷原稿核对题量、题序与要求，参考答文单独署明性质。旧材料、任务及旧答案保留在恢复凭据，不以解析或来源说明充作答案正文。\n\n[原稿（固定Git版本）]('+d['source_url']+')\n\n'
 if variant=='统考':text+='> 本入口已恢复为同年完整通用卷，题量以原稿明确的3题、合计100分为依据；不是混题片段桶。\n\n'
 for m in d['materials']:
  n=m.get('number',m['source_label']);text+='## 给定资料 '+str(n)+'\n\n'+m['text']+'\n\n'
 text+='## 作答要求\n\n'
 for n,q in qs.items():text+='## 第 '+str(n)+' 题\n\n'+q+'\n\n'
 text+='## 答案与解析\n\n';metrics=[]
 for n,q in qs.items():
  reviewed=d['reviewed_answers'][str(n)];kind=reviewed['kind'];answer=reviewed['answer'];author='原资料未署个人作者；本次仅作版式校勘'
  if '来源：粉笔' in d['source_answer_region']:author='原稿标注来源为粉笔，未署个人作者；本次仅作版式校勘'
  elif '参考答案（F）' in d['source_answer_region']:author='原稿首个同题参考版本；仅以F等区分版本，未披露个人作者'
  if kind=='ai_original':author='AI辅助原创示范，依据本卷完整材料独立编写'
  if kind=='ai_revision':author='AI辅助修订示范；原作者/原稿来源见固定资料链接'
  e=dict(answer=answer,attribution_kind=kind,author=author,sources=[dict(title='题面与参考版本所据原稿（固定Git版本）',url=d['source_url'])])
  if reviewed.get('reason'):e['replace_reason']=reviewed['reason']+'；原版全文保存在固定源和本次凭据。'
  nc=validate_answer(q,e);metrics.append(dict(number=n,characters=nc,kind=kind,answer_sha256=sha(answer)));text+='<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+render_answer(e)+'\n\n</details>\n\n'
 text=text.replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷')
 if year=='2019' and '县级' in rel:text+='> 题面计量校勘：原稿及同题网页均已明确作文总字数1000～1200，提取文字末尾漏写单位；本次补足“字”，不改变原有区间。\n'
 text,layout=format_essay(text,rel);nd=b.parse(text,rel);assert len(nd['questions'])==count and len(nd['answers'])==count
 mapped=[]
 for on,oq in op['questions'].items():
  nn,sim=max(((nn,SequenceMatcher(None,b.qkey(oq),b.qkey(qq),autojunk=False).ratio()) for nn,qq in nd['questions'].items()),key=lambda x:x[1]);assert sim>.9,(rel,on,sim);mapped.append(dict(old_number=on,new_number=nn,question_similarity=sim))
 oldnorm=b.norm(next(iter(op['materials'].values())));materialcover=[]
 for m in d['materials']:
  grams=b.shingles(m['text']);materialcover.append(dict(number=m.get('number',m['source_label']),source_material_12gram_in_existing_coverage=sum(x in oldnorm for x in grams)/max(1,len(grams))))
 rec=dict(path=rel,before_sha256=sha(old),before_text=old,after_sha256=sha(text),source_path=d['source_path'],source_commit=d['source_commit'],source_sha256=d['source_sha256'],source_git_blob_verified=True,materials=len(d['materials']),questions=count,points=d['points'],answers=metrics,old_to_real_numbers=mapped,source_material_comparison=materialcover,layout=layout)
 ready.append((p,old,text,rec));print('READY',rel,count,metrics)
# All source and body requirements validated before any paper mutation.
before_dir=R/'reports/FULL-REPAIR-FUJIAN-FULL-SOURCE-A-BEFORE-20261015';before_dir.mkdir(exist_ok=True)
for p,old,new,record in ready:
 snapshot=before_dir/(str(len(record['path']))+'-'+sha(record['path'])[:16]+'.md')
 if not snapshot.exists():snapshot.write_bytes(old.encode())
 tmp=p.with_name(p.name+'.fujian-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());assert sha(p.read_text(encoding='utf8'))==sha(old),'Concurrent change '+str(p);os.replace(tmp,p);assert sha(p.read_text(encoding='utf8'))==sha(new)
 prior=rp.read_text(encoding='utf8') if rp.exists() else '';rp.write_text(prior+json.dumps(record,ensure_ascii=False)+'\n',encoding='utf8')
print('APPLIED',len(ready),'papers',sum(len(r[3]['answers']) for r in ready),'answers')
