"""来源并集元数据解析的回归测试（不得伪造来源身份）。"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("source_provenance", ROOT / "tools" / "source_provenance.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestSourceProvenance(unittest.TestCase):
    def test_legacy_single_source(self):
        text = '---\n来源: "https://spa.fenbi.com/ti/exam/exercise/abc"\n---\n'
        fields, sources = MODULE.metadata(text)
        self.assertEqual(fields["来源"], "https://spa.fenbi.com/ti/exam/exercise/abc")
        self.assertEqual(sources, [])

    def test_union_is_not_flattened(self):
        text = ('---\n来源: ["gwy.dtiku.cn"]\n来源清单:\n'
                '  - 来源方: "公考加油站"\n'
                '    定位: "gwy.dtiku.cn/paper/51836"\n'
                '  - 来源方: "华图在线"\n'
                '    来源试卷ID: "4092439"\n'
                '    题号: [3, 6]\n'
                '---\n')
        fields, sources = MODULE.metadata(text)
        self.assertEqual(fields["来源"], ["gwy.dtiku.cn"])
        self.assertEqual([s["来源方"] for s in sources], ["公考加油站", "华图在线"])
        self.assertEqual(sources[1]["题号"], [3, 6])

    def test_real_huatu_case_has_multiple_sources(self):
        content = (ROOT / "省考" / "云南" / "2026" / "行测-统考.md").read_text(encoding="utf-8")
        meta, sources = MODULE.metadata(content)
        self.assertTrue(meta["来源"])
        self.assertEqual([s["来源方"] for s in sources], ["粉笔", "华图在线"])
        self.assertEqual(sources[1]["题号"], [3, 6])
        self.assertEqual(sources[1]["来源试卷ID"], "4135196")


if __name__ == "__main__":
    unittest.main()
