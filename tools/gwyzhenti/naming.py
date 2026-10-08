# -*- coding: utf-8 -*-
"""试卷名 + 地区字段 → PaperKey。只做保守命中，拿不准就抛 Unparsed。"""
import re
from dataclasses import dataclass

from .model import LEVEL_GUOKAO, LEVEL_SHENGKAO, PaperKey

# 实测存在的非国省考地区值
EXCLUDE_REGIONS = {"选调", "深圳市考", "广州市考"}
# 标题里的排除词（实测样本：法检统一考录、司法所、事业编、职测、综应、模考）
EXCLUDE_TITLE = re.compile(r"选调|法检|司法所|事业编|事业单位|职测|综应|模考|公开课|模拟")

# 卷型：**长模式在前**，先命中先返回
PTYPE_RULES = (
    (re.compile(r"副省级"), "副省级"),
    (re.compile(r"地市级"), "地市级"),
    (re.compile(r"行政执法"), "行政执法"),
    (re.compile(r"A类"), "A类"),
    (re.compile(r"B类"), "B类"),
    (re.compile(r"C类"), "C类"),
    (re.compile(r"D类"), "D类"),
    (re.compile(r"乡镇卷|乡镇"), "乡镇卷"),
    (re.compile(r"县级卷|县级"), "县级卷"),
)
MEMORY = re.compile(r"网友回忆版")
SELECTED = re.compile(r"精选")
LIANKAO = re.compile(r"联考")


class Unparsed(Exception):
    """解析不了 —— 进 unparsed.jsonl，绝不静默丢弃。"""

    def __init__(self, reason, title=""):
        super().__init__("%s | %s" % (reason, title))
        self.reason = reason
        self.title = title


@dataclass(frozen=True)
class Classified:
    key: PaperKey
    nature: str
    form: str


def classify(region, year, title, subject="行测"):
    title = title or ""
    if not region:
        raise Unparsed("地区字段为空", title)
    if region in EXCLUDE_REGIONS:
        raise Unparsed("非国省考地区: %s" % region, title)
    m = EXCLUDE_TITLE.search(title)
    if m:
        raise Unparsed("试卷名含排除词: %s" % m.group(0), title)

    level = LEVEL_GUOKAO if region == LEVEL_GUOKAO else LEVEL_SHENGKAO
    ptype = "统考"
    for rx, value in PTYPE_RULES:
        if rx.search(title):
            ptype = value
            break

    if MEMORY.search(title):
        nature = "网友回忆版"
    elif SELECTED.search(title):
        nature = "精选"
    else:
        nature = "正式真题"

    form = "联考" if LIANKAO.search(title) else "单独命题"
    key = PaperKey(level, "" if level == LEVEL_GUOKAO else region, str(year), subject, ptype)
    return Classified(key, nature, form)
