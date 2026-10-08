# -*- coding: utf-8 -*-
"""卷的归一身份与清单记录。"""
from dataclasses import dataclass, field, asdict

LEVEL_GUOKAO = "国考"
LEVEL_SHENGKAO = "省考"


@dataclass(frozen=True, order=True)
class PaperKey:
    """一卷的归一键。year 为四位字符串（源里就是字符串）。"""
    level: str      # 国考 | 省考
    region: str     # 省名；国考时为空串（国考不设地区层）
    year: str       # "2016"
    subject: str    # 行测 | 申论
    ptype: str      # A类 | B类 | C类 | 乡镇卷 | 县级卷 | 副省级 | 地市级 | 行政执法 | 统考

    def as_dict(self):
        return asdict(self)
