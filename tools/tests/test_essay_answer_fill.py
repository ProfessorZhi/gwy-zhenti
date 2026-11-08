# -*- coding: utf-8 -*-
import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'essay_answer_fill.py'
def sha(b): return hashlib.sha256(b).hexdigest()
PAPER = '''---
考试: "省考"
地区: "西藏"
年份: "2019"
科目: "申论"
卷型: "统考"
真题性质: "正式真题"
来源: ["slb"]
校验状态: "机器校验；第1、4题为GPT-6生成参考答案，非官方答案；第2、3题沿用已登记来源答案"
GPT-6生成参考答案题号: [1, 4]
已收录参考答案题号: [1, 2, 3, 4]
缺参考答案题号: []
---
# 测试
## 给定材料
### 材料 1
材料正文。
## 题目
### 第 1 题
根据“给定资料1”，谈谈对于飞所说的“家乡，不只是乡愁，还有诗和远方”这句话的理解。（30分）
要求：全面、准确、简明，有条理，字数不超过300字。
<details>
<summary>第 1 题 · 答案与解析</summary>

**GPT-6 生成参考答案（非官方参考答案，供学习讨论；未发现可用同题来源答案）。**

旧的GPT答案。

</details>
### 第 2 题
第二题正文。
'''
SOURCE_TEXT = '''公务员丨【2019联考】西藏省--《申论》试卷
一、根据给定资料2，谈谈你对于飞所说的“家乡，不只是乡愁，还有诗和远方”这句话的理解。(30分)
要求：全面、准确、简明，有条理，字数不超过300字。
二、参考答案
“乡愁”，指的是离乡者向往乡村宁静、怀念美好记忆的心态。“诗和远方”，指的是把落后村落打造为富裕、文明、有序、亲近自然的村落的愿望。
三、评分方式
乡愁6分、诗和远方6分、语境逻辑12分、展望4分。
'''
class EssayAnswerFillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        target = self.root/'省考/西藏/2019/申论-统考.md'; target.parent.mkdir(parents=True)
        target.write_text(PAPER, encoding='utf-8')
        st = self.root/'source.json'
        st.write_text(json.dumps({'url':'https://wx.huatu.com/x','title':'公务员丨【2019联考】西藏省--《申论》试卷',
                                  'institution':'华图网校','text':SOURCE_TEXT,'sha256':sha(SOURCE_TEXT.encode()),
                                  'scoring_summary':{'1':'乡愁6分、诗和远方6分、语境逻辑12分、展望4分'}},ensure_ascii=False),encoding='utf-8')
        self.target = target; self.source = st
        self.plan = {'target':'省考/西藏/2019/申论-统考.md','before_sha256':sha(PAPER.encode()),'question':1,
                     'source_file':str(st),'source_sha256':sha(st.read_bytes()),'source_url':'https://wx.huatu.com/x',
                     'source_title':'公务员丨【2019联考】西藏省--《申论》试卷','answer_label':'华图网校参考答案（非官方）',
                     'answer':'“乡愁”，指的是离乡者向往乡村宁静、怀念美好记忆的心态。“诗和远方”，指的是把落后村落打造为富裕、文明、有序、亲近自然的村落的愿望。',
                     'scoring':'乡愁6分、诗和远方6分、语境逻辑12分、展望4分',
                     'expected_old_marker':'GPT-6 生成参考答案',
                     'anchors':[{'kind':'question','text':'家乡，不只是乡愁，还有诗和远方'},{'kind':'score','text':'这句话的理解。（30分）'},{'kind':'word_limit','text':'字数不超过300字'}]}
        self.plan_path=self.root/'plan.json'; self.write_plan()
    def tearDown(self): self.tmp.cleanup()
    def write_plan(self): self.plan_path.write_text(json.dumps(self.plan,ensure_ascii=False),encoding='utf-8')
    def run_tool(self,*args):
        return subprocess.run([sys.executable,'-I',str(TOOL),'--root',str(self.root),'--plan',str(self.plan_path),*args],capture_output=True,text=True)
    def test_write_replaces_gpt_answer(self):
        r=self.run_tool(); self.assertEqual(r.returncode,0,r.stderr); d=json.loads(r.stdout)
        r=self.run_tool('--write','--expect-after',d['after_sha256']); self.assertEqual(r.returncode,0,r.stderr)
        t=self.target.read_text(encoding='utf-8')
        self.assertIn('华图网校参考答案',t); self.assertNotIn('旧的GPT答案',t); self.assertIn('GPT-6生成参考答案题号: [4]',t)
        self.assertIn('来源清单:',t); self.assertIn('参考答案来源:',t)
    def test_source_sha_mismatch(self):
        self.plan['source_sha256']='0'*64; self.write_plan(); r=self.run_tool(); self.assertNotEqual(r.returncode,0)
    def test_answer_not_in_source(self):
        self.plan['answer']='这段答案不在来源快照中。'; self.write_plan(); r=self.run_tool(); self.assertNotEqual(r.returncode,0)
    def test_anchor_missing(self):
        self.plan['anchors'][0]['text']='不存在的锚点文本'; self.write_plan(); r=self.run_tool(); self.assertNotEqual(r.returncode,0)
    def test_old_marker_missing(self):
        self.target.write_text(PAPER.replace('GPT-6 生成参考答案','其他答案'),encoding='utf-8')
        self.plan['before_sha256']=sha(self.target.read_bytes()); self.write_plan(); r=self.run_tool(); self.assertNotEqual(r.returncode,0)
    def test_expect_after_mismatch(self):
        r=self.run_tool('--write','--expect-after','0'*64); self.assertNotEqual(r.returncode,0)
        self.assertIn('旧的GPT答案',self.target.read_text(encoding='utf-8'))
if __name__=='__main__': unittest.main()
