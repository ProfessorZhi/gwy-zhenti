"""Regression tests for 2026-10-12 source identity, layout and overwrite guards."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cloud_quality
from reference_sequence_repair import reconstruct, validate_plan, sha
from paper_integrity_repair import split_paper
from essay_layout import parse_whole, format_whole
from essay_source_structure import parse_paragraphs
from gwyzhenti.export import _write


def sample_paper():
    return ('---\n地区: "江苏"\n年份: "2023"\n科目: "行测"\n卷型: "A类"\n校验状态: "旧版"\n---\n'
            '# sample\n\n> 行测 · 2 题\n\n## 材料 1\n\n材料原文。\n\n'
            '### 第 1 题　<sub>qid 11</sub>\n\n第一题原文。\n\n'
            '## 第 2 题　<sub>qid 12</sub>\n\n第二题原文。\n\n'
            '## 答案与解析\n\n<details>\n<summary>第 1 题</summary>\n\n**答案**：A\n\n</details>\n\n'
            '<details>\n<summary>第 2 题</summary>\n\n**答案**：B\n\n</details>\n')


def plan(t):
    return {'path':'省考/江苏/2023/行测-A类.md','before_sha256':sha(t),'expected_questions':3,
            'old_to_source':{1:2,2:1},'material_map':{'m1':'g1'},'question_groups':{1:None,2:'g1',3:'g1'},
            'source':{'url':'https://example.test/frozen/reference'},'additions':[]}


def essay():
    return ('---\n科目: "申论"\n校验状态: "旧版"\n---\n# 样本\n> 申论 · 2 题\n\n'
            '材料1\n材料正文原句。\n\n作答要求\n问题一：概括材料。（40分）\n要求：准确，不超过200字。\n\n'
            '问题二：撰写文章。（60分）\n要求：论证充分，1000字。\n')


def paragraphs():
    return ['注意事项','二、给定材料','材料1','完整材料正文。','三、作答要求',
            '一、请归纳给定材料中的问题。（40分）','要求：准确，不超过200字。',
            '二、围绕主题写一篇议论文。（60分）','要求：观点明确，不少于1000字。']


class SequenceGuards(unittest.TestCase):
    def test_preserves_existing_bodies_and_missing_ids(self):
        t=sample_paper();out,r=reconstruct(t,plan(t));old=split_paper(t);new=split_paper(out)
        self.assertEqual(new['qs'][2]['text'],old['qs'][1]['text'])
        self.assertEqual(new['answers'][1],old['answers'][2])
        self.assertEqual(r['missing_original_numbers'],[3])
        self.assertIsNone(new['qs'][1]['material'])
        self.assertIsNotNone(new['qs'][2]['material'])
    def test_wrong_hash(self):
        t=sample_paper();s=plan(t);s['before_sha256']='0'*64
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_incomplete_map(self):
        t=sample_paper();s=plan(t);del s['old_to_source'][2]
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_duplicate_map(self):
        t=sample_paper();s=plan(t);s['old_to_source'][2]=2
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_material_not_dropped(self):
        t=sample_paper();s=plan(t);s['material_map']={}
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_all_reference_memberships_required(self):
        t=sample_paper();s=plan(t);del s['question_groups'][3]
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_noncontiguous_material_rejected(self):
        t=sample_paper();s=plan(t);s['question_groups']={1:'g1',2:None,3:'g1'}
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_placeholder_rejected(self):
        t=sample_paper();s=plan(t);s['additions']=[{'number':3,'text':'题目暂缺','answer':'A','provenance':{'url':'x'}}]
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_addition_requires_provenance(self):
        t=sample_paper();s=plan(t);s['additions']=[{'number':3,'text':'题面完整','answer':'A'}]
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_addition_must_not_replace_old(self):
        t=sample_paper();s=plan(t);s['additions']=[{'number':2,'text':'错误覆盖','answer':'A','provenance':{'url':'x'}}]
        with self.assertRaises(ValueError):reconstruct(t,s)
    def test_followup_has_one_current_summary(self):
        t=sample_paper();a,_=reconstruct(t,plan(t));d=split_paper(a);s=plan(a)
        s['old_to_source']={n:n for n in d['qs']};s['question_groups']={1:None,2:'g1',3:'g1'}
        b,_=reconstruct(a,s);self.assertEqual(b.count('> **当前实有'),1)


class EssayGuards(unittest.TestCase):
    def test_explicit_scores_and_headings(self):
        d=parse_whole(essay(),2);self.assertEqual(d['points'],[40,60])
        out,r=format_whole(essay(),2,{},'reference');self.assertIn('## 第 2 题',out);self.assertIn('材料正文原句。',out)
    def test_wrong_declared_count_rejected(self):
        with self.assertRaises(ValueError):parse_whole(essay(),3)
    def test_wrong_score_rejected(self):
        with self.assertRaises(ValueError):parse_whole(essay().replace('60分','50分'),2)
    def test_requirements_not_invented(self):
        with self.assertRaises(ValueError):parse_whole(essay().replace('要求：','限制：'),2)
    def test_answers_explicitly_pending(self):
        out,r=format_whole(essay(),2,{1:'这是单独核对的参考答案。'},'nonofficial');self.assertEqual(r['unanswered'],[2])
        self.assertIn('本题参考答案尚未核实收录',out)
    def test_existing_answers_not_overwritten(self):
        a,_=format_whole(essay(),2,{1:'参考一',2:'参考二'},'nonofficial')
        with self.assertRaises(ValueError):format_whole(a,2,{1:'replacement'},'no')
    def test_source_sections_and_scores(self):
        d=parse_paragraphs(paragraphs(),expected_title='x',actual_title='x');self.assertEqual(len(d['questions']),2)
    def test_wrong_year_title_rejected(self):
        with self.assertRaises(ValueError):parse_paragraphs(paragraphs(),expected_title='2026B',actual_title='2025B')
    def test_source_placeholder_rejected(self):
        ps=paragraphs();ps[3]='给定材料暂缺'
        with self.assertRaises(ValueError):parse_paragraphs(ps,expected_title='x',actual_title='x')
    def test_missing_material_id_rejected(self):
        ps=paragraphs();ps[2]='材料2'
        with self.assertRaises(ValueError):parse_paragraphs(ps,expected_title='x',actual_title='x')
    def test_missing_word_limit_rejected(self):
        ps=paragraphs();ps[-1]='要求：观点明确。'
        with self.assertRaises(ValueError):parse_paragraphs(ps,expected_title='x',actual_title='x')
    def test_missing_section_rejected(self):
        ps=paragraphs();ps.remove('三、作答要求')
        with self.assertRaises(ValueError):parse_paragraphs(ps,expected_title='x',actual_title='x')


class ExportGuards(unittest.TestCase):
    def test_changed_protected_paper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'paper.md';old='---\n题序证据: "receipt"\n---\n已修复原文'.encode();p.write_bytes(old)
            with self.assertRaises(ValueError):_write(p,b'old exporter data')
            self.assertEqual(p.read_bytes(),old);self.assertFalse(Path(str(p)+'.tmp').exists())
    def test_unchanged_protected_paper_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'paper.md';b=b'---\n'+ '分卷核对证据: "receipt"'.encode()+b'\n---\nbody';p.write_bytes(b);_write(p,b);self.assertEqual(p.read_bytes(),b)
    def test_unprotected_document_still_writable(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'notes.md';p.write_bytes(b'old');_write(p,b'new');self.assertEqual(p.read_bytes(),b'new')
    def test_long_missing_answer_warning_is_not_answer(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'省考/江苏/2026/申论-B类.md';p.parent.mkdir(parents=True)
            t='---\n地区: "江苏"\n年份: 2026\n科目: "申论"\n卷型: "B类"\n已收录参考答案题号: []\n缺参考答案题号: [1]\n---\n> 申论 · 1 题\n## 第 1 题\n题干。\n## 答案与解析\n<details><summary>第 1 题</summary>'+('本题参考答案未取得，请勿视为正式答案。'*8)+'</details>'
            p.write_text(t)
            with patch.object(cloud_quality,'tracked_paths',return_value={p.relative_to(root).as_posix()}):rows,_=cloud_quality.scan(root)
            self.assertFalse(rows[0]['has_answer_content']);self.assertEqual(rows[0]['answer_blocks'],0)

if __name__=='__main__':unittest.main()
