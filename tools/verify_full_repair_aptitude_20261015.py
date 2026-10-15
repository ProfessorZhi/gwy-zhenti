#!/usr/bin/env python3
"""Check independent baseline invariants for aptitude changes without image rewriting."""
from pathlib import Path
import subprocess,json,re,hashlib
R=Path(__file__).resolve().parents[1];BASE='f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab'
def qblocks(t):
 f=t.split('## 答案与解析',1)[0];ms=list(re.finditer(r'(?m)^#{2,3} 第 (\d+) 题[^\n]*\n',f));return {int(m[1]):f[m.end():ms[i+1].start() if i+1<len(ms) else len(f)].strip() for i,m in enumerate(ms)}
def answers(t):
 return {int(m[1]):a[1] for m in re.finditer(r'<summary>第 (\d+) 题</summary>(.*?)</details>',t,re.S) if (a:=re.search(r'\*\*答案\*\*[：:]\s*([ABCD]+)',m[2]))}
def image_refs(t):return re.findall(r'(?:!\[[^\]]*\]\(|src=["\'])([^)"\']+\.(?:png|jpe?g|gif|webp|bmp|svg))',t,re.I)
def main(baseline_root=None,git_bin='git'):
 git=[git_bin,'-c','core.fsmonitor=false']
 rows=[] if baseline_root else subprocess.run(git+['ls-tree','-rz',BASE],cwd=R,check=True,stdout=subprocess.PIPE).stdout.split(b'\0');entries=[]
 for row in rows:
  if not row:continue
  meta,path=row.split(b'\t',1);rel=path.decode('utf8')
  if rel.startswith(('省考/','国考/')) and '/行测-' in rel and rel.endswith('.md') and rel!='省考/北京/2025/行测-统考.md':entries.append((meta.split()[2].decode(),rel))
 if baseline_root:
  entries=[('',p.relative_to(baseline_root).as_posix()) for area in ['国考','省考'] for p in (baseline_root/area).rglob('行测-*.md') if p.relative_to(baseline_root).as_posix()!='省考/北京/2025/行测-统考.md']
  raw=b''
 else:
  proc=subprocess.run(git+['cat-file','--batch'],cwd=R,input=('\n'.join(x[0] for x in entries)+'\n').encode(),check=True,stdout=subprocess.PIPE);raw=proc.stdout
 pos=0;reports=[];changed_q=[];changed_a=[];added=0
 allowed_q={('国考/2024/行测-副省级.md',12),('省考/西藏/2016/行测-统考.md',96),('省考/江苏/2024/行测-C类.md',110),('省考/山东/2023/行测-统考.md',42)}
 for _,rel in entries:
  if baseline_root:old=(baseline_root/rel).read_text(encoding='utf8')
  else:
   end=raw.index(b'\n',pos);head=raw[pos:end];size=int(head.split()[-1]);old=raw[end+1:end+1+size].decode('utf8');pos=end+1+size+1
  new=(R/rel).read_text(encoding='utf8')
  oq,nq=qblocks(old),qblocks(new);assert set(oq)==set(nq),(rel,'question IDs changed')
  cq=[n for n in oq if oq[n]!=nq[n]]
  assert all((rel,n) in allowed_q for n in cq),(rel,'unexpected question/material edit',cq)
  oa,na=answers(old),answers(new);ca=[n for n in oa if oa[n]!=na.get(n)]
  assert all((rel,n) in {('国考/2024/行测-副省级.md',12),('省考/江西/2019/行测-法检.md',41)} for n in ca),(rel,'existing answer changed',ca)
  if rel=='省考/江西/2019/行测-法检.md' and 41 in ca:assert '**参考作答**：按本卷现有题面计算为5400元' in new and '不能给出有效单选字母' in new
  assert not (set(image_refs(old))-set(image_refs(new))),(rel,'image removed')
  changed_q.extend((rel,n) for n in cq);changed_a.extend((rel,n) for n in ca);added+=len(set(na)-set(oa))
  reports.append({'path':rel,'question_count':len(oq),'existing_answers':len(oa),'added_answers':len(set(na)-set(oa)),'changed_question_numbers':cq,'changed_existing_answer_numbers':ca})
 assert added==141,added
 result={'baseline':BASE,'baseline_root':str(baseline_root) if baseline_root else None,'baseline_note':'固定main审计快照；PR19未涉及行测，父agent另做整体PR基线验收' if baseline_root else 'Git固定PR19基线','papers_verified':len(reports),'added_answers':added,'question_edits':changed_q,'existing_answer_edits':changed_a,'no_existing_question_ids_removed':True,'no_existing_image_refs_removed':True,'excluded_concurrent_owner_file':'省考/北京/2025/行测-统考.md','papers':reports}
 (R/'reports/FULL-REPAIR-APTITUDE-VERIFICATION-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k!='papers'},ensure_ascii=False))
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--baseline-root',type=Path);ap.add_argument('--git-bin',default='git');a=ap.parse_args();main(a.baseline_root,a.git_bin)
