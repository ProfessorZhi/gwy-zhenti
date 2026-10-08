# -*- coding: utf-8 -*-
"""所有源 adapter 的统一接口。段一只认这个接口，段二只认 catalog.jsonl。"""
from dataclasses import dataclass, field

@dataclass
class ScanResult:
    # records 每条 = **卷×模块** 粒度，键固定为：
    #   family / title / region / year / subject / module / n_questions / relpath /
    #   images_题目 / images_公式 / declared_questions
    # `declared_questions` = 源 frontmatter 自报题数（非数字则 -1），**只供 G1 对账，不参与导出**。
    records: list = field(default_factory=list)
    unparsed: list = field(default_factory=list)    # [{family, title, region, year, subject, module, relpath, reason}]
    excluded: list = field(default_factory=list)    # [{family, title, region, year, subject, module, relpath, reason}]


class SourceAdapter:
    family = ""

    def scan(self, root):
        raise NotImplementedError
