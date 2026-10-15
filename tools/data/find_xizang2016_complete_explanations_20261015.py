"""Read-only search for complete same-condition/same-option existing explanations."""
import re,json,sys,hashlib,difflib,html
from pathlib import Path
sys.path.insert(0,'tools');import round5_bulk as parser
R=Path('.');target=R/'省考/西藏/2016/行测-统考.md';T=target.read_text(encoding='utf-8');numbers=[59,61,62,64,65,66,85,106,109,110,113,114,115,116,117,118,119,120,122,123,125]
def norm(s):
 s=re.sub(r'<img[^>]*>|!\[[^\]]*\]\([^)]*\)','',s);s=re.sub(r'<[^>]+>|<!--.*?-->','',s,flags=re.S);return parser.norm(html.unescape(s))
def blocks(s):
 s=s[:s.index('## 答案与解析')];heads=list(re.finditer(r'(?m)^#{2,3}\s*第\s*(\d+)\s*题[^\n]*\n',s));d={}
 for i,m in enumerate(heads):
  raw=s[m.end():heads[i+1].start() if i+1<len(heads) else len(s)];raw=re.split(r'(?m)^## 材料',raw)[0];d[int(m[1])]=raw.strip()
 return d
q=blocks(T);hits={n:[] for n in numbers}
for f in R.glob('省考/*/2016/行测*.md'):
 if f==target:continue
 s=f.read_text(encoding='utf-8');qs=blocks(s);ans={int(m[1]):m[2].strip() for m in re.finditer(r'<summary>第\s*(\d+)\s*题</summary>(.*?)</details>',s,re.S)}
 for n in numbers:
  stem=norm(q[n].split('- **A**.')[0]);opts=norm(q[n].split('- **A**.',1)[-1]);pot=[]
  for k,v in qs.items():
   sk=norm(v.split('- **A**.')[0])
   if sk==stem:pot.append((k,1.0))
   elif len(sk)>20 and abs(len(sk)-len(stem))<25 and sk[:15]==stem[:15]:
    ratio=difflib.SequenceMatcher(None,stem,sk,autojunk=False).ratio()
    if ratio>.94:pot.append((k,ratio))
  for k,ratio in pot:
   other=qs[k];op2=norm(other.split('- **A**.',1)[-1]);ar=ans.get(k,'');imgs=re.findall(r'src="([^"]+)"',ar);missing=bool(re.search(r'为\s*[，。]|则\s*[，。]|得\s*[，。]|为\s*（[^）]{0,4}）',re.sub(r'<[^>]+>','',ar)))
   hits[n].append({'path':f.as_posix(),'number':k,'stem_similarity':ratio,'options_text_equal':opts==op2,'target_options_normalized':opts,'donor_options_normalized':op2,'images_in_explanation':imgs,'characters':len(ar),'has_blank_pattern':missing,'answer':ar,'question':other,'donor_md_sha256':hashlib.sha256(s.encode()).hexdigest()})
out={'target_path':target.as_posix(),'target_sha256':hashlib.sha256(T.encode()).hexdigest(),'read_only':True,'matches':hits};Path('tools/data/xizang2016-complete-explanation-candidates-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for n,rows in hits.items():
 ranked=sorted(rows,key=lambda r:(not r['options_text_equal'],r['has_blank_pattern'],-len(r['images_in_explanation']),-r['stem_similarity'],-r['characters']));print(n,[(x['path'],x['number'],x['options_text_equal'],len(x['images_in_explanation']),x['has_blank_pattern']) for x in ranked[:3]],flush=True)
