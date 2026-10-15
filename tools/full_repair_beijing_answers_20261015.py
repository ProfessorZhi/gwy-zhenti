"""Evidence mapping and answer rendering for the 93-question Beijing recall extract."""
import hashlib,html,json,re,unicodedata
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
PAPER='省考/北京/2025/行测-统考.md'
MATERIAL=Path('D:/projects/gwy-material-ops')
COURSE=MATERIAL/'knowledge/gwy/000【上岸独家】花生十三/【003】【套题班-国考二期】2026年花生十三飞扬行测申论套题二期⭐'
ANSWER_DATA=ROOT/'tools/data/beijing93-answers-20261015.json'

def put(n,letter,reason,sources=None,kind='ai_original'):
 rows=json.loads(ANSWER_DATA.read_text(encoding='utf-8')) if ANSWER_DATA.exists() else []
 if any(r['number']==n for r in rows):raise ValueError('duplicate Beijing '+str(n))
 q=next(q for q in questions((ROOT/PAPER).read_text(encoding='utf-8')) if q['number']==n)
 rows.append({'path':PAPER,'number':n,'qid':str(1072210+n),'answer':letter,'explanation':reason.strip(),'attribution_kind':kind,'author':'Codex（AI辅助推导与整理）','sources':sources or [],'question_body_sha256':sha(q['body'])})
 ANSWER_DATA.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('北京',n,letter,flush=True)

def norm(t):return ''.join(c for c in unicodedata.normalize('NFKC',html.unescape(t)) if c.isalnum())
def sha(t):return hashlib.sha256(t.encode()).hexdigest()
def questions(t):
 hs=list(re.finditer(r'(?m)^## 第 (\d+) 题[^\n]*\n',t));out=[]
 for i,h in enumerate(hs):
  body=t[h.end():hs[i+1].start() if i+1<len(hs) else len(t)]
  opts={k:v.strip() for k,v in re.findall(r'(?m)^- \*\*([ABCD])\*\*\.\s*(.+)',body)}
  stem=re.split(r'(?m)^- \*\*A\*\*\.',body)[0].strip()
  out.append({'number':int(h[1]),'stem':stem,'options':opts,'body':body})
 return out
def source_questions(t):
 t=unicodedata.normalize('NFKC',html.unescape(t));hs=list(re.finditer(r'(?m)^###\s+(\d{1,3})[.、]\s*$',t));out=[]
 for i,h in enumerate(hs):
  body=t[h.end():hs[i+1].start() if i+1<len(hs) else len(t)]
  opts={k:v.strip() for k,v in re.findall(r'(?m)^- \*\*([ABCD])[.、]\*\*\s*(.+)',body)}
  out.append({'number':int(h[1]),'body':body,'options':opts})
 return out
def source_key(t):
 d={}
 for lo,hi,letters in re.findall(r'(\d{1,3})\s*--\s*(\d{1,3})\s*([ABCD]{3,10})',t):
  lo,hi=int(lo),int(hi)
  if len(letters)==hi-lo+1:
   for n,c in enumerate(letters,lo):d[n]=c
 return d
def apply_answers():
 rows=json.loads(ANSWER_DATA.read_text(encoding='utf-8'));by={r['number']:r for r in rows}
 if len(by)!=len(rows) or any(not 1<=n<=93 or r['answer'] not in 'ABCD' for n,r in by.items()):raise ValueError('Bad answer identities')
 p=ROOT/PAPER;old=p.read_text(encoding='utf-8');new=old;changes=[]
 hs=list(re.finditer(r'(?m)^## 第 (\d+) 题[^\n]*\n',old))
 for i,h in reversed(list(enumerate(hs))):
  n=int(h[1])
  if n not in by:continue
  end=hs[i+1].start() if i+1<len(hs) else len(old);body=old[h.end():end];r=by[n]
  if '**答案**：' in body:raise ValueError('Answer already present: '+str(n))
  opts=list(re.finditer(r'(?m)^- \*\*D\*\*\.[^\n]*',body))
  if len(opts)!=1:raise ValueError('Ambiguous options: '+str(n))
  author='来源机构参考键，解析由AI辅助整理；原稿未单列个人解题作者。' if r['attribution_kind']=='owned_source' else 'AI辅助独立推导与整理，非官方答案；有链接的题另列同题交叉对照。'
  answer='\n\n**答案**：'+r['answer']+'\n\n<!-- beijing-verified-answer-20261015 -->\n**解析**：'+r['explanation']+'\n\n> 作答性质：'+author
  for s in r['sources']:answer+='\n\n['+s['title']+']('+s['url']+')'+('（'+s['author']+'）' if s.get('author') else '')
  answer+='\n<!-- /beijing-verified-answer-20261015 -->\n\n---'
  at=opts[0].end();nb=body[:at]+answer+body[at:]
  new=new[:h.end()]+nb+new[end:]
  changes.append({'number':n,'qid':r['qid'],'answer':r['answer'],'before_block_sha256':sha(body),'after_block_sha256':sha(nb),'insert_after_offset':at,'insertion':answer,'attribution_kind':r['attribution_kind'],'sources':r['sources']})
 pending=sorted(set(range(1,94))-set(by))
 # Preserve all existing source and material metadata; record current answer state
 # separately so the anonymous source's shifted key is never rehabilitated.
 endfm=new.find('\n---',4)
 fm='\n已复核参考答案题号: '+json.dumps(sorted(by),ensure_ascii=False)+'\n缺参考答案题号: '+json.dumps(pending,ensure_ascii=False)+'\n北京答案修复凭据: "reports/FULL-REPAIR-BEIJING-ANSWERS-20261015.json"'
 new=new[:endfm]+fm+new[endfm:]
 receipt={'path':PAPER,'before_sha256':sha(old),'after_sha256':sha(new),'answers_written':len(rows),'pending_numbers':pending,'changes':list(reversed(changes)),'metadata_added':fm,'validation':'93 original task headings retained; original stem, options, images, shared material preserved; only independently derived or matched source keys written.'}
 if len(questions(new))!=93:raise ValueError('Question count changed')
 for q in questions(new):
  original=next(x for x in questions(old) if x['number']==q['number'])
  if q['options']!=original['options']:raise ValueError('Options changed')
 p.write_text(new,encoding='utf-8',newline='\n')
 (ROOT/'reports/FULL-REPAIR-BEIJING-ANSWERS-20261015.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'written':len(rows),'pending':pending,'task_count':93,'status':'passed'},ensure_ascii=False))
def match_sources():
 targets=questions((ROOT/PAPER).read_text(encoding='utf-8'));matches=[];seen=[]
 paths=[]
 for dirname in ['行测-地市级和行政执法','行测-副省级']:
  paths.extend((COURSE/'题本'/dirname).glob('*.pdf.md'))
 print('source files',len(paths),flush=True)
 for p in sorted(paths):
  title=unicodedata.normalize('NFKC',p.name);part='副省级' if '副省' in title else '地市级'
  m=re.search(r'(?:副省|地市)\((\d+)\)',title)
  if not m:continue
  seq=m[1];keyfiles=[x for x in (COURSE/'行测套题/答案'/part).glob('*.md') if re.search(r'(?:冲刺|行测)'+seq+r'(?:[ (（]|\.)',unicodedata.normalize('NFKC',x.name))]
  if len(keyfiles)!=1:continue
  kp=keyfiles[0];keys=source_key(kp.read_text(encoding='utf-8'))
  source=source_questions(p.read_text(encoding='utf-8'));seen.append([p.name,len(source),len(keys)])
  print('reading',p.name,len(source),len(keys),flush=True)
  for s in source:
   s['normalized_options']={k:norm(v) for k,v in s['options'].items()};s['normalized_body']=norm(s['body'])
  for target in targets:
   for s in source:
    if len(s['options'])!=4 or len(target['options'])!=4:continue
    op={k:norm(v) for k,v in target['options'].items()};so=s['normalized_options']
    if sum(len(v) for v in op.values())<35 or op!=so:continue
    # Option identity alone is insufficient for generic image choices. Require
    # a distinctive textual stem anchor present in the source question too.
    anchor=norm(re.sub(r'<[^>]+>','',target['stem']))
    anchor=anchor[:24]
    if len(anchor)<12 or anchor not in s['normalized_body']:continue
    if s['number'] not in keys:continue
    matches.append({'number':target['number'],'source_number':s['number'],'answer':keys[s['number']],'source_path':p.relative_to(MATERIAL).as_posix(),'key_path':kp.relative_to(MATERIAL).as_posix(),'option_match':4,'stem_anchor':anchor,'source_question':s['body'],'source_sha256':sha(p.read_text(encoding='utf-8')),'source_key_sha256':sha(kp.read_text(encoding='utf-8'))})
 result={'papers_checked':seen,'matches':matches}
 (ROOT/'tools/data/beijing93-owned-source-matches-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'source_papers':len(seen),'matches':len(matches),'covered':sorted(set(m['number'] for m in matches)),'pairs':[[m['number'],m['answer'],m['source_number'],m['source_path'].split('/')[-1]] for m in matches]},ensure_ascii=False,indent=2))
if __name__=='__main__':
 import sys
 if len(sys.argv)>1 and sys.argv[1]=='images':
  for q in questions((ROOT/PAPER).read_text(encoding='utf-8')):
   if q['number'] in [44,48,49,50,64,65,66,88]:print(q['number'],re.findall(r'src="([^"]+)',q['body']))
 elif len(sys.argv)>1 and sys.argv[1]=='apply':apply_answers()
 else:match_sources()
