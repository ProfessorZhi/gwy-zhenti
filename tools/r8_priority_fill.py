#!/usr/bin/env python3
"""Add seven distinct, expressly labelled original study drafts into existing essay MD.
Institutional links are reading comparators, not an attribution of our own prose.
"""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing,operations
from round5_delivery import body_text

ROOT=g.ROOT
RECEIPT='ROUND8-PRIORITY-ESSAY-20261013.jsonl'
DATA=ROOT/'tools/data/r8-priority-reference-drafts.json'
EXPECT={
 '省考/江苏/2026/申论-B类.md':{1:'融合',2:'AI城管',3:'康和路',4:'合则一'},
 '省考/浙江/2025/申论-A类.md':{2:'服务型制造'},
 '省考/浙江/2026/申论-A类.md':{2:'中国电力'},
 '省考/浙江/2026/申论-C类.md':{2:'中国电力'}
}
NOTE='**原创练习参考作答（AI辅助撰写、未经过实考评分）**'
DESC='以下内容根据本卷题面和给定材料重新组织，供练习比对；不冒充机构原文或实际高分考场卷。原页面另提供同题参考作答，可对照立意与要点。'
def validate_source(p,url):
 if not url.startswith('https://') or not any(host in url for host in ('132gk.com/','sjds.net/')):
  raise ValueError('Unapproved comparison URL '+url)
def output(a,url):
 return NOTE+'\n\n'+DESC+'\n\n'+a.strip()+'\n\n[同题机构/网传参考答案对照阅读]('+url+')\n\n'
def make(entry):
 rel=entry['path'];target=ROOT/rel
 if rel not in EXPECT or set(map(int,entry['answers']))!=set(EXPECT[rel]):raise ValueError('Unexpected paper or task')
 if not target.is_file():raise ValueError('Missing target '+rel)
 old=target.read_text(encoding='utf-8');data=b.parse(old,rel)
 validate_source(rel,entry['source_url'])
 adds={}
 for k,ans in entry['answers'].items():
  n=int(k);q=data['questions'].get(n,'')
  if not q or EXPECT[rel][n] not in q:raise ValueError('Question mismatch '+rel+':'+k)
  if not is_missing(data['answers'].get(n,'')):raise ValueError('Already answered '+rel+':'+k)
  minlen=800 if n==4 and '江苏' in rel else 170
  textlen=len(re.sub(r'\s','',ans))
  if textlen<minlen or '\ufffd' in ans:raise ValueError('Draft truncated '+rel+':'+k)
  maxlen=1250 if n==4 and '江苏' in rel else (650 if n==2 and '浙江' in rel else (350 if n==1 else 440))
  if textlen>maxlen:raise ValueError('Draft exceeds target length '+rel+':'+k+' '+str(textlen))
  adds[n]=output(ans,entry['source_url'])
 new=old
 if data['answer_heading']:
  found=set()
  def replace(m):
   n=int(m[2])
   if n not in adds:return m[0]
   found.add(n);return m[1]+'\n\n'+adds[n]+m[4]
  new=g.DETAIL.sub(replace,new)
  if found!=set(adds):raise ValueError('Missing reference block '+rel)
 else:
  # Preserve the old "未收录" statement as a historical source note. The new
  # answer section supplies explicit dated status, without mutating the original.
  blocks=['## 答案与解析',
    '> **2026-10-13 补录说明：** 以下为原创参考练习稿。此前“参考答案尚未取得”指机构全文收录历史状态；请勿将本篇练习稿误认为当时发布的机构版本。']
  for n in data['questions']:
   content=adds[n] if n in adds else '尚无经审核的完整参考作答。'
   blocks.append('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+content+'\n</details>')
  new=old.rstrip()+'\n\n'+'\n\n'.join(blocks)+'\n'
 complete=sorted(n for n in data['questions'] if n in adds or not is_missing(data['answers'].get(n,'')))
 new=g.set_fields(new,{'已收录参考答案题号':complete,
    '缺参考答案题号':sorted(set(data['questions'])-set(complete)),
    '原创练习稿性质':'AI辅助原创示范；未经过阅卷评分；不同于机构发布的参考答案原文',
    '第八轮参考作答凭据':'reports/'+RECEIPT},
    '2026-10-13第八轮：有来源链接的同题原创练习作答；非机构原文与实考高分认证')
 nd=b.parse(new,rel)
 if set(nd['questions'])!=set(data['questions']) or body_text(old)!=body_text(new):
  raise ValueError('Paper text/task ids mutated '+rel)
 for n,a in data['answers'].items():
  if not is_missing(a) and a!=nd['answers'][n]:raise ValueError('Existing reference overwritten '+rel)
 for n in adds:
  if not nd['answers'][n].startswith(NOTE):raise ValueError('New source label missing '+rel)
 r={'path':rel,'before_sha256':g.digest(old),'after_sha256':g.digest(new),
   'body_sha256':g.digest(body_text(old)),
   'kind':'clearly_labelled_original_practice_draft',
   'question_count':len(data['questions']),
   'new_study_answers':[{'number':n,'answer_sha256':g.digest(nd['answers'][n]),
      'original_text_sha256':g.digest(entry['answers'][str(n)]),
      'original_text_chars':len(re.sub(r'\s','',entry['answers'][str(n)])),
      'target_question_sha256':g.digest(data['questions'][n]),
      'comparison_source_url':entry['source_url'],
      'source_nature':'Comparison link only; new text is authored study draft, not reproduced institutional prose'} for n in sorted(adds)],
   'preserved_existing_answers':{str(n):g.digest(v) for n,v in data['answers'].items() if not is_missing(v)},
   'remaining_answer_ids':nd['missing'],'operations':operations(old,new)}
 return target,new,r

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 spec=json.loads(DATA.read_text(encoding='utf-8'))
 if len(spec)!=4:raise ValueError('Unexpected source count')
 ready=[make(e) for e in spec]
 answer_count=sum(len(r['new_study_answers']) for _,_,r in ready)
 if answer_count!=7:raise ValueError('Wrong draft count')
 print('R8_PREVIEW',json.dumps({'papers':len(ready),'distinct_study_answers':answer_count,
   'class':'Clearly labeled original study drafts; not cited as official/real-score essays',
   'question_text_preserved':True,'apply':args.apply},ensure_ascii=False),flush=True)
 if not args.apply:return
 receipt=ROOT/'reports'/RECEIPT
 if receipt.exists():raise ValueError('Already applied')
 for p,new,r in ready:
  if g.digest(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent edit')
 for p,new,r in ready:
  p.write_text(new,encoding='utf-8',newline='\n')
  if g.digest(p.read_bytes())!=r['after_sha256']:raise ValueError('Writeback differs')
 receipt.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in ready),encoding='utf-8')
if __name__=='__main__':main()
