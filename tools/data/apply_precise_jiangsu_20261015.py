"""Apply reviewed Jiangsu bodies and preserve complete prior versions."""
import sys,json,re,hashlib,copy
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,'tools');import round5_bulk as p,round4_gap_repair as g,full_repair_precise_answer_audit_20261015 as a,full_repair_answers_20261015 as app
sha=lambda s:hashlib.sha256(s.encode()).hexdigest();rows=json.loads(Path('tools/data/precise-jiangsu-review-input-20261015.json').read_text(encoding='utf-8'));entries=json.loads(Path('tools/data/precise-jiangsu-answer-plan-20261015.json').read_text(encoding='utf-8'));BASE='f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab'
pre={r['path']:Path(r['path']).read_text(encoding='utf-8') for r in rows};legacy={};boundary=[]
for r in rows:
 d=p.parse(pre[r['path']],r['path']);assert d['answers'][r['question_number']]==r['full_answer'],('Concurrent answer edit',r['path'],r['question_number'])
for e in entries:e['sources']=[{'title':'篇幅修订所据此前收录版本（固定Git基线；作者署名未核实）','url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+quote(e['path'],safe='/')}]
for i in [13,21]:
 r=rows[i];old=r['full_answer']
 if i==13:body=old[old.index('处理晒谷'):old.index('参考答案说明')].strip();reason='保留原有合规第一版本为当前主作答；较长第二版本完整移至历史对照，避免读者误认同一字数合规稿'
 else:body=Path('tools/data/jiangsu2020c-restored-body-20261015.txt').read_text(encoding='utf-8');reason='原主作答末尾错置于来源校勘附记，按连续原句将485字续文归回主区；不改写来源正文、不生成尾段'
 e={'path':r['path'],'number':r['question_number'],'question':r['question'],'answer':body,'author':'原收录来源参考稿，作者署名未核实；本轮仅整理解读边界/归位','attribution_kind':'source_reference','replace_reason':reason,'sources':[{'title':'本库固定版本同题参考稿（含校勘附记）','url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+quote(r['path'],safe='/')}]};app.validate_answer(e['question'],e);entries.append(e)
for e in entries:
 d=p.parse(pre[e['path']],e['path']);legacy.setdefault(e['path'],[]).append((e['number'],d['answers'][e['number']]))
reportpath=Path('reports/PRECISE-JIANGSU-NAMED-REPAIRS-20261015.json');reportpath.write_text(json.dumps({'status':'prepared','preimages':pre,'entries':entries},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
result,receipts=app.apply_entries(Path('.'),entries,True);assert result['status']=='passed',result
for i in [5,8]:
 r=rows[i];rel=r['path'];text=Path(rel).read_text(encoding='utf-8');d=p.parse(text,rel);old=d['answers'][r['question_number']];body=a.extract_versions(old)[0]['body'].split('（239字）')[0].strip();assert old.count(body)==1
 wrapped=old.replace(body,'<!-- full-repair-answer-20261015 -->\n'+body+'\n<!-- /full-repair-answer-20261015 -->',1)
 def sub(m):return m[1]+'\n\n'+wrapped+'\n\n'+m[4] if int(m[2])==r['question_number'] else m[0]
 text=g.DETAIL.sub(sub,text);Path(rel).write_text(text,encoding='utf-8',newline='');boundary.append({'path':rel,'number':r['question_number'],'action':'only_enclose_actual_body_exclude_count_claim_and_source_heading','characters':a.char_count(body),'body_sha256':sha(body),'original_full_answer':old})
for rel,olds in legacy.items():
 text=Path(rel).read_text(encoding='utf-8').rstrip()+'\n\n## 真实正文篇幅修订前版本\n\n旧稿仅作校勘、来源和写法对照，当前作答以各题明确正文区为准。\n'
 for n,old in olds:text+='\n<details>\n<summary>展开第'+str(n)+'题此前收录稿（校勘留存）</summary>\n\n'+old+'\n\n</details>\n'
 Path(rel).write_text(text.rstrip()+'\n',encoding='utf-8',newline='')
checks=[]
for rel,old in pre.items():
 text=Path(rel).read_text(encoding='utf-8').rstrip()+'\n';Path(rel).write_text(text,encoding='utf-8',newline='');before=p.parse(old,rel);after=p.parse(text,rel);assert before['questions']==after['questions'];assert before['materials']==after['materials'];touched={e['number'] for e in entries if e['path']==rel}|{b['number'] for b in boundary if b['path']==rel}
 for n,ans in before['answers'].items():
  if n not in touched:assert ans==after['answers'][n],(rel,n)
  else:
   v=a.extract_versions(after['answers'][n]);assert len(v)==1;issues=a.inspect_version(after['questions'][n],v[0],a.word_rules(after['questions'][n]))[1];assert not issues,(rel,n,issues)
 for n,ans in legacy.get(rel,[]):assert ans in text
 checks.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(text),'changed_tasks':sorted(touched),'task_material_unrelated_answers_unchanged':True})
report={'status':'passed','papers':len(checks),'ai_revision_tasks':35,'source_body_restorations':2,'boundary_only_tasks':2,'preimages':pre,'entries':entries,'boundary_repairs':boundary,'checks':checks,'applier_result':result,'boundary':'字数左右的90%–112%是库内复核目标，不宣称官方评分下限；正文性质明确、旧稿留存、未更动任何题面或材料。2019B范文补正考试后事例时序，2020C从旧稿附记归位真实485字续文。'}
reportpath.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print({k:report[k] for k in ['status','papers','ai_revision_tasks','source_body_restorations','boundary_only_tasks']})
