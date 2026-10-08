# -*- coding: utf-8 -*-
"""试卷名 + 地区字段 → PaperKey。只做保守命中，拿不准就抛 Unparsed。"""
import re
from dataclasses import dataclass

from .model import LEVEL_GUOKAO, LEVEL_SHENGKAO, PaperKey

# 实测存在的非国省考地区值
EXCLUDE_REGIONS = {"选调", "深圳市考", "广州市考", "公安院校"}

# 卷名里出现「地区」时的排除族。**值必须是 `EXCLUDE_REGIONS` 的成员** ——
# 这样 adapter 只需把 `region_exclusion()` 的结果交给 `classify`，排除逻辑只有一处。
REGION_EXCLUDE_RULES = (
    (re.compile(r"选调"), "选调"),
    (re.compile(r"深圳"), "深圳市考"),
    (re.compile(r"广州"), "广州市考"),
    (re.compile(r"公安院校"), "公安院校"),
)
# **22 省 + 5 自治区 + 4 直辖市 = 31**（不含台港澳）。**按长度倒序**（评审 F1 实测更正）：词表内**没有任何
# 省名互为子串**（31×30 排列枚举，嵌套对 0），故长度排序**不**提供「防短别名抢先」的保证 ——
# 它实际决定的只是**等长省名之间的先后**。`region_from_text` 取「词表首个命中」，故对
# **同时点名 ≥2 个省**的卷（实测 16 条，全部 2009–2015，如 `2009·426公务员联考…天津、陕西、湖北卷`）
# 取到的是**词表序**里的那个 —— 这是**已知限制**：任何单省标签对多省联考卷都不准确，
# spec §63 只规定「无省份的联考卷填 `多省联考`」，未规定多省点名时的取值。
# 影响面：16 条全部 ≤2015，**在 M1 的 2016+ 导出范围之外**（见 ledger 裁定 R-T5-7）。
# 深圳/广州是**市**不是省 —— 它们只走上面的排除族，不进这张表。
PROVINCES = tuple(sorted((
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建",
    "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州",
    "云南", "陕西", "甘肃", "青海",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
), key=len, reverse=True))
GUOKAO_TEXT = re.compile(r"国家公务员|国家公考|国考")
LIANKAO_TEXT = re.compile(r"多省联考|联考")


def region_exclusion(text):
    """卷名文本 → 要排除的地区值；没有则 `None`。"""
    for rx, value in REGION_EXCLUDE_RULES:
        if rx.search(text):
            return value
    return None


def region_from_text(text):
    """卷名文本 → 地区。**按长度降序的词表取首个命中；绝不切片。**

    实测卷名里地区**不一定在开头**（`9月吉林公务员考试《行测》甲级`、
    `公务员录用考试《行测》甘肃真题`、`2020年度浙江省…`），切 `[:2]` 会把 `黑龙江` 截成
    `黑龙`、把联考日期码 `0822` 截成 `08`；而 `classify` **不校验省份**（只在 `EXCLUDE_REGIONS`
    三值上抛错）⇒ 脏地区会**静默写进 catalog**。故只认词表命中，认不出返回 `None`，
    由调用方抛 `Unparsed`。
    """
    # 排除族**不是地区** —— 认不出（返回 `None`），由调用方的 `region_exclusion()` 负责给出
    # 排除值。缺这道闸 `公安院校联考` 会被下面误判成 `多省联考`（实测该串属排除族，
    # 且 adapter 的顺序是 `region_exclusion() or region_from_text()`，故此处返回 None 不影响分流）。
    if region_exclusion(text):
        return None
    if GUOKAO_TEXT.search(text):
        return LEVEL_GUOKAO
    for p in PROVINCES:
        if p in text:
            return p
    if LIANKAO_TEXT.search(text):
        # 无省份的多省联考卷（实测 `2016·公务员多省联考`）。**不猜省份** —— 填一个
        # 非省份的类别值，catalog 里一眼可辨。
        return "多省联考"
    return None
# 标题里的排除词（实测样本：法检统一考录、司法所、事业编、职测、综应、模考）
EXCLUDE_TITLE = re.compile(r"选调|法检|司法所|公检法|事业编|事业单位|职测|综应|模考|公开课|模拟")

# 卷型：**长模式在前**，先命中先返回。**只归一到 spec 已声明的词表**，其余一律不推测。
# 词表来源 = spec §卷型归一表（:137 的第一张表 + :141-144 实测的后缀词表）。
# **顺序有讲究**：`县级以上` 必须排在 `县级卷|县级` 之前，`定向乡镇` 必须排在 `乡镇卷|乡镇` 之前，
# 否则前者的 search 会被更短的后者抢先命中 ⇒ 卷型判错 ⇒ 可能撞 slug。
PTYPE_RULES = (
    (re.compile(r"副省级"), "副省级"),
    (re.compile(r"地市级"), "地市级"),
    (re.compile(r"行政执法"), "行政执法"),
    (re.compile(r"A类|A卷"), "A类"),
    (re.compile(r"B类|B卷"), "B类"),
    (re.compile(r"C类|C卷"), "C类"),
    (re.compile(r"D类|D卷"), "D类"),
    # —— spec :141-144 实测的后缀词表（此前缺失，正是撞 slug 的根因）——
    (re.compile(r"甲级|甲卷"), "甲级"),
    (re.compile(r"乙级|乙卷"), "乙级"),
    (re.compile(r"上半年"), "上半年"),
    (re.compile(r"下半年"), "下半年"),
    (re.compile(r"县乡卷|县乡"), "县乡卷"),
    (re.compile(r"省直卷|省直"), "省直"),
    (re.compile(r"兵团"), "兵团"),
    (re.compile(r"县级以上"), "县级以上"),
    (re.compile(r"区级及以上"), "区级及以上"),
    (re.compile(r"定向乡镇"), "定向乡镇"),
    (re.compile(r"单考区卷"), "单考区卷"),
    # —— 原有的两级，必须排在「定向乡镇」「县级以上」之后 ——
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
    UNPARSED = "unparsed"    # 缺陷：必须被 G1 盯住
    EXCLUDED = "excluded"    # 有意排除：spec §2 非目标

    def __init__(self, reason, title="", kind=UNPARSED):
        super().__init__("%s | %s" % (reason, title))
        self.reason = reason
        self.title = title
        self.kind = kind


@dataclass(frozen=True)
class Classified:
    key: PaperKey
    nature: str
    form: str


def classify(region, year, title, subject="行测"):
    title = title or ""
    # **检查顺序是有意的**：排除族 → 标题排除词 → 地区为空。
    # 理由（Task 5 修复轮实测）：模考/选调这类卷是 spec §2 的**非目标**（有意排除），
    # 而它们常常**根本没有地区**（实测 `2021·省考行测申论联合终极模考大赛`，共 56 条）。
    # 若把「地区为空」放在最前，这些卷会在走到标题判断**之前**就抛错 ⇒ 落进
    # `unparsed`（**G1 盯的缺陷桶**），而 `unparsed` 长期非零会让人习惯性忽略它 ——
    # 缺陷桶就废了。`模考` 由 `EXCLUDE_TITLE` 判定，故必须让它**先**有机会命中。
    if region in EXCLUDE_REGIONS:
        raise Unparsed("非国省考地区: %s" % region, title, kind=Unparsed.EXCLUDED)
    m = EXCLUDE_TITLE.search(title)
    if m:
        raise Unparsed("试卷名含排除词: %s" % m.group(0), title, kind=Unparsed.EXCLUDED)
    if not region:
        raise Unparsed("地区字段为空", title)

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
