#!/usr/bin/env python3
"""Per-question offline validator for gwy-zhenti papers.

Runs with no network, no browser, no account. It answers, for every question:

  * is the original number present, unique and inside the declared range?
  * does the file's declared identity (region / year / variant) match the expectation?
  * is the stem real text, or an image with a resolvable file and a computed sha256?
  * do options A-D each actually carry content (text, or an image with a hash)?
  * does every <img> resolve to a real file with a hash?
  * is the question a fenbi "not yet collected" stub or otherwise empty?
  * are answers / explanations observable? (usually not -> unknown)

It NEVER prints question or option text. Output is counts, lengths, numbers,
hashes and booleans only.

Vocabulary is deliberately narrow, so nothing gets overclaimed:

  structurally_valid : every local structural check passed. This says NOTHING
                       about whether the content is the official paper.
  invalid            : a hard structural check failed (see reasons).
  unknown            : a check could not be evaluated (e.g. no capture handoff).

`capture_verified` is tracked separately and is `unknown` unless an authorized
no-credential handoff covering that paper is supplied.

Usage:
  python3 -I paper_question_validator.py --repo . [--handoff <handoff>] \
      [--paper <key> ...] [--focus <number>] [--out ledger.json]
"""
import argparse
import collections
import json
import os
import re
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visual_consistency_audit as V  # noqa: E402
import visual_representation_audit as R  # noqa: E402

HDR = re.compile(r'^#{2,3}\s*(第\s*(\d+)\s*题|材料\s*(\d+)(?:（第\s*(\d+)\s*[—–-]\s*(\d+)\s*题共用）)?)', re.M)
FM = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S | re.M)
ANSWERS = re.compile(r'^##\s*答案与解析', re.M)

PLACEHOLDER_OPTS = {"缺失", "暂缺"}
PLACEHOLDER_STEM_MARKERS = ("征集", "上传")

# paper registry: key -> (path, expected region/year/variant, handoff key or None)
PAPERS = {
    "js-2025-c": ("省考/江苏/2025/行测-C类.md", ("江苏", "2025", "C类"), "js-2025-xingce-c-4189916"),
    "js-2024-a": ("省考/江苏/2024/行测-A类.md", ("江苏", "2024", "A类"), "js-2024-xingce-a-4162243"),
    "gd-2020-county": ("省考/广东/2020/行测-县级卷.md", ("广东", "2020", "县级卷"), "gd-2020-xingce-county-96785"),
    "zj-2026-c": ("省考/浙江/2026/行测-C类.md", ("浙江", "2026", "C类"), "zj-2026-xingce-c-8399763"),
    "gk-2026-fushengji": ("国考/2026/行测-副省级.md", ("国考", "2026", "副省级"), None),
    "gk-2026-dishiji": ("国考/2026/行测-地市级.md", ("国考", "2026", "地市级"), None),
}


# ------------------------------------------------------------------ parsing
def frontmatter(text):
    m = FM.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        mm = re.match(r'^\s*([^:#]+):\s*(.*)$', line)
        if mm:
            out[mm.group(1).strip()] = mm.group(2).strip().strip('"')
    return out


def split_doc(path):
    text = open(path, encoding="utf8").read()
    fm = frontmatter(text)
    cut = ANSWERS.search(text)
    body = text[:cut.start()] if cut else text
    marks = [(m.start(), m.group(2), m.group(3), m.group(4), m.group(5))
             for m in HDR.finditer(body)]
    return text, fm, body, marks, bool(cut)


def blocks_of(body, marks):
    q, mat = {}, {}
    for i, (off, qn, mn, lo, hi) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        if qn:
            q[int(qn)] = body[off:end]
        else:
            mat[int(mn)] = {"block": body[off:end],
                            "range": (int(lo), int(hi)) if lo else None}
    return q, mat


def split_options(block):
    # drop the "## 第 N 题 <sub>qid ...</sub>" heading line first, otherwise the
    # heading is counted as stem text and every stemChars figure is inflated.
    block = re.sub(r"^#{2,3}[^\n]*\n", "", block)
    opts = [(m.group(1), m.group(2).strip()) for m in R.OPT.finditer(block)]
    first = R.OPT.search(block)
    stem = block[:first.start()] if first else block
    return stem, opts


def images_in(text):
    out = []
    for m in V.IMG.finditer(text):
        s = V.SRC.search(m.group(1))
        if s:
            out.append(s.group(1))
    return out


def resolve(repo, mdrel, src):
    p = os.path.normpath(os.path.join(repo, os.path.dirname(mdrel), src))
    if os.path.isfile(p):
        return p
    return None


def image_facts(repo, mdrel, src):
    p = resolve(repo, mdrel, src)
    if not p:
        return {"basename": os.path.basename(src), "resolved": False}
    try:
        with Image.open(p) as im:
            im.load()
            w, h = im.width, im.height
        return {"basename": os.path.basename(src), "resolved": True,
                "sha256": V.sha256_file(p), "w": w, "h": h,
                "bytes": os.path.getsize(p)}
    except Exception as e:
        return {"basename": os.path.basename(src), "resolved": True,
                "decodeError": type(e).__name__}


def is_placeholder(stem_text, option_texts):
    if option_texts and all(t in PLACEHOLDER_OPTS for t in option_texts):
        return True
    return all(m in (stem_text or "") for m in PLACEHOLDER_STEM_MARKERS)


def has_content(text, imgs):
    """An option/stem carries content if it has non-space text (that is not just
    its label) OR at least one image."""
    t = (text or "").strip()
    if imgs:
        return True
    return bool(t) and not re.fullmatch(r'[A-D]', t)


# ------------------------------------------------------------------ validate
def validate_paper(repo, handoff, key, focus=None):
    mdrel, expect, hkey = PAPERS[key]
    path = os.path.join(repo, mdrel)
    if not os.path.isfile(path):
        return {"paper": key, "status": "missing-markdown", "path": mdrel}
    text, fm, body, marks, has_answers = split_doc(path)
    qblocks, mats = blocks_of(body, marks)
    handoff_canon = None
    if handoff and hkey:
        hp = os.path.join(handoff, "papers", hkey, "canonical.json")
        if os.path.isfile(hp):
            handoff_canon = json.load(open(hp, encoding="utf8"))
    hq = ({q["sourceNumber"]: q for q in handoff_canon["questions"]}
          if handoff_canon else {})

    declared = int(fm.get("实有题数") or len(qblocks))
    declared_missing = fm.get("缺失原题号") or ""
    try:
        declared_missing = json.loads(declared_missing) if declared_missing else []
    except Exception:
        declared_missing = []

    region_ok = (fm.get("地区") == expect[0] and fm.get("年份") == expect[1]
                 and fm.get("卷型") == expect[2])

    # read the raw header numbers, not the dict keys: a dict collapses
    # duplicates, so duplicate detection has to happen before that.
    raw_numbers = [int(m[1]) for m in marks if m[1]]
    numbers = sorted(qblocks)
    in_range = [n for n in numbers if 1 <= n <= declared]
    gaps = sorted(set(range(1, declared + 1)) - set(numbers))
    dups = sorted(n for n, c in collections.Counter(raw_numbers).items() if c > 1)

    rows = []
    for n in numbers:
        blk = qblocks[n]
        stem, opts = split_options(blk)
        stem_text = R.TAG.sub("", V.IMG.sub("", stem)).strip()
        stem_imgs = images_in(stem)
        stem_facts = [image_facts(repo, mdrel, s) for s in stem_imgs]
        opt_texts = [(l, t) for l, t in opts]
        opt_plain = [R.TAG.sub("", V.IMG.sub("", t)).strip() for _, t in opt_texts]
        opt_imgs = [images_in(t) for _, t in opt_texts]
        opt_facts = [[image_facts(repo, mdrel, s) for s in ims] for ims in opt_imgs]

        reasons = []
        if is_placeholder(stem_text, opt_plain):
            reasons.append("fenbi-placeholder-stub")
        if not has_content(stem_text, stem_imgs):
            reasons.append("empty-stem")
        labels = [l for l, _ in opt_texts]
        if labels != ["A", "B", "C", "D"]:
            reasons.append("options-not-abcd")
        label_only = bool(opt_plain) and all(
            (t == l) for (l, _), t in zip(opt_texts, opt_plain))
        incomplete = []
        for i, (l, t) in enumerate(opt_texts):
            if not has_content(opt_plain[i], opt_imgs[i]):
                if label_only:
                    # bounded, known case: the figures are fused into the stem
                    # composite; there is no per-option image object anywhere.
                    incomplete.append(f"option-{l}-label-only-no-figure-object")
                else:
                    reasons.append(f"option-{l}-empty")
        bad_imgs = [f["basename"] for grp in [stem_facts] + opt_facts
                    for f in grp if not f.get("resolved") or f.get("decodeError")]
        if bad_imgs:
            reasons.append("unresolved-or-undecodable-image")

        # capture side
        if hq:
            h = hq.get(n)
            if h is None:
                capture = {"status": "not-in-capture"}
                reasons.append("not-in-capture")
            else:
                ph = is_placeholder(h.get("stemText") or "",
                                    [(o.get("text") or "").strip()
                                     for o in h.get("options") or []])
                capture = {
                    "status": "captured",
                    "captureIsPlaceholder": ph,
                    "answerPresent": bool(h.get("answerPresent")),
                    "explanationPresent": bool(h.get("explanationPresent")),
                }
        else:
            capture = {"status": "no-authorized-handoff"}

        if reasons:
            verdict = "invalid"
        elif incomplete:
            verdict = "incomplete"
        else:
            verdict = "structurally_valid"
        rec = {
            "number": n,
            "verdict": verdict,
            "reasons": reasons,
            "incompleteReasons": incomplete,
            "stemChars": len(stem_text),
            "stemImages": len(stem_imgs),
            "stemImageSha": [f.get("sha256") for f in stem_facts if f.get("sha256")],
            "optionCount": len(opt_texts),
            "optionChars": [len(t) for t in opt_plain],
            "optionImages": [len(x) for x in opt_imgs],
            "optionImageSha": [[f.get("sha256") for f in grp if f.get("sha256")]
                               for grp in opt_facts],
            "optionLabelOnly": label_only,
            "capture": capture,
            "answer": "unknown",        # answers are not observable in the repo
            "explanation": "unknown",
        }
        rows.append(rec)

    material_imgs = []
    for mn, md in mats.items():
        for src in images_in(md["block"]):
            material_imgs.append(image_facts(repo, mdrel, src))

    summary = collections.Counter(r["verdict"] for r in rows)
    reason_counts = collections.Counter(x for r in rows for x in r["reasons"])
    doc = {
        "paper": key,
        "path": mdrel,
        "sourceId": (handoff_canon["identity"]["sourceId"] if handoff_canon else None),
        "sourceIdStatus": ("from-authorized-handoff" if handoff_canon
                           else "unknown-no-authorized-handoff"),
        "identity": {"declared": {k: fm.get(k) for k in ("考试", "地区", "年份", "科目", "卷型")},
                     "expected": list(expect),
                     "matches": region_ok},
        "questionCount": {"declared": declared, "parsed": len(numbers),
                          "inRange": len(in_range), "gaps": gaps,
                          "declaredMissing": declared_missing,
                          "gapsMatchDeclaredMissing": gaps == sorted(declared_missing),
                          "duplicates": dups},
        "answersSectionPresent": has_answers,
        "summary": {"questions": len(rows),
                    "structurallyValid": summary.get("structurally_valid", 0),
                    "incomplete": summary.get("incomplete", 0),
                    "invalid": summary.get("invalid", 0),
                    "reasonCounts": dict(reason_counts),
                    "incompleteReasonCounts": dict(collections.Counter(
                        x for r in rows for x in r["incompleteReasons"]))},
        "rows": rows,
    }
    # image aggregate
    all_sha = set()
    refs = 0
    for r in rows:
        refs += r["stemImages"] + sum(r["optionImages"])
        for s in r["stemImageSha"]:
            all_sha.add(s)
        for grp in r["optionImageSha"]:
            for s in grp:
                all_sha.add(s)
    mat_sha = {f["sha256"] for f in material_imgs if f.get("sha256")}
    doc["images"] = {
        "questionBlockRefs": refs,
        "questionBlockDistinctSha": len(all_sha),
        "materialRefs": len(material_imgs),
        "materialDistinctSha": len(mat_sha),
        "materialUnresolved": sum(1 for f in material_imgs if not f.get("resolved")),
        "totalDistinctSha": len(all_sha | mat_sha),
    }
    return doc



# ------------------------------------------------------------------ focus
def build_focus(doc, number):
    """Cross-source evidence matrix for one original number.

    Three columns, each with its own evidence tier:
      repo    : read from this repository, fully reproducible here
      capture : only when an authorized handoff covers the paper
      claims  : statements made in another PR; NOT independently verified here
    """
    matrix = {"originalNumber": number, "columns": {}}
    for k, v in doc["papers"].items():
        if v.get("status"):
            continue
        for r in v["rows"]:
            if r["number"] != number:
                continue
            matrix["columns"].setdefault(k, {
                "evidenceTier": "repo-read",
                "verdict": r["verdict"],
                "reasons": r["reasons"],
                "incompleteReasons": r["incompleteReasons"],
                "stemChars": r["stemChars"],
                "stemImages": r["stemImages"],
                "stemImageSha": r["stemImageSha"],
                "optionCount": r["optionCount"],
                "optionChars": r["optionChars"],
                "optionImages": r["optionImages"],
                "optionImageSha": r["optionImageSha"],
                "capture": r["capture"],
                "answer": r["answer"],
                "explanation": r["explanation"],
            })
    matrix["note"] = ("a row present under several papers is the SAME original number in "
                      "DIFFERENT papers; they must not be conflated")
    return matrix


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--handoff", default="")
    ap.add_argument("--paper", action="append", default=[])
    ap.add_argument("--focus", type=int, default=None)
    ap.add_argument("--out")
    a = ap.parse_args()
    keys = a.paper or list(PAPERS)
    doc = {
        "schemaVersion": 1,
        "kind": "no-content-per-question-validation-ledger",
        "contentPolicy": "numbers, lengths, counts, hashes, booleans only; "
                         "no question text, no option text, no image bytes",
        "vocabulary": {
            "structurally_valid": "all LOCAL structural checks passed; says nothing "
                                  "about official provenance",
            "invalid": "a hard structural check failed",
            "unknown": "check could not be evaluated",
            "capture_verified": "only set when an authorized no-credential handoff "
                                "covering the paper is supplied",
        },
        "papers": {},
    }
    for k in keys:
        doc["papers"][k] = validate_paper(a.repo, a.handoff or None, k, a.focus)
    if a.focus is not None:
        doc["focus"] = build_focus(doc, a.focus)
    out = json.dumps(doc, ensure_ascii=False, indent=1)
    (open(a.out, "w").write(out) if a.out else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
