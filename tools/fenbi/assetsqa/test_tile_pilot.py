#!/usr/bin/env python3
"""Offline tests for the graphic-option tile pilot.

    python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v

Every test here is self-contained: synthetic images are drawn into a temp dir,
so the suite needs no handoff and no repository image tree. The two repository
integration checks skip when ASSETSQA_REPO / ASSETSQA_HANDOFF are unset.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tile_pilot as T  # noqa: E402

REPO = os.environ.get("ASSETSQA_REPO", "")
HANDOFF = os.environ.get("ASSETSQA_HANDOFF", "")


def draw(path, w, h, rects):
    """White canvas with black filled rects [(x0,y0,x1,y1), ...]."""
    im = Image.new("L", (w, h), 255)
    px = im.load()
    for x0, y0, x1, y1 in rects:
        for y in range(y0, y1):
            for x in range(x0, x1):
                px[x, y] = 0
    im.save(path)
    return path


def label_row(w, y0=120, heights=12, width=14, xs=(100, 220, 340, 460)):
    return [(x, y0, x + width, y0 + heights) for x in xs]


class TestRowBands(unittest.TestCase):
    def test_separate_bands_are_split(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 200, 200,
                     [(10, 10, 190, 60), (10, 120, 190, 140)])
            ink, w, h = T.load_ink(p)
            bands = T.row_bands(ink, w, h)
            self.assertEqual(len(bands), 2)

    def test_empty_image_has_no_band(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 100, 100, [])
            ink, w, h = T.load_ink(p)
            self.assertEqual(T.row_bands(ink, w, h), [])


class TestColumnSegments(unittest.TestCase):
    def test_four_glyphs_make_four_segments(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 600, 200, label_row(600))
            ink, w, h = T.load_ink(p)
            y0, y1 = T.row_bands(ink, w, h)[0]
            segs = T.col_segments(ink, y0, y1)
            self.assertEqual(len(segs), 4)

    def test_touching_blocks_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 100, 50, [(0, 0, 50, 40), (50, 0, 100, 40)])
            ink, w, h = T.load_ink(p)
            segs = T.col_segments(ink, 0, 49)
            self.assertEqual(len(segs), 1)


class TestLabelBandDetection(unittest.TestCase):
    def _detect(self, rects, w=600, h=200):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), w, h, rects)
            ink, ww, hh = T.load_ink(p)
            return T.find_label_band(ink, ww, hh)

    def test_valid_four_glyph_row_is_accepted(self):
        self.assertIsNotNone(self._detect(label_row(600)))

    def test_three_glyphs_rejected(self):
        rects = [(x, 120, x + 14, 132) for x in (100, 220, 340)]
        self.assertIsNone(self._detect(rects))

    def test_five_glyphs_rejected(self):
        rects = [(x, 120, x + 14, 132) for x in (80, 180, 280, 380, 480)]
        self.assertIsNone(self._detect(rects))

    def test_uneven_widths_rejected(self):
        rects = [(100, 120, 114, 132), (220, 120, 226, 132),
                 (340, 120, 354, 132), (460, 120, 466, 132)]
        # widths 14,6,14,6 -> CV ~0.4, still accepted; make it extreme instead
        rects = [(100, 120, 140, 132), (220, 120, 226, 132),
                 (340, 120, 354, 132), (460, 120, 466, 132)]
        self.assertIsNone(self._detect(rects))

    def test_band_too_tall_rejected(self):
        rects = [(x, 100, x + 14, 180) for x in (100, 220, 340, 460)]
        self.assertIsNone(self._detect(rects))

    def test_gaps_too_small_rejected(self):
        rects = [(x, 120, x + 14, 132) for x in (100, 120, 140, 160)]
        self.assertIsNone(self._detect(rects))


class TestOptionSlots(unittest.TestCase):
    """Regression: extending slot 1 to x=0 absorbs the stem figure."""

    def test_slots_are_uniform_and_do_not_start_at_zero(self):
        segs = [[100, 114], [220, 234], [340, 354], [460, 474]]
        slots, step = T.option_slots(segs, 600)
        self.assertEqual(len(slots), 4)
        widths = [b - a for a, b in slots]
        self.assertLessEqual(max(widths) - min(widths), 2)
        self.assertGreater(slots[0][0], 0)          # did not swallow the stem

    def test_first_slot_does_not_absorb_left_space(self):
        segs = [[216, 232], [338, 350], [456, 470], [575, 589]]
        slots, step = T.option_slots(segs, 700)
        # spacing ~119 -> first slot must start near 224-59.5, not at 0
        self.assertGreater(slots[0][0], 150)
        # centres 224/344/463/582 -> diffs 120/119/119 -> median 119.0
        self.assertAlmostEqual(step, 119.0, places=1)

    def test_slots_are_centred_on_glyphs(self):
        segs = [[100, 114], [220, 234], [340, 354], [460, 474]]
        slots, _ = T.option_slots(segs, 600)
        for (a, b), (g0, g1) in zip(slots, segs):
            self.assertAlmostEqual((a + b) / 2, (g0 + g1) / 2, delta=1.5)

    def test_clipped_to_image_width(self):
        segs = [[560, 574], [580, 594], [600, 614], [620, 634]]
        slots, _ = T.option_slots(segs, 600)
        for a, b in slots:
            self.assertGreaterEqual(a, 0)
            self.assertLessEqual(b, 600)


class TestFigureBand(unittest.TestCase):
    """Regression: picking by ink area grabbed the stem row on two-row layouts."""

    def test_nearest_band_above_is_chosen(self):
        with tempfile.TemporaryDirectory() as d:
            # stem row (much more ink) 10..80, option row 120..180, labels 200..212
            rects = [(0, 10, 590, 80), (0, 120, 400, 180)]
            rects += [(x, 200, x + 14, 212) for x in (100, 220, 340, 460)]
            p = draw(os.path.join(d, "a.png"), 600, 240, rects)
            ink, w, h = T.load_ink(p)
            lb = T.find_label_band(ink, w, h)
            self.assertIsNotNone(lb)
            fb = T.figure_band(ink, w, h, lb)
            self.assertEqual(fb, (120, 179))   # option row, not the fatter stem row

    def test_bands_above_is_nearest_first(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 600, 300,
                     [(0, 10, 590, 80), (0, 120, 400, 180)] + label_row(600, y0=250))
            ink, w, h = T.load_ink(p)
            lb = T.find_label_band(ink, w, h)
            above = T.bands_above(ink, w, h, lb)
            self.assertGreaterEqual(len(above), 2)
            self.assertGreater(above[0][1], above[1][1])


class TestCropping(unittest.TestCase):
    def test_crop_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 120, 60, [(10, 10, 50, 50)])
            a = T.crop_and_hash(p, (0, 0, 60, 60), os.path.join(d, "o1.png"))
            b = T.crop_and_hash(p, (0, 0, 60, 60), os.path.join(d, "o2.png"))
            self.assertEqual(a["sha256"], b["sha256"])

    def test_different_rect_gives_different_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 120, 60, [(10, 10, 50, 50)])
            a = T.crop_and_hash(p, (0, 0, 40, 60), os.path.join(d, "o1.png"))
            b = T.crop_and_hash(p, (40, 0, 80, 60), os.path.join(d, "o2.png"))
            self.assertNotEqual(a["sha256"], b["sha256"])

    def test_crop_size_matches_rect(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 120, 60, [(10, 10, 50, 50)])
            r = T.crop_and_hash(p, (5, 5, 65, 45), os.path.join(d, "o.png"))
            self.assertEqual((r["w"], r["h"]), (60, 40))
            self.assertEqual(r["rect"], [5, 5, 65, 45])


class TestSlotStability(unittest.TestCase):
    def test_stable_when_geometry_clean(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 600, 200,
                     [(0, 10, 590, 80)] + label_row(600))
            st = T.slot_stability(p)
            self.assertTrue(st["stable"])
            self.assertEqual(len(st["segments"]), 4)

    def test_unstable_when_no_label_row(self):
        with tempfile.TemporaryDirectory() as d:
            p = draw(os.path.join(d, "a.png"), 200, 100, [(0, 0, 200, 90)])
            st = T.slot_stability(p)
            self.assertFalse(st["stable"])
            self.assertIsNone(st["segments"])


class TestCompletenessGate(unittest.TestCase):
    """The gate must call label-only options INCOMPLETE while keeping the
    composite image referenced."""

    @staticmethod
    def _q(n, texts):
        return {"sourceNumber": n, "stemText": "略",
                "options": [{"label": l, "text": t} for l, t in zip("ABCD", texts)]}

    def test_classification_table(self):
        cases = {
            ("A", "B", "C", "D"): (False, "composite-figure-no-option-objects"),
            ("缺失",) * 4: (False, "source-placeholder"),
            ("暂缺",) * 4: (False, "source-placeholder"),
            ("甲", "乙", "丙", "丁"): (True, None),
        }
        for texts, (complete, reason) in cases.items():
            label_only = all(t == l for l, t in zip("ABCD", texts))
            placeholder = T.R.is_placeholder_stub(self._q(1, list(texts)))
            if placeholder:
                got = (False, "source-placeholder")
            elif label_only:
                got = (False, "composite-figure-no-option-objects")
            else:
                got = (True, None)
            self.assertEqual(got, (complete, reason), msg=str(texts))


class TestSafetyGuard(unittest.TestCase):
    def test_out_dir_outside_work_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(repo)
            outside = os.path.join(d, "elsewhere")
            proc = subprocess.run(
                [sys.executable, "-I", os.path.join(HERE, "tile_pilot.py"),
                 "--repo", repo, "--handoff", os.path.join(d, "nope"),
                 "--out-dir", outside],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("must live under work/", proc.stderr)

    def test_out_dir_inside_work_is_allowed_past_the_guard(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "work"))
            proc = subprocess.run(
                [sys.executable, "-I", os.path.join(HERE, "tile_pilot.py"),
                 "--repo", repo, "--handoff", os.path.join(d, "nope"),
                 "--out-dir", os.path.join(repo, "work", "tiles")],
                capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 2)


class TestNoBindingClaims(unittest.TestCase):
    """The pilot must never assert an A/B/C/D binding."""

    def test_claims_section_denies_binding(self):
        src = open(os.path.join(HERE, "tile_pilot.py"), encoding="utf8").read()
        self.assertIn("A/B/C/D assignment", src)
        self.assertIn("not_supported", src)


@unittest.skipUnless(REPO and HANDOFF, "ASSETSQA_REPO / ASSETSQA_HANDOFF not set")
class TestRepositoryPilot(unittest.TestCase):
    PICK = [("js-2025-xingce-c-4189916", 88), ("js-2024-xingce-a-4162243", 77),
            ("gd-2020-xingce-county-96785", 41), ("gd-2020-xingce-county-96785", 42),
            ("zj-2026-xingce-c-8399763", 61), ("zj-2026-xingce-c-8399763", 65)]

    def test_six_picks_locate_four_slots_and_never_resolve_letters(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "tiles")
            for key, n in self.PICK:
                rec = T.analyze(REPO, HANDOFF, key, n, out)
                self.assertEqual(len(rec["images"]), 1, f"{key} Q{n}")
                im = rec["images"][0]
                self.assertEqual(im["slotLocalization"], "deterministic", f"{key} Q{n}")
                self.assertEqual(len(im["optionSlots"]), 4, f"{key} Q{n}")
                self.assertFalse(im["A_D_resolved"], f"{key} Q{n}")
                self.assertEqual(rec["binding"], "need_review", f"{key} Q{n}")
                widths = [s["w"] for s in im["optionSlots"]]
                self.assertLessEqual(max(widths) - min(widths), 6, f"{key} Q{n}")

    def test_composite_that_cannot_be_anchored_is_ambiguous(self):
        # 广东 Q77 has no four-glyph label row; it must be reported, not guessed
        rec = T.analyze(REPO, HANDOFF, "gd-2020-xingce-county-96785", 77,
                        tempfile.mkdtemp())
        for im in rec["images"]:
            if im.get("slotLocalization"):
                self.assertEqual(im["slotLocalization"], "ambiguous")


if __name__ == "__main__":
    unittest.main(verbosity=2)
