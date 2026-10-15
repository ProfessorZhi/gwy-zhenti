"""Select actual same-question source bodies; revise only where needed."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from full_repair_answers_20261015 import validate_answer,answer_characters
from shanghai2016_restore_20261015 import pretty
PACKETS=json.loads((ROOT/'tools/data/priority-confirmed-mops-source-packets-20261015.json').read_text(encoding='utf-8'))[:10]
OLD=json.loads((ROOT/'reports/FULL-REPAIR-PRIORITY-B-PREIMAGES-20261015.json').read_text(encoding='utf-8'));OLD={r['path']:r for r in OLD}
def clean(t):
 t=re.sub(r'获取试卷更新，请关注公众号[^\n]*','',t)
 t=re.sub(r'(?m)^\s*(?:第\s*\d+\s*页\s*共\s*\d+\s*页|-\s*\d+\s*-)\s*$','',t)
 t=re.sub(r'(?m)^#{1,6}\s*','',t)
 return pretty(t.strip()).translate(str.maketrans({',':'，',':':'：',';':'；','(':'（',')':'）'}))
def between(t,a,b=None):
 assert a in t,a;t=t.split(a,1)[1]
 if b:assert b in t,b;t=t.split(b,1)[0]
 return clean(t)
NEW={}
def put(i,n,answer,kind='owned_source',reason='同年同卷原稿完整正文，未混入解析与其他年份示例'):
 NEW[(i,n)]={'answer':answer,'attribution_kind':kind,'reason':reason}
put(0,4,'''让梦想为创业定向

创业热潮涌动，年轻人带着想法走进市场，有人成功，也有人在资金、经验和经营压力前止步。材料中“为钱创业是肤浅的，应为梦想所驱动”，提醒我们认真思考创业的出发点。梦想不只是对成功的想象，更应是对真实问题的关注、对创造价值的追求。让梦想确定方向，以理性实践和持续创新支撑行动，创业才可能走得稳、走得远。

梦想为创业赋予超越短期收益的价值目标。市场中不缺追逐热点的项目，却始终需要解决真实需求的产品和服务。如果只看到别人融资、盈利，便匆忙照搬，容易忽视自身能力和用户需要，在热潮退去后失去动力。材料中的社会创业家，把帮助特定群体、改善生活作为追求，探索兼顾效率与公平的商业方式。这说明创业的意义不仅是个人财富增加，还在于创造工作机会、提供有用服务、推动社会进步。目标更清晰，才有理由在困难面前坚持。

让梦想落地，需要承认创业规律、做好现实准备。创业成功不是一句口号的自然结果，方案能否执行、资金从何而来、产品卖给谁，都必须具体考虑。大学生在创意比赛中提出设想，还要走进市场检验成本和需求，积累管理经验、人脉与专业知识。对失败概率有清醒认识，并不意味着失去热情，而是把热情转化为准备。根据资源分步推进，及时修正不成熟的环节，避免以冲动代替判断，梦想才能拥有可以抵达的路径。

实现梦想，还要在合作创新中形成竞争能力。比逗咖啡馆等案例表明，创业可以汇聚不同参与者的资源，让消费者、投资者和传播者形成联系。互联网拓宽了寻找伙伴和发现需求的渠道，但合作也需要明确分工、决策机制与股权流转规则。只有在相互信任的基础上建立稳定制度，才能将众人的热情转化为持续经营的力量。同时，应重视原创与知识产权，辨别真创新和简单模仿，通过独特产品和服务赢得认可，而不是依靠短期噱头吸引关注。

坚持梦想与重视经营相互支撑。否定唯利是图，并不意味着忽视收入、成本和现金流。企业只有具备合理盈利能力，才能维持服务、承担责任，继续实现最初愿景。应在长期价值与当期生存之间作好安排，控制盲目扩张、识别风险，以质量和信誉积累客户。政府、高校和社会机构也应提供培训、专业指导与交流平台，帮助创业者理解市场，而不是只营造热闹的创业气氛。理想有保障，责任才有持续兑现的条件。

创业的道路不会一帆风顺，梦想的价值恰在于帮助人们看清为何出发、愿意付出怎样的努力。把个人志趣同社会需要结合，把创新勇气同扎实准备结合，在创造价值中获得发展，才能让创业既成就自我，也为他人带来更好的生活。''','ai_original','源文件第4题后误附政府公信力范文，与本题创业主题不符，明确排除并据同卷材料原创')
t=PACKETS[1]['source_answer_region'];put(1,2,between(t,'## 二、参考答案：','【审题及答题思路】'));put(1,4,between(t,'## 四、参考答案：','【题目精析】').replace('平衡——学好“快与慢”的辩证法知识爆炸','平衡\n——学好“快与慢”的辩证法\n\n知识爆炸'))
t=PACKETS[2]['source_answer_region'];put(2,1,between(t,'1、参考答案：','### 2、参考答案：'));put(2,4,between(t,'4、参考答案：').replace('寻找平衡点共建信用体系伴随着','寻找平衡点 共建信用体系\n\n伴随着'))
t=PACKETS[3]['source_answer_region'];a=between(t,'## 四、参考答案').replace('当平凡人 做伟大事提起','当平凡人 做伟大事\n\n提起');a=a.replace('他们有着普通的姓名、平凡的模样、寻常的家庭，那么为何英雄之名能够为他们所享？那是因为，','').replace('他们的眼中只有群众利益，他们的心里只有国家荣誉。','');put(3,4,a,'ai_revision','压缩重复铺陈，保留同题理想信念、奉献实干和材料案例的完整论证')
t=PACKETS[4]['source_answer_region'];a=between(t,'3、参考答案：','答题演示');a=a.replace('提高创新能力促进创新发展习近平总书记说过：','提高创新能力，促进创新发展\n\n习近平总书记说过：');paragraphs=a.split('\n\n');
# Rework repeated opening and talent discussion, preserving all four policy directions.
start=a.index('习近平总书记说过：');end=a.index('搭平台，政策大力支持。');a=a[:start]+'''创新能力关系发展主动权。材料反映，我国部分行业仍存在人才不足、研发投入偏低、成果转化不畅、知识产权保护薄弱等问题。应把创新摆在核心位置，以平台、人才、投入和制度协同发力，提高创新能力，促进创新发展。

'''+a[end:]
start=a.index('育人才，发挥人才效应。');end=a.index('重投入，提高成果转化。');a=a[:start]+'''育人才，发挥人才效应。针对高精尖人才短缺，应发挥高校和科研机构的培养作用，加强本土人才培育，重视科研队伍建设；同时引进掌握关键技术的海外人才和创新团队，形成优势互补。完善激励与保障，使人才愿意投入长期研究，能把专业能力转化为创新成果。

'''+a[end:];put(4,3,a,'ai_revision','原同题范文超限，压缩重复开头与人才论述，保留平台、人才、投入转化和企业创新完整对策')
t=PACKETS[5]['source_answer_region'];a=between(t,'问题三：参考答案：');start=a.index('共享单车、共享租车');end=a.index('发展分享经济，');a='共享与发展\n\n'+'''共享单车、共享住宿和工业云等新事物，展现了资源协同的力量。共享既能提高资源利用效率，也应让发展成果惠及更多人。坚持发展为了人民、发展依靠人民、发展成果由人民共享，需要推动分享经济创新，完善公共服务，补齐发展短板，拓展互利合作。

'''+a[end:];start=a.index('打造共享合作共同体，');end=a.index('共享是理念，',start);a=a[:start]+'''拓展共享合作，共建“一带一路”。在项目、规划和机制建设中坚持平等协商、互利共赢，开展多领域经贸合作，创造就业和发展机会，协调共同利益与各国利益。共享不应局限于一地、一国，应通过合作把资源优势转化为共同发展的动力。

'''+a[end:];put(5,3,a,'ai_revision','原同题范文超限，重写重复开头和合作段，保留资源、公共服务、扶贫及国际合作完整论点')
t=PACKETS[6]['source_answer_region'];a=between(t,'第三题参考答案').replace('优化营商环境助力企业发展习总书记','优化营商环境 助力企业发展\n\n习总书记').replace('第三贪多依据信用风险分类','第三，要依据信用风险分类').replace('直接关系','关系');put(6,3,a,'ai_revision','同题正文整理，校正明显错词并删除页眉广告；对策与全部材料相符，未混入其他题例文')
t=PACKETS[7]['source_answer_region'];a=between(t,'## 三、参考答案（F）','### 参考答案（H）').replace('提高现代化治理水平绘就广东发展新蓝图几千年前','提高现代化治理水平 绘就广东发展新蓝图\n\n几千年前');a=re.sub('几千年前，先人就秉持“周虽旧邦，其命维新”的精神，开启了缔造华夏文明的伟大实践。','',a);put(7,3,a,'ai_revision','原同题F版稍超800–1000区间，去除重复历史铺陈，保留治理、人才、市场与区域合作论证')
t=PACKETS[8]['source_answer_region'];a=between(t,'【参考例文】').replace('践行新发展理念实现高质量发展','践行新发展理念 实现高质量发展',1);start=a.index('随着全球价值链分工的不断深化');end=a.index('加强科学技术研发，',start);a=a[:start]+'''广东制造业基础雄厚，但在新工业革命和疫情冲击下仍面临产业链风险。应加强产业规划，推进数字化、智能化改造，培育关键环节配套能力，提高附加值，推动传统产业升级与新兴产业成长。以稳定、高效、富有韧性的产业体系，夯实高质量发展的经济基础。

'''+a[end:];put(8,3,a,'ai_revision','原同题范文超限，压缩产业链重复分析，保留双区协同、产业升级、科研转化与数字政府四个方向')
put(8,2,'''“密码”指以制度、平台、人才和投入协同推进科技创新，促进质量、效率与动力变革。
一、创新体制。建设G城实验室，探索事业单位市场化运行，统筹财政支持与自身产出。
二、改造产业。运用工业互联网和机器换人，减少库存与故障，提高生产效率。
三、建强平台。汇集科研资源、推进产学研结合，形成原创成果与全链条研究模式。
四、加大投入。增加研发支出，以后补助、税收优惠等支持企业研发机构和高新企业。
五、集聚人才。完善人才优惠政策，增强吸引力、激发创新活力。
六、攻关技术。依托国家实验室集中突破关键技术，抢占发展制高点。''','ai_revision','原稿同题七条要点篇幅偏长，合并投入与企业研发支持，完整保留关键机制')
t=PACKETS[9]['source_answer_region'];a=between(t,'【参考例文】').replace('推进区域协同发展  构建世界级城市群2017','推进区域协同发展 构建世界级城市群\n\n2017',1);start=a.index('打造世界级城市群，首先');end=a.index('深入推进城市间基础设施',start);a=a[:start]+'''打造世界级城市群，需要加强顶层设计。国家应明确区域功能定位和目标，将区域发展融入国家大局，构建政策体系；地方做好政策衔接，细化落实责任，为城市协同提供持续制度支持。

'''+a[end:];start=a.index('加强城市间内部合作，');end=a.index('打造国际一流的城市群，',start);a=a[:start]+'''深化内部合作，促进区域融合。建设金融、人才、科研等合作平台，立足各地优势推动资源共享，把产业合作延伸至学习、工作和生活。通过机制创新减少合作障碍，让发展成果惠及三地居民，形成同频共振、共同受益的动力。

'''+a[end:];put(9,3,a,'ai_revision','原同题范文超限，压缩顶层设计及合作平台段，保留实效总结、软硬联通、文化合作与绿色发展')

NEW[(3,4)]['answer']=re.sub(r'2019\s*年末.*?正当人们被无奈、焦灼与惶恐的情绪围剿时，','新冠肺炎疫情发生后，',NEW[(3,4)]['answer'],flags=re.S)
a=NEW[(8,3)]['answer'];start=a.index('改革开放四十年来');end=a.index('全力推进“双区”建设',start);NEW[(8,3)]['answer']=a[:start].rstrip()+'''\n\n改革开放以来，广东敢闯敢试，取得显著成就，也面临产业升级与区域协调的新挑战。站在新起点，应践行新发展理念，统筹“双区”建设、现代产业、科技创新和数字政府，以制度创新与实干作为推动高质量发展。\n\n'''+a[end:]

# Precisely reduce five previously readable short references that exceed the newly restored real limits.
for i,n,old_number,replacements in [
 (4,1,2,[('1.人才匮乏。人才缺口大；人才结构性失衡，缺乏高精尖人才。','1.人才短缺且结构失衡，缺乏高精尖人才。')]),
 (4,2,1,[('5.众创空间延伸到三四线城市，推动三四线城市创业，营造一种全社会创新创业氛围。','5.延伸至三四线城市，推动创业，营造全社会创新创业氛围。')]),
 (5,1,2,[('分享经济能整合资源，实现供需快速匹配，优化资源配置；使人摆脱对物的依赖，构建有人情味、实现共享发展的社会经济生态系统。','分享经济整合资源，实现供需匹配，优化资源配置，构建共享发展的社会经济生态系统。')]),
 (8,1,1,[('广东搭建政务平台，实现高频服务事项网上办理：','广东以政务平台推动高频事项网办：')]),
 (9,2,1,[('5.文化产业蓬勃发展。湾区相关产业已成为支柱产业，文化类上市公司数量多，占上市公司比例高，带动经济发展，扩大就业；文化产业交易会推动项目合作。','5.文化产业发达。相关产业成为支柱，文化上市公司多，带动增长与就业，文化产业交易会促进项目合作。')])]:
 body=OLD[PACKETS[i]['target_path']]['parsed']['answers'][str(old_number)];m=re.search(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',body,re.S);body=m[1] if m else re.split('参考答案说明|文章分析|> 来源说明|> 出处',body)[0].strip();body=clean(body)
 for old,new in replacements:assert old in body,(i,n,old);body=body.replace(old,new)
 put(i,n,body,'ai_revision','原可读参考在补回实际题面后发现少量超限；依据材料合并冗余表达，保留要点')

def main():
 rows=[]
 for (i,n),d in NEW.items():
  p=PACKETS[i];q=clean(next(q['text'] for q in p['questions'] if q['number']==n));entry={**d,'path':p['target_path'],'number':n,'question':q,'author':'Codex（AI辅助修订／原创）' if d['attribution_kind'].startswith('ai') else '原稿未单列答文作者；整理者以源文件为准','sources':[{'title':'用户资料库同年同卷原稿','url':p['source_url']}]}
  entry['characters']=validate_answer(q,entry);rows.append(entry)
 (ROOT/'tools/data/priority-b-restoration-answers-20261015.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print([(r['path'],r['number'],r['characters'],r['attribution_kind']) for r in rows])
if __name__=='__main__':main()
