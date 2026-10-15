"""Prepare evidence-backed, literal material corrections for the root integrator."""
import hashlib,json
from pathlib import Path
from urllib.parse import quote
R=Path(__file__).resolve().parents[2]
M=Path('D:/projects/gwy-material-ops')
rel='省考/黑龙江/2016/申论-C卷：县乡.md'
src='knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【11】黑龙江公务员考试真题pdf版/黑龙江公务员考试真题——申论05-24/2016年黑龙江公务员考试《申论》真题参考答案(县乡).pdf.md'
ops=[
 ('\n材料五：\n','\n材料六：\n'),
 ('\n材料四：\n','\n材料五：\n'),
 ('\n材料三：\n','\n材料四：\n'),
 ('中国乡村社会向来推崇','\n\n材料三：\n\n中国乡村社会向来推崇'),
 ('老王认为老李新改建房屋设施严重多次调解','老王认为老李新改建房屋设施严重影响其住房采光、通风，而老李则认为老王霸占公地盖房，自己没有什么错。为此，两家多次发生争吵，虽然镇村多次调解'),
 ('每个周三他都要到该县白家庄果没啥事','每个周三他都要到该县白家庄村走访一番。村里的调解室，就是他的办公室。每到这一天，调解室总会很热闹。“碰上矛盾纠纷就现场调解了，如果没啥事'),
 ('平时忙于应付一般的乡村事务记者还了解到','平时忙于应付一般的乡村事务工作，很少有纠纷被提交到这里来解决。记者还了解到'),
 ('传统习俗在村民发生F村一位干部记者讲了一个实例','传统习俗在村民发生纠纷时，也能起到一定的润滑作用。F村一位干部记者讲了一个实例'),
 ('的美好家\n','的美好家园。\n'),
]
old=(R/rel).read_text(encoding='utf-8');new=old
out=[]
for a,b in ops:
 count=new.count(a)
 out.append({'old':a,'new':b,'occurrences':count})
 if count==1:new=new.replace(a,b,1)
row={'path':rel,'status':'ready_for_root_apply','before_sha256':hashlib.sha256(old.encode()).hexdigest(),'proposed_after_sha256':hashlib.sha256(new.encode()).hexdigest(),'source_path':src,'source_url':'https://github.com/ProfessorZhi/gwy-material-ops/blob/main/'+quote(src,safe='/'),'source_sha256':hashlib.sha256((M/src).read_bytes()).hexdigest(),'operations':out,'notes':['原PDF编号1—6：原材料3段落被拼入本库材料二，本库后续材料三四五应依次四五六。','为些在原转录中为显然错字，此处以为此规范；其余恢复字句来自用户保存原稿。','原稿本身仍缺“无讼…传统文化”片段与“加盖厂房”前文，不编造、不以本补遗宣称全卷题面完整。']}
(R/'tools/data/essay-b-material-supplements-20261015.json').write_text(json.dumps([row],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print([(o['old'][:22],o['occurrences']) for o in out])
