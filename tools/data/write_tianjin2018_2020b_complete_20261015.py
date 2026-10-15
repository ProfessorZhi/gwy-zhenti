"""Restore proved Tianjin2018 and 2020B complete same-paper material and tasks."""
import sys,json,re,hashlib,os,uuid,difflib
from pathlib import Path
sys.path.insert(0,'tools');import round5_bulk as p,full_repair_precise_answer_audit_20261015 as a,full_repair_answers_20261015 as app
from priority_b_fullpaper_restore_20261015 import old_segments
from paper_integrity_repair import set_fields
from full_repair_layout_20261015 import format_essay
sha=lambda s:hashlib.sha256(s if isinstance(s,bytes) else s.encode()).hexdigest()
packets=json.loads(Path('tools/data/tianjin2018-2020b-complete-source-packets-20261015.json').read_text(encoding='utf-8'));ready=[]
for packet in packets:
 rel=packet['path'];old=packet['before_text'];assert sha(Path(rel).read_text(encoding='utf-8'))==packet['before_sha256'];d=p.parse(old,rel);qs={int(k):v for k,v in packet['questions'].items()};assert len(qs)==4 and sum(packet['points'])==100
 candidates=old_segments({'parsed':d});mats=[];alignment=[]
 for m in packet['materials']:
  src=m['text'];sn=p.norm(src);choices=[(difflib.SequenceMatcher(None,sn,p.norm(x),autojunk=False).ratio(),x) for x in candidates];ratio,match=max(choices,default=(0,''));keep=ratio>=.98 and len(p.norm(match))>=len(sn)*.99
  selected=match if keep else src;selected=re.sub(r'(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])','',selected);selected=re.sub(r'但\s*\n\s*是，直接向用户收费','但是，直接向用户收费',selected);selected=re.sub(r'\n{3,}','\n\n',selected).strip();mats.append('### 材料'+str(m['number'])+'\n\n'+selected)
  alignment.append({'number':m['number'],'best_existing_similarity':ratio,'selected_kind':'preserved_existing_readable' if keep else 'complete_owned_source','source_text':src,'selected_text':selected,'source_sha256':sha(src),'selected_sha256':sha(selected)})
 fm=old[:old.index('\n---',4)+4]+'\n';fields={'实有题数':4,'对照题本题量':4,'缺失原题号':[],'给定材料段数':6,'题目分值':[15,20,25,40],'已收录参考答案题号':[1,2,3,4],'缺参考答案题号':[],'完整题本固定来源':packet['source_url'],'完整题本SHA256':packet['source_sha256'],'原题完整性核实凭据':'reports/FULL-REPAIR-TIANJIN-2018-2020B-COMPLETE-20261015.json'}
 if '2020' in rel:fields['卷型']='区县卷（历史文件名B类兼容）'
 fm=set_fields(fm,fields,'2026-10-15依据固定同年同卷完整原稿恢复6段材料和4道真实任务，原3道题逐题回接完整题序；原题约束、完整来源参考正文分别核验，不以目录计数补造题目。')
 title=re.search(r'(?m)^# [^\n]+',old)[0];out=[fm,title,'',f'> 完整题本依据：[用户已有原稿（固定Git blob已核验）]({packet["source_url"]})；[同题公开转录交叉核对]({packet["public_url"]})。原3道任务依完整题序回接1→3、2→2、3→1，补回此前漏收的第4题及其相关材料。全部修复前材料、题目、参考和异文保存在恢复凭据。','']
 if '2020' in rel:out+=['> 同题异文：用户原稿第2题写“S区”，但同段材料明确为“G县”，原库题面和公开同题完整转录也写“G县”；本次保留“G县”并记录原稿异文，不倒灌错配地名。历史文件名B类保留兼容。','']
 else:out+=['> 材料4日期异文：旧库为2016年9月28日至2017年2月，用户原稿和同题公开转录写2017年至2018年。本轮保留旧库日期；国家文物局2016年9月30日同期报道证实该268件（套）展览于2016年举办。来源：http://www.ncha.gov.cn/art/2016/9/30/art_723_133885.html 。原稿异文另存于恢复凭据。','','> 分值校勘：用户原稿第4题作答要求正文未显示分值，其同题解析注明40分，公开完整题本亦为40分；全卷分值为15、20、25、40，共100分。','']
 out+=['## 给定材料','','\n\n'.join(mats),'','## 作答要求','']
 for n,q in qs.items():out += ['## 第 '+str(n)+' 题','',q,'']
 out+=['## 答案与解析',''];metrics=[];mapping={x['new_number']:x['old_number'] for x in packet['mapping']}
 for n,q in qs.items():
  if n in mapping:
   on=mapping[n];versions=a.extract_versions(d['answers'][on]);assert len(versions)==1;body=versions[0]['body'];kind='preserved_existing_source';author='原库已收录同题参考，作者署名未核实；本轮仅按完整题序回接'
  else:body=packet['source_answer_4'];kind='owned_source';author='用户资料库同题完整参考原稿，未署个人作者；本轮按固定版本整理'
  e={'answer':body,'attribution_kind':kind,'author':author,'sources':[{'title':'用户已有同题完整原稿（固定Git版本）','url':packet['source_url']}],'replace_reason':'补回完整同题作文来源正文' if n==4 else '依完整原题序与真实字数约束保留原有合规参考，正文不改写'}
  count=app.validate_answer(q,e);issues=a.inspect_version(q,a.strip_body(body),a.word_rules(q))[1];assert not issues,(rel,n,issues)
  out += ['<a id="r7-reference-'+str(n)+'"></a>','<details>','<summary>第 '+str(n)+' 题</summary>','',app.render_answer(e),'','</details>',''];metrics.append({'number':n,'old_number':mapping.get(n),'kind':kind,'characters':count,'body_sha256':sha(body)})
 new='\n'.join(out);new,layout=format_essay(new,rel);new=new.rstrip()+'\n';nd=p.parse(new,rel);assert len(nd['questions'])==len(nd['answers'])==4
 for x in packet['mapping']:
  originalbody=a.extract_versions(d['answers'][x['old_number']])[0]['body'];newbody=a.extract_versions(nd['answers'][x['new_number']])[0]['body'];assert originalbody==newbody,(rel,x)
 report={'path':rel,'before_sha256':packet['before_sha256'],'before_text':old,'after_sha256':sha(new),'after_text':new,'source_git_blob':packet['source_git_blob'],'source_commit':packet['source_commit'],'source_url':packet['source_url'],'source_sha256':packet['source_sha256'],'source_git_blob_verified':True,'public_url':packet['public_url'],'public_response_sha256':packet['public_response_sha256'],'task_mapping':packet['mapping'],'source_question_region':packet['public_question_region'],'materials_alignment':alignment,'expected_tasks':4,'points':[15,20,25,40],'answers':metrics,'layout':layout,'original_answers':d['answers']};ready.append((rel,old,new,report))
receipt=Path('reports/FULL-REPAIR-TIANJIN-2018-2020B-COMPLETE-20261015.json');assert not receipt.exists();receipt.write_text(json.dumps({'status':'prepared','papers':[x[3] for x in ready]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for rel,old,new,report in ready:
 assert Path(rel).read_text(encoding='utf-8')==old;tmp=Path(rel+'.complete-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());os.replace(tmp,rel);assert sha(Path(rel).read_bytes())==report['after_sha256']
receipt.write_text(json.dumps({'status':'passed','papers':[x[3] for x in ready],'restored_original_task_positions':2,'restored_full_owned_source_essays':2,'ai_generated_answers':0,'boundary':'原稿完整6材料4题经同题公开全文校核；不是官方原件认证；未以其他卷型或模拟题补缺。所有原文及参考在修复前快照可逆保留。'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('APPLIED',[(rel,[x['characters'] for x in report['answers']]) for rel,_,_,report in ready])
