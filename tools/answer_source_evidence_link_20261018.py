#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Link sampled papers to the reusable legal sources the repo already records.

The distinction this tool exists to enforce:

* A source card from `reports/SCOPE-COUNTS-2016-2026-20261015.json` can attest
  **identity / scope** (did this exam, in this year, have these subjects and this many
  papers?). It generally cannot attest an **answer key** -- and in this repository no
  official source anywhere does.
* Therefore a paper can be `identity_supported` and still be `answers_blocked`.

Nothing here fetches the network. It reads only what the repo already stores, so every
link it prints is a URL the repository has already cited, not one this tool invented.

Verdict vocabulary recorded per paper:
  identity_supported   a reusable legal source attests the paper's existence/scope
  identity_unverified  no such source for this specific year
  answers_blocked      no reusable legal source anywhere gives an answer key
  generic_only         the paper's answer provenance is generic (kind, not source)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REGION_PREFIX = {
    "上海": ("SH",), "江苏": ("js_",), "浙江": ("zj_",), "广东": ("gd_", "gz_"),
    "广州": ("gz_",), "深圳": ("sz_",), "天津": ("TJ",), "福建": ("FJ",),
    "北京": ("bj_", "contemporary_", "outline_", "paper_", "notice_", "history_"),
}

# Papers selected for this round: 8 from the 19 P0 set + 10 from the 22 上海 行测 set.
SAMPLE = [
    # P0
    "省考/上海/2017/行测-统考.md",
    "省考/上海/2026/行测-统考.md",
    "省考/辽宁/2017/行测-公安.md",
    "省考/广东/2020/行测-县级卷.md",
    "省考/江苏/2024/行测-A类.md",
    "省考/浙江/2020/行测-A类.md",
    "省考/新疆/2024/行测-兵团.md",
    "省考/北京/2025/行测-统考.md",
    # 上海 行测
    "省考/上海/2016/行测-A类.md",
    "省考/上海/2016/行测-B类.md",
    "省考/上海/2016/行测-行政执法.md",
    "省考/上海/2017/行测-行政执法.md",
    "省考/上海/2018/行测-A类.md",
    "省考/上海/2019/行测-A类.md",
    "省考/上海/2020/行测-A类.md",
    "省考/上海/2021/行测-B类.md",
    "省考/上海/2023/行测-A类.md",
    "省考/上海/2026/行测-统考.md",
]


def load_cards(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d.get("source_cards", [])


def paper_meta(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fm = {}
    m = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"')
    return fm


ID_YEAR = re.compile(r"(?:^|[^0-9])(20)?(\d{2})(?=[A-Z_\-]|$)")
TEXT_YEAR = re.compile(r"20\d{2}")


def card_years(c: dict) -> set[str]:
    """Years a card can speak to, from its id (SH17A -> 2017) and from its text."""
    years: set[str] = set()
    cid = str(c.get("id") or "")
    for m in ID_YEAR.finditer(cid):
        yy = m.group(2)
        years.add("20" + yy if m.group(1) is None else "20" + yy)
    text = " ".join(str(c.get(k) or "") for k in ("supports", "fact", "title", "kind"))
    years.update(TEXT_YEAR.findall(text))
    return years


def matching_cards(cards: list[dict], region: str, year: str, variant: str) -> dict:
    """Split matches into year-specific and year-only-other-variant.

    A card attesting that 2017 had an A卷 does not attest that 2017 had an 行政执法卷.
    Conflating the two is how a paper's identity gets "supported" by a source about a
    different paper.
    """
    prefixes = REGION_PREFIX.get(region, ())
    same_year, other_variant = [], []
    for c in cards:
        cid = str(c.get("id") or "")
        if not any(cid.startswith(p) for p in prefixes) and cid:
            continue
        if year not in card_years(c):
            continue
        text = " ".join(str(c.get(k) or "") for k in ("supports", "fact", "title", "kind"))
        # Does the card speak about this paper's variant, or only about another?
        if variant and variant in text:
            same_year.append(c)
        elif not variant:
            same_year.append(c)
        else:
            other_variant.append(c)
    return {"same_year": same_year, "other_variant": other_variant}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--cards", type=Path, default=None)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    repo = args.repo.resolve()
    cards = load_cards(args.cards or repo / "reports" / "SCOPE-COUNTS-2016-2026-20261015.json")
    index = {}
    for line in args.index.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            index[r["path"]] = r

    rows = []
    for rel in SAMPLE:
        p = repo / rel
        if not p.exists():
            rows.append({"path": rel, "exists": False})
            continue
        fm = paper_meta(p)
        region, year = fm.get("地区", ""), fm.get("年份", "")
        matched = matching_cards(cards, region, year, fm.get("卷型", ""))
        idx = index.get(rel, {})
        rows.append({
            "path": rel,
            "exists": True,
            "region": region, "year": year,
            "subject": fm.get("科目"), "variant": fm.get("卷型"),
            "paper_nature": fm.get("真题性质"),
            "declared_sources": fm.get("来源"),
            "priority": idx.get("priority"),
            "flags": idx.get("flags", []),
            "answer_blocks": idx.get("answer_blocks"),
            "provenance_verified": idx.get("provenance_verified"),
            "provenance_source_present": idx.get("provenance_source_present"),
            "file_provenance_state": idx.get("file_provenance_state"),
            "year_specific_cards": [
                {"id": c.get("id"), "url": c.get("url"),
                 "supports": (c.get("supports") or c.get("fact") or "")[:300]}
                for c in matched["same_year"]
            ],
            "year_only_other_variant_cards": [
                {"id": c.get("id"), "url": c.get("url"),
                 "supports": (c.get("supports") or c.get("fact") or "")[:300]}
                for c in matched["other_variant"]
            ],
            "identity_supported": bool(matched["same_year"]),
            "identity_partial_other_variant": bool(matched["other_variant"]),
            # No card in this repository is an answer key; that is checked separately
            # by counting official URLs inside answer blocks (6, all content citations).
            "answers_blocked": True,
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"{'paper':48} {'year':4} {'id':6} {'cards':>5}  verdict")
    for r in rows:
        if not r.get("exists"):
            print(f"{r['path']:48} MISSING")
            continue
        if r["identity_supported"]:
            v = "identity_supported"
        elif r["identity_partial_other_variant"]:
            v = "identity_partial_other_variant"
        else:
            v = "identity_unverified"
        print(f"{r['path']:48} {r['year']:4} {r.get('priority'):6} "
              f"{len(r['year_specific_cards']):2}+{len(r['year_only_other_variant_cards']):2}  {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
