# -*- coding: utf-8 -*-
"""ERRRC/xingcezhenti adapter：卷×模块 粒度清单。只读，不产正文。"""
import os

from .. import mdread
from ..naming import Unparsed, classify
from .base import ScanResult, SourceAdapter

FAMILY = "xingcezhenti"

# 本 adapter 全部是行测：目录本身即行测六模块。**必须显式带出**，不能靠 classify 默认 ——
# `classify` 不校验科目，缺省会静默把后续接入的申论源错标成行测。
SUBJECT = "行测"

# 目录序 **就是** 行测标准顺序（政治理论在最前，覆盖 2025+ 国考新增）
MODULE_DIRS = (
    "01-政治理论", "02-常识判断", "03-言语理解与表达",
    "04-数量关系", "05-判断推理", "06-资料分析",
)

# **噪声白名单**：源根下**确知不是模块**的目录，逐项显式列出 + 写明理由。
# 这与「不在白名单就记台账」是**同一件事的两面**：白名单里的静默跳过，白名单外的**必须留痕**
# （整改 F2·C，评审 I3）。真树实测（`D:\projects\_gwy-upstream\xingcezhenti` 顶层）除 6 个模块目录外
# 只有这两个目录：`.git`（版本库元数据）与 `90-图片`（图库，由 `export`/`gates` 直接按
# `90-图片/<图类>/<文件名>` 读取，**本就不该**当模块收）；其余项（`README.md`、
# `图片缺失清单.txt`、`蒸馏方法参考.md`）是**文件**，非目录，天然不进这条对账。
NON_MODULE_DIRS = {
    ".git": "版本库元数据，不是模块目录",
    "90-图片": "图库（export/gates 直接读 90-图片/<图类>/），不是模块目录",
}


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
        self._record_unmapped_dirs(root, res)
        return res

    def _record_unmapped_dirs(self, root, res):
        """列 `root` 下**实际存在**的目录，凡不在 `MODULE_DIRS`/`NON_MODULE_DIRS` 者**记台账**。

        **只报不收**：这些目录的正文**不进** `records`（`catalog.jsonl` 的行数因此不变），
        但它们**不再被静默跳过** —— 少了多少题在 `work/catalog/unmapped.jsonl` 里可查、计数非零。
        """
        if not os.path.isdir(root):
            return
        for name in sorted(os.listdir(root)):
            if not os.path.isdir(os.path.join(root, name)):
                continue                            # 非目录（README.md 等）不进这条对账
            if name in MODULE_DIRS or name in NON_MODULE_DIRS:
                continue
            res.unmapped.append({
                "family": FAMILY, "dir": name, "relpath": name,
                "reason": "模块目录不在白名单: %s" % name,
            })

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
            # 分流依据是**结构化 kind**，不是 reason 前缀 —— 新增任何 reason 都不会把「缺陷」错分进
            # 「有意排除」（excluded 不被 G1 盯）。UNPARSED = 缺陷，进 unparsed；EXCLUDED = spec §2 有意排除。
            bucket = res.unparsed if exc.kind == Unparsed.UNPARSED else res.excluded
            bucket.append({
                "family": FAMILY, "title": title, "region": region, "year": year,
                "subject": SUBJECT, "module": module, "relpath": relpath, "reason": exc.reason,
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
            "subject": SUBJECT,
            "module": module,
            "n_questions": actual,
            "relpath": relpath,
            "images_题目": sum(1 for t, _ in imgs if t == "题目图"),
            "images_公式": sum(1 for t, _ in imgs if t == "公式图"),
            # 台账用：源自报题数，供 G1 对账（不参与导出）
            "declared_questions": int(declared) if declared.isdigit() else -1,
        })
