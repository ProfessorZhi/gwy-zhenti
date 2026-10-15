import json,re,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
from priority_b_fullpaper_restore_20261015 import mainbody
from shanghai2016_restore_20261015 import pretty
from full_repair_answers_20261015 import validate_answer
import round5_bulk as b
p=R/'tools/data/last4-full-source-packets-a-20261015.json';D=json.loads(p.read_text(encoding='utf8'))
revisions={
('市级卷',1):'''仙路陷入危机：依赖老产品，产品可替代性强，市场饱和；沿用代工思维，缺少技术创新，所谓新品只是结构微调，未找到新增长点，品牌老化。

国欣实现蝶变：一、深耕细分市场，立足新材料，自主创新，改进工艺，实现进口替代。二、调研客户需求，从牙刷丝扩展到油漆刷丝，开拓新市场。三、把握机遇、审慎决策，从部件升级为整套刷具生产。四、父女接力，结合专业积累与国际视野，拓展国际订单。五、谋划平台整合产业链资源，以匠心打造优质产品。''',
('区县卷',1):'''高大妈：喜在村容整洁、煤改电改善取暖，子女返乡尽孝，村干部关心帮衬，并有公益电影；盼建托老所，方便老人吃饭、照料、交流；发展乡村旅游等产业，让子女有收入；改善购物和公交出行条件。

老姚：喜在村庄富裕、生活水平提高，文化纪念馆保存乡村共同记忆，老仓库改文化礼堂即将启用；盼发挥乡贤议事会作用，用民俗活动和桑蚕等产业有形展示乡村文化，让游客亲身参与，延续农耕与蚕桑文化的根脉。''',
('区县卷',2):'''一、山地救援难。山势险、警情多，缺基站，定位和无人机难发挥作用，搜救风险高。民警熟悉地形植被，询问游客行程判断位置，预先标图规划路线，互助救援，指导被困者自救。

二、旅店管理难。场所多、警力少，业主情况复杂，个别不配合。民警转变服务理念，办证、解纷中熟悉业主；分片建34个微信群，掌握信息、精准管理，真诚沟通解决实际困难。

三、节假日警情密集、突发性强。民警优化值守，将警力下沉岗亭街面，快速出警；发动客栈群提供线索，协同寻人，主动回应游客诉求。''',
('县级卷',1):'''一、示范引领。设省政府质量奖，表彰标杆、推广经验，向全产业链传播质量文化与品牌理念。二、制定标准。联合建设供应链平台，完善全链条技术、管理、服务标准，打造区域品牌。三、加强公共服务。建设商标品牌一站式平台，开展专题培训，依托专业组织提供人才培养、品牌培育和战略服务。四、扩大影响。举办高端品牌会议、品牌日等活动，宣传广东制造，推动企业转向品牌竞争。''',
('县级卷',2):'''一、年轻企业家引领转型。发挥企业家精神、国际视野和趋势判断优势，突破核心技术、拓展海外市场；推进数字化管理，建设年轻专业团队，提升经营效益。

二、技能人才夯实产业基础。研发工装设备，以榜样带动青年技能报国，壮大高素质产业工人队伍，支撑完备产业链供应链和工业体系。

三、科研人才增强创新能力。依托校企培养基地、创新实验室解决技术难题，推动专利研发与成果应用；海归团队带来前沿技术和国际专利。

四、专业服务人才优化经营。提供法律、管理咨询、知识产权和设计服务，规范合同及收款流程，降低风险，助力企业健康发展。'''}
eco='''这句话指法院以调解结合持续执行监管，兼顾权利救济、公共生态利益和长期修复效果，避免一罚了之。

一、明确修复责任。由被告支付500万元保底修复款，并设不足部分继续支付的兜底条款，为持续修复提供资金保障。

二、创新执行机制。指定有保护职责和实施能力的林场为执行代管人，列明权责、报告进度；设专项账户，按程序支付资金，使责任、资金和实施衔接。

三、强化全过程监督。组织原告和第三方专家实地检查，接受社会监督；严格施工质量，持续浇水、施肥、补植，经过多年抚育和专家验收，保障修复成效。

因此，生态司法应统筹调解、执行与长期管护，把裁判责任转化为可持续的生态改善。'''
for d in D:
 old=b.parse((R/d['path']).read_text(encoding='utf8'),d['path']);variant=Path(d['path']).stem.replace('申论-','');answers={}
 for m in d['mapping']:
  n=m['new_number'];a=pretty(mainbody(old['answers'][m['old_number']]))
  if (variant,n) in revisions:a=revisions[(variant,n)];kind='ai_revision'
  else:kind='preserved_existing'
  answers[str(n)]=dict(answer=a,kind=kind,reason='按已恢复真实字数上限及题意修订，分别概括对象或压缩冗余；旧稿全文保存在写前凭据。' if kind=='ai_revision' else '保留原库同题正文与署名性质，按真实题序回接。')
 if '行政执法' in d['path']:answers['2']=dict(answer=eco,kind='ai_original',reason='旧卷完全缺失该任务与参考；依据完整同卷资料2独立编写，不冒称原机构作答。')
 t=re.sub(r'<!-- page:\s*\d+\s*-->','\n',d['source_full_text'])
 if '天津' in d['path']:
  a=t[t.rfind('四、参考答案（F）')+len('四、参考答案（F）'):].strip()
  if '市级卷' in d['path']:a=a.replace('赶考中国共产党','赶考\n\n中国共产党')
  elif '区县卷' in d['path']:
   a=a.replace('伟大的梦事者谋定而动行且坚毅','伟大的梦').replace('想与事业','梦想与事业');a='谋定而动，实干笃行，戒骄戒躁\n\n'+a
  else:a=a.replace('推动法治文化创新发展回溯历史','推动法治文化创新发展\n\n回溯历史')
  n=4
 else:a='推动制造业高质量发展，挺起现代化建设脊梁\n\n'+t[t.rfind('问题三推动'):].split('改革开放以来，',1)[1];a=a.replace('脊梁\n\n','脊梁\n\n改革开放以来，',1);n=3
 a=pretty(a)
 a=re.sub(r'(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])','',a)
 for x,y in {'岀':'出','莫定':'奠定','傕生':'催生','思維':'思维','動':'动','掲':'揭','増':'增','揺':'摇','釆':'采','〃':'”'}.items():a=a.replace(x,y)
 a=a.replace('伟大的梦梦想','伟大的梦想').replace('維护','维护')
 if '市级卷' in d['path']:a=a.replace('赶考中国共产党','赶考\n\n中国共产党',1)
 elif '区县卷' in d['path']:a=a.replace('戒骄戒躁《管子','戒骄戒躁\n\n《管子',1)
 elif '行政执法' in d['path']:
  a=a.replace('推动法治文化创新发展回溯历史','推动法治文化创新发展\n\n回溯历史',1)
  begin=a.index('创新发展法治文化需要推陈出新');end=a.index('创新发展法治文化除了丰富法治文化内容之外')
  a=a[:begin]+'''创新发展法治文化，要植根本土、丰富内容。F省挖掘红色法治史料，融入客家、闽学与乡贤文化，让抽象规则具有可感知的历史脉络和地方表达。继承应取精华、去糟粕，以现代法治精神阐释传统资源，让传统文化服务平等、公正、权利保障等现实需要。

'''+a[end:]
 else:a=a.replace('挺起现代化建设脊梁改革开放以来','挺起现代化建设脊梁\n\n改革开放以来',1)
 answers[str(n)]=dict(answer=a,kind='ai_revision',reason='依据用户已有同题参考稿回接完整作文，校正OCR断字、标题混排和明显错字；法治文化文按题目约1000字压缩重复，阐明传统资源须以现代法治精神转化。本次修订不再冒作原作者原文，原稿固定Git版本与全文可核。')
 d['reviewed_answers']=answers
 for q in d['questions']:
  a=answers[str(q['number'])]
  try:count=validate_answer(q['text'],dict(answer=a['answer'],attribution_kind='ai_revision' if a['kind']=='preserved_existing' else a['kind'],author='AI辅助修订示范',sources=[]));print(d['path'],q['number'],count,a['kind'])
  except Exception as e:print('FAIL',d['path'],q['number'],str(e))
p.write_text(json.dumps(D,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
