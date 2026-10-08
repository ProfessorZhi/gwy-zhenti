# -*- coding: utf-8 -*-
"""确定性卷标识：用于目录名、文件名与图片目录名。"""
from .model import PaperKey


def paper_slug(key: PaperKey, variant: str = "") -> str:
    parts = [key.level, key.region, key.year, key.subject, key.ptype]
    if variant:
        parts.append(variant)
    return "-".join(p.strip() for p in parts if p and p.strip())
