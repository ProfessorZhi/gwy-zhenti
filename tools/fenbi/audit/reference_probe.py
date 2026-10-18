#!/usr/bin/env python3
"""Probe a locally held reference document at the declared missing numbers.

Answers one question per number: does the source of record itself carry real
question text there, or a collection placeholder? That is what separates a
genuine library gap from a recoverable one.

This script never downloads anything. Point it at a file you have already
obtained (an HTML export, or the text layer of a PDF produced by
`pdftotext -layout file.pdf out.txt`). Only marker names and counts are
emitted, never the source's question text.

Usage:
    python3 tools/fenbi/audit/reference_probe.py --file REF --numbers 49,50 [--format text|html]
"""

import argparse
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import PLACEHOLDER_MARKERS  # noqa: E402


def html_to_lines(raw):
    """Strip an HTML export down to text lines (no external parser needed)."""
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t　]+", " ", raw)
    return [l.strip() for l in raw.splitlines() if l.strip()]


def probe(text, numbers, window=700):
    """Classify each number's slot in the reference text.

    Two heading shapes occur across these exports: a bare number on its own line
    (HTML exports) and a number opening a line followed by punctuation
    ("49、网友未回忆起…", PDF text layers). Both are accepted; a match only counts
    as a placeholder when a placeholder marker occurs in the surrounding window.
    """
    results = []
    for n in numbers:
        occurrences = list(re.finditer(r"(?m)^\s*%d\s*(?:[\.、]|$)" % n, text))
        markers = {}
        for m in occurrences:
            chunk = text[max(0, m.start() - 150): m.start() + window]
            for name, pattern in PLACEHOLDER_MARKERS.items():
                if re.search(pattern, chunk, re.M):
                    markers[name] = markers.get(name, 0) + 1
        if not occurrences:
            verdict = "NUMBER_ABSENT_FROM_SOURCE"
        elif markers:
            verdict = "PLACEHOLDER_AT_SOURCE"
        else:
            verdict = "TEXT_PRESENT_AT_SOURCE"
        results.append({
            "number": n,
            "number_line_occurrences": len(occurrences),
            "placeholder_marker_counts": markers,
            "verdict": verdict,
        })
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="path to the locally held reference")
    ap.add_argument("--label", default=None, help="human label for the source")
    ap.add_argument("--numbers", required=True,
                    help="comma-separated question numbers, e.g. 49,50")
    ap.add_argument("--format", choices=("text", "html"), default="text")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    numbers = [int(x) for x in args.numbers.split(",") if x.strip()]
    raw = open(args.file, encoding="utf-8", errors="replace").read()
    text = "\n".join(html_to_lines(raw)) if args.format == "html" else raw

    doc = {
        "audit": "missing25-reference-probe",
        "label": args.label or args.file,
        "source_file": args.file,
        "source_format": args.format,
        "note": "Marker names and counts only; the source's question text is not reproduced.",
        "items": probe(text, numbers),
    }
    doc["summary"] = {
        "numbers_checked": len(numbers),
        "placeholder_at_source": sum(
            1 for i in doc["items"] if i["verdict"] == "PLACEHOLDER_AT_SOURCE"),
        "text_present_at_source": sum(
            1 for i in doc["items"] if i["verdict"] == "TEXT_PRESENT_AT_SOURCE"),
        "number_absent_from_source": sum(
            1 for i in doc["items"] if i["verdict"] == "NUMBER_ABSENT_FROM_SOURCE"),
    }

    out = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
