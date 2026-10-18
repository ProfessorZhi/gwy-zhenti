#!/usr/bin/env python3
"""Recompute the answer-source index numbers from its own JSONL.

Metadata-only arithmetic. It reads `quality-index.jsonl` (one row per paper) and
`summary.json`, recomputes every headline figure, and compares against both the
machine summary and the numbers stated in the narrative. No question text, no
options, no image bytes.

Checks
  papers-total            : rows == summary.papers == stated 1169
  answer-blocks           : sum(answer_blocks) == summary.answerBlocks == stated 56047
  verified-blocks         : sum(provenance_verified) == summary.verified == stated
  zero-verified-papers    : papers with provenance_verified == 0
  generic-only-papers     : zero-verified papers that nevertheless have answers
  fully-verified-papers   : papers whose every block is verified
  priority-closure        : P0+P1+P2+P3 == papers
  priority-matches-tickets: P0+P1+P2 == ticket rows
  self-reference-excluded : no paper is "verified" only because it cites this repo

`--stated` accepts a JSON object with the numbers a report claims, so narrative
and artifact are checked against each other rather than either being trusted.

Usage:
  python3 -I verify_answer_source_index.py --index quality-index.jsonl \
      --summary summary.json [--tickets priority-tickets.jsonl] \
      [--stated claims.json] [--out ledger.json]
Exit 0 = ran; 2 = unreadable input.
"""
import argparse
import json
import sys

SELF_REPO_MARKERS = ("github.com/ProfessorZhi/gwy-zhenti",)


def read_jsonl(path):
    with open(path, encoding="utf8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--tickets")
    ap.add_argument("--stated")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        rows = read_jsonl(a.index)
        summary = json.load(open(a.summary, encoding="utf8"))
    except Exception as e:
        print(f"cannot read inputs: {e}", file=sys.stderr)
        return 2
    tickets = read_jsonl(a.tickets) if a.tickets else []
    stated = json.load(open(a.stated, encoding="utf8")) if a.stated else {}

    papers = len(rows)
    blocks = sum(r.get("answer_blocks", 0) for r in rows)
    verified = sum(r.get("provenance_verified", 0) for r in rows)
    present = sum(r.get("provenance_source_present", 0) for r in rows)
    unsupported = sum(r.get("provenance_unsupported", 0) for r in rows)
    zero = [r for r in rows if r.get("provenance_verified", 0) == 0]
    generic = [r for r in zero if r.get("answer_blocks", 0) > 0]
    full = [r for r in rows if r.get("answer_blocks", 0) > 0
            and r.get("provenance_verified", 0) == r.get("answer_blocks", 0)]
    prio = {}
    for r in rows:
        prio[r.get("priority")] = prio.get(r.get("priority"), 0) + 1
    self_cited = [r for r in rows
                  if any(m in str(r.get("declared_sources") or "").lower()
                         for m in SELF_REPO_MARKERS)]

    checks = []

    def add(name, verdict, detail, evidence=None):
        checks.append({"check": name, "verdict": verdict, "detail": detail,
                       "evidence": evidence or {}})

    def cmp(name, computed, machine, claim):
        ok_machine = machine is None or computed == machine
        ok_claim = claim is None or computed == claim
        verdict = "PASS" if ok_machine and ok_claim else "FAIL"
        detail = f"computed {computed}; summary.json {machine}; stated {claim}"
        add(name, verdict, detail,
            {"computed": computed, "summary": machine, "stated": claim})

    prov = summary.get("provenance", {})
    cmp("papers-total", papers, summary.get("papers"), stated.get("papers"))
    cmp("answer-blocks", blocks, prov.get("answerBlocks"), stated.get("answerBlocks"))
    cmp("verified-blocks", verified, prov.get("verified"), stated.get("verified"))
    cmp("zero-verified-papers", len(zero), None, stated.get("papersWithNoVerifiedBlock"))
    cmp("generic-only-papers", len(generic), prov.get("papersGenericOnly"),
        stated.get("papersGenericOnly"))
    cmp("fully-verified-papers", len(full), prov.get("papersFullyVerified"),
        stated.get("papersFullyVerified"))

    prio_sum = sum(prio.values())
    add("priority-closure", "PASS" if prio_sum == papers else "FAIL",
        f"P0+P1+P2+P3 = {prio_sum} vs papers {papers}",
        {"distribution": prio})
    if tickets:
        p012 = sum(v for k, v in prio.items() if k in ("P0", "P1", "P2"))
        add("priority-matches-tickets", "PASS" if p012 == len(tickets) else "FAIL",
            f"P0+P1+P2 = {p012} vs ticket rows {len(tickets)}")
    add("self-reference-excluded", "PASS" if not self_cited else "FAIL",
        f"{len(self_cited)} paper(s) declare this repository as their own source",
        {"paths": [r.get("path") for r in self_cited][:5]})

    # A narrative figure that matches neither artifact is the dangerous case.
    if stated.get("verified") is not None and stated["verified"] != verified:
        add("narrative-vs-artifact", "FAIL",
            f"narrative states {stated['verified']} verified blocks; artifact contains "
            f"{verified} (difference {verified - stated['verified']})",
            {"artifact": verified, "narrative": stated["verified"],
             "summaryJson": prov.get("verified")})

    doc = {
        "schemaVersion": 1,
        "kind": "no-content-answer-source-index-verification",
        "contentPolicy": "counts only; no question text, options, image bytes or credentials",
        "recomputed": {"papers": papers, "answerBlocks": blocks, "verified": verified,
                       "sourcePresent": present, "unsupported": unsupported,
                       "zeroVerifiedPapers": len(zero),
                       "genericOnlyPapers": len(generic),
                       "fullyVerifiedPapers": len(full),
                       "priority": prio},
        "checks": checks,
    }
    out = json.dumps(doc, ensure_ascii=False, indent=1)
    (open(a.out, "w").write(out) if a.out else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
