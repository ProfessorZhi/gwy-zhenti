#!/usr/bin/env python3
"""Apply reviewed aptitude repairs with SHA-256 receipts; never invent questions."""
from pathlib import Path
import argparse,json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
def sha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def clean(s):
 s=re.sub(r'<!--\s*page:\s*\d+\s*-->','',s)
 s=re.sub(r'(?m)^\s*-?\s*\d+\s*-?\s*$','',s)
 s=re.sub(r'\n{3,}','\n\n',s).strip()
 return s
def run(plan,apply=False):
 receipts=[]
 for spec in plan:
  p=ROOT/spec['path'];old=p.read_text(encoding='utf8')
  assert sha(old)==spec['before_sha256'],f'Concurrent edit: {p}'
  new=old;records=[]
  for n in spec['missing']:
   body='**答案**：'+spec['answers'][str(n)]+'\n\n**参考解析（用户提供资料）**\n\n'+clean(spec['source_sections'][str(n)])
   if n==5 and '边境县' in spec['path']:
    body+='\n\n> 版本说明：来源将本题列为单选，但解析认定B、D均正确；保留来源争议，不将BD冒称官方标准答案。'
   body+='\n\n**来源**：用户提供《'+Path(spec['source']).name.removesuffix('.md')+'》，第'+str(n)+'题；资料性质为机构/个人整理参考解析，原文件标记“来源：F”（未明确机构全称），不是官方公布答案。源文件SHA-256：`'+spec['source_sha256']+'`。'
   pat=r'(<details>\s*<summary>第 '+str(n)+r' 题</summary>)(.*?)(</details>)'
   m=re.search(pat,new,re.S)
   if m:
    assert not re.search(r'\*\*答案\*\*[：:]\s*[ABCD]',m[2]),'Existing answer would be overwritten'
    new=new[:m.start()]+m[1]+'\n\n'+body+'\n\n'+m[3]+new[m.end():]
   else:
    if '## 答案与解析' not in new:new=new.rstrip()+'\n\n## 答案与解析\n'
    new=new.rstrip()+'\n\n<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+body+'\n\n</details>\n'
   records.append({'question':n,'answer':spec['answers'][str(n)],'answer_body_sha256':sha(body)})
  new=new.rstrip()+'\n'
  receipt={k:v for k,v in spec.items() if k not in ('source_sections','answers')}
  receipt.update(after_sha256=sha(new),added=records,boundary='同卷用户提供解析补录；既有题干、图像、选项、已有答案未改动。对照旧答案出现的7项版本分歧另列，不据少数分歧覆盖原字母。PDF公式转录完整性仍须独立复核。')
  receipts.append(receipt)
  if apply:p.write_text(new,encoding='utf8',newline='\n')
 if apply:(ROOT/'reports/FULL-REPAIR-APTITUDE-ANSWERS-20261015.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 return receipts
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--apply',action='store_true');a=ap.parse_args();r=run(json.loads(a.plan.read_text(encoding='utf8')),a.apply);print(json.dumps({'applied':a.apply,'papers':len(r),'added_answers':sum(len(x['added']) for x in r)},ensure_ascii=False))
