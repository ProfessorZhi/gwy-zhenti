# -*- coding: utf-8 -*-
"""华图补题工具：用合成试卷与合成华图缓存验证对齐、写入与保护。全部为虚构文本。"""
import json
import shutil
import sys
import tempfile
import unittest
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
    return {"paperId": "999", "title": "合成", "capturedAt": "2026-11-04T00:00:00Z", "questions": qs,
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
        row = json.loads((self.root / "catalog/manifest.jsonl").read_text())
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

    def test_tail_gap_needs_matching_paper_length(self):
        report = self.run_fill({7, 8}, huatu_paper(), write=False)
        self.assertEqual([7, 8], [f["q"] for f in report["fills"]])
        longer = huatu_paper()
        longer["questions"].append({"stem_html": "<p>华图多出来的一题</p>", "options": [], "answer": "A"})
        report = self.run_fill({7, 8}, longer, write=False)
        self.assertEqual([], report["fills"])


if __name__ == "__main__":
    unittest.main()
