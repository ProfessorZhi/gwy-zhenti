import json,re,sys,hashlib,subprocess,os,uuid
from pathlib import Path
from urllib.parse import quote
from difflib import SequenceMatcher
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as b
from full_repair_precise_answer_audit_20261015 import word_rules,extract_versions,char_count
from paper_integrity_repair import set_fields
D=json.loads((R/'tools/data/precise-a-review-packets-20261015.json').read_text(encoding='utf8'));existing={x['index']:x for x in json.loads((R/'tools/data/precise-a-manual-task-matches-20261015.json').read_text(encoding='utf8'))};owned={x['index']:x for x in json.loads((R/'tools/data/precise-a-manual-owned-matches-20261015.json').read_text(encoding='utf8'))};M=Path('D:/projects/gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6';sha=lambda x:hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
net=json.loads((R/'tools/data/precise-a-manual-public-sources-20261015.json').read_text(encoding='utf8'))['results'];patches=[]
def ownrecord(path,q):
 p=Path(path);raw=p.read_bytes();sr=p.relative_to(M).as_posix();blob=subprocess.run(['git','show',REV+':'+sr],cwd=M,check=True,stdout=subprocess.PIPE).stdout;assert raw==blob
 return dict(kind='owned_complete_same_paper_task',url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(sr,safe='/'),source_path=str(p),source_sha256=sha(raw),source_commit=REV,source_git_blob_verified=True,source_task=q)
def trim_material(t):
 h=re.search(r'(?m)^\s*(?:#{1,4}\s*)?(?:给定资料|资料|材料)\s*[一1][：:\s]',t)
 if h:t=t[h.start():]
 return t.split('作答要求')[0]
for i in [5,9,10,11,16,17,18,19,20,21,27,38,39,40,42,43,45,46,47,51,54,55,56,57,62,63,68,73,79,80,86,96,12,13,14]:
 r=D[i];e=None;q=None
 if i in [16,17,18,19,20,21,62,63,68,73,80]:
  m=existing[i]['matches'][0];assert m['similarity']>=.98,(i,m['similarity']);p=R/m['path'];raw=p.read_bytes();pd=b.parse(raw.decode(),m['path']);grams=b.shingles(trim_material(pd['materials'][m['number']]));fragment_norm=b.norm(trim_material(r['material']));coverage=sum(x in fragment_norm for x in grams)/max(1,len(grams));assert coverage>.90,(i,coverage)
  q=m['question'];e=dict(kind='same_year_same_area_existing_complete_task',path=m['path'],number=m['number'],source_sha256=sha(raw),source_question=q,question_key_similarity=m['similarity'],canonical_material_12gram_in_fragment_coverage=coverage)
 elif i in [5,9,10,11,38,39,40,42,43,45,47,51,54,55,86,96]:
  m=owned[i]['matches'][0];assert m['similarity']>=.96,(i,m['similarity']);q=m['source_question'];e=ownrecord(m['source_path'],q);e['question_key_similarity']=m['similarity']
 elif i in [46,27]:
  url='http://m.houzhiwang.com/html/201910/2340.html' if i==46 else 'http://www.ahgkw.org/2024/0828/62963.html';n=next(z for z in net if z['url']==url);txt=n['text'];phrase='（四）进一步思考' if i==46 else '“给定资料4”中提到：“做好';pos=txt.rfind(phrase);assert pos>0;q=txt[pos:];q=re.split(r'\n\s*(?:2023年安徽公务员|点击分享|参考答案)',q)[0].strip();assert len(q)<900 and word_rules(q)['kind']!='unspecified';e=dict(kind='same_year_same_paper_public_complete_question',url=url,source_task=q,source_text_sha256=sha(txt))
 elif i in [56,57]:
  dr=next(p for p in (M/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf').iterdir() if '山东' in p.name);p=next(dr.rglob('2022*申论*'+('A' if i==56 else 'B')+'类）.pdf.md'));t=p.read_text(encoding='utf8');key='请结合全部给定资料，以';pos=t.rfind(key);q=t[pos:];q=re.sub(r'<!--.*?-->','',q,flags=re.S);q=re.sub(r'\n\s*\d+\s*$','',q).strip();assert word_rules(q)['kind']=='approximate_target';e=ownrecord(str(p),q)
 elif i==79:
  dr=next(p for p in (M/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf').iterdir() if '广西' in p.name);p=next(dr.rglob('2018*申论*B卷*.md'));t=p.read_text(encoding='utf8');pos=t.index('四、请围绕微传播');tail=t[pos:];q=tail[:tail.index('<!-- page:')].strip();assert word_rules(q)['minimum']==800;e=ownrecord(str(p),q)
 elif i in [12,13,14]:
  proof=json.loads((R/'reports/FULL-REPAIR-SICHUAN2021-PUBLIC-REQUIREMENTS-20261015.json').read_text(encoding='utf8'));suffix={12:'26384.html',13:'26383.html',14:'26385.html'}[i];e=next(z for z in proof if z['url'].endswith(suffix)).copy();q=e['same_question_excerpt'];e['kind']='parent_independently_fetched_complete_same_paper_public_task';e['proof_report']='reports/FULL-REPAIR-SICHUAN2021-PUBLIC-REQUIREMENTS-20261015.json'

 assert e and q,(i,'evidence');reqpos=q.find('要求');assert reqpos>=0,(i,q);req=q[reqpos:];quota=re.search(r'(?:\d{2,4}\s*[-—～~]\s*)?\d{2,4}\s*字(?:左右|以上|以下|以内)?',req);assert quota,(i,req);req=req[:quota.end()].rstrip('。；;')+'。';req=re.sub(r'<!--.*?-->','',req,flags=re.S);req=re.split(r'\n\s*(?:20\d\d\s*年|###?\s*(?:参考答案|【参考)|参考答案|文章分析)',req)[0];req=re.sub(r'(?<=\d)\s+(?=字)','',req);req=re.sub(r'\n{3,}','\n\n',req).strip();assert len(req)<1100,(i,len(req));assert word_rules(req)['kind']!='unspecified',(i,req)
 if i==42:e['source_variant_notice']='用户完整原稿及联创世华完整HTML均录1000–2000字；另一同机构PDF检索摘要录1000–1200，未取得PDF正文，保留原稿异文不冒称官方上限；现正文1090同时符合两者。';e['corroboration_url']='https://sd.lgwy.net/html/m/m_52100.html'
 newq=re.split(r'要求[：:]',r['question'],1)[0].strip()+'\n\n'+req
 patches.append(dict(index=i,path=r['path'],number=r['question_number'],new_question=newq,evidence=e,restored_rules=word_rules(newq)))
outp=R/'tools/data/precise-a-manual-question-patches-20261015.json';outp.write_text(json.dumps(patches,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
rp=R/'reports/FULL-REPAIR-PRECISE-A-REQUIREMENTS-20261015.jsonl';assert not rp.exists();by={}
for d in patches:by.setdefault(d['path'],[]).append(d)
for rel,ds in by.items():
 p=R/rel;raw=p.read_bytes();old=raw.decode();parsed=b.parse(old,rel);new=old
 for z in ds:
  oldq=parsed['questions'][z['number']];assert new.count(oldq)==1,(rel,z['number']);new=new.replace(oldq,z['new_question'],1)
  url=z['evidence'].get('url') or 'https://github.com/ProfessorZhi/gwy-zhenti/blob/main/'+quote(z['evidence']['path'],safe='/');new+=f'\n> 第{z["number"]}题作答要求校勘：依据[同年同题明确任务]({url})补回原已缺失的要求，题干与材料逐题匹配凭据见 `reports/FULL-REPAIR-PRECISE-A-REQUIREMENTS-20261015.jsonl`；不是官方题本逐字认证。\n'
  if z['index']==42:new+='\n> 字数异文：所据完整原稿及联创世华同题HTML均写1000—2000字；另份PDF检索摘要显示1000—1200字，尚未取得该PDF正文，本次保留原稿异文，现范文1090字同时符合两者。\n'
 new=set_fields(new,{'作答要求校勘凭据':'reports/FULL-REPAIR-PRECISE-A-REQUIREMENTS-20261015.jsonl'},'2026-10-15逐题核对同年同题明确来源，恢复缺失作答要求；不根据现有答案长度猜测或放宽限制。');rec=dict(path=rel,before_sha256=sha(raw),before_text=old,after_sha256=sha(new),task_requirements=ds)
 with rp.open('a',encoding='utf8') as f:f.write(json.dumps(rec,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 tmp=p.with_name(p.name+'.requirements-a-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());assert p.read_bytes()==raw;os.replace(tmp,p);assert sha(p.read_bytes())==sha(new);print('RESTORED',rel,[z['number'] for z in ds])
print('TASKS',len(patches))
