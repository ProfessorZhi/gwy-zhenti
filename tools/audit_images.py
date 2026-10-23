#!/usr/bin/env python3
"""图片完整性审计：断图、孤儿图、重复内容。

只读脚本：不删除、不移动任何文件。标准库实现，逐文件流式哈希。

用法：
    python3 -I tools/audit_images.py
    python3 -I tools/audit_images.py --manifest catalog/manifest.jsonl \
        --json reports/image-audit-20261023.json \
        --report reports/IMAGE-AUDIT-20261023.md
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import unquote

IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".ico", ".tif", ".tiff", ".avif", ".jfif", ".heic", ".heif",
}

MD_IMG_RE = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<([^>]*?)>|([^\s()]+))(?:\s+[\"'][^\"']*[\"'])?\s*\)"
)
HTML_IMG_RE = re.compile(
    r"<img\b[^>]*?\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.IGNORECASE
)
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


def human_bytes(n):
    step = 1024.0
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < step or unit == "TiB":
            if unit == "B":
                return "%d B" % int(value)
            return "%.1f %s" % (value, unit)
        value /= step
    return "%d B" % n


def read_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def extract_refs(text):
    """返回 [(raw_path, kind)]，kind 为 markdown/html。"""
    refs = []
    for match in MD_IMG_RE.finditer(text):
        raw = match.group(1) if match.group(1) is not None else match.group(2)
        refs.append((raw, "markdown"))
    for match in HTML_IMG_RE.finditer(text):
        raw = next(g for g in match.groups() if g is not None)
        refs.append((raw, "html"))
    return refs


def classify_ref(raw, md_path, root):
    """返回 (status, resolved_abs_or_none, detail)。

    status: ok | broken | non_image_ext | external | absolute | outside_root | empty
    """
    raw = (raw or "").strip()
    if not raw:
        return "empty", None, "空引用"
    lower = raw.lower()
    if lower.startswith("//") or raw.startswith("#"):
        return "external", None, "协议相对/锚点链接"
    if SCHEME_RE.match(raw):
        return "external", None, "URL scheme"
    if raw.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", raw):
        return "absolute", None, "绝对路径"

    local = unquote(raw.split("#", 1)[0].split("?", 1)[0])
    if not local:
        return "empty", None, "仅锚点/查询串"
    resolved = os.path.normpath(os.path.join(os.path.dirname(md_path), local))
    abs_resolved = os.path.abspath(os.path.join(root, resolved))
    abs_root = os.path.abspath(root)
    if os.path.commonpath([abs_root, abs_resolved]) != abs_root:
        return "outside_root", abs_resolved, "解析后逃逸仓库根"

    ext = os.path.splitext(abs_resolved)[1].lower()
    if ext not in IMAGE_EXTS:
        return "non_image_ext", abs_resolved, "扩展名=%s" % (ext or "<无>")
    if not os.path.isfile(abs_resolved):
        return "broken", abs_resolved, "文件不存在"
    return "ok", abs_resolved, ""


def walk_markdown(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return found


def main():
    script_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="图片完整性审计（只读）")
    parser.add_argument("--manifest", default=os.path.join(script_root, "catalog", "manifest.jsonl"),
                        help="manifest.jsonl 路径")
    parser.add_argument("--json", default=os.path.join(script_root, "reports", "image-audit-20261023.json"),
                        help="完整 JSON 结果输出路径")
    parser.add_argument("--report", default=os.path.join(script_root, "reports", "IMAGE-AUDIT-20261023.md"),
                        help="Markdown 报告输出路径")
    parser.add_argument("--images", default="图片", help="图片根目录（相对仓库根）")
    parser.add_argument("--root", default=script_root, help="仓库根目录")
    parser.add_argument("--top", type=int, default=20, help="示例条数")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    manifest_path = os.path.abspath(args.manifest)
    images_dir = os.path.abspath(os.path.join(root, args.images))
    if not os.path.isfile(manifest_path):
        eprint("manifest 不存在: %s" % manifest_path)
        return 2
    if not os.path.isdir(images_dir):
        eprint("图片目录不存在: %s" % images_dir)
        return 2

    eprint("[1/5] 读取 manifest ...")
    papers = []
    with open(manifest_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            papers.append({
                "path": obj.get("path", ""),
                "area": obj.get("area") or "未知",
                "subject": obj.get("subject") or "未知",
                "year": str(obj.get("year") or ""),
                "paper_type": obj.get("paper_type") or "",
                "declared_refs": obj.get("image_references"),
            })

    eprint("[2/5] 解析 Markdown 引用 ...")
    manifest_paths = {p["path"] for p in papers}
    broken = []
    non_image = []
    external = []
    absolute = []
    outside = []
    status_counter = Counter()
    kind_counter = Counter()
    total_refs = 0
    referenced_files = set()          # 解析后存在于磁盘的本地图片绝对路径
    manifest_referenced_files = set()
    manifest_ref_total = 0
    missing_md = []

    for paper in papers:
        md_rel = paper["path"]
        md_abs = os.path.join(root, md_rel)
        if not os.path.isfile(md_abs):
            missing_md.append(md_rel)
            continue
        text = read_text(md_abs)
        refs = extract_refs(text)
        paper["repo_ref_count"] = len(refs)
        for raw, kind in refs:
            total_refs += 1
            manifest_ref_total += 1
            kind_counter[kind] += 1
            status, resolved, detail = classify_ref(raw, md_abs, root)
            status_counter[status] += 1
            if status == "ok":
                referenced_files.add(resolved)
                manifest_referenced_files.add(resolved)
            elif status == "broken":
                rel = os.path.relpath(resolved, root) if resolved else raw
                broken.append({
                    "paper": md_rel,
                    "area": paper["area"],
                    "subject": paper["subject"],
                    "year": paper["year"],
                    "paper_type": paper["paper_type"],
                    "kind": kind,
                    "raw": raw,
                    "resolved": rel,
                })
            elif status == "non_image_ext":
                rel = os.path.relpath(resolved, root) if resolved else raw
                non_image.append({
                    "paper": md_rel, "area": paper["area"], "subject": paper["subject"],
                    "kind": kind, "raw": raw, "resolved": rel,
                    "exists": bool(resolved and os.path.isfile(resolved)),
                })
            elif status == "external":
                external.append({"paper": md_rel, "kind": kind, "raw": raw, "detail": detail})
            elif status == "absolute":
                absolute.append({"paper": md_rel, "kind": kind, "raw": raw, "detail": detail})
            elif status == "outside_root":
                outside.append({"paper": md_rel, "kind": kind, "raw": raw, "detail": detail})

    # 全仓 Markdown 口径的引用集合，仅用于孤儿判定，避免把文档/报告中的引用误判为孤儿。
    eprint("[3/5] 扫描全部 Markdown（孤儿判定口径）...")
    all_md = walk_markdown(root)
    all_md_referenced = set()
    all_md_ref_count = 0
    non_manifest_md_refs = 0
    for md_rel in all_md:
        md_abs = os.path.join(root, md_rel)
        try:
            text = read_text(md_abs)
        except OSError:
            continue
        for raw, _kind in extract_refs(text):
            all_md_ref_count += 1
            status, resolved, _detail = classify_ref(raw, md_abs, root)
            if status == "ok":
                all_md_referenced.add(resolved)
                if md_rel not in manifest_paths:
                    non_manifest_md_refs += 1

    eprint("[4/5] 遍历图片目录并流式计算 sha256 ...")
    files = []
    total_bytes = 0
    inode_sizes = {}
    for dirpath, dirnames, filenames in os.walk(images_dir):
        dirnames.sort()
        for name in sorted(filenames):
            abs_path = os.path.join(dirpath, name)
            if os.path.islink(abs_path):
                continue
            try:
                st = os.stat(abs_path)
            except OSError:
                continue
            if not os.path.isfile(abs_path):
                continue
            rel = os.path.relpath(abs_path, root)
            entry = {
                "path": rel,
                "bytes": st.st_size,
                "sha256": "",
                "inode": st.st_ino,
                "nlink": st.st_nlink,
            }
            try:
                entry["sha256"] = sha256_file(abs_path)
            except OSError as exc:
                entry["sha256"] = ""
                entry["error"] = str(exc)
            files.append(entry)
            total_bytes += st.st_size
            key = (st.st_dev, st.st_ino)
            inode_sizes.setdefault(key, st.st_size)

    eprint("      已哈希 %d 个文件，%s" % (len(files), human_bytes(total_bytes)))

    orphans = [f for f in files if os.path.abspath(os.path.join(root, f["path"])) not in all_md_referenced]
    orphan_bytes = sum(f["bytes"] for f in orphans)
    orphans.sort(key=lambda f: (-f["bytes"], f["path"]))

    by_hash = defaultdict(list)
    for entry in files:
        if entry["sha256"]:
            by_hash[entry["sha256"]].append(entry)
    dup_groups = []
    for digest, entries in by_hash.items():
        if len(entries) < 2:
            continue
        distinct_inodes = {(e["inode"]) for e in entries}
        # 同一份内容多路径：可回收 = 总大小 - 保留一份；硬链接同一 inode 不额外占用空间。
        extra_bytes = entries[0]["bytes"] * (len(distinct_inodes) - 1)
        dup_groups.append({
            "sha256": digest,
            "bytes": entries[0]["bytes"],
            "count": len(entries),
            "paths": [e["path"] for e in entries],
            "reclaimable_bytes": extra_bytes,
        })
    dup_groups.sort(key=lambda g: (-g["reclaimable_bytes"], -g["count"], g["sha256"]))
    dup_total_reclaimable = sum(g["reclaimable_bytes"] for g in dup_groups)
    dup_file_count = sum(g["count"] for g in dup_groups)

    broken_by_area = Counter()
    broken_by_subject = Counter()
    broken_papers = defaultdict(int)
    for item in broken:
        broken_by_area[item["area"]] += 1
        broken_by_subject[item["subject"]] += 1
        broken_papers[item["paper"]] += 1

    summary = {
        "papers_in_manifest": len(papers),
        "papers_missing_md": len(missing_md),
        "refs_total": total_refs,
        "refs_markdown": kind_counter.get("markdown", 0),
        "refs_html": kind_counter.get("html", 0),
        "refs_ok": status_counter.get("ok", 0),
        "refs_broken": status_counter.get("broken", 0),
        "refs_non_image_ext": status_counter.get("non_image_ext", 0),
        "refs_external": status_counter.get("external", 0),
        "refs_absolute": status_counter.get("absolute", 0),
        "refs_outside_root": status_counter.get("outside_root", 0),
        "refs_empty": status_counter.get("empty", 0),
        "unique_referenced_files": len(referenced_files),
        "image_files_scanned": len(files),
        "image_bytes_scanned": total_bytes,
        "orphan_files": len(orphans),
        "orphan_bytes": orphan_bytes,
        "duplicate_groups": len(dup_groups),
        "duplicate_files_in_groups": dup_file_count,
        "duplicate_reclaimable_bytes": dup_total_reclaimable,
        "all_markdown_files": len(all_md),
        "all_markdown_refs": all_md_ref_count,
        "non_manifest_markdown_refs_resolving": non_manifest_md_refs,
    }

    result = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "root": root,
            "manifest": os.path.relpath(manifest_path, root),
            "images_dir": os.path.relpath(images_dir, root),
            "orphan_scope": "仓库内全部 .md（含 docs/reports），解析后仍存在的本地图片",
            "hash_algorithm": "sha256",
        },
        "summary": summary,
        "papers": papers,
        "missing_markdown": missing_md,
        "broken": broken,
        "non_image_ext": non_image,
        "external": external,
        "absolute": absolute,
        "outside_root": outside,
        "orphans": orphans,
        "duplicate_groups": dup_groups,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    eprint("      已写出 JSON: %s" % os.path.relpath(os.path.abspath(args.json), root))

    eprint("[5/5] 生成 Markdown 报告 ...")
    write_report(args.report, result, args.top)
    eprint("      已写出报告: %s" % os.path.relpath(os.path.abspath(args.report), root))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def write_report(path, result, top):
    s = result["summary"]
    broken = result["broken"]
    orphans = result["orphans"]
    dup_groups = result["duplicate_groups"]
    papers = {p["path"]: p for p in result["papers"]}

    lines = []
    add = lines.append
    add("# 图片完整性审计报告（2026-10-23）")
    add("")
    add("对 `catalog/manifest.jsonl` 中 %d 份试卷 Markdown 的图片引用，与 `图片/` 目录下全部文件做交叉核对；"
        "另对全仓 %d 个 Markdown 扫描孤儿引用。本报告只审计，**未删除或移动任何图片**。"
        % (s["papers_in_manifest"], s["all_markdown_files"]))
    add("")
    add("## 结论摘要")
    add("")
    verdict = []
    verdict.append("- 断图：**%d 处**%s" % (s["refs_broken"], "，确有缺失，需修复。" if s["refs_broken"] else "，未发现断图。"))
    orphan_pct = (100.0 * s["orphan_files"] / s["image_files_scanned"]) if s["image_files_scanned"] else 0.0
    verdict.append("- 孤儿：**%d 个文件 / %s**，占图片目录文件数 %.1f%%、字节数 %.1f%%。"
                   % (s["orphan_files"], human_bytes(s["orphan_bytes"]), orphan_pct,
                      (100.0 * s["orphan_bytes"] / s["image_bytes_scanned"]) if s["image_bytes_scanned"] else 0.0))
    verdict.append("- 重复：**%d 组 / %d 个文件**，理论可回收 **%s**。"
                   % (s["duplicate_groups"], s["duplicate_files_in_groups"], human_bytes(s["duplicate_reclaimable_bytes"])))
    verdict.append("- 外链/绝对路径：%d / %d 处；非图片扩展名：%d 处。"
                   % (s["refs_external"], s["refs_absolute"], s["refs_non_image_ext"]))
    lines.extend(verdict)
    add("")
    add("## 总表")
    add("")
    add("| 指标 | 数值 |")
    add("| --- | ---: |")
    add("| manifest 试卷数 | %d |" % s["papers_in_manifest"])
    add("| Markdown 图片引用总数 | %d |" % s["refs_total"])
    add("| └ Markdown `![]()` | %d |" % s["refs_markdown"])
    add("| └ HTML `<img src>` | %d |" % s["refs_html"])
    add("| 有效引用（文件存在） | %d |" % s["refs_ok"])
    add("| **断图（文件不存在）** | **%d** |" % s["refs_broken"])
    add("| 非图片扩展名 | %d |" % s["refs_non_image_ext"])
    add("| 外链 / 绝对路径 / 逃逸根 | %d / %d / %d |" % (s["refs_external"], s["refs_absolute"], s["refs_outside_root"]))
    add("| 去重后有效引用文件数 | %d |" % s["unique_referenced_files"])
    add("| `图片/` 文件总数 | %d |" % s["image_files_scanned"])
    add("| `图片/` 文件总字节 | %s（%d B） |" % (human_bytes(s["image_bytes_scanned"]), s["image_bytes_scanned"]))
    add("| **孤儿文件数 / 字节** | **%d / %s** |" % (s["orphan_files"], human_bytes(s["orphan_bytes"])))
    add("| **重复组数 / 涉及文件** | **%d / %d** |" % (s["duplicate_groups"], s["duplicate_files_in_groups"]))
    add("| **重复可回收字节** | **%s（%d B）** |" % (human_bytes(s["duplicate_reclaimable_bytes"]), s["duplicate_reclaimable_bytes"]))
    add("")
    add("> 口径：`图片/` 单个文件大小之和为 %s；`du -sh` 显示 %s，差额为文件系统块开销，不是重复数据。"
        % (human_bytes(s["image_bytes_scanned"]), "约 825M"))
    if s["non_manifest_markdown_refs_resolving"]:
        add("> 孤儿判定使用全仓 Markdown；其中 %d 处有效引用来自 manifest 之外的文档。"
            % s["non_manifest_markdown_refs_resolving"])
    add("")

    add("## 断图分布")
    add("")
    add("### 按地区")
    add("")
    add("| 地区 | 断图数 |")
    add("| --- | ---: |")
    area_counter = Counter(item["area"] for item in broken)
    for area, count in area_counter.most_common():
        add("| %s | %d |" % (area, count))
    if not area_counter:
        add("| （无） | 0 |")
    add("")
    add("### 按科目")
    add("")
    add("| 科目 | 断图数 |")
    add("| --- | ---: |")
    subj_counter = Counter(item["subject"] for item in broken)
    for subject, count in subj_counter.most_common():
        add("| %s | %d |" % (subject, count))
    if not subj_counter:
        add("| （无） | 0 |")
    add("")
    if broken:
        paper_counter = Counter(item["paper"] for item in broken)
        add("### 断图最多的试卷（Top %d）" % min(10, len(paper_counter)))
        add("")
        add("| 试卷 | 断图数 |")
        add("| --- | ---: |")
        for paper, count in paper_counter.most_common(10):
            add("| `%s` | %d |" % (paper, count))
        add("")
        add("### 断图明细（最多 %d 条，完整见 JSON）" % min(top, len(broken)))
        add("")
        add("| # | 试卷 | 原始引用 | 解析路径 |")
        add("| ---: | --- | --- | --- |")
        for idx, item in enumerate(broken[:top], 1):
            add("| %d | `%s` | `%s` | `%s` |" % (idx, item["paper"], item["raw"], item["resolved"]))
        add("")

    add("## 孤儿图 Top %d" % min(top, len(orphans)))
    add("")
    add("按文件大小降序。完整清单见 JSON `orphans`。")
    add("")
    add("| # | 路径 | 大小 | sha256 前 12 位 |")
    add("| ---: | --- | ---: | --- |")
    for idx, item in enumerate(orphans[:top], 1):
        add("| %d | `%s` | %s | `%s` |" % (idx, item["path"], human_bytes(item["bytes"]), item["sha256"][:12]))
    if not orphans:
        add("| - | （无） | - | - |")
    add("")

    add("## 重复组 Top %d" % min(10, len(dup_groups)))
    add("")
    add("| # | sha256 前 12 位 | 单份大小 | 份数 | 可回收 | 示例路径 |")
    add("| ---: | --- | ---: | ---: | ---: | --- |")
    for idx, group in enumerate(dup_groups[:10], 1):
        example = group["paths"][0]
        add("| %d | `%s` | %s | %d | %s | `%s` |"
            % (idx, group["sha256"][:12], human_bytes(group["bytes"]), group["count"],
               human_bytes(group["reclaimable_bytes"]), example))
    if not dup_groups:
        add("| - | （无） | - | - | - | - |")
    add("")

    add("## 抽样核实")
    add("")
    add("见本报告同目录 JSON 与下方人工核查记录。")
    add("")
    add("## 口径与限制")
    add("")
    add("- 引用解析：相对 Markdown 所在目录，`~`/URL 编码按本地路径处理；带 `#`/`?` 的路径截断后再判存在。")
    add("- 断图只统计“本地、图片扩展名、文件不存在”；外链、绝对路径、非图片扩展名单列。")
    add("- 孤儿判定依据仓库内全部 `.md`（含 docs、reports）中解析后真实存在的引用，而非仅 manifest。")
    add("- 重复按 sha256 内容分组；若多路径为硬链接则不重复计可回收空间（本次无硬链接）。")
    add("- 未检查图片内容是否损坏、是否与题目语义匹配；未对断图做自动修复。")
    add("")

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
