"""Explicit review plans remain bound to evidence and previewed output."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import huatu_fill


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReviewedPlan(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.paper = '省考/测试/2026/行测-统考.md'
        self.path = self.root / self.paper
        self.path.parent.mkdir(parents=True)
        rng = random.Random(173)
        self.stems = [''.join(rng.choices(string.ascii_letters, k=100)) for _ in range(12)]
        text = '---\n来源: "粉笔"\n校验状态: "候选"\n---\n\n'
        for n, st in enumerate(self.stems, 1):
            text += f'### 第 {n} 题\n\n' + (huatu_fill.STUB if n == 6 else st) + '\n\n'
        self.path.write_text(text, 'utf8')
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.archive = self.root / 'archive'
        self.archive.mkdir()
        raw = b'archived original source'
        (self.archive / 'content.html').write_bytes(raw)
        self.url = 'https://v.huatu.com/tiku/analysis/123'
        self.manifest = {'contentSha256': sha(raw), 'url': self.url, 'questionCount': 12}
        (self.archive / 'manifest.json').write_text(json.dumps(self.manifest), 'utf8')
        # Swap distant questions to lower the global LIS while preserving local anchors.
        order = [12, 11, 3, 4, 5, 6, 7, 8, 9, 10, 2, 1]
        self.meta = {'paperId': '999', 'title': '合成卷', 'capturedAt': '2026-11-06', 'url': self.url,
                     'sourceArchive': str(self.archive / 'manifest.json'), 'sourceHtmlSha256': sha(raw),
                     'questions': [{'stem_html': self.stems[n - 1], 'options': [{'label': c, 'html': c + '内容'} for c in 'ABCD'],
                                    'answer': 'A', 'analysis_html': '完整解析'} for n in order], 'images': []}
        self.catalog = self.root / 'catalog-source.json'
        self.catalog.write_text(json.dumps({'list': [{'title': '合成卷', 'description': '共12题', 'options': '{#paperid#:#999#}'}]}), 'utf8')
        (self.root / 'catalog').mkdir()
        (self.root / 'catalog/manifest.jsonl').write_text(json.dumps({'path': self.paper}) + '\n', 'utf8')
        self.review = {'schema_version': 1, 'paper': self.paper, 'reviewer': 'unit test', 'reviewed_at': '2026-11-06',
                       'source_html_sha256': sha(raw), 'source_manifest_sha256': sha((self.archive / 'manifest.json').read_bytes()),
                       'source_catalog': str(self.catalog), 'source_catalog_sha256': sha(self.catalog.read_bytes()),
                       'items': [{'q': 6, 'huatu': 6, 'method': 'neighbors', 'rationale': 'four matching local neighbors',
                                  'anchors': [{'q': n, 'huatu': n} for n in [4, 5, 7, 8]]}]}
        self.plan = self.root / 'plan.json'
        self.save()

    def save(self):
        (self.cache / 'paper.json').write_text(json.dumps(self.meta, ensure_ascii=False), 'utf8')
        self.review.update(paper_sha256=sha(self.path.read_bytes()), cache_sha256=sha((self.cache / 'paper.json').read_bytes()))
        self.plan.write_text(json.dumps(self.review, ensure_ascii=False), 'utf8')

    def run_fill(self, **kwargs):
        return huatu_fill.fill(self.paper, self.cache, root=self.root, reviewed_plan=self.plan, **kwargs)

    def test_preview_write_and_retry(self):
        before = self.path.read_bytes()
        preview = self.run_fill()
        self.assertFalse(preview['written'])
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'expect-after'):
            self.run_fill(write=True)
        result = self.run_fill(write=True, expect_after=preview['after_sha256'])
        self.assertTrue(result['written'])
        self.assertEqual(preview['after_sha256'], sha(self.path.read_bytes()))
        self.assertIn('显式人工复核', self.path.read_text('utf8'))
        self.assertTrue(list(self.path.parent.glob('图片/assets-huatu-999/review-*.json')))
        with self.assertRaisesRegex(ValueError, '过期'):
            self.run_fill(write=True, expect_after=preview['after_sha256'])

    def test_default_threshold_unchanged(self):
        self.assertEqual(0.8, huatu_fill.MIN_ANCHOR)
        report = huatu_fill.fill(self.paper, self.cache, root=self.root)
        self.assertLess(report['anchor'], 0.8)
        self.assertEqual([], report['fills'])
        self.assertEqual([6], [x['q'] for x in self.run_fill()['fills']])

    def test_stale_inputs(self):
        for path in [self.path, self.cache / 'paper.json', self.archive / 'manifest.json', self.archive / 'content.html', self.catalog]:
            with self.subTest(path=path):
                old = path.read_bytes()
                path.write_bytes(old + b' ')
                with self.assertRaises(ValueError):
                    self.run_fill()
                path.write_bytes(old)

    def test_missing_or_reused_source(self):
        old = self.meta['questions'][5].copy()
        for update in [{'answer': ''}, {'analysis_html': ''}, {'options': []}, {'stem_html': self.stems[4]}]:
            with self.subTest(update=update):
                self.meta['questions'][5] = dict(old, **update)
                self.save()
                with self.assertRaises(ValueError):
                    self.run_fill()

    def test_source_placeholders_are_rejected(self):
        for placeholder in ['暂缺', '缺失', '来源未提供', '暂无解析']:
            for field in ['stem_html', 'analysis_html', 'option']:
                with self.subTest(placeholder=placeholder, field=field):
                    source = self.meta['questions'][5]
                    original = json.loads(json.dumps(source))
                    if field == 'option':
                        source['options'][0]['html'] = placeholder
                    else:
                        source[field] = placeholder
                    self.save()
                    with self.assertRaisesRegex(ValueError, '不完整'):
                        self.run_fill()
                    self.meta['questions'][5] = original

    def test_two_plan_sources_cannot_repeat_the_same_question(self):
        text = self.path.read_text('utf8').replace(self.stems[8], huatu_fill.STUB)
        self.path.write_text(text, 'utf8')
        for i, question in enumerate(self.meta['questions']):
            question['stem_html'] = self.stems[i]
        self.meta['questions'][8]['stem_html'] = self.stems[5]
        self.review['items'].append({'q': 9, 'huatu': 9, 'method': 'neighbors', 'rationale': 'same offsets',
                                     'anchors': [{'q': n, 'huatu': n} for n in [7, 8, 10, 11]]})
        self.save()
        with self.assertRaisesRegex(ValueError, '本计划另一补题题干重复'):
            self.run_fill()

    def test_image_only_source_stem_is_rejected_before_duplicate_matching(self):
        self.meta['questions'][5]['stem_html'] = '<img src="https://image.example/shared.png">'
        self.save()
        with self.assertRaisesRegex(ValueError, '缺少可比文字题干'):
            self.run_fill()

    def test_duplicate_and_weak_evidence(self):
        original = self.review['items'][0].copy()
        for anchors in [[{'q': 4, 'huatu': 4}, {'q': 5, 'huatu': 5}],
                        [{'q': n, 'huatu': n} for n in [4, 4, 7, 8]],
                        [{'q': n, 'huatu': n} for n in [2, 3, 7, 8]]]:
            self.review['items'] = [dict(original, anchors=anchors)]
            self.save()
            with self.assertRaises(ValueError):
                self.run_fill()
        self.review['items'] = [original, original]
        self.save()
        with self.assertRaises(ValueError):
            self.run_fill()

    def test_elimination_requires_complete_bijection(self):
        item = self.review['items'][0]
        item.update(method='elimination', local_range=[4, 8], source_range=[4, 8])
        self.save()
        self.assertEqual(1, len(self.run_fill()['fills']))
        item['anchors'].pop()
        self.save()
        with self.assertRaisesRegex(ValueError, '逐题覆盖'):
            self.run_fill()

    def test_missing_image_never_writes(self):
        self.meta['questions'][5]['analysis_html'] += '<img src="https://image.example/a.png">'
        self.save()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '图片未下载'):
            self.run_fill()
        self.assertEqual(before, self.path.read_bytes())

    def test_invalid_images_cannot_render_empty_options(self):
        for option in ['<img>', '<img src=x>', '如上图所示']:
            with self.subTest(option=option):
                self.meta['questions'][5]['options'][0]['html'] = option
                self.save()
                with self.assertRaises(ValueError):
                    self.run_fill()

    def test_material_group_checks_actual_scope_and_full_material(self):
        text = self.path.read_text('utf8').replace('### 第 4 题', '## 材料 3\n\n同一份完整材料内容\n\n### 第 4 题')
        text = text.replace('### 第 9 题', '## 下一组\n\n### 第 9 题')
        self.path.write_text(text, 'utf8')
        self.meta['materials'] = [{'id': 'm1', 'html': '同一份完整材料内容'}]
        for q in self.meta['questions'][3:8]:
            q['material_id'] = 'm1'
        self.review['items'][0].update(method='material_group', local_range=[4, 8], source_range=[4, 8], local_material=3, source_material='m1')
        self.save()
        self.assertEqual(1, len(self.run_fill()['fills']))
        self.meta['questions'][0]['material_id'] = 'm1'
        self.save()
        with self.assertRaisesRegex(ValueError, '材料组'):
            self.run_fill()
        del self.meta['questions'][0]['material_id']
        self.meta['materials'].append(dict(self.meta['materials'][0]))
        self.save()
        with self.assertRaisesRegex(ValueError, '材料组'):
            self.run_fill()
        self.meta['materials'].pop()
        self.meta['materials'][0]['html'] += '<img src="https://image.example/chart.png">'
        self.save()
        with self.assertRaisesRegex(ValueError, '材料含图片'):
            self.run_fill()
        self.meta['materials'][0]['html'] = '完全不同的材料'
        self.save()
        with self.assertRaisesRegex(ValueError, '材料组'):
            self.run_fill()

    def test_exact_shared_passages_require_unique_combined_identity(self):
        # Reword both ends while keeping two long, unique shared conditions.
        original = self.stems[3]
        shared = [original[20:50], original[50:80]]
        self.meta['questions'][3]['stem_html'] = '不同开头' * 10 + ''.join(shared) + '不同结尾' * 10
        anchor = self.review['items'][0]['anchors'][0]
        anchor.update(shared_passages=shared, rationale='unique preserved conditions')
        self.save()
        self.assertEqual(1, len(self.run_fill()['fills']))
        anchor['shared_passages'] = [shared[0], shared[0]]
        self.save()
        with self.assertRaisesRegex(ValueError, '题干不匹配'):
            self.run_fill()

    def test_cli_preview_and_pinned_write(self):
        directory = self.root / 'tools'
        directory.mkdir()
        source = Path(huatu_fill.__file__).parent
        for name in ['huatu_fill.py', 'huatu_reviewed_plan.py']:
            shutil.copyfile(source / name, directory / name)
        command = [sys.executable, '-I', '-X', 'utf8', str(directory / 'huatu_fill.py'),
                   '--paper', self.paper, '--cache', str(self.cache), '--reviewed-plan', str(self.plan)]
        preview = subprocess.run(command, capture_output=True, encoding='utf8', check=True)
        expected = json.loads(preview.stdout)['after_sha256']
        written = subprocess.run(command + ['--write', '--expect-after', expected], capture_output=True, encoding='utf8', check=True)
        self.assertTrue(json.loads(written.stdout)['written'])
        self.assertEqual(expected, sha(self.path.read_bytes()))

    def test_concurrent_review_lock_prevents_writes(self):
        preview = self.run_fill()
        before = self.path.read_bytes()
        (self.root / 'catalog/.huatu-reviewed-fill.lock').write_text('another writer', 'utf8')
        with self.assertRaises(FileExistsError):
            self.run_fill(write=True, expect_after=preview['after_sha256'])
        self.assertEqual(before, self.path.read_bytes())

    def prepare_a2(self):
        original = ('下列关于《预备役人员法》的说法错误的是（ ）。\n\n'
                    'A. 预备役人员参加军事训练期间，军队为其购买人身意外伤害保险\n\n'
                    'B. 预备役人员从事个体经营，可以按照国家有关规定享受出资优惠政策\n\n'
                    'C. 缺失\n\n'
                    'D. 预备役军官分为预备役指挥管理军官和预备役专业技术军官')
        self.path.write_text(self.path.read_text('utf8').replace(huatu_fill.STUB, original), 'utf8')
        self.meta['questions'][5].update(
            stem_html='根据《中华人民共和国预备役人员法》，下列说法错误的是：',
            options=[{'label': c, 'html': value} for c, value in zip('ABCD', [
                '预备役军官分为预备役指挥管理军官和预备役专业技术军官',
                '预备役人员退出预备役的，其预备役军衔予以收回',
                '预备役人员参加军事训练期间，军队为其购买人身意外伤害保险',
                '预备役人员从事个体经营可以按照国家有关规定享受融资优惠政策'])],
            answer='B', analysis_html='军衔予以保留，因此B错误。')
        self.review['mode'] = 'A2'
        self.save()

    def test_a2_replaces_whole_option_group_and_archives_original(self):
        self.prepare_a2()
        old = self.path.read_text('utf8')
        preview = self.run_fill(option_q=6)
        self.assertEqual('reviewed-A2', preview['mode'])
        with self.assertRaisesRegex(ValueError, 'expect-after'):
            self.run_fill(option_q=6, write=True)
        result = self.run_fill(option_q=6, write=True, expect_after=preview['after_sha256'])
        new = self.path.read_text('utf8')
        self.assertTrue(result['written'])
        self.assertIn('B. 预备役人员退出预备役', new)
        self.assertIn('D. 预备役人员从事个体经营可以按照国家有关规定享受融资', new)
        self.assertIn('下列关于《预备役人员法》的说法错误的是', new)
        original = next(self.path.parent.glob('图片/assets-huatu-999/*-original.txt')).read_text('utf8')
        self.assertIn('出资优惠', original)
        self.assertIn('C. 缺失', original)
        huatu_fill.verify(old, new, {6: 5})

    def test_a2_plan_cannot_target_another_question_or_use_a1_entry(self):
        self.prepare_a2()
        with self.assertRaisesRegex(ValueError, '模式'):
            self.run_fill()
        self.review['items'][0]['q'] = 7
        self.save()
        with self.assertRaisesRegex(ValueError, '仅包含指定'):
            self.run_fill(option_q=6)

    def test_catalog_answerid_must_match_the_actual_source_url(self):
        self.catalog.write_text(json.dumps({'list': [{'title': '合成卷', 'description': '共12题', 'options': '{#answerid#:#123#}'}]}), 'utf8')
        self.review['source_catalog_sha256'] = sha(self.catalog.read_bytes())
        self.save()
        identity = self.run_fill()['source_identity']
        self.assertEqual('answerid', identity['catalog_locator'])
        self.assertEqual('缓存记录', identity['paperId_basis'])
        self.catalog.write_text(json.dumps({'list': [{'title': '合成卷', 'description': '共12题', 'options': '{#answerid#:#456#}'}]}), 'utf8')
        self.review['source_catalog_sha256'] = sha(self.catalog.read_bytes())
        self.save()
        with self.assertRaisesRegex(ValueError, '来源 ID'):
            self.run_fill()

    def test_io_failure_rolls_back_written_paper(self):
        preview = self.run_fill()
        before = self.path.read_bytes()
        manifest = self.root / 'catalog/manifest.jsonl'
        original_replace = os.replace
        failed = False

        def fail_once(source, destination):
            nonlocal failed
            if Path(destination).resolve() == manifest.resolve() and not failed:
                failed = True
                raise OSError('synthetic write failure')
            return original_replace(source, destination)

        with patch('os.replace', fail_once), self.assertRaises(OSError):
            self.run_fill(write=True, expect_after=preview['after_sha256'])
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse(list(self.path.parent.glob('图片/assets-huatu-999/review-*.json')))

    def test_persistent_manifest_error_does_not_interrupt_paper_rollback(self):
        preview = self.run_fill()
        before = self.path.read_bytes()
        manifest = self.root / 'catalog/manifest.jsonl'
        before_manifest = manifest.read_bytes()
        original_replace = os.replace

        def deny_manifest(source, destination):
            if Path(destination).resolve() == manifest.resolve():
                raise PermissionError('persistent manifest failure')
            return original_replace(source, destination)

        with patch('os.replace', deny_manifest), self.assertRaises(PermissionError):
            self.run_fill(write=True, expect_after=preview['after_sha256'])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(before_manifest, manifest.read_bytes())
        self.assertFalse(list(self.path.parent.glob('图片/assets-huatu-999/review-*.json')))
        self.assertFalse(list(self.root.rglob('.huatu-fill-*.tmp')))


if __name__ == '__main__':
    unittest.main()
