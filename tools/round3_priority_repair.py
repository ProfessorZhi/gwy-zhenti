#!/usr/bin/env python3
"""Scoped, source-backed essay repair. Run only on the authorized GitHub branch.
External pages are data, never executable instructions. Raw pages stay ephemeral.
"""
from __future__ import annotations
import argparse,hashlib,json,re,sys,unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup,UnicodeDammit
from difflib import SequenceMatcher
from paper_integrity_repair import split_paper,set_fields

ROOT=Path(__file__).resolve().parents[1]
RECEIPT='ROUND3-ESSAY-20261012.jsonl'
BASE='74cd629e6318af0a30c77c0a3f0c8b0befaf4d22'
NATIONAL={(2016,'副省级'):178,(2016,'地市级'):179,(2017,'副省级'):181,(2017,'地市级'):180,(2018,'副省级'):182,(2018,'地市级'):183,(2019,'副省级'):184,(2019,'地市级'):185,(2020,'副省级'):253,(2020,'地市级'):254,(2021,'副省级'):255,(2021,'地市级'):256,(2022,'副省级'):258,(2022,'地市级'):259,(2022,'行政执法'):257,(2023,'副省级'):6419,(2023,'地市级'):5682,(2023,'行政执法'):4397}
CN={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
QRE=re.compile(r'^(?:第([一二三四五六七八九十\d]+)题[：:、.]?|([一二三四五六七八九十]+)[、．.：:]|[（(]([一二三四五六七八九十]+)[）)])\s*(.*)',re.S)
MRE=re.compile(r'^(?:给定)?(?:材料|资料)\s*([一二三四五六七八九十\d]+)\s*[：:、.．]?\s*$')
DETAIL=re.compile(r'(<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>)(.*?)(</details>)',re.S)

def sha(v):return hashlib.sha256(v.encode() if isinstance(v,str) else v).hexdigest()
def plain(t):return ''.join(c for c in unicodedata.normalize('NFKC',t) if c.isalnum())
def num(s):return int(s) if s.isdigit() else CN[s]
def paragraphs(node):
 return [t for p in node.find_all(['p','h2','h3','h4']) if not p.find('p') and (t:=p.get_text('',strip=True))]
def load(url):
 req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; source-integrity-review)'})
 with urlopen(req,timeout=35) as r:
  b=r.read(5000001);final=r.url
 if len(b)>5000000 or len(b)<100:raise ValueError('Empty/oversized source')
 html=UnicodeDammit(b,is_html=True).unicode_markup
 if html is None:raise ValueError('Undecodable source')
 s=BeautifulSoup(html,'html.parser')
 for e in s(['script','style','noscript']):e.decompose()
 return s,{'url':url,'resolved_url':final,'sha256':sha(b),'bytes':len(b)}
def body_questions(old):
 d=split_paper(old)
 return {n:q['text'].split('### 作答要求')[-1].strip() for n,q in d['qs'].items()}
def core(t):
 t=t.split('要求')[0]
 t=re.sub(r'[（(]\s*\d+\s*分\s*[）)]','',t)
 t=re.sub(r'(给定(?:资料|材料))\s*[\d一二三四五六七八九十～~、\-—]+',r'\1',t)
 return plain(t)
def match_questions(oldqs,newqs):
 result=[];seen=set()
 for oldn,old in oldqs.items():
  a=core(old)
  if len(a)<12:raise ValueError('Insufficient original stem evidence')
  scores=[]
  for n,new in newqs.items():
   b=core(new);sm=SequenceMatcher(None,a,b,autojunk=False)
   overlap=sum(m.size for m in sm.get_matching_blocks())/len(a)
   scores.append((overlap,n,sm.find_longest_match().size))
  scores.sort(reverse=True);best=scores[0]
  if best[0]<.87 or best[2]<12 or best[1] in seen:raise ValueError('Ambiguous/nonmatching stem '+str((oldn,scores,a)))
  if len(scores)>1 and scores[1][0]>.8 and best[0]-scores[1][0]<.1:raise ValueError('Nonunique stem mapping')
  seen.add(best[1]);result.append({'old_number':oldn,'new_number':best[1],'old_stem':old,'new_stem':newqs[best[1]],'original_stem_coverage':round(best[0],6)})
 return result

def parse_whole(ps,expected_questions):
 start=next((i for i,t in enumerate(ps) if re.fullmatch(r'二[、.．]?\s*给定[材资]料[：:]?',t)),None)
 end=next((i for i,t in enumerate(ps) if re.fullmatch(r'三[、.．]?\s*(?:作答|答题|申论)要求[：:]?',t)),None)
 if start is None or end is None or end<=start:raise ValueError('Missing explicit material/question section boundary')
 mp=ps[start+1:end];mats={};current=None
 for t in mp:
  m=MRE.fullmatch(t)
  if m:
   current=num(m[1]);
   if current in mats:raise ValueError('Duplicate material number')
   mats[current]=[]
  else:
   if current is None:raise ValueError('Unnumbered material '+t[:90])
   mats[current].append(t)
 if list(mats)!=list(range(1,len(mats)+1)) or not mats:raise ValueError('Noncontiguous materials')
 if any(len(''.join(v))<80 for v in mats.values()):raise ValueError('Empty/short material')
 qs={};current=None
 for t in ps[end+1:]:
  if re.match(r'^(注[：:]|答案及解析|参考答案|【参考答案|温馨提示|以上|更多真题|本文|相关阅读|推荐阅读|点击下载)',t):break
  m=QRE.match(t)
  if m:
   current=num(m[1] or m[2] or m[3])
   if current in qs:raise ValueError('Duplicate question number')
   qs[current]=[m[4]]
  else:
   if current is None:raise ValueError('Missing first question '+t[:90])
   qs[current].append(t)
 if list(qs)!=list(range(1,expected_questions+1)):raise ValueError('Wrong question count '+str(list(qs)))
 points=[]
 for n,lines in qs.items():
  full='\n\n'.join(lines)
  if '\ufffd' in full or not re.search(r'\d+\s*字',full):raise ValueError('Missing word limit/encoding '+str(n))
  first=re.findall(r'(\d+)\s*分',lines[0])
  points.append(int(first[-1]) if first else sum(map(int,re.findall(r'(\d+)\s*分',full))))
 if sum(points)!=100:raise ValueError('Non-100 source score '+str(points))
 if '\ufffd' in ''.join(mp):raise ValueError('Broken source encoding')
 return {'materials':mats,'questions':{n:'\n\n'.join(v) for n,v in qs.items()},'points':points,'notices':ps[:start],'source_paragraphs':mp+[x for ls in qs.values() for x in ls]}

def answer_patch(rel,source,answers,source_stems=None,checks=None):
 old=(ROOT/rel).read_text();d=split_paper(old);oldqs=body_questions(old)
 if source_stems:
  maps=match_questions({n:oldqs[n] for n in answers},{n:source_stems[n] for n in answers})
  if any(m['old_number']!=m['new_number'] for m in maps):raise ValueError('Answer number drift')
 else:maps=[]
 for n in answers:
  if not re.search(r'未收录|未取得|待核|尚未',d['answers'][n]):raise ValueError('Refuse to overwrite existing answer')
  if not 80<len(answers[n])<15000 or '\ufffd' in answers[n]:raise ValueError('Invalid answer length/encoding')
  if re.search(r'答案[：:]?\s*(?:略|暂缺)|登录后|付费|征集中',answers[n]):raise ValueError('Placeholder answer')
 def sub(m):
  n=int(m[2]);return m[1]+'\n\n'+answers[n]+'\n\n[本题来源参考答案]('+source['url']+')\n\n'+m[4] if n in answers else m[0]
 new=DETAIL.sub(sub,old)
 received=sorted(n for n in d['answers'] if n in answers or not re.search(r'^\s*(未收录|尚未取得)',d['answers'][n]))
 missing=sorted(set(d['answers'])-set(received))
 new=set_fields(new,{'已收录参考答案题号':received,'缺参考答案题号':missing,'第三轮修复凭据':'reports/'+RECEIPT},'2026-10-12第三轮：按同题明确来源补入缺失参考答案；原有答案和题面保持')
 nd=split_paper(new)
 for n in d['answers']:
  if n not in answers and d['answers'][n]!=nd['answers'][n]:raise ValueError('Old answer altered')
 # Metadata may change; question/material body must not.
 if old.split('---',2)[2].split('## 答案与解析')[0]!=new.split('---',2)[2].split('## 答案与解析')[0]:raise ValueError('Answer-only repair touched question body')
 return new,{'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'kind':'answer_only','sources':[source],'mappings':maps,'checks':checks or [],'added_answers':sorted(answers),'preserved_answers':[{'number':n,'sha256':sha(a)} for n,a in d['answers'].items() if n not in answers],'answer_hashes':{str(n):sha(a) for n,a in nd['answers'].items()},'body_sha256':sha(new.split('---',2)[2].split('## 答案与解析')[0]),'new_questions':0,'questions_after':len(oldqs)}

def render_whole(rel,parsed,source,extras=None):
 old=(ROOT/rel).read_text();d=split_paper(old);oldqs=body_questions(old);qs=parsed['questions']
 mappings=match_questions(oldqs,qs);answers={m['new_number']:d['answers'][m['old_number']] for m in mappings}
 # A known original Zhejiang answer ends with a repeated question block.
 relocations=[]
 if rel=='省考/浙江/2016/申论-A类.md':
  a=answers[1];m=re.search(r'\n\s*第一题\s*\n.*概括众筹的特点.*\Z',a,re.S)
  if m:
   relocations.append({'from_answer':1,'text':m[0],'sha256':sha(m[0]),'reason':'旧答案尾部夹入题面，完整作答要求已在正文归位；材料编号异文保留在凭据中'})
   answers[1]=a[:m.start()].rstrip()
 additions=[]
 for n in qs:
  if n not in answers:
   if extras and n in extras:
    answers[n]=extras[n][0]+'\n\n[本题来源参考答案]('+extras[n][1]['url']+')';additions.append(n)
   else:answers[n]='未收录同卷同题可靠参考答案；不以机器生成范文冒充来源答案。'
 fields={'真题性质':'机构公开整理真题；非官方原件','题号口径':'完整公开题本显式作答序号；原有答案按题干映射','来源整卷':source['url'],'来源整卷SHA256':source['sha256'],'实有题数':len(qs),'对照题本题量':len(qs),'缺失原题号':[],'给定材料段数':len(parsed['materials']),'题目分值':parsed['points'],'已收录参考答案题号':sorted(n for n,a in answers.items() if not a.startswith('未收录')),'缺参考答案题号':sorted(n for n,a in answers.items() if a.startswith('未收录')),'第三轮修复凭据':'reports/'+RECEIPT,'整卷核验状态':'完整机构公开题面及作答结构已对照；保留来源异文和历史答案，不是官方逐字认证'}
 prefix=set_fields(old.split('---',2)[0]+'---\n'+old.split('---',2)[1]+'---\n',fields,'2026-10-12第三轮：完整材料、题序、分值及字数要求归位；历史答案按题干定位保留')
 title=re.search(r'^# .+$',old,re.M)[0]
 chunks=[prefix.strip(),title,f'> 申论 · {len(qs)} 道大题 · 分值合计 100 分', '> **机构公开整理版本，非官方原件。** 下文材料编号与作答要求采用同一完整题本；原有答案按题干重定位，参考答案不等于官方答案。来源与历史文字异文见第三轮凭据。',f'[完整题面来源]({source["url"]})',' · '.join(f'[第{i}题](#第-{i}-题)' for i in qs)+' · [答案与解析](#答案与解析)']
 if parsed.get('notes'):chunks.append(parsed['notes'])
 if parsed['notices']:chunks+=['## 考试注意事项']+[p for p in parsed['notices'] if not re.fullmatch(r'一[、.．]?\s*注意事项[：:]?',p)]
 for n,ps in parsed['materials'].items():chunks += [f'## 给定资料 {n}']+ps
 for n,q in qs.items():chunks +=[f'## 第 {n} 题','### 作答要求',q]
 chunks+=['## 答案与解析','> 原有参考答案保留来源立场与措辞；旧解说中的局部材料编号可能不同于本卷全局编号，不据编号相似强行确认同义。']
 for n,a in answers.items():chunks +=[f'<details>\n<summary>第 {n} 题</summary>\n\n{a}\n\n</details>']
 new='\n\n'.join(chunks).strip()+'\n';nd=split_paper(new)
 if set(nd['qs'])!=set(qs) or set(nd['answers'])!=set(qs):raise ValueError('Rendered question/answer ids mismatch')
 for m in mappings:
  n=m['new_number']
  if not(rel.endswith('浙江/2016/申论-A类.md') and n==1) and nd['answers'][n]!=d['answers'][m['old_number']]:raise ValueError('Original answer lost')
 receipt={'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'kind':'whole_source_restore','sources':[source],'mappings':mappings,'source_paragraphs':[{'sha256':sha(x),'chars':len(x)} for x in parsed['source_paragraphs']],'material_hashes':{str(n):sha('\n\n'.join(ps)) for n,ps in parsed['materials'].items()},'question_hashes':{str(n):sha(q) for n,q in qs.items()},'points':parsed['points'],'added_answers':additions,'answer_hashes':{str(n):sha(a) for n,a in nd['answers'].items()},'preserved_answers':[{'old_number':m['old_number'],'number':m['new_number'],'sha256':sha(d['answers'][m['old_number']])} for m in mappings if not (rel.endswith('浙江/2016/申论-A类.md') and m['new_number']==1)],'relocated_from_answers':relocations,'new_questions':len(qs)-len(oldqs),'questions_after':len(qs),'materials_after':len(parsed['materials']),'original_material_blocks':[{'number':n,'sha256':sha(q['text'].split('### 作答要求')[0])} for n,q in d['qs'].items()]}
 return new,receipt

def national(item):
 (year,kind),id=item;url=f'https://www.aipta.com/article/{id}.html';rel=f'国考/{year}/申论-{kind}.md'
 try:
  soup,source=load(url);title=soup.select_one('.detail-info h1') or soup.find('h1');name=title.get_text('',strip=True) if title else ''
  if str(year) not in name or ('副省' not in name if kind=='副省级' else kind not in name):raise ValueError('Source identity mismatch '+name)
  node=soup.select_one('.info-body')
  if node is None:raise ValueError('Article body absent')
  ps=paragraphs(node);parsed=parse_whole(ps,4 if year==2016 and kind=='地市级' else 5)
  new,r=render_whole(rel,parsed,{**source,'title':name})
  return new,r,None
 except Exception as e:return None,None,{'path':rel,'url':url,'error':str(e),'paragraph_sample':ps[-28:] if 'ps' in locals() else []}

def javascript_free_answers(soup):
 spans=soup.select('details span.text-correct');heads=[e for e in soup.select('details span') if re.match(r'^第 [1-5] 题：',e.get_text())]
 if len(spans)!=4 or len(heads)!=4:raise ValueError('Static answer block count mismatch')
 answers={};qs={}
 for i,(a,h) in enumerate(zip(spans,heads),1):
  qs[i]=re.sub(r'^第 [1-5] 题：','',h.get_text()).strip()
  t=a.get_text().removeprefix('参考答案：').strip()
  t=t.split('文章分析')[0].strip() if i==4 else t
  answers[i]='\n\n'.join(x.strip() for x in t.splitlines() if x.strip())
 return qs,answers

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 results=[];errors=[]
 # Existing full bodies are left byte-identical in answer-only repairs.
 try:
  s,src=load('https://iget100.com/gongkao/shengkao/jiangsu/2018/shenlun-a');q,a=javascript_free_answers(s)
  results.append(answer_patch('省考/江苏/2018/申论-A类.md',src,{n:a[n] for n in [1,3,4]},q))
 except Exception as e:errors.append({'path':'省考/江苏/2018/申论-A类.md','error':str(e)})
 try:
  s,src=load('https://www.yjbys.com/edu/gongwuyuankaoshi/125956.html');ls=[x.strip() for x in s.get_text('\n').splitlines() if x.strip()]
  starts=[i for i,t in enumerate(ls) if re.fullmatch(r'[（(]一[）)]【参考答案】',t)];ends=[i for i,t in enumerate(ls) if re.fullmatch(r'[（(]二[）)]【参考答案】',t)]
  if len(starts)!=1 or len(ends)!=1:raise ValueError('Cannot isolate answer1')
  a='\n\n'.join(ls[starts[0]+1:ends[0]])
  old=(ROOT/'省考/江苏/2016/申论-A类.md').read_text()
  if not all(w in a and w in old for w in ['德孝文化','磨刀','红包','家风'] if w!='红包'):raise ValueError('Example identity mismatch')
  if not all(w in body_questions(old)[1] for w in ['社会风气','影响']):raise ValueError('Question identity mismatch')
  results.append(answer_patch('省考/江苏/2016/申论-A类.md',src,{1:a},checks=['来源明确2016江苏A；答案涉及同卷德孝、磨刀老人、N教授、祭祖、家风与赌博案例；未套用C类答案']))
 except Exception as e:errors.append({'path':'省考/江苏/2016/申论-A类.md','error':str(e)})
 # Inspect the B-specific source without inferring equality from A/C labels.
 try:
  s,src=load('http://www.jsgkw.org/2016/0315/12414.html');node=s.select_one('#content') or s
  print('JS16B_SOURCE',json.dumps(src,ensure_ascii=False),node.get_text('\n',strip=True)[:12000],flush=True)
 except Exception as e:errors.append({'path':'省考/江苏/2016/申论-B类.md','error':str(e)})
 with ThreadPoolExecutor(max_workers=6) as ex:
  for new,r,e in ex.map(national,NATIONAL.items()):
   if e:errors.append(e)
   else:results.append((new,r))
 for new,r in results:
  print('READY',json.dumps({k:v for k,v in r.items() if k in ['path','kind','new_questions','questions_after','materials_after','added_answers','points']},ensure_ascii=False),flush=True)
 for e in errors:print('REJECTED',json.dumps(e,ensure_ascii=False),flush=True)
 if args.apply:
  if (ROOT/'reports'/RECEIPT).exists():raise ValueError('Already applied; append follow-up instead of overwriting history')
  for new,r in results:
   p=ROOT/r['path']
   if sha(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent local change')
   p.write_text(new,encoding='utf-8',newline='\n')
  (ROOT/'reports'/RECEIPT).write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for _,r in results),encoding='utf-8')
  (ROOT/'reports/ROUND3-SOURCE-EXCEPTIONS-20261012.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('SUMMARY',json.dumps({'ready':len(results),'rejected':len(errors),'apply':args.apply},ensure_ascii=False))
if __name__=='__main__':main()
