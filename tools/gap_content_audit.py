#!/usr/bin/env python3
"""Read-only question-level gap scanner for current Markdown papers.

This scanner makes conservative findings: an absent source answer is not the
same as an unverified answer, and option words such as "缺失" may be genuine.
It never edits the corpus or reuses a historical gap count as a live count.

Usage:
  python tools/gap_content_audit.py --output /tmp/gap-issues.jsonl
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
QUESTION = re.compile(r"(?m)^#{2,3}[ \t]*第[ \t]*(\d+)[ \t]*题[^\n]*$")
DETAIL = re.compile(
    r"<details>\s*<summary>\s*第\s*(\d+)\s*题[^<]*</summary>(.*?)</details>",
    re.S,
)
OPTION = re.compile(
    r"(?m)^[ \t]*(?:[-*][ \t]+)?(?:\*\*([A-G])\*\*|([A-G]))"
    r"[ \t]*[.．、:：][ \t]*(.*)$"
)
FM = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.S)
EXPLICIT_NO_ANSWER = re.compile(
    r"未收录同卷同题的完整参考答案|本题尚未收录可核对的完整参考作答|"
    r"没有收录可核对的完整参考作答|尚未取得(?:同题)?参考答案|"
    r"答案状态[：:]\s*(?:unknown|待核实)|"
    r"本题暂无(?:参考)?答案|参考答案暂未收录",
    re.I,
)
A1_STUB = "粉笔暂未收录本题（来源缺题，题位保留）"
SHORT_STUBS = {"缺", "缺失", "暂缺", "待补", "待收录", "暂无"}
DEFAULT_ANSWER = re.compile(r"正确答案默认设置|暂以[ABCD]项代替|默认(?:设置)?为[ABCD]项")


def frontmatter(text: str) -> dict:
    m = FM.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        try:
            out[k.strip()] = json.loads(v)
        except ValueError:
            out[k.strip()] = v.strip('"')
    return out


def question_blocks(text: str):
    matches = list(QUESTION.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield int(m.group(1)), text[m.end():end]


def option_findings(stem: str) -> tuple[str, dict]:
    pairs = [(a or b, value.strip()) for a, b, value in OPTION.findall(stem)]
    choices = {}
    for letter, value in pairs:
        choices.setdefault(letter, value)
    # Judgment questions deliberately have only two valid choices.
    if set(choices) == {"A", "B"}:
        values = {re.sub(r"\s+", "", x).rstrip("。.") for x in choices.values()}
        if values <= {"正确", "错误", "对", "错", "是", "否"}:
            return "", {}
    abc = [choices.get(letter) for letter in "ABCD"]
    stubs = [letter for letter, value in zip("ABCD", abc)
             if value is not None and (
                 value.strip().rstrip("。.") in SHORT_STUBS
                 or bool(re.search(r"全力以赴征集|正确答案默认设置|题目缺失，正在征集", value))
             )]
    if len(stubs) >= 2:
        return "a2_confirmed_option_placeholders", {"stub_labels": stubs, "option_count": len(choices)}
    if len(stubs) == 1:
        # "A. 缺失" may be a real word in a fill-in-the-blank question.
        return "a2_review_single_option_word", {"stub_labels": stubs, "option_count": len(choices)}
    if 1 <= len(choices) < 4 and not any(x in choices for x in "EFG"):
        return "a2_review_option_format", {"option_labels": sorted(choices)}
    return "", {}


def answer_findings(body: str, subject: str, explicitly_missing: bool) -> str:
    if explicitly_missing or EXPLICIT_NO_ANSWER.search(body):
        return "b2_confirmed_explicit_no_answer"
    if not body:
        return "b2_review_no_details"
    # A normal answer may be a single A-D letter, a long essay or R7 text.
    explicit = (re.search(r"\*\*(?:参考答案[^*\n]*|答案)\*\*\s*[：:]?\s*(?:\n\s*)?\S", body)
                or re.search(r"正确答案[：:]\s*[A-G]", body)
                or re.search(r"\*\*同题参考作答\*\*\s*\n\s*\S", body))
    if not explicit and len(re.sub(r"<[^>]*>|\s+", "", body)) < 80:
        return "b2_review_short_unparsed_answer"
    return ""


def scan(root: Path) -> tuple[list[dict], dict]:
    manifest = root / "catalog/manifest.jsonl"
    inventory = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    counts = Counter()
    seen = set()
    for row in inventory:
        path = row["path"]
        paper = root / path
        raw = paper.read_text(encoding="utf-8-sig")
        fm = frontmatter(raw)
        subject = row.get("subject") or fm.get("科目", "")
        declared_missing = fm.get("缺参考答案题号") or []
        if not isinstance(declared_missing, list):
            declared_missing = []
        declared_missing = set(int(x) for x in declared_missing)
        details = {int(q): block for q, block in DETAIL.findall(raw)}
        blocks = list(question_blocks(raw))
        counts["paper_files"] += 1
        counts["question_blocks"] += len(blocks)
        if len(blocks) != row.get("question_anchors"):
            counts["papers_anchor_mismatch"] += 1
        if fm.get("从属佐证版") is True:
            # Source witness copies are not independent missing-answer debt.
            counts["dependent_copy_papers"] += 1
            counts["dependent_copy_question_positions"] += len(blocks)
            continue
        for number, block in blocks:
            key = (path, number)
            if key in seen:
                counts["duplicate_question_number"] += 1
                continue
            seen.add(key)
            counts["question_positions"] += 1
            # The stem precedes the first details block. Ignore trailing section
            # headings (e.g. "## 材料 3") after a question.
            stem = block.split("<details>", 1)[0].split("\n## 材料", 1)[0]
            if A1_STUB in stem:
                counts["a1_open_body_placeholder"] += 1
                continue
            counts["body_present"] += 1
            if subject == "行测":
                state, data = option_findings(stem)
                if state:
                    results.append({"path": path, "question": number, "type": state, "details": data})
                    counts[state] += 1
                if state == "a2_confirmed_option_placeholders":
                    results.append({"path": path, "question": number,
                                    "type": "answer_mapping_unverified_due_to_missing_options",
                                    "details": {}})
                    counts["answer_mapping_unverified_due_to_missing_options"] += 1
                if DEFAULT_ANSWER.search(block) and (
                    state == "a2_confirmed_option_placeholders" or "缺失" in stem
                ):
                    results.append({"path": path, "question": number,
                                    "type": "answer_unverified_default_option", "details": {}})
                    counts["answer_unverified_default_option"] += 1
            answer_state = answer_findings(
                details.get(number, ""),
                subject,
                number in declared_missing,
            )
            if answer_state:
                results.append({"path": path, "question": number,
                                "type": answer_state,
                                "details": {"frontmatter_missing": number in declared_missing,
                                            "has_details": number in details}})
                counts[answer_state] += 1
        if subject == "申论":
            anchor_numbers = {n for n, _ in blocks}
            unanchored = declared_missing - anchor_numbers
            if unanchored:
                results.append({"path": path, "question": None,
                                "type": "metadata_missing_number_without_anchor",
                                "details": {"numbers": sorted(unanchored)}})
                counts["metadata_missing_number_without_anchor"] += len(unanchored)
    summary = dict(sorted(counts.items()))
    summary["inventory_papers"] = len(inventory)
    summary["finding_rows"] = len(results)
    return results, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, help="optional JSONL output (never inside a paper)")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    results, summary = scan(args.root)
    print("GAP_AUDIT_SUMMARY " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    for item in results[:args.limit]:
        print("GAP_AUDIT_FINDING " + json.dumps(item, ensure_ascii=False, sort_keys=True))
    # Complete grouped index for review without flooding the Actions log.
    by_type = {}
    for item in results:
        group = by_type.setdefault(item["type"], {})
        group.setdefault(item["path"], []).append(item["question"])
    for kind, group in sorted(by_type.items()):
        print("GAP_AUDIT_GROUP " + json.dumps(
            {"type": kind, "papers": group}, ensure_ascii=False, sort_keys=True))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in results),
            encoding="utf-8",
        )
    if summary["paper_files"] != summary["inventory_papers"]:
        raise SystemExit("Inventory/file count mismatch")


if __name__ == "__main__":
    main()
