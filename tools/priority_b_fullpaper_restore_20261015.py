"""Restore only the ten independently matched Tianjin/Guangdong complete papers."""
import hashlib,json,os,re,subprocess,uuid,unicodedata
from pathlib import Path
from difflib import SequenceMatcher
import round5_bulk as parser
from paper_integrity_repair import set_fields
from full_repair_answers_20261015 import validate_answer,render_answer
from shanghai2016_restore_20261015 import pretty
ROOT=Path(__file__).resolve().parents[1];M=Path('D:/projects/gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
def sha(t):return hashlib.sha256(t if isinstance(t,bytes) else t.encode()).hexdigest()
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKC',t) if c.isalnum())
def clean(t):
 t=re.sub(r'获取试卷更新，请关注公众号[^\n]*','',t)
 t=re.sub(r'(?m)^\s*(?:第\s*\d+\s*页\s*共\s*\d+\s*页|-\s*\d+\s*-)\s*$','',t)
 return t.strip()
def mainbody(t):
 m=re.search(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',t,re.S)
 if m:return m[1]
 return re.split('参考答案说明|文章分析|> 来源说明|> 出处',t)[0].strip()
def old_segments(old):
 found=[];seen=set()
 for t in old['parsed']['materials'].values():
  ms=list(re.finditer(r'(?m)^材料\s*\d+\s*[：:]?\s*$',t))
  for i,m in enumerate(ms):
   body=t[m.end():ms[i+1].start() if i+1<len(ms) else len(t)].strip();key=norm(body)
   if key and key not in seen:found.append(body);seen.add(key)
 return found
def merge_materials(packet,old):
 candidates=old_segments(old);used=set();parts=[];receipt=[]
 for m in packet['materials']:
  source=clean(m['text']);sn=norm(source);pairs=[]
  for j,t in enumerate(candidates):
   if j in used:continue
   on=norm(t);ratio=SequenceMatcher(None,sn,on,autojunk=False).ratio();pairs.append((ratio,j,t,on))
  choice=max(pairs,default=(0,-1,'',''));ratio,j,t,on=choice
  # Retain the readable old segment where it is the same material and no shorter.
  use_old=ratio>=.85 and len(on)>=len(sn)*.90
  selected=t if use_old else source
  if use_old:used.add(j)
  parts += [f'### 材料{m["number"]}','',''+pretty(selected),'']
  receipt.append({'number':m['number'],'selected':'existing_readable_material' if use_old else 'complete_same_paper_source','best_existing_similarity':ratio,'source_characters':len(sn),'selected_characters':len(norm(selected)),'source_sha256':sha(source),'selected_sha256':sha(selected),'source_text':source,'selected_text':selected})
 return '\n'.join(parts).strip(),receipt
def atomic(p,t):
 temp=p.with_name(p.name+'.fullpaper-'+uuid.uuid4().hex+'.tmp');temp.write_bytes(t.encode());os.replace(temp,p)
def main():
 packets=json.loads((ROOT/'tools/data/priority-confirmed-mops-source-packets-20261015.json').read_text(encoding='utf-8'))[:10]
 oldrows=json.loads((ROOT/'reports/FULL-REPAIR-PRIORITY-B-PREIMAGES-20261015.json').read_text(encoding='utf-8'));oldby={r['path']:r for r in oldrows}
 answers=json.loads((ROOT/'tools/data/priority-b-restoration-answers-20261015.json').read_text(encoding='utf-8'));newby={(r['path'],r['number']):r for r in answers};summary=[]
 for packet in packets:
  rel=packet['target_path'];old=oldby[rel];p=ROOT/rel;assert sha(p.read_bytes())==old['before_sha256'],('Concurrent modification',rel)
  assert packet['points_sum']==100 and packet['material_label_sequence_complete'];assert all(r['question_similarity']>=.97 for r in packet['current_to_source_task_map'])
  assert sorted(m['number'] for m in packet['materials'])==list(range(1,len(packet['materials'])+1))
  sr=packet['source_relative_path'];env=dict(os.environ,GIT_CONFIG_GLOBAL='NUL',GIT_CONFIG_NOSYSTEM='1');cmd=['git','-c','core.fsmonitor=false'];blob=subprocess.check_output(cmd+['rev-parse',REV+':'+sr],cwd=M,env=env,timeout=120).decode().strip();data=subprocess.check_output(cmd+['cat-file','blob',blob],cwd=M,env=env,timeout=120);assert data==Path(packet['source_path']).read_bytes();assert sha(data.decode('utf-8').replace('\r\n','\n'))==packet['source_sha256']
  qs={q['number']:clean(q['text']) for q in packet['questions']};qs={n:re.sub(r'(?m)^\s*\d{4}\s*年[^\n]*(?:解析|参考答案)[^\n]*$','',q).strip() for n,q in qs.items()};nq=packet['standard_question_count'];assert set(qs)==set(range(1,nq+1))
  mapping={r['source_number']:r['current_number'] for r in packet['current_to_source_task_map']};rendered={};metrics=[]
  for n,q in qs.items():
   key=(rel,n)
   if key in newby:
    e=newby[key];count=validate_answer(q,e);rendered[n]=render_answer(e);kind=e['attribution_kind']
   else:
    assert n in mapping,(rel,n,'Missing full answer');donor=mapping[n];whole=old['parsed']['answers'][str(donor)];body=pretty(mainbody(whole));count=validate_answer(q,{'answer':body,'attribution_kind':'owned_source','author':'原库署名保留'});kind='preserved_existing'
    if '<!-- full-repair-answer-20261015 -->' in whole:
     # Preserve original authorship and explanation block, merely remap its task number.
     rendered[n]=whole
    else:rendered[n]='**同题来源参考作答（原库保留）**\n\n<!-- full-repair-answer-20261015 -->\n'+body+'\n<!-- /full-repair-answer-20261015 -->\n\n> 来源说明：原库已收录的同题参考，按完整题本原序回接；原署名与全部解析见恢复凭据，不将其改称原创或官方答案。不是官方答案，未经实考评分。'
   metrics.append({'number':n,'characters':count,'kind':kind,'old_number':mapping.get(n)})
  mats,alignment=merge_materials(packet,old);header=old['before_text'][:old['before_text'].index('\n---',4)+4]+'\n';fields={'已收录参考答案题号':list(qs),'缺参考答案题号':[],'对照题本题量':nq,'实有题数':nq,'缺失原题号':[],'原题完整性核实凭据':'reports/FULL-REPAIR-PRIORITY-B-FULLPAPERS-20261015.jsonl','完整题本固定来源':packet['source_url']}
  if rel=='省考/天津/2020/申论-A类.md':fields['卷型']='市级卷（历史文件名A类兼容）'
  header=set_fields(header,fields,'2026-10-15依据固定提交同年同卷完整题本恢复遗漏原题、分值及要求；保留可用旧材料和正确既有参考，缺文以来源原稿或明确AI示范补足。')
  title=re.search(r'(?m)^# [^\n]+',old['before_text'])[0]+'（完整题本核对版）';notice=f'> 本卷依据[同年同题完整原稿]({packet["source_url"]})恢复为{nq}题，分值合计100。固定提交实际Git blob已核对；原资料编制者／答文署名以原稿为准，未明确者不推定为机构或实考高分。材料按原题编号完整衔接，同一材料优先保留原库较清晰且不短的版本；所有旧材料、题目、答案及源异文完整存证。'
  out=[header,title,'',notice,'']
  if '广东/2017/' in rel:out += ['> 卷名校勘：用户原资料文件名写“乡镇级”，但其中分享经济、公共服务共享和《共享与发展》三题与本卷逐题相符；未仅凭文件名调换卷别。原文件名异文及公开同题依据见恢复凭据。','']
  if '天津/2016/' in rel:out += ['> 原参考校勘：原资料第4题后误附“政府公信力”范文，与创业梦想题不对应，未作为本题参考。该错配原文存证，主文为依据本卷材料独立编写的AI辅助示范。','']
  out += ['## 给定材料','',mats,'','## 作答要求','']
  for n,q in qs.items():out += [f'## 第 {n} 题','',pretty(q),'']
  out += ['## 答案与解析','']
  for n,a in rendered.items():out += [f'<a id="r7-reference-{n}"></a>','<details>',f'<summary>第 {n} 题</summary>','',a,'','</details>','']
  new='\n'.join(out);nd=parser.parse(new,rel);assert len(nd['questions'])==len(nd['answers'])==nq
  row={'path':rel,'status':'prepared','before_sha256':old['before_sha256'],'before_text':old['before_text'],'after_sha256':sha(new),'after_text':new,'source':{**packet,'git_blob':blob,'verified_git_revision':REV},'old_task_map':packet['current_to_source_task_map'],'materials_alignment':alignment,'answers':metrics,'original_old_answers':old['parsed']['answers'],'expected_task_count':nq}
  rp=ROOT/'reports/FULL-REPAIR-PRIORITY-B-FULLPAPERS-20261015.jsonl'
  with rp.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  atomic(p,new);assert sha(p.read_bytes())==row['after_sha256']
  with rp.open('a',encoding='utf-8') as f:f.write(json.dumps({'path':rel,'status':'applied','after_sha256':row['after_sha256']},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  item={'path':rel,'question_count':nq,'new_tasks':packet['missing_source_task_numbers'],'answers':metrics};summary.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
 (ROOT/'reports/FULL-REPAIR-PRIORITY-B-FULLPAPERS-SUMMARY-20261015.json').write_text(json.dumps({'status':'passed','papers':summary,'restored_papers':len(summary),'added_original_task_positions':sum(len(p['new_tasks']) for p in summary),'boundary':'Complete same-paper sources, not directory-count inference; lower-quality source variants do not overwrite better existing paragraphs.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
