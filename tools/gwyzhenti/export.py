# -*- coding: utf-8 -*-
"""段二：按 catalog.jsonl 逐卷导出，并只复制被引用的图片。"""
import hashlib
import io
import json
import os
import re
import shutil
from dataclasses import dataclass, field

from . import mdread, render
from .model import PaperKey

IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"[^>]*>')


@dataclass
class ExportReport:
    papers: int = 0
    files: int = 0
    images: int = 0
    manifest_path: str = ""
    skipped: list = field(default_factory=list)
    # 撞 slug：同一键在 xingcezhenti 源里有**多个卷名** ⇒ 只导第一个，其余在此如实记下。
    # 与 `skipped` 分开，是因为「少导了一份卷」和「这份卷没导出」是**两种不同的事故**（裁定 R-T8-1）。
    collided: list = field(default_factory=list)


def repo_paths(key, slug):
    if key.level == "国考":
        md = "国考/%s/%s-%s.md" % (key.year, key.subject, key.ptype)
    else:
        md = "省考/%s/%s/%s-%s.md" % (key.region, key.year, key.subject, key.ptype)
    return md, "图片/%s" % slug


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _write(path, data_bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data_bytes)
    os.replace(tmp, path)


def load_catalog(catalog_dir):
    with io.open(os.path.join(catalog_dir, "catalog.jsonl"), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _xingce_titles(row):
    """该卷在 **xingcezhenti 源**里的卷名（排序列表）。空 = 该源根本没有此卷。

    **绝不能用 `row["title"]` 当文件名**（裁定 R-T8-1）。`title` 是**首个被聚合进来的原始卷名**，
    而聚合按 `sorted(uproots.items())` 走、`linfukai186` 排在 `xingcezhenti` 之前 ⇒
    凡是**两源都有的键**，`title` 就是 **linfukai186** 的卷名。实测这种键 **286** 个，
    且 **286/286** 两侧卷名**完全不是同一串**：

        2016·国家公务员考试副省级            （linfukai186）
        2016年国家公务员录用考试《行测》题（副省级）  （xingcezhenti）

    拿前者去 xingcezhenti 根下拼路径 ⇒ **全数落空** ⇒ 整卷被错判成「上游文件缺失」而丢。
    这是本任务**最会静默吃掉交付量**的一处，故单独成函数、单独可测。
    """
    return sorted(row.get("titles", {}).get("xingcezhenti", []))


def _parts_for(row, upstream_xingce):
    """按 MODULE_ORDER 取该卷各模块源文本；模块缺失则跳过（并如实记录）。

    文件名用 **xingcezhenti 源自己的卷名**（见 `_xingce_titles`）。同名多值（`len > 1`）
    = 该键疑似撞 slug ⇒ 只取第一个，**多出来的**卷名由调用方记进 `rep.collided`（不静默丢）。
    """
    names = _xingce_titles(row)
    if not names:
        return [], []
    want = [m for m in render.MODULE_ORDER if m in row["modules"]]
    parts, got = [], []
    for module in want:
        # 模块目录前缀
        prefix = {"政治理论": "01-政治理论", "常识判断": "02-常识判断",
                  "言语理解与表达": "03-言语理解与表达", "数量关系": "04-数量关系",
                  "判断推理": "05-判断推理", "资料分析": "06-资料分析"}[module]
        path = os.path.join(upstream_xingce, prefix, names[0] + ".md")
        if os.path.exists(path):
            with io.open(path, encoding="utf-8") as fh:
                parts.append(fh.read())
            got.append(module)
    return parts, got


def run(catalog_dir, uproots, repo_root, limit=None):
    rep = ExportReport()
    manifest = os.path.join(repo_root, "work", "manifest.jsonl")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    rows = load_catalog(catalog_dir)
    if limit:
        rows = rows[:limit]
    entries = []
    for row in rows:
        if "xingcezhenti" not in row["sources"]:
            rep.skipped.append({"slug": row["slug"], "reason": "本批只导出有正文的源"})
            continue
        key = PaperKey(row["level"], row["region"], row["year"], row["subject"], row["ptype"])
        # xingcezhenti 侧同名多值 ⇒ 该键疑似撞 slug，只导第一个，**其余如实记进 `collided`**
        # （不是静默丢；见裁定 R-T8-1）。
        extra = _xingce_titles(row)[1:]
        if extra:
            rep.collided.append({"slug": row["slug"], "titles": extra})
        parts, modules = _parts_for(row, uproots["xingcezhenti"])
        if not parts:
            rep.skipped.append({"slug": row["slug"], "reason": "上游文件缺失"})
            continue
        md_rel, img_dir = repo_paths(key, row["slug"])
        depth = md_rel.count("/")
        # 收集被引用的图 → 建 image_map（源 src → 输出相对路径）
        image_map = {}
        for text in parts:
            for src in IMG.findall(text):
                name = os.path.basename(src)
                seg = "公式图" if "/公式图/" in src else "题目图"
                image_map[src] = "../" * depth + "%s/%s/%s" % (img_dir, seg, name)
        out = render.render_paper(parts, key, nature=row["nature"], form=row["form"],
                                  sources=row["sources"], modules=modules, image_map=image_map)
        data = out.body.encode("utf-8")
        _write(os.path.join(repo_root, md_rel), data)
        rep.files += 1
        entries.append({"path": md_rel.replace("\\", "/"), "sha256": _sha256_bytes(data)})
        # 只复制被引用的图
        for src, dest_rel in image_map.items():
            name = os.path.basename(src)
            seg = "公式图" if "/公式图/" in src else "题目图"
            src_abs = os.path.normpath(os.path.join(uproots["xingcezhenti"], "90-图片", seg, name))
            if not os.path.exists(src_abs):
                rep.skipped.append({"slug": row["slug"], "reason": "源图片缺失: %s" % name})
                continue
            # `dest_rel` 是**相对 md 文件**的路径（写进正文的就是它）；落盘必须把它锚在 md 所在目录，
            # 否则那串 `../` 会从 `repo_root` 再往上跳 ⇒ 图片落到**仓库外**（真库会落到 `D:\图片`）。
            dest_abs = os.path.normpath(os.path.join(
                repo_root, os.path.dirname(md_rel), dest_rel.replace("/", os.sep)))
            if os.path.exists(dest_abs):
                continue
            os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
            shutil.copyfile(src_abs, dest_abs)
            rep.images += 1
        rep.papers += 1
    with io.open(manifest, "w", encoding="utf-8", newline="\n") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    rep.manifest_path = manifest
    return rep
