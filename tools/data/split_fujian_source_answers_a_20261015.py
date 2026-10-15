import json,re,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from full_repair_answers_20261015 import validate_answer
ds=json.loads((R/'tools/data/fujian-full-restore-packets-a-20261015.json').read_text(encoding='utf8'))
for d in ds:
 a=d['source_answer_region'];cn={c:i for i,c in enumerate('零一二三四')}
 pat=re.compile(r'(?:([一二三四1-4])[、.]\s*参考(?:答案|范文|例文)[:：]?|[（(]([一二三四])[）)]\s*[【\[]参考(?:答案|范文|例文)[】\]]|第([一二三四])题\s*[:：、]?\s*[【（(]?参考(?:答案|范文|例文))')
 hh=list(pat.finditer(a));out={}
 for i,m in enumerate(hh):
  ns=next(s for s in m.groups() if s);n=int(ns) if ns.isdigit() else cn[ns];body=a[m.end():hh[i+1].start() if i+1<len(hh) else None].strip()
  body=re.sub(r'^[（(]F[）)]\s*','',body);body=re.split(r'(?:#{1,4}\s*)?参考答案（H）|参考答案说明[:：]|文章分析|【试题解析】|【题目精析】|【审题及答题思路】',body,1)[0].strip()
  body=re.sub(r'(?m)^#{1,4}\s*','',body).strip();body=re.sub(r'^【备注[^】]+】','',body).strip()
  if str(n) not in out:out[str(n)]=body
 assert set(out)=={str(q['number']) for q in d['questions']},(d['target_path'],list(out))
 d['split_source_answers']=out
 print(d['target_path'])
 for q in d['questions']:
  n=str(q['number']);body=out[n]
  try:val=validate_answer(q['text'],dict(answer=body,attribution_kind='owned_source',author='来源校验'));state='PASS'
  except Exception as ex:state=str(ex)
  print(n,len(re.sub(r'\s','',body)),state,body[:130].replace('\n',''))
(R/'tools/data/fujian-full-restore-packets-a-20261015.json').write_text(json.dumps(ds,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
