"""Restore explicitly identified Shanghai historical full papers; leave old buckets."""
import json,re,sys,os,uuid,hashlib
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
sha=lambda t:hashlib.sha256(t.encode('utf8')).hexdigest()
ds=json.loads((ROOT/'tools/data/shanghai-b-full-source-packets-a-20261015.json').read_text(encoding='utf8'))
receipts=[]
for d in ds:
 year=d['year'];variant=d['variant']
 if year==2022:continue
 p=ROOT/d['path'];old=p.read_text(encoding='utf8') if p.exists() else None
 if year<2023:assert old is None,d['path']
 else:assert old is not None,d['path']
 url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(d['source_relative_path'],safe='/')
 text='---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in {
 '考试':'省考','地区':'上海','年份':str(year),'科目':'申论','卷型':variant+'类','真题性质':'机构整理/考生回忆真题，非官方原件','命题形式':'单独命题','来源':['用户已有完整原始资料'],'来源整卷':url,'来源整卷SHA256':d['source_sha256'],'实有题数':4,'对照题本题量':4,'缺失原题号':[],'给定材料段数':len(d['materials']),'题目分值':[15,20,15,50] if year==2023 else [20,20,20,40],'已收录参考答案题号':[1,2,3,4],'缺参考答案题号':[],'题号口径':'完整同年分卷作答要求顺序；与旧统考桶逐题映射','校验状态':'2026-10-15依据已有完整原稿恢复材料与4题；参考正文独立计字，旧桶保留供归档；非官方逐字认证','恢复凭据':'reports/FULL-REPAIR-SHANGHAI-HISTORICAL-A-20261015.jsonl'}.items())+'---\n# '+str(year)+'年上海市公务员考试申论（'+variant+'类）\n\n'
 text+='> 本卷依据用户已有同年同卷完整原稿整理；题面、机构参考版本及本次AI修订分别注明，不认作官方标准答案或实考高分答卷。\n\n[原始资料（固定版本）]('+url+')\n\n'
 if d['instructions']:text+='## 考试注意事项\n\n'+d['instructions']+'\n\n'
 if d['unnumbered_intro']:text+='## 总括资料\n\n'+d['unnumbered_intro']+'\n\n'
 for m in d['materials']:text+='## 给定资料 '+str(m['number'])+'\n\n'+m['text']+'\n\n'
 text+='## 作答要求\n\n'
 for n,q in d['questions'].items():text+='## 第 '+str(n)+' 题\n\n'+q+'\n\n'
 text+='## 答案与解析\n\n';metrics=[]
 for ns,q in d['questions'].items():
  n=int(ns);a=d['source_answers'][ns];kind='owned_source';reason=None
  a=a.replace('运用新兴科技，创新城市治理大力发展','运用新兴科技，创新城市治理\n\n大力发展').replace('聚力放管服涵养城市温度从匪夷所思','聚力放管服 涵养城市温度\n\n从匪夷所思').replace('加强基层治理，推进中国式现代化——推进党建引领基层治理习近平总书记','加强基层治理，推进中国式现代化\n——推进党建引领基层治理\n\n习近平总书记')
  if (year,n)==(2019,3):a=a.replace('加强市场化运作','强化市场运作');kind='ai_revision';reason='原来源正文301字，压缩冗词，保留五方面经验。'
  if (year,n)==(2019,4):
   a=a.replace('培育契约精神打造海纳百川的城市文化上海','培育契约精神 打造海纳百川的城市文化\n\n上海').replace('敢穿敢拼','敢闯敢拼').replace('各家各自尊重与坚守','各方尊重与坚守')
   a=a.replace('这种法律制度，不等同于专制集权的封建社会，偏重于强制性和惩罚性。而是在现代商业精神和工业革命相联系的法律制度，在平等自愿的基础上，各方有所约束。','在法治框架下，坚持平等自愿、诚实守信，明确各方权利义务，才能让社会交往既有自由也有边界。')
   a=a.replace('林则徐曾说：“海纳百川，有容乃大。”现在的上海市已经形成了这种开放包容的城市精神，但如何能让这种精神走的长远、走的坚定。我想，卢梭的话给出了最中肯答案——人生而自由，却无往不在枷锁之中。城市精神的发展也需要这个“枷锁”，这种契约的精神。','海纳百川，有容乃大。让守约成为习惯，让规则保障包容，开放的城市才能在有序交往中不断汇聚创造活力，使海纳百川的精神行稳致远。')
   kind='ai_revision';reason='原参考正文1043字超800—1000要求，去重复论述，修订自由与规则的表达，校正明显错字；题干漏“百川”等据同年厚职完整题面校勘。'
  if (year,n)==(2020,3):a=a.replace('“四度”指明了上海创新发展的目标与方向。','“四度”指上海创新发展的目标与方向。');kind='ai_revision';reason='原参考正文302字，精简开头，四项内涵保持。'
  if (year,n)==(2021,1):a=a.replace('金融危机极其罕见，无法预测，需足够了解，加强重视。','风险复杂、难预测，须提高防范意识。');kind='ai_revision';reason='原参考正文306字，精炼风险防范表述，不把危机概括为绝对无法预测。'
  author='原资料未署名；本次仅作出版页码与段落校勘'
  if year==2021:author='原资料仅以F标识本参考版本，未披露作者全名或所属机构'
  if kind=='ai_revision':author='AI辅助修订示范；原参考稿作者未署名'
  e=dict(answer=a,attribution_kind=kind,author=author,sources=[dict(title='修订所据原稿（固定版本）' if kind=='ai_revision' else '用户已有同题参考资料（固定版本）',url=url)])
  if reason:e['replace_reason']=reason+'；原稿完整保存于源包及源SHA凭据。'
  count=validate_answer(q,e);metrics.append(dict(number=n,characters=count,kind=kind,answer_sha256=sha(a)))
  text+='<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+render_answer(e)+'\n\n</details>\n\n'
 text=text.replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷')
 if year==2019:text+='> 题面校勘：原资料“海纳”漏字、“语音流程”等提取错误，按同年同卷[厚职全文](http://www.houzhiwang.com/html/201910/2344.html)及旧桶同题题干恢复“海纳百川”“语言流畅”；材料3标题从上一段末分离。\n'
 if year==2023:text+='> 资料编号说明：原稿总括资料不另编号，随后材料1—5及题干引用保持。旧“统考”唯一作文与本卷第4题对应，不能因此当作B卷。\n'
 text,layout=format_essay(text,d['path']);nd=b.parse(text,d['path']);assert len(nd['questions'])==4 and len(nd['answers'])==4
 temp=p.with_name(p.name+'.full-'+uuid.uuid4().hex+'.tmp');temp.write_bytes(text.encode('utf8'))
 if old is None:assert not p.exists(),d['path']
 else:assert sha(p.read_text(encoding='utf8'))==sha(old),d['path']
 os.replace(temp,p);assert sha(p.read_text(encoding='utf8'))==sha(text)
 receipts.append(dict(path=d['path'],source_path=d['source_path'],source_revision=REV,source_sha256=d['source_sha256'],before_sha256=sha(old) if old else None,before_text=old,after_sha256=sha(text),materials=len(d['materials']),unnumbered_intro=bool(d['unnumbered_intro']),questions=4,answers=metrics,bucket_matching_tasks=d['bucket_matching_tasks'],old_bucket_preserved=True,layout=layout,cleaning=d['cleaning']))
 print(d['path'],len(d['materials']),metrics)
rp=ROOT/'reports/FULL-REPAIR-SHANGHAI-HISTORICAL-A-20261015.jsonl';previous=rp.read_text(encoding='utf8') if rp.exists() else '';rp.write_text(previous+''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in receipts),encoding='utf8')
