#!/usr/bin/env python3
"""Pre-flight vetting of a candidate source against a paper's declared gap list.

This answers a question the reconciler does not: **does a candidate source even
contain the missing questions?** `handoff_reconcile.py` compares two texts
dimension by dimension; this runs upstream of that, because a source can list a
question number while holding only a collection stub, or hold nothing at all.
Vetting first stops a stub or a partial edition from ever reaching a comparison.

The gap list is read from the paper's own front matter (`缺失原题号`) — never
hardcoded — so it follows the manifest as the manifest changes.

Sources are classified per number as:

    content   real text present for that question
    stub      only a collection placeholder ("题目正在全力以赴征集…")
    absent    the number does not appear in the candidate at all
    (nothing) no candidate source was supplied

A number counts as recovered only when it is `content`. Stub and absent are both
"not available", and a source that is stub-only is reported as such rather than
as a partial recovery.

Nothing is written back into the repository. No question text is emitted.

Usage:
    python3 tools/fenbi/audit/source_candidate_vet.py --repo . \
        --paper 省考/江苏/2026/行测-A类.md [--source FILE] [--source-format text|html]
"""

import argparse
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    default_repo_root, detect_placeholders, looks_like_placeholder_stub,
    parse_frontmatter, parse_int_list, parse_paper, read_text,
)

# Coarse question-type classifier used only to say what a GAP probably contains,
# inferred from its neighbours. Runs on the library's own text; emits a label,
# never the text itself.
TYPE_PATTERNS = (
    ("逻辑填空", r"填入|横线"),
    ("语句表达", r"重新排列|语序|句子排序"),
    ("片段阅读", r"这段文字|主旨|意在|标题|概括|文意"),
    ("定义判断", r"属于|不属于"),
    ("类比推理", r"∶"),
    ("图形推理", r"问号处|呈现一定的规律"),
    ("数量关系", r"多少|倍|千米|小时"),
    ("资料分析", r"同比|比重|增长率"),
)

# Identity tokens a genuine candidate for this paper must carry.
IDENTITY_TOKENS = ("2026", "江苏", "行测")


def classify_question(question):
    if not question:
        return None
    stem = question.get("stem", "")
    for name, pattern in TYPE_PATTERNS:
        if re.search(pattern, stem):
            return name
    return "other"


def gap_runs(numbers):
    """Group the declared numbers into consecutive runs."""
    if not numbers:
        return []
    runs, current = [], [numbers[0]]
    for n in numbers[1:]:
        if n == current[-1] + 1:
            current.append(n)
        else:
            runs.append(current)
            current = [n]
    runs.append(current)
    return runs


def html_to_text(raw):
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
    raw = html.unescape(raw)
    return raw


def split_source_questions(text):
    """Best-effort split of a candidate source into number -> body.

    Several numbering conventions occur in practice; accept a number that opens
    a line and is followed by punctuation or whitespace. This is intentionally
    permissive: the goal is to find the number, then judge what follows.
    """
    lines = text.splitlines()
    starts = []
    for index, line in enumerate(lines):
        m = re.match(r"^\s*(\d{1,3})\s*[.．、]\s*", line)
        if m:
            starts.append((int(m.group(1)), index))
    bodies = {}
    for pos, (number, index) in enumerate(starts):
        stop = starts[pos + 1][1] if pos + 1 < len(starts) else len(lines)
        body = "\n".join(lines[index + 1:stop]).strip()
        # Keep the opening line's remainder too — some editions put the stem
        # on the same line as the number.
        head = re.sub(r"^\s*\d{1,3}\s*[.．、]\s*", "", lines[index])
        bodies.setdefault(number, (head + "\n" + body).strip())
    return bodies


def vet_number(number, body):
    """Classify one source slot."""
    if body is None:
        return {"state": "absent", "reason": "number-not-found-in-candidate"}
    if looks_like_placeholder_stub(body):
        return {"state": "stub",
                "reason": "collection-placeholder-only",
                "markers": detect_placeholders(body)}
    if len(re.findall(r"\s", body)) and len(body.strip()) < 12:
        return {"state": "absent", "reason": "too-short-to-be-a-stem"}
    return {"state": "content", "reason": "text-present"}


def nearest_context(number, questions, declared):
    """Nearest PRESENT question on each side, skipping over other gaps.

    Inside a run of consecutive gaps the immediate neighbours are gaps too, so
    looking only one step out would report nothing. Walking outward to the
    nearest surviving question gives a usable hint about what the gap held.
    """
    lower = upper = None
    for candidate in range(number - 1, 0, -1):
        if candidate in questions:
            lower = classify_question(questions[candidate])
            break
    highest = max([number] + [n for n in questions if n > number] + [number])
    for candidate in range(number + 1, highest + 1):
        if candidate in questions:
            upper = classify_question(questions[candidate])
            break
    return {"previous_type": lower, "next_type": upper}


def build(repo, paper_rel, source_path=None, source_format="text"):
    frontmatter, body = parse_frontmatter(read_text(os.path.join(repo, paper_rel)))
    parsed = parse_paper(body)
    questions = parsed["questions"]

    declared = sorted(parse_int_list(frontmatter.get("缺失原题号", "")))
    declared_total = parse_int_list(frontmatter.get("对照题本题量", ""))

    source_text = None
    if source_path:
        raw = read_text(source_path)
        source_text = html_to_text(raw) if source_format == "html" else raw
    source_questions = split_source_questions(source_text) if source_text else {}

    items = []
    for number in declared:
        context = nearest_context(number, questions, declared)
        prev_type, next_type = context["previous_type"], context["next_type"]
        entry = {
            "number": number,
            "library_state": ("present" if number in questions else "absent-gap-preserved"),
            "neighbour_context": context,
            "expected_type": next_type if next_type not in (None, "other") else prev_type,
            "source": (vet_number(number, source_questions.get(number))
                       if source_text is not None
                       else {"state": "not-supplied", "reason": "no-candidate-source-given"}),
        }
        items.append(entry)

    identity = {}
    if source_text is not None:
        for token in IDENTITY_TOKENS:
            identity[token] = token in source_text
    else:
        for token in IDENTITY_TOKENS:
            identity[token] = None

    states = [i["source"]["state"] for i in items]
    content = states.count("content")
    stubs = states.count("stub")
    if source_text is None:
        verdict = "blocked-no-source-supplied"
    elif declared and content == len(declared):
        verdict = "candidate-covers-all-gaps"
    elif content:
        verdict = "candidate-covers-some-gaps"
    elif stubs:
        verdict = "no-recoverable-content-stub-present"
    else:
        verdict = "candidate-lacks-the-gaps"

    return {
        "audit": "js2026a-source-candidate-vet",
        "paper": {
            "path": paper_rel,
            "declared_missing_count": len(declared),
            "declared_total_questions": declared_total[0] if declared_total else None,
            "library_question_count": len(questions),
            "library_sha256": __import__("hashlib").sha256(
                read_text(os.path.join(repo, paper_rel)).encode("utf-8")).hexdigest(),
            "provenance_nature": frontmatter.get("真题性质"),
            "declared_missing": declared,
            "gap_runs": [{"from": r[0], "to": r[-1], "count": len(r)}
                         for r in gap_runs(declared)],
        },
        "candidate": {
            "supplied": source_text is not None,
            "path": os.path.basename(source_path) if source_path else None,
            "format": source_format if source_path else None,
            "numbers_found": len(source_questions),
            "identity_tokens": identity,
            "identity_ok": (all(identity.values()) if source_text is not None else None),
        },
        "items": items,
        "summary": {
            "declared_missing": len(declared),
            "source_content": content,
            "source_stub": stubs,
            "source_absent": states.count("absent"),
            "source_not_supplied": states.count("not-supplied"),
            "verdict": verdict,
        },
        "policy": [
            "A number counts as recovered only when the source holds text for it.",
            "A collection stub is not content and is never counted as partial recovery.",
            "The gap list is read from the paper's front matter, not hardcoded.",
            "No question text is emitted by this tool.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--paper", required=True, help="paper path relative to the repo root")
    ap.add_argument("--source", default=None,
                    help="candidate source file (any local copy you are permitted to read)")
    ap.add_argument("--source-format", choices=("text", "html"), default="text")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    doc = build(args.repo, args.paper, args.source, args.source_format)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    print(json.dumps(doc["summary"], ensure_ascii=False))
    print("gap runs:", doc["paper"]["gap_runs"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
