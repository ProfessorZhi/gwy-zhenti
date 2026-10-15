"""Restore five verified original requirements; preserve complete per-file preimages."""
from pathlib import Path
import hashlib,json,os,re,subprocess,uuid
from urllib.parse import quote
import round5_bulk as p
import full_repair_precise_answer_audit_20261015 as precise
ROOT=Path(__file__).resolve().parents[1]
MOPS=Path('D:/projects/gwy-material-ops');BASE='95676de3a494730fdcacd43416fd51d6bed48ab6'
def sha(b):return hashlib.sha256(b if isinstance(b,bytes) else b.encode()).hexdigest()
def pin(fragment):
 candidates=[x for x in MOPS.glob('knowledge/gwy/001*/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/*/*/'+fragment)]
 assert len(candidates)==1,(fragment,candidates)
 f=candidates[0];rel=f.relative_to(MOPS).as_posix();env={**os.environ,'GIT_CONFIG_GLOBAL':'NUL','GIT_CONFIG_NOSYSTEM':'1'}
 b=subprocess.run(['git','-c','core.fsmonitor=false','show',BASE+':'+rel],cwd=MOPS,env=env,check=True,capture_output=True).stdout
 assert b==f.read_bytes(),fragment
 return {'path':rel,'fixed_url':'https://github.com/ProfessorZhi/gwy-material-ops/blob/'+BASE+'/'+quote(rel,safe='/'),'sha256':sha(b),'git_blob':subprocess.run(['git','hash-object','--stdin'],input=b,cwd=MOPS,env=env,capture_output=True,check=True).stdout.decode().strip(),'text':b.decode('utf8')}
def main():
 hbcounty=pin('2019年420联考《申论》真题（河北县级卷）及答案.pdf.md');hbtown=pin('2019年420联考《申论》真题（河北乡镇卷）及答案.pdf.md');gs=pin('2019年甘肃省公考《申论》真题及参考答案.pdf.md');qh=pin('2019年青海公务员考试《申论》真题及答案.pdf.md')
 plan={
 '省考/河北/2019/申论-统考.md':[(1,'（1）切合题意，观点鲜明，论证充分，层次分明，表达有力；\n\n（2）联系实际不拘泥于给定资料；\n\n（3）不少于1000字。',hbcounty),(2,'（1）联系实际不拘泥于“给定资料”；\n\n（2）观点明确，论证有力，层次清楚，语言流畅；\n\n（3）不少于1000字。',hbtown)],
 '省考/甘肃/2019/申论-统考.md':[(1,'（1）联系实际，不拘泥于“给定资料”；\n\n（2）立意明确，思路清晰，语言流畅；\n\n（3）总字数1000～1200字。',gs)],
 '省考/青海/2019/申论-统考.md':[(1,'（1）自选角度，立意明确；\n\n（2）联系实际，不拘泥于给定资料；\n\n（3）思路清晰，语言流畅；\n\n（4）不超过1000字。',qh)]}
 evidence=json.loads((ROOT/'reports/FULL-REPAIR-B-2019-HEALTH-TINYFISH-20261015.json').read_text(encoding='utf8'))
 web=json.loads(evidence['content'][0]['text'])['results'];pdf=next(x for x in web if x['url'].endswith('.pdf'));assert '总字数1000-1200' in pdf['text']
 health={'fixed_url':pdf['url'],'sha256':sha(pdf['text']),'text':pdf['text'],'author':'星光公考公开原题PDF，原命题机关署名未见；网页对照注明网友回忆版','evidence':'reports/FULL-REPAIR-B-2019-HEALTH-TINYFISH-20261015.json'}
 plan['省考/黑龙江/2019/申论-统考.md']=[(1,'（1）自选角度，立意明确；\n\n（2）依据“给定资料”，但不拘泥于“给定资料”；\n\n（3）思路清晰，语言流畅；\n\n（4）总字数1000—1200字。',health)]
 rp=ROOT/'reports/FULL-REPAIR-B-PRECISE-MANUAL-20261015.jsonl';details=[]
 for rel,tasks in plan.items():
  f=ROOT/rel;before=f.read_bytes();old=before.decode('utf8');d=p.parse(old,rel);new=old;metrics=[]
  for n,req,src in tasks:
   question=d['questions'][n];stem=question.split('要求：')[0].strip();key=p.norm(stem);source_norm=p.norm(src['text'])
   # Whole task stem is attested; punctuation, line wraps and OCR compatibility glyphs are ignored.
   assert key in source_norm,(rel,n,key)
   replacement=stem+'\n要求：\n\n'+req;assert new.count(question)==1,(rel,n);new=new.replace(question,replacement,1)
   source={k:v for k,v in src.items() if k!='text'};metrics.append({'number':n,'old_question':question,'restored_question':replacement,'source':source})
  if '黑龙江' in rel:
   new=new.replace('卷型: "统考"','卷型: "急需紧缺岗位（作文摘录）"',1).replace('# 2019 黑龙江省公务员录用考试 申论（统考）','# 2019 黑龙江省公务员录用考试 申论（急需紧缺岗位·作文摘录）',1)
  note='\n\n## 原题要求补全校勘（2026-10-15）\n\n本文件保留旧库题号及较完整材料，不据摘录题数宣称原卷完整。本次逐题对照完整同题原稿，补回原先遗漏的作答要求；原题及误混文字逐字留存修复凭据。\n\n'
  for r in metrics:note+='- 当前第'+str(r['number'])+'题：[同题原卷对照来源]('+r['source']['fixed_url']+')。源文件／提取正文 SHA-256：`'+r['source']['sha256']+'`。\n'
  if '黑龙江' in rel:note+='\n公开完整题本明确为2019年急需紧缺岗位试卷；本文只保留其中作文摘录，兼容旧“统考”文件路径。[同题网页交叉核对](https://www.benet-wh.com.cn/shengkao/shenlun/26794.html)注明“网友回忆版”，不据此宣称官方发布。\n'
  new+=note
  nd=p.parse(new,rel);assert nd['answers']==d['answers'];assert set(nd['questions'])==set(d['questions'])
  for r in metrics:
   q=nd['questions'][r['number']];rules=precise.word_rules(q)
   for v in precise.extract_versions(nd['answers'][r['number']]):assert not precise.inspect_version(q,v,rules)[1],(rel,r,v)
  row={'path':rel,'status':'prepared','before_sha256':sha(before),'before_text':old,'after_sha256':sha(new),'after_text':new,'requirements':metrics,'answers_unchanged':True,'no_material_replacement':True}
  with rp.open('a',encoding='utf8') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush();os.fsync(out.fileno())
  tmp=f.with_name(f.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());os.replace(tmp,f)
  with rp.open('a',encoding='utf8') as out:out.write(json.dumps({'path':rel,'status':'applied','after_sha256':sha(f.read_bytes())},ensure_ascii=False)+'\n');out.flush();os.fsync(out.fileno())
  details.append({'path':rel,'questions':[r['number'] for r in metrics]});print(rel,'restored',details[-1]['questions'],flush=True)
 # An empty alternate label was separated from its body by old source transcription.
 # Preserve the complete alternate in the existing appendix as an explicitly historical version.
 rel='省考/甘肃/2021/申论-乡镇卷.md';f=ROOT/rel;before=f.read_bytes();old=before.decode();needle='参考答案二：\n\n</details>';assert old.count(needle)==1
 new=old.replace(needle,'> 来源边界校勘：旧“参考答案二”标签为空，其对应文字已在下方转录附记完整保留，作为历史参考；本题当前主作答为上方完整参考答案一。\n\n</details>',1)
 row={'path':rel,'status':'prepared','before_sha256':sha(before),'before_text':old,'after_sha256':sha(new),'after_text':new,'change':'明确已有合规版本为主作答，旧空标签不再冒充另一份完整答案；历史文字在原附记保留'}
 with rp.open('a',encoding='utf8') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush();os.fsync(out.fileno())
 tmp=f.with_name(f.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());os.replace(tmp,f)
 with rp.open('a',encoding='utf8') as out:out.write(json.dumps({'path':rel,'status':'applied','after_sha256':sha(f.read_bytes())},ensure_ascii=False)+'\n')
 print('Removed false empty alternate; full historical original preserved.');print(details)
if __name__=='__main__':main()
