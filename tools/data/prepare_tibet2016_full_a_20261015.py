import json,re,sys,hashlib,subprocess
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from cloud_quality import HEAD_Q,DETAIL
import round5_bulk as b
M=Path('D:/projects/gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6';base=M/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【27】西藏公务员考试真题pdf版/西藏公务员考试真题——行测09-19'
sha=lambda x:hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest();sources=[]
texts=[]
for sub in ['题目','答案及解析']:
 p=next((base/sub).glob('2016*.md'));raw=p.read_bytes();sr=p.relative_to(M).as_posix();blob=subprocess.run(['git','show',REV+':'+sr],cwd=M,check=True,stdout=subprocess.PIPE).stdout;assert raw==blob;t=raw.decode();t=re.sub(r'<!-- page:\s*(\d+)\s*-->\s*(?:\1(?!\d))?','\n\n',t);texts.append(t);sources.append(dict(path=str(p),source_url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(sr,safe='/'),source_commit=REV,source_sha256=sha(raw),git_blob_verified=True))
t,at=texts;t=t.replace('高于21 元117、','高于21 元\n\n117、');hs=list(re.finditer(r'(?m)^\s*(?:#{1,4}\s*)?(\d{1,3})[、．.]',t));assert [int(m[1]) for m in hs]==list(range(1,126));questions={};materials=[]
for i,m in enumerate(hs):
 n=int(m[1]);q=t[m.end():hs[i+1].start() if i+1<len(hs) else len(t)].strip();mat=re.search(r'[（(]材料([1-4])[）)]',q)
 if mat:materials.append(dict(number={105:1,110:2,115:3,120:4}[n],source_label=int(mat[1]),text=q[mat.end():].strip(),before_question=n+1));q=q[:mat.start()].strip()
 q=re.split(r'(?m)^\s*##\s*第[一二三四五]部分',q)[0].strip();questions[n]=q
ah=list(re.finditer(r'(?m)^\s*(\d{1,3})、正确答案[：:]\s*([A-D])',at));assert [int(m[1]) for m in ah]==list(range(1,126)),[int(m[1]) for m in ah];source_answers={int(m[1]):dict(letter=m[2],text=at[m.end():ah[i+1].start() if i+1<len(ah) else len(at)].strip()) for i,m in enumerate(ah)}
rel='省考/西藏/2016/行测-统考.md';raw=(R/rel).read_bytes();old=raw.decode();hh=list(HEAD_Q.finditer(old));ans={int(n):txt for n,txt in DETAIL.findall(old)};assert len(hh)==len(ans)==120
old_qs={int(m[1]):re.split(r'(?m)^## 答案与解析',old[m.end():hh[i+1].start() if i+1<len(hh) else len(old)],1)[0].strip() for i,m in enumerate(hh)}
mapping=[];missing=[69,71,72,74,75];realnums=[n for n in range(1,126) if n not in missing]
for on,nn in enumerate(realnums,1):
 # Source has final module/common-material blocks, never compare those to a question stem.
 a=re.sub(r'<[^>]*>','',old_qs[on]);a=re.split(r'2015年2月，我国快递业务|2014年4月.?2015年4月全国租赁贸易',a)[0];a=re.split(r'(?m)^>\s*选项',a)[0];a=re.sub(r'^\s*常识判断|^\s*言语理解与表达|^\s*数量关系|^\s*判断推理|^\s*资料分析','',a).strip();ratio=SequenceMatcher(None,b.norm(a),b.norm(questions[nn]),autojunk=False).ratio();mapping.append(dict(old_number=on,original_number=nn,question_similarity=ratio));assert ratio>.88,(on,nn,ratio,a[:100],questions[nn][:100])
out=dict(path=rel,before_text=old,before_sha256=sha(raw),sources=sources,questions=questions,materials=materials,source_answers=source_answers,old_questions=old_qs,old_answers=ans,mapping=mapping,missing_original_numbers=missing)
(R/'tools/data/tibet2016-complete-owned-source-a-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(questions=len(questions),answers=len(source_answers),materials=[dict(number=m['number'],before_question=m['before_question'],characters=len(m['text'])) for m in materials],mapping_count=len(mapping),minimum_question_similarity=min(x['question_similarity'] for x in mapping),missing=missing),ensure_ascii=False))
