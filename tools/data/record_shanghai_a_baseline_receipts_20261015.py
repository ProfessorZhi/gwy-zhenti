"""Disclose fixed Git before-images where transient working-state capture was lost."""
from pathlib import Path
import json,sys,hashlib,re,subprocess
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer
REV='f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab';BASE=Path(r'D:\artifacts\gwy-quality-audit-20261015\baseline-pr19-exact');sha=lambda x:hashlib.sha256(x).hexdigest()
packets=json.loads((ROOT/'tools/data/shanghai-additional-a-full-source-packets-20261015.json').read_text(encoding='utf8'))
rp=ROOT/'reports/FULL-REPAIR-SHANGHAI-ADDITIONAL-A-20261015.jsonl';records=[json.loads(x) for x in rp.read_text(encoding='utf8').splitlines() if x.strip()] if rp.exists() else [];present={r['path'] for r in records}
for d in packets:
 if d['year'] not in [2018,2019,2020] or d['path'] in present:continue
 raw=(BASE/d['path']).read_bytes();gitraw=subprocess.run(['git','show',REV+':'+d['path']],cwd=ROOT,capture_output=True,check=True).stdout;assert raw==gitraw,d['path']
 old=raw.decode('utf8');current=(ROOT/d['path']).read_text(encoding='utf8');op=b.parse(old,d['path']);nd=b.parse(current,d['path']);mapped=[];metrics=[]
 for on,oq in op['questions'].items():
  nn,sim=max(((nn,SequenceMatcher(None,b.qkey(oq),b.qkey(qq),autojunk=False).ratio()) for nn,qq in nd['questions'].items()),key=lambda x:x[1]);assert sim>.9;(mapped.append(dict(old_number=on,new_number=nn,question_similarity=sim)))
 for n,q in nd['questions'].items():
  answer=nd['answers'][n];m=re.search(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',answer,re.S);assert m
  count=validate_answer(q,dict(answer=m[1],attribution_kind='owned_source',author='校验条目'))
  metrics.append(dict(number=n,characters=count,answer_sha256=sha(m[1].strip().encode())))
 records.append(dict(path=d['path'],before_basis='fixed_git_baseline_not_immediate_previous_working_state',before_revision=REV,before_sha256=sha(raw),before_text=old,before_intermediate_working_state_preserved=False,disclosure='中间阶段before未保存；采用已与Git逐字节相等的固定f9c原稿作为可核验旧版本，不声称该baseline是最后一次写入前像。最终外层变更凭据按固定Git基线绑定终态。',after_sha256=sha(current.encode()),source_path=d['source_path'],source_revision='95676de3a494730fdcacd43416fd51d6bed48ab6',source_sha256=d['source_sha256'],questions=4,materials=len(d['materials']),answers=metrics,old_to_real_question_numbers=mapped))
rp.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf8');print('Preserved records',len(records),'fixed-baseline disclosures',sum(x.get('before_basis')=='fixed_git_baseline_not_immediate_previous_working_state' for x in records))
