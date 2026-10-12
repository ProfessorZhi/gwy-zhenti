import unittest
from round3_source_boundaries import parse_complete

class StandaloneQuestionHeadingTest(unittest.TestCase):
    def test_standalone_heading_has_no_empty_body_prefix(self):
        stem='请根据给定资料1概括有关问题并提出改进建议。（100分）'
        requirement='要求：准确完整，不超过500字。'
        source=['一、注意事项','二、给定材料','材料1','仅作解析器测试而非真实试题的完整材料。'*12,'三、作答要求','第一题',stem,requirement]
        result=parse_complete(source,1)
        self.assertEqual(result['questions'][1],stem+'\n\n'+requirement)
        self.assertTrue(any(e.get('kind')=='question_boundary_whitespace' for e in result['source_header_corrections']))
