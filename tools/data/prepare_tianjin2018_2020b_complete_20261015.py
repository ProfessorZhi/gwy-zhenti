import sys,re,json,hashlib,subprocess,os,difflib
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,'tools');import round5_bulk as p,full_repair_precise_answer_audit_20261015 as a
R=Path('.');M=Path('D:/projects/gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6';GIT=r'D:\develop\sdk\Git\mingw64\bin\git.exe'
base=M/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【26】天津公务员考试真题pdf版/天津公务员考试真题——申论【05-25】'
web=json.loads(Path('D:/artifacts/gwy-quality-audit-20261015/tianjin2018-2020b-network-evidence.json').read_text(encoding='utf-8'))['sources'];packets=[]
for rel,filename,url in [('省考/天津/2018/申论-统考.md','2018年421联考《申论》（天津卷）真题及参考答案.pdf.md','https://www.aipta.com/article/1464.html'),('省考/天津/2020/申论-B类.md','2020年0725公务员多省联考《申论》题（天津区县卷）真题及参考答案.pdf.md','https://www.aipta.com/article/1467.html')]:
 sp=base/filename;raw=sp.read_bytes();text=raw.decode('utf-8');sr=sp.relative_to(M).as_posix();env={**os.environ,'GIT_CONFIG_GLOBAL':'NUL','GIT_CONFIG_NOSYSTEM':'1'};blob=subprocess.check_output([GIT,'-c','core.fsmonitor=false','rev-parse',REV+':'+sr],cwd=M,env=env,timeout=60).decode().strip();fixed=subprocess.check_output([GIT,'-c','core.fsmonitor=false','cat-file','blob',blob],cwd=M,env=env,timeout=60);assert fixed==raw
 t=re.sub(r'<!-- page:\s*\d+\s*-->','\n',text).replace('**','');qm=re.search(r'(?m)^#{1,4}\s*[二三][、.]\s*作答要求',t);assert qm
 before=t[:qm.start()];before=re.sub(r'(?m)^\s*\d{1,2}(?=材料[一二三四五六123456])','',before)
 hs=list(re.finditer(r'(?m)^\s*(?:#{1,4}\s*)?(?:材料|资料)\s*([1-6一二三四五六])\s*[：:]?',before));mats=[]
 for i,h in enumerate(hs):
  n=int(h[1]) if h[1].isdigit() else '零一二三四五六'.index(h[1]);s=before[h.end():hs[i+1].start() if i+1<len(hs) else len(before)].strip();s=re.sub(r'(?m)^\s*\d{1,2}\s*$','',s);s=re.sub(r'(?m)^5(?=是，直接向用户收费)','',s);s=s.replace('一幅幅幅佳作','一幅幅佳作');mats.append({'number':n,'text':s})
 assert [x['number'] for x in mats]==[1,2,3,4,5,6],(filename,[x['number'] for x in mats])
 pub=next(x for x in web if x['url']==url);qt=pub['text'].split('三、作答要求')[1].split('注：篇幅有限')[0].strip();scores=list(re.finditer(r'[（(]\s*(15|20|25|40)分\s*[）)]',qt));assert len(scores)==4;scoresint=[int(m[1]) for m in scores];starts=[qt.rfind('\n\n',0,m.start())+2 for m in scores];qs={i+1:qt[st:starts[i+1] if i+1<len(starts) else len(qt)].strip() for i,st in enumerate(starts)};assert scoresint==[15,20,25,40]
 old=Path(rel).read_text(encoding='utf-8');d=p.parse(old,rel);mapping=[]
 for n,q in d['questions'].items():
  k,best=max(((k,difflib.SequenceMatcher(None,p.qkey(q),p.qkey(v),autojunk=False).ratio()) for k,v in qs.items()),key=lambda x:x[1]);assert best>.96,(rel,n,k,best);mapping.append({'old_number':n,'new_number':k,'task_similarity':best,'old_question':q,'source_question':qs[k]})
 # Extract owned-source essay, never copy third-party web answers.
 if '2018' in rel:
  last=t[t.index('### 4、参考答案：'):];am=list(re.finditer(r'(?m)^#{1,4}\s*【参考答案】',last));assert am;essay=last[am[-1].end():].strip();essay=re.sub(r'(?m)^\s*9(?=让传统文化)','',essay);essay=essay.replace('传统文化的共享与传承《国家宝藏》','传统文化的共享与传承\n\n《国家宝藏》')
 else:essay=t.split('## 四、参考答案',1)[1].strip();essay=essay.replace('定分工，汇民智，推进社区精细化治理所谓','定分工，汇民智，推进社区精细化治理\n\n所谓')
 essay=re.sub(r'(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])','',essay);essay=re.sub(r'\n{3,}','\n\n',essay).strip();v=a.strip_body(essay);issues=a.inspect_version(qs[4],v,a.word_rules(qs[4]))[1]
 packets.append({'path':rel,'source_path':str(sp),'source_relative_path':sr,'source_commit':REV,'source_git_blob':blob,'source_git_blob_verified':True,'source_sha256':hashlib.sha256(raw).hexdigest(),'source_url':'https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(sr,safe='/'),'public_url':url,'public_title':pub['title'],'public_response_sha256':hashlib.sha256(pub['text'].encode()).hexdigest(),'public_question_region':qt,'materials':mats,'questions':qs,'points':scoresint,'mapping':mapping,'source_answer_4':essay,'answer_4_characters':a.char_count(essay),'answer_4_issues':issues,'source_full_text':text,'before_text':old,'before_sha256':hashlib.sha256(old.encode()).hexdigest()})
 print(rel,'MATS',len(mats),'MAP',[(x['old_number'],x['new_number'],x['task_similarity']) for x in mapping],'ESSAY',a.char_count(essay),issues,flush=True)
Path('tools/data/tianjin2018-2020b-complete-source-packets-20261015.json').write_text(json.dumps(packets,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
