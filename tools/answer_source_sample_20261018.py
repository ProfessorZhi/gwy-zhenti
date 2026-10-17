#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-paper source dossiers for a focused region, for manual metadata review.

This does not decide truth. It surfaces, per paper, exactly what the paper claims about
its own answer provenance, whether that claim is backed by a retained receipt, and which
identifiers are missing -- so a reviewer can record a verdict without re-reading 47 files
from scratch.

Verdict vocabulary used by the reviewer (recorded in the output, not derived here):
  source_verified  -- a retained, checkable artifact identifies the answer source
  source_present   -- a source is named but no retained artifact backs the identifier
  unsupported      -- nothing identifies where the answer came from
  blocked          -- the source exists only off-repo and cannot be obtained legitimately
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer_provenance_markers_20261017 as prov  # noqa: E402
import answer_source_quality_index_20261018 as idx  # noqa: E402

# Frontmatter fields worth showing a human reviewer, in reading order.
FM_FIELDS = ("真题性质", "命题形式", "来源", "来源明细", "来源路径", "答案来源",
             "补题核验来源", "整卷核验状态", "校验状态", "新增答案性质")

# The paper declaring that its own upstream's redistribution terms are unverified is the
# strongest signal available that content must stay local_only.
LICENCE_LANGUAGE = re.compile(r"再分发|转载|版权|许可|会员|local_only|不对外|不得上传|授权")


def dossier(path: Path, repo: Path, receipt_index: set, tree: set[str],
            index_row: dict | None) -> dict:
    text = path.read_text(encoding="utf-8")
    fm = prov.parse_frontmatter(text)
    fp = prov.file_provenance(fm, receipt_index)
    blocks = list(prov.iter_answer_blocks(text))

    cited: dict[str, int] = {}
    for _n, b, _s, _e in blocks:
        bc = idx.strip_quarantined(b)
        for h in prov.HEX64_RE.findall(bc):
            cited[h.lower()] = cited.get(h.lower(), 0) + 1
        for u in prov.URL_RE.findall(bc):
            cited[u] = cited.get(u, 0) + 1

    # Same rule as the validator and the index: a link to this repository's own
    # history is not evidence of an external source.
    self_repo = sorted(k for k in cited if prov.SELF_REPO_URL.match(k))
    backed = sorted(k for k in cited
                    if k in receipt_index and not prov.SELF_REPO_URL.match(k))
    unbacked = sorted(k for k in cited
                      if k not in receipt_index and not prov.SELF_REPO_URL.match(k))

    row_prov = index_row or {}
    if row_prov.get("provenance_verified", 0) > 0:
        evidence_grade = "source_verified"
        reason = "至少一处答案引用的外部标识在 reports/ 有留存凭据"
    elif fp["state"] != "none" or row_prov.get("provenance_source_present", 0) > 0:
        evidence_grade = "source_present"
        reason = "声明了来源或来源性质，但没有留存凭据支撑具体标识"
    else:
        evidence_grade = "unsupported"
        reason = "未声明答案来源"

    licence = ""
    for k in FM_FIELDS:
        if fm.get(k) and LICENCE_LANGUAGE.search(str(fm.get(k))):
            licence = k
            break
    redistribution = "unverified" if licence else "not_stated"

    return {
        "path": str(path.relative_to(repo)),
        "evidence_grade": evidence_grade,
        "evidence_reason": reason,
        "redistribution": redistribution,
        "licence_declared_in": licence or None,
        "region": fm.get("地区"),
        "year": fm.get("年份"),
        "subject": fm.get("科目"),
        "variant": fm.get("卷型"),
        "fields": {k: fm.get(k) for k in FM_FIELDS if fm.get(k)},
        "answer_blocks": len(blocks),
        "provenance": (index_row or {}),
        "file_provenance_state": fp["state"],
        "file_provenance_backed": fp["backed"],
        "declared_absent": fp["declared_absent"],
        "claims_official": fp["claims_official"],
        "official_with_institutional_only": fp["official_claim_with_only_institutional_sources"],
        "cited_identifier_count": len(cited),
        "cited_backed_count": len(backed),
        "cited_backed": backed[:8],
        "cited_self_repo": self_repo[:8],
        "cited_unbacked": unbacked[:8],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--region", required=True)
    ap.add_argument("--commit", default="e1feb5187ec3544cde62a1a128a6269a8d63011b")
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    repo = args.repo.resolve()
    tree = idx.tracked_paths(repo, args.commit)
    receipt_index = prov.build_receipt_index(repo)
    index = {}
    if args.index.exists():
        for line in args.index.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                index[r["path"]] = r

    rows = []
    for p in sorted(prov.iter_markdown(repo, None)):
        rel = str(p.relative_to(repo))
        fm = prov.parse_frontmatter(p.read_text(encoding="utf-8"))
        if fm.get("地区") != args.region:
            continue
        rows.append(dossier(p, repo, receipt_index, tree, index.get(rel)))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"{args.region}: {len(rows)} papers")
    print(f"{'path':52} {'sub':4} {'blk':>4} {'ver':>4} {'sp':>5} {'cite':>4} {'bkd':>4} {'state':20} flags")
    for r in rows:
        pr = r["provenance"]
        flags = ",".join(pr.get("flags", []))
        print(f"{r['path']:52} {str(r['subject'])[:4]:4} {r['answer_blocks']:4} "
              f"{pr.get('provenance_verified', 0):4} {pr.get('provenance_source_present', 0):5} "
              f"{r['cited_identifier_count']:4} {r['cited_backed_count']:4} "
              f"{r['file_provenance_state']:20} {flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
