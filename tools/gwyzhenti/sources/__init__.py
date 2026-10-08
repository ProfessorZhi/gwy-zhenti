# -*- coding: utf-8 -*-
"""adapter 注册表。加新源 = 在这里多一行。"""
from .xingcezhenti import XingceZhentiAdapter

ADAPTERS = {
    XingceZhentiAdapter.family: XingceZhentiAdapter(),
}
