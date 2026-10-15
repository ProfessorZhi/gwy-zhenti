"""Prepare explicitly matched Fujian sources; do not write paper MD."""
import json,re,sys,hashlib,subprocess
from pathlib import Path
from urllib.parse import quote
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'));sys.path.insert(0,str(Path(__file__).parent))
from confirm_priority_count_gaps_mops_20261015 import extract,QA
BASE=Path(r'D:\projects\gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
allpackets=json.loads((R/'tools/data/priority-confirmed-mops-source-packets-20261015.json').read_text(encoding='utf8'))
targets=['省考/福建/2016/申论-统考.md','省考/福建/2017/申论-统考.md','省考/福建/2019/申论-乡镇卷.md','省考/福建/2019/申论-县级卷.md','省考/福建/2020/申论-县级卷.md','省考/福建/2022/申论-省市卷.md','省考/福建/2018/申论-乡镇卷.md','省考/福建/2020/申论-乡镇卷.md']
conf=json.loads((R/'reports/PRIORITY-ESSAY-MOPS-COUNT-CONFIRMATION-20261015.json').read_text(encoding='utf8'))['rows'];out=[]
for target in targets:
 ds=[d for d in allpackets if d['target_path']==target]
 if ds:d=ds[0].copy()
 else:
  row=next(x for x in conf if x['path']==target);ss=row['sources']
  s=next(x for x in ss if '省市卷' in x['path']) if '2022/申论-省市卷' in target else max(ss,key=lambda x:x['minimum_task_similarity'])
  f=Path(s['path']);raw=f.read_text(encoding='utf8');e=extract(raw);assert e['status']=='explicit_complete_score100',(target,e['status'])
  rel=f.relative_to(BASE).as_posix();d=dict(target_path=target,source_path=str(f),source_relative_path=rel,source_commit=REV,source_url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(rel,safe='/'),source_sha256=hashlib.sha256(raw.encode()).hexdigest(),standard_question_count=e['question_count'],points=e['points'],questions=e['questions'])
 # Use exact raw source with only verified PDF publishing markers removed.
 raw=Path(d['source_path']).read_text(encoding='utf8');blob=subprocess.run(['git','-C',str(BASE),'show',REV+':'+d['source_relative_path']],capture_output=True,check=True).stdout;assert hashlib.sha256(blob).hexdigest()==d['source_sha256'],target
 t=re.sub(r'<!-- page:\s*(\d+)\s*-->\s*(?:\1(?!\d))?',lambda m:'\n\n',raw).replace('**','');qh=QA.search(t);assert qh,target
 before=t[:qh.start()]
 for x,y in [('给定材料材料1','给定材料\n\n材料1'),('”材料六2019','”\n\n材料六\n\n2019')]:before=before.replace(x,y)
 mh=list(re.finditer(r'(?m)^\s*(?:#{1,4}\s*)?(?:材料|资料)\s*([\d一二三四五六七八九十]+)(?:\s*[（(]\d+[）)])?\s*[：:]?',before));assert mh,target
 def num(label):
  if label.isdigit():return int(label)
  cn={c:i for i,c in enumerate('零一二三四五六七八九十')}
  if label in cn:return cn[label]
  a,b=label.split('十');return (cn[a] if a else 1)*10+(cn[b] if b else 0)
 mats=[dict(number=num(m[1]),source_label=m[1],text=before[m.end():mh[i+1].start() if i+1<len(mh) else None].strip()) for i,m in enumerate(mh)]
 assert [m['number'] for m in mats]==list(range(1,len(mats)+1)),(target,[m['number'] for m in mats])
 # The first explicit answer marker after the entire question section sets boundary.
 tail=t[qh.end():];ah=re.search(r'(?m)^\s*(?:#{1,4}\s*)?(?:[一二三四1-4][、.]\s*参考答案|20\d\d[^\n]{0,100}(?:解析|参考答案)|[（(][一二三四][）)]\s*[【\[]参考(?:答案|范文|例文))',tail)
 assert ah,(target,'answer region')
 d.update(materials=mats,source_answer_region=tail[ah.start():],source_git_blob_verified=True)
 # Clean publishers' next-page heading mistakenly included in final task by triage.
 for q in d['questions']:
  q['text']=re.split(r'(?m)^\s*20\d\d\s*年[^\n]*(?:解析|参考答案)',q['text'],1)[0].strip().replace('字。。','字。')
 out.append(d);print(target,len(mats),d['standard_question_count'],d['points'])
(R/'tools/data/fujian-full-restore-packets-a-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
