import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
rows=json.loads((ROOT/'reports/FULL-REPAIR-DECLARED-LENGTH-A-BEFORE-20261015.json').read_text(encoding='utf8'))
def body(i):
 a=re.split(r'\n\s*>\s*(?:出处|来源说明)|\n\s*\[本题(?:既有)?来源记录\]',rows[i]['answer'],1)[0]
 return re.sub(r'^\*\*来源(?:参考作答|作文范文)\*\*\s*','',a).replace('**','').strip()
def change(i,*pairs):
 a=body(i)
 for x,y in pairs:assert x in a,(i,x);a=a.replace(x,y)
 return a
out={}
out[30]=change(30,
 ('群众参与执法','群众参与监督'),
 ('让公众参与，执法的树苗才能够根深叶茂，蓬勃发展','公众参与能为执法夯实社会基础'),
 ('执法工作应当调动群众参与监督的积极性','执法工作应当调动群众参与监督、协助治理的积极性'),
 ('最重要的法律，既不是刻在大理石上，也不是刻在铜表上，而是铭刻在公民的内心里。',''),
 ('这样就能够减少违法行为的发生，让每个人都能够按照法律办事，提升对于法律的遵从度，营造人人懂法、人人守法的良好氛围。','从而减少违法行为，营造尊法守法的氛围。'),
 ('凝心聚力开创法治时代，同心同德共建美好未来。让我们与民同行，与民同治，与民同享，携手推进社会主义法治化进程，全面提升法治工作科学化水平，守护群众岁月静好，维护社会长治久安，谱写新时代的法治新篇章。','公众参与不等于代替执法，调查处罚仍须由有权机关依法实施。以群众监督、专家支持和普法宣传汇聚合力，才能让严格执法与社会共治相互促进。'))
out[35]='''一、需求规模：辖区老人数量、分布、身体状况和就餐困难，特殊老人送餐需求。

二、场地设施：现有养老服务中心规模、可用场地，厨房、卫生、安全及送餐条件。

三、运营保障：所需工作人员、社工数量，政府购买服务预算、持续运营成本和专业机构资质。

四、服务方案：老人饮食习惯、菜品与口味需求、可接受价格，居民收入、消费水平及周边餐价。

五、资源效益：可整合的公共资源、试点运营经验，专家及居民意见，设立食堂的可行性与效益。'''
out[37]=change(37,('有效构建多维化法律服务体系','构建多维法律服务体系'),('群众调节','群众调解'))
a=body(34)
a=a.replace('深圳市全体公务员：2020 年10 月14 日，深圳经济特区建立40 周年庆祝大会隆重举行，习近平总书记发表重要讲话，强调永葆“闯”的精神、“创”的劲头、“干”的作风，努力续写更多“春天的故事”，努力创造让世界刮目相看的新的更大奇迹！这是对深圳等经济特区精神品质的深刻总结，更是对经济特区在新征程上创造新的历史伟业的殷切期待。对此，我市公务员主管部门向全市公务员发出倡议，深入学习贯彻习近平总书记重要讲话、重要指示精神，勇于担当，积极作为，服务“双区”建设。','深圳市全体公务员：\n\n习近平总书记在深圳经济特区建立40周年庆祝大会上的重要讲话，为深圳新征程指明了方向。为深入贯彻重要讲话、重要指示精神，服务粤港澳大湾区和中国特色社会主义先行示范区建设，我们向全市公务员发出以下倡议：')
ad='获取试卷更新，请关注公众号：gwyeasy（公务员考试挺简单）,一个上岸考生分享经验和答疑的平台。\n\n'
assert ad in a;a=a.replace(ad,'')
a=a.replace('40 年春风化雨，40 年春华秋实。回首深圳40 年非凡历程，敢闯敢试、敢为人先、埋头苦干，始终是深圳等经济特区不变的精神气质，也始终是深圳等经济特区不断创造发展奇迹的重要支撑。','敢闯敢试、敢为人先、埋头苦干，是深圳发展奇迹的重要支撑。')
a=a.replace('深圳市公务员主管部门XXXX 年XX 月XX 日','深圳市公务员主管部门')
a=a.replace('今天，再开新局、再蹚新路，“闯”的精神依然不可或缺、至关重要。','今天，我们应坚持问题导向，在法治轨道上大胆探索，打通服务企业和群众的堵点。')
a=a.replace('“改革开放、创新发展”，这是历史发出的时代召唤，更是千载难逢的历史机遇。','我们应主动学习新知识、运用新技术，把创新落实到政务服务和产业服务中。')
out[34]=a;out[36]=a
out[41]=change(41,('嘉兴“民声一键办”','K市“民声一键办”'),('促使群众反映的问题，得到全面收集反馈、无障碍流转解决。','让群众反映的问题能够全面收集、有序流转。数字平台之外，还要保持电话和基层走访等渠道畅通，照顾不善使用智能设备的人群，避免技术门槛遮蔽真实诉求。'),('在基层治理工作中，应始终坚持以人民为中心','办理结果还要交由群众检验。通过限时销号、督办整改和回访评价，核实问题是否真正解决，防止以转派代替办理、以程序办结代替群众满意。把高频诉求分析与政策完善结合起来，才能办好一件事、带动解决一类事。\n\n在基层治理工作中，应始终坚持以人民为中心'))
# Same original material was independently reviewed in the peer-review task.
donor_path='省考/陕西/2024/申论-B类.md'
dd=b.parse((ROOT/donor_path).read_text(encoding='utf8'),donor_path)
target=rows[46]['materials'];part=target[target.index('傍晚时分的B市'):]
grams=b.shingles(part);coverage=sum(x in b.norm(dd['materials'][5]) for x in grams)/max(1,len(grams))
assert coverage>.98,coverage
entries=json.loads((ROOT/'tools/data/full-repair-essay-b-20261015.json').read_text(encoding='utf8'))
out[46]=next(e['answer'] for e in entries if e['path']==donor_path and e['number']==5)
print('CQ2024 innovation original-answer donor material coverage',coverage)
(ROOT/'tools/data/declared_length_long_a_20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'reports/FULL-REPAIR-LENGTH-SAME-MATERIAL-A-20261015.json').write_text(json.dumps({'target':rows[46]['path'],'target_number':4,'donor':donor_path,'donor_number':5,'material_12gram_coverage':coverage,'basis':'current original target material matches independently reviewed same-exam donor material; target word limit revalidated separately'},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
