import unittest
from round3_source_boundaries import parse_complete

class SourceLineEndingTests(unittest.TestCase):
    def fixture(self,sep):
        return ['一、注意事项','二、给定材料','材料1',('这是来源中应保留的材料段落。'+sep)*12,'三、作答要求','第一题：请根据给定资料1概括主要问题并提出改进建议。（100分）','要求：准确完整，不超过500字。']
    def test_crlf_is_normalized_before_hashing(self):
        source=self.fixture('\r\n');before=list(source)
        result=parse_complete(source,1)
        self.assertNotIn('\r',''.join(result['materials'][1]))
        self.assertEqual(source,before)
        self.assertTrue(any(x.get('kind')=='line_endings' for x in result['source_header_corrections']))
    def test_lone_cr_preserves_nonwhitespace(self):
        import re
        original=self.fixture('\r');result=parse_complete(original,1)
        self.assertEqual(re.sub(r'\s','',original[3]),re.sub(r'\s','',''.join(result['materials'][1])))
        self.assertNotIn('\r',''.join(result['materials'][1]))
