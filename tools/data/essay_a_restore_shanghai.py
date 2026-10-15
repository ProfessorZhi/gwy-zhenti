import sys,json,hashlib,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_repair_essay_a_20261015 import ROOT,OUT
from full_repair_answers_20261015 import apply_entries
rel='省考/上海/2017/申论-行政执法卷.md';p=ROOT/rel;old=p.read_text(encoding='utf8');new=old
source='https://www.kangaroo.top/question_bank/essay_papers/shanghai/shanghai_2017_shenlun_xingzhengzhifa_zhifa'
pairs=[
('请概括给定资料给定资料-给定资料的主要内容。','请概括给定资料2-8的主要内容。'),
('除了不据上海市消保委负责人介绍','除了不按规则停放之外，自行车二维码被涂改、车座损坏、车身贴满小广告、擅自上锁成为私人专用等等，都很常见。据上海市消保委负责人介绍'),
('城市规划中而面对规范停车','城市规划中还缺大约60万个自行车的停车位。这正是各大城市遭遇共享单车“围城”压力的根源。而面对规范停车'),
('这一法案还对地方德国联邦汽车共享协会会长认为','这一法案还对地方政府提出对共享汽车供应商提供停车费优惠，甚至免去费用的倡议。德国联邦汽车共享协会会长认为'),
('洗鞋机等18台滚这里的“共享洗衣机”','洗鞋机等18台滚筒烘洗设备两两叠放，启用首个小时内便台台“爆满”。这里的“共享洗衣机”'),
('甚至还有专门的耳在卫生保障方面','甚至还有专门的耳塞。在休息结束后，用户需扫码结束计费，并将一次性物品投入回收桶内。在卫生保障方面'),
('助力创新模式的\n','助力创新模式的健康发展。\n')]
operations=[]
for before,after in pairs:
 if before in new:
  if new.count(before)!=1:raise ValueError('Ambiguous restoration '+before)
  new=new.replace(before,after);operations.append({'before':before,'after':after,'source':source if '助力创新模式' not in before else 'http://auto.people.com.cn/n1/2017/0609/c1005-29328424.html'})
if operations:
 note='> 题面补全记录（2026-10-15）：据[公开同题材料与题目]('+source+')恢复第1题“资料2-8”范围及材料2、4、5、7、8的拼接缺文；材料9末句“健康发展”据[2017年人民网同段报道](http://auto.people.com.cn/n1/2017/0609/c1005-29328424.html)校复。来源为公开整理／报道，非考试机关原卷认证。\n\n'
 new=new.replace('材料一：',note+'材料一：',1)
 record={'path':rel,'before_sha256':hashlib.sha256(old.encode()).hexdigest(),'after_sha256':hashlib.sha256(new.encode()).hexdigest(),'operations':operations,'old_text':old,'source_method':'TinyFish search and fetch_content; public visible content only'}
 (ROOT/'reports/FULL-REPAIR-ESSAY-A-SHANGHAI-RESTORE-20261015.json').write_text(json.dumps([record],ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 p.write_text(new,encoding='utf8',newline='\n')
rows=json.loads(OUT.read_text(encoding='utf8'));e=next(x for x in rows if x['path']==rel and x['number']==1)
e['question']='问题一：请概括给定资料2-8的主要内容。（25分）\n\n要求：语言精练，层次要点清楚。字数不超过200字。'
e['answer']='''共享单车便利短途出行，但存在成本高、用户违规损坏、过量投放等问题，各地加强总量与精细化管理，并探索公众参与、智能监管。共享汽车可节约资源，德国以两种模式和立法支持发展，国内受网点、停车位不足制约。共享洗衣机借助互联网拓展服务，但卫生和运营成本仍受关注。共享床铺便利午休，却因消防、经营许可及安全隐患需要严格规范。新业态应协调创新发展与公共安全、空间秩序。'''
e['replace_reason']='原题资料范围由残缺文字核复为2-8，依该范围重写概括，不将资料1和9政策背景混入主答'
e['sources']=[{'title':'2017上海行政执法同题题面与材料核对','url':source,'author':'袋鼠知识（页面未署名）'}]
result,receipts=apply_entries(ROOT,[e],write=True)
if result['status']!='passed':raise ValueError(result)
OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
rp=ROOT/'reports/FULL-REPAIR-ESSAY-A-20261015.jsonl'
rp.write_text(rp.read_text(encoding='utf8')+''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in receipts),encoding='utf8')
print(json.dumps({'restorations':len(operations),'answer':result},ensure_ascii=False))
