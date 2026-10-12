import unittest
from essay_transcript_restore import parse_transcript,parse_publisher_answers,source_variants,prompt_key
from essay_layout import parse_whole,format_whole


def sample():
    return ['一、注意事项','说明文字。','材料1','材料完整段落描述一个公共问题及其背景，涉及参与主体、措施与效果，不应被删除或截短。'*2,
            '作答要求','（一）请概括问题。（40分）','要求：完整准确，不超过200字。',
            '（二）请撰写文章。（60分）','要求：论证充分，1000字。']

def run(ps):return parse_transcript(ps,question_count=2,material_count=1)

class TranscriptTests(unittest.TestCase):
    def test_explicit_labels(self):
        d=run(sample());self.assertEqual([q['number'] for q in d['questions']],[1,2]);self.assertEqual([q['score'] for q in d['questions']],[40,60])
    def test_original_paragraph_retained(self):
        d=run(sample());self.assertEqual(d['materials'][0]['paragraphs'],[sample()[3]])
    def test_missing_h2_heading_not_missing_question(self):
        ps=sample();ps.remove('作答要求');self.assertEqual(len(run(ps)['questions']),2)
    def test_question_order_not_guessed(self):
        ps=sample();ps[5]=ps[5].replace('（一）','（二）');ps[7]=ps[7].replace('（二）','（一）')
        with self.assertRaises(ValueError):run(ps)
    def test_missing_question(self):
        with self.assertRaises(ValueError):run(sample()[:-2])
    def test_missing_score(self):
        ps=sample();ps[5]=ps[5].replace('（40分）','')
        with self.assertRaises(ValueError):run(ps)
    def test_wrong_total_score(self):
        ps=sample();ps[5]=ps[5].replace('40分','35分')
        with self.assertRaises(ValueError):run(ps)
    def test_no_requirements(self):
        ps=sample();ps[6]='仅有提示，不是要求。'
        with self.assertRaises(ValueError):run(ps)
    def test_no_word_limit(self):
        ps=sample();ps[-1]='要求：准确。'
        with self.assertRaises(ValueError):run(ps)
    def test_invalid_encoding_rejected(self):
        ps=sample();ps[3]+='\ufffd'
        with self.assertRaises(ValueError):run(ps)
    def test_material_gap(self):
        ps=sample();ps[2]='材料2'
        with self.assertRaises(ValueError):run(ps)
    def test_empty_material(self):
        ps=sample();ps[3]=''
        with self.assertRaises(ValueError):run(ps)
    def test_zero_material_count(self):
        with self.assertRaises(ValueError):parse_transcript(sample(),question_count=2,material_count=0)
    def test_placeholder_source(self):
        ps=sample();ps[3]+='本题暂缺'
        with self.assertRaises(ValueError):run(ps)
    def test_answer_section_not_attached_to_final_requirements(self):
        ps=sample()+['参考答案','（一）【参考答案】','参考答案文字。'*10,'（二）【参考范文】','参考范文文字。'*10]
        d=run(ps);self.assertEqual(d['questions'][-1]['requirements'],[sample()[-1]]);self.assertEqual(set(parse_publisher_answers(d['answer_paragraphs'],2)),{1,2})
    def test_answer_truncation_rejected(self):
        ps=['（一）【参考答案】','参考答案文字。'*10+'......','（二）【参考范文】','参考范文文字。'*10]
        with self.assertRaises(ValueError):parse_publisher_answers(ps,2)
    def test_missing_answer_marker_does_not_pad(self):
        self.assertEqual(parse_publisher_answers(['（一）【参考答案】','完整参考。'*10],2),{})
    def test_ads_excluded_after_answers(self):
        ps=['（一）【参考答案】','第一答案。'*10,'（二）【参考范文】','第二答案。'*10,'编辑推荐','广告内容']
        self.assertNotIn('广告',parse_publisher_answers(ps,2)[2])

class VariantAndLayoutTests(unittest.TestCase):
    def test_multiple_explicit_variants(self):
        self.assertEqual(source_variants('2016年江苏公考申论（A卷、B卷、C卷）'),{'A','B','C'})
    def test_only_declared_variant(self):
        self.assertEqual(source_variants('2017年江苏公考申论（B卷）'),{'B'})
    def test_non_variant_letters_not_used(self):
        self.assertEqual(source_variants('ABC教学分析'),set())
    def test_pure_selected_exam_rejected(self):
        self.assertEqual(source_variants('2019江苏选调生（A卷）'),set())
    def test_explicit_shared_civil_service_A(self):
        self.assertEqual(source_variants('2019年江苏省公考《申论》题（A、普通选调卷）'),{'A'})
    def test_mock_source_rejected(self):
        self.assertEqual(source_variants('2019年江苏公考模考（A卷）'),set())
    def test_answer_heading_alias_preserves_body(self):
        text='---\n科目: "申论"\n---\n# 原文\n\n材料一\n材料原文。\n\n答题要求\n一、概括问题。（40分）\n要求：准确，200字。\n二、撰写文章。（60分）\n要求：完整，1000字。\n'
        self.assertEqual(parse_whole(text,2)['points'],[40,60]);out,r=format_whole(text,2,{},'未取得答案');self.assertIn('材料原文。',out);self.assertIn('答题要求',out);self.assertIn('## 第 2 题',out)
    def test_prompt_does_not_drop_material_number(self):
        self.assertNotEqual(prompt_key('一、分析给定材料1。（20分）'),prompt_key('一、分析给定材料2。（20分）'))

if __name__=='__main__':unittest.main()
