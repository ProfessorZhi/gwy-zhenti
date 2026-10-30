# -*- coding: utf-8 -*-
"""文字卫生：正文里不许留转写残留的部首字、兼容字和不可见字符。

2026-10-30 清过一遍（reports/CHARNORM-20261030.jsonl）：PDF 转写的旧来源卷混进
CJK 部首补充区字符（⺠→民、⻓→长），题库富文本夹着零宽字符。它们都能显示、看不见，
但按词搜索和题面对齐会漏，成本极低又容易复发，所以钉成测试。

允许的例外（有意保留）：
- 全角标点、全角下划线 ＿、NBSP 与全角空格——选词填空的填空横线；
- ㎡——NFKC 会拆成 m2，比原字符更差。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOTS = ("国考", "省考")

FORBIDDEN = {
    "CJK 部首补充区 (U+2E80–U+2EFF)": re.compile("[⺀-⻿]"),
    "CJK 兼容汉字 (U+F900–U+FAFF)": re.compile("[豈-﫿]"),
    "小写形变 (U+FE50–U+FE6F)": re.compile("[﹐-﹯]"),
    "零宽字符": re.compile("[\u200b\u200c\u200d\ufeff]"),
    "行分隔符": re.compile("[\u2028\u2029]"),
}


class TextHygiene(unittest.TestCase):
    def test_corpus_has_no_transcription_artifacts(self):
        found = []
        for top in CORPUS_ROOTS:
            for path in sorted((ROOT / top).rglob("*.md")):
                text = path.read_text(encoding="utf-8")
                for label, pattern in FORBIDDEN.items():
                    for m in pattern.finditer(text):
                        found.append("%s: %s %r" % (
                            path.relative_to(ROOT).as_posix(), label, m.group()))
        self.assertEqual([], found)

    def test_both_renderers_strip_invisible_characters(self):
        # 清完还得防复发：两个渲染器都要在正文出口把零宽字符去掉。
        for rel in ("tools/fenbi/src/render.mjs", "tools/gwyzhenti/render.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("INVISIBLE", text, rel)
            self.assertIn("200b", text, rel)


if __name__ == "__main__":
    unittest.main()
