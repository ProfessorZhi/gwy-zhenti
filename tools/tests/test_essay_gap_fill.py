import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('essay_gap_fill', Path(__file__).resolve().parents[1] / 'essay_gap_fill.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def sha(s): return hashlib.sha256(s.encode()).hexdigest()

class EssayGapFillTest(unittest.TestCase):
    def setUp(self):
        self.material1='材料一已有的背景资料足够长便于稳定验证跨来源是否是同一张试卷和同一份材料内容'
        self.material3='后备干部培训班材料有独特的村庄和培训情景足够长用于验证对应材料并确保编号正确'
        self.question='请根据材料1-2列出观摩会议前期准备工作并按实际情况简要说明'
        self.body='本次观摩会相关材料提供了详细的时间安排和地点人员信息并且介绍了产业园建设和组织过程'
        self.target=('---\n考试: "省考"\n地区: "广东"\n年份: 2019\n科目: "申论"\n卷型: "乡镇卷"\n来源: "粉笔"\n---\n\n# 测试卷\n\n## 给定材料\n\n### 材料 1\n\n'+self.material1+
                     '\n\n### 材料 2\n\n'+self.material3+'\n\n## 题目\n\n### 第 1 题\n\n**'+self.question+
                     '。**\n\n关联材料：材料 1、材料 2\n\n### 第 2 题\n\n**根据材料3介绍培训活动。**\n\n关联材料：材料 1、材料 2\n')
        self.source=('华图广东2019申论乡镇试卷标题\n材料1\n'+self.material1+'\n材料2\n'+self.body+'\n材料3\n'+self.material3+'\n问题\n'+self.question)
        self.plan={'before_sha256':sha(self.target),'source_sha256':sha(self.source),'source_url':'https://www.huatu.com/example',
                   'source_title':'华图广东2019申论乡镇试卷标题', 'anchors':[{'kind':'material','text':self.material1},{'kind':'question','text':self.question}],
                   'renumber':{'2':3},'renumber_checks':{'2':self.material3},'repair_references':True,
                   'additions':[{'number':2,'text':self.body,'source_start':'材料2','source_end':'材料3'}]}

    def run_preview(self): return mod.preview(self.plan,self.target.encode(),self.source.encode()).decode()

    def test_success_preserves_existing_material_and_repairs_explicit_references(self):
        out=self.run_preview();self.assertIn('### 材料 2\n\n'+self.body,out)
        self.assertIn('### 材料 3\n\n'+self.material3,out)
        self.assertIn('关联材料：材料 3',out);self.assertIn('定位: "https://www.huatu.com/example"',out)
        self.assertEqual(out.count(self.material1),1);self.assertEqual(out.count(self.material3),1)

    def test_hash_mismatch_wrong_source_and_missing_anchors_fail(self):
        for change in ('hash','url','anchor','boundary','body','rename_proof'):
            with self.subTest(change=change):
                self.setUp()
                if change=='hash':self.plan['source_sha256']='0'*64
                if change=='url':self.plan['source_url']='https://other.example/a'
                if change=='anchor':self.plan['anchors'][1]['text']='不匹配的题目锚点但是这个句子需要足够长才能通过长度检查'
                if change=='boundary':self.plan['additions'][0]['source_start']='材料3'
                if change=='body':self.plan['additions'][0]['text']+='原文中并没有出现的额外文字'
                if change=='rename_proof':self.plan['renumber_checks']={}
                with self.assertRaises(ValueError):self.run_preview()

    def test_replacing_existing_material_is_rejected(self):
        self.plan['additions'][0]['number']=3
        with self.assertRaisesRegex(ValueError,'replace existing'):self.run_preview()

    def test_public_fenbi_republication_keeps_actual_provider(self):
        self.plan['source_url']='https://gwy.gkzhenti.cn/paper/1494401835671'
        out=self.run_preview()
        self.assertIn('来源方: "公开真题库"',out)
        self.assertNotIn('来源方: "华图教育"',out)

    def test_republication_host_suffix_spoof_is_rejected(self):
        self.plan['source_url']='https://gwy.gkzhenti.cn.evil.example/paper/1'
        with self.assertRaises(ValueError):self.run_preview()

    def test_third_party_pre2016_is_rejected(self):
        self.target=self.target.replace('2019','2015');self.source=self.source.replace('2019','2015')
        self.plan.update(before_sha256=sha(self.target),source_sha256=sha(self.source),
                         source_title=self.plan['source_title'].replace('2019','2015'),
                         source_url='https://gwy.gkzhenti.cn/paper/123')
        with self.assertRaisesRegex(ValueError,'2016 onward'):self.run_preview()

    def test_source_body_truncation_at_either_end_is_rejected(self):
        whole = self.body * 3
        self.source = self.source.replace(self.body, whole)
        self.plan['source_sha256'] = sha(self.source)
        self.plan['additions'][0]['text'] = whole
        self.run_preview()
        for fragment in (whole[50:], whole[:-50]):
            with self.subTest(fragment=fragment[:10]):
                self.assertGreater(len(mod.norm(fragment)), 40)
                self.plan['additions'][0]['text'] = fragment
                with self.assertRaisesRegex(ValueError,'complete source section'):self.run_preview()

    def test_material_punctuation_is_evidence_not_silently_ignored(self):
        self.plan['additions'][0]['text'] = self.body + '。'
        with self.assertRaisesRegex(ValueError,'complete source section'):self.run_preview()

    def test_dry_run_then_guarded_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); target=root/'省考'/'样本'/'申论-乡镇卷.md';target.parent.mkdir(parents=True)
            target.write_bytes(self.target.encode());source=root/'source.txt';source.write_bytes(self.source.encode())
            plan={**self.plan,'target':str(target.relative_to(root)),'source_file':str(source)}
            plan_path=root/'plan.json';plan_path.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf8')
            out=io.StringIO()
            with patch.object(mod,'ROOT',root),patch.object(sys,'argv',['essay_gap_fill','--plan',str(plan_path)]),contextlib.redirect_stdout(out):mod.main()
            self.assertEqual(target.read_bytes(),self.target.encode())
            expected=json.loads(out.getvalue().splitlines()[0])['after_sha256']
            with patch.object(mod,'ROOT',root),patch.object(sys,'argv',['essay_gap_fill','--plan',str(plan_path),'--write','--expect-after',expected]),contextlib.redirect_stdout(io.StringIO()):mod.main()
            self.assertEqual(mod.digest(target.read_bytes()),expected)

if __name__ == '__main__': unittest.main()
