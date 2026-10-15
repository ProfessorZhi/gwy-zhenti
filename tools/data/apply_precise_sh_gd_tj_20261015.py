"""Reviewed Shanghai/Guangdong/Tianjin answer repairs. Never changes tasks/materials."""
import sys,json,re,hashlib,copy
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import round5_bulk as parser
import round4_gap_repair as g
import full_repair_answers_20261015 as applier
import full_repair_precise_answer_audit_20261015 as audit
ROOT=Path(__file__).resolve().parents[2]
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
BASE='f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab'
plan=json.loads((ROOT/'tools/data/precise-sh-gd-tj-answer-plan-20261015.json').read_text(encoding='utf-8'))
candidates=json.loads((ROOT/'reports/PRECISE-SH-GD-TJ-BASELINE-CANDIDATES-20261015.json').read_text(encoding='utf-8'))
pre=json.loads((ROOT/'reports/PRECISE-SH-GD-TJ-BASELINE-PREIMAGES-20261015.json').read_text(encoding='utf-8'))
byhash={e['body_sha256']:e for e in plan}
entries=[];to_wrap={};legacy={};evidence=[]
for r in candidates:
 rel=r['path'];n=r['question_number'];p=parser.parse(pre[rel],rel);old=p['answers'][n]
 if r['body_sha256'] in byhash:
  e=copy.deepcopy(byhash[r['body_sha256']]);e.update(path=rel,number=n,question=p['questions'][n],sources=[{'title':'修订所据既有同题参考版本（固定Git基线；原稿署名未核实）','url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+quote(rel,safe='/')}])
  applier.validate_answer(e['question'],e);entries.append(e);legacy.setdefault(rel,[]).append((n,old))
 elif rel=='省考/上海/2019/申论-行政执法卷.md':
  body=re.sub(r'^\*\*原创示范作答.*?\n\n','',old,flags=re.S).split('> 写作依据：')[0].strip()
  to_wrap.setdefault(rel,{})[n]=(body,'metadata_separation_only')
 elif rel in ('省考/广东/2025/申论-县镇.md','省考/广东/2025/申论-统考.md') and r['characters']==3442:
  title='以“产业兴”促“乡村兴”';at=old.find(title,old.find(title)+len(title));assert at>0
  body=old[:at].strip();to_wrap.setdefault(rel,{})[n]=(body,'composition_commentary_separation_only')

for rel in set(e['path'] for e in entries)|set(to_wrap):
 assert (ROOT/rel).read_text(encoding='utf-8')==pre[rel],('Concurrent edit',rel)
result,receipts=applier.apply_entries(ROOT,entries,True)
assert result['status']=='passed',result
for rel,items in to_wrap.items():
 text=(ROOT/rel).read_text(encoding='utf-8');d=parser.parse(text,rel)
 def sub(m):
  n=int(m[2])
  if n not in items:return m[0]
  body,reason=items[n];old=d['answers'][n];assert old.count(body)==1
  wrapped=old.replace(body,'<!-- full-repair-answer-20261015 -->\n'+body+'\n<!-- /full-repair-answer-20261015 -->',1)
  v=audit.extract_versions(wrapped);assert len(v)==1
  issues=audit.inspect_version(d['questions'][n],v[0],audit.word_rules(d['questions'][n]))[1]
  # The old mixed bucket has a missing original task limit; separation does not invent it.
  assert not [i for i in issues if i['confidence']!='manual'],issues
  evidence.append({'path':rel,'number':n,'action':reason,'body_characters':audit.char_count(body),'body_sha256':sha(body),'original_answer':old,'body_preserved_exactly':True})
  return m[1]+'\n\n'+wrapped+'\n\n'+m[4]
 text=g.DETAIL.sub(sub,text);(ROOT/rel).write_text(text.rstrip()+'\n',encoding='utf-8',newline='')
for rel,olds in legacy.items():
 text=(ROOT/rel).read_text(encoding='utf-8')
 text+='\n\n## 本轮修订前参考稿留存\n\n以下为篇幅修订前的既有收录稿，仅供校勘；当前主作答以各题的明确正文区为准。\n\n'
 for n,old in olds:text+='<details>\n<summary>展开第'+str(n)+'题此前收录版本（校勘留存）</summary>\n\n'+old+'\n\n</details>\n\n'
 (ROOT/rel).write_text(text.rstrip()+'\n',encoding='utf-8',newline='')
checks=[]
for rel in sorted(set(e['path'] for e in entries)|set(to_wrap)):
 text=(ROOT/rel).read_text(encoding='utf-8');before=parser.parse(pre[rel],rel);after=parser.parse(text,rel)
 assert before['questions']==after['questions'],('Task changed',rel)
 assert before['materials']==after['materials'],('Material changed',rel)
 touched={e['number'] for e in entries if e['path']==rel}|set(to_wrap.get(rel,{}))
 for n,old in before['answers'].items():
  if n not in touched:assert after['answers'][n]==old,('Unrelated answer changed',rel,n)
  else:
   if n in {x[0] for x in legacy.get(rel,[])}:assert old in text
   versions=audit.extract_versions(after['answers'][n]);assert len(versions)==1
   issues=audit.inspect_version(after['questions'][n],versions[0],audit.word_rules(after['questions'][n]))[1]
   assert not [i for i in issues if i['confidence']!='manual'],(rel,n,issues)
 checks.append({'path':rel,'before_sha256':sha(pre[rel]),'after_sha256':sha(text),'before_text':pre[rel],'task_and_material_exactly_unchanged':True,'changed_tasks':sorted(touched),'legacy_versions_preserved':len(legacy.get(rel,[]))})
report={'status':'passed','ai_revised_tasks':len(entries),'boundary_only_tasks':len(evidence),'papers':len(checks),'applier_result':result,'entries':entries,'boundary_repairs':evidence,'checks':checks,'boundary':'仅修正真实正文篇幅与明确正文边界；未更动题目/材料/字数限制；无原题字数的混合桶仍标人工核验，不伪造约束；不是官方评分认证。'}
(ROOT/'reports/PRECISE-SH-GD-TJ-REPAIRS-20261015.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print({k:report[k] for k in ['status','ai_revised_tasks','boundary_only_tasks','papers']})
