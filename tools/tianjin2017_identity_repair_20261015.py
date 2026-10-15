"""Confirm the Binhai special recruitment without altering original tasks or answers."""
import hashlib,json,re
from pathlib import Path
import round5_bulk as parser
from paper_integrity_repair import set_fields
from full_repair_answers_20261015 import validate_answer
ROOT=Path(__file__).resolve().parents[1]
def sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def main():
 evidence=json.loads((ROOT/'tools/data/tianjin2017-source-comparison-20261015.json').read_text(encoding='utf-8'));rel=evidence['path'];p=ROOT/rel;old=p.read_text(encoding='utf-8');d=parser.parse(old,rel)
 assert all(r['exact_norm_equal'] for r in evidence['material_exact_checks'])
 assert all(r['html_full_question_found'] and r['pdf_full_question_found'] for r in evidence['question_exact_checks'])
 assert len(d['questions'])==len(d['answers'])==4
 counts=[]
 for n,a in d['answers'].items():
  m=re.search(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',a,re.S);assert m,n
  counts.append({'number':n,'answer_characters':validate_answer(d['questions'][n],{'answer':m[1],'attribution_kind':'ai_original','author':'原库署名保留'})})
 new=set_fields(old,{'卷型':'滨海新区等单位专项','考试日期':'2017-12-23','命题形式':'专项招考，非4月常规联考','真题性质':'专项考试公开整理真题，非官方公布原件','身份核实状态':'已核实：六材料、四题题干分值要求均与公开网页及PDF同题；同期大纲与公告确认专项身份','身份核实凭据':'reports/FULL-REPAIR-TIANJIN-2017-BINHAI-IDENTITY-20261015.json'},'2026-10-15依据同题完整公开PDF和同期专项招考文件解除身份待核，保留旧文件名供兼容；全部原材料、题目、示范作答保持。')
 new=re.sub(r'(?m)^# [^\n]+','# 2017年天津市滨海新区等单位公开招考公务员申论（12月23日专项）',new,count=1)
 notice='\n> **试卷身份已核实：滨海新区等单位专项招考。** 本卷属于2017年12月23日另行招考，不是当年4月常规联考。原文件名 `申论-统考__t443.md` 兼容保留。六段材料规范化后与[公开整理全文](http://www.tjgwyw.org/2018/1220/24369.html)及[同题PDF](http://download.tjgwyw.org/20180411145819_14866.pdf)逐字相同，四题题干、分值和要求全部对应；[同期大纲转载](https://www.eol.cn/gongwuyuan/difang/skzx/201711/t20171127_1569596.shtml)与[招考公告转载](http://banyuetanedu.com/a/tjsk/zpxx/zkgg/42.html)交叉确认考试身份。题本为网络公开整理，编制者未明确，未宣称官方公布原件；完整核实证据见 `reports/FULL-REPAIR-TIANJIN-2017-BINHAI-IDENTITY-20261015.json`。\n'
 title=re.search(r'(?m)^# [^\n]+\n',new);new=new[:title.end()]+notice+new[title.end():]
 nd=parser.parse(new,rel);assert nd['questions']==d['questions'];assert nd['answers']==d['answers'];assert old[old.index('材料一'):old.index('作答要求',old.index('材料一'))]==new[new.index('材料一'):new.index('作答要求',new.index('材料一'))]
 p.write_text(new,encoding='utf-8')
 receipt={'status':'passed','path':rel,'resolved_identity':'2017-12-23滨海新区等单位专项招考','ordinary_april_exam':'独立于4月常规天津联考；不能相互替代或混称','material_normalized_characters':len(evidence['normalized_material']),'evidence':evidence,'before_sha256':sha(old),'after_sha256':sha(new),'before_text':old,'after_text':new,'answers_checked':counts,'preservation':{'materials_exactly_unchanged':True,'questions_exactly_unchanged':True,'answers_exactly_unchanged':True},'missing_tasks':0}
 (ROOT/'reports/FULL-REPAIR-TIANJIN-2017-BINHAI-IDENTITY-20261015.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('Identity confirmed; 6 materials and 4 questions/answers unchanged:',counts)
if __name__=='__main__':main()
