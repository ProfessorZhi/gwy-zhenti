#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic per-paper quality + answer-source index for the 1,169-paper library.

One pass, read-only, no network, no OCR. Emits one JSONL row per paper and a derived
priority-ticket list.

Grain: **one row per paper**. A paper with several defects appears once, with every
defect listed in `flags`. Counts in the summary are therefore paper counts, never
defect counts summed across papers -- the point is to avoid counting the same paper
several times.

Inputs
------
* the library Markdown itself (省考/, 国考/)
* `reports/QUALITY-AUDIT.md` -- the repository's own machine-warning ledger
* the git tree at the audited commit, for image-path existence (no blob checkout)

Provenance states come from `answer_provenance_markers_20261017` so there is exactly
one definition of `verified` / `source-present` / `unsupported` in this lane.

Determinism
-----------
Rows are sorted by path. No clock value, no absolute paths, no iteration-order
dependent fields are written. Re-running on the same commit reproduces the files
byte-for-byte; `--self-check` asserts that.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer_provenance_markers_20261017 as prov  # noqa: E402

# Question heading: H2 for standalone items, H3 under `## 材料 N（第X—Y题共用）`.
Q_HEAD = re.compile(r"^(#{2,3})\s*第\s*(\d+)\s*题", re.M)
MATERIAL_HEAD = re.compile(r"^##\s*材料\s*\d+", re.M)
# Option labels run A-H in the library (陕西 uses E/F/G/H on 8-option items),
# not just A-D. An A-D-only pattern under-counted options and made those papers
# look option-less.
OPT_LINE = re.compile(r"^-\s*\*\*([A-H])\*\*[.．、]?\s*(.*)$", re.M)
IMG_SRC = re.compile(r'src="([^"]+)"')
# Answers may be multi-select (`**答案**：AB`, 上海 has 多选题). A single-letter
# pattern reported 42 papers as missing 12-19 answers each; they were AB/ABC answers.
ANSWER_LINE = re.compile(
    r"\*\*答案\*\*\s*[：:]\s*\**\s*([A-H](?:\s*[、,，/]?\s*[A-H]){0,7})\b")
# Some papers deliberately answer in prose instead of a letter -- e.g. 江西2019 法检
# 第41题 explains that no existing option matches its computed value and declines to
# give a letter. That is correct handling, not a missing answer.
PROSE_ANSWER = re.compile(r"\*\*参考作答\*\*\s*[：:]")
# Legacy answers are quarantined between a PAIR of HTML comments:
#   <!-- legacy-unverified-answer-54 --> ... <!-- /legacy-unverified-answer-54 -->
# Stripping only the comment tags leaves the enclosed legacy answer in the block, which
# then counts as a current answer. Remove the whole wrapped span.
COMMENT = re.compile(r"<!--.*?-->", re.S)
QUARANTINE = re.compile(
    r"<!--\s*legacy-unverified-answer-\d+\s*-->.*?<!--\s*/legacy-unverified-answer-\d+\s*-->", re.S)


def strip_quarantined(block: str) -> str:
    return COMMENT.sub("", QUARANTINE.sub("", block))
# A link to this repository's own history documents what the library used to say; it
# is not independent evidence of where an answer came from. Counting it as "backed"
# made the audit corroborate itself: 241 blocks were "verified" on that basis alone.
SELF_REPO = re.compile(r"^https?://(?:www\.)?github\.com/ProfessorZhi/gwy-zhenti(?:/|$)")

# Quality-ledger issue strings that are boilerplate rather than a substantive gap.
BOILERPLATE_ISSUE = "历史模块拼接题序未获原卷证据核对"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tracked_paths(repo: Path, commit: str) -> set[str]:
    """Image/figure paths that exist in the tree, without checking out blobs."""
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", commit],
        cwd=repo, capture_output=True, text=True)
    if out.returncode != 0:
        return set()
    return {line for line in out.stdout.splitlines() if line}


def parse_quality_ledger(path: Path) -> tuple[dict, dict]:
    """Return ({paper: issues[]}, header_counts) from QUALITY-AUDIT.md."""
    if not path.exists():
        return {}, {}
    text = path.read_text(encoding="utf-8")
    rows = re.findall(r"^\| \[([^\]]+)\]\(([^)]+)\) \| ([^|]+) \|$", text, re.M)
    issues: dict[str, list[str]] = {}
    for label, _link, issue in rows:
        parts = [p.strip() for p in re.split(r"[；;]", issue) if p.strip()]
        issues[label] = parts
    header = {}
    m = re.search(r"正文文件\s*(\d+)\s*份；有规则告警\s*(\d+)\s*份", text)
    if m:
        header["declared_files"] = int(m.group(1))
        header["declared_flagged"] = int(m.group(2))
    m = re.search(r"已明确缺原题\s*(\d+)\s*道", text)
    if m:
        header["declared_missing_original"] = int(m.group(1))
    return issues, header


def split_questions(text: str) -> list[tuple[int, str]]:
    """Return [(question_no, block_text)] cutting at the next question or material head."""
    body = text
    cut = body.find("## 答案与解析")
    if cut >= 0:
        body = body[:cut]
    hits = list(Q_HEAD.finditer(body))
    bounds = sorted([h.start() for h in hits] + [h.start() for h in MATERIAL_HEAD.finditer(body)])
    out = []
    for h in hits:
        end = next((b for b in bounds if b > h.start()), len(body))
        out.append((int(h.group(2)), body[h.start():end]))
    return out


def classify_issue(issue: str) -> str:
    if issue == BOILERPLATE_ISSUE:
        return "ordering_provenance_unverified"
    if "缺原题" in issue:
        return "original_missing"
    if "选项缺失" in issue:
        return "option_missing"
    if "共用题干条件缺失" in issue or "关键条件缺失" in issue:
        return "stem_condition_gap"
    if "主图缺失" in issue:
        return "image_bytes_missing"
    if "争议" in issue:
        # Distinct from official_label_conflict: the ledger's 争议 is a disagreement
        # about a question's text/conditions, not a mislabelled authority claim.
        return "content_dispute"
    if "答案未收录" in issue:
        return "answer_missing"
    if "答案数量与题量不一致" in issue:
        return "answer_count_mismatch"
    if "材料中间缺段" in issue:
        return "material_gap"
    if "回忆版不全" in issue:
        return "recall_incomplete"
    if "题号非连续" in issue:
        return "numbering_non_contiguous"
    if "单一整理版来源" in issue:
        return "single_source_unverified"
    return "other"


def analyse_paper(path: Path, repo: Path, tree: set[str], receipt_index: set,
                  ledger_issues: list[str] | None) -> dict:
    text = path.read_text(encoding="utf-8")
    fm = prov.parse_frontmatter(text)
    rel = str(path.relative_to(repo))

    qs = split_questions(text)
    opt_counts = {n: len(OPT_LINE.findall(b)) for n, b in qs}
    imgs = []
    for _n, b in qs:
        imgs.extend(IMG_SRC.findall(b))

    # Resolve image refs against the tree (repo-relative), not the filesystem: the
    # audit worktree is sparse and does not check out 图片/.
    missing_imgs = []
    unresolved_imgs = []
    for ref in imgs:
        if ref.startswith(("http://", "https://", "data:")):
            unresolved_imgs.append(ref)
            continue
        target = (path.parent / ref).resolve()
        try:
            rel_target = str(target.relative_to(repo.resolve()))
        except ValueError:
            missing_imgs.append(ref)
            continue
        if rel_target not in tree:
            missing_imgs.append(ref)

    blocks = list(prov.iter_answer_blocks(text))
    fp = prov.file_provenance(fm, receipt_index)
    cov = {"verified": 0, "source-present": 0, "unsupported": 0}
    for _n, b, _s, _e in blocks:
        bc = strip_quarantined(b)
        info = prov.classify_block(bc)
        bh = [h.lower() for h in prov.HEX64_RE.findall(bc)]
        burl = prov.URL_RE.findall(bc)
        backed = (any(h in receipt_index for h in bh)
                  or any(u in receipt_index for u in burl if not SELF_REPO.match(u)))
        if info["declared"]:
            cov["verified" if backed else "source-present"] += 1
        elif fp["state"] in ("explicit_answer_source", "detail_names_answers"):
            cov["verified" if fp["backed"] else "source-present"] += 1
        elif fp["state"] == "source_list_only":
            cov["source-present"] += 1
        elif fp["state"] == "declared_absent" and info["declared"]:
            cov["source-present"] += 1
        else:
            cov["unsupported"] += 1

    # Current answers only: a quarantined legacy answer does not count as an answer.
    answers = [n for n, b, _s, _e in blocks
               if ANSWER_LINE.search(strip_quarantined(b))]
    prose_answers = [n for n, b, _s, _e in blocks
                     if PROSE_ANSWER.search(strip_quarantined(b))]

    flags = []
    if fm.get("缺失原题号") and fm["缺失原题号"] not in ("[]", ""):
        flags.append("original_missing")
    # Option checks apply to 行测 only. 申论 questions are essays and legitimately have
    # no A-D options; testing them there reported 718 papers as option-less.
    if fm.get("科目") == "行测":
        if any(c == 0 for c in opt_counts.values()):
            flags.append("option_missing")
        if any(0 < c < 4 for c in opt_counts.values()):
            flags.append("option_incomplete")
    if missing_imgs:
        flags.append("image_bytes_missing")
    if len(blocks) != len(qs):
        flags.append("answer_block_count_mismatch")
    answered = len(set(answers) | set(prose_answers))
    if fm.get("科目") == "行测" and answered and answered != len(qs):
        flags.append("letter_answer_count_mismatch")
    multi_select = sum(1 for n, b, _s, _e in blocks
                       if (m := ANSWER_LINE.search(strip_quarantined(b)))
                       and len(re.sub(r"[^A-D]", "", m.group(1))) > 1)
    if cov["unsupported"]:
        flags.append("answer_provenance_unsupported")
    if cov["source-present"] and not cov["verified"]:
        flags.append("answer_provenance_generic")
    if fp["official_claim_with_only_institutional_sources"]:
        flags.append("official_label_conflict")
    if fm.get("缺参考答案题号") and fm["缺参考答案题号"] not in ("[]", ""):
        flags.append("answer_missing")

    issue_classes = sorted({classify_issue(i) for i in (ledger_issues or [])})
    for c in issue_classes:
        if c not in flags and c != "ordering_provenance_unverified":
            flags.append(c)

    substantive = [f for f in flags if f not in
                   ("answer_provenance_generic", "ordering_provenance_unverified")]
    if substantive:
        priority = "P0"
    elif ledger_issues:
        priority = "P1"
    elif cov["source-present"] or cov["unsupported"]:
        priority = "P2"
    else:
        priority = "P3"

    return {
        "path": rel,
        "region": fm.get("地区"),
        "year": fm.get("年份"),
        "subject": fm.get("科目"),
        "variant": fm.get("卷型"),
        "paper_nature": fm.get("真题性质"),
        "declared_sources": fm.get("来源"),
        "declared_questions": _int(fm.get("实有题数")),
        "reference_questions": _int(fm.get("对照题本题量")),
        "declared_missing_original": fm.get("缺失原题号"),
        "question_blocks": len(qs),
        "questions_lt4_options": sum(1 for c in opt_counts.values() if 0 < c < 4),
        "questions_no_options": sum(1 for c in opt_counts.values() if c == 0),
        "image_refs": len(imgs),
        "image_refs_missing": len(missing_imgs),
        "image_refs_unresolved": len(unresolved_imgs),
        "answer_blocks": len(blocks),
        "letter_answers": len(answers),
        "multi_select_answers": multi_select,
        "prose_answers": len(prose_answers),
        "answer_block_count_matches_questions": len(blocks) == len(qs),
        "provenance_verified": cov["verified"],
        "provenance_source_present": cov["source-present"],
        "provenance_unsupported": cov["unsupported"],
        "file_provenance_state": fp["state"],
        "file_provenance_backed": fp["backed"],
        "quality_flagged": bool(ledger_issues),
        "quality_issues": sorted(ledger_issues or []),
        "issue_classes": issue_classes,
        "flags": sorted(set(flags)),
        "priority": priority,
    }


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--commit", default="e1feb5187ec3544cde62a1a128a6269a8d63011b")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--quality-ledger", type=Path, default=None)
    ap.add_argument("--self-check", action="store_true",
                    help="re-run and assert the output is byte-identical")
    args = ap.parse_args()

    repo = args.repo.resolve()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    ledger_path = args.quality_ledger or (repo / "reports" / "QUALITY-AUDIT.md")

    ledger, header = parse_quality_ledger(ledger_path)
    tree = tracked_paths(repo, args.commit)
    receipt_index = prov.build_receipt_index(repo)

    rows = []
    for p in sorted(prov.iter_markdown(repo, None)):
        rel = str(p.relative_to(repo))
        rows.append(analyse_paper(p, repo, tree, receipt_index, ledger.get(rel)))

    # Papers named by the ledger but absent from the tree (renamed/removed).
    seen = {r["path"] for r in rows}
    ledger_orphans = sorted(set(ledger) - seen)

    tickets = []
    for r in rows:
        if r["priority"] in ("P0", "P1", "P2"):
            tickets.append({
                "path": r["path"],
                "priority": r["priority"],
                "region": r["region"], "year": r["year"],
                "subject": r["subject"], "variant": r["variant"],
                "flags": r["flags"],
                "issue_classes": r["issue_classes"],
                "required_evidence": required_evidence(r),
            })

    summary = build_summary(rows, header, ledger_orphans, args.commit)
    summary["selfCheckStable"] = None

    _write(out / "quality-index.jsonl", rows)
    _write(out / "priority-tickets.jsonl", tickets)
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.self_check:
        first = {p.name: sha256_bytes(p.read_bytes()) for p in sorted(out.glob("*"))}
        rows2 = []
        for p in sorted(prov.iter_markdown(repo, None)):
            rows2.append(analyse_paper(p, repo, tree, receipt_index,
                                       ledger.get(str(p.relative_to(repo)))))
        _write(out / "quality-index.jsonl", rows2)
        second = {p.name: sha256_bytes(p.read_bytes()) for p in sorted(out.glob("*"))}
        if first["quality-index.jsonl"] != second["quality-index.jsonl"]:
            print("SELF-CHECK FAILED: index not byte-identical on re-run", file=sys.stderr)
            return 1
        print("self-check: byte-identical on re-run")

    print(json.dumps({k: v for k, v in summary.items() if k != "by_region"}, ensure_ascii=False, indent=2))
    return 0


def required_evidence(row: dict) -> list[str]:
    """What a reviewer would need to close each flag -- named, not guessed."""
    out = []
    f = set(row["flags"])
    if "original_missing" in f:
        out.append("原卷扫描件或官方题本，覆盖 缺失原题号 所列题位")
    if "option_missing" in f or "option_incomplete" in f:
        out.append("原卷该题的完整四个选项（扫描件或官方题本）")
    if "image_bytes_missing" in f:
        out.append("缺失的题干/选项图原图字节（按题号对应；台账声明缺图，结构扫描未发现悬空引用）")
    if "stem_condition_gap" in f:
        out.append("共用题干/关键条件的原文段落")
    if "official_label_conflict" in f:
        out.append("答案发布方署名证据（版权页/页眉），以裁定「官方」称谓")
    if "content_dispute" in f:
        out.append("该争议题的完整原题与来源解析原文，以裁定条件歧义")
    if "answer_provenance_generic" in f or "answer_provenance_unsupported" in f:
        out.append("该卷答案的具体来源标识（sha256/URL 或具名出版物），并留存于 reports/")
    if "answer_missing" in f:
        out.append("该卷参考答案原文及出处")
    if "ordering_provenance_unverified" in f:
        out.append("原卷题序证据（官方目录页或原卷扫描顺序）")
    if "single_source_unverified" in f:
        out.append("第二独立来源或原卷，以交叉复核单一整理版")
    if "material_gap" in f:
        out.append("原卷材料的完整段落（被截断/缺失处）")
    if "recall_incomplete" in f:
        out.append("该卷完整版原卷或另一独立回忆版")
    if "numbering_non_contiguous" in f:
        out.append("原卷题号顺序证据")
    if "answer_count_mismatch" in f or "answer_block_count_mismatch" in f:
        out.append("该卷参考答案原文，使其与题量一致")
    if not out:
        out.append("该卷原卷或具名公开来源，以裁定缺口性质")
    return sorted(set(out))


def build_summary(rows, header, orphans, commit) -> dict:
    def count(pred):
        return sum(1 for r in rows if pred(r))

    prio = {}
    for r in rows:
        prio[r["priority"]] = prio.get(r["priority"], 0) + 1

    by_region = {}
    for r in rows:
        if r["priority"] in ("P0", "P1", "P2"):
            key = r["region"] or "?"
            by_region.setdefault(key, {"P0": 0, "P1": 0, "P2": 0})
            by_region[key][r["priority"]] += 1

    flagged = [r for r in rows if r["quality_flagged"]]
    return {
        "schemaVersion": 1,
        "auditedCommit": commit,
        "papers": len(rows),
        "qualityFlagged": len(flagged),
        "qualityLedgerDeclared": header,
        "qualityLedgerOrphans": orphans,
        # Grain: one row per paper. These are paper counts, not defect counts.
        "structural": {
            "papersWithOriginalMissing": count(lambda r: "original_missing" in r["flags"]),
            "papersWithOptionMissing": count(lambda r: "option_missing" in r["flags"]),
            "papersWithOptionIncomplete": count(lambda r: "option_incomplete" in r["flags"]),
            "papersWithMissingImageBytes": count(lambda r: "image_bytes_missing" in r["flags"]),
            "papersWithAnswerBlockMismatch": count(lambda r: not r["answer_block_count_matches_questions"]),
            "papersWithLetterAnswerMismatch":
                count(lambda r: "letter_answer_count_mismatch" in r["flags"]),
            "totalMultiSelectAnswers": sum(r["multi_select_answers"] for r in rows),
            "papersLedgerDeclaresImageGap":
                count(lambda r: "image_bytes_missing" in r["flags"]),
            "totalMissingImageRefs": sum(r["image_refs_missing"] for r in rows),
            "papersWithZeroQuestions": count(lambda r: r["question_blocks"] == 0),
        },
        "provenance": {
            "answerBlocks": sum(r["answer_blocks"] for r in rows),
            "verified": sum(r["provenance_verified"] for r in rows),
            "sourcePresent": sum(r["provenance_source_present"] for r in rows),
            "unsupported": sum(r["provenance_unsupported"] for r in rows),
            "papersFullyVerified": count(
                lambda r: r["answer_blocks"] > 0 and r["provenance_verified"] == r["answer_blocks"]),
            "papersGenericOnly": count(
                lambda r: r["answer_blocks"] > 0 and r["provenance_verified"] == 0),
            "papersWithUnsupported": count(lambda r: r["provenance_unsupported"] > 0),
        },
        "priority": prio,
        "priorityByRegion": dict(sorted(by_region.items())),
        "flags": _flag_counts(rows),
        "issueClasses": _issue_counts(rows),
    }


def _flag_counts(rows) -> dict:
    c = {}
    for r in rows:
        for f in r["flags"]:
            c[f] = c.get(f, 0) + 1
    return dict(sorted(c.items()))


def _issue_counts(rows) -> dict:
    c = {}
    for r in rows:
        for i in r["issue_classes"]:
            c[i] = c.get(i, 0) + 1
    return dict(sorted(c.items()))


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
