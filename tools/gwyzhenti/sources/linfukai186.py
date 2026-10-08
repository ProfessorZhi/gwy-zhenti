# -*- coding: utf-8 -*-
"""linfukai186-arch/gongkao-tiku adapter：题级 JSON，按 **卷标识** 归组。

四个类目：`guokao-xingce` / `shengkao-xingce`（行测）、`guokao-shenlun` / `shengkao-shenlun`（申论）。
**科目由目录决定，地区由卷名决定** —— 实测 `shengkao-shenlun` 里有 46 个 `国家公考` 键，
反过来也会成立，故两者不可互相推导。此源**无卷型字段、无卷级图片**（图片按题级文本实测计数，
实测多为 0）。行测用于覆盖交叉对照；申论在 M1 只入 catalog，**不给正文**。
"""
import json
import os
import re

from ..naming import Unparsed, classify, region_exclusion, region_from_text
from .base import ScanResult, SourceAdapter

FAMILY = "linfukai186"

# (目录名, 科目) —— 实测四类都存在；`guokao-shenlun` 的键 100% 含「模考」，会全数进 excluded，
# 仍然接入：excluded 台账本身就是对账证据。
CATS = (
    ("guokao-xingce", "行测"),
    ("shengkao-xingce", "行测"),
    ("guokao-shenlun", "申论"),
    ("shengkao-shenlun", "申论"),
)
YEAR_RE = re.compile(r"^y(\d{4})\.json$")
YEAR_IN_KEY = re.compile(r"(\d{4})")
# 题级文本里出现即计一次（实测本机样本多为 0；不假设，按内容数）
IMGISH = re.compile(r"<img|\.png|\.jpg|\.jpeg|\.webp|/media/")


class Linfukai186Adapter(SourceAdapter):
    family = FAMILY

    def scan(self, root):
        res = ScanResult()
        for cat, subject in CATS:
            cat_dir = os.path.join(root, "data", cat)
            if not os.path.isdir(cat_dir):
                continue
            for name in sorted(os.listdir(cat_dir)):
                m = YEAR_RE.match(name)
                if not m:
                    continue                      # index.json 等非 `y<年>.json` 一律跳过
                self._one(os.path.join(cat_dir, name),
                          "data/%s/%s" % (cat, name), m.group(1), subject, res)
        return res

    def _one(self, abspath, relpath, fallback_year, subject, res):
        with open(abspath, encoding="utf-8") as fh:
            papers = json.load(fh)
        for title, items in papers.items():
            if not items:
                continue
            m = YEAR_IN_KEY.search(title)
            year = m.group(1) if m else fallback_year
            rest = title.split("·", 1)[1] if "·" in title else title
            # 排除族先于地区匹配：`2025·深圳行测申论联合终极模考大赛` 两个族都命中，
            # 报「非国省考地区」比报「模考」更贴近它的身份。
            region = region_exclusion(rest) or region_from_text(rest) or ""
            try:
                # **不要在此预判「地区为空」**（初稿曾写 `if not region: raise ...`）：
                # 模考卷（实测 56 条）**往往没有地区**，预判会让它们在 `classify` 之前就抛错、
                # 落进 `unparsed`（**G1 盯的缺陷桶**），而它们其实是 spec §2 的**有意排除**。
                # 一律交给 `classify`，由它的**检查顺序**（排除族 → 标题排除词 → 地区为空）给出正确 `kind`。
                classify(region, year, title, subject=subject)
            except Unparsed as exc:
                # 用**结构化判据** `exc.kind`，不比对 reason 前缀（前缀会在新增 reason 时错分）
                bucket = res.unparsed if exc.kind == Unparsed.UNPARSED else res.excluded
                bucket.append({
                    "family": FAMILY, "title": title, "region": region, "year": year,
                    "subject": subject, "module": "", "relpath": relpath,
                    "reason": exc.reason,
                })
                continue
            n_by_module, img_by_module = {}, {}
            for it in items:
                mod = it.get("t", "")
                n_by_module[mod] = n_by_module.get(mod, 0) + 1
                n_img = len(IMGISH.findall(json.dumps(it, ensure_ascii=False)))
                if n_img:
                    img_by_module[mod] = img_by_module.get(mod, 0) + n_img
            for module, n in n_by_module.items():
                res.records.append({
                    "family": FAMILY, "title": title, "region": region, "year": year,
                    "subject": subject, "module": module, "n_questions": n,
                    "relpath": relpath, "images_题目": img_by_module.get(module, 0),
                    "images_公式": 0, "declared_questions": -1,
                })
