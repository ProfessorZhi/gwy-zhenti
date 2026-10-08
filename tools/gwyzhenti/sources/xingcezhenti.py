# -*- coding: utf-8 -*-
"""ERRRC/xingcezhenti adapter：卷×模块 粒度清单。只读，不产正文。"""
import os

from .. import mdread
from ..naming import Unparsed, classify
from .base import ScanResult, SourceAdapter

FAMILY = "xingcezhenti"

# 目录序 **就是** 行测标准顺序（政治理论在最前，覆盖 2025+ 国考新增）
MODULE_DIRS = (
    "01-政治理论", "02-常识判断", "03-言语理解与表达",
    "04-数量关系", "05-判断推理", "06-资料分析",
)


class XingceZhentiAdapter(SourceAdapter):
    family = FAMILY

    def scan(self, root):
        res = ScanResult()
        for module_dir in MODULE_DIRS:
            abs_dir = os.path.join(root, module_dir)
            if not os.path.isdir(abs_dir):
                continue
            for name in sorted(os.listdir(abs_dir)):
                if not name.endswith(".md") or name == "README.md":
                    continue
                relpath = "%s/%s" % (module_dir, name)
                self._one(os.path.join(abs_dir, name), relpath, res)
        return res

    def _one(self, abspath, relpath, res):
        with open(abspath, encoding="utf-8") as fh:
            text = fh.read()
        fm = mdread.read_frontmatter(text)
        title = fm.get("试卷", os.path.splitext(os.path.basename(relpath))[0])
        module = fm.get("模块", os.path.basename(os.path.dirname(relpath)))
        region = fm.get("地区", "")
        year = fm.get("年份", "")
        try:
            classify(region, year, title)
        except Unparsed as exc:
            # 分流：**有意排除**（非国省考地区 / 试卷名含排除词）进 excluded；
            # **解析不了**（如「地区字段为空」）是缺陷，必须进 unparsed 被 G1 盯住。
            bucket = res.unparsed if exc.reason.startswith("地区字段为空") else res.excluded
            bucket.append({
                "family": FAMILY, "title": title, "region": region, "year": year,
                "module": module, "relpath": relpath, "reason": exc.reason,
            })
            return
        imgs = mdread.iter_images(text)
        declared = fm.get("题数", "")
        actual = mdread.count_questions(text)
        res.records.append({
            "family": FAMILY,
            "title": title,
            "region": region,
            "year": year,
            "module": module,
            "n_questions": actual,
            "relpath": relpath,
            "images_题目": sum(1 for t, _ in imgs if t == "题目图"),
            "images_公式": sum(1 for t, _ in imgs if t == "公式图"),
            # 台账用：源自报题数，供 G1 对账（不参与导出）
            "declared_questions": int(declared) if declared.isdigit() else -1,
        })
