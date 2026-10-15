"""Restore the two 2016 Shanghai papers without replacing their fuller materials."""
import hashlib,json,os,re,subprocess,unicodedata,uuid
from pathlib import Path
from urllib.parse import quote
from difflib import SequenceMatcher
import round5_bulk as parser
from full_repair_answers_20261015 import validate_answer,render_answer
ROOT=Path(__file__).resolve().parents[1];M=Path('D:/projects/gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
BASE=M/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【24】上海公务员考试真题pdf版/上海公务员考试真题——申论03-24'
def sha(t):return hashlib.sha256(t if isinstance(t,bytes) else t.encode()).hexdigest()
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKC',t) if c.isalnum())
def pretty(t):
 t=unicodedata.normalize('NFKC',t)
 paragraphs=re.split(r'\n\s*\n',t.strip());out=[]
 for part in paragraphs:
  part=re.sub(r'(?<=\S)\n(?=\S)','',part.strip())
  if out and not re.search(r'[。！？；：…!?;:”“」]$',out[-1]) and not re.match(r'[#<]|材料\d|[一二三四五六七八九十]+[、.]|\d+[、.]',part) and not out[-1].startswith('#') and not re.fullmatch(r'材料\d+[：:]?',out[-1]):out[-1]+=part
  else:out.append(part)
 return '\n\n'.join(out)
def atomic(p,t):
 temp=p.with_name(p.name+'.sh16-'+uuid.uuid4().hex+'.tmp');temp.write_bytes(t.encode());os.replace(temp,p)
ESSAY='''以改革创新提升市场监管效能

食品安全牵动千家万户，电梯运行关系出行平安，市场监管就在群众日常生活之中。材料中的多重检查、监管空白和新业态风险，说明市场活力需要有效规则护航。加强市场监管，应以群众生命健康和公平竞争为重，在理清职责、提升能力、协同共治中推进改革，让权力用在该管的地方，让市场运行更有秩序。

理顺监管体制，是提升效能的基础。食品从生产到销售跨越多个环节，部门各管一段，容易出现重复检查与无人负责并存的局面。浦东探索职能整合，将工商、质监、食药监等领域的检查衔接起来，减少多头上门，却加大了检查力度；深圳则在综合协调与专业分类之间寻找平衡。改革的关键不能停留在机构名称变化上，还要依据业务联系再造流程，明确责任清单、信息通报和案件移送规则，避免旧壁垒变成新机构内部的壁垒。

夯实基层能力，才能把制度要求落实到监管现场。市场主体数量多、类型杂，食品检验、特种设备等领域专业性强，而基层人员存在知识结构不匹配、装备不足和任务繁重等问题。对此，应根据工作量合理配置力量，将资源向一线倾斜，完善培训、专业支持与履职保障。推广清晰可用的操作流程，既有助于降低执法随意性，也能让不同人员依照共同标准开展工作。对协管员、信息员加强指导和激励，使其真正发挥发现问题、及时反映的作用。

坚持依法监管，才能兼顾安全底线与公平秩序。监管不是检查越多越好，更不能在不同主体之间宽严不一。应完善与基层实践相适应的规则，细化执法标准，明确经营者、管理者和维护单位的责任。对于电梯等风险点，日常维护、定期检验和隐患整改要形成闭环，不能等事故发生后才集中整治。对于小作坊、小餐饮等薄弱环节，应在守住安全要求的前提下加强规范指导，以持续治理替代反复突击，让经营者有稳定预期，消费者有可靠保障。

适应新业态，还须拓展监管方式和参与渠道。网络订餐打破了传统经营空间，虚假证照、信息不透明等问题要求监管跟着业务变化走。应运用数据共享、风险监测和线上线下协作，提高问题识别与处置效率，同时落实平台和经营主体责任。公众投诉、行业自律有助于扩大监管视野，应畅通受理反馈，依法查证处理，让线索有人接、隐患有人改、结果有人问。各方各负其责，才能形成安全网络。

监管改革是一项持续工程。以制度整合打通梗阻，以专业能力应对复杂问题，以法治和协作约束权力、保障权益，才能把市场监管的责任落实到每个环节，为经济健康发展和群众安心生活提供坚实支撑。'''
def main():
 oldrows=json.loads((ROOT/'reports/FULL-REPAIR-SHANGHAI-2016-PREIMAGES-20261015.json').read_text(encoding='utf-8'));by={r['path']:r for r in oldrows};mixed=by['省考/上海/2016/申论-统考.md'];receipts=[];maps=[]
 for variant in ['A','B']:
  rel=f'省考/上海/2016/申论-{variant}类.md';old=by[rel];p=ROOT/rel;assert sha(p.read_bytes())==old['before_sha256'],rel;d=old['parsed']
  sp=next(BASE.glob('2016*'+variant+'卷*.md'));raw=sp.read_bytes();source=raw.decode('utf-8');env=dict(os.environ,GIT_CONFIG_GLOBAL='NUL',GIT_CONFIG_NOSYSTEM='1');sr=sp.relative_to(M).as_posix();blob=subprocess.check_output(['git','-c','core.fsmonitor=false','rev-parse',REV+':'+sr],cwd=M,env=env,timeout=120).decode().strip();committed=subprocess.check_output(['git','-c','core.fsmonitor=false','cat-file','blob',blob],cwd=M,env=env,timeout=120);assert committed==raw,(rel,'source working bytes differ from pinned commit');url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(sr,safe='/')
  source_clean=re.sub(r'<!-- page: (\d+) -->\s*(?:\1(?!\d))?','\n\n',source);materials_source=source_clean[source_clean.index('### 资料1'):source_clean.index('## 三、作答要求')];tail=source_clean[source_clean.index('## 三、作答要求'):];stop=re.search(r'(?m)^\s*2016\s*年上海[^\n]*参考答案',tail);assert stop;taskregion=tail[:stop.start()]
  qm=list(re.finditer(r'[（(]([一二三四])[）)]',taskregion));assert len(qm)==4
  source_questions={str(i+1):re.sub(r'\*\*','',taskregion[m.end():qm[i+1].start() if i<3 else len(taskregion)]).strip() for i,m in enumerate(qm)}
  common=re.sub(r'^\s*###\s*给定材料\s*','',d['materials']['1']).strip();assert re.findall(r'(?m)^材料([1-7])[：:]?\s*$',common)==list('1234567')
  questions={};answerblocks={};mapping=[]
  for n,donor in enumerate([3,2,1],1):
   q=d['questions'][str(donor)].strip().replace('\u200b','');cap=200 if variant=='B' and n==1 or variant=='A' and n==3 else 300
   # Keep the existing complete source's wording; private booklet is a documented alternate version.
   questions[n]=q+'（20分）\n\n要求：概括准确，条理清楚，语言精练，字数不超过'+str(cap)+'字。'
   aa=d['answers'][str(donor)];body=re.split('参考答案说明|文章分析|> 来源说明|> 出处',aa)[0].strip();body=pretty(body);count=validate_answer(questions[n],{'answer':body,'attribution_kind':'owned_source','author':'原库未明确署名'})
   answerblocks[n]='**同题来源参考作答（原库保留）**\n\n<!-- full-repair-answer-20261015 -->\n'+body+'\n<!-- /full-repair-answer-20261015 -->\n\n> 来源说明：原库同年同卷已收录参考，按题序回接；仅整理断行、兼容字形，不改作答观点。原作者未明确，不是官方答案，不代表实考分数。完整旧参考及解析存于恢复凭据。'
   mapping.append({'new_number':n,'old_path':rel,'old_number':donor,'old_question':d['questions'][str(donor)],'source_question':source_questions[str(n)],'new_question':questions[n],'reference_characters':count,'original_answer':aa})
  questions[4]=source_questions['4']
  if not re.search(r'40\s*分',questions[4]):questions[4]=questions[4].replace('\n要求：','（40分）\n要求：').replace('\n\n要求：','（40分）\n\n要求：')
  # Source task 4 is complete and its actual 800–1000 constraint is restored.
  assert '800' in questions[4] and '1000' in questions[4]
  donor=2 if variant=='A' else 1;old_answer=mixed['parsed']['answers'][str(donor)];mq=mixed['parsed']['questions'][str(donor)]
  if variant=='A':
   entry={'answer':ESSAY,'attribution_kind':'ai_revision','author':'Codex（AI辅助修订示范）','sources':[{'title':'同卷题本用于题目要求核对；旧原库范文另存凭据','url':url}]};count=validate_answer(questions[4],entry);answerblocks[4]=render_answer(entry)
  else:
   body=re.split('参考答案说明|文章分析|> 来源说明|> 出处',old_answer)[0].strip();body=pretty(body);count=validate_answer(questions[4],{'answer':body,'attribution_kind':'owned_source','author':'原库未明确署名'});answerblocks[4]='**同题来源参考范文（原库保留）**\n\n<!-- full-repair-answer-20261015 -->\n'+body+'\n<!-- /full-repair-answer-20261015 -->\n\n> 来源说明：原库2016统考桶第1题既有完整同题范文，现回接B卷第4题。原作者未明确，不是官方答案，不代表实考分数；仅整理断行和兼容汉字，完整旧稿存于凭据。'
  maps.append({'old_path':mixed['path'],'old_number':donor,'canonical':rel,'canonical_number':4,'old_question':mq,'restored_question':questions[4],'answer_characters':count,'materials_same_exam':'Old full composition material matches corresponding A/B subject; original current mixed packet retained in preimages.'})
  title=f'# 2016年上海市公务员考试申论（{variant}类，完整四题核对版）';out=['---','考试: "省考"','地区: "上海"','年份: "2016"','科目: "申论"',f'卷型: "{variant}类"','命题形式: "单独命题"','真题性质: "公开整理真题，同题来源核对版"','题号口径: "同卷四题题序；旧三小题3/2/1回接，统考桶作文回接第4题"','已收录参考答案题号: [1, 2, 3, 4]','缺参考答案题号: []','恢复凭据: "reports/FULL-REPAIR-SHANGHAI-2016-RESTORATION-20261015.jsonl"','---',title,'',f'> [用户同卷完整题本]({url})已以固定提交实际Git blob核实，用于核对四题顺序与作文800–1000字要求。材料正文保留原库较完整的七段，仅共用一次并整理断行；未用较短整理本覆盖较完整原材料。原文、原参考和版本对照均存恢复凭据。网络整理题本不冒称官方公布原件。','']
  if variant=='A':out += ['> **题面异文：** 用户题本／[新都同题全文](http://edu.newdu.com/204391_4.html)将第1题表述为食品监管问题、第3题上限300字；[另一完整公开题本](https://gwysydw.com/bs/dqgwy/news_92257.html)与原库采用市场监管问题，第3题上限200字。此处保留原库题干，补回完整要求，并对第3题采用较严格200字；172字既有参考满足两种上限。作文主题依据用户题本及新都为“加强市场监管”。这些差异并非官方版本裁定。','']
  out += ['## 给定材料','',pretty(common),'','## 作答要求','']
  for n in range(1,5):out += [f'## 第 {n} 题','',pretty(questions[n]),'']
  out += ['## 答案与解析','']
  for n in range(1,5):out += [f'<a id="r7-reference-{n}"></a>','<details>',f'<summary>第 {n} 题</summary>','',answerblocks[n],'','</details>','']
  new='\n'.join(out);nd=parser.parse(new,rel);assert len(nd['questions'])==len(nd['answers'])==4;assert norm(pretty(common))==norm(common)
  receipt={'path':rel,'status':'prepared','before_sha256':old['before_sha256'],'before_text':old['before_text'],'after_sha256':sha(new),'after_text':new,'source':{'path':sr,'url':url,'revision':REV,'git_blob':blob,'source_sha256':sha(raw),'questions':source_questions,'materials':materials_source},'original_materials_retained':common,'source_material_version_boundary':'Original fuller current materials retained; shorter/OCR-variant private transcription kept separately for comparison.','old_question_mapping':mapping,'composition_mapping':maps[-1],'original_mixed_composition':old_answer,'question_count':4,'reference_count':4}
  # Each complete operation is durably recorded before its MD write, then marked applied.
  receipt_path=ROOT/'reports/FULL-REPAIR-SHANGHAI-2016-RESTORATION-20261015.jsonl'
  with receipt_path.open('a',encoding='utf-8') as f:f.write(json.dumps(receipt,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  atomic(p,new)
  assert sha(p.read_bytes())==receipt['after_sha256']
  with receipt_path.open('a',encoding='utf-8') as f:f.write(json.dumps({'path':rel,'status':'applied','after_sha256':receipt['after_sha256']},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  receipts.append({'path':rel,'four_questions':True,'main_answers':4,'composition_characters':count});print(rel,'applied',receipts[-1],flush=True)
 (ROOT/'reports/FULL-REPAIR-SHANGHAI-2016-MIXED-MAPPING-20261015.json').write_text(json.dumps({'status':'passed','mixed_path':mixed['path'],'maps':maps,'restore_papers':receipts,'recommendation':'root将2016统考两题混卷完整归档；两道作文分别属于B4、A4，不是第三套独立原卷。'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
