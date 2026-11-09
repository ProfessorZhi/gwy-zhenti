# -*- coding: utf-8 -*-
import copy, hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'source_fill.py'

def sha(data): return hashlib.sha256(data).hexdigest()

PAPER = '''---
来源: "原来源"
校验状态: "候选"
---

# 测试卷

### 第 1 题

本地前锚题干完整内容。

### 第 2 题

粉笔暂未收录本题（来源缺题，题位保留）

<details><summary>第 2 题 · 答案与解析</summary>

**答案状态：unknown（来源未提供）**

**解析状态：unknown（来源未提供）**

</details>

### 第 3 题

本地后锚题干完整内容。
'''

SNAP = {
    'schema_version': 1, 'capture_method': 'test', 'url': 'https://example.test/paper/中文',
    'answer_url': 'https://example.test/answer', 'title': '测试源卷',
    'captured_at': '2026-11-08T00:00:00+00:00', 'question_count': 3,
    'questions': {
        '6': {'number': 6, 'stem': '源侧前锚题干内容。', 'options': {'A': '甲', 'B': '乙', 'C': '丙', 'D': '丁'}, 'answer': 'A'},
        '7': {'number': 7, 'stem': '这是一个完整的新题干，包含足够长度的正文内容。',
              'options': {'A': '选项甲', 'B': '选项乙', 'C': '选项丙', 'D': '选项丁'}, 'answer': 'B'},
        '8': {'number': 8, 'stem': '源侧后锚题干内容。', 'options': {'A': '甲', 'B': '乙', 'C': '丙', 'D': '丁'}, 'answer': 'C'},
        '9': {'number': 9, 'stem': '另一道后锚题干。', 'options': {'A': '甲', 'B': '乙', 'C': '丙', 'D': '丁'}, 'answer': 'D'},
    },
}

def filled_paper(source_q=7, answer='B'):
    return f'''---
来源: "原来源"
来源清单:
  - 来源方: "测试公开站"
    定位: "https://example.test/paper/%E4%B8%AD%E6%96%87"
    题号: [{source_q}]
    用途: "补第 2 题题干、选项、参考答案"
    证据: "测试源卷"
    核验: "测试"
校验状态: "候选；{source_q} 公开题本站补入第 2 题（非官方，来源见来源清单）"
---

# 测试卷

### 第 1 题

本地前锚题干完整内容。

### 第 2 题

这是一个完整的新题干，包含足够长度的正文内容。

**A**. 选项甲

**B**. 选项乙

**C**. 选项丙

**D**. 选项丁

<details><summary>第 2 题 · 答案与解析</summary>

**参考答案（公开题本站补录；非官方）**

{answer}

**解析**

测试解析。

**来源**：测试公开站《测试源卷》https://example.test/paper/%E4%B8%AD%E6%96%87 第{source_q}题；网友回忆版，非官方

</details>

### 第 3 题

本地后锚题干完整内容。
'''

class SourceFillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'catalog').mkdir()
        (self.root / 'p.md').write_text(PAPER, encoding='utf-8')
        self.snap_path = self.root / 'snap.json'
        self.snap = copy.deepcopy(SNAP)
        self.snap_path.write_text(json.dumps(self.snap, ensure_ascii=False), encoding='utf-8')
        self.plan = {
            'schema_version': 1, 'paper': 'p.md', 'paper_sha256': sha(PAPER.encode()),
            'target_q': 2, 'source_q': 7, 'source_platform': '测试公开站',
            'source_url': 'https://example.test/paper/中文', 'source_title': '测试源卷',
            'source_region': '测试', 'source_year': 2025, 'source_variant': '统考',
            'source_snapshot': {'path': str(self.snap_path), 'sha256': sha(self.snap_path.read_bytes())},
            'anchors': [
                {'local_q': 1, 'source_q': 6, 'local_text': '本地前锚题干完整内容。', 'source_text': '源侧前锚题干内容。'},
                {'local_q': 3, 'source_q': 8, 'local_text': '本地后锚题干完整内容。', 'source_text': '源侧后锚题干内容。'},
            ],
            'stem': '这是一个完整的新题干，包含足够长度的正文内容。',
            'options': {'A': '选项甲', 'B': '选项乙', 'C': '选项丙', 'D': '选项丁'},
            'answer': 'B', 'explanation': '测试解析。', 'source_note': '网友回忆版，非官方',
            'reviewer': '测试复核', 'reviewed_at': '2026-11-08', 'images': [],
        }
        self.plan_path = self.root / 'plan.json'
        self.write_plan()

    def tearDown(self): self.tmp.cleanup()

    def write_plan(self):
        self.plan_path.write_text(json.dumps(self.plan, ensure_ascii=False), encoding='utf-8')

    def run_tool(self, *args):
        return subprocess.run([sys.executable, '-I', str(TOOL), '--root', str(self.root),
                               '--plan', str(self.plan_path), *args], capture_output=True, text=True)

    def test_valid_preflight_and_write(self):
        r = self.run_tool(); self.assertEqual(r.returncode, 0, r.stderr)
        report = json.loads(r.stdout); self.assertFalse(report['written'])
        r = self.run_tool('--write', '--expect-after', report['after_sha256'])
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root/'p.md').read_text(encoding='utf-8')
        self.assertNotIn('粉笔暂未收录本题', text)
        self.assertIn('**参考答案（公开题本站补录；非官方）**', text)
        self.assertIn('来源清单:', text)
        self.assertIn('第7题', text)
        self.assertIn('%E4%B8%AD%E6%96%87', text)  # normalized URL in body

    def test_stale_paper_rejected(self):
        (self.root/'p.md').write_text(PAPER + '\n', encoding='utf-8')
        r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('paper_sha256', r.stderr)

    def test_placeholder_source_rejected(self):
        self.plan['stem'] = '题目正在全力以赴征集，将会在征集到后第一时间上传'
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)

    def test_bad_local_anchor_rejected(self):
        self.plan['anchors'][0]['local_text'] = '不存在的锚点'
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)

    def test_missing_source_neighbour_rejected(self):
        del self.snap['questions']['8']
        self.snap_path.write_text(json.dumps(self.snap, ensure_ascii=False), encoding='utf-8')
        self.plan['source_snapshot']['sha256'] = sha(self.snap_path.read_bytes())
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('q8', r.stderr)

    def test_target_stem_mismatch_rejected(self):
        self.plan['stem'] = '这是一个与来源完全不同的题干，长度也足够。'
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('题干', r.stderr)

    def test_answer_mismatch_rejected(self):
        self.plan['answer'] = 'C'
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('答案', r.stderr)

    def test_url_mismatch_rejected(self):
        self.plan['source_url'] = 'https://example.test/other'
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('URL', r.stderr)

    def test_anchor_text_from_wrong_question_rejected(self):
        # text exists in q6, but the anchor claims q8
        self.plan['anchors'][1]['source_text'] = '源侧前锚题干内容。'
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('q8', r.stderr)

    def test_expect_after_mismatch_does_not_write(self):
        r = self.run_tool('--write', '--expect-after', '0'*64)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('粉笔暂未收录本题', (self.root/'p.md').read_text(encoding='utf-8'))

    def test_metadata_only_syncs_frontmatter_and_body(self):
        # content is source q8, but the old metadata/source line says q7
        paper8 = filled_paper(7).replace('这是一个完整的新题干，包含足够长度的正文内容。', '源侧后锚题干内容。')
        paper8 = paper8.replace('**A**. 选项甲', '**A**. 甲').replace('**B**. 选项乙', '**B**. 乙')
        paper8 = paper8.replace('**C**. 选项丙', '**C**. 丙').replace('**D**. 选项丁', '**D**. 丁')
        paper8 = paper8.replace('**参考答案（公开题本站补录；非官方）**\n\nB', '**参考答案（公开题本站补录；非官方）**\n\nC')
        (self.root/'p.md').write_text(paper8, encoding='utf-8')
        self.plan = {
            'schema_version': 1, 'paper': 'p.md', 'paper_sha256': sha((self.root/'p.md').read_bytes()),
            'target_q': 2, 'source_q': 8, 'old_source_q': 7, 'metadata_only': True,
            'source_platform': '测试公开站', 'source_url': 'https://example.test/paper/中文',
            'source_title': '测试源卷', 'source_region': '测试', 'source_year': 2025,
            'source_variant': '统考',
            'source_snapshot': {'path': str(self.snap_path), 'sha256': sha(self.snap_path.read_bytes())},
            'reviewer': '测试复核', 'reviewed_at': '2026-11-08',
        }
        self.write_plan(); r = self.run_tool('--metadata-only')
        self.assertEqual(r.returncode, 0, r.stderr)
        report = json.loads(r.stdout)
        r = self.run_tool('--metadata-only', '--write', '--expect-after', report['after_sha256'])
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root/'p.md').read_text(encoding='utf-8')
        self.assertIn('题号: [8]', text)
        self.assertIn('第8题', text)
        self.assertNotIn('题号: [7]', text)

    def test_withdraw_restores_stub_and_removes_entry(self):
        (self.root/'p.md').write_text(filled_paper(7), encoding='utf-8')
        self.plan = {
            'schema_version': 1, 'paper': 'p.md', 'paper_sha256': sha((self.root/'p.md').read_bytes()),
            'target_q': 2, 'withdraw': True, 'reason': '源侧锚点不成立',
            'expected_current': {
                'stem': '这是一个完整的新题干，包含足够长度的正文内容。',
                'options': {'A': '选项甲', 'B': '选项乙', 'C': '选项丙', 'D': '选项丁'},
                'answer': 'B',
            },
            'reviewer': '测试复核', 'reviewed_at': '2026-11-08',
        }
        self.write_plan(); r = self.run_tool('--withdraw')
        self.assertEqual(r.returncode, 0, r.stderr)
        report = json.loads(r.stdout)
        r = self.run_tool('--withdraw', '--write', '--expect-after', report['after_sha256'])
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root/'p.md').read_text(encoding='utf-8')
        self.assertIn('粉笔暂未收录本题', text)
        self.assertNotIn('来源清单:', text)
        self.assertIn('撤回第 2 题', text)

    def test_receipt_has_normalized_url_and_sha_chain(self):
        r = self.run_tool(); report = json.loads(r.stdout)
        receipt = self.root/'receipt.jsonl'
        r = self.run_tool('--write', '--expect-after', report['after_sha256'], '--receipt', str(receipt))
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads(receipt.read_text(encoding='utf-8').strip())
        self.assertEqual(rec['source_url'], 'https://example.test/paper/%E4%B8%AD%E6%96%87')
        self.assertEqual(rec['before_sha256'], report['before_sha256'])
        self.assertEqual(rec['after_sha256'], report['after_sha256'])
        self.assertEqual(rec['source_snapshot_sha256'], self.plan['source_snapshot']['sha256'])

    def _enable_image(self):
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        self.img = self.root/'img.png'
        self.img.write_bytes(png)
        self.pdf = self.root/'src.pdf'
        self.pdf.write_bytes(b'%PDF-1.4 test')
        self.snap['questions']['7']['stem'] += ' {{IMG1}}'
        self.snap_path.write_text(json.dumps(self.snap, ensure_ascii=False), encoding='utf-8')
        self.plan['stem'] += ' {{IMG1}}'
        self.plan['source_snapshot']['sha256'] = sha(self.snap_path.read_bytes())
        self.plan['assets_dir'] = 'assets-test'
        self.plan['source_pdf'] = {'url': 'https://example.test/src.pdf', 'sha256': sha(self.pdf.read_bytes()),
                                   'path': str(self.pdf)}
        self.plan['images'] = [{'source_path': str(self.img), 'sha256': sha(png),
                                'filename': sha(png) + '.png', 'alt': '图1', 'marker': '{{IMG1}}'}]
        self.write_plan()

    def test_image_write_copies_and_renders(self):
        self._enable_image()
        r = self.run_tool(); self.assertEqual(r.returncode, 0, r.stderr)
        report = json.loads(r.stdout)
        r = self.run_tool('--write', '--expect-after', report['after_sha256'])
        self.assertEqual(r.returncode, 0, r.stderr)
        target = self.root/'图片'/'assets-test'/(sha(self.img.read_bytes()) + '.png')
        self.assertTrue(target.is_file())
        text = (self.root/'p.md').read_text(encoding='utf-8')
        self.assertIn('![图1](图片/assets-test/' + sha(self.img.read_bytes()) + '.png)', text)

    def test_image_sha_mismatch_rejected(self):
        self._enable_image()
        self.plan['images'][0]['sha256'] = '0'*64
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('图片哈希', r.stderr)

    def test_image_marker_missing_rejected(self):
        self._enable_image()
        self.plan['stem'] = self.plan['stem'].replace('{{IMG1}}', '')
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('marker', r.stderr)

    def test_image_path_traversal_rejected(self):
        self._enable_image()
        self.plan['images'][0]['filename'] = '../evil.png'
        self.write_plan(); r = self.run_tool(); self.assertNotEqual(r.returncode, 0)
        self.assertIn('filename', r.stderr)

    def test_metadata_sync_covers_known_defect_pairs(self):
        # 广西 q35 (35->34), 广西 q59 (59->67), 河北 q94 (95->106)
        for old_q, new_q in [(35, 34), (59, 67), (95, 106)]:
            with self.subTest(old=old_q, new=new_q):
                snap = {'schema_version': 1, 'capture_method': 'test', 'url': 'https://example.test/paper/中文',
                        'answer_url': '', 'title': '测试源卷', 'captured_at': '2026-11-08T00:00:00+00:00',
                        'question_count': 3, 'questions': {}}
                for n in (new_q-1, new_q, new_q+1):
                    snap['questions'][str(n)] = {'number': n, 'stem': '这是一个完整的新题干，包含足够长度的正文内容。',
                        'options': {'A': '选项甲', 'B': '选项乙', 'C': '选项丙', 'D': '选项丁'}, 'answer': 'B'}
                self.snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
                paper = filled_paper(old_q)
                (self.root/'p.md').write_text(paper, encoding='utf-8')
                plan = {'schema_version': 1, 'paper': 'p.md', 'paper_sha256': sha(paper.encode()),
                        'target_q': 2, 'source_q': new_q, 'old_source_q': old_q, 'metadata_only': True,
                        'source_platform': '测试公开站', 'source_url': 'https://example.test/paper/中文',
                        'source_title': '测试源卷', 'source_region': '测试', 'source_year': 2025,
                        'source_variant': '统考',
                        'source_snapshot': {'path': str(self.snap_path), 'sha256': sha(self.snap_path.read_bytes())},
                        'reviewer': '测试复核', 'reviewed_at': '2026-11-08'}
                self.plan = plan; self.write_plan()
                r = self.run_tool('--metadata-only'); self.assertEqual(r.returncode, 0, r.stderr)
                report = json.loads(r.stdout)
                r = self.run_tool('--metadata-only', '--write', '--expect-after', report['after_sha256'])
                self.assertEqual(r.returncode, 0, r.stderr)
                text = (self.root/'p.md').read_text(encoding='utf-8')
                self.assertIn(f'题号: [{new_q}]', text)
                self.assertIn(f'第{new_q}题', text)
                self.assertNotIn(f'题号: [{old_q}]', text)

if __name__ == '__main__':
    unittest.main()
