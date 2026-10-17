#!/usr/bin/env python3
"""Deterministic, metadata-only provenance / identity / count-boundary gate.

Everything here reads *declared metadata only*: front-matter fields, source labels,
slot descriptors and receipt flags. It never reads question text, options, image
bytes or credentials, and it makes no legal determination -- it only refuses to
let a declaration outrun its evidence.

Fail-closed rules
-----------------
R1  restricted-source labelling
    A paper that declares itself 正式真题/官方原题 while its own source detail
    names a restricted membership capture (粉笔会员, 再分发条件未核实, 会员采)
    and no explicit redistribution permission is recorded must NOT be reported as
    verified. Verdict: `provenance_uncertain` + `verified=False`.

R2  identity conflation
    Distinct paper identities must not be merged into one slot:
      * 通用卷 vs 综合卷          (same area/year, both claims present)
      * 优秀村干部 (行测 C/D + 综合应用能力) vs 申论
      * 行政执法专项招录 vs 市考 A/B 申论
    Any such merge is an `identity_conflict`.

R3  count boundary
    A reclassification may move slots between denominators, but it must not lower
    the registry's remaining count without a recovery event. Reclassifying slots
    away is not recovering them.

R4  image-evidence promotion
    A pair whose verified image content hashes *conflict* is positive evidence of
    difference. It must never be promoted to auto-acceptable / exact. (This is
    stricter than "image evidence unavailable", which is merely absent.)

Usage:
  python3 -I metadata_provenance_gate.py <metadata.json> [--out ledger.json]
Exit 0 = gate ran. Exit 2 = unreadable input. Verdicts are data, not exit codes.
"""
import argparse
import json
import re
import sys

OFFICIAL_CLAIMS = {"正式真题", "官方原题", "官方真题"}
RESTRICTED_SOURCE_MARKERS = ("粉笔会员", "会员采", "再分发条件未核实", "fbi会员", "会员采集")
REDISTRIBUTION_GRANTED = ("allowed", "permitted", "public_domain", "licensed", "已许可", "可再分发")


def _text(*parts):
    return " ".join(str(p) for p in parts if p is not None)


# ------------------------------------------------------------------ R1
def assess_restricted_label(meta):
    """Whether a paper may be reported as verified, from its own declarations."""
    nature = str(meta.get("真题性质") or meta.get("paper_nature") or "").strip()
    source_detail = _text(meta.get("来源明细"), meta.get("source_detail"),
                          meta.get("来源"), meta.get("sources"))
    redistribution = str(meta.get("再分发许可") or meta.get("redistribution") or "").strip()
    verification = str(meta.get("校验状态") or meta.get("verification_status") or "")

    claims_official = nature in OFFICIAL_CLAIMS or any(c in nature for c in OFFICIAL_CLAIMS)
    restricted_hits = [m for m in RESTRICTED_SOURCE_MARKERS
                       if m in source_detail or m in verification]
    granted = any(g.lower() in redistribution.lower() for g in REDISTRIBUTION_GRANTED)

    if claims_official and restricted_hits and not granted:
        return {
            "rule": "R1-restricted-source-labelling",
            "verdict": "provenance_uncertain",
            "verified": False,
            "reason": ("declares an official-paper nature while its own source detail names a "
                       "restricted membership capture and records no redistribution permission"),
            "evidence": {"claimedNature": nature, "restrictedMarkers": restricted_hits,
                         "redistributionRecorded": bool(redistribution)},
            "requiredAction": "obtain a source-confirmation record, or downgrade the claim",
        }
    if claims_official and restricted_hits and granted:
        return {
            "rule": "R1-restricted-source-labelling", "verdict": "verified_allowed",
            "verified": True,
            "reason": "official claim + restricted source, but an explicit redistribution permission is recorded",
            "evidence": {"claimedNature": nature, "redistribution": redistribution},
        }
    return {
        "rule": "R1-restricted-source-labelling",
        "verdict": "no_conflict",
        "verified": claims_official,
        "reason": "no restricted-source marker alongside an official claim",
        "evidence": {"claimedNature": nature, "restrictedMarkers": restricted_hits},
    }


# ------------------------------------------------------------------ R2
def assess_identity(meta):
    """Detect identities that must not be merged into one slot."""
    conflicts = []
    aliases = meta.get("aliases") or []
    alias_text = _text(*aliases)
    variant = str(meta.get("卷型") or meta.get("variant") or "")
    subject = str(meta.get("科目") or meta.get("subject") or "")

    # 通用 vs 综合
    if ("通用" in variant or "通用" in alias_text) and ("综合" in variant or "综合" in alias_text
                                                          or "综合" in str(meta.get("claimed_equivalent") or "")):
        conflicts.append({
            "kind": "generic-vs-composite",
            "detail": "通用卷 and 综合卷 are asserted as the same paper without a volume-type ruling",
        })

    # 优秀村干部 vs 申论
    if "优秀村干部" in variant or "优秀村干部" in alias_text:
        if subject == "申论" or "申论" in str(meta.get("claimed_equivalent") or ""):
            conflicts.append({
                "kind": "village-cadre-not-shenlun",
                "detail": ("优秀村干部类 sits 行测 C/D + 《综合应用能力》; counting it as 申论 "
                           "moves a slot into the wrong subject denominator"),
            })

    # 行政执法专项 vs 市考 A/B
    if "行政执法" in variant and ("专项" in variant or "招录" in variant):
        if any(k in alias_text for k in ("市考", "A卷", "B卷", "第三类", "A/B")):
            conflicts.append({
                "kind": "separate-recruitment-not-third-paper",
                "detail": ("行政执法类专项招录 is an independent recruitment exam; it is not a "
                           "third 市考 申论 paper beside A/B"),
            })

    # 市考名义 vs 专项招录：标题/来源把它写成「市考《申论》」，而卷型是行政执法卷、
    # 又没有任何「专项/招录」标记 —— 这不足以定身份，但足以要求人工确认。
    source_text = _text(meta.get("来源明细"), meta.get("source_detail"),
                        meta.get("标题"), meta.get("title"), alias_text)
    claims_municipal = any(k in source_text for k in ("市考", "公考《申论》", "市公务员录用"))
    marked_special = any(k in source_text for k in ("专项", "招录", "执法类专项"))
    if "行政执法" in variant and claims_municipal and not marked_special:
        conflicts.append({
            "kind": "enforcement-special-labelled-as-municipal",
            "detail": ("labelled as an annual municipal 市考 申论 paper although the variant is "
                       "行政执法; the 行政执法 special recruitment is a separate exam and the "
                       "identity needs a volume-type ruling before it is counted as 市考 A/B"),
            "severity": "needs_review",
        })

    return {
        "rule": "R2-identity-conflation",
        "verdict": "identity_conflict" if conflicts else "no_conflict",
        "conflicts": conflicts,
    }


# ------------------------------------------------------------------ R3
def assess_count_boundary(before, after, recovered=0, reclassified=0):
    """A reclassification is not a recovery."""
    ok = after == before - recovered
    return {
        "rule": "R3-count-boundary",
        "verdict": "PASS" if ok else "FAIL",
        "reason": ("remaining count changed without a matching recovery"
                   if not ok else "remaining count consistent with recoveries"),
        "evidence": {"before": before, "after": after, "recovered": recovered,
                     "reclassified": reclassified,
                     "expectedAfter": before - recovered,
                     "reclassifiedSlotsMustStayInSomeDenominator": True},
    }


# ------------------------------------------------------------------ R4
def assess_image_promotion(row):
    """Verified-but-conflicting image content must never be auto-acceptable."""
    flags = list(row.get("flags") or [])
    images = row.get("images") or {}
    verified = images.get("available") is True
    conflict = verified and images.get("similarity") == 0
    auto = row.get("autoAcceptable") is True or row.get("auto_acceptable") is True
    grade = row.get("grade")

    promoted = auto and grade == "exact" and (conflict or images.get("contradictory") is True)
    return {
        "rule": "R4-image-evidence-promotion",
        "verdict": "FAIL" if promoted else "PASS",
        "reason": ("verified image content conflicts, yet the row is exact/auto-acceptable"
                   if promoted else "no conflicting-image promotion detected"),
        "evidence": {"grade": grade, "autoAcceptable": auto, "imagesAvailable": verified,
                     "imagesSimilarity": images.get("similarity"), "flags": flags,
                     "verifiedConflictIsPositiveEvidenceOfDifference": conflict},
    }


# ------------------------------------------------------------------ driver
def assess_record(meta):
    out = {"label": meta.get("label") or meta.get("path") or None,
           "area": meta.get("地区") or meta.get("area"),
           "year": meta.get("年份") or meta.get("year"),
           "subject": meta.get("科目") or meta.get("subject"),
           "variant": meta.get("卷型") or meta.get("variant"),
           "checks": []}
    out["checks"].append(assess_restricted_label(meta))
    out["checks"].append(assess_identity(meta))
    if "count_boundary" in meta:
        cb = meta["count_boundary"]
        out["checks"].append(assess_count_boundary(
            cb.get("before"), cb.get("after"), cb.get("recovered", 0),
            cb.get("reclassified", 0)))
    for row in meta.get("receipt_rows") or []:
        out["checks"].append(assess_image_promotion(row))
    out["blocking"] = [c["rule"] for c in out["checks"]
                       if c["verdict"] in ("provenance_uncertain", "identity_conflict", "FAIL")]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metadata")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        doc = json.load(open(a.metadata, encoding="utf8"))
    except Exception as e:
        print(f"cannot read {a.metadata}: {e}", file=sys.stderr)
        return 2
    records = doc.get("records") if isinstance(doc, dict) and "records" in doc else [doc]
    ledger = {
        "schemaVersion": 1,
        "kind": "metadata-only-provenance-gate",
        "contentPolicy": "declared metadata only: no question text, options, image bytes or credentials",
        "isLegalDetermination": False,
        "note": ("assesses whether a declaration outruns its own stated evidence; it does not "
                 "decide copyright status and never edits the underlying paper"),
        "records": [assess_record(r) for r in records],
    }
    out = json.dumps(ledger, ensure_ascii=False, indent=1)
    (open(a.out, "w").write(out) if a.out else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
