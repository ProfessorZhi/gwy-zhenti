#!/usr/bin/env python3
"""Prepare material-grounded writing packets; no inference service or source mutations."""
from __future__ import annotations
import collections,hashlib,json,re
from pathlib import Path
import r7_delivery as layout
from r7_reference_audit import assess,word_range,task_type
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/r9-context'
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 tasks=[];papers=[];bad=[];counter=0
 for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]):
  rel=p.relative_to(ROOT).as_posix();text=p.read_text(encoding='utf-8')
  try:
   d=layout.parse(text,rel)
   if d is None:raise ValueError('not essay')
  except Exception as e:
   bad.append({'path':rel,'error':str(e),'text':text});continue
  missing=[]
  for n,q in d['questions'].items():
   st=assess(q,d['answers'].get(n,''))
   if st['status']=='已收录':continue
   counter+=1;uid='R9-'+str(counter).zfill(4)
   t={'id':uid,'path':rel,'number':n,'question':q,'question_sha256':sha(q),
      'paper_sha256':sha(text),'kind':task_type(q),'word_range':word_range(q),'old_status':st['status']}
   tasks.append(t);missing.append((t,d['materials'][n]))
  if missing:papers.append((rel,missing))
 manifest={'baseline':'8c23683610441d82836b907e20c586f2b4622646','tasks':tasks,
           'unparsed':[{'path':x['path'],'error':x['error']} for x in bad]}
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 index=['# 第九轮逐卷写作材料索引','','临时分支资料，不代表已补入答案；只以原卷题干与给定材料作为作答依据。','',
        '| 材料包 | 待写ID | 原卷 |','|---|---|---|']
 for i in range(0,len(papers),3):
  group=papers[i:i+3];num=i//3;name='packet-'+str(num).zfill(3)+'.md';lines=[];ids=[];paths=[]
  for rel,missing in group:
   paths.append(rel);lines.extend(['# '+rel,''])
   mats=collections.OrderedDict()
   for t,mat in missing:
    mat=layout.strip_guide(mat)
    if mat.startswith('---'):mat=mat.split('---',2)[2]
    # Only collapse whitespace. Never discard material paragraphs or change wording.
    mat=re.sub(r'[ \t\u3000]+',' ',mat);mat=re.sub(r'\n{3,}','\n\n',mat).strip()
    key=sha(mat);mats.setdefault(key,{'text':mat,'ids':[]})['ids'].append(t['id'])
   for v in mats.values():lines.extend(['## 适用 '+', '.join(v['ids'])+' 的原材料','',v['text'],''])
   for t,mat in missing:
    ids.append(t['id']);lines.extend(['## '+t['id']+' ／ 原题 '+str(t['number'])+' ／ '+t['kind'],'',t['question'].strip(),''])
  (OUT/name).write_text('\n'.join(lines)+'\n',encoding='utf-8')
  index.append('| '+name+' | '+', '.join(ids)+' | '+'；'.join(paths)+' |')
 for i,item in enumerate(bad):
  name='unparsed-'+str(i).zfill(2)+'.md'
  (OUT/name).write_text('# 原路径：'+item['path']+'\n\n'+layout.strip_guide(item['text']),encoding='utf-8')
  index.append('| '+name+' | 题号结构待核 | '+item['path']+' |')
 (OUT/'index.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
 print('R9_PREPARED',json.dumps({'tasks':len(tasks),'papers':len(papers),'packets':(len(papers)+2)//3,
      'unparsed':len(bad),'by_kind':dict(collections.Counter(t['kind'] for t in tasks))},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
