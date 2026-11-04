#!/usr/bin/env python3
"""审查 catalog/manifest.jsonl 中每份卷的来源，并导出多来源并集索引（仅标准库）。

使用:
    python3 tools/source_provenance.py --check
    python3 tools/source_provenance.py --export /tmp/paper-sources.jsonl

老卷可沿用 `来源`（单字符串或列表）；多源卷使用 `来源清单`。
仅提取已有来源证据，不尝试推断粉笔/华图身份，不改变卷内容及 manifest。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "catalog" / "manifest.jsonl"
META_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def scalar(s):
    s = s.strip()
    if not s:
        return ""
    if s.startswith('"') or s.startswith("["):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    return s.strip("'\"")


def metadata(text):
    m = META_RE.match(text)
    if not m:
        return None, []
    front = m.group(1)
    fields = {}
    for line in front.splitlines():
        if line and not line[0].isspace() and ":" in line:
            key, value = line.split(":", 1)
            fields[key] = scalar(value)
    items = []
    active = False
    for line in front.splitlines():
        if line == "来源清单:":
            active = True
            continue
        if not active:
            continue
        if line and not line.startswith(" "):
            break
        first = re.match(r"^  - ([^:]+):\s*(.*)$", line)
        more = re.match(r"^    ([^:]+):\s*(.*)$", line)
        if first:
            items.append({first.group(1): scalar(first.group(2))})
        elif more and items:
            items[-1][more.group(1)] = scalar(more.group(2))
    return fields, items


def audit():
    result, errors = [], []
    records = [json.loads(s) for s in MANIFEST.read_text(encoding="utf-8").splitlines() if s.strip()]
    for rec in records:
        rel = rec["path"]
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"{rel}: manifest 引用文件不存在")
            continue
        content = path.read_text(encoding="utf-8")
        meta, sources = metadata(content)
        if meta is None:
            errors.append(f"{rel}: 无 frontmatter")
            continue
        legacy = meta.get("来源")
        if not legacy and not sources:
            errors.append(f"{rel}: 缺来源 / 来源清单")
        for item in sources:
            if not item.get("来源方"):
                errors.append(f"{rel}: 来源清单中缺来源方")
            if not item.get("定位") and not item.get("来源试卷ID") and not item.get("证据"):
                errors.append(f"{rel}: 来源无链接、ID 或证据")
        if "参考答案（华图在线" in content and not any("华图" in str(s.get("来源方", "")) for s in sources):
            errors.append(f"{rel}: 存在华图补录正文但未登记华图来源清单")
        base = []
        if legacy:
            vals = legacy if isinstance(legacy, list) else [legacy]
            base = [{"来源方": "历史来源字段（未据此自动推断平台）", "定位": s} for s in vals]
        result.append({"path": rel, "历史来源": base, "来源清单": sources})
    return result, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="核验所有已登记试卷均有来源")
    ap.add_argument("--export", type=Path, help="导出每卷来源并集 JSONL，含原样历史来源")
    args = ap.parse_args()
    result, errors = audit()
    multi = sum(bool(item["来源清单"]) for item in result)
    print(f"试卷 {len(result)} · 已登记结构化来源清单 {multi} · 来源问题 {len(errors)}")
    if args.export:
        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in result), encoding="utf-8")
        print("已导出", args.export)
    for issue in errors[:40]:
        print("ERROR:", issue, file=sys.stderr)
    if len(errors) > 40:
        print(f"...另有 {len(errors)-40} 条", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
