import sys,json,re,hashlib
from pathlib import Path
sys.path.insert(0,'tools');import round5_bulk as p,full_repair_precise_answer_audit_20261015 as a,full_repair_answers_20261015 as app
sha=lambda s:hashlib.sha256(s.encode()).hexdigest();entries=[];pre={};legacy={};maps=[]
for year in [2017,2020,2022]:
 src=f'省考/广东/{year}/申论-县级卷.md';rel=f'省考/广东/{year}/申论-统考.md';st=Path(src).read_text(encoding='utf-8');sd=p.parse(st,src);old=Path(rel).read_text(encoding='utf-8');d=p.parse(old,rel);q=d['questions'][1];ans=sd['answers'][3];v=a.extract_versions(ans);assert len(v)==1 and not a.inspect_version(sd['questions'][3],v[0],a.word_rules(sd['questions'][3]))[1]
 urls=re.findall(r'\[([^\]]+)\]\((https://[^)]+)\)',ans)
 e={'path':rel,'number':1,'question':q,'answer':v[0]['body'],'attribution_kind':'ai_revision','author':'AI辅助修订；与本轮已校核同题命名卷的修订主文一致','sources':[{'title':x[0],'url':x[1]} for x in urls],'replace_reason':'恢复真实800—1000字要求后，匹配同年同题命名卷已经完整修订且符合篇幅的主文，保留此前超长稿供对照'}
 app.validate_answer(q,e);entries.append(e);pre[rel]=old;legacy[rel]=d['answers'][1];maps.append({'path':rel,'number':1,'source_path':src,'source_sha256':sha(st),'source_question':sd['questions'][3],'target_question':q,'question_identity':'同年主题及给定材料匹配，题目实义一致；题号/要求异文已在约束映射报告记录','body_sha256':sha(v[0]['body'])})
rel='省考/广东/2018/申论-广州市考-3月25日.md';old=Path(rel).read_text(encoding='utf-8');d=p.parse(old,rel);q=d['questions'][1];body=a.extract_versions(d['answers'][1])[0]['body'];paras=body.split('\n\n');assert paras[3].startswith('但乡愁')
paras[3]='但乡愁不能代替生活条件。青年回乡，也要面对收入、教育、医疗和事业机会。蒋玮把电商经验带回故乡，逐步经营起来，既靠个人努力，也受益于场地、贷款和服务支持。这说明回乡并非放弃现代生活，而是让现代发展要素进入乡村。当人才、资金与技术能够双向流动，乡村才会成为平等选择，而非不得已的退路。'
body='\n\n'.join(paras);e={'path':rel,'number':1,'question':q,'answer':body,'attribution_kind':'ai_revision','author':'AI辅助修订（原主文亦为AI示范）','sources':[],'replace_reason':'按原题1200—1500字要求，重写生活条件与要素流动论证段，保留全部论点、材料事例和原主文，避免正文超限','target_word_range':[1200,1500]};app.validate_answer(q,e);entries.append(e);pre[rel]=old;legacy[rel]=d['answers'][1]
fp=Path('reports/PRECISE-SH-GD-TJ-CONSTRAINT-FOLLOWUP-20261015.json');fp.write_text(json.dumps({'status':'prepared','preimages':pre,'entries':entries,'maps':maps},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
result,receipts=app.apply_entries(Path('.'),entries,True);assert result['status']=='passed',result
for rel,old in legacy.items():
 text=Path(rel).read_text(encoding='utf-8').rstrip()+'\n\n## 原约束恢复后的旧稿校勘\n\n<details>\n<summary>展开此前收录作答（仅供版本对照）</summary>\n\n'+old+'\n\n</details>\n';Path(rel).write_text(text,encoding='utf-8',newline='')
 before=p.parse(pre[rel],rel);after=p.parse(text,rel);assert before['questions']==after['questions'] and before['materials']==after['materials'];v=a.extract_versions(after['answers'][1]);assert len(v)==1 and not a.inspect_version(after['questions'][1],v[0],a.word_rules(after['questions'][1]))[1];assert old in text
for receipt in receipts:receipt['after_sha256']=sha(Path(receipt['path']).read_text(encoding='utf-8'))
fp.write_text(json.dumps({'status':'passed','preimages':pre,'entries':entries,'maps':maps,'receipts':receipts,'body_counts':[a.char_count(e['answer']) for e in entries]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(result,[a.char_count(e['answer']) for e in entries])
