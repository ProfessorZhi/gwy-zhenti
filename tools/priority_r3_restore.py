"""Restore explicitly matched whole-paper layouts without replacing sound old text.
Only the 20 reviewed national/Zhejiang essay paths are eligible. No downloads,
commands or writes on external devices. Source disagreements remain explicit.
"""
from __future__ import annotations
import concurrent.futures,difflib,hashlib,json,re,unicodedata
from pathlib import Path
from bs4 import Tag
from priority_r3_review import parts,oldblocks,MAT,FOOT
from priority_r3_whole import read,norm
from priority_r3_answers import DETAIL,setmeta,digest
RECEIPT='reports/ROUND3-WHOLE-20261012.jsonl'
CN={c:i for i,c in enumerate('一二三四五六',1)}
ORD=re.compile(r'^(?:第([一二三四五六])题\s*[:：]?|([一二三四五六])[、.．：:]|[（(]([一二三四五六])[)）])\s*')

def prompt_key(s):
 s=ORD.sub('',s.strip());s=re.split(r'要求\s*[:：]',s)[0]
 s=re.sub(r'[（(]\s*\d+\s*分\s*[)）]','',s)
 s=re.sub(r'((?:给定)?(?:资料|材料))\s*\d+(?:\s*[-—～至、，,]\s*\d+)*',r'\1',s)
 return norm(s)

def full_tasks(soup):
 h=next((t for t in soup.find_all('h2') if '作答要求' in t.get_text()),None)
 if h is None:raise ValueError('No task section')
 tasks=[];cur=None
 for t in h.find_all_next(['h2','b','strong','p','h3','h4']):
  if t.name=='h2':break
  text=re.sub(r'\s+',' ',t.get_text()).strip()
  if FOOT.search(text):break
  if not text:continue
  if t.name in ['b','strong']:
   if t.find_parent(['p','h3','h4']):continue
   if text not in CN:continue
   n=CN[text];cur={'number':n,'paragraphs':[]};tasks.append(cur);continue
  m=ORD.match(text)
  if m:
   n=CN[next(g for g in m.groups() if g)]
   if cur and cur['number']==n and not cur['paragraphs']:pass
   else:cur={'number':n,'paragraphs':[]};tasks.append(cur)
   text=text[m.end():]
  if cur and text:cur['paragraphs'].append(text)
 if [q['number'] for q in tasks]!=list(range(1,len(tasks)+1)):raise ValueError('Ambiguous task numbers')
 for q in tasks:
  text='\n\n'.join(q['paragraphs']);q['text']=text
  q['score']=sum(map(int,re.findall(r'[（(]\s*(\d+)\s*分\s*[)）]',text)))
  if not q['score'] or not re.search(r'\d+\s*字',text):raise ValueError('Missing score/word limit: '+text[:120])
 if sum(q['score'] for q in tasks)!=100:raise ValueError('Task scores do not sum to 100')
 return tasks

def reflow(s):
 # Only whitespace is changed; CJK characters, punctuation and all numbers persist.
 paras=[re.sub(r'\s*\n\s*','',p).strip() for p in re.split(r'\n\s*\n',s.strip()) if p.strip()]
 out=[]
 for p in paras:
  if out and not re.search(r'[。！？!?；;：:”」』）)]$',out[-1]) and not re.match(r'^(?:\d+[.、]|[A-G][：:]|[一二三四五六七八九]+[、.])',p):out[-1]+=p
  else:out.append(p)
 ans='\n\n'.join(out)
 if re.sub(r'\s+','',ans)!=re.sub(r'\s+','',s):raise ValueError('Non-whitespace reflow mutation')
 return ans

def paired_tasks(old,new):
 mapping={};scores=[];used=set()
 for q in old:
  a=prompt_key(q['requirements']);rs=sorted([(difflib.SequenceMatcher(None,a,prompt_key(t['text']),autojunk=False).ratio(),t['number']) for t in new],reverse=True)
  if not rs or rs[0][0]<.78 or (len(rs)>1 and rs[0][0]-rs[1][0]<.15) or rs[0][1] in used:raise ValueError('Question identity unresolved: '+json.dumps({'old':q,'rank':rs},ensure_ascii=False))
  mapping[q['number']]=rs[0][1];used.add(rs[0][1]);scores.append({'old':q['number'],'original':rs[0][1],'similarity':round(rs[0][0],6),'old_prompt':q['requirements'],'source_prompt':new[rs[0][1]-1]['text']})
 return mapping,scores

def source_for(item):
 r,soup=read(item['url']);p=parts(soup);mats=[]
 if p['images']:raise ValueError('Source has images; visual review required before import')
 for text in p['materials']:
  m=MAT.fullmatch(text)
  if m:mats.append({'number':int(m[1]),'paragraphs':[]})
  elif mats:mats[-1]['paragraphs'].append(text)
 if [m['number'] for m in mats]!=list(range(1,len(mats)+1)) or not mats:raise ValueError('Invalid material sequence')
 tasks=full_tasks(soup)
 expected=3 if '浙江/2016' in item['path'] else 4 if item['path']=='国考/2016/申论-地市级.md' else 5
 if len(tasks)!=expected:raise ValueError(f'Expected {expected} main tasks, got {len(tasks)}')
 # The same source body must still agree with the snapshot reviewed before editing.
 reviewed=''.join(item.get('requirements',[]));now=''.join(p['requirements'])
 if norm(reviewed)!=norm(now):raise ValueError('Reviewed source requirements changed')
 return {'url':item['url'],'raw_sha256':hashlib.sha256(r.content).hexdigest(),'materials':mats,'tasks':tasks,'instructions':p['instructions']}

def build(item,source,originals,huatu):
 path=item['path'];before=originals[path]
 if digest(before)!=item['before_sha256']:raise ValueError('Baseline bytes changed: '+path)
 oldqs,oldmats=oldblocks(before);mapping,taskproof=paired_tasks(oldqs,source['tasks'])
 donor=[]
 for b in oldmats:donor.append(b|{'path':path,'file_sha256':digest(before)})
 if path=='省考/浙江/2016/申论-B类.md':
  other='省考/浙江/2016/申论-A类.md'
  donor.extend(b|{'path':other,'file_sha256':digest(originals[other])} for b in oldblocks(originals[other])[1])
 chosen=[];matproof=[];patches=[]
 for mat in source['materials']:
  n=mat['number'];raw='\n\n'.join(mat['paragraphs']);target=norm(raw)
  rank=[]
  for b in donor:
   seq=difflib.SequenceMatcher(None,b['normalized'],target,autojunk=False);size=sum(z.size for z in seq.get_matching_blocks())
   rank.append((seq.ratio(),size/max(1,len(target)),b))
  rank.sort(key=lambda x:(x[0],len(x[2]['text'])),reverse=True)
  if rank and rank[0][0]>=.93 and rank[0][1]>=.94:
   score,coverage,b=rank[0];body=reflow(b['text']);origin={'type':'preserved_existing_material','path':b['path'],'file_sha256':b['file_sha256'],'old_question':b['old_question'],'local_number':b['local_number'],'original_text_sha256':digest(b['text']),'non_whitespace_sha256':digest(re.sub(r'\s+','',body)),'source_similarity':score,'source_coverage':coverage}
  else:
   body=raw;origin={'type':'same_paper_public_source','url':source['url'],'source_text_sha256':digest(raw)}
  if '浙江/2016' in path:
   fixes=[('气瓶气管里面找合适的人们是增加了一个调节器','气瓶、气管、面罩，后世的人们只增加了一个调节器'),('马洛里斯去了','马洛里辞去了')]
   for bad,good in fixes:
    if bad in body:
     if not huatu or good not in huatu['text']:raise ValueError('Independent correction source unavailable')
     body=body.replace(bad,good);patches.append({'section':'material','number':n,'before':bad,'after':good,'url':huatu['url'],'source_sha256':huatu['sha256'],'reason':'公开转录OCR异文；按独立同段文本校对，不使用该页冲突的第1题'})
   if n==6 and body.startswith('在众多') and '\n\n轻女孩' in body:
    body=body.replace('\n\n轻女孩','\n\n年轻女孩',1);patches.append({'section':'material','number':n,'before':'轻女孩','after':'年轻女孩','url':'https://gwy.gkzhenti.cn/paper/20160802100920','reason':'A类同年同段完整人称对照'})
  if any(x in body for x in ['气瓶气管里面找','马洛里斯去了','\ufffd']):raise ValueError('Known corrupt text rejected')
  chosen.append((n,body));matproof.append({'original_number':n,'delivered_sha256':digest(body),'source_paragraph_sha256':[digest(x) for x in mat['paragraphs']],**origin})
 tasks=[]
 for q in source['tasks']:
  text=q['text']
  if '浙江/2016' in path:
   for bad,good in [('马格里','马洛里'),('影响力无数','影响了无数')]:
    if bad in text:
     if not huatu or good not in huatu['text']:raise ValueError('Question typo needs independent evidence')
     text=text.replace(bad,good);patches.append({'section':'question','number':q['number'],'before':bad,'after':good,'url':huatu['url'],'reason':'同年同题姓名和动词异文；不改变卷型、分值、字数'})
  tasks.append(q|{'delivered_text':text})
 oldanswers={int(m[1]):m[2] for m in DETAIL.finditer(before)}
 if set(oldanswers)-set(mapping):raise ValueError('Unmapped answer')
 answers={mapping[n]:a for n,a in oldanswers.items()};answerproof=[];removed=[]
 # The final lines in old A answer 2 are a misplaced question, not an answer.
 if path=='省考/浙江/2016/申论-A类.md' and 1 in answers:
  a=answers[1];m=re.search(r'\n第一题\s*\n请结合给定资料1、2、3，概括众筹的特点。.*\Z',a,re.S)
  if m:removed.append({'old_question':2,'original_question':1,'misplaced_text':m[0].strip(),'reason':'旧答案尾部误排作答要求，完整要求已在第1题正文恢复'});answers[1]=a[:m.start()].rstrip()+'\n\n'
 for oldn,newn in mapping.items():
  if oldn in oldanswers:answerproof.append({'old_number':oldn,'original_number':newn,'old_sha256':digest(oldanswers[oldn].strip()),'delivered_sha256':digest(answers[newn].strip()),'unchanged':oldanswers[oldn].strip()==answers[newn].strip()})
 title=re.search(r'^# .+$',before,re.M)[0]
 intro='> **机构公开整理/考生回忆版，不是官方原件逐字认证。** 本轮恢复全卷材料编号、作答题序、分值和字数限制。可与整卷来源对应的既有材料优先保留；来源版本异文、补入段落及旧题号映射见第三轮凭据。\n\n'
 if path=='国考/2016/申论-地市级.md':intro+='> 本卷为4道大题，第3题含两个小问，分值分别为10分；不得按5道大题重新编号。\n\n'
 if '浙江/2016' in path:intro+='> 材料7的两处明显OCR异文按华图同段文本校对；该网页第1题与本卷冲突，未用于替换本卷题目。分卷要求采用与既有题干一致的公开题本版本。\n\n'
 nav=' · '.join(f'[资料 {n}](#给定资料-{n})' for n,_ in chosen)+'\n\n'+' · '.join(f'[第 {q["number"]} 题](#第-{q["number"]}-题)' for q in tasks)+' · [答案与解析](#答案与解析)'
 chunks=[title,f'> 申论 · {len(tasks)} 道作答大题 · {len(chosen)} 则给定资料',intro+'[本卷完整公开来源]('+source['url']+')','## 阅读导航\n\n'+nav,'## 考试注意事项\n\n'+'\n\n'.join(source['instructions'])]
 chunks.extend(f'## 给定资料 {n}\n\n{text}' for n,text in chosen)
 chunks.extend(f'## 第 {q["number"]} 题\n\n### 作答要求\n\n{q["delivered_text"]}' for q in tasks)
 chunks.append('## 答案与解析\n\n> 既有参考答案按同题映射保留。旧答案中的“材料1”等可能指原题级材料编号，请对照下表理解；不据此改写答案。\n\n| 旧题号 | 当前原题号 |\n|---|---|\n'+'\n'.join(f'| {o} | {n} |' for o,n in sorted(mapping.items())))
 for q in tasks:
  n=q['number'];a=answers.get(n,'\n\n未收录可靠参考答案；不以“略”或生成文字冒充原来源答案。\n\n')
  chunks.append(f'<details>\n<summary>第 {n} 题</summary>'+a+'</details>')
 if removed:chunks.append('## 校对说明\n\n旧答案区误排的第1题题干与字数要求已移回题目区，旧文字及哈希保存在 `'+RECEIPT+'`；未删除解题内容。')
 header='---'+before.split('---',2)[1]+'---\n\n';after=header+'\n\n'.join(chunks).rstrip()+'\n'
 fields={'真题性质':'机构公开整理/网友回忆真题；非官方原件','题号口径':'同年同卷公开题本原题序；题级局部材料映射到全卷材料','实有题数':len(tasks),'对照题本题量':len(tasks),'缺失原题号':[],'给定材料段数':len(chosen),'题目分值':[q['score'] for q in tasks],'已收录参考答案题号':sorted(answers),'缺参考答案题号':[q['number'] for q in tasks if q['number'] not in answers],'第三轮整卷修复证据':RECEIPT,'整卷核验状态':'完整公开题面与同题映射；原件逐字真实性和答案正确性仍须独立复核','来源整卷':source['url'],'来源整卷SHA256':source['raw_sha256']}
 for k,v in fields.items():after=setmeta(after,k,v)
 proof={'path':path,'before_sha256':digest(before),'after_sha256':digest(after),'source_url':source['url'],'source_raw_sha256':source['raw_sha256'],'original_material_count':len(chosen),'original_task_count':len(tasks),'added_tasks':len(tasks)-len(oldqs),'task_scores':[q['score'] for q in tasks],'task_mapping':taskproof,'material_mapping':matproof,'preserved_answers':answerproof,'explicit_transcription_corrections':patches,'misplaced_requirements_moved':removed,'question_sha256':{str(q['number']):digest(q['delivered_text']) for q in tasks},'boundary':'结构、题干身份、材料映射及保持性验收；不是官方逐字或答案真实性认证'}
 return after,proof

def main():
 if Path(RECEIPT).exists():print('Whole paper repairs already applied');return
 items=json.loads(Path('reports/R3-MAPPING-REVIEW.json').read_text());originals={x['path']:Path(x['path']).read_text() for x in items};sources={};errors=[]
 def load(x):
  try:return x['path'],source_for(x),None
  except Exception as e:return x['path'],None,str(e)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for path,s,e in pool.map(load,items):
   if e:errors.append({'path':path,'stage':'source','error':e})
   else:sources[path]=s
 huatu=None
 try:
  url='https://ha.huatu.com/2020/0318/1805456_6.html';r,soup=read(url);text=soup.get_text('\n');huatu={'url':url,'text':text,'sha256':hashlib.sha256(r.content).hexdigest()}
 except Exception as e:errors.append({'path':'Zhejiang independent correction source','error':str(e)})
 records=[]
 for item in items:
  path=item['path']
  if path not in sources:continue
  try:
   after,proof=build(item,sources[path],originals,huatu)
   Path(path).write_text(after,encoding='utf-8');records.append(proof)
  except Exception as e:errors.append({'path':path,'stage':'identity/build','error':str(e)})
 if not records:raise ValueError('No safe repairs: '+json.dumps(errors,ensure_ascii=False))
 Path(RECEIPT).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf-8')
 summary={'papers_modified':len(records),'added_tasks':sum(x['added_tasks'] for x in records),'papers':[{'path':x['path'],'materials':x['original_material_count'],'tasks':x['original_task_count'],'added_tasks':x['added_tasks'],'new_source_materials':[m['original_number'] for m in x['material_mapping'] if m['type']=='same_paper_public_source'],'old_to_original':{str(t['old']):t['original'] for t in x['task_mapping']},'preserved_answers':len(x['preserved_answers'])} for x in records],'unresolved':errors}
 Path('reports/R3-RESTORE-RESULT.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
