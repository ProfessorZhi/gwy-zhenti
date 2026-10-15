import json,re,sys,hashlib,uuid,os
from pathlib import Path
from urllib.parse import quote
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
REV='95676de3a494730fdcacd43416fd51d6bed48ab6';sha=lambda t:hashlib.sha256(t.encode()).hexdigest()
ds=json.loads((ROOT/'tools/data/shanghai-additional-a-full-source-packets-20261015.json').read_text(encoding='utf8'));receipts=[]
for d in ds:
 y=d['year'];p=ROOT/d['path'];old=p.read_text(encoding='utf8');op=b.parse(old,d['path']);corrections=[]
 if '恢复凭据: "reports/FULL-REPAIR-SHANGHAI-ADDITIONAL-A-20261015.jsonl"' in old:
  print('Already restored; preserved',d['path']);continue
 before_dir=ROOT/'reports/FULL-REPAIR-SHANGHAI-ADDITIONAL-A-BEFORE-20261015';before_dir.mkdir(exist_ok=True)
 if not (before_dir/(str(y)+'.md')).exists():(before_dir/(str(y)+'.md')).write_bytes(old.encode('utf8'))
 if y==2021:
  m=re.search(r'(?ms)^材料7\s*(.*?)^材料8\s*$',old);assert m,'No existing material7'
  retained=m[1].strip();cross=json.loads((ROOT/'tools/data/shanghai2021a-material7-crosscheck-20261015.json').read_text(encoding='utf8'))
  ratio=SequenceMatcher(None,b.norm(retained),b.norm(cross['material7']),autojunk=False).ratio();assert ratio>.99,ratio
  corrections.append(dict(material=7,original_source_text=d['materials'][6]['text'],restored_text_sha256=sha(retained),basis='已有库正确资料7原文与爱真题同年A全文交叉核对，不能以MOPS误重复的资料6覆盖',cross_url=cross['url'],normalized_similarity=ratio))
  d['materials'][6]['text']=retained
 text='---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in {'考试':'省考','地区':'上海','年份':str(y),'科目':'申论','卷型':'A类','真题性质':'机构整理/考生回忆真题，非官方原件','命题形式':'单独命题','来源':['用户已有完整原始资料'],'来源整卷':'https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(d['source_relative_path'],safe='/'),'来源整卷SHA256':d['source_sha256'],'实有题数':4,'对照题本题量':4,'缺失原题号':[],'给定材料段数':len(d['materials']),'题目分值':[20,20,20,40],'已收录参考答案题号':[1,2,3,4],'缺参考答案题号':[],'题号口径':'完整同年A卷作答要求顺序；从旧源乱序恢复原题号','校验状态':'2026-10-15恢复完整4题、材料及参考正文；不代表官方原件逐字认证','恢复凭据':'reports/FULL-REPAIR-SHANGHAI-ADDITIONAL-A-20261015.jsonl'}.items())+'---\n# '+str(y)+'年上海市公务员考试申论（A类）\n\n'
 url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(d['source_relative_path'],safe='/')
 text+='> 按用户已有完整A卷恢复题序与作文。机构原参考与AI修订分别标明，旧版全文留存凭据，未把解析文字算作文正文。\n\n[原稿固定版本]('+url+')\n\n'
 if d['instructions']:text+='## 考试注意事项\n\n'+d['instructions']+'\n\n'
 for m in d['materials']:text+='## 给定资料 '+str(m['number'])+'\n\n'+m['text']+'\n\n'
 text+='## 作答要求\n\n'
 for n,q in d['questions'].items():
  q=q.replace('语音流程','语言流畅')
  if y==2019 and n=='4':q=q.replace('结合给定材料，“创新驱动与追求卓越”为主题','结合给定材料，以“创新驱动与追求卓越”为主题')
  d['questions'][n]=q;text+='## 第 '+n+' 题\n\n'+q+'\n\n'
 text+='## 答案与解析\n\n';metrics=[]
 for n,q in d['questions'].items():
  a=d['source_answers'][n];kind='owned_source';reason=None
  if y==2018 and n=='4':
   a=a.replace('坚定信念勿动摇传承精神拓事业信念','坚定信念勿动摇 传承精神拓事业\n\n信念').replace('失去信念的人如同行尸走肉一般，既没有了精神支柱，也会失去生命的动力，事业更是无从谈起。','失去信念便失去精神支柱，事业也难以为继。');kind='ai_revision';reason='源正文1011字略超上限，精炼开头、分开标题，论证保留。'
  if y==2019 and n=='4':
   a=a.replace('创新驱动是追求卓越的必由之路“海纳百川','创新驱动是追求卓越的必由之路\n\n“海纳百川')
   start=a.index('走创新驱动的道路，本质就是不断追求卓越。');end=a.index('实施创新驱动，首先要致力于掌握核心高端技术')
   a=a[:start]+'创新驱动与追求卓越相互促进。追求卓越使人不满足于已有成绩，不断寻找更好的方法；创新驱动则通过技术革新提升效率和质量、挖掘新需求、创造新产品，把追求转化为成果。要实现这种转化，既需要敢于突破的人才，也需要支持探索的制度和文化。\n\n'+a[end:]
   a=a.replace('当前，我国在军工制造、高铁、大飞机制造、航天制造等“硬件”制造方面掌握了一些核心技术，具备了相当的竞争力。','我国在高铁、大飞机、航天等领域已有一定技术优势。')
   kind='ai_revision';reason='原参考正文1244字超800—1000要求，精简重复定义及举例，保留核心技术、科研体制与开放合作三层对策。'
  if y==2020 and n=='3':a=a.replace('社会存在决定社会意识，社会意识是社会存在的反映。','社会存在决定社会意识。').replace('团结协助精神','团结协作精神');kind='ai_revision';reason='源正文302字，精炼重复释义并校正明显错词。'
  if y==2020 and n=='4':
   a=a.replace('循群众路线享美好生活天地之大','循群众路线 享美好生活\n\n天地之大')
   a=a.replace('“民为邦本，本固邦宁”，得民心者得天下，失民心者失天下，从周幽王烽火戏诸侯到李世民休养生息政策固本安邦，便向我们印证了这一颠扑不破的真理。','')
   a=a.replace('古人常说：“天将降大任于斯人也，必先苦其心志，劳其筋骨，饿其体肤，空乏其身”，基层工作的艰苦众所周知，但这并不是放弃的理由，吃苦耐劳是中华民族的传统美德，是作为我们评价年轻干部作风品行、发展潜力和能否取得成功的重要标志。','基层工作艰苦，越需要干部保持公仆意识，吃苦在前、真诚服务，在实践中磨炼作风。')
   kind='ai_revision';reason='源正文1125字超过800—1000要求，删去旁逸的古代事例与冗长引语，保留群众立场、公仆作风和调查研究三条论证。'
  if y==2021 and n=='4':
   a=a.replace('于危机中育先机于变局中开新局——依托数字时代开展公平竞争习近平总书记指出，“科学研究既要追求知识和真理，也要服务于经济社会发展和广大人民群众”。可以说，任何科技创新都应以服务社会为出发点，以改善和提升人民生活质量为宗旨。','于变局中开新局\n——以公平竞争护航数字经济\n\n科技创新应服务社会、改善人民生活。')
   a=a.replace('劳动者就业危机、大数据杀熟带来信息泛滥、平台垄断带来不正当竞争','劳动者就业风险、大数据杀熟损害消费者权益、信息泛滥影响平台生态、平台垄断阻碍公平竞争')
   a=a.replace('政府应出台并制定针对性法规，对互联网平台加以监管，追责问责，为数字经济下的广大行业之间能够公平竞争提供有力的政策保障。借助数字经济发展特征，一些互联网平台不断向用户推送垃圾信息的现象越来越多。随着个人信息的泄露、泛娱乐化信息的增多、网络诈骗等案件屡见不鲜。一些专门应用于数字经济时代的法律法规已经被越来越多的人所呼吁。','政府应完善针对性规则，强化平台监管与追责，为公平竞争提供制度保障。针对信息泄露、泛娱乐化内容和网络诈骗等问题，应明确平台责任、加强数据保护、完善投诉处置，使技术应用有章可循。')
   a=a.replace('企业应当把握数字时代发展机遇，迎难而上、顺势而为，革新经营方式，提升自身业务能力和核心竞争力，在不断变化的市场环境中寻求生机。','企业应把握数字机遇，革新经营方式，依靠业务能力和核心竞争力开拓市场。')
   a=a.replace('当下，数字经济发展迅猛，在催生新业态、新模式的同时也带来了新挑战，呈现出新的时代变局。此时，我们需把握住科技创新的重要方向，依托数字经济发展机遇，稳住市场公平大局。','数字经济催生新业态，也带来新挑战。把握科技创新方向，兼顾活力与公平，才能让数字发展成果惠及更多人。')
   a=a.replace('尤其今年在新冠肺炎的大背景下，一些小微企业出现了严重的业绩亏损','疫情冲击下，一些小微企业经营困难')
   a=a.replace('互联网平台经济已成为经济发展新动能','平台经济已成为发展新动能')
   kind='ai_revision';reason='源正文1215字超800—1000要求，压缩重复背景及倡导语，纠正大数据杀熟与信息泛滥之间的不当因果表述。'
  author='原资料未署名；仅作出版页码、标题和段落校勘' if kind=='owned_source' else 'AI辅助修订示范；所据原稿未署名'
  if y==2021 and kind=='owned_source':author='原资料仅标识F，未披露全名或所属机构'
  e=dict(answer=a,attribution_kind=kind,author=author,sources=[dict(title='同题原参考稿（固定版本）',url=url)])
  if reason:e['replace_reason']=reason+' 原稿及原版卷文完整保存在恢复凭据。'
  count=validate_answer(q,e);metrics.append(dict(number=int(n),characters=count,kind=kind,answer_sha256=sha(a)))
  text+='<details>\n<summary>第 '+n+' 题</summary>\n\n'+render_answer(e)+'\n\n</details>\n\n'
 text=text.replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷')
 if y==2021:text+='> 材料校勘：本地原稿资料7误重复资料6，保留现有库正确的技工技能培训资料，并以[同年A卷机构全文](https://www.aipta.com/article/1219.html)核对；原误段与相似度记录见恢复凭据。\n'
 text,layout=format_essay(text,d['path']);nd=b.parse(text,d['path']);assert len(nd['questions'])==4 and len(nd['answers'])==4
 mapped=[]
 for on,oq in op['questions'].items():
  matches=[(nn,SequenceMatcher(None,b.qkey(oq),b.qkey(qq),autojunk=False).ratio()) for nn,qq in nd['questions'].items()];nn,sim=max(matches,key=lambda x:x[1]);assert sim>.9,(y,on,sim);mapped.append(dict(old_number=on,new_number=nn,question_similarity=sim))
 tmp=p.with_name(p.name+'.A-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(text.encode());assert sha(p.read_text(encoding='utf8'))==sha(old);os.replace(tmp,p);assert sha(p.read_text(encoding='utf8'))==sha(text)
 record=dict(path=d['path'],source_path=d['source_path'],source_revision=REV,source_sha256=d['source_sha256'],before_sha256=sha(old),before_text=old,after_sha256=sha(text),materials=len(d['materials']),questions=4,answers=metrics,old_to_real_question_numbers=mapped,material_corrections=corrections,layout=layout)
 rp=ROOT/'reports/FULL-REPAIR-SHANGHAI-ADDITIONAL-A-20261015.jsonl';prior=rp.read_text(encoding='utf8') if rp.exists() else '';rp.write_text(prior+json.dumps(record,ensure_ascii=False)+'\n',encoding='utf8')
 print(d['path'],metrics,mapped)
