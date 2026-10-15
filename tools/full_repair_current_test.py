"""Behavioral regression tests for the new answer and preservation safeguards."""
import json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from full_repair_answers_20261015 import validate_answer,apply_entries
from full_repair_receipts_20261015 import operations,reverse,sha
from cloud_quality import inline_answer_numbers
import full_repair_receipts_20261015 as receipts
import cloud_quality
from verify_image_pixels import decode_one
from PIL import Image

class Safeguards(unittest.TestCase):
    def test_ndjson_source_unicode_separators_are_not_record_boundaries(self):
        # Actual Guangdong 2024 text contains U+2028; U+2029 is equivalent here.
        values=[{'path':'省考/广东/2024/行测-统考.md','old':'题面\u2028来源\u2029原文'}, {'path':'下一份.md','old':'普通正文'}]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/receipts.SHARD_DIR;folder.mkdir(parents=True)
            rel=receipts.SHARD_DIR+'/receipts-001.jsonl'
            data=('\n'.join(json.dumps(v,ensure_ascii=False) for v in values)+'\n').encode('utf-8')
            (root/rel).write_bytes(data)
            (root/receipts.INDEX).write_bytes(json.dumps({'receipt_shards':[{'path':rel,'sha256':receipts.sha(data)}]}).encode())
            self.assertEqual(receipts.records(root),values)

    def test_repeated_blank_and_heading_lines_still_restore_exact_bytes(self):
        old=('材料\r\n\r\n段落\u2028原文\r\n'*600)+'唯一旧尾\r\n'
        new=('材料\n\n段落\u2028原文\n'*300)+'补回关键资料\n'+('材料\n\n段落\u2028原文\n'*300)+'修订尾\n'
        record={'path':'源稿.md','before_sha256':sha(old),'after_sha256':sha(new),'operations':operations(old,new)}
        self.assertEqual(reverse(new,record),old)

    def test_rebuilding_inventory_preserves_history_without_repeated_growth(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'PROGRESS.md').write_text('# 旧进度\n独特历史修复记录。\n',encoding='utf-8')
            with patch.object(cloud_quality,'tracked_paths',return_value=set()):
                rows,stats=cloud_quality.scan(root)
            cloud_quality.build(root,rows,stats);first=(root/'PROGRESS.md').read_text(encoding='utf-8')
            cloud_quality.build(root,rows,stats);second=(root/'PROGRESS.md').read_text(encoding='utf-8')
            self.assertEqual(second.count('独特历史修复记录。'),1)
            self.assertEqual(first,second)
    def test_pixels_decode_all_frames_and_reject_invalid_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'two.gif'
            Image.new('RGB',(5,5),'red').save(p,save_all=True,append_images=[Image.new('RGB',(5,5),'blue')],duration=30,loop=0)
            self.assertEqual(decode_one(root,'two.gif'),(2,None))
            (root/'broken.png').write_bytes(b'not an image')
            self.assertIsNotNone(decode_one(root,'broken.png')[1])
    def test_inventory_keeps_incomplete_shared_conditions_visible(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'省考/北京/2025/行测-统考.md';p.parent.mkdir(parents=True)
            p.write_text('---\n地区: 北京\n年份: 2025\n科目: 行测\n卷型: 统考\n现仍缺失共用条件题号: [2]\n---\n# 部分回忆题\n\n> 行测 · 2 题\n\n## 第 1 题\n题面。\n\n**答案**：B\n\n## 第 2 题\n缺共用条件的题。\n\n**答案**：待补条件后作答。\n',encoding='utf-8')
            with patch.object(cloud_quality,'tracked_paths',return_value=set()):rows,stats=cloud_quality.scan(root)
            self.assertEqual(rows[0]['answer_blocks'],1)
            self.assertEqual(stats['confirmed_missing_shared_condition_questions'],1)
            self.assertIn('已确认共用题干条件缺失：2',rows[0]['issues'])
    def test_archived_path_can_hold_a_new_paper_without_losing_either_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'current';base=Path(td)/'base'
            oldrel='国考/2020/申论.md';archive='docs/来源校勘/旧稿.md'
            original='原始中文材料\r\n旧段落\r\n'.encode('utf-8')
            fixture='tools/tests/fixtures/example.png';binary=b'\x89PNG\r\n\x1a\n\x00\xff'
            for folder,rel,data in [(base,oldrel,original),(root,archive,original+'归档说明\r\n'.encode()),(root,oldrel,'另一份真实试卷\r\n'.encode()),(base,fixture,binary),(root,fixture,binary)]:
                p=folder/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            (root/'reports').mkdir()
            (root/'reports/FULL-REPAIR-IDENTITY-DISPOSITION-20261015.json').write_text(json.dumps({'relocations':{oldrel:archive}}),encoding='utf-8')
            for name in ('浙江2025-行测-原52.png','浙江2025-行测-原55.png'):
                p=root/'图片/校核补录/20261012'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(binary)
            tree={oldrel:receipts.git_blob(original),fixture:receipts.git_blob(binary)}
            with patch.object(receipts,'base_tree',return_value=tree):
                self.assertEqual(receipts.capture(base,root)['created_papers'],1)
                self.assertEqual(receipts.verify(root)['status'],'passed')
                restored=Path(td)/'restored';receipts.historical_snapshot(root,restored)
                self.assertEqual((restored/oldrel).read_bytes(),original)
                self.assertEqual((restored/fixture).read_bytes(),binary)
                # A new paper reusing an archived basename must be protected too.
                (root/oldrel).write_bytes(b'corrupted new paper')
                with self.assertRaisesRegex(ValueError,'Created paper changed'):
                    receipts.verify(root)
                # An export cannot claim to be the pinned tree after byte drift.
                (base/oldrel).write_bytes(b'not the pinned Git blob')
                with self.assertRaisesRegex(ValueError,'fixed Git commit'):
                    receipts.capture(base,root)
    def test_inline_keys_are_counted_but_missing_notices_are_not(self):
        text='## 第 1 题\n题面。\n\n**答案**：A\n\n## 第 2 题\n题面。\n\n**答案**：待恢复共用条件。\n\n## 第 3 题\n题面。\n\n**答案**：D项缺失，不能确定。\n'
        self.assertEqual(inline_answer_numbers(text),[1])
    def entry(self,answer):
        return {'answer':answer,'author':'AI辅助整理','attribution_kind':'ai_original','sources':[]}
    def test_read_following_material_is_not_a_word_maximum(self):
        question='阅读以下材料，写一篇文章，不少于1000字。'
        self.assertEqual(validate_answer(question,self.entry('论'*1200)),1200)
    def test_explicit_maximum_is_enforced(self):
        with self.assertRaisesRegex(ValueError,'maximum'):
            validate_answer('不超过200字。',self.entry('答'*201))
    def test_one_sided_explicit_target_bounds_are_not_ignored(self):
        with self.assertRaisesRegex(ValueError,'upper-only'):
            validate_answer('提出建议。',{**self.entry('答'*90),'target_word_range':[0,80]})
        with self.assertRaisesRegex(ValueError,'lower-only'):
            validate_answer('写一篇文章。',{**self.entry('文'*900),'target_word_range':[1000,0]})
    def test_explicit_minimum_is_enforced(self):
        with self.assertRaisesRegex(ValueError,'minimum'):
            validate_answer('不少于1000字。',self.entry('论'*999))
    def test_each_subquestion_has_its_own_word_limit(self):
        q='嘉宾讨论了三个问题，请分别阐述，每个问题聚焦点阐述不超过100字。'
        body='\n'.join('第'+n+'，'+'答'*80 for n in '一二三')
        self.assertGreater(validate_answer(q,self.entry(body)),200)
        with self.assertRaisesRegex(ValueError,'per-question'):
            validate_answer(q,self.entry(body.replace('第一，','第一，'+'答'*30)))
    def test_two_different_subquestion_caps_are_never_an_aggregate(self):
        q='（1）分析，不超过150字。（2）梳理理由，不超过300字。'
        body='第（1）小题\n'+'甲'*140+'\n第（2）小题\n'+'乙'*295
        self.assertGreater(validate_answer(q,self.entry(body)),300)
        with self.assertRaisesRegex(ValueError,'subquestion'):
            validate_answer(q,self.entry(body.replace('甲'*140,'甲'*151)))
    def test_prompt_or_placeholder_is_not_an_answer(self):
        with self.assertRaises(ValueError):
            validate_answer('请作答。',self.entry('本题尚未收录'+'需补'*50))
    def test_receipt_restores_archived_and_reformatted_source(self):
        old='原材料一\n\n甲乙\n丙丁\n';new='> 年份校勘归档\n\n原材料一\n\n甲乙丙丁\n'
        row={'path':'省考/某地/2018/申论.md','kind':'relocated','destination':'docs/来源.md','before_sha256':sha(old),'after_sha256':sha(new),'operations':operations(old,new)}
        self.assertEqual(reverse(new,row),old)
        with self.assertRaisesRegex(ValueError,'postimage'):
            reverse(new+'被意外修改',row)
    def test_existing_answer_requires_explicit_reason_before_replacement(self):
        # Real repository parser syntax, isolated from the delivered corpus.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);rel='省考/浙江/2025/申论-A类.md';p=root/rel;p.parent.mkdir(parents=True)
            text='---\n地区: 浙江\n年份: 2025\n科目: 申论\n---\n# 测试\n\n## 第 1 题\n\n请概括材料，200字以内。\n\n## 答案与解析\n\n<details>\n<summary>第 1 题</summary>\n\n'+('既有完整作答。'*30)+'\n\n</details>\n'
            p.write_text(text,encoding='utf-8')
            entry={**self.entry('新的示范作答。'*20),'path':rel,'number':1}
            result,_=apply_entries(root,[entry])
            self.assertEqual(result['status'],'failed')
            self.assertIn('Existing reference preserved',result['errors'][0]['error'])
            self.assertEqual(p.read_text(encoding='utf-8'),text)

if __name__=='__main__':unittest.main()
