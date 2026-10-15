"""Expose a proven old source gap, preserving the unverified old key as evidence."""
from pathlib import Path
import hashlib,json,os,re,subprocess,uuid
from urllib.parse import quote
import cloud_quality as c
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
UP=Path('D:/projects/_gwy-upstream/xingcezhenti')
def sha(b):return hashlib.sha256(b if isinstance(b,bytes) else b.encode()).hexdigest()
def main():
 rel='省考/新疆/2024/行测-兵团.md';file=ROOT/rel;before=file.read_bytes();old=before.decode('utf8');source_rel='04-数量关系/2024年新疆生产建设兵团面向社会招录公务员考试《行测》题（网友回忆版）.md';source=UP/source_rel
 env={**os.environ,'GIT_CONFIG_GLOBAL':'NUL','GIT_CONFIG_NOSYSTEM':'1'}
 commit=subprocess.check_output(['git','-c','core.fsmonitor=false','rev-parse','HEAD'],cwd=UP,env=env,timeout=30).decode().strip()
 blob=subprocess.check_output(['git','-c','core.fsmonitor=false','show',commit+':'+source_rel],cwd=UP,env=env,timeout=30)
 # This upstream Windows checkout uses CRLF. The citation binds the actual Git
 # blob bytes; only its LF-normalized text may be compared with the checkout.
 assert blob.replace(b'\r\n',b'\n')==source.read_bytes().replace(b'\r\n',b'\n')
 fixed_url='https://github.com/ERRRC/xingcezhenti/blob/'+commit+'/'+quote(source_rel,safe='/')
 source_text=blob.decode('utf8');source_block=re.search(r'## 第 4 题[^\n]*\n(.*?)(?=\n---|\Z)',source_text,re.S);assert source_block and 'qid 16191092' in source_block[0] if source_block else False
 q=next(b for b in c.QBLOCK.finditer(old) if int(b[1])==54);oldanswers=c.DETAIL.findall(old);ids=[int(n) for n,body in oldanswers];assert ids==list(range(1,116))
 a=re.search(r'(<details>\s*<summary>第 54 题</summary>)(.*?)(</details>)',old,re.S);assert a and '**答案**：C' in a[2] and '略。' in a[2]
 notice='\n\n**答案**：待补完整题干及主图后核定。\n\n> **题面与答案边界：** 原来源遗漏长方形BCDE的主体图，题干以“……”省略关键条件，未交代A点位置。仅凭BC=40米、BE=30米及现存四个选项，不能核定唯一最短路程。以下C只作为未经验证的原来源答案留存，不能据其倒推或绘造真题。\n\n**原来源参考留存（非当前可验证主答案）**\n\n<!-- legacy-unverified-answer-54 -->\n'+a[2].strip()+'\n<!-- /legacy-unverified-answer-54 -->\n\n**查源记录**：上游原模块同样缺失主体图与完整条件；公开题库仅前题预览或要求登录，未取得可靠补全。详见 `reports/FULL-REPAIR-B-XINJIANG2024-54-20261015.jsonl`。\n\n'
 new=old[:a.start(2)]+notice+old[a.end(2):]
 fields={'缺失题干图片题号':[54],'缺失题干条件题号':[54],'已收录参考答案题号':[n for n in ids if n!=54],'待核来源答案题号':[54],'缺参考答案题号':[54],'题干缺失核实凭据':'reports/FULL-REPAIR-B-XINJIANG2024-54-20261015.jsonl'}
 new=set_fields(new,fields,'2026-10-15逐题实际内容扫描发现第54题主体图及A点关键条件在原源缺失；原C仅作未经核实的来源记录，不计完整可验证主答案。')
 title=re.search(r'(?m)^# [^\n]+\n',new);assert title
 front='\n> **题面待补：** 第54题缺少主体图与A点等关键位置条件，现存C仅为未核实的原来源记录。本卷不能据已有选项图片与来源字母宣称全部题面完整。\n'
 new=new[:title.end()]+front+new[title.end():]
 qnew=next(b for b in c.QBLOCK.finditer(new) if int(b[1])==54);assert qnew[0]==q[0],('Real task altered')
 qa=next((n,b) for n,b in oldanswers if int(n)==54)
 for n,body in oldanswers:
  now=next(x for k,x in c.DETAIL.findall(new) if k==n)
  if int(n)!=54:assert body==now
  else:assert body.strip() in now
 row={'path':rel,'status':'prepared','before_text':old,'before_sha256':sha(before),'after_text':new,'after_sha256':sha(new),'question_number':54,'qid':16191092,'kind':'confirmed_existing_question_missing_stem_image_and_conditions','question_and_real_options_untouched':True,'old_answer_verbatim_preserved':True,'original_source':{'fixed_url':fixed_url,'commit':commit,'source_sha256':sha(blob),'original_module_question':4,'excerpt':source_block[0]},'source_search_evidence':'D:/artifacts/gwy-quality-audit-20261015/xinjiang2024-bingtuan54-source-search-20261015.json','public_candidates':[{'url':'https://www.kkgwy.com/e/extend/exam/paper.php?id=10246','restriction':'同115题目录仅前5题预览，未取54'},{'url':'https://www.maiziliao.com/ks/gwy/1147.html','restriction':'同卷PDF题录，但只前2页预览；未下载会员资料'},{'url':'https://www.kangaroo.top/question_bank/papers/xinjiang/xinjiang_2024_xingce_2','restriction':'TinyFish live正常访问被登录墙阻止，未取54，run5e71ad4e-e0fc-4da1-bea4-8707af8b00d1'}],'boundary':'此为已有题的条件和主图残缺，非新缺失整题；没有新造图形或推定A点。'}
 rp=ROOT/'reports/FULL-REPAIR-B-XINJIANG2024-54-20261015.jsonl'
 with rp.open('a',encoding='utf8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 assert file.read_bytes()==before
 tmp=file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());os.replace(tmp,file)
 with rp.open('a',encoding='utf8') as f:f.write(json.dumps({'path':rel,'status':'applied','after_sha256':sha(file.read_bytes())},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 print(json.dumps({'status':'honest_unresolved_source_boundary','path':rel,'number':54,'source':fixed_url,'new_image_created':False,'usable_answers':114,'recognized_tasks':115},ensure_ascii=False))
if __name__=='__main__':main()
