"""Prepare owned-source evidence packets, without touching any delivered paper."""
import sys,json,re,hashlib
from pathlib import Path
from urllib.parse import quote
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'));sys.path.insert(0,str(Path(__file__).parent))
from confirm_priority_count_gaps_mops_20261015 import QA
BASE=Path('D:/projects/gwy-material-ops');COMMIT='95676de3a494730fdcacd43416fd51d6bed48ab6'
d=json.loads((R/'reports/PRIORITY-ESSAY-MOPS-COUNT-CONFIRMATION-20261015.json').read_text(encoding='utf8'));out=[]
for row in d['rows']:
 if row['status'] not in ['confirmed_same_paper_missing_tasks','confirmed_same_paper_missing_constraints']:continue
 s=row['sources'][0];f=Path(s['path']);raw=f.read_text(encoding='utf8');t=re.sub(r'<!-- page:\s*\d+\s*-->','\n',raw).replace('**','');m=QA.search(t)
 if not m:m=re.search(r'(?m)^[ \t]*(?:#{1,4}\s*)?(?:(?:问题及作答要求|问题)\s*)?(?=问题一)',t)
 if not m:raise ValueError('Explicit source question start missing: '+str(f))
 before=t[:m.start()];source_before_cleaning=before;fixes=[]
 for old,new in [('给定材料材料1','给定材料\n\n材料1'),('”材料六2019','”\n\n材料六\n\n2019')]:
  if old in before:before=before.replace(old,new);fixes.append({'before':old,'after':new,'reason':'existing explicit material label glued to preceding paragraph; no content generated'})
 mh=list(re.finditer(r'(?m)^\s*(?:#{1,4}\s*)?(?:材料|资料)\s*([\d一二三四五六七八九十]+)(?:\s*[（(]\d+[）)])?\s*[：:]?',before))
 def material_number(label):
  if label.isdigit():return int(label)
  cn={c:i for i,c in enumerate('零一二三四五六七八九十')}
  if label in cn:return cn[label]
  if '十' in label:
   a,b=label.split('十',1);return (cn[a] if a else 1)*10+(cn[b] if b else 0)
  raise ValueError('Unknown material number '+label)
 mats=[{'source_label':x[1],'number':material_number(x[1]),'text':before[x.end():mh[i+1].start() if i+1<len(mh) else len(before)].strip()} for i,x in enumerate(mh)]
 # Retain the source's answer region for the agent to identify exact same-task answers.
 qregion=s['extraction']['question_region'];at=t.find(qregion.strip())
 ans=t[at+len(qregion.strip()):].strip() if at>=0 else ''
 rel=f.relative_to(BASE).as_posix()
 out.append({'target_path':row['path'],'source_path':str(f),'source_relative_path':rel,'source_commit':COMMIT,'source_url':'https://github.com/ProfessorZhi/gwy-material-ops/blob/'+COMMIT+'/'+quote(rel,safe='/'),'source_sha256':s['sha256'],'author':'源文件未明确编制者，不能冒称官方','standard_question_count':s['extraction']['question_count'],'points':s['extraction']['points'],'points_sum':s['extraction']['points_sum'],'materials':mats,'material_label_sequence_complete':[x['number'] for x in mats]==list(range(1,len(mats)+1)),'material_label_transcription_fixes':fixes,'questions':s['extraction']['questions'],'current_to_source_task_map':s['current_to_source_task_map'],'missing_source_task_numbers':row['missing_source_task_numbers'],'source_answer_region':ans,'source_answer_extraction_status':'raw post-question source region; must split by actual answer labels, retain author/score boundaries','warning':'Packet is evidence, not blind replacement. Preserve better current material where raw PDF OCR is worse; check question order and every scoring/word limit requirement.'})
 out[-1]['material_label_sequence_complete']=bool(mats) and out[-1]['material_label_sequence_complete']
 if not mats:out[-1]['material_structure_note']='原给定材料没有材料N格式标签，可能使用（一）等子节；完整材料仍在source_path，不能用空数组覆盖现材料。'
 out[-1]['attribution_excerpts']=[raw[max(0,m.start()-15):m.end()+70].split('\n')[0] for m in re.finditer(r'(?:来源|整理|作者)[：:]',raw)][:8]
 if any('整理' in x for x in out[-1]['attribution_excerpts']):out[-1]['author']='源原作作者未明确；整理者/来源署名须按attribution_excerpts分别注明，不将整理者冒称原作者'
(R/'tools/data/priority-confirmed-mops-source-packets-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('confirmed packets',len(out));print([(x['target_path'],len(x['materials']),x['standard_question_count'],len(x['source_answer_region'])) for x in out])
