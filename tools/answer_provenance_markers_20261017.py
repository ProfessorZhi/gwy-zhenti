#!/usr/bin/env python3
"""Check that every answer declares where it came from, and how well that is backed.

Why this exists
---------------
QUALITY.md requires each question to record 答案来源, and distinguishes 官方公布答案 /
培训机构参考答案 / 解题者争议观点. Nothing enforced it. A reader (or a renderer, or a
downstream QA agent) therefore cannot tell, from a given answer, whether the key is an
official publication, an institution's reference answer, or a model's re-derivation --
and an answer that silently looks authoritative is the exact failure mode this
repository's own policy is written to prevent.

Where provenance may live
-------------------------
The library uses **two** conventions, and a checker that knows only one over-reports:

1. **Block level** -- a marker inside `<details><summary>第 N 题</summary>`:
   `**来源参考解析（非官方标准答案）**`, `**AI辅助独立校核解析…**`, `**答案性质**`,
   or a prose 来源说明.
2. **File level** -- frontmatter fields `答案来源` / `来源明细` / `来源` / `来源路径`,
   sometimes with a sha256 or URL. A paper may declare one answer source for all 120
   questions and say nothing per block. That is a real declaration, not a gap.

An earlier revision of this tool scanned only block bodies and reported 1,555
"undeclared" blocks. Roughly half of those papers were in fact declared at file level
(e.g. 内蒙古2020 行测-统考 sets `答案来源: "同上《参考答案及解析》PDF"`). The number was
wrong, and the error was in the direction that gets an audit ignored.

Three coverage states
---------------------
* `verified`   -- declared AND the cited source is stably identified (sha256/URL) AND
                  that identifier appears in a retained receipt under reports/.
                  This verifies the *provenance declaration*, never the answer's
                  correctness.
* `source-present` -- declared, with a source named, but no retained receipt backs the
                  named identifier (or the source is named only by name).
* `unsupported` -- nothing declares where this answer came from.

Negation is evaluated at both levels. `答案来源: "缺（两源均无此卷答案）"` declares that
there is *no* source; counting it as a declaration would invert its meaning.

No question, answer or explanation text is modified. `--json` is machine-readable.
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
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)

# The two forms the repository settled on. Everything else that still discloses
# provenance is a format variant, not a defect.
CANONICAL_MARKERS = (
    "**来源参考解析（非官方标准答案）**",
    "**AI辅助独立校核解析（非官方答案，非王智公考原解析，未经实考评分）**",
)

MARKER_RE = re.compile(r"\*\*[^*\n]*?(?:来源参考解析|AI辅助独立校核解析|答案性质)[^*\n]*?\*\*"
                       r"(（[^）\n]*）)?")

# Semantic test for "this block says where the answer came from".
#
# The library uses 36 distinct bold provenance labels, not one. A checker that knows
# only the canonical string reports whole papers as undeclared when they in fact carry
# excellent per-question citations -- e.g. 黑龙江2019 行测-边境县 declares, for every
# question, the source PDF, its SHA-256, the fact that it is an institution/individual
# compilation, and that it is *not* an official answer, under the label
# `**参考解析（用户提供资料）**` plus a `**来源**：` line. None of those matched a
# `来源参考解析` literal, so all 120 were reported as gaps.
#
# Matching on the semantic family instead of one spelling is what keeps the gap list
# trustworthy. It is deliberately a little broad: for this audit a missed gap is
# cheaper than a fabricated accusation against a well-cited paper.
DISCLOSURE_RE = re.compile(
    # any bold label in the provenance family
    r"\*\*[^*\n]{0,40}(?:来源|解析|答案性质|校核|参考答案|参考作答)[^*\n]{0,40}\*\*|"
    # provenance stated in prose
    r"非官方|不是官方|官方公布答案|官方标准答案|官方发布|"
    r"培训机构|机构/个人整理|用户提供|独立校算|"
    # stable identifiers that only appear in a provenance line
    r"SHA-?256|源文件|"
    # a markdown link whose label names the provenance, e.g.
    # `[本题来源参考答案](https://…)` -- used by the essay papers
    r"\[[^\]\n]{0,40}(?:来源|参考答案|解析)[^\]\n]{0,40}\]\([^)\n]+\)"
)

AI_RE = re.compile(r"AI辅助独立校核解析|AI\s*辅助|原创校核解析|AI[\s-]*derived")
DISPUTE_RE = re.compile(r"校核提示|笔误|存疑|争议|质疑|逻辑问题")
INSTITUTION_RE = re.compile(r"来源参考解析|培训机构|机构参考答案|机构解析|来源解析")

OFFICIAL_RE = re.compile(r"官方(?:公布答案|标准答案|发布|答案)|(?:考试院|人社)[^。\n]{0,12}公布")
NEGATION_RE = re.compile(r"非|不|未|无|缺|没有")
NEGATION_WINDOW = 14

HEX64_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
# A link to this repository's own history documents what the library used to say; it is
# not independent evidence of where an answer came from. Counting it as "backed" made
# the audit corroborate itself: 241 blocks were verified on that basis alone.
SELF_REPO_URL = re.compile(r"^https?://(?:www\.)?github\.com/ProfessorZhi/gwy-zhenti(?:/|$)")
# Legacy answers are quarantined between a PAIR of HTML comments. They are not current
# answers, so their citations must not be credited as provenance for the question.
QUARANTINE = re.compile(
    r"<!--\s*legacy-unverified-answer-\d+\s*-->.*?<!--\s*/legacy-unverified-answer-\d+\s*-->",
    re.S)


def strip_quarantined(block: str) -> str:
    """Remove quarantined legacy spans before judging provenance."""
    return QUARANTINE.sub("", block)
URL_RE = re.compile(r"https?://[^\s)\]\"'>]+")

# Named corpora / institutions that are third-party by construction. If a paper claims
# an official source while its declared 来源 are only these, the claim needs adjudication.
INSTITUTION_SOURCE_TOKENS = (
    "huatu", "gwyeasy", "xingcezhenti", "linfukai186", "zhonggong", "fenbi",
    "shiwuooo", "errrc", "zzcc", "wangzhi", "jygwy", "32xueyuan", "wuhoushu",
    "xingguang", "中公", "华图", "粉笔", "王智", "展鸿",
)

# Frontmatter keys that can carry answer provenance. Derived by enumerating the 118
# distinct keys actually in use, not by guessing: a checker that knows only `来源`
# misses papers that record their evidence under `来源补录凭据`, `来源整卷SHA256`,
# `第六轮原始资料补答案凭据` and a dozen other names.
FILE_SOURCE_KEYS = (
    "答案来源", "来源明细", "来源整卷", "来源整卷SHA256", "来源补录凭据",
    "第六轮原始资料补答案凭据", "补全来源", "补全证据", "完整题本固定来源",
    "来源路径", "来源题本文件", "补题核验来源", "补题证据", "题序对照来源",
    "题序证据", "分卷核对证据", "北京答案修复凭据", "原始ZIP来源SHA256",
    "外部答案收录形式", "已定位外部答案来源题号", "来源链接", "题量校核来源",
    "题面约束来源", "来源", "新增答案性质", "整卷核验状态", "校验状态",
)

MD_SUFFIX = ".md"


def claims_official(text: str) -> bool:
    """True only if some mention of an official source is *not* negated.

    Negation may sit anywhere in the clause before the claim, not immediately before
    it: `并非本卷的独立官方答案` puts four characters between `并非` and `官方`, and
    `不将其改称原创或官方答案` uses a bare `不`. A fixed-width lookbehind misses both
    and reads the library's own disclaimer as an official key.

    The negation set is intentionally broad. It can in principle suppress a genuine
    official claim sitting near an unrelated 不; that asymmetry is deliberate -- for
    this audit, missing a real official key is far cheaper than asserting one that
    does not exist.
    """
    for m in OFFICIAL_RE.finditer(text or ""):
        window = text[max(0, m.start() - NEGATION_WINDOW):m.start()]
        if not NEGATION_RE.search(window):
            return True
    return False


OFFICIAL_BROAD_RE = re.compile(r"官方")


def claims_official_broad(text: str) -> bool:
    """Official-claim detector for *frontmatter provenance fields only*.

    Provenance notes say things like `答案 同批官方《行政职业能力测验解析》PDF`, where
    官方 is followed by a book title rather than by 答案/解析. The strict detector used
    on question bodies would miss that, but a bare 官方 match on a question body would
    fire on ordinary exam text about government. The two contexts therefore get
    different detectors, each appropriate to its noise level.
    """
    for m in OFFICIAL_BROAD_RE.finditer(text or ""):
        window = text[max(0, m.start() - NEGATION_WINDOW):m.start()]
        if not NEGATION_RE.search(window):
            return True
    return False


def is_negated_absent(value: str) -> bool:
    """True when a provenance field declares the source to be *missing*.

    `答案来源: "缺（两源均无此卷答案）"` says there is no source. Treating the mere
    presence of the key as a declaration would invert its meaning.
    """
    if not value:
        return False
    return bool(re.search(r"^\s*(缺|无|暂无|未收录|没有)|(均无|均缺|两源均|无此卷|未找到)", value))


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER.match(text or "")
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v.startswith('"') and v.endswith('"') and len(v) >= 2:
            v = v[1:-1]
        fm[k] = v
    return fm


def build_receipt_index(root: Path) -> set:
    """Collect stable identifiers (sha256 hex, URLs) retained anywhere under reports/docs.

    A source cited by sha256 is only checkable if that hash is recorded somewhere in
    the repository. If it is not, the citation is an assertion, not evidence.
    """
    index = set()
    for sub in ("reports", "docs", "catalog"):
        base = root / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.stat().st_size > 8 * 1024 * 1024:
                continue
            # Never let this audit lane's own output seed the evidence index. Its
            # reports quote the very hashes the audit is checking, so including them
            # would make the audit cite itself as corroboration and silently upgrade
            # an unbacked citation to `verified`. The full prefix is excluded, not
            # just the tool's own filename, because the pending-list report quotes
            # hashes too.
            if p.name.startswith("ANSWER-PROVENANCE-"):
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            index.update(h.lower() for h in HEX64_RE.findall(txt))
            index.update(URL_RE.findall(txt))
    return index


def file_provenance(fm: dict, receipt_index: set) -> dict:
    """Classify what the frontmatter says about where the answers came from."""
    values = {k: fm.get(k, "") for k in FILE_SOURCE_KEYS if fm.get(k)}
    blob = " ".join(values.values())

    explicit = fm.get("答案来源", "")
    absent = is_negated_absent(explicit)

    hashes = sorted({h.lower() for h in HEX64_RE.findall(blob)})
    urls = sorted(set(URL_RE.findall(blob)))
    backed = [h for h in hashes if h in receipt_index]

    # Keys that name where the answers specifically came from, as opposed to keys that
    # only record the question paper's source or a generic verification note.
    DETAIL_KEYS = ("来源明细", "来源整卷", "来源补录凭据", "来源整卷SHA256",
                   "第六轮原始资料补答案凭据", "补全来源", "补全证据",
                   "完整题本固定来源", "补题证据", "补题核验来源")

    if absent:
        state = "declared_absent"
    elif explicit:
        state = "explicit_answer_source"
    elif any(fm.get(k) for k in DETAIL_KEYS) or (
            re.search(r"答案", fm.get("来源明细", ""))):
        state = "detail_names_answers"
    elif fm.get("来源"):
        state = "source_list_only"
    else:
        state = "none"

    declared_sources = fm.get("来源", "")
    institutional_only = False
    if declared_sources:
        low = declared_sources.lower()
        institutional_only = any(t in low for t in INSTITUTION_SOURCE_TOKENS) and not re.search(
            r"官方|考试院|人社", declared_sources)

    return {
        "state": state,
        "fields": sorted(values),
        "answer_source_field": explicit or None,
        "declared_absent": absent,
        "cited_hashes": hashes,
        "cited_urls": urls,
        "backed_hashes": backed,
        "backed": bool(backed) or bool([u for u in urls
                                        if u in receipt_index and not SELF_REPO_URL.match(u)]),
        "claims_official": claims_official_broad(blob),
        "sources_institutional_only": institutional_only,
        "official_claim_with_only_institutional_sources":
            bool(claims_official_broad(blob) and institutional_only),
    }


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


def scan_file(path: Path, root: Path, receipt_index: set) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    fp = file_provenance(parse_frontmatter(text), receipt_index)
    findings = []
    for qno, block, _s, _e in iter_answer_blocks(text):
        # Judge provenance on the *current* content only.
        block = strip_quarantined(block)
        info = classify_block(block)
        block_declared = info["declared"]

        # Three-state coverage.
        #
        # `verified` means the *declaration* is checkable: a source is named AND a
        # stable identifier for it (sha256 / URL) appears in a retained receipt under
        # reports/. It never means the answer is correct, and a bare
        # `来源参考解析（非官方标准答案）` with no identifier is `source-present`, not
        # verified -- the paper says what *kind* of key it is without saying which one.
        block_hashes = [h.lower() for h in HEX64_RE.findall(block)]
        block_urls = URL_RE.findall(block)
        block_backed = (any(h in receipt_index for h in block_hashes)
                        or any(u in receipt_index for u in block_urls
                               if not SELF_REPO_URL.match(u)))

        if block_declared:
            coverage = "verified" if block_backed else "source-present"
        elif fp["state"] in ("explicit_answer_source", "detail_names_answers"):
            coverage = "verified" if fp["backed"] else "source-present"
        elif fp["state"] == "source_list_only":
            coverage = "source-present"
        else:
            coverage = "unsupported"

        # A block-level citation outranks a file-level "we have no source" note: the
        # note is often stale, written before a later repair filled the answers in.
        # But such a contradiction is itself worth reporting, because the frontmatter
        # then misdescribes the file to every reader and every tool.
        stale = bool(fp["state"] == "declared_absent" and block_declared)
        if fp["state"] == "declared_absent" and not block_declared:
            coverage = "unsupported"

        if coverage == "unsupported":
            issue = "undeclared"
        elif not block_declared:
            issue = "file_level_only"
        elif not info["canonical_marker"]:
            issue = "format_variant"
        else:
            issue = "ok"

        findings.append({
            "file": str(path.relative_to(root)),
            "question_no": qno,
            "issue": issue,
            "coverage": coverage,
            "marker": info["marker"],
            "authority_class": info["authority_class"],
            "block_declared": block_declared,
            "block_backed": block_backed,
            "file_state": fp["state"],
            "file_backed": fp["backed"],
            "stale_file_provenance": stale,
            "file_claims_official": fp["claims_official"],
            "official_claim_with_only_institutional_sources":
                fp["official_claim_with_only_institutional_sources"],
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


def scan(root: Path, paths: list[str] | None = None, receipt_index: set | None = None) -> dict:
    if receipt_index is None:
        receipt_index = build_receipt_index(root)
    findings: list[dict] = []
    files = 0
    for path in iter_markdown(root, paths):
        files += 1
        findings.extend(scan_file(path, root, receipt_index))

    by_coverage = {"verified": 0, "source-present": 0, "unsupported": 0}
    for f in findings:
        by_coverage[f["coverage"]] = by_coverage.get(f["coverage"], 0) + 1

    undeclared = [f for f in findings if f["issue"] == "undeclared"]
    variants = [f for f in findings if f["issue"] == "format_variant"]
    file_level = [f for f in findings if f["issue"] == "file_level_only"]

    by_marker: dict[str, int] = {}
    for f in variants:
        key = f["marker"] or "(declared in prose, no bold marker)"
        by_marker[key] = by_marker.get(key, 0) + 1

    by_file: dict[str, int] = {}
    for f in undeclared:
        by_file[f["file"]] = by_file.get(f["file"], 0) + 1

    # Roll authority up over EVERY declared block, not only canonically-spelled ones.
    by_authority: dict[str, int] = {}
    for f in findings:
        if f["issue"] != "undeclared":
            key = f["authority_class"] or "unclassified"
            by_authority[key] = by_authority.get(key, 0) + 1

    ai_by_file: dict[str, int] = {}
    for f in findings:
        if f["issue"] != "undeclared" and f["authority_class"] == "ai_derived":
            ai_by_file[f["file"]] = ai_by_file.get(f["file"], 0) + 1

    official_flags = sorted({f["file"] for f in findings
                             if f["official_claim_with_only_institutional_sources"]})

    # Frontmatter that says "no answer source" while the body cites one per question.
    stale_by_file: dict[str, int] = {}
    for f in findings:
        if f["stale_file_provenance"]:
            stale_by_file[f["file"]] = stale_by_file.get(f["file"], 0) + 1

    # Per-paper ledger: the read-only coverage view, one row per file that has answers.
    by_file_findings: dict[str, list[dict]] = {}
    for f in findings:
        by_file_findings.setdefault(f["file"], []).append(f)
    papers = []
    for rel, fs in sorted(by_file_findings.items()):
        try:
            fm = parse_frontmatter((root / rel).read_text(encoding="utf-8"))
        except OSError:
            fm = {}
        fp = file_provenance(fm, receipt_index)
        cov = {"verified": 0, "source-present": 0, "unsupported": 0}
        for f in fs:
            cov[f["coverage"]] = cov.get(f["coverage"], 0) + 1
        papers.append({
            "file": rel,
            "blocks": len(fs),
            "verified": cov["verified"],
            "source_present": cov["source-present"],
            "unsupported": cov["unsupported"],
            "file_state": fp["state"],
            "file_backed": fp["backed"],
            "cited_hashes": len(fp["cited_hashes"]),
            "backed_hashes": len(fp["backed_hashes"]),
            "cited_urls": len(fp["cited_urls"]),
            "declared_absent": fp["declared_absent"],
            "stale_file_provenance": any(f["stale_file_provenance"] for f in fs),
            "claims_official": fp["claims_official"],
            "official_claim_with_only_institutional_sources":
                fp["official_claim_with_only_institutional_sources"],
            "authority_classes": dict(sorted(
                {k: sum(1 for f in fs if f["authority_class"] == k)
                 for k in {(f["authority_class"] or "unclassified") for f in fs}}.items())),
        })

    return {
        "schemaVersion": 2,
        "root": str(root),
        "filesScanned": files,
        "answerBlocks": len(findings),
        "coverage": by_coverage,
        "declared": len(findings) - len(undeclared),
        "blockDeclared": sum(1 for f in findings if f["block_declared"]),
        "fileLevelOnly": len(file_level),
        "undeclared": len(undeclared),
        "undeclaredFiles": len(by_file),
        "formatVariants": len(variants),
        "formatVariantsByMarker": dict(sorted(by_marker.items(), key=lambda kv: -kv[1])),
        "authorityClasses": by_authority,
        "aiDerivedBlocks": sum(ai_by_file.values()),
        "aiDerivedFiles": len(ai_by_file),
        "officialClaimWithOnlyInstitutionalSources": official_flags,
        "staleFileProvenance": dict(sorted(stale_by_file.items(), key=lambda kv: -kv[1])),
        "staleFileProvenanceBlocks": sum(stale_by_file.values()),
        "worstAiDerivedFiles": sorted(ai_by_file.items(), key=lambda kv: -kv[1])[:20],
        "canonicalMarkers": list(CANONICAL_MARKERS),
        "worstUndeclaredFiles": sorted(by_file.items(), key=lambda kv: -kv[1])[:20],
        "undeclaredFindings": undeclared,
        "formatVariantFindings": variants,
        "papers": papers,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--paths", nargs="*", help="limit to these paths under --root")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when any answer declares no provenance at all")
    ap.add_argument("--json", type=Path, help="write the full machine-readable report here")
    ap.add_argument("--max-findings", type=int, default=0,
                    help="cap the per-finding arrays in --json (0 = no cap). The summary "
                         "counts are always complete; the full list is regenerable.")
    ap.add_argument("--ledger", type=Path,
                    help="write the per-paper coverage ledger (read-only view) here")
    ap.add_argument("--show-variants", action="store_true",
                    help="list format variants too (informational)")
    args = ap.parse_args()

    result = scan(args.root, args.paths)

    if args.json:
        # The per-paper ledger belongs in --ledger. Leaving it in the scan report made
        # that file 660 KB and duplicated the ledger wholesale.
        result = {k: v for k, v in result.items() if k != "papers"}
        payload = result
        if args.max_findings:
            payload = dict(result)
            payload["findingsTruncatedTo"] = args.max_findings
            payload["undeclaredFindings"] = result["undeclaredFindings"][:args.max_findings]
            payload["formatVariantFindings"] = result["formatVariantFindings"][:args.max_findings]
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                             encoding="utf-8")

    if args.ledger:
        ledger = {
            "schemaVersion": 1,
            "root": result["root"],
            "totals": {
                "filesScanned": result["filesScanned"],
                "answerBlocks": result["answerBlocks"],
                "coverage": result["coverage"],
                "aiDerivedBlocks": result["aiDerivedBlocks"],
                "staleFileProvenanceBlocks": result["staleFileProvenanceBlocks"],
                "officialClaimWithOnlyInstitutionalSources":
                    result["officialClaimWithOnlyInstitutionalSources"],
            },
            "papers": result["papers"],
        }
        args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True),
                               encoding="utf-8")

    c = result["coverage"]
    print(f"files scanned        : {result['filesScanned']}")
    print(f"answer blocks        : {result['answerBlocks']}")
    print(f"  verified           : {c['verified']}")
    print(f"  source-present     : {c['source-present']}")
    print(f"  unsupported        : {c['unsupported']}")
    print(f"declared (any level) : {result['declared']}")
    print(f"  block-level        : {result['blockDeclared']}")
    print(f"  file-level only    : {result['fileLevelOnly']}")
    print(f"UNSUPPORTED          : {result['undeclared']} across {result['undeclaredFiles']} files")
    print(f"format variants      : {result['formatVariants']} (informational)")
    if result["authorityClasses"]:
        print("authority classes (all declared blocks):")
        for k, v in sorted(result["authorityClasses"].items(), key=lambda kv: -kv[1]):
            print(f"    {v:6}  {k}")
    print(f"AI-derived blocks    : {result['aiDerivedBlocks']} across {result['aiDerivedFiles']} files")
    if result["staleFileProvenance"]:
        print(f"STALE frontmatter    : {result['staleFileProvenanceBlocks']} block(s) in "
              f"{len(result['staleFileProvenance'])} file(s) -- frontmatter says no source, "
              f"body cites one")
        for f, n in list(result["staleFileProvenance"].items())[:10]:
            print(f"    {n:6}  {f}")
    if result["officialClaimWithOnlyInstitutionalSources"]:
        print(f"OFFICIAL claim but only institutional sources declared: "
              f"{len(result['officialClaimWithOnlyInstitutionalSources'])} file(s)")
        for f in result["officialClaimWithOnlyInstitutionalSources"][:20]:
            print(f"    {f}")
    if result["formatVariantsByMarker"]:
        print("format variants by spelling:")
        for k, v in result["formatVariantsByMarker"].items():
            print(f"    {v:6}  {k}")
    if result["worstUndeclaredFiles"]:
        print("files with the most unsupported blocks:")
        for f, n in result["worstUndeclaredFiles"][:10]:
            print(f"    {n:6}  {f}")

    if args.check and result["undeclared"]:
        print(f"\nFAIL: {result['undeclared']} answer block(s) declare no provenance.",
              file=sys.stderr)
        return 1
    if args.check:
        print("\nOK: every answer block declares its provenance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
