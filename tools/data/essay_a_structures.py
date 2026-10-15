import sys,re,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_repair_essay_a_20261015 import ROOT
rp=ROOT/'reports/FULL-REPAIR-ESSAY-A-STRUCTURES-20261015.json'
receipts=json.loads(rp.read_text(encoding='utf8')) if rp.exists() else []
for rel,labels in [('省考/天津/2017/申论-统考__t443.md',['1、请根据','2、根据','3、参阅','4、请结合']),('省考/福建/2018/申论-县级卷.md',['一、根据','二、根据','三、给定']),('省考/广西/2018/申论-A类.md',['一、根据','二、“给定资料3”中','三、假如你是某省','四、“给定资料7”中']),('省考/广西/2025/申论-B类.md',['题目一、','题目二、','题目三、','题目四、']),('省考/广东/2016/申论-广州市考.md',['问题一：']),('省考/广东/2017/申论-广州市考-单考区.md',['问题一：']),('省考/广东/2017/申论-广州市考-双考区.md',['问题一：']),('省考/广东/2018/申论-广州市考-3月24日.md',['问题一：']),('省考/广东/2018/申论-广州市考-3月25日.md',['请以“回乡”为主题'])]:
 p=ROOT/rel;old=p.read_text(encoding='utf8')
 if re.search(r'(?m)^## 第 1 题',old):continue
 new=old
 for n,label in enumerate(labels,1):
  if new.count(label)!=1:raise ValueError((rel,label,new.count(label)))
  new=new.replace(label,'\n\n## 第 '+str(n)+' 题\n\n'+label,1)
 receipts.append({'path':rel,'before_sha256':hashlib.sha256(old.encode()).hexdigest(),'after_sha256':hashlib.sha256(new.encode()).hexdigest(),'operation':'Insert explicit task heading before existing source question label; no source character removed','old_text':old})
 p.write_text(new,encoding='utf8',newline='\n')
if receipts:
 rp.write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('STRUCTURES',len(receipts))
