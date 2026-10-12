import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import round4_gap_repair as g
import round4_delivery as d
from verify_round4_repairs import reverse

MATERIAL='某县深入调研产业发展的困难，建立人才培养机制，改善办事服务并完善基础设施。企业通过技术创新和合作逐步提高产品质量，群众积极参与市场经营。'+''.join(str(i)+'产业发展必须坚持质量提升和协同创新。' for i in range(20))
QUESTION='根据给定资料1，概括某县推进产业发展的主要做法。（100分）\n\n要求：全面准确，不超过300字。'
ANSWER='一、深入开展调查研究，了解企业和群众的困难。二、完善人才培养和公共服务，健全基础设施。三、支持技术创新和企业合作，不断提高产品质量。四、鼓励群众参与，形成多方协同发展的格局。'
def paper(answer='未收录同题参考答案。',heading='答案与解析'):
 return '---\n考试: "省考"\n地区: "测试"\n年份: 2024\n科目: "申论"\n卷型: "A类"\n---\n\n# 测试卷\n\n## 给定资料 1\n\n'+MATERIAL+'\n\n## 第 1 题\n\n'+QUESTION+'\n\n## '+heading+'\n\n<details>\n<summary>第 1 题</summary>\n\n'+answer+'\n\n</details>\n'
def addition(t):
 return {'number':1,'kind':'repository_same_question','answer':ANSWER,'target_question_sha256':g.digest(t['questions'][1]),'source_variant':'A类','source_url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+g.BASE+'/example.md','donor_path':'example.md','donor_number':1}
class Round4Tests(unittest.TestCase):
 def test_known_placeholder(self):self.assertTrue(d.is_missing('本题参考答案尚未核实收录，不以空白或默认选项冒充答案。'))
 def test_real_answer_not_missing(self):self.assertFalse(d.is_missing(ANSWER))
 def test_alias_not_missing(self):self.assertEqual(g.parse_text(paper(ANSWER,'参考答案'),'x.md')['missing'],[])
 def test_duplicate_answer_rejected(self):
  x=paper().replace('</details>','</details>\n<details><summary>第 1 题</summary>xx</details>')
  with self.assertRaises(ValueError):g.parse_text(x,'x.md')
 def test_answer_overwrite_rejected(self):
  t=g.parse_text(paper(ANSWER),'x.md')
  with self.assertRaises(ValueError):d.add_proved_answers(t,[addition(t)])
 def test_answer_patch_preserves_body(self):
  t=g.parse_text(paper(),'x.md');new=d.add_proved_answers(t,[addition(t)])
  self.assertEqual(d.body_without_inserted_headers(new,'details'),d.body_without_inserted_headers(t['text'],'details'))
 def test_reversible(self):
  t=g.parse_text(paper(),'x.md');a=addition(t);new=d.add_proved_answers(t,[a]);r=d.receipt(t['text'],new,t,[a]);self.assertEqual(reverse(new,r),t['text'])
 def test_mutated_delivery_rejected(self):
  t=g.parse_text(paper(),'x.md');a=addition(t);new=d.add_proved_answers(t,[a]);r=d.receipt(t['text'],new,t,[a])
  with self.assertRaises(ValueError):reverse(new+'bad',r)
 def test_material_mutation_rejected(self):
  t=g.parse_text(paper(),'x.md');a=addition(t);new=d.add_proved_answers(t,[a]).replace('某县深入调研','某县忽视调研')
  with self.assertRaises(ValueError):d.receipt(t['text'],new,t,[a])
 def test_stale_question_hash_rejected(self):
  t=g.parse_text(paper(),'x.md');a=addition(t);a['target_question_sha256']='0'*64
  with self.assertRaises(ValueError):d.add_proved_answers(t,[a])
 def test_missing_material_proof_rejected(self):
  a=g.parse_text(paper(),'a.md');b=g.parse_text(paper(ANSWER).replace(MATERIAL,'另一个完全无关的材料。'),'b.md')
  self.assertIsNone(g.match(a,1,[(b,1)])[0])
 def test_matching_existing_source(self):
  a=g.parse_text(paper(),'a.md');b=g.parse_text(paper(ANSWER),'b.md');self.assertIsNotNone(g.match(a,1,[(b,1)])[0])
 def test_wrong_word_limit_rejected(self):
  a=g.parse_text(paper(),'a.md');b=g.parse_text(paper(ANSWER).replace('300字','500字'),'b.md');self.assertIsNone(g.match(a,1,[(b,1)])[0])
 def test_conflicting_answers_rejected(self):
  a=g.parse_text(paper(),'a.md');b=g.parse_text(paper(ANSWER),'b.md');c=g.parse_text(paper(ANSWER+'补充另一种不同的解释。'),'c.md')
  self.assertEqual(g.match(a,1,[(b,1),(c,1)])[1],'conflicting_supported_answers')
 def test_unrecognized_answer_layout_rejected(self):
  with self.assertRaises(ValueError):g.parse_text(paper().replace('<details>','').replace('</details>',''),'x.md')
 def test_operation_roundtrip(self):
  for a,b in [('abc\ndef\n','xyz\nabc\ndef\n'),('x\ny\n','x\nz\n'),('a\n','a\nmore')]:
   r={'path':'x','before_sha256':g.digest(a),'after_sha256':g.digest(b),'operations':d.operations(a,b)};self.assertEqual(reverse(b,r),a)
if __name__=='__main__':unittest.main()
