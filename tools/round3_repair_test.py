import unittest
from copy import deepcopy
from round3_source_boundaries import parse_complete
from round3_repair_apply import retain_material
from round3_priority_repair import match_questions

class Round3Tests(unittest.TestCase):
    def paper(self,native=True):
        ps=['一、注意事项','二、给定材料','材料1','这一段是测试材料，并不是历史真题。'*12,'三、作答要求']
        for i in range(1,6):
            ps += [(f'第{i}题：' if native else '')+f'请依据给定资料1分析第{i}个不同问题并说明本题的核心含义。（20分）','要求：条理清晰，不超过200字。']
        return ps
    def test_native(self):self.assertEqual(len(parse_complete(self.paper(),5)['questions']),5)
    def test_list_numbers(self):self.assertEqual(parse_complete(self.paper(False),5)['points'],[20]*5)
    def test_id_material(self):
        ps=self.paper();ps[2]='材料1(341891)';r=parse_complete(ps,5);self.assertEqual(r['source_header_corrections'][0]['source_internal_id'],'341891')
    def test_does_not_erase_material_body_number(self):
        ps=self.paper();ps[3]+='这不是标题：材料1(341891)';self.assertIn('341891',parse_complete(ps,5)['materials'][1][0])
    def test_missing_material_reference(self):
        ps=self.paper();ps[5]=ps[5].replace('资料1','资料2')
        with self.assertRaises(ValueError):parse_complete(ps,5)
    def test_missing_word_limit(self):
        ps=self.paper();ps[-1]='要求：条理清晰。'
        with self.assertRaises(ValueError):parse_complete(ps,5)
    def test_missing_question(self):
        with self.assertRaises(ValueError):parse_complete(self.paper()[:-2],5)
    def test_score_sum(self):
        ps=self.paper();ps[5]=ps[5].replace('20分','15分')
        with self.assertRaises(ValueError):parse_complete(ps,5)
    def test_duplicate_material(self):
        ps=self.paper();ps[4:4]=['材料1','另一段材料'*30]
        with self.assertRaises(ValueError):parse_complete(ps,5)
    def test_question_match(self):
        r=match_questions({1:'请概括本地知识产权保护的主要措施及成效。'},{2:'请概括本地知识产权保护的主要措施及成效。（20分）\n要求：200字。'})
        self.assertEqual(r[0]['new_number'],2)
    def test_unrelated_question(self):
        with self.assertRaises(ValueError):match_questions({1:'请概括本地知识产权保护的主要措施及成效。'},{1:'请分析三个乡村企业扶贫贷款的推广经验及问题。'})
    def test_ambiguous_match(self):
        q='请概括本地知识产权保护的主要措施及成效。'
        with self.assertRaises(ValueError):match_questions({1:q},{1:q,2:q})
    def test_material_preservation(self):
        t='这是原有材料。\n\n所有字句都应当得到保留。';p={'materials':{1:[t]}};changes=[]
        retain_material(p,1,t,changes);self.assertEqual(''.join(p['materials'][1]),'这是原有材料。所有字句都应当得到保留。')
    def test_material_mismatch(self):
        with self.assertRaises(ValueError):retain_material({'materials':{1:['另一份毫不相关的卷。']}},1,'这是待保护的原有材料。',[])
    def test_unnumbered_subquestions_do_not_split_major(self):
        ps=self.paper(False);ps[6:6]=['1.说明一个方面。','2.说明另一个方面。'];self.assertEqual(len(parse_complete(ps,5)['questions']),5)
    def test_four_major_not_five(self):
        ps=self.paper();ps=ps[:-2];ps=[x.replace('20分','25分') for x in ps];r=parse_complete(ps,4);self.assertEqual(len(r['questions']),4)
if __name__=='__main__':unittest.main()
