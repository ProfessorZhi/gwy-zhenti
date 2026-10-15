"""Remove proven publisher ads/page digits, preserving exact old file in receipt."""
import json,sys,re,hashlib,os,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_layout_20261015 import format_essay
sha=lambda t:hashlib.sha256(t.encode('utf8')).hexdigest()
paths=['省考/深圳/2016/申论-A类.md','省考/深圳/2019/申论-一卷.md','省考/深圳/2019/申论-二卷.md','省考/深圳/2023/申论-一卷.md','省考/深圳/2023/申论-二卷.md','省考/吉林/2019/申论-甲级.md']
ad='获取试卷更新，请关注公众号：gwyeasy（公务员考试挺简单）,一个上岸考生分享经验和答疑的平台。'
receipts=[]
for rel in paths:
 p=ROOT/rel;old=p.read_text(encoding='utf8');before=b.parse(old,rel);new=old;changes=[]
 if ad in new:changes.append({'kind':'proven_publisher_ad','count':new.count(ad),'removed':ad});new=new.replace(ad,'')
 for x,y,kind in [
  ('高等\n\n- 5 -\n\n院校','高等院校','join_word_across_known_page_break'),
  ('深圳，大步迈向“国际化”36 年前','深圳，大步迈向“国际化”\n\n36年前','separate_essay_title'),
  ('深圳高质量的发展需要新发展理念保驾护航习总书记','深圳高质量的发展需要新发展理念保驾护航\n\n习近平总书记','separate_essay_title_and_formal_name'),
  ('谱写中国式现代化的深圳新篇章习近平总书记','谱写中国式现代化的深圳新篇章\n\n习近平总书记','separate_essay_title'),
  ('\n7加强生态治理','\n加强生态治理','remove_known_page_digit')]:
  if x in new:changes.append({'kind':kind,'before':x,'after':y,'count':new.count(x)});new=new.replace(x,y)
 if new==old:continue
 new=new.rstrip()+'\n\n<!-- source-noise-a-20261015 -->\n> 来源排版校勘：删除出版推广文字及混入正文的独立页码，恢复被其隔断的词句，分开作文标题与首段；完整旧文与操作记录见 reports/FULL-REPAIR-SOURCE-NOISE-A-20261015.jsonl。此校勘不改变原题或将参考版本认作实考高分卷。\n'
 new,layout=format_essay(new,rel);after=b.parse(new,rel)
 assert {n:b.qkey(q) for n,q in before['questions'].items()}=={n:b.qkey(q) for n,q in after['questions'].items()},rel
 temp=p.with_name(p.name+'.noise-'+uuid.uuid4().hex+'.tmp');temp.write_bytes(new.encode('utf8'))
 if sha(p.read_text(encoding='utf8'))!=sha(old):raise RuntimeError('Concurrent change '+rel)
 os.replace(temp,p);assert sha(p.read_text(encoding='utf8'))==sha(new)
 receipts.append(dict(path=rel,before_sha256=sha(old),after_sha256=sha(new),before_text=old,operations=changes,layout=layout))
 print(rel,len(changes))
rp=ROOT/'reports/FULL-REPAIR-SOURCE-NOISE-A-20261015.jsonl'
if receipts:
 previous=rp.read_text(encoding='utf8') if rp.exists() else ''
 rp.write_text(previous+''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in receipts),encoding='utf8')
print('FILES',len(receipts))
