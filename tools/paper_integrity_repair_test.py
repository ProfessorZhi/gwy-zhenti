import unittest
from paper_identity import reference_number_issues
from paper_integrity_repair import validate_plan

class OriginalNumberTests(unittest.TestCase):
 def test_internally_consecutive_is_not_enough(self):
  self.assertIn('原题号与已声明缺口不一致',reference_number_issues([1,2,3],{'对照题本题量':4,'缺失原题号':[]}))
 def test_explicit_missing_is_reported(self):
  self.assertEqual(reference_number_issues([1,2,4],{'对照题本题量':4,'缺失原题号':[3],'实有题数':3}),['已确认仍缺原题号：3'])
 def test_complete(self):self.assertEqual(reference_number_issues([1,2],{'对照题本题量':2,'缺失原题号':[]}),[])
 def test_mismatch_gap(self):self.assertTrue(reference_number_issues([1,2,3],{'对照题本题量':4,'缺失原题号':[2]}))
 def test_missing_duplicate(self):self.assertTrue(reference_number_issues([1,2],{'对照题本题量':4,'缺失原题号':[3,3]}))
 def test_out_of_order(self):self.assertTrue(reference_number_issues([2,1],{'对照题本题量':2,'缺失原题号':[]}))
 def test_invalid_missing(self):self.assertTrue(reference_number_issues([1],{'对照题本题量':2,'缺失原题号':'2'}))
 def test_no_expected_preserves_old_warning(self):self.assertTrue(reference_number_issues([1,3],{}))

class PlanTests(unittest.TestCase):
 def setup_plan(self):
  old={'qs':{1:{},2:{}}}
  spec={'path':'国考/2022/行测-副省级.md','old_to_source':{'1':2,'2':1},'additions':[],'expected_questions':2,'missing_original_numbers':[]}
  return spec,old
 def test_unique_mapping(self):
  s,o=self.setup_plan();self.assertEqual(validate_plan(s,o)[0],{1:2,2:1})
 def test_duplicate_mapping_rejected(self):
  s,o=self.setup_plan();s['old_to_source']['1']=1
  with self.assertRaises(ValueError):validate_plan(s,o)
 def test_omitted_id_rejected(self):
  s,o=self.setup_plan();s['expected_questions']=3
  with self.assertRaises(ValueError):validate_plan(s,o)
 def test_wrong_scope_rejected(self):
  s,o=self.setup_plan();s['path']='省考/其他/2020/行测-统考.md'
  with self.assertRaises(ValueError):validate_plan(s,o)
 def test_source_placeholder_rejected(self):
  s,o=self.setup_plan();s['expected_questions']=3;s['additions']=[{'number':3,'stem':'题目正在征集','options':['a','b','c','d'],'answer':'A'}]
  with self.assertRaises(ValueError):validate_plan(s,o)
 def test_empty_option_rejected(self):
  s,o=self.setup_plan();s['expected_questions']=3;s['additions']=[{'number':3,'stem':'known','options':['a','b','c',''],'answer':'A'}]
  with self.assertRaises(ValueError):validate_plan(s,o)

if __name__=='__main__':unittest.main()
