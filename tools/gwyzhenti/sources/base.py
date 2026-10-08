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
    # 硬编码的目录白名单**之外**、被**显式记录**（不静默跳过）的目录。判据见整改 F2·C：
    # 只报不收 —— 表外目录的正文**不进** `catalog.jsonl`，但必须在台账里可查、计数非零。
    # [{family, dir, relpath, reason}]
    unmapped: list = field(default_factory=list)


class SourceAdapter:
    family = ""

    def scan(self, root):
        raise NotImplementedError
