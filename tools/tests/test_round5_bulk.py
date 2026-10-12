import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import round5_bulk as b
from round5_delivery import render,body_text
from verify_round5_repairs import reverse
import round4_gap_repair as g

class BulkTests(unittest.TestCase):
 def fixture(self):
  t='---\n地区: "浙江"\n年份: 2020\n科目: "申论"\n卷型: "A类"\n校验状态: "待核"\n---\n\n# 试卷\n\n## 给定资料 1\n\n'+('材料包含公共服务建设和社区治理的具体事实。'*20)+'\n\n## 第 1 题\n\n请根据给定资料1概括社区服务治理的具体做法。（100分）\n\n要求：不超过200字。\n\n## 答案与解析\n\n<details>\n<summary>第 1 题</summary>\n\n未收录同卷同题可靠参考答案。\n\n</details>\n'
  return b.parse(t,'省考/浙江/2020/申论-test.md')
 def addition(self,t):
  return {'number':1,'answer':'一、完善服务设施，明确社区服务职责。二、加强基层队伍建设，定期培训工作人员。三、畅通群众反馈渠道，实行问题闭环处理。四、建立长效工作机制，加强对服务质量的监督。','kind':'repository_same_question','source_variant':'A类','source_url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+b.BASE+'/source.md','target_question_sha256':g.digest(t['questions'][1])}
 def test_equivalent_glyphs(self):self.assertEqual(b.norm('⺠⻔⻛⻓⻅⻆'),b.norm('民门风长见角'))
 def test_original_glyph_not_rewritten(self):self.assertEqual('⻛','⻛')
 def test_question_label_normalization(self):self.assertEqual(b.qkey('问题一：请概括给定资料1的主要内容。（20分）要求：'),b.qkey('（一）请概括给定资料2的主要内容。（20分）要求：'))
 def test_distinct_stems_not_equal(self):self.assertNotEqual(b.qkey('请分析农业发展的主要困难'),b.qkey('请分析工业发展的主要困难'))
 def test_addition_preserves_body(self):
  t=self.fixture();new,r=render(t,[self.addition(t)]);self.assertEqual(body_text(t['text']),body_text(new));self.assertEqual(reverse(new,r),t['text'])
 def test_stale_hash_rejected(self):
  t=self.fixture();a=self.addition(t);a['target_question_sha256']='0'*64
  with self.assertRaises(ValueError):render(t,[a])
 def test_existing_answer_not_overwritten(self):
  t=self.fixture();t['answers'][1]='已经收录的真实答案内容。'
  with self.assertRaises(ValueError):render(t,[self.addition(t)])
 def test_duplicate_addition_rejected(self):
  t=self.fixture();a=self.addition(t)
  with self.assertRaises(ValueError):render(t,[a,a])
 def test_incomplete_answer_rejected(self):
  t=self.fixture();a=self.addition(t);a['answer']='暂缺'
  with self.assertRaises(ValueError):render(t,[a])
 def test_changed_delivery_rejected(self):
  t=self.fixture();new,r=render(t,[self.addition(t)])
  with self.assertRaises(ValueError):reverse(new+'修改',r)
 def test_changed_receipt_rejected(self):
  t=self.fixture();new,r=render(t,[self.addition(t)]);r['before_sha256']='0'*64
  with self.assertRaises(ValueError):reverse(new,r)
 def test_fullwidth_numeric_normalization(self):self.assertEqual(b.norm('２０２４'),b.norm('2024'))

if __name__=='__main__':unittest.main()
