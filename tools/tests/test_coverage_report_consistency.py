# -*- coding: utf-8 -*-
"""Keep the human-readable coverage totals synchronized with the manifest.

The coverage Markdown is maintained separately from cloud_quality's manifest
generator, so later image additions must not leave stale regional totals.
"""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from coverage_stats import load_rows, summarize  # noqa: E402


def parse_int(value):
    return int(value.strip().replace(",", ""))


class CoverageReportConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = summarize(load_rows())
        cls.coverage = (ROOT / "docs/COVERAGE.md").read_text(encoding="utf-8")
        cls.quality = json.loads(
            (ROOT / "reports/QUALITY-SUMMARY.json").read_text(encoding="utf-8"))

    def test_overall_manifest_and_quality_totals(self):
        total_images = self.summary["images"]
        self.assertEqual(total_images, self.quality["image_references"])
        self.assertEqual(self.summary["files"], self.quality["paper_files"])
        for field, expected in (
            ("试卷文件", self.summary["files"]),
            ("槽位", self.summary["slots"]),
            ("地区", self.summary["areas"]),
            ("题目", self.summary["questions"]),
            ("图片引用", total_images),
        ):
            hits = re.findall(
                rf"(?m)^\| {re.escape(field)} \|\s*([\d,]+)\s*\|$",
                self.coverage,
            )
            self.assertEqual(1, len(hits), field)
            self.assertEqual(expected, parse_int(hits[0]), field)

    def test_each_area_matches_current_manifest(self):
        section = self.coverage.split("## 分地区\n", 1)[1]
        section = section.split("\n---\n", 1)[0]
        found = {}
        for line in section.splitlines():
            if not line.startswith("| "):
                continue
            cells = [part.strip() for part in line.strip("|").split("|")]
            if len(cells) != 7 or not re.fullmatch(r"[\d,]+", cells[2]):
                continue
            area = cells[0]
            self.assertNotIn(area, found, f"duplicate coverage area: {area}")
            found[area] = {
                "files": parse_int(cells[2]),
                "xingce": parse_int(cells[3]),
                "shenlun": parse_int(cells[4]),
                "questions": parse_int(cells[5]),
                "images": parse_int(cells[6]),
            }
        self.assertEqual(set(self.summary["by_area"]), set(found))
        for area, expected in self.summary["by_area"].items():
            for field in ("files", "xingce", "shenlun", "questions", "images"):
                self.assertEqual(expected[field], found[area][field],
                                 f"{area} {field}")


if __name__ == "__main__":
    unittest.main()
