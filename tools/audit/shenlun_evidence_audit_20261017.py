#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""申论原卷/材料完整性与证据等级审计（只读）。

本工具不重算覆盖率矩阵（那是 tools/cloud_quality.py 的职责），只回答四个
证据层问题：

  1. reports/FULL-REPAIR-20261015.md 登记的「尚未取得的真实整卷」与实际文件是否一致；
  2. 卷内 `答案来源：<path>` 指针是否指向真实存在的文件（悬空指针 = 证据链不可追溯）；
  3. 申论 frontmatter `真题性质` 的措辞是否与 `来源` 的实际证据等级相称；
  4. 每份申论当前 sha256 是否被 reports/ 下任一凭据记录（未记录 = 交付态无凭据）。

全部只读：不写任何正式卷，不修改 main。
"""
from __future__ import annotations
import argparse, glob, hashlib, json, os, re, sys

# reports/FULL-REPAIR-20261015.md「尚未取得的真实整卷」表（2026-10-15 登记态）
REGISTERED_MISSING = [
    ("上海", "2016", "行政执法专项"), ("上海", "2021", "行政执法专项"),
    ("上海", "2022", "A"), ("上海", "2022", "行政执法专项"), ("上海", "2023", "B"),
    ("上海", "2024", "行政执法专项"), ("上海", "2025", "行政执法专项"),
    ("北京", "2026", "统一卷"),
    ("天津", "2022", "行政执法"), ("天津", "2024", "综合街镇"), ("天津", "2024", "行政执法"),
    ("天津", "2025", "行政执法"), ("天津", "2026", "综合市区"), ("天津", "2026", "综合街镇"),
    ("江苏", "2026", "A"), ("江苏", "2026", "C"),
    ("浙江", "2022", "A"), ("浙江", "2022", "B"), ("浙江", "2022", "C"),
    ("深圳", "2024", "Ⅰ"), ("福建", "2026", "省市综合管理"),
]

INK = re.compile(r'答案来源：`([^`]+)`')
ZENGTI = re.compile(r'^真题性质:\s*(.*)$', re.M)
LAIYUAN = re.compile(r'^来源:\s*(.*)$', re.M)

# 第三方聚合源标识 -> 证据等级。抽查依据见 SOURCES.md 六/七节。
SOURCE_TIER = {
    "linfukai186": "第三方聚合(题级JSON，无卷型字段)",
    "slb": "第三方站点(shenlunhome.com，裸格式)",
    "qiushi": "第三方站点(粉柿系)",
    "yanshen": "第三方站点(囊中对比 srnz.net)",
    "kaogong-shuati": "第三方题库APP(粉柿系)",
    "huatu-zhenti": "培训机构整理",
    "SGHCN0762": "第三方PDF集",
}


def sha_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def read(p: str) -> str:
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def shenlun_files(root: str):
    os.chdir(root)
    return sorted(glob.glob("国考/*/申论-*.md") + glob.glob("省考/*/*/申论-*.md"))


# 登记卷型 -> 该卷在库内可能的文件名片段（同名卷型在不同批次有 A类/A卷、一卷/Ⅰ卷 两种写法）
TYPE_ALIASES = {
    "A": ["A类", "A卷"], "B": ["B类", "B卷"], "C": ["C类", "C卷"],
    "行政执法专项": ["行政执法"], "行政执法": ["行政执法"],
    "统一卷": ["统考"], "综合街镇": ["街镇"], "综合市区": ["市区"],
    "Ⅰ": ["Ⅰ卷", "一卷"], "省市综合管理": ["省市综合管理"],
}


def missing_reconciliation(root: str):
    rows = []
    for region, year, ptype in REGISTERED_MISSING:
        d = os.path.join("省考", region, year)
        files = sorted(os.listdir(d)) if os.path.isdir(d) else []
        sl = [f for f in files if f.startswith("申论")]
        aliases = TYPE_ALIASES.get(ptype, [ptype])
        matched = [f for f in sl if any(a in f for a in aliases)]
        rows.append({
            "region": region, "year": year, "paper_type": ptype,
            "dir_exists": os.path.isdir(d),
            "shenlun_files_in_dir": sl,
            "matched_file": matched[0] if matched else None,
            "status": "present" if matched else "absent",
        })
    present = [r for r in rows if r["status"] == "present"]
    absent = [r for r in rows if r["status"] == "absent"]
    return {
        "registered_in_report": len(REGISTERED_MISSING),
        "confirmed_still_missing": len(absent),
        "reconciled_present": present,
        "entries": rows,
    }


def dangling_pointers(root: str, files):
    out = []
    for p in files:
        for i, line in enumerate(read(p).splitlines(), 1):
            m = INK.search(line)
            if not m:
                continue
            target = m.group(1)
            out.append({
                "path": p, "line": i, "pointer": target,
                "target_exists": os.path.exists(target),
                "in_git_history": git_has_history(target),
            })
    return out


def git_has_history(path: str) -> bool:
    import subprocess
    try:
        r = subprocess.run(["git", "log", "--all", "--oneline", "--", path],
                           capture_output=True, text=True, timeout=120)
        return bool(r.stdout.strip())
    except Exception:
        return False


def zhengt_i_tiers(root: str, files):
    tiers, bare = {}, []
    for p in files:
        t = read(p)
        m = ZENGTI.search(t)
        label = m.group(1).strip().strip('"') if m else ""
        tiers[label] = tiers.get(label, 0) + 1
        if label == "正式真题":
            lm = LAIYUAN.search(t)
            loc = lm.group(1).strip() if lm else ""
            ids = re.findall(r'"([^"]+)"', loc)
            bare.append({
                "path": p,
                "declared": label,
                "source_ids": ids,
                "source_tiers": [SOURCE_TIER.get(i, "未登记源标识") for i in ids],
            })
    return tiers, bare


def receipt_coverage(root: str, files):
    after, before, all_after = {}, {}, set()
    for f in sorted(glob.glob("reports/**/*.json*", recursive=True)):
        try:
            txt = read(f)
        except Exception:
            continue
        if "sha256" not in txt:
            continue
        dec = json.JSONDecoder()
        i = 0
        while i < len(txt):
            while i < len(txt) and txt[i] in " \t\r\n":
                i += 1
            if i >= len(txt):
                break
            try:
                obj, j = dec.raw_decode(txt, i)
            except json.JSONDecodeError:
                break
            i = j
            stack = [obj]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    p, a, b = o.get("path"), o.get("after_sha256"), o.get("before_sha256")
                    if a:
                        all_after.add(a)
                    if p and a:
                        after.setdefault(p, set()).add(a)
                    if p and b:
                        before.setdefault(p, set()).add(b)
                    stack.extend(o.values())
                elif isinstance(o, list):
                    stack.extend(o)
    unrecorded = []
    for p in files:
        cur = sha_text(read(p))
        known = after.get(p, set()) | before.get(p, set())
        if cur not in known and cur not in all_after:
            unrecorded.append({"path": p, "sha256": cur})
    return {"files": len(files), "current_hash_recorded": len(files) - len(unrecorded),
            "unrecorded": unrecorded}


def build(root: str) -> dict:
    root = os.path.abspath(root)
    files = shenlun_files(root)
    tiers, bare = zhengt_i_tiers(root, files)
    return {
        "generated": "2026-10-17",
        "baseline": {"pr": 20, "head": "e1feb5187ec3544cde62a1a128a6269a8d63011b"},
        "shenlun_files_audited": len(files),
        "missing_whole_papers": missing_reconciliation(root),
        "dangling_answer_source_pointers": dangling_pointers(root, files),
        "zhenti_label_tiers": tiers,
        "bare_zhengshi_zhenti": bare,
        "receipt_coverage": receipt_coverage(root, files),
    }


def main():
    ap = argparse.ArgumentParser(description="申论证据等级与完整性只读审计")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    d = build(a.root)
    txt = json.dumps(d, ensure_ascii=False, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
    print("shenlun files audited      :", d["shenlun_files_audited"])
    print("registered missing         :", d["missing_whole_papers"]["registered_in_report"])
    print("confirmed still missing    :", d["missing_whole_papers"]["confirmed_still_missing"])
    print("reconciled (now present)   :", len(d["missing_whole_papers"]["reconciled_present"]))
    print("dangling answer pointers   :", sum(1 for x in d["dangling_answer_source_pointers"] if not x["target_exists"]))
    print("bare 正式真题 labels        :", len(d["bare_zhengshi_zhenti"]))
    print("receipt coverage           :", d["receipt_coverage"]["current_hash_recorded"], "/", d["receipt_coverage"]["files"])


if __name__ == "__main__":
    main()
