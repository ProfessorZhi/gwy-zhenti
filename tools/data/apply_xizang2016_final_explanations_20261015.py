"""Finish 20 evidenced Xizang2016 explanations after the paper owner's freeze."""
import sys,re,json,hashlib,os,uuid,copy
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,'tools');from paper_integrity_repair import set_fields
R=Path('.');rel='省考/西藏/2016/行测-统考.md';path=R/rel;old_bytes=path.read_bytes();old=old_bytes.decode('utf-8');sha=lambda x:hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest();assert sha(old_bytes)=='c676a2c277b66ba07547a276f50fe78aa4580d04865d30f3e6be186cf5248ccc',('Concurrent edit',sha(old_bytes))
D=json.loads(Path('tools/data/xizang2016-reviewed-independent-explanations-20261015.json').read_text(encoding='utf-8'));ai={int(k):v for k,v in D['answers'].items()};donors={59:('省考/云南/2016/行测-统考.md',64),61:('省考/新疆/2016/行测-兵团.md',56),64:('省考/云南/2016/行测-统考.md',67),106:('省考/云南/2016/行测-统考.md',114),114:('省考/云南/2016/行测-统考.md',110),116:('省考/四川/2016/行测-统考.md',96),117:('省考/四川/2016/行测-统考.md',97)}
assert len(set(ai)|set(donors))==20
# Separate, precisely authorized pagination cleanup. No real option value changes.
page=old;page_records=[]
for a,b in [('国有企业应交税金占同期营业总收入的一成以上 13','国有企业应交税金占同期营业总收入的一成以上'),('2015年4月全国租赁贸易进出口额比2013年4月翻了一番 15','2015年4月全国租赁贸易进出口额比2013年4月翻了一番'),('表中全国租赁贸易进出口额同比下降的月份占总数的三分之一 16','表中全国租赁贸易进出口额同比下降的月份占总数的三分之一')]:
 assert page.count(a)==1,(a,page.count(a));page=page.replace(a,b,1);page_records.append({'before':a,'after':b,'evidence':'MOPS原页脚13/15/16误粘；根agent以政华同题PDF页25-B、26-A/D逐项确认无这些尾号，并明确授权只删孤立页码'})
pattern=re.compile(r'(<details>\s*<summary>第\s*(\d+)\s*题</summary>)(.*?)(</details>)',re.S);parts={int(m[2]):m[3].strip() for m in pattern.finditer(page)};assert len(parts)==125
keys={n:re.search(r'\*\*答案\*\*[：:]\s*([ABCD]+)',v)[1] for n,v in parts.items()};records=[];source_data={};BASE='f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab'
for n,(source,number) in donors.items():
 raw=Path(source).read_text(encoding='utf-8');m=next(x for x in pattern.finditer(raw) if int(x[2])==number);whole=m[3].strip();key=re.search(r'\*\*答案\*\*[：:]\s*([ABCD]+)',whole)[1];assert key==keys[n],(n,key,keys[n]);url='https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+quote(source,safe='/');source_data[n]={'path':source,'number':number,'sha256':sha(raw),'source_url':url,'source_answer':whole,'answer_key':key}

def sub(m):
 n=int(m[2]);key=keys[n]
 if n not in ai and n not in donors:return m[0]
 if n in donors:
  src=source_data[n];body=src['source_answer'];body+='\n\n> 来源说明：从本库固定版本的同年联考同题完整参考解析迁入；原稿未署个人作者，不推定为考试机关标准解析。题干实际条件、选项内容及顺序和本题对应，保留原参考文字及公式图。不是官方答案，未经实考评分；原缺式稿另留校勘对照。\n\n[同年同题完整来源（'+str(src['number'])+'题）]('+src['source_url']+')'
  if n==117:body+='\n\n> 独立核算补记（AI辅助复核）：820×23.4÷0.976≈19659.84件，即约1.966万件，与A项1.96万最接近；此前缺式稿中“2.3万”是错文，旧稿保留不作为现行推导。'
  record={'number':n,'kind':'existing_same_question_source','source':src}
 else:
  body='**答案**：'+key+'\n\n**AI辅助修订解析**\n\n'+ai[n]+'\n\n> 来源说明：依据本卷原题条件、完整共享资料及实际原图独立计算，作者／整理性质为AI辅助修订；不是原机构作者原文，不是官方答案，未经实考评分。原参考稿与完整修复前文本存于独立凭据及下方旧稿对照。'
  record={'number':n,'kind':'ai_revision','explanation':ai[n],'basis':'本卷同题给定条件/原表原图，交叉来源候选另存tools/data/xizang2016-complete-explanation-candidates-20261015.json'}
 record.update(answer_key=key,before_answer=parts[n],before_answer_sha256=sha(parts[n]),after_answer_sha256=sha(body));records.append(record)
 return m[1]+'\n\n'+body+'\n\n'+m[4]
new=pattern.sub(sub,page);new+='\n\n## 解析补式与断尾修复前版本\n\n以下为原收录稿，仅供来源、版本和计算校勘；当前解析以各题上方完整版本为准。\n'
for n in sorted(set(ai)|set(donors)):new+='\n<details>\n<summary>展开此前第'+str(n)+'题解析（历史校勘）</summary>\n\n'+parts[n]+'\n\n</details>\n'
new=set_fields(new,{'解析公式修复题号':sorted(set(ai)|set(donors)),'解析公式修复凭据':'reports/FULL-REPAIR-TIBET2016-FINAL-EXPLANATIONS-20261015.json','解析公式核验状态':'20处实际缺式/断尾已补：7处复用同题完整参考（含原公式图），13处明确AI修订；119现有增速比较法完整，未重复改写；117错写2.3万已据原表核正。'},'2026-10-15补全20题解析公式及断尾，原125参考键保持；明确区分同题来源迁入与AI修订，保留全部旧解析；只清除已证的3个选项页脚尾号，不改真实题干条件或选项数值。');new=new.rstrip()+'\n'
np={int(m[2]):m[3].strip() for m in pattern.finditer(new)};assert len(np)==125
assert {n:re.search(r'\*\*答案\*\*[：:]\s*([ABCD]+)',v)[1] for n,v in np.items()}==keys
actual_front=page[:page.index('## 答案与解析')];newfront=new[:new.index('## 答案与解析')];assert actual_front[actual_front.index('# '):]==newfront[newfront.index('# '):]
for n,v in parts.items():
 if n not in ai and n not in donors:assert np[n]==v,n
 else:assert v in new
# Resolve every newly migrated reference; every image must already be present and decodable.
from PIL import Image,ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES=False;images=[]
for n in donors:
 for src in re.findall(r'src="([^"]+)"',np[n]):
  f=(path.parent/src).resolve();assert f.is_file(),f
  with Image.open(f) as im:
   for frame in range(getattr(im,'n_frames',1)):im.seek(frame);im.load()
  images.append({'question':n,'path':f.relative_to(R.resolve()).as_posix(),'sha256':sha(f.read_bytes())})
report={'status':'prepared','path':rel,'before_sha256':sha(old_bytes),'before_text':old,'pagination_step':{'before_sha256':sha(old),'after_sha256':sha(page),'changes':page_records},'explanation_step':{'before_sha256':sha(page),'after_sha256':sha(new),'repaired_questions':sorted(set(ai)|set(donors)),'existing_source_count':7,'ai_revision_count':13},'after_sha256':sha(new),'after_text':new,'records':records,'independent_calculations':D['independent_calculations'],'question119_review':D['already_complete_question_119'],'migrated_image_references':images,'all125_answer_keys_preserved':True,'all_other_actual_question_option_material_image_bytes_preserved':True,'all20_previous_answers_retained':True,'boundary':'依原题条件和真实原表补足公式；来源迁入保持原署名性质未知；化学85只按题干简化定义作答，不冒称完整热力学判据。未将125键齐备本身当成解析完整证明。'}
rp=Path('reports/FULL-REPAIR-TIBET2016-FINAL-EXPLANATIONS-20261015.json');assert not rp.exists();rp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp=path.with_name(path.name+'.explanation-'+uuid.uuid4().hex+'.tmp');temp.write_bytes(new.encode());assert path.read_bytes()==old_bytes;os.replace(temp,path);assert sha(path.read_bytes())==report['after_sha256'];report['status']='passed';rp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('PASSED 20 explanations / 3 proved pagination tails;',len(images),'migrated existing formula/image references decoded; SHA',report['after_sha256'])
