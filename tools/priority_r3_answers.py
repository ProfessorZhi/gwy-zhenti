"""Apply reviewed source answers, preserving pre-existing question and answer text."""
from __future__ import annotations
import difflib,hashlib,json,re,unicodedata
from pathlib import Path
DETAIL=re.compile(r'<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>(.*?)</details>',re.S)
RECEIPT='reports/ROUND3-ANSWERS-20261012.jsonl'
def digest(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def key(s):
 s=re.sub(r'^(?:第\s*\d+\s*题[:：]?|[（(]?[一二三四][)）]?、?)','',s.strip())
 s=re.split(r'要求\s*[:：]|[（(]\d+分[)）]',s)[0]
 return ''.join(c for c in unicodedata.normalize('NFKC',s) if c.isalnum())
def setmeta(text,k,v):
 a,h,b=text.split('---',2);line=k+': '+json.dumps(v,ensure_ascii=False)
 h=re.sub(r'^'+re.escape(k)+r':.*$',lambda m:line,h,flags=re.M) if re.search(r'^'+re.escape(k)+':',h,re.M) else h.rstrip()+'\n'+line+'\n'
 return '---'+h+'---'+b

def get_prompt(text,n):
 m=re.search(r'^## 第\s*'+str(n)+r'\s*题[^\n]*\n(.*?)(?=^## 第\s*\d+\s*题|^## 答案与解析|\Z)',text,re.M|re.S)
 if not m:raise ValueError(f'No question {n}')
 return m[1].split('### 作答要求',1)[-1].strip()
def materials(text):
 return {int(m[1]):''.join(c for c in unicodedata.normalize('NFKC',m[2]) if c.isalnum()) for m in re.finditer(r'^## 给定资料 (\d+)\n(.*?)(?=^## |\Z)',text,re.M|re.S)}

def insert_answers(text, additions):
 oldbody=text.split('---',2)[2].split('## 答案与解析')[0]
 old={int(m[1]):m[2] for m in DETAIL.finditer(text)}
 for n,ans in additions.items():
  if len(ans)<80 or re.search(r'答案[：:]?略|全力以赴征集|正确答案默认',ans):raise ValueError('Empty or placeholder answer rejected')
  existing=next((m for m in DETAIL.finditer(text) if int(m[1])==n),None)
  block=f'<details>\n<summary>第 {n} 题</summary>\n\n{ans}\n\n</details>'
  if existing:
   if not re.search(r'未收录|尚未|未取得|暂无',existing[2]) or len(existing[2].strip())>450:raise ValueError(f'Refuse to overwrite existing answer {n}')
   text=text[:existing.start()]+block+text[existing.end():]
  else:
   later=next((m for m in DETAIL.finditer(text) if int(m[1])>n),None)
   if later:text=text[:later.start()]+block+'\n\n'+text[later.start():]
   else:text=text.rstrip()+'\n\n'+block+'\n'
 new={int(m[1]):m[2] for m in DETAIL.finditer(text)}
 for n,ans in old.items():
  if n not in additions and new.get(n)!=ans:raise ValueError('Existing answer changed')
 if text.split('---',2)[2].split('## 答案与解析')[0]!=oldbody:raise ValueError('Question body changed during answer insertion')
 return text,{str(n):digest(ans.strip()) for n,ans in old.items() if n not in additions}

def main():
 if Path(RECEIPT).exists():print('Reviewed answer repair already applied');return
 sources={x['key']:x for x in json.loads(Path('reports/R3-SOURCE-PROBE2.json').read_text())}
 a_path='省考/江苏/2016/申论-A类.md';b_path='省考/江苏/2016/申论-B类.md'
 a=Path(a_path).read_text();b=Path(b_path).read_text()
 ref=sources['js16a_ref'];ps=[x['text'] for x in ref['paragraphs']]
 assert '2016' in ref['title'] and '江苏' in ref['title'] and 'A卷' in ref['title']
 start=ps.index('(一)【参考答案】')+1;end=ps.index('(二)【参考答案】');answer16='\n\n'.join(ps[start:end])
 assert '消极影响' in answer16 and '磨刀老人' in answer16 and '(247字)' in answer16
 doc=sources['js16a_doc'];dp=[x['text'] for x in doc['paragraphs']];i=dp.index('三、作答要求')
 source_prompt=''.join(dp[i+1:i+3]);assert key(source_prompt)==key(get_prompt(a,1))
 ma,mb=materials(a),materials(b);abdiff=[]
 for n in sorted(set(ma)|set(mb)):
  x,y=ma.get(n,''),mb.get(n,'');sm=difflib.SequenceMatcher(None,x,y,autojunk=False)
  changes=[{'a':x[i:j],'b':y[k:l]} for tag,i,j,k,l in sm.get_opcodes() if tag!='equal']
  if changes:abdiff.append({'material':n,'ratio':sm.ratio(),'changes':changes})
 print('AB_MATERIAL_DIFFERENCES '+json.dumps(abdiff,ensure_ascii=False))
 evidence16={'url':ref['url'],'raw_sha256':ref['sha256'],'source_question':source_prompt,'question_identity':'2016江苏A卷题干与完整题本对应','crosscheck_url':doc['url'],'B_class_automatic_reuse':'rejected unless eight materials are exactly identical','AB_material_differences':abdiff}
 answer='**来源参考答案（非官方）**\n\n'+answer16+'\n\n[明确标注2016江苏A卷的参考答案来源]('+ref['url']+')'
 plans=[(a_path,{1:answer},{'1':evidence16})]
 if len(ma)==len(mb)==8 and ma==mb and key(get_prompt(a,1))==key(get_prompt(b,1)):
  plans.append((b_path,{1:answer+'\n\n> 本卷题干及8则给定材料与A卷逐项完全对应后引用。'},{'1':evidence16}))
 source=sources['js18a'];ps=[x['text'] for x in source['paragraphs']]
 p='省考/江苏/2018/申论-A类.md';s=Path(p).read_text();adds={};ev={}
 for n in [1,3,4]:
  ix=next(i for i,t in enumerate(ps) if re.match(r'^第\s*'+str(n)+r'\s*题[:：]',t))
  stem=re.sub(r'^第\s*\d+\s*题[:：]','',ps[ix]);assert key(stem)==key(get_prompt(s,n)),f'2018A Q{n} identity mismatch'
  ai=ps.index('参考答案：',ix)+1;parts=[]
  for t in ps[ai:]:
   if t.startswith('参考答案说明') or t.startswith('文章分析') or re.match(r'^第\s*\d+\s*题',t):break
   parts.append(t)
  content='\n\n'.join(parts)
  if n==3:assert '李XX' in content and '陈XX' not in content and 'XXXX年XX月XX日' in content,content
  if n==4:assert '民族精神的传承' in content and len(content)>950,content
  adds[n]='**来源参考答案（非官方；范文不等于唯一答案）**\n\n'+content+'\n\n[同年同卷同题来源]('+source['url']+')'
  ev[str(n)]={'url':source['url'],'raw_sha256':source['sha256'],'source_prompt':stem,'source_answer_sha256':digest(content),'paragraph_sha256':[digest(x) for x in parts],'review':'同年A卷题干匹配；感谢信李XX/小张/刘医生及医院角色核对；不导入选调独立卷'}
 plans.append((p,adds,ev));records=[]
 for path,adds,ev in plans:
  before=Path(path).read_text();after,oldhash=insert_answers(before,adds)
  after=setmeta(after,'已收录参考答案题号',[1,2,3,4]);after=setmeta(after,'缺参考答案题号',[])
  after=setmeta(after,'第三轮答案补录证据',RECEIPT)
  Path(path).write_text(after,encoding='utf-8')
  records.append({'path':path,'before_sha256':digest(before),'after_sha256':digest(after),'added_answers':sorted(adds),'preserved_answers':oldhash,'answer_sources':ev,'delivered_answer_sha256':{str(n):digest(m[2].strip()) for m in DETAIL.finditer(after) if (n:=int(m[1])) in adds},'body_sha256':digest(after.split('---',2)[2].split('## 答案与解析')[0])})
 Path(RECEIPT).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf-8')
 print(json.dumps({'modified_papers':len(records),'added_reference_answers':sum(len(x['added_answers']) for x in records)},ensure_ascii=False))
if __name__=='__main__':main()
