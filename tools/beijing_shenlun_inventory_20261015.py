"""Evidence-backed reconstruction of Beijing's 2020–2021 real exam variants."""
import hashlib,html,json,re,unicodedata
from urllib.parse import quote
from pathlib import Path
from difflib import SequenceMatcher
import round5_bulk as b
R=Path(__file__).resolve().parents[1]
M=Path('D:/projects/gwy-material-ops')
SOURCE_BASE=M/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【02】北京公务员考试真题pdf版/北京申论09-23'
REVISION='95676de3a494730fdcacd43416fd51d6bed48ab6'
SPECS=[
 (2020,'区级','2020年北京公务员考试申论真题及答案（区级及以上）.pdf.md',[(2,'区级'),(3,'统考'),(1,'区级'),(1,'统考')]),
 (2020,'乡镇卷','2020年北京公务员考试申论真题及答案(乡镇).pdf.md',[(2,'乡镇卷'),(4,'统考'),(1,'乡镇卷'),(2,'统考')]),
 (2021,'区级','2021年北京公务员考试申论真题及答案（区级试卷）.pdf.md',[(2,'区级'),(3,'统考'),(1,'区级'),(1,'统考')]),
 (2021,'乡镇卷','2021年北京公务员考试申论真题及答案（乡镇试卷）.pdf.md',[(2,'乡镇卷'),(4,'统考'),(1,'乡镇卷'),(2,'统考')]),
]
def sha(t):return hashlib.sha256(t.encode()).hexdigest()
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKC',html.unescape(t)) if c.isalnum())
def clean_source(t):
 t=re.sub(r'<!-- page: \d+ -->','',t)
 t=re.sub(r'(?m)^\s*第\s*\d+\s*页\s*共\s*\d+\s*页\s*$','',t)
 t=re.sub(r'(?m)^\s*\d+\s*$','',t)
 return t
def source_parts(path):
 raw=path.read_text(encoding='utf-8');t=clean_source(raw)
 mark=re.search('作答要求',t);assert mark
 body_start=re.search(r'(?:材料|资料)\s*[一1](?!\d)',t)
 assert body_start and body_start.start()<mark.start()
 materials=t[body_start.start():mark.start()]
 materials=re.sub(r'\n\s*#{0,3}\s*[二三][、.．]?\s*$','',materials).strip()
 after=t[mark.end():]
 answer_start=re.search(r'(?:#{1,6}\s*)?参考答案',after)
 assert answer_start
 qpart=after[:answer_start.start()]
 if re.search('问题一',qpart):ms=list(re.finditer(r'问题([一二三四])[：:]?\s*',qpart))
 else:ms=list(re.finditer(r'[（(]([一二三四])[）)]',qpart))
 assert [m[1] for m in ms]==list('一二三四'),[(m[0],m.start()) for m in ms]
 questions={i+1:qpart[m.end():ms[i+1].start() if i+1<len(ms) else len(qpart)].strip() for i,m in enumerate(ms)}
 # Remove PDF formatting marks only, preserving all task words, scores and limits.
 questions={n:re.sub(r'\*\*','',q).strip() for n,q in questions.items()}
 return raw,materials,questions
def make_packet():
 result=[]
 for year,variant,name,mapping in SPECS:
  sp=SOURCE_BASE/name;raw,mats,qs=source_parts(sp);rel=f'省考/北京/{year}/申论-{variant}.md';old=(R/rel).read_text(encoding='utf-8');entries=[]
  for n,(old_n,donor_variant) in enumerate(mapping,1):
   dr=f'省考/北京/{year}/申论-{donor_variant}.md';dt=(R/dr).read_text(encoding='utf-8');d=b.parse(dt,dr);oq=d['questions'][old_n]
   # Phrase comparison ignores only material numbering/formatting, never adds tasks.
   qsim=SequenceMatcher(None,b.qkey(qs[n]),b.qkey(oq),autojunk=False).ratio()
   sn=norm(mats);dn=norm(d['materials'][old_n]);grams={sn[i:i+14] for i in range(0,len(sn)-14,7)};coverage=sum(g in dn for g in grams)/max(1,len(grams))
   entries.append({'number':n,'question':qs[n],'donor_path':dr,'donor_number':old_n,'donor_question':oq,'question_similarity':round(qsim,5),'source_material_shingle_coverage_in_donor':round(coverage,5),'donor_answer':d['answers'][old_n],'donor_sha256':sha(dt),'donor_question_sha256':sha(oq)})
  result.append({'path':rel,'year':year,'variant':variant,'source_path':sp.relative_to(M).as_posix(),'source_revision':REVISION,'source_sha256':sha(raw),'source_text':raw,'materials':mats,'questions':qs,'mapping':entries,'before_sha256':sha(old),'before_text':old})
 path=R/'tools/data/beijing-shenlun-reconstruction-packets-20261015.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps([{'path':r['path'],'material_characters':len(r['materials']),'questions':[{'n':e['number'],'question':e['question'],'donor':e['donor_path']+':'+str(e['donor_number']),'qsim':e['question_similarity'],'materials_overlap':e['source_material_shingle_coverage_in_donor']} for e in r['mapping']]} for r in result],ensure_ascii=False,indent=2))
def readable(t):
 t=unicodedata.normalize('NFKC',html.unescape(t)).replace('⺠','民').replace('⻓','长').replace('⻋','车').replace('⻝','食').replace('⻛','风').replace('⻔','门').replace('⻅','见').replace('⻄','西').replace('⻆','角').replace('⻘','青').replace('⻥','鱼')
 # PDF line wrapping is presentational; existing blank paragraphs remain distinct.
 t=re.sub(r'(?<=\S)\n(?=\S)','',t)
 t=re.sub(r'(?m)^\s*(?:材料|资料)([一二三四五六七八九十]+|\d+)\s*',lambda m:'### 材料'+m[1]+'\n\n',t)
 t=re.sub(r'\n{3,}','\n\n',t)
 return t.strip()

def reconstruct():
 packets=json.loads((R/'tools/data/beijing-shenlun-reconstruction-packets-20261015.json').read_text(encoding='utf-8'))
 answers=json.loads((R/'tools/data/beijing-shenlun-reconstruction-answers-20261015.json').read_text(encoding='utf-8'))
 indexed={(x['path'],x['number']):x for x in answers};receipts=[]
 for p in packets:
  path=R/p['path'];old=path.read_text(encoding='utf-8')
  assert all(e['question_similarity']==1 for e in p['mapping'])
  url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REVISION+'/'+quote(p['source_path'],safe='/')
  out=['---','考试: "省考"','地区: "北京"',f'年份: "{p["year"]}"','科目: "申论"',f'卷型: "{p["variant"]}"','真题性质: "公开整理真题；用户题本核对版"','命题形式: "单独命题"','题号口径: "按完整同年同卷题本顺序"','已收录参考答案题号: [1, 2, 3, 4]','缺参考答案题号: []','复原凭据: "reports/FULL-REPAIR-BEIJING-ESSAY-RECONSTRUCTION-20261015.json"','---',f'# {p["year"]}年北京市公务员考试申论（{p["variant"]}）','',
  '> 本卷按同年同卷完整题本恢复材料、四道题的原卷顺序、分值和字数要求。原库拆散的题目与参考版本逐题映射，原文件全文及哈希保存在复原凭据；不将原“统考”混卷重复计为独立试卷。','',
  f'> 材料与题目来源：[用户资料库中的同卷题本]({url})，固定版本 `{REVISION}`，原文件作者／编制机构未明确。PDF转录中的分页、断行与兼容汉字已规范；画线样式未完整保留，涉及句应结合材料上下文阅读。','',
  '## 给定材料','',readable(p['materials']),'','## 作答要求','']
  for n in range(1,5):out += [f'## 第 {n} 题','',readable(p['questions'][str(n)]),'']
  out += ['## 答案与解析','', '> 主作答为AI辅助原创示范，依据本卷材料与要求编写；不是官方答案，未经实考评分。作者：Codex。原库同题参考版本与解析完整保留在复原凭据的映射记录中，供追溯对照。','']
  for n in range(1,5):
   a=indexed[(p['path'],n)]
   out += [f'<a id="r7-reference-{n}"></a>','<details>',f'<summary>第 {n} 题</summary>','','**AI辅助原创示范作答**','','<!-- full-repair-answer-20261015 -->',a['answer'],'<!-- /full-repair-answer-20261015 -->','','> 来源说明：AI辅助原创示范，依据本卷给定材料与作答要求独立编写；不是官方答案，未经实考评分。作者：Codex。','','</details>','']
  new='\n'.join(out);parsed=b.parse(new,p['path']);assert set(parsed['questions'])=={1,2,3,4};assert set(parsed['answers'])=={1,2,3,4}
  assert sha(old) in [p['before_sha256'],sha(new)],p['path']
  assert norm(p['materials'].replace('资料','材料'))==norm(readable(p['materials']).replace('资料','材料').replace('### ','')),p['path']
  path.write_text(new,encoding='utf-8')
  receipts.append({**p,'after_sha256':sha(new),'after_text':new,'new_answers':[indexed[(p['path'],n)] for n in range(1,5)],'verification':{'question_identity':'all 4 normalized qkeys equal mapped existing tasks','materials':'complete same-paper titled PDF transcription; only line/page presentation normalized','material_content_unchanged_after_nfkc':True,'tasks':4,'answers':4,'scores_total':100}})
 for year in [2020,2021]:
  path=R/f'省考/北京/{year}/申论-统考.md';old=path.read_text(encoding='utf-8');notice=f'\n> **历史混卷汇编，非独立试卷。** 本文件混合了{year}年区级、乡镇两套申论的题目，原文保留用于校勘，不能作为一套完整原卷训练或计入独立试卷数量。请使用[完整区级卷](申论-区级.md)与[完整乡镇卷](申论-乡镇卷.md)；逐题映射见 `reports/FULL-REPAIR-BEIJING-ESSAY-RECONSTRUCTION-20261015.json`。\n\n'
  end=old.find('\n---',4)+4;new=old[:end]+notice+old[end:];path.write_text(new,encoding='utf-8');receipts.append({'path':path.relative_to(R).as_posix(),'action':'legacy_mixed_paper_notice','before_sha256':sha(old),'after_sha256':sha(new),'before_text':old})
 rp=R/'reports/FULL-REPAIR-BEIJING-ESSAY-RECONSTRUCTION-20261015.json';rp.write_text(json.dumps({'status':'passed','restored_real_papers':4,'restored_task_positions':16,'prior_partial_task_positions':8,'new_main_original_answers':16,'legacy_mixed_files':2,'operations':receipts},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Reconstructed 4 real papers / 16 questions and answers; preserved 6 complete before snapshots.')
if __name__=='__main__':
 import sys
 reconstruct() if '--apply' in sys.argv else make_packet()
