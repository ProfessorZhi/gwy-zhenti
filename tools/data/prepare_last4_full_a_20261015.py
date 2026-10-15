import json,re,sys,hashlib,subprocess
from pathlib import Path
from urllib.parse import quote
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'));sys.path.insert(0,str(Path(__file__).parent))
from confirm_priority_count_gaps_mops_20261015 import extract,QA
from difflib import SequenceMatcher
import round5_bulk as b
M=Path('D:/projects/gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
rows=json.loads((R/'reports/PRIORITY-ESSAY-MOPS-COUNT-CONFIRMATION-20261015.json').read_text(encoding='utf8'))['rows']
net=json.loads(Path('D:/artifacts/gwy-quality-audit-20261015/last4-tianjin2021-guangdong2023-network-evidence.json').read_text(encoding='utf8'))['sources'];out=[]
for rel,needle,webid in [('省考/天津/2021/申论-市级卷.md','天津市级卷',1468),('省考/天津/2021/申论-区县卷.md','天津区县卷',1469),('省考/天津/2021/申论-行政执法.md','天津行政执法卷',1470),('省考/广东/2023/申论-县级卷.md','县级',None)]:
 row=next(r for r in rows if r['path']==rel);ss=next(s for s in row['sources'] if needle in Path(s['path']).name);sp=Path(ss['path']);raw=sp.read_bytes();sr=sp.relative_to(M).as_posix();blob=subprocess.run(['git','show',REV+':'+sr],cwd=M,check=True,stdout=subprocess.PIPE).stdout;assert blob==raw
 text=raw.decode();t=re.sub(r'<!-- page:\s*\d+\s*-->','\n',text).replace('**','');t=t.replace('（县级）材料一','（县级）\n\n材料一');qmark=QA.search(t)
 if qmark:before=t[:qmark.start()]
 else:before=t[:re.search(r'(?m)^\s*(?:#{1,4}\s*)?问题一',t).start()]
 heads=list(re.finditer(r'(?m)^\s*(?:#{1,4}\s*)?(?:给定)?(?:材料|资料)\s*([1-9一二三四五六七八九十])\s*[：:]?',before));materials=[]
 for i,m in enumerate(heads):
  n=int(m[1]) if m[1].isdigit() else '零一二三四五六七八九十'.index(m[1]);materials.append(dict(number=n,text=before[m.end():heads[i+1].start() if i+1<len(heads) else len(before)].strip()))
 qs=ss['extraction']['questions'];public=None
 if webid:
  public=next(n for n in net if '/'+str(webid)+'.html' in n['url']);pt=public['text'];matches=list(re.finditer(r'(?:三[、.]\s*作答要求|作答要求)',pt));assert matches;qt=pt[matches[-1].end():];scores=list(re.finditer(r'[（(]\s*(15|20|25|40)\s*分[）)]',qt));assert len(scores)==4;starts=[qt.rfind('\n\n',0,m.start())+2 for m in scores];qs=[dict(number=i+1,text=qt[x:starts[i+1] if i+1<len(starts) else len(qt)].split('注：篇幅有限')[0].strip(),points=[int(scores[i][1])]) for i,x in enumerate(starts)]
  # Public transcript corroborates original materials; use for local OCR crosscheck only.
  pm=pt[:matches[-1].start()];ph=list(re.finditer(r'(?m)^\s*(?:材料|资料)\s*([1-9])\s*[：:]?',pm));public_mats=[dict(number=int(m[1]),text=pm[m.end():ph[i+1].start() if i+1<len(ph) else len(pm)].strip()) for i,m in enumerate(ph)]
 else:public_mats=[]
 old=b.parse((R/rel).read_text(encoding='utf8'),rel);mapping=[]
 for n,q in old['questions'].items():
  nn,score=max(((z['number'],SequenceMatcher(None,b.qkey(q),b.qkey(z['text']),autojunk=False).ratio()) for z in qs),key=lambda v:v[1]);mapping.append(dict(old_number=n,new_number=nn,similarity=score))
 out.append(dict(path=rel,source_path=str(sp),source_relative_path=sr,source_commit=REV,source_url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(sr,safe='/'),source_sha256=hashlib.sha256(raw).hexdigest(),source_git_blob_verified=True,materials=materials,questions=qs,points=ss['extraction']['points'],mapping=mapping,public_url=public['url'] if public else None,public_materials=public_mats,source_full_text=text))
 print(rel,'MATS',len(materials),'PUBLICMATS',len(public_mats),'QS',[q['text'][:45] for q in qs],'MAP',mapping)
(R/'tools/data/last4-full-source-packets-a-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
