"""Same-paper verification and small source-preserving fixes for Tianjin 2022."""
import hashlib,json,re,sys,unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote
import round5_bulk as parser
from paper_integrity_repair import set_fields
from full_repair_answers_20261015 import validate_answer,render_answer
ROOT=Path(__file__).resolve().parents[1]
M=Path('D:/projects/gwy-material-ops');REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
SOURCE=M/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【26】天津公务员考试真题pdf版/天津公务员考试真题——申论【05-25】'
def sha(t):return hashlib.sha256(t.encode('utf-8')).hexdigest()
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKC',s) if c.isalnum())
def main():
 packets=json.loads((ROOT/'tools/data/tianjin2022-identity-packets-20261015.json').read_text(encoding='utf-8'));by={r['path']:r for r in packets};matches=[];operations=[];sources=[]
 for fragment,canonical in [('区级卷','县级'),('市级卷','市级')]:
  a=by[f'省考/天津/2022/申论-{fragment}.md'];b=by[f'省考/天津/2022/申论-{canonical}.md']
  for n,m in [(1,2),(2,1)]:
   qsim=SequenceMatcher(None,parser.qkey(a['questions'][str(n)]),parser.qkey(b['questions'][str(m)]),autojunk=False).ratio();assert qsim==1
   am=norm(a['materials'][str(n)]);bm=norm(b['materials'][str(m)]);grams={am[i:i+14] for i in range(0,len(am)-14,7)};coverage=sum(g in bm for g in grams)/len(grams);assert coverage>.99
   matches.append({'fragment':a['path'],'fragment_number':n,'canonical':b['path'],'canonical_number':m,'question_identity':qsim,'material_14gram_coverage':coverage,'fragment_question':a['questions'][str(n)],'canonical_question':b['questions'][str(m)]})
 for kind,name in [('区级以下','2022年公务员多省联考《申论》（天津区级卷）题及参考答案.pdf.md'),('市级','2022年公务员多省联考《申论》题（天津市级卷）.pdf.md')]:
  p=SOURCE/name;raw=p.read_text(encoding='utf-8');url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(p.relative_to(M).as_posix(),safe='/');sources.append({'kind':kind,'path':p.relative_to(M).as_posix(),'url':url,'sha256':sha(raw),'author':'题本未明确编制机构／作者','note':'市级PDF为OCR转录，存在已知漏字，未用其低质量转录替换现有较完整材料。' if kind=='市级' else '完整题本三段材料规范化后与现县级文件逐字相同。'})
 edits=[('县级','综合管理类区级以下机关','区级以下','''一、改善人居环境。完善公共设施，集中清理垃圾，实行收运市场化，建设污水垃圾处理设施，成立保洁办公室，推进改厕和长效管护。
二、壮大产业增收。探索党支部、龙头企业、合作社联动，入股分红、订单种养，发展特色养殖与加工，提供技术、销售和就业支持。
三、培育文明乡风。传播家风家训，修订村规民约，组织返乡大学生挖掘村史乡俗，建设村史馆，发挥乡贤建言出资作用。'''),('市级','综合管理类市级机关','市级','''一、明确服务内容，确定课业辅导、体育锻炼、素质拓展板块，学校结合实际落实。
二、按需提供项目，依据学生身心特点制定清单、自主报名，邀请体校教练志愿服务。
三、分时段看护，衔接班级、年级和校级服务，兼顾少数家庭需求。
四、注重心理健康，开设情绪管理课程，对校内教师开展针对性培训。
五、关爱服务教师，落实补贴、弹性上下班，引入有资质机构分担工作；探索跨校假期托管。''')]
 for filename,variant,kind,answer in edits:
  rel=f'省考/天津/2022/申论-{filename}.md';p=ROOT/rel;old=p.read_text(encoding='utf-8');entry={'answer':answer,'attribution_kind':'ai_revision','author':'Codex（AI辅助修订示范）','sources':[{'title':'用户资料库同卷完整题本','url':next(s['url'] for s in sources if s['kind']==kind)}]};d=parser.parse(old,rel);count=validate_answer(d['questions'][1],entry)
  new=set_fields(old,{'卷型':variant,'卷型校核凭据':'reports/FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json'},'2026-10-15依同年同卷完整题本与当年大纲核对三题原卷身份；两个两题片段是重复来源，非新增分卷。')
  new=re.sub(r'(?m)^# [^\n]+',f'# 2022年天津市公务员考试申论（{variant}）',new,count=1)
  notice='\n> **卷型校勘：** 2022年应使用当年分类“综合管理类市级机关／综合管理类区级以下机关／行政执法”，不能倒套2023年后的市区／街镇类名。本卷三段材料、三道题及20／30／50分结构与同年同卷完整题本一致。历史文件名兼容保留；重复片段及逐题映射见 `reports/FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json`。\n'
  title=re.search(r'(?m)^# [^\n]+\n',new);new=new[:title.end()]+notice+new[title.end():]
  pat=re.compile(r'(<summary>第\s*1\s*题</summary>)(.*?)(</details>)',re.S);m=pat.search(new);assert m;new=new[:m.start(2)]+'\n\n'+render_answer(entry)+'\n\n'+new[m.end(2):]
  if filename=='县级':
   new=new.replace('不超过200字。、','不超过200字。').replace('创新乡村治理 促进和谐发展乡村治，','创新乡村治理 促进和谐发展\n\n乡村治，')
  nd=parser.parse(new,rel);assert {n:parser.qkey(q) for n,q in d['questions'].items()}=={n:parser.qkey(q) for n,q in nd['questions'].items()};assert len(nd['questions'])==len(nd['answers'])==3
  p.write_text(new,encoding='utf-8');operations.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'before_text':old,'after_text':new,'answer1_characters':count,'preserved_materials':True,'preserved_other_answers_except_title_linebreak':True})
 for variant in ['区级卷','市级卷']:
  rel=f'省考/天津/2022/申论-{variant}.md';p=ROOT/rel;old=p.read_text(encoding='utf-8');new=set_fields(old,{'收录状态':'同年同卷两题片段，非另一独立卷','身份校核凭据':'reports/FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json'},'2026-10-15完整题本确认本文件仅为三题原卷中的第2、1题倒序片段；等待统一来源归档。')
  target='申论-县级.md' if variant=='区级卷' else '申论-市级.md';notice=f'\n> **重复来源片段，非完整原卷。** 此文件只含同年同卷第2、1题的倒序收录，缺第3题作文及其材料；完整原卷已有[三题完整稿]({target})。本片段全部原文和旧作答保留，不能计作另一套独立试卷。\n';m=re.search(r'(?m)^# [^\n]+\n',new);new=new[:m.end()]+notice+new[m.end():];p.write_text(new,encoding='utf-8');operations.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'before_text':old,'after_text':new,'action':'duplicate_partial_notice'})
 report={'status':'passed','original_current_files':4,'confirmed_distinct_papers':2,'two_question_fragments':2,'same_question_mappings':matches,'source_papers':sources,'evidence':[{'title':'当年大纲解读','url':'http://www.tjgwyw.org/2022/0224/38404.html','supports':'2022分综合管理市级、综合管理区级以下、行政执法；未按后续市区/街镇改名'},{'title':'中公2019–2023天津考情简析','url':'https://www.eoffcn.com/kszx/detail/1275187.html','supports':'2022受疫情影响，三类卷题量都改为3道'}],'remaining':'已证2022存在行政执法类命题，但本次仍未取得可靠完整原卷，不能将现四文件任意一份改名充数。','recommended_relocations':{'省考/天津/2022/申论-区级卷.md':'docs/来源校勘/天津2022申论-原区级卷两题重复片段.md','省考/天津/2022/申论-市级卷.md':'docs/来源校勘/天津2022申论-原市级卷两题重复片段.md'},'operations':operations}
 (ROOT/'reports/FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('4 files checked: 2 complete three-task papers, 2 duplicate fragments; two over-limit short answers revised.')
if __name__=='__main__':main()
