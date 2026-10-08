# -*- coding: utf-8 -*-
"""adapter 注册表。加新源 = 在这里多一行。"""
from .linfukai186 import Linfukai186Adapter
from .xingcezhenti import XingceZhentiAdapter

ADAPTERS = {
    XingceZhentiAdapter.family: XingceZhentiAdapter(),
    Linfukai186Adapter.family: Linfukai186Adapter(),
}
