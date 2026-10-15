"""Repair evidenced lost formulas; preserve old keys/questions/images and full old text."""
import sys,json,re,hashlib,os,uuid
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,'tools');from paper_integrity_repair import set_fields
ROOT=Path('.');rel='省考/上海/2017/行测-统考.md';target=ROOT/rel;old=target.read_text(encoding='utf-8');sha=lambda s:hashlib.sha256(s if isinstance(s,bytes) else s.encode()).hexdigest();plan=json.loads(Path('tools/data/shanghai2017-reviewed-formula-bodies-20261015.json').read_text(encoding='utf-8'));answers={int(k):v for k,v in plan['answers'].items()};pattern=re.compile(r'(<details>\s*<summary>第\s+(\d+)\s+题</summary>)(.*?)(</details>)',re.S);oldparts={int(m[2]):m[3].strip() for m in pattern.finditer(old)};assert len(oldparts)==136
beforekey={n:re.search(r'\*\*答案\*\*[：:]\s*([A-D]+)',v)[1] for n,v in oldparts.items()};prefix=old[:old.index('## 答案与解析')];records=[]
url='https://github.com/ProfessorZhi/gwy-zhenti/blob/f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab/'+quote(rel,safe='/')
def sub(m):
 n=int(m[2])
 if n not in answers:return m[0]
 key=beforekey[n];body='**答案**：'+key+'\n\n**AI辅助修订解析**\n\n'+answers[n]+'\n\n> 来源说明：根据本卷原题、给定表格/图像及旧来源解析独立重算、补足公式与断尾；作者／整理性质为AI辅助修订，不是原机构作者原稿，不是官方答案，未经实考评分。原解析和完整修复前卷面保存于修复凭据及下方旧稿对照。\n\n[本库固定同题及给定材料基线]('+url+')'
 if n in [53,71]:body+='\n\n> 来源条件争议：'+plan['remaining_source_ambiguities'][str(n)]
 records.append({'number':n,'answer_key':key,'before_answer':oldparts[n],'before_answer_sha256':sha(oldparts[n]),'new_explanation':answers[n],'new_explanation_sha256':sha(answers[n]),'kind':'ai_revision','source_condition_pending':n in [53,71]})
 return m[1]+'\n\n'+body+'\n\n'+m[4]
new=pattern.sub(sub,old)
new+='\n\n## 解析公式修复前版本对照\n\n以下为旧来源原稿，仅供校勘；当前解析见各题上方，原稿中缺失公式不作为现行解答。\n'
for n in sorted(answers):new+='\n<details>\n<summary>展开此前第'+str(n)+'题解析（历史校勘）</summary>\n\n'+oldparts[n]+'\n\n</details>\n'
fields={'校验状态':'原卷题面、136题题号与既有38张题面图保持；2026-10-15据原题、原卷图表重算并修复22题解析公式/断尾/受力表述，明确AI修订且完整保留旧稿；第53与71题仍有来源规则/条件歧义，已逐题说明，不作唯一标准答案认证。','解析公式修复凭据':'reports/FULL-REPAIR-SHANGHAI2017-FORMULA-20261015.json','解析公式修复题号':sorted(answers),'解析来源争议题号':[53,71],'解析来源争议说明':'53乘积法得D而源另列可拟合规则得A；71原题写前三天总额但来源按第三天单日额求D，原文字样保留'}
new=set_fields(new,fields,'2026-10-15公式修复后更新当前状态，历史问题全文与原状态在独立修复凭据保留；不以解码成功冒称题图题义均验真。');new=new.rstrip()+'\n'
newparts={int(m[2]):m[3].strip() for m in pattern.finditer(new)};assert len(newparts)==136
assert {n:re.search(r'\*\*答案\*\*[：:]\s*([A-D]+)',v)[1] for n,v in newparts.items()}==beforekey
# FM can change; every actual question/material/option/image byte remains untouched.
oldfront=prefix[prefix.index('# 2017'):];nf=new[:new.index('## 答案与解析')];assert nf[nf.index('# 2017'):]==oldfront
for n in oldparts:
 if n not in answers:assert oldparts[n]==newparts[n],n
for n in answers:assert oldparts[n] in new
sources=[]
for path in [Path(r'D:\projects\gwy-zhenti\work\qa\ref-上海2017\上海2017行测AB合卷.pdf'),Path(r'D:\projects\gwy-zhenti\work\qa\ref-上海2017\上海2017行测AB合卷-答案解析.pdf'),Path(r'D:\projects\gwy-zhenti\work\qa\sh2017\QPDF.jsonl'),Path(r'D:\projects\gwy-zhenti\work\qa\sh2017\APDF.jsonl')]:sources.append({'path':str(path),'sha256':sha(path.read_bytes()),'role':'用户已有同卷PDF/逐题提取证据；不是新网络原稿'})
report={'status':'prepared','path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'before_text':old,'after_text':new,'repaired_questions':sorted(answers),'records':records,'sources':sources,'arithmetic_checks':plan['arithmetic_checks'],'remaining_source_ambiguities':plan['remaining_source_ambiguities'],'question_material_option_image_bytes_preserved':True,'all_136_answer_keys_preserved':True,'untouched_answers_preserved':True,'all_22_old_answers_retained':True,'boundary':'已修复的是可据现有题面重算的公式与解析，不消除53/71真实题源歧义，也不扩称整卷官方逐字认证。'}
rp=Path('reports/FULL-REPAIR-SHANGHAI2017-FORMULA-20261015.json');assert not rp.exists();rp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp=target.with_name(target.name+'.formula-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());assert target.read_text(encoding='utf-8')==old;os.replace(tmp,target);assert sha(target.read_bytes())==report['after_sha256'];report['status']='passed';rp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('PASSED',len(records),'repaired; all136 keys / actual task bytes preserved; source ambiguities53/71 retained')
