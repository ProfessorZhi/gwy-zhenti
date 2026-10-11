import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cloud_quality as c


class MatchingTests(unittest.TestCase):
    def text(self, material=None, pending=1, q='根据材料回答。'):
        material=material or ('甲乙丙丁，'*1100+'截断到这里')
        return ('---\n考试: "省考"\n地区: "上海"\n年份: "2016"\n科目: "申论"\n卷型: "A类"\n'
                '校验状态: "历史材料截断 1 题"\n上游截断题数: 1\n现仍截断题数: '+str(pending)+'\n---\n'
                '# 测试\n> 申论 · 1 题\n\n## 第 1 题（单一题）\n\n### 给定材料\n\n'+material+
                '\n\n### 作答要求\n\n'+q+'\n\n## 答案与解析\n\n<details>\n<summary>第 1 题</summary>\n原答案。\n</details>\n')

    def pool(self, text, tail='的完整后文。', title='2016年上海公考申论（A卷）'):
        b=next(c.QBLOCK.finditer(text));m=c.MAT.search(b.group(2));full=m.group(1).strip()+tail
        key=c.normalized(m.group(2).strip())
        return {key:[dict(title=title,material=full,normalized=c.normalized(full),path='sample.md',sha256='a'*64,question_id='12')]}

    def test_exact_tail_only(self):
        old=self.text();new,proof=c.plan_repair(old,self.pool(old))
        self.assertEqual(len(proof),1);self.assertIn('现仍截断题数: 0',new)
        self.assertEqual(c.DETAIL.findall(old),c.DETAIL.findall(new))
        self.assertIn('截断到这里的完整后文。',new)
        self.assertIn('上游截断题数: 1',new)

    def test_no_unrecorded_expansion(self):
        old=self.text(pending=0);self.assertEqual(c.plan_repair(old,self.pool(old)),(old,[]))

    def test_wrong_year_or_region_is_rejected(self):
        old=self.text()
        for title in ('2017年上海公考申论（A卷）','2016年北京公考申论（A卷）'):
            self.assertEqual(c.plan_repair(old,self.pool(old,title=title)),(old,[]))

    def test_ambiguous_source_versions_are_rejected(self):
        old=self.text();p=self.pool(old);key=next(iter(p));p[key]+=self.pool(old,tail='的另一个结尾。')[key]
        self.assertEqual(c.plan_repair(old,p),(old,[]))

    def test_middle_gap_is_not_tail_repair(self):
        old=self.text();p=self.pool(old);key=next(iter(p));p[key][0]['material']='别的开头'+p[key][0]['material'];p[key][0]['normalized']=c.normalized(p[key][0]['material'])
        self.assertEqual(c.plan_repair(old,p),(old,[]))

    def test_question_spillover_rejected(self):
        old=self.text();self.assertEqual(c.plan_repair(old,self.pool(old,tail='。\n## 新题\n伪材料。')),(old,[]))

    def test_images_not_invented(self):
        old=self.text();self.assertEqual(c.plan_repair(old,self.pool(old,tail='。\n![](unknown.png)\n结束。')),(old,[]))

    def test_tiny_valid_tail_is_allowed(self):
        old=self.text();new,proof=c.plan_repair(old,self.pool(old,tail='。'))
        self.assertEqual(len(proof),1)

    def test_whitespace_match_preserves_existing(self):
        self.assertEqual(c.suffix_after_prefix('甲\n乙','甲 乙\n丙。'),'\n丙。')

    def test_compatibility_character_not_cut_in_middle(self):
        self.assertIsNone(c.suffix_after_prefix('1','½结束。'))

    def test_meta_numbers_and_quoted_values(self):
        self.assertEqual(c.meta(self.text())['现仍截断题数'],1)

    def test_html_and_markdown_images(self):
        self.assertEqual(c.image_refs('<img src="../图/a.png"/> ![x](../图/b.png)'),['../图/a.png','../图/b.png'])

    def test_relative_image_resolving(self):
        self.assertEqual(c.resolve_image('国考/2026/行测-A.md','../../图片/a.png'),'图片/a.png')
        self.assertTrue(c.resolve_image('a.md','../../outside.png').startswith('!outside:'))
        self.assertIsNone(c.resolve_image('a.md','https://host/a.png'))

    def test_short_answer_not_misclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'省考/上海/2016/行测-A类.md';p.parent.mkdir(parents=True)
            p.write_text('---\n科目: "行测"\n地区: "上海"\n年份: "2016"\n卷型: "A类"\n---\n> 行测 · 1 题\n## 第 1 题\n题干\n<details>\n<summary>第 1 题</summary>\n**答案**：C\n</details>',encoding='utf-8')
            with patch.object(c,'tracked_paths',return_value={p.relative_to(root).as_posix()}):rows,stats=c.scan(root)
            self.assertEqual(rows[0]['answer_blocks'],1)
            self.assertNotIn('答案数量与题量不一致',rows[0]['issues'])

if __name__=='__main__':unittest.main()
