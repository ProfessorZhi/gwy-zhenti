"""Regression examples for exact body extraction; historical tests stay unchanged."""
import unittest
from pathlib import Path
import round5_bulk as parser
from full_repair_precise_answer_audit_20261015 import ROOT,extract_versions,char_count,word_rules,inspect_version

class MainBodyExtraction(unittest.TestCase):
    def test_labels_count_notes_and_matching_disclaimer_are_not_body(self):
        source='> **同题参考答案，非独立B卷发布答案。** 同卷题面已核。\n\n**发布方参考答案（非官方）**\n\n保留全部真实答案要点。(12字)\n\n题面与参考答案公开来源\n[来源](https://example.com)'
        self.assertEqual(extract_versions(source)[0]['body'],'保留全部真实答案要点。')

    def test_ai_header_and_writing_basis_do_not_inflate_body(self):
        source='**原创示范作答（AI辅助编写；非机构原文，未经实考评分）**\n\n以融合提升效能\n\n开展联合检查。\n\n> 写作依据：给定资料1。\n同题机构参考作答／范文对照入口。'
        self.assertEqual(extract_versions(source)[0]['body'],'以融合提升效能\n\n开展联合检查。')

    def test_sourced_analysis_boundaries_and_double_dash_range(self):
        for boundary in ('参考范文一文章分析：','文章分析1','第一步审题通过勾画材料','第二步阅读资料'):
            self.assertEqual(extract_versions('真实正文。\n\n'+boundary+'\n附解析。')[0]['body'],'真实正文。')
        self.assertEqual(word_rules('总字数800——1000字')['maximum'],1000)
        self.assertEqual(word_rules('总字数1200字—1500字')['maximum'],1500)

    def test_long_source_link_cannot_complete_short_essay(self):
        answer='**来源作文范文**\n\n守护历史记忆\n\n'+('保护遗址，传承精神。'*12)+'\n\n> 出处：用户资料，答文作者未署名。\n\n[原资料（固定版本）](https://github.com/example/'+('very-long-source-path/'*120)+')'
        v=extract_versions(answer)[0]
        self.assertEqual(v['characters'],char_count('守护历史记忆\n\n'+'保护遗址，传承精神。'*12))
        _,issues=inspect_version('写一篇文章，800—1000字。',v,word_rules('800—1000字。'))
        self.assertIn('explicit_minimum_not_met',{i['rule'] for i in issues})

    def test_real_tail_phrase_and_synthetic_source_footer(self):
        # The actual audited legacy Shenzhen 2016B Q2 ends at “地铁站点免”.
        a='便民服务持续完善，地铁站点免\n\n> 出处：课程参考稿。\n\n[原资料（固定版本）](https://example.com/'+('x'*2000)+')'
        v=extract_versions(a)[0];self.assertTrue(v['body'].endswith('地铁站点免'))
        _,issues=inspect_version('请概括，不超过300字。',v,word_rules('不超过300字。'))
        self.assertIn('possible_truncated_final_word',{i['rule'] for i in issues})

    def test_normal_essay_title_survives(self):
        v=extract_versions('**以创新之力回应时代之问**\n\n创新来自实践。\n\n参考答案说明：标题突出主题。')[0]
        self.assertIn('以创新之力回应时代之问',v['body']);self.assertNotIn('标题突出主题',v['body'])

    def test_bylines_and_inline_links_do_not_add_url_length(self):
        a='创新与责任\n\n文/石天晓\n\n'+('创新需要实干。'*12)+'[参考事实](https://example.com/'+('y'*1000)+')'
        v=extract_versions(a)[0];self.assertNotIn('石天晓',v['body']);self.assertNotIn('https://',v['body']);self.assertIn('参考事实',v['body'])

    def test_real_truncated_family_phrase_is_only_a_review_candidate(self):
        v=extract_versions('树立先进典型，评选“最美家')[0];_,issues=inspect_version('800—1000字',v,word_rules('800—1000字'))
        self.assertIn('possible_truncated_final_word',{i['rule'] for i in issues});self.assertTrue(v['body'].endswith('“最美家'))

    def test_explicit_marker_has_priority(self):
        a='说明与旧稿。\n<!-- full-repair-answer-20261015 -->\n标题\n'+'正文。'*100+'\n<!-- /full-repair-answer-20261015 -->\n> 来源说明：署名。'
        vs=extract_versions(a);self.assertEqual(len(vs),1);self.assertNotIn('说明与旧稿',vs[0]['body']);self.assertEqual(vs[0]['extraction_method'],'explicit_main_body_marker')

    def test_two_essays_are_never_added_together(self):
        a='参考范文1\n题名甲\n'+'甲。'*220+'\n\n参考范文2：题名乙\n'+'乙。'*230
        vs=extract_versions(a);self.assertEqual(len(vs),2)
        for v in vs:
            _,issues=inspect_version('800–1000字',v,word_rules('800–1000字'))
            self.assertIn('explicit_minimum_not_met',{i['rule'] for i in issues})

    def test_per_item_caps_are_separate(self):
        q='嘉宾讨论了三个问题，请分别阐述，每个问题聚焦点不超过100字。'
        body='\n'.join('第'+c+'，'+'答'*80 for c in '一二三');v=extract_versions(body)[0]
        _,issues=inspect_version(q,v,word_rules(q));self.assertEqual(issues,[]);self.assertEqual(len(v['per_item_characters']),3)

    def test_uncertain_multiple_questions_do_not_get_aggregate_max(self):
        q='（1）概括，不超过100字；（2）提出建议，不超过200字。';r=word_rules(q)
        self.assertEqual(r['kind'],'multiple_task_limits');v=extract_versions('答'*250)[0];_,issues=inspect_version(q,v,r)
        self.assertNotIn('explicit_maximum_exceeded',{i['rule'] for i in issues})

    def test_different_caps_can_be_checked_with_unambiguous_source_labels(self):
        q='（1）概括，不超过150字。（2）梳理理由，不超过300字。'
        v=extract_versions('第（1）小题\n'+'甲'*140+'\n第（2）小题\n'+'乙'*295)[0]
        _,issues=inspect_version(q,v,word_rules(q));self.assertEqual(issues,[])
        self.assertEqual(v['per_item_characters'],[140,295])

    def test_no_punctuation_alone_does_not_imply_truncation(self):
        q='不超过200字';v=extract_versions('建议完善设施并加强服务，促进乡村振兴')[0];_,issues=inspect_version(q,v,word_rules(q))
        self.assertNotIn('possible_truncated_final_word',{i['rule'] for i in issues})

    def test_lower_bound_is_not_a_maximum(self):
        r=word_rules('字数不少于1000字');self.assertEqual(r['kind'],'explicit_minimum')
        v=extract_versions('论'*1200)[0];_,issues=inspect_version('不少于1000字',v,r);self.assertEqual(issues,[])

    def test_analysis_is_not_an_answer_body(self):
        v=extract_versions('【题目精析】\n先审题，后从材料归纳要点。')[0];self.assertEqual(v['characters'],0);self.assertTrue(v['analysis_only'])

    def test_real_hebei_2018_three_subquestions(self):
        p=ROOT/'省考/河北/2018/申论-乡镇.md'
        if not p.exists():self.skipTest('Corpus example unavailable in isolated unit environment')
        d=parser.parse(p.read_text(encoding='utf-8'),str(p));q=d['questions'][2];v=extract_versions(d['answers'][2])[0];r=word_rules(q)
        self.assertEqual(r['kind'],'per_item_maximum');_,issues=inspect_version(q,v,r);self.assertNotIn('per_item_maximum_exceeded',{i['rule'] for i in issues})

    def test_real_restored_beijing_body_excludes_authorship(self):
        p=ROOT/'省考/北京/2020/申论-乡镇卷.md'
        if not p.exists():self.skipTest('Corpus example unavailable in isolated unit environment')
        d=parser.parse(p.read_text(encoding='utf-8'),str(p));v=extract_versions(d['answers'][4])[0]
        self.assertGreaterEqual(v['characters'],800);self.assertLessEqual(v['characters'],1000);self.assertNotIn('来源说明',v['body'])

if __name__=='__main__':unittest.main()
