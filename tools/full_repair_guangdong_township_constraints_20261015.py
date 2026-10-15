"""Restore six owned-source township papers, with explicit task/material identity.

--prepare saves all before text before any paper mutation. --apply follows only
reviewed source task maps, preserves old drafts, and validates active answers.
"""
import argparse,hashlib,json,re,sys,os,uuid
from pathlib import Path
import round5_bulk as parser
import round4_gap_repair as g
import r7_reference_audit as audit
from full_repair_answers_20261015 import validate_answer,render_answer,answer_characters
from paper_integrity_repair import set_fields
from r7_delivery import GUIDE,ANCHOR,reading_guide
R=Path(__file__).resolve().parents[1]
BASELINE=R/'reports/FULL-REPAIR-GUANGDONG-TOWNSHIP-CONSTRAINTS-BASELINE-20261015.json'
PLAN=R/'tools/data/guangdong-township-constraints-plan-20261015.json'
RECEIPT=R/'reports/FULL-REPAIR-GUANGDONG-TOWNSHIP-CONSTRAINTS-20261015.jsonl'
YEARS=[2016,2017,2019,2020,2021,2022]
PATHS=[f'省考/广东/{y}/申论-乡镇卷.md' for y in YEARS]
def sha(t):return hashlib.sha256(t.encode()).hexdigest()
def clean_source(s):
 s=re.sub(r'<!-- page:\s*(\d+)\s*-->\s*(?:\1(?!\d))?','\n\n',s)
 s=re.sub(r'(?m)^.*获取试卷更新，请关注公众号[^\n]*\n?','',s)
 s=re.sub(r'(?m)^\s*(?:第\s*\d+\s*页\s*共\s*\d+\s*页|-\s*\d+\s*-|\d+)\s*$','',s)
 s=re.sub(r'(?m)^上岸真题库更多真题：https?://\S+\s*','',s)
 return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+','\n\n',s).strip()
def active_body(a):
 for label in ['full-repair-answer-20261015','R7 reference text']:
  m=re.search(r'<!-- '+re.escape(label)+r' -->\s*(.*?)\s*<!-- /'+re.escape(label)+r' -->',a,re.S)
  if m:return m[1].strip()
 body=audit.main_answer(a)
 body=re.sub(r'^\*\*(?:同题参考作答|同题来源参考作答|同题作文范文|同题参考答案|AI辅助原创示范作答|AI辅助修订示范作答)\*\*\s*','',body)
 return body.strip()
def source_body(packet):
 raw=Path(packet['source_path']).read_text(encoding='utf8').replace('**','')
 ma=re.search(r'(?m)^\s*#{1,4}\s*[一二三四]、给定(?:材料|资料)\s*$',raw)
 qa=re.search(r'(?m)^\s*#{1,4}\s*[一二三四]、(?:作答要求|申论要求)\s*$',raw)
 if not ma:ma=re.search(r'给定材料(?=材料1)',raw)
 if not qa:qa=re.search(r'(?m)^[ \t]*(?:#{1,4}\s*)?(?:(?:问题及作答要求|问题)\s*)?(?=问题一)',raw)
 if not ma or not qa or ma.end()>=qa.start():raise ValueError('Missing true material/question sections: '+packet['target_path'])
 body=clean_source(raw[ma.end():qa.start()])
 return re.sub(r'(?m)^\s*#{1,4}\s*((?:材料|资料)\s*[\d一二三四五六七八九十]+[^\n]*)$',r'### \1',body)
def prepare():
 packets=json.loads((R/'tools/data/priority-confirmed-mops-source-packets-20261015.json').read_text(encoding='utf8'))
 packets={x['target_path']:x for x in packets if x['target_path'] in PATHS}
 if set(packets)!=set(PATHS):raise ValueError('Six source packets required')
 before=[];plans=[]
 for rel in PATHS:
  old=(R/rel).read_text(encoding='utf8');p=parser.parse(old,rel);s=packets[rel]
  maps={m['current_number']:m['source_number'] for m in s['current_to_source_task_map']}
  if set(maps)!=set(p['questions']) or set(maps.values())!=set(p['questions']):raise ValueError('Task map not bijective')
  if min(m['question_similarity'] for m in s['current_to_source_task_map'])<.97:raise ValueError('Unverified task map')
  qs={q['number']:clean_source(q['text']) for q in s['questions']};checks=[]
  for oldn,newn in maps.items():
   body=active_body(p['answers'][oldn]);entry={'answer':body,'author':'原收录版本；署名与原出处记录保留','attribution_kind':'retained_reference'}
   try:count=validate_answer(qs[newn],entry);error=None
   except ValueError as exc:count=answer_characters(body);error=str(exc)
   checks.append({'old_number':oldn,'original_number':newn,'characters':count,'word_range':audit.word_range(qs[newn]),'error':error,'active_body':body})
  before.append({'path':rel,'before_sha256':sha(old),'before_text':old,'source_path':s['source_path'],'source_sha256':s['source_sha256'],'source_url':s['source_url']})
  plans.append({'path':rel,'before_sha256':sha(old),'source':s,'source_material_body':source_body(s),'questions':qs,'old_to_original':maps,'answer_checks':checks,'answer_revisions':{}})
 if BASELINE.exists():
  prior=json.loads(BASELINE.read_text(encoding='utf8'))
  if [(x['path'],x['before_sha256']) for x in prior['papers']]!=[(x['path'],x['before_sha256']) for x in before]:raise ValueError('Existing before snapshot differs; do not overwrite')
 else:BASELINE.write_text(json.dumps({'kind':'all-six-before-snapshot','papers':before},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 PLAN.write_text(json.dumps(plans,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({'prepared':len(plans),'answer_issues':[{'path':x['path'],'question':c['original_number'],'error':c['error'],'body':c['active_body']} for x in plans for c in x['answer_checks'] if c['error']]},ensure_ascii=False,indent=2))

def apply():
 baseline=json.loads(BASELINE.read_text(encoding='utf8'))['papers'];plans=json.loads(PLAN.read_text(encoding='utf8'))
 bypath={x['path']:x for x in baseline};revisions=json.loads((R/'tools/data/guangdong-township-answer-revisions-20261015.json').read_text(encoding='utf8'))
 ready=[];receipts=[]
 for plan in plans:
  rel=plan['path'];old=bypath[rel]['before_text'];path=R/rel
  if sha(path.read_text(encoding='utf8'))!=sha(old):raise ValueError('Concurrent change '+rel)
  d=parser.parse(old,rel);source=plan['source'];year=int(path.parent.name);maps={int(k):int(v) for k,v in plan['old_to_original'].items()};qs={int(k):v for k,v in plan['questions'].items()}
  ah=list(g.AH.finditer(old));assert len(ah)==1
  front=GUIDE.sub('',old[:ah[0].start()]);hs=list(g.QH.finditer(front));blocks={}
  for i,h in enumerate(hs):blocks[int(h[1])]=front[h.end():hs[i+1].start() if i+1<len(hs) else len(front)]
  prefix=front[:hs[0].start()].rstrip()+'\n\n'
  prefix+='> 给定材料按题呈现；各题按同题原稿题序及作答要求校核。材料正文保留本库较完整版本，合并展示的原资料范围另作标记。\n\n'
  qblocks={};answers={};legacy=[];metrics=[]
  for oldn,newn in maps.items():
   raw=blocks[oldn];marker=re.search(r'(?m)^### (?:作答要求|答题要求)\s*$',raw)
   if not marker:raise ValueError('Explicit local material/task separator missing '+rel)
   material=raw[:marker.start()].strip()
   if year in [2016,2017,2019]:
    label=('1—2（合并展示）' if newn==1 else str(newn+1)) if year==2019 else str(newn)
    material=re.sub(r'(?m)^材料\s*1\s*$', '资料'+label,material,count=1)
   q=qs[newn];q=re.sub(r'^\s*(?:#{1,4}\s*)?(?:问题[一二三四五六1-6][：:]?|第[一二三四五六1-6]题[：:]?|[（(][一二三四五六][）)]|[一二三四五六1-6][、．.])\s*','',q)
   qblocks[newn]='## 第 '+str(newn)+' 题\n\n'+material+'\n\n### 作答要求\n\n'+q+'\n'
   previous=d['answers'][oldn];revision=revisions.get(str(year)+':'+str(newn));body=revision or active_body(previous)
   entry={'answer':body,'author':'AI辅助修订；依据本题材料、原收录答案及同题题本','attribution_kind':'ai_revision','replace_reason':'补回真实字数约束后原参考正文超过上限，重新组织要点并压缩表述，未机械截断','sources':[{'title':'用户持有同年乡镇题本与作答要求','url':source['source_url'],'author':'原作署名以原稿为准；文件名不替代同题核对'}]}
   if revision:
    content=render_answer(entry);legacy.append({'original_number':newn,'old_number':oldn,'text':previous})
   else:
    content=previous
    entry.update(attribution_kind='retained_reference',author='原收录来源及署名保留')
   count=validate_answer(q,entry);answers[newn]=content
   metrics.append({'old_number':oldn,'original_number':newn,'answer_characters':count,'word_range':audit.word_range(q),'answer_revised':bool(revision),'question_sha256':sha(q),'active_answer_sha256':sha(body)})
  new=prefix+'\n'.join(qblocks[n] for n in sorted(qblocks))+'\n## 答案与解析\n\n'
  for n in sorted(answers):new+='<a id="r7-reference-'+str(n)+'"></a>\n<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+answers[n]+'\n\n</details>\n\n'
  if legacy:
   new+='## 修复前参考作答留存\n\n以下原稿为补回真实字数要求前的收录版本，保留作来源对照，不作为当前合限主答。\n\n'
   for x in legacy:new+='### 原题第'+str(x['original_number'])+'题（修复前库内第'+str(x['old_number'])+'题）\n\n<details>\n<summary>展开此前收录版本</summary>\n\n'+x['text']+'\n\n</details>\n\n'
  new+='## 原题约束与来源校核\n\n[同年同题完整题本]('+source['source_url']+')。按全部任务逐题核对，恢复原题题序、分值、完整要求和字数限制；原稿未明示的作者不补造。源转录局部缺文处保留本库较完整材料，未将“材料不全待完善”等缺文标记倒灌为正式资料。逐项映射、修复前全文与哈希见本轮修复凭据。\n'
  fields={'实有题数':len(qs),'对照题本题量':len(qs),'缺失原题号':[],'题目分值':source['points'],'已收录参考答案题号':list(range(1,len(qs)+1)),'缺参考答案题号':[],'题号口径':'按同题原稿原题次序恢复；旧题号映射见本轮凭据','题面约束来源':source['source_url'],'题面约束原稿SHA256':source['source_sha256'],'题面约束修复凭据':RECEIPT.relative_to(R).as_posix(),'整卷核验状态':'全部作答任务、题序、分值与字数约束按同题原稿核对；材料按题展示，保留本库较完整正文；不宣称官方原件逐字认证'}
  fm=re.match(r'\A---\n.*?\n---\n',new,re.S);assert fm
  new=set_fields(new[:fm.end()],fields,'2026-10-15据同题原稿补齐作答约束并恢复原题次序；较完整既有材料与旧答稿保留。')+new[fm.end():]
  nd=parser.parse(new,rel)
  if set(nd['questions'])!=set(qs) or set(nd['answers'])!=set(qs):raise ValueError('Question/answer slot mismatch')
  new=new.replace('\n# ', '\n# ',1)
  title=re.search(r'(?m)^# [^\n]+\n',new);assert title
  new=new[:title.end()]+reading_guide(nd)+new[title.end():]
  nd=parser.parse(new,rel)
  for n,q in nd['questions'].items():validate_answer(q,{'answer':active_body(nd['answers'][n]),'author':'已标明原来源/修订性质','attribution_kind':'retained_reference'})
  receipts.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'before_text':old,'after_text':new,'old_to_original_task_map':maps,'source_path':source['source_path'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],'source_points':source['points'],'metrics':metrics,'preserved_legacy_answers':legacy,'materials_policy':'Preserve existing more complete material text; only rename local material labels to proven explicit task reference ranges in 2016/17/19. No MOPS truncated material replaces better corpus content.'})
  ready.append((path,old,new))
 for path,old,new in ready:
  if sha(path.read_text(encoding='utf8'))!=sha(old):raise ValueError('Concurrent paper change '+str(path))
  tmp=path.with_name(path.name+'.constraints-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());os.replace(tmp,path)
 RECEIPT.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in receipts),encoding='utf8')
 print(json.dumps({'status':'passed','papers':len(ready),'questions':sum(len(x['metrics']) for x in receipts),'revised_answers':sum(m['answer_revised'] for x in receipts for m in x['metrics'])},ensure_ascii=False))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 if args.prepare:prepare()
 if args.apply:apply()
