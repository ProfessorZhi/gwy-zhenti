import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('fenbi_full', Path(__file__).parents[1]/'driver/fenbi-full.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FullPaperTests(unittest.TestCase):
    def setUp(self):
        self.paper = {'name':'测试卷','solutions':[
            {'globalId':'q2','correctAnswer':{'choice':'B'}},
            {'globalId':'q1','correctAnswer':{'choice':'A'}}],
            'materials':[{'globalId':'m1'}],
            'card':{'children':[{'nodeType':2,'key':'q1','materialKeys':['m1']},
                                {'nodeType':2,'key':'q2','materialKeys':[]}]}}
    def test_order_comes_from_card_not_payload_array(self):
        self.assertEqual([x['key'] for x in module.validate(self.paper,2,'测试卷')],['q1','q2'])
    def test_first_module_and_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'count'):module.validate(self.paper,110,'测试卷')
        self.paper['solutions'][1]['globalId']='q2'
        with self.assertRaisesRegex(ValueError,'ids'):module.validate(self.paper,2,'测试卷')
    def test_missing_answers_and_materials_rejected(self):
        bad=copy.deepcopy(self.paper);bad['solutions'][0].pop('correctAnswer')
        with self.assertRaisesRegex(ValueError,'answers_missing'):module.validate(bad,2,'测试卷')
        self.paper['materials']=[]
        with self.assertRaisesRegex(ValueError,'material_missing'):module.validate(self.paper,2,'测试卷')
    def test_wrong_title_rejected(self):
        with self.assertRaisesRegex(ValueError,'title_mismatch'):module.validate(self.paper,2,'另一卷')

if __name__=='__main__':unittest.main()
