"""Correct four stale summary counts without changing any task/material/answer."""
from pathlib import Path
import hashlib,json,os,re,uuid
import round5_bulk as parser
import full_repair_precise_answer_audit_20261015 as precise
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b if isinstance(b,bytes) else b.encode()).hexdigest()
def main():
 rows=[('省考/山东/2023/申论-B类.md',2,3,'旧摘要未随第3道完整作文和参考正文补入而更新'),('省考/深圳/2019/申论-一卷.md',6,3,'旧合卷两套各3题的总数6未随显式一卷题面拆分而更新'),('省考/黑龙江/2018/申论-省直.md',5,4,'旧摘要题量5与正文4题、4答案及15/20/25/40分不符'),('省考/黑龙江/2021/申论-省级.md',2,4,'旧摘要未随完整4题、4答案及15/20/25/40分同步更新')]
 receipt=ROOT/'reports/FULL-REPAIR-B-DECLARED-ANSWER-COUNTS-20261015.jsonl';results=[]
 for rel,oldcount,count,reason in rows:
  file=ROOT/rel;before=file.read_bytes();old=before.decode('utf8');paper=parser.parse(old,rel)
  assert sorted(paper['questions'])==list(range(1,count+1));assert set(paper['questions'])==set(paper['answers'])
  refs=[]
  for n,q in paper['questions'].items():
   vs=precise.extract_versions(paper['answers'][n]);assert any(v['characters'] and not precise.inspect_version(q,v,precise.word_rules(q))[1] for v in vs),(rel,n)
   refs.append({'number':n,'question_sha256':sha(q),'answer_sha256':sha(paper['answers'][n]),'main_body_characters':[v['characters'] for v in vs]})
  pattern=re.compile(r'(?m)^(> 申论 · )'+str(oldcount)+r'( 题 · [^\n]+)$');assert len(list(pattern.finditer(old)))==1
  new=pattern.sub(lambda m:m[1]+str(count)+m[2],old,count=1)
  again=parser.parse(new,rel);assert again['questions']==paper['questions'] and again['answers']==paper['answers']
  row={'path':rel,'status':'prepared','reason':reason,'before_text':old,'before_sha256':sha(before),'after_text':new,'after_sha256':sha(new),'old_declared_questions':oldcount,'new_declared_questions':count,'questions_and_answers_unchanged':True,'material_and_other_content_unchanged':True,'verified_current_tasks':refs,'boundary':'仅纠正现有正文摘要数量；不据此新增原题、推定官方完整性或新计答案缺口。北京2025行测真实88/93及5题共用条件缺失未改。'}
  with receipt.open('a',encoding='utf8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  assert file.read_bytes()==before
  temp=file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(new.encode());os.replace(temp,file)
  with receipt.open('a',encoding='utf8') as f:f.write(json.dumps({'path':rel,'status':'applied','after_sha256':sha(file.read_bytes())},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  results.append({'path':rel,'before':oldcount,'after':count,'answer_blocks':count});print(results[-1],flush=True)
 (ROOT/'reports/FULL-REPAIR-B-DECLARED-ANSWER-COUNTS-SUMMARY-20261015.json').write_bytes((json.dumps({'status':'passed','changed_files':4,'changed_summary_lines':4,'new_tasks_or_answers':0,'details':results,'known_real_mismatch_retained':{'path':'省考/北京/2025/行测-统考.md','recognized_recall_tasks':93,'usable_answers':88,'missing_shared_conditions':[56,57,58,79,80]}},ensure_ascii=False,indent=2)+'\n').encode())
if __name__=='__main__':main()
