#!/usr/bin/env python3
"""Reconcile a captured source document against the library, per dimension.

This is the docking point for evidence produced elsewhere (the browser owner's
captures). It compares seven dimensions — number / stem / options / materials /
images / answer / explanation — using the same four states and reason strings as
tools/fenbi/src/align.mjs, so its output can be read next to a capture-time
alignment.json.

Two things it is careful about:

1. **The join.** This library preserves original-paper numbering and leaves the
   missing numbers out, so a paper can hold 93 questions numbered up to 100. A
   direct number join is therefore wrong after the first gap. `--join` chooses
   `number` or `sequence` (positional); `auto` picks `sequence` whenever the
   library has gaps and says so in the output.

2. **Answers.** A source that does not publish answers yields `unknown`, never a
   value borrowed from the library or from a sibling paper. Nothing is written
   back into the repository: this script only reports.

Accepted input shapes:
  * `fenbi-candidate-handoff-v1` — the reduced, metadata-only projection:
      {paper: {...}, questions: [{source_number, qid, stem, options, material_ids,
                                  images: [sha256...], answer, explanation}]}
  * a framework `document.json` (identity/source/questions/assets), adapted on
    the fly.

Usage:
    python3 tools/fenbi/audit/handoff_reconcile.py --repo . --handoff FILE
                                                    [--join auto|number|sequence]
                                                    [--out FILE]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    compare_images, compare_options, compare_text, default_repo_root,
    parse_frontmatter, parse_paper, read_text, resolve_image_ref, image_refs,
)

DIMENSIONS = ("number", "stem", "options", "materials", "images", "answer", "explanation")


def adapt_handoff(raw):
    """Normalise either accepted input shape into the reduced projection."""
    if raw.get("schema") == "fenbi-candidate-handoff-v1":
        return raw

    identity = raw.get("identity") or {}
    source = raw.get("source") or {}
    assets = {a.get("localPath"): a for a in raw.get("assets", [])}
    questions = []
    for q in raw.get("questions", []):
        images = []
        for ref in _image_srcs([q.get("contentHtml", "")] +
                               [o.get("contentHtml", "") for o in q.get("options", [])]):
            asset = assets.get(ref) or assets.get(os.path.basename(ref or ""))
            images.append((asset or {}).get("sha256"))
        questions.append({
            "source_number": q.get("number"),
            "qid": q.get("id") or "",
            "stem": q.get("contentHtml", ""),
            "options": [{"label": o.get("label"), "text": o.get("contentHtml", "")}
                        for o in q.get("options", [])],
            "material_ids": q.get("materialIds") or [],
            "images": images,
            "answer": q.get("answerHtml") or None,
            "explanation": q.get("explanationHtml") or None,
        })
    return {
        "schema": "fenbi-candidate-handoff-v1",
        "adapted_from": "framework-document-json",
        "paper": {
            "label": identity.get("title") or "",
            "fenbi_source_id": identity.get("id"),
            "captured_at": source.get("capturedAt"),
            "binding": "unverified",
        },
        "questions": questions,
    }


def _image_srcs(chunks):
    out = []
    for chunk in chunks:
        out.extend(ref["src"] for ref in image_refs(chunk or ""))
    return out


def library_question_view(repo, paper_rel, number, parsed):
    """The library side of a comparison for one number."""
    question = parsed["questions"].get(number)
    if question is None:
        return None
    refs = image_refs(question["stem"]) + [r for o in question["options"]
                                           for r in image_refs(o["text"])]
    resolved = [resolve_image_ref(repo, paper_rel, r["src"]) for r in refs]
    return {
        "qid": question["qid"],
        "stem": question["stem"],
        "options": question["options"],
        "material_ids": question["material_ids"],
        "image_digests": [r.get("sha256") for r in resolved],
        "answer": question.get("answer", ""),
        "explanation": question.get("explanation", ""),
    }


def evaluate_joins(library_numbers, source_numbers):
    """Score both join strategies against the actual numbers on both sides.

    Returns (scores, best). `number` pairs equal numbers; `sequence` pairs by
    position. The two disagree exactly when the library preserves original
    numbering with gaps and the source does not — and it is the *positional*
    join that misaligns there, not the number join.
    """
    ordered = sorted(library_numbers)
    library_set = set(library_numbers)
    number_hits = sum(1 for s in source_numbers if s in library_set)
    sequence_hits = sum(1 for i, s in enumerate(source_numbers)
                        if i < len(ordered) and ordered[i] == s)
    scores = {
        "number": {"hits": number_hits, "of": len(source_numbers)},
        "sequence": {"hits": sequence_hits, "of": len(source_numbers)},
    }
    best = "number" if number_hits >= sequence_hits else "sequence"
    return scores, best


def join_warning(library_numbers, source_numbers, scores, chosen):
    """Flag the gap hazard whenever the library preserves gaps.

    Score alone cannot tell "the source numbers some questions the same way"
    from "the source is contiguous and the numbers merely coincide": a
    contiguous 1..93 source against this 93/100 library scores 86 for a number
    join, of which the last 18 are wrong. So whenever the library has gaps we
    say so and show both scores, rather than letting the operator trust a
    silent choice.
    """
    ordered = sorted(library_numbers)
    if not ordered or ordered[-1] == len(ordered):
        return None
    gap_numbers = [n for n in range(1, ordered[-1] + 1) if n not in set(ordered)]
    shifted_example = None
    for index, source_number in enumerate(source_numbers):
        if index < len(ordered) and ordered[index] != source_number:
            shifted_example = {"source_number": source_number,
                               "positional_join_would_use_library_number": ordered[index]}
            break
    return {
        "reason": "library-preserves-original-numbering-with-gaps",
        "library_gap_numbers": gap_numbers[:20],
        "chosen": chosen,
        "candidate_scores": scores,
        "hazard": ("a positional join would pair source questions with the wrong "
                   "library questions after the first gap"),
        "example": shifted_example,
        "action": ("confirm the source's numbering convention (gap-preserving vs "
                   "contiguous) before trusting either join"),
    }


def choose_join(strategy, library_numbers, source_numbers):
    """Resolve the join strategy, returning (strategy, reason, scores).

    `auto` picks whichever strategy actually lines up more questions, rather
    than assuming a gap-preserving library implies a contiguous source. The
    earlier heuristic did the latter and would have mapped 广东2020 source
    question 69 onto library question 76 — the misalignment this guard exists
    to prevent.
    """
    scores, best = evaluate_joins(library_numbers, source_numbers)
    if strategy in ("number", "sequence"):
        return strategy, "requested explicitly", scores
    if best == "number":
        reason = (f"number join lines up {scores['number']['hits']} of "
                  f"{scores['number']['of']} source questions vs "
                  f"{scores['sequence']['hits']} positionally")
    else:
        reason = (f"positional join lines up {scores['sequence']['hits']} of "
                  f"{scores['sequence']['of']} source questions vs "
                  f"{scores['number']['hits']} by number")
    return best, reason, scores


def reconcile_item(source, library, join_basis):
    """Per-dimension comparison for one matched pair."""
    dims = {}
    dims["number"] = {
        "status": "same" if join_basis == "same" else "not_compared",
        "reason": ("number-join" if join_basis == "same"
                   else "positional-join-library-preserves-gaps"),
        "library_number": library.get("library_number"),
        "source_number": source.get("source_number"),
    }
    dims["stem"] = compare_text(source.get("stem", ""), library["stem"])
    dims["options"] = compare_options(source.get("options") or [], library["options"])

    source_materials = source.get("material_ids") or []
    library_materials = library["material_ids"]
    if not source_materials and not library_materials:
        dims["materials"] = {"status": "not_compared", "reason": "no-shared-material",
                             "sourceCount": 0, "repositoryCount": 0}
    elif sorted(source_materials) != sorted(library_materials):
        dims["materials"] = {"status": "different",
                             "reason": "shared-material-linkage-differs",
                             "sourceCount": len(source_materials),
                             "repositoryCount": len(library_materials)}
    else:
        dims["materials"] = {"status": "same", "reason": "shared-material-linkage-equal",
                             "sourceCount": len(source_materials),
                             "repositoryCount": len(library_materials)}

    dims["images"] = compare_images(source.get("images") or [],
                                    library["image_digests"])

    # Answers and explanations are only compared when the source actually
    # publishes them. Absence is `unknown`, never borrowed.
    for field in ("answer", "explanation"):
        value = source.get(field)
        if value is None or str(value).strip() == "":
            dims[field] = {
                "status": "unknown",
                "reason": f"source-{field}-not-published",
                "note": "not inferred from the library or from any sibling paper",
            }
        else:
            dims[field] = compare_text(value, library.get(field, ""))
    return dims


def build(repo, handoff, strategy, library_path=None):
    paper = handoff.get("paper") or {}
    # A framework document.json carries no library path; the caller supplies it.
    paper_rel = library_path or paper.get("library_path")
    if not paper_rel:
        raise SystemExit(
            "no library path: pass --paper PATH, or set handoff.paper.library_path")
    frontmatter, body = parse_frontmatter(read_text(os.path.join(repo, paper_rel)))
    parsed = parse_paper(body)
    library_numbers = sorted(parsed["questions"])

    source_numbers = [q.get("source_number") for q in handoff["questions"]]
    join, join_reason, join_scores = choose_join(
        strategy, library_numbers, source_numbers)
    ordered = list(library_numbers)

    items, unmapped_source, unmapped_library = [], [], []
    used_library = set()
    for index, source in enumerate(handoff["questions"]):
        if join == "number":
            library_number = source.get("source_number")
            if library_number not in parsed["questions"]:
                unmapped_source.append({"index": index,
                                        "source_number": source.get("source_number"),
                                        "reason": "no-library-question-with-this-number"})
                continue
            basis = "same"
        else:
            if index >= len(ordered):
                unmapped_source.append({"index": index,
                                        "source_number": source.get("source_number"),
                                        "reason": "beyond-library-question-count"})
                continue
            library_number = ordered[index]
            basis = ("same" if library_number == source.get("source_number")
                     else "shifted")

        view = library_question_view(repo, paper_rel, library_number, parsed)
        view["library_number"] = library_number
        used_library.add(library_number)
        qid_note = None
        if source.get("qid") and view["qid"] and source["qid"] != view["qid"]:
            qid_note = {"status": "not_compared",
                        "reason": "qid-namespaces-are-incompatible-by-design",
                        "source": source["qid"], "library": view["qid"]}
        items.append({
            "library_number": library_number,
            "source_number": source.get("source_number"),
            "join_basis": basis,
            "dimensions": reconcile_item(source, view, basis),
            "qid": qid_note or {"status": "not_compared",
                                "reason": "qid-namespaces-are-incompatible-by-design"},
        })

    for number in ordered:
        if number not in used_library:
            unmapped_library.append(number)

    tally = {}
    for dim in DIMENSIONS:
        counts = {"same": 0, "different": 0, "unknown": 0, "not_compared": 0}
        for item in items:
            counts[item["dimensions"][dim]["status"]] += 1
        tally[dim] = counts

    return {
        "audit": "three-paper-handoff-reconcile",
        "handoff_schema": handoff.get("schema"),
        "adapted_from": handoff.get("adapted_from"),
        "paper": {
            "label": paper.get("label"),
            "library_path": paper_rel,
            "fenbi_source_id": paper.get("fenbi_source_id"),
            "captured_at": paper.get("captured_at"),
            "paper_binding": paper.get("binding", "unverified"),
            "library_file_declared_missing": frontmatter.get("缺失原题号"),
            "library_question_count": len(library_numbers),
            "source_question_count": len(handoff["questions"]),
        },
        "join": {"strategy": join, "reason": join_reason,
                 "candidate_scores": join_scores,
                 "warning": join_warning(library_numbers, source_numbers,
                                         join_scores, join),
                 "unmapped_source_items": unmapped_source,
                 "library_numbers_not_covered": unmapped_library},
        "dimension_tally": tally,
        "items": items,
        "boundary": [
            "Reports only; nothing is written back into the repository.",
            "Missing source answers/explanations stay unknown; they are never "
            "inferred from the library or from a sibling paper.",
            "Paper identity is reported as unverified unless the capture proves it.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--handoff", required=True,
                    help="captured source document (handoff projection or document.json)")
    ap.add_argument("--paper", default=None,
                    help="library paper path to reconcile against; required when the "
                         "handoff does not carry handoff.paper.library_path")
    ap.add_argument("--join", choices=("auto", "number", "sequence"), default="auto")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    raw = json.loads(read_text(args.handoff))
    handoff = adapt_handoff(raw)
    doc = build(args.repo, handoff, args.join, library_path=args.paper)

    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)

    print(f"join={doc['join']['strategy']} ({doc['join']['reason']})")
    print(f"matched items: {len(doc['items'])}")
    for dim, counts in doc["dimension_tally"].items():
        print(f"  {dim:12} same={counts['same']:<4} different={counts['different']:<4} "
              f"unknown={counts['unknown']:<4} not_compared={counts['not_compared']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
