import hashlib, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'source_fill.py'

def sha(data): return hashlib.sha256(data).hexdigest()

PAPER = '''---
来源: "原来源"
校验状态: "候选"
---

# 测试卷

### 第 1 题

前锚题干内容完整。

### 第 2 题

粉笔暂未收录本题（来源缺题，题位保留）

<details><summary>第 2 题 · 答案与解析</summary>

**答案状态：unknown（来源未提供）**

</details>

### 第 3 题

后锚题干内容完整。
'''

EVIDENCE = '''来源：测试公开 PDF
题干：这是一个完整的新题干，包含足够长度的正文内容。
A. 选项甲
B. 选项乙
C. 选项丙
D. 选项丁
答案：B
前锚题干内容完整。
后锚题干内容完整。
'''

class SourceFillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'catalog').mkdir()
        (self.root / 'p.md').write_text(PAPER, encoding='utf-8')
        (self.root / 'ev.txt').write_text(EVIDENCE, encoding='utf-8')
        self.plan = {
            'schema_version': 1, 'paper': 'p.md', 'paper_sha256': sha(PAPER.encode()),
            'target_q': 2, 'source_q': 7, 'source_platform': '测试公开站',
            'source_url': 'https://example.test/paper/7', 'source_title': '测试卷',
            'source_region': '测试', 'source_year': 2025, 'source_variant': '统考',
            'source_evidence': [{'path': str(self.root/'ev.txt'), 'sha256': sha(EVIDENCE.encode()), 'role': 'stem_options'}],
            'anchors': [
                {'local_q': 1, 'source_q': 1, 'local_text': '前锚题干内容完整。', 'source_text': '前锚题干内容完整。'},
                {'local_q': 3, 'source_q': 3, 'local_text': '后锚题干内容完整。', 'source_text': '后锚题干内容完整。'},
            ],
            'stem': '这是一个完整的新题干，包含足够长度的正文内容。',
            'options': {'A': '选项甲', 'B': '选项乙', 'C': '选项丙', 'D': '选项丁'},
            'answer': 'B', 'explanation': '测试解析。', 'source_note': '网友回忆版，非官方',
            'reviewer': '测试复核', 'reviewed_at': '2026-11-07', 'images': [],
        }
        self.plan_path = self.root/'plan.json'
        self.plan_path.write_text(json.dumps(self.plan, ensure_ascii=False), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, '-I', str(TOOL), '--root', str(self.root), '--plan', str(self.plan_path), *args],
                              capture_output=True, text=True)

    def test_valid_preflight_and_write(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        report = json.loads(r.stdout)
        self.assertFalse(report['written'])
        after = report['after_sha256']
        r = self.run_tool('--write', '--expect-after', after)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root/'p.md').read_text(encoding='utf-8')
        self.assertNotIn('粉笔暂未收录本题', text)
        self.assertIn('**参考答案（公开题本站补录；非官方）**', text)
        self.assertIn('来源清单:', text)
        self.assertIn('第 1 题', text)
        self.assertIn('前锚题干内容完整。', text)

    def test_stale_paper_rejected(self):
        (self.root/'p.md').write_text(PAPER + '\n', encoding='utf-8')
        r = self.run_tool()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('paper_sha256', r.stderr)

    def test_placeholder_source_rejected(self):
        self.plan['stem'] = '题目正在全力以赴征集，将会在征集到后第一时间上传'
        self.plan_path.write_text(json.dumps(self.plan, ensure_ascii=False), encoding='utf-8')
        r = self.run_tool()
        self.assertNotEqual(r.returncode, 0)

    def test_bad_anchor_rejected(self):
        self.plan['anchors'][0]['local_text'] = '不存在的锚点'
        self.plan_path.write_text(json.dumps(self.plan, ensure_ascii=False), encoding='utf-8')
        r = self.run_tool()
        self.assertNotEqual(r.returncode, 0)

    def test_expect_after_mismatch_does_not_write(self):
        r = self.run_tool('--write', '--expect-after', '0'*64)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('粉笔暂未收录本题', (self.root/'p.md').read_text(encoding='utf-8'))

if __name__ == '__main__':
    unittest.main()
