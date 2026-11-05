# -*- coding: utf-8 -*-
"""华图补题工具：用合成试卷与合成华图缓存验证对齐、写入与保护。全部为虚构文本。"""
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import huatu_fill  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452")
STEMS = [f"合成题干第{i}题：关于虚构城市第{i}号街区的交通规划，下列说法正确的是" for i in range(1, 9)]


def paper_md(missing):
    lines = ["---", '考试: "省考"', '地区: "测试"', "年份: 2025", '科目: "行测"', '卷型: "统考"',
             '来源: "https://spa.fenbi.com/ti/exam/exercise/synthetic"', '校验状态: "候选"', "---", "",
             "# 合成试卷", "", "## 题目", ""]
    for i, stem in enumerate(STEMS, 1):
        if i == 6:
            lines += ["## 材料 1", "", huatu_fill.MATERIAL_STUB, ""]
        lines += [f"### 第 {i} 题", ""]
        if i in missing:
            lines += [huatu_fill.STUB, "", f"<details><summary>第 {i} 题 · 答案与解析</summary>", "",
                      "**答案状态：unknown（来源未提供）**", "", "**解析状态：unknown（来源未提供）**", "", "</details>", ""]
        else:
            lines += [stem, "", "A. 甲", "", "B. 乙", "", f"<details><summary>第 {i} 题 · 答案与解析</summary>", "",
                      "**参考答案（粉笔题库参考内容）**", "", "A", "", "</details>", ""]
    return "\n".join(lines) + "\n"


def huatu_paper(extra_front=1):
    qs = [{"stem_html": "<p>华图独有的卷首说明题</p>", "options": [], "answer": "A"}] * extra_front
    for i, stem in enumerate(STEMS, 1):
        q = {"stem_html": f"<p>{stem}</p>", "options": [{"label": "A", "html": "甲"}, {"label": "B", "html": "乙"}],
             "answer": "B", "analysis_html": f"<p>合成解析{i}</p>"}
        if i == 3:
            q["stem_html"] += '<p><img src="https://img.example/3.png"></p>'
        if i >= 6:
            q["material_id"] = "m1"
        qs.append(q)
    return {"paperId": "999", "title": "合成", "url": "https://v.huatu.com/tiku/analysis/synthetic?token=not-real#x", "capturedAt": "2026-11-04T00:00:00Z", "questions": qs,
            "materials": [{"id": "m1", "html": "<p>合成材料正文：虚构的统计表说明。</p>"}],
            "images": [{"url": "https://img.example/3.png", "file": "images/3.png"}]}


class HuatuFill(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.rel = "省考/测试/2025/行测-统考.md"
        (self.root / self.rel).parent.mkdir(parents=True)
        (self.root / "catalog").mkdir()
        self.cache = self.root / "cache"
        (self.cache / "images").mkdir(parents=True)
        (self.cache / "images/3.png").write_bytes(PNG)

    def run_fill(self, missing, meta, write=True):
        (self.root / self.rel).write_text(paper_md(missing), encoding="utf-8")
        (self.root / "catalog/manifest.jsonl").write_text(json.dumps({"path": self.rel, "sha256": "x", "bytes": 0}) + "\n")
        (self.cache / "paper.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return huatu_fill.fill(self.rel, self.cache, write=write, root=self.root)

    def test_fills_offset_question_material_and_records_source(self):
        report = self.run_fill({3, 6}, huatu_paper(extra_front=1))
        self.assertEqual(1, report["offset"])
        self.assertEqual([3, 6], [f["q"] for f in report["fills"]])
        text = (self.root / self.rel).read_text(encoding="utf-8")
        self.assertNotIn(huatu_fill.STUB, text)
        self.assertNotIn(huatu_fill.MATERIAL_STUB, text)
        self.assertIn("合成材料正文", text)
        self.assertIn("对齐 hu4", text)
        self.assertIn('来源方: "华图在线"', text)
        self.assertIn("题号: [3, 6]", text)
        img = list((self.root / self.rel).parent.glob("assets-huatu-999/*.png"))
        self.assertEqual(1, len(img))
        self.assertIn(f"assets-huatu-999/{img[0].name}", text)
        row = json.loads((self.root / "catalog/manifest.jsonl").read_text(encoding='utf8'))
        self.assertEqual(len(text.encode("utf-8")), row["bytes"])
        # 未补的题逐字节不变
        original = paper_md({3, 6})
        for q in (1, 2, 4, 5, 7, 8):
            block = lambda t: t.split(f"### 第 {q} 题")[1].split("### 第")[0].split("## 材料")[0]
            self.assertEqual(block(original), block(text), q)

    def test_dry_run_does_not_write(self):
        report = self.run_fill({3}, huatu_paper(), write=False)
        self.assertFalse(report["written"])
        self.assertIn(huatu_fill.STUB, (self.root / self.rel).read_text(encoding="utf-8"))

    def test_different_paper_is_refused(self):
        meta = huatu_paper()
        for q in meta["questions"]:
            q["stem_html"] = "<p>完全不同的另一份试卷题干，与本卷无关的虚构内容</p>"
        report = self.run_fill({3}, meta)
        self.assertEqual([], report["fills"])
        self.assertIn("卷级锚点", report["skipped"][0]["reason"])

    def test_recall_paper_with_inserted_and_dropped_questions(self):
        # 回忆卷：华图卷首和第 4、5 题之间各多一题，题数与本库不同；前后局部偏移不同，仍应逐题夹逼补入。
        meta = huatu_paper(extra_front=1)
        meta["questions"].insert(5, {"stem_html": "<p>华图回忆版多出的一题</p>", "options": [], "answer": "C"})
        report = self.run_fill({2, 7}, meta, write=True)
        self.assertEqual([(2, 3), (7, 9)], [(f["q"], f["huatu"]) for f in report["fills"]])
        text = (self.root / self.rel).read_text(encoding="utf-8")
        self.assertIn(STEMS[1], text)
        self.assertIn(STEMS[6], text)
        self.assertNotIn("华图回忆版多出的一题", text)

    def test_crossing_match_is_not_an_anchor(self):
        # 华图把第 3、4 题顺序对调：两题不能同时作锚点。
        self.assertEqual(7, len(huatu_fill.monotone({1: 1, 2: 2, 3: 4, 4: 3, 5: 5, 6: 6, 7: 7, 8: 8})))

    def test_one_sided_gap_is_skipped(self):
        # 华图缺本库第 8 题：第 7 题后侧无锚点，只有前侧支持，不补。
        meta = huatu_paper()
        meta["questions"].pop()
        report = self.run_fill({7}, meta, write=False)
        self.assertEqual([], report["fills"])

    def test_tail_gap_needs_matching_paper_length(self):
        report = self.run_fill({7, 8}, huatu_paper(), write=False)
        self.assertEqual([7, 8], [f["q"] for f in report["fills"]])
        longer = huatu_paper()
        longer["questions"].append({"stem_html": "<p>华图多出来的一题</p>", "options": [], "answer": "A"})
        report = self.run_fill({7, 8}, longer, write=False)
        self.assertEqual([], report["fills"])

    def option_fixture(self, heading='###'):
        original = paper_md(set())
        original = original.replace('### 第 4 题\n\n'+STEMS[3]+'\n\nA. 甲\n\nB. 乙',
                                    heading+' 第 4 题\n\n'+STEMS[3]+'\n\nA. 甲\n\nB. 乙\n\nC. 缺失\n\nD. 丁')
        meta=huatu_paper(extra_front=0)
        meta['questions'][3]['options']=[{'label':v,'html':t} for v,t in zip('ABCD',['新甲','新乙','新丙','新丁'])]
        meta['questions'][3]['answer']='C'
        (self.root/self.rel).write_text(original,encoding='utf8')
        (self.root/'catalog/manifest.jsonl').write_text(json.dumps({'path':self.rel,'sha256':'x','bytes':0})+'\n',encoding='utf8')
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        return original,meta

    def test_a2_whole_option_set_from_same_question_and_preserves_other_questions(self):
        original,meta=self.option_fixture()
        dry=huatu_fill.fill(self.rel,self.cache,write=False,root=self.root,option_q=4)
        self.assertEqual([4],[x['q'] for x in dry['fills']]);self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertTrue(report['written']);new=(self.root/self.rel).read_text(encoding='utf8')
        self.assertIn('C. 新丙',new);self.assertNotIn('C. 缺失',new)
        self.assertIn('用途: "补选项、参考答案及解析"',new)
        self.assertIn('卷级锚点',new);self.assertIn('邻题夹逼 4/4',new)
        before={n:original[a:b] for n,a,b in huatu_fill.split_questions(original)}
        after={n:new[a:b] for n,a,b in huatu_fill.split_questions(new)}
        for n in before:
            if n!=4:self.assertEqual(before[n],after[n])
        self.assertEqual(1,len(list((self.root/self.rel).parent.glob('assets-huatu-999/*-original.txt'))))

    def test_a2_mismatched_stem_and_missing_neighbors_are_refused(self):
        original,meta=self.option_fixture();meta['questions'][3]['stem_html']='完全不同的题干'
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertFalse(report['written']);self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))
        original,meta=self.option_fixture();meta['questions'][4]['stem_html']='不相关题'
        meta['questions'][5]['stem_html']='另一道不相关题'
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=False,root=self.root,option_q=4)
        self.assertEqual([],report['fills'])

    def test_a2_missing_image_or_out_of_order_option_must_not_write(self):
        original,meta=self.option_fixture();meta['questions'][3]['options'][2]['html']='<img src="https://img.example/missing.png">'
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        with self.assertRaises(ValueError):huatu_fill.fill(self.rel,self.cache,write=False,root=self.root,option_q=4)
        with self.assertRaises(ValueError):huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))
        original,meta=self.option_fixture();meta['questions'][3]['options'].reverse()
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertFalse(report['written']);self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))

    def test_a2_supports_second_level_question_heading(self):
        original,meta=self.option_fixture(heading='##')
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertTrue(report['written']);self.assertIn('C. 新丙',(self.root/self.rel).read_text(encoding='utf8'))

    def test_a2_figure_options_require_present_shared_image(self):
        original,meta=self.option_fixture(heading='##')
        meta['questions'][3]['options']=[{'label':v,'html':'如图所示'} for v in 'ABCD']
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertFalse(report['written']);self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))
        meta['questions'][3]['option_figure_html']='<img src="https://img.example/3.png">'
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertTrue(report['written']);self.assertIn('assets-huatu-999/',(self.root/self.rel).read_text(encoding='utf8'))

    def test_a2_above_figure_wording_requires_shared_figure(self):
        original,meta=self.option_fixture()
        meta['questions'][3]['options']=[{'label':v,'html':'如上图所示'} for v in 'ABCD']
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertFalse(report['written']);self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))

    def test_a2_rejects_archive_path_escape_before_any_write(self):
        original,meta=self.option_fixture();meta['questions'][3]['options'][2]['html']='<img src="https://img.example/a.png">';meta['images']=[{'url':'https://img.example/a.png','file':'../outside.png'}]
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        with self.assertRaises(ValueError):huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))
        self.assertFalse((self.root/self.rel).parent.joinpath('assets-huatu-999').exists())

    def test_a2_does_not_treat_valid_literal_word_as_missing(self):
        original,meta=self.option_fixture();original=original.replace('C. 缺失','C. 缺失是题目中的实际词语')
        (self.root/self.rel).write_text(original,encoding='utf8')
        with self.assertRaises(ValueError):huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))

    def test_a2_rejects_mapped_but_absent_image_before_any_write(self):
        original,meta=self.option_fixture();meta['questions'][3]['options'][2]['html']='<img src="https://img.example/3.png">';meta['images'][0]['file']='images/not-there.png'
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'图片文件缺失'):huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))

    def test_a2_equivalent_law_stem_needs_two_identical_existing_options(self):
        original,meta=self.option_fixture()
        original=original.replace(STEMS[3],'下列关于《预备役人员法》的说法错误的是：')
        original=original.replace('A. 甲\n\nB. 乙\n\nC. 缺失','A. 共同选项甲项内容\n\nB. 共同选项乙项内容\n\nC. 缺失')
        (self.root/self.rel).write_text(original,encoding='utf8')
        meta['questions'][3]['stem_html']='根据《中华人民共和国预备役人员法》，下列说法错误的是：'
        meta['questions'][3]['options']=[{'label':v,'html':t} for v,t in zip('ABCD',['共同选项乙项内容','新内容','共同选项甲项内容','另一个选项'])]
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=False,root=self.root,option_q=4)
        self.assertEqual([4],[x['q'] for x in report['fills']])
        # One shared option or reversed polarity is insufficient.
        meta['questions'][3]['options'][0]['html']='不相同'
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        self.assertEqual([],huatu_fill.fill(self.rel,self.cache,write=False,root=self.root,option_q=4)['fills'])
        meta['questions'][3]['options'][0]['html']='共同选项乙项内容'
        meta['questions'][3]['stem_html']=meta['questions'][3]['stem_html'].replace('错误','正确')
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        self.assertEqual([],huatu_fill.fill(self.rel,self.cache,write=False,root=self.root,option_q=4)['fills'])

    def test_cli_routes_essay_plan_and_restores_argv(self):
        args=['huatu_fill.py','--essay-plan','work/essay-plan.json','--write','--expect-after','ab12']
        calls=[]
        def fake_run(path, run_name):
            calls.append((Path(path).name,run_name,list(sys.argv)))
        with patch.object(sys,'argv',args.copy()), patch('runpy.run_path',side_effect=fake_run):
            self.assertEqual(0,huatu_fill.main())
            self.assertEqual(args,sys.argv)
        self.assertEqual([('essay_gap_fill.py','__main__',['essay_gap_fill.py','--plan','work/essay-plan.json','--write','--expect-after','ab12'])],calls)

    def test_cli_rejects_essay_plan_mixed_with_xingce_flags(self):
        with patch.object(sys,'argv',['huatu_fill.py','--essay-plan','x','--paper','x']):
            with self.assertRaises(SystemExit):huatu_fill.main()

    def test_preserves_real_jiangsu_array_sources_and_adds_sanitized_huatu_url(self):
        old=paper_md(set()).replace('来源: "https://spa.fenbi.com/ti/exam/exercise/synthetic"',
                                   '来源: ["linfukai186", "xingcezhenti"]')
        new=huatu_fill.update_frontmatter(old,huatu_paper(),[4])
        self.assertIn('来源: ["linfukai186", "xingcezhenti"]',new)
        self.assertNotIn('来源方: "粉笔"',new)
        self.assertIn('来源方: "linfukai186"',new)
        self.assertIn('来源方: "xingcezhenti"',new)
        self.assertIn('定位: "https://v.huatu.com/tiku/analysis/synthetic"',new)
        self.assertNotIn('not-real',new)

    def test_refuses_missing_or_non_huatu_source_url(self):
        meta=huatu_paper();meta['url']='https://example.com/not-huatu'
        with self.assertRaises(ValueError):huatu_fill.update_frontmatter(paper_md(set()),meta,[4])

    def test_option_dry_run_rejects_invalid_provenance_before_reporting_fill(self):
        original,meta=self.option_fixture();meta['url']='https://example.com/not-huatu'
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        with self.assertRaises(ValueError):huatu_fill.fill(self.rel,self.cache,write=False,root=self.root,option_q=4)
        self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))

    def test_a2_does_not_copy_unrelated_archive_images(self):
        original,meta=self.option_fixture();meta['images'].append({'url':'https://img.example/unused.png','file':'images/unused.png'})
        (self.cache/'paper.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
        report=huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertTrue(report['written'])
        self.assertFalse(list((self.root/self.rel).parent.glob('assets-huatu-999/*.png')))

    def test_target_outside_exam_tree_rejected_before_read_or_write(self):
        with self.assertRaises(ValueError):huatu_fill.fill('../external.md',self.cache,write=True,root=self.root,option_q=4)

    def test_a2_invalid_manifest_rejected_before_any_file_write(self):
        original,meta=self.option_fixture();(self.root/'catalog/manifest.jsonl').write_text('bad json',encoding='utf8')
        with self.assertRaises(ValueError):huatu_fill.fill(self.rel,self.cache,write=True,root=self.root,option_q=4)
        self.assertEqual(original,(self.root/self.rel).read_text(encoding='utf8'))
        self.assertFalse((self.root/self.rel).parent.joinpath('assets-huatu-999').exists())


if __name__ == "__main__":
    unittest.main()
