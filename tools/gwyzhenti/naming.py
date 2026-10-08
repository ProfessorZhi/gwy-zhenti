# -*- coding: utf-8 -*-
"""试卷名 + 地区字段 → PaperKey。只做保守命中，拿不准就抛 Unparsed。"""
import re
from dataclasses import dataclass

from .model import LEVEL_GUOKAO, LEVEL_SHENGKAO, PaperKey

# 实测存在的非国省考地区值
EXCLUDE_REGIONS = {"选调", "深圳市考", "广州市考"}
# 标题里的排除词（实测样本：法检统一考录、司法所、事业编、职测、综应、模考）
EXCLUDE_TITLE = re.compile(r"选调|法检|司法所|公检法|事业编|事业单位|职测|综应|模考|公开课|模拟")

# 卷型：**长模式在前**，先命中先返回。**只归一到 spec 已声明的词表**，其余一律不推测。
PTYPE_RULES = (
    (re.compile(r"副省级"), "副省级"),
    (re.compile(r"地市级"), "地市级"),
    (re.compile(r"行政执法"), "行政执法"),
    (re.compile(r"A类|A卷"), "A类"),
    (re.compile(r"B类|B卷"), "B类"),
    (re.compile(r"C类|C卷"), "C类"),
    (re.compile(r"D类|D卷"), "D类"),
    (re.compile(r"乡镇卷|乡镇"), "乡镇卷"),
    (re.compile(r"县级卷|县级"), "县级卷"),
)
MEMORY = re.compile(r"网友回忆版")
SELECTED = re.compile(r"精选")
LIANKAO = re.compile(r"联考")

# 标题里的括号内容（全角与半角都认）
PAREN = re.compile(r"[（(]([^）)]*)[）)]")
# 括号里这些词是**性质/形式**，不是卷型 —— 不能进 slug。用 `sub` 在 token **内部**剔除，
# 因为复合后缀（`行政执法卷网友回忆版`）里它们只是尾巴；精确匹配会漏 ⇒ 性质词被带上 slug。
NOT_PTYPE = re.compile(r"网友回忆版|精选|联考")
# 已声明词表的**值**集合 —— 尾缀 `卷` 只在剥掉后能落回词表时才允许剥（见 `_match_value`）。
PTYPE_VALUES = frozenset(v for _, v in PTYPE_RULES)


def _ptype_tokens(region, title):
    """取出标题括号里的「卷型/批次」token：先剥掉其中的地区标记（`浙江A卷`→`A卷`、`四川卷`→空），
    再**逐字**返回剩下的部分。性质/形式词（网友回忆版/精选/联考）不算卷型。
    """
    out = []
    for raw in PAREN.findall(title):
        s = raw.strip()
        if region and s.startswith(region):
            s = s[len(region):]
        s = NOT_PTYPE.sub("", s)
        if s == "卷":
            s = ""
        if s:
            out.append(s)
    return out


def _match_value(token):
    """token → 已声明卷型值；认不出返回 `None`。

    尾缀 `卷` 的容差是**窄的**：只在剥掉后能落回 `PTYPE_VALUES` 时才剥。真库同时存在
    `（省直）` 与 `（黑龙江省直卷）`，宽容差会把两者收敛成同一个 ptype ⇒ 撞 slug ⇒ **丢卷**。
    """
    for rx, value in PTYPE_RULES:
        if rx.fullmatch(token):
            return value
    if token.endswith("卷") and token[:-1] in PTYPE_VALUES:
        return token[:-1]
    return None


def _ptype(region, title):
    """卷型判定。**塌成同一个值 = 撞 slug = 丢卷**，故认不出时逐字带上，绝不默认。"""
    tokens = _ptype_tokens(region, title)
    for t in tokens:
        value = _match_value(t)
        if value:
            return value
    if tokens:
        return "+".join(sorted(set(tokens)))
    # 没有括号后缀 —— 回落到全标题扫描（覆盖 `2026·国家公务员考试副省级` 这种无括号写法）
    for rx, value in PTYPE_RULES:
        if rx.search(title):
            return value
    # spec §6.1：无后缀 ⇒ 统考
    return "统考"


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
    ptype = _ptype(region, title)

    if MEMORY.search(title):
        nature = "网友回忆版"
    elif SELECTED.search(title):
        nature = "精选"
    else:
        nature = "正式真题"

    form = "联考" if LIANKAO.search(title) else "单独命题"
    key = PaperKey(level, "" if level == LEVEL_GUOKAO else region, str(year), subject, ptype)
    return Classified(key, nature, form)
