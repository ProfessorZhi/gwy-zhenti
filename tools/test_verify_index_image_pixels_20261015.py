"""Small real Git-index regression cases; never stages the working repository."""
import io
import json
import os
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import verify_index_image_pixels_20261015 as verifier


class IndexPixelTests(unittest.TestCase):
    def setUp(self):
        parent = (Path('D:/artifacts/gwy-quality-audit-20261015') if os.name == 'nt'
                  else Path(tempfile.gettempdir()) / 'gwy-index-image-tests')
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='index-pixels-review-', dir=parent)
        self.root = Path(self.temp.name).resolve()
        assert self.root.parent == parent.resolve()
        self.git('init', '-q')
        self.paper = self.root / '国考/2020/行测-test.md'
        self.paper.parent.mkdir(parents=True)
        (self.root / '图片').mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(verifier.command(*args), cwd=self.root,
                                       env=verifier.ENV, stderr=subprocess.STDOUT)

    def write_image(self, name='good.png', animated=False):
        target = self.root / '图片' / name
        if animated:
            images = [Image.new('RGB', (12, 9), color) for color in ('red', 'blue', 'green')]
            images[0].save(target, save_all=True, append_images=images[1:], duration=30, loop=0)
        else:
            Image.new('RGB', (12, 9), 'blue').save(target)
        return target

    def stage_paper(self, name='good.png'):
        self.paper.write_text(f'![test](../../图片/{name})\n', encoding='utf8')
        self.git('add', '--', '国考', '图片')

    def verify(self):
        return verifier.verify(self.root, progress=False)

    def test_good_png_from_index_even_if_worktree_image_is_corrupt(self):
        image = self.write_image()
        self.stage_paper()
        image.write_bytes(b'working-tree corruption is irrelevant to staged publication')
        result = self.verify()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['decoded_frames'], 1)

    def test_all_frames_of_staged_gif_are_loaded(self):
        self.write_image('three.gif', animated=True)
        self.stage_paper('three.gif')
        result = self.verify()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['decoded_frames'], 3)

    def test_identical_blob_copies_bind_all_paths_and_decode_every_gif_frame(self):
        first=self.write_image('first.gif', animated=True)
        (self.root/'图片/second.gif').write_bytes(first.read_bytes())
        self.paper.write_text('![one](../../图片/first.gif)\n![two](../../图片/second.gif)\n',encoding='utf8')
        self.git('add','--','国考','图片')
        result=self.verify()
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['unique_images'],2)
        self.assertEqual(result['unique_git_image_blobs'],1)
        self.assertEqual(result['decoded_frames'],3)
        self.assertEqual(result['validated_image_path_frames'],6)
        # Both paths still participate in the final index-change guard.
        with self.mutate_at_final_snapshot(lambda: self.git('rm','--cached','图片/second.gif')):
            with self.assertRaisesRegex(ValueError,'index changed'):
                self.verify()

    def test_same_corrupt_blob_reports_each_referenced_path(self):
        for name in ('one.png','two.png'):(self.root/'图片'/name).write_bytes(b'not a real image')
        self.paper.write_text('![one](../../图片/one.png)\n![two](../../图片/two.png)\n',encoding='utf8')
        self.git('add','--','国考','图片')
        result=self.verify()
        self.assertEqual(result['status'],'failed');self.assertEqual(result['failed_images'],2)
        self.assertEqual({x['path'] for x in result['errors']},{'图片/one.png','图片/two.png'})

    def test_staged_bad_image_not_hidden_by_worktree_markdown(self):
        (self.root / '图片/bad.png').write_bytes(b'not an image')
        self.stage_paper('bad.png')
        self.paper.write_text('worktree removed image reference\n', encoding='utf8')
        result = self.verify()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failed_images'], 1)
        self.assertEqual(result['errors'][0]['path'], '图片/bad.png')

    def test_staged_paper_not_skipped_if_worktree_paper_deleted(self):
        self.write_image()
        self.stage_paper()
        self.paper.unlink()
        self.assertEqual(self.verify()['unique_images'], 1)

    def test_reference_missing_from_index_is_rejected(self):
        self.stage_paper('missing.png')
        with self.assertRaisesRegex(ValueError, 'not staged'):
            self.verify()

    def mutate_at_final_snapshot(self, action):
        original = verifier.index_snapshot
        calls = []

        def snapshot(root):
            calls.append(True)
            if len(calls) == 2:
                action()
            return original(root)

        return patch.object(verifier, 'index_snapshot', snapshot)

    def test_new_indexed_paper_is_not_silently_accepted(self):
        self.write_image()
        self.stage_paper()

        def add_paper():
            p = self.paper.with_name('申论-new.md')
            p.write_text('new staged exam\n', encoding='utf8')
            self.git('add', '--', '国考')

        with self.mutate_at_final_snapshot(add_paper):
            with self.assertRaisesRegex(ValueError, 'index changed.*markdown'):
                self.verify()

    def test_new_indexed_image_is_not_silently_accepted(self):
        self.write_image()
        self.stage_paper()

        def add_image():
            self.write_image('added.png')
            self.git('add', '--', '图片')

        with self.mutate_at_final_snapshot(add_image):
            with self.assertRaisesRegex(ValueError, 'index changed.*images'):
                self.verify()

    def test_changed_staged_markdown_is_rejected(self):
        self.write_image()
        self.stage_paper()

        def change_paper():
            self.paper.write_text('changed staged Markdown\n', encoding='utf8')
            self.git('add', '--', '国考')

        with self.mutate_at_final_snapshot(change_paper):
            with self.assertRaisesRegex(ValueError, 'index changed.*markdown'):
                self.verify()

    def test_removed_unreferenced_index_image_still_changes_guard(self):
        self.write_image()
        self.write_image('unused.png')
        self.stage_paper()

        def remove_image():
            self.git('rm', '--cached', '--', '图片/unused.png')

        with self.mutate_at_final_snapshot(remove_image):
            with self.assertRaisesRegex(ValueError, 'index changed.*images'):
                self.verify()

    def test_truncated_later_gif_frame_fails_full_pixel_load(self):
        image = self.write_image('broken.gif', animated=True)
        image.write_bytes(image.read_bytes()[:-12])
        self.stage_paper('broken.gif')
        with patch.object(verifier.ImageFile, 'LOAD_TRUNCATED_IMAGES', True):
            result = self.verify()
            self.assertTrue(verifier.ImageFile.LOAD_TRUNCATED_IMAGES)
        self.assertEqual(result['status'], 'failed')
        self.assertGreaterEqual(result['decoded_frames'], 1)

    def test_hash_mismatch_is_rejected(self):
        self.write_image()
        self.stage_paper()
        oid = self.git('rev-parse', ':图片/good.png').decode('ascii').strip()
        loose = self.root / '.git/objects' / oid[:2] / oid[2:]
        raw = zlib.decompress(loose.read_bytes())
        raw = raw[:-1] + bytes([raw[-1] ^ 1])
        assert loose.resolve().is_relative_to(self.root)
        loose.chmod(0o600)  # Git's new loose objects are read-only on Windows.
        loose.write_bytes(zlib.compress(raw))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.verify()

    def test_truncated_batch_stream_fails(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            verifier.read_exact(io.BytesIO(b'abc'), 4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
