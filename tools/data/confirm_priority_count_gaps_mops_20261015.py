"""Read-only, evidence-ranked source task matching for catalog count discrepancies."""
import sys,json,re,hashlib
from pathlib import Path
from difflib import SequenceMatcher
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as p
BASE=Path('D:/projects/gwy-material-ops/knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf')
count_audit=json.loads((R/'reports/PRIORITY-ESSAY-QUESTION-COUNT-AUDIT-20261015.json').read_text(encoding='utf8'))
issues=list(count_audit['confirmed_count_discrepancies'])
seen_paths={x['path'] for x in issues}
for x in count_audit['rows']:
 if x['path'] not in seen_paths and x['status']=='same_count' and any(s is None for s in x['parsed_task_points']):issues.append(x);seen_paths.add(x['path'])
SCORE=re.compile(r'[（(]\s*(?:本题\s*)?(\d+)\s*分\s*[）)]')
QA=re.compile(r'(?m)^\s*(?:#{1,4}\s*)?(?:[一二三四五六七八九十]+[、．.]\s*)?(?:作答要求|申论要求|题目及要求|答题要求)[：:]?\s*$')
ANSWER=re.compile(r'(?m)^\s*(?:#{1,5}\s*)?(?:(?:20\d\d\s*年[^\n]{0,80})?(?:参考答案|答案及解析|答案解析)|[1-6一二三四五六][、．.]\s*参考答案|第[一二三四五六]题\s*[（(【：:]\s*参考答案)')
LABEL=re.compile(r'(?m)^[ \t　]*(?:#{1,4}\s*)?(?:问题[一二三四五六1-6][：:]?|第[一二三四五六1-6]题[：:]?|[（(][一二三四五六―-][）)]|[一二三四五六1-6][、．.])')
def task_key(text):
 text=re.sub(r'^\s*(?:#{1,4}\s*)?(?:问题)?(?:问题|题目)[一二三四五六1-6][：:]?\s*','',text)
 text=re.sub(r'[（(]\s*本题\s*\d+\s*分\s*[）)]','',text)
 return p.qkey(text)
def extract(s):
 t=re.sub(r'<!-- page:\s*\d+\s*-->','\n',s).replace('**','')
 markers=list(QA.finditer(t))
 if markers:start=markers[0].end()
 else:
  first=re.search(r'(?m)^[ \t]*(?:#{1,4}\s*)?(?:(?:问题及作答要求|问题)\s*)?(?=问题一)',t)
  if not first:return {'status':'no_explicit_question_section'}
  start=first.end()
 tail=t[start:];ans=ANSWER.search(tail)
 if ans:tail=tail[:ans.start()]
 labels=list(LABEL.finditer(tail));starts=[];qs=[]
 for i,m in enumerate(labels):
  text=tail[m.start():labels[i+1].start() if i+1<len(labels) else len(tail)].strip()
  if SCORE.search(text) and len(task_key(text))>=10:
   starts.append(m.start())
 for i,start in enumerate(starts):
  text=tail[start:starts[i+1] if i+1<len(starts) else len(tail)].strip()
  qs.append({'number':i+1,'text':text,'key':task_key(text),'points':[int(x) for x in SCORE.findall(text)]})
 pts=[q['points'][-1] for q in qs]
 # Some genuine PDF transcripts drop task numbers or OCR 一/二 as dashes.
 # Only use the alternative when explicit visible task scores sum to 100.
 scores=list(SCORE.finditer(tail))
 if not (2<=len(qs)<=6 and sum(pts)==100) and 2<=len(scores)<=6 and sum(int(m[1]) for m in scores)==100:
  starts=[];previous=0
  lead=re.compile(r'(?m)^\s*(?:#{1,4}\s*)?(?:[（(][^）)\n]{0,4}[）)]\s*)?(?=(?:根据|请|假设|假如|结合|[“"]给定|给定|平川县|G市))')
  for score in scores:
   region=tail[previous:score.start()]
   lexical=list(lead.finditer(region))
   labels2=[m for m in LABEL.finditer(region) if not re.match(r'(?:要求|准确|全面|字数|篇幅|观点|思路|内容|紧扣|考虑|条理|语言|表述|结构|对策|不超过|标题|参考|建议|逻辑|层次|所提|要点|总字数)',region[m.end():].lstrip('：:、 \t\n'))]
   options=[m.start() for m in lexical]+[m.start() for m in labels2]
   starts.append(previous+min(options) if options else previous)
   previous=score.end()
  alt=[]
  for i,start in enumerate(starts):
   q=tail[start:starts[i+1] if i+1<len(starts) else len(tail)].strip()
   alt.append({'number':i+1,'text':q,'key':task_key(q),'points':[int(scores[i][1])]})
  if all(len(q['key'])>=10 for q in alt):qs=alt;pts=[int(m[1]) for m in scores]
 return {'status':'explicit_complete_score100' if 2<=len(qs)<=6 and sum(pts)==100 else 'requires_source_review','question_count':len(qs),'points':pts,'points_sum':sum(pts),'questions':qs,'question_region':tail[:15000]}
def main():
 files={a:[f for d in BASE.iterdir() if d.is_dir() and a in d.name for f in d.rglob('*申论*.md')] for a in {x['area'] for x in issues}}
 out=[]
 for issue in issues:
  year=issue['year'];area=issue['area'];current=p.parse((R/issue['path']).read_text(encoding='utf8'),issue['path']);cqs={n:p.qkey(q) for n,q in current['questions'].items()};sources=[]
  for f in files.get(area,[]):
   if not f.name.startswith(str(year)):continue
   raw=f.read_text(encoding='utf8');e=extract(raw)
   maps=[]
   for n,key in cqs.items():
    scores=[(SequenceMatcher(None,key,q['key'],autojunk=False).ratio(),q) for q in e.get('questions',[])]
    if scores:
     ratio,q=max(scores,key=lambda z:z[0]);maps.append({'current_number':n,'source_number':q['number'],'question_similarity':round(ratio,6),'current_key':key,'source_key':q['key']})
   rank=min([m['question_similarity'] for m in maps],default=0) if len(maps)==len(cqs) else 0
   sources.append({'path':str(f),'relative_path':f.relative_to(Path('D:/projects/gwy-material-ops')).as_posix(),'sha256':hashlib.sha256(raw.encode()).hexdigest(),'extraction':e,'current_to_source_task_map':maps,'minimum_task_similarity':rank})
  sources.sort(key=lambda s:(s['minimum_task_similarity'],s['extraction']['status']=='explicit_complete_score100'),reverse=True)
  best=sources[0] if sources else None
  status='manual_source_selection_required';needs_constraints=any(not SCORE.search(q) or not re.search(r'\d+\s*(?:[-—～~]\s*\d+\s*)?字',q) for q in current['questions'].values())
  if best and best['minimum_task_similarity']>=.97 and best['extraction']['status']=='explicit_complete_score100':status='confirmed_same_paper_missing_tasks' if best['extraction']['question_count']>len(cqs) else 'confirmed_same_paper_missing_constraints' if needs_constraints else 'same_paper_task_count_now_complete'
  row={'path':issue['path'],'area':area,'year':year,'current_count':len(cqs),'catalog_count':issue['catalog_count'],'status':status,'sources':sources}
  if best:row['best_source']=best['path'];row['best_source_score']=best['minimum_task_similarity'];row['standard_count']=best['extraction'].get('question_count');row['missing_source_task_numbers']=sorted(set(q['number'] for q in best['extraction'].get('questions',[]))-{m['source_number'] for m in best['current_to_source_task_map'] if m['question_similarity']>=.97})
  out.append(row)
  print(area,year,issue['variant'],len(cqs),status,[(s['path'].split('\\')[-1],s['extraction']['status'],s['extraction'].get('question_count'),s['minimum_task_similarity']) for s in sources[:2]])
 (R/'reports/PRIORITY-ESSAY-MOPS-COUNT-CONFIRMATION-20261015.json').write_text(json.dumps({'date':'2026-10-15','rows':out,'method':'Actual same-year owned original transcripts, explicit task sections/scores, all current task keys mapped; no reconstruction from answer prose.'},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
if __name__ == '__main__':main()
