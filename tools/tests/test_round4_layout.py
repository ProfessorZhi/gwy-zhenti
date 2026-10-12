import unittest
from test_round4_answers import paper,addition,MATERIAL,QUESTION
import round4_gap_repair as g
import round4_delivery as d
from verify_round4_repairs import reverse

class Round4LayoutTests(unittest.TestCase):
 def test_indented_unstructured_body_is_identical(self):
  prefix=paper().split('## 第 1 题')[0]
  q1='问题一：'+QUESTION.replace('100分','50分')
  q2='问题二：请根据给定资料，提出推动当地企业创新发展的建议。（50分）\n\n要求：全面准确，不超过300字。'
  old=prefix+'二、作答要求\n\n　　'+q1+'\n\n　　'+q2+'\n'
  p=g.parse_text(old,'x.md');self.assertEqual(p['mode'],'unstructured');self.assertEqual(len(p['questions']),2)
  a=addition(p);new=d.add_proved_answers(p,[a]);r=d.receipt(old,new,p,[a])
  self.assertEqual(d.body_without_inserted_headers(old,p['mode']),d.body_without_inserted_headers(new,p['mode']))
  self.assertEqual(reverse(new,r),old)
  self.assertEqual(r['remaining_answer_ids'],[2])
 def test_global_material_is_not_empty(self):
  text=paper().replace('## 第 1 题\n\n','## 第 1 题\n\n### 作答要求\n\n')
  p=g.parse_text(text,'x.md')
  self.assertIn(MATERIAL,p['materials'][1])
  self.assertNotIn('### 作答要求',p['questions'][1])
if __name__=='__main__':unittest.main()
