#!/usr/bin/env python3
"""Check that every answer block declares where its answer came from.

Why this exists
---------------
QUALITY.md requires each question to record 答案来源, and distinguishes 官方公布答案 /
培训机构参考答案 / 解题者争议观点. Nothing enforced it. A reader (or a renderer, or a
downstream QA agent) therefore cannot tell, from a given answer block, whether the key
is an official publication, an institution's reference answer, or a model's
re-derivation -- and an answer that silently looks authoritative is the exact failure
mode this repository's own policy is written to prevent.

Two separable things are reported:

* **undeclared** -- the block states no provenance at all. This is a real gap and `--check`
  fails on it.
* **format variant** -- the block *does* declare provenance, but spells the marker
  differently from the canonical form. Four variants exist in the library today, e.g.
  ``**来源参考解析**（不是官方公布答案）`` puts the disclaimer outside the bold span while
  ``**来源参考解析（非官方标准答案）**`` puts it inside. Both disclose the same thing, so
  this is informational, not a failure. It is reported because a consumer that matches on
  the exact canonical string will silently mis-bucket the variants; this checker matches
  on meaning instead.

The checker never rewrites anything. Run with ``--json`` for the machine-readable form.

Usage
-----
    python tools/answer_provenance_markers_20261017.py                # report
    python tools/answer_provenance_markers_20261017.py --check        # gate (exit 1 on gaps)
    python tools/answer_provenance_markers_20261017.py --json out.json
    python tools/answer_provenance_markers_20261017.py --paths 省考/江苏
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Answer blocks are emitted as fenced <details> blocks keyed by the printed 题号.
BLOCK_OPEN = re.compile(r"<details>\s*\n<summary>\s*第\s*(\d+)\s*题\s*</summary>", re.M)
BLOCK_CLOSE = re.compile(r"^[ \t]*</details>[ \t]*$", re.M)

# The two forms the repository settled on. Everything else that still discloses
# provenance is a format variant, not a defect.
CANONICAL_MARKERS = (
    "**来源参考解析（非官方标准答案）**",
    "**AI辅助独立校核解析（非官方答案，非王智公考原解析，未经实考评分）**",
)

# Any bolded marker that is clearly an answer-provenance label.
MARKER_RE = re.compile(r"\*\*[^*\n]*?(?:来源参考解析|AI辅助独立校核解析|答案性质)[^*\n]*?\*\*"
                       r"(（[^）\n]*）)?")

# Semantic test for "this block says where the answer came from".
#
# Deliberately broader than MARKER_RE: a block that states its provenance in prose, or
# that names an official source, must not be reported as undeclared just because it
# avoided the house marker. A checker that over-reports gets switched off.
DISCLOSURE_RE = re.compile(
    r"来源参考解析|AI辅助独立校核解析|答案性质|独立校算|"
    r"非官方|不是官方|官方公布答案|官方标准答案|官方发布|"
    r"培训机构|参考答案来源|答案来源"
)

# Classify a declared block into the taxonomy QUALITY.md line 40 defines, so the
# report tells a reader *which kind* of evidence each answer rests on.
#
# Order matters, and so does negation. `非官方标准答案` ('NON-official standard answer')
# contains the substring `官方标准答案`, so a naive pattern classifies the library's own
# disclaimer as an official key -- the exact inversion this checker exists to prevent.
# Every official pattern therefore carries an explicit negation guard, and `official`
# is matched last so a block that also names an institution is not upgraded to official.
AI_RE = re.compile(r"AI辅助独立校核解析|AI\s*辅助|原创校核解析|AI[\s-]*derived")
DISPUTE_RE = re.compile(r"校核提示|笔误|存疑|争议|质疑|逻辑问题")
INSTITUTION_RE = re.compile(r"来源参考解析|培训机构|机构参考答案|机构解析|来源解析")

OFFICIAL_RE = re.compile(r"官方(?:公布答案|标准答案|发布|答案)|(?:考试院|人社)[^。\n]{0,12}公布")
# Negation may sit anywhere in the clause before the claim, not just immediately
# before it: `并非本卷的独立官方答案` ('NOT this paper's independent official answer')
# puts four characters between `并非` and `官方`, so a fixed-width lookbehind misses it
# and the library's own disclaimer gets read as an official key -- the exact inversion
# this checker exists to prevent. Scan a window instead.
NEGATION_RE = re.compile(r"非|不|未|无")
# The negation set is deliberately broad (bare 不 / 非 / 未 / 无, not just
# 不是 / 并非) because the library phrases the disclaimer several ways:
#   非官方标准答案 / 并非本卷的独立官方答案 / 不将其改称原创或官方答案 / 也不称为官方答案
# A broad set can in principle suppress a genuine official claim sitting near an
# unrelated 不. That asymmetry is intentional: for this audit, missing an official
# key is far cheaper than asserting one that does not exist.
NEGATION_WINDOW = 14


def claims_official(block: str) -> bool:
    """True only if some mention of an official source is *not* negated."""
    for m in OFFICIAL_RE.finditer(block):
        window = block[max(0, m.start() - NEGATION_WINDOW):m.start()]
        if not NEGATION_RE.search(window):
            return True
    return False

MD_SUFFIX = ".md"


def iter_answer_blocks(text: str):
    """Yield (question_no, block_text, start, end) for each answer block."""
    for m in BLOCK_OPEN.finditer(text):
        rest = text[m.end():]
        c = BLOCK_CLOSE.search(rest)
        end = m.end() + (c.end() if c else len(rest))
        yield int(m.group(1)), text[m.start():end], m.start(), end


def classify_block(block: str) -> dict:
    marker = MARKER_RE.search(block)
    # group(0) already spans the trailing parenthetical, so do not append group(1).
    marker_text = marker.group(0) if marker else None
    declared = bool(DISCLOSURE_RE.search(block))
    canonical = any(cm in block for cm in CANONICAL_MARKERS)
    if AI_RE.search(block):
        authority = "ai_derived"
    elif DISPUTE_RE.search(block):
        authority = "solver_dispute"
    elif claims_official(block):
        authority = "official_published"
    elif INSTITUTION_RE.search(block):
        authority = "institution_reference"
    else:
        authority = None
    return {
        "declared": declared,
        "marker": marker_text,
        "canonical_marker": canonical,
        "authority_class": authority,
    }


def scan_file(path: Path, root: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    findings = []
    for qno, block, _s, _e in iter_answer_blocks(text):
        info = classify_block(block)
        if not info["declared"]:
            findings.append({
                "file": str(path.relative_to(root)),
                "question_no": qno,
                "issue": "undeclared",
                "marker": None,
                "authority_class": None,
            })
        elif not info["canonical_marker"]:
            findings.append({
                "file": str(path.relative_to(root)),
                "question_no": qno,
                "issue": "format_variant",
                "marker": info["marker"],
                "authority_class": info["authority_class"],
            })
        else:
            findings.append({
                "file": str(path.relative_to(root)),
                "question_no": qno,
                "issue": "ok",
                "marker": info["marker"],
                "authority_class": info["authority_class"],
            })
    return findings


def iter_markdown(root: Path, paths: list[str] | None):
    bases = [root / p for p in paths] if paths else [root / "国考", root / "省考"]
    for base in bases:
        if base.is_file() and base.suffix == MD_SUFFIX:
            yield base
            continue
        if not base.exists():
            continue
        for p in sorted(base.rglob("*" + MD_SUFFIX)):
            yield p


def scan(root: Path, paths: list[str] | None = None) -> dict:
    findings: list[dict] = []
    files = 0
    for path in iter_markdown(root, paths):
        files += 1
        findings.extend(scan_file(path, root))

    undeclared = [f for f in findings if f["issue"] == "undeclared"]
    variants = [f for f in findings if f["issue"] == "format_variant"]

    by_marker: dict[str, int] = {}
    for f in variants:
        # A block may declare provenance in prose without any bold marker at all;
        # keep that bucket keyed by a string so the report stays JSON-serialisable.
        key = f["marker"] or "(declared in prose, no bold marker)"
        by_marker[key] = by_marker.get(key, 0) + 1

    by_file: dict[str, int] = {}
    for f in undeclared:
        by_file[f["file"]] = by_file.get(f["file"], 0) + 1

    # Roll authority up over EVERY declared block, not only the canonically-spelled
    # ones. Many AI-assisted blocks declare themselves in prose, so counting only
    # canonical spellings undercounts AI-derived answers by orders of magnitude and
    # would make them look like institution-sourced keys.
    by_authority: dict[str, int] = {}
    for f in findings:
        if f["issue"] != "undeclared":
            key = f["authority_class"] or "unclassified"
            by_authority[key] = by_authority.get(key, 0) + 1

    # Per-paper breakdown of AI-derived blocks: the distinction this repository most
    # needs to keep visible is model re-derivation vs a published key.
    ai_by_file: dict[str, int] = {}
    for f in findings:
        if f["issue"] != "undeclared" and f["authority_class"] == "ai_derived":
            ai_by_file[f["file"]] = ai_by_file.get(f["file"], 0) + 1

    return {
        "schemaVersion": 1,
        "root": str(root),
        "filesScanned": files,
        "answerBlocks": len(findings),
        "declared": len(findings) - len(undeclared),
        "undeclared": len(undeclared),
        "undeclaredFiles": len(by_file),
        "formatVariants": len(variants),
        "formatVariantsByMarker": dict(sorted(by_marker.items(), key=lambda kv: -kv[1])),
        "authorityClasses": by_authority,
        "aiDerivedBlocks": sum(ai_by_file.values()),
        "aiDerivedFiles": len(ai_by_file),
        "worstAiDerivedFiles": sorted(ai_by_file.items(), key=lambda kv: -kv[1])[:20],
        "canonicalMarkers": list(CANONICAL_MARKERS),
        "worstUndeclaredFiles": sorted(by_file.items(), key=lambda kv: -kv[1])[:20],
        "undeclaredFindings": undeclared,
        "formatVariantFindings": variants,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--paths", nargs="*", help="limit to these paths under --root")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when any answer block declares no provenance")
    ap.add_argument("--json", type=Path, help="write the full machine-readable report here")
    ap.add_argument("--max-findings", type=int, default=0,
                    help="cap the per-finding arrays in --json (0 = no cap). The summary "
                         "counts are always complete; the full list is regenerable.")
    ap.add_argument("--show-variants", action="store_true",
                    help="list format variants too (informational)")
    args = ap.parse_args()

    result = scan(args.root, args.paths)

    if args.json:
        payload = result
        if args.max_findings:
            payload = dict(result)
            payload["findingsTruncatedTo"] = args.max_findings
            payload["undeclaredFindings"] = result["undeclaredFindings"][:args.max_findings]
            payload["formatVariantFindings"] = result["formatVariantFindings"][:args.max_findings]
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                             encoding="utf-8")

    print(f"files scanned        : {result['filesScanned']}")
    print(f"answer blocks        : {result['answerBlocks']}")
    print(f"declared provenance  : {result['declared']}")
    print(f"UNDECLARED           : {result['undeclared']} across {result['undeclaredFiles']} files")
    print(f"format variants      : {result['formatVariants']} (informational)")
    if result["authorityClasses"]:
        print("authority classes (all declared blocks):")
        for k, v in sorted(result["authorityClasses"].items(), key=lambda kv: -kv[1]):
            print(f"    {v:6}  {k}")
    if result["formatVariantsByMarker"]:
        print("format variants by spelling:")
        for k, v in result["formatVariantsByMarker"].items():
            print(f"    {v:6}  {k}")
    print(f"AI-derived blocks    : {result['aiDerivedBlocks']} across {result['aiDerivedFiles']} files")
    if result["worstAiDerivedFiles"]:
        print("files with the most AI-derived blocks:")
        for f, n in result["worstAiDerivedFiles"][:10]:
            print(f"    {n:6}  {f}")
    if result["worstUndeclaredFiles"]:
        print("files with the most undeclared blocks:")
        for f, n in result["worstUndeclaredFiles"]:
            print(f"    {n:6}  {f}")
    if args.show_variants and result["formatVariantFindings"]:
        for f in result["formatVariantFindings"][:200]:
            print(f"    variant {f['file']} 第{f['question_no']}题  {f['marker']}")

    if args.check and result["undeclared"]:
        print(f"\nFAIL: {result['undeclared']} answer block(s) declare no provenance.",
              file=sys.stderr)
        return 1
    if args.check:
        print("\nOK: every answer block declares its provenance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
