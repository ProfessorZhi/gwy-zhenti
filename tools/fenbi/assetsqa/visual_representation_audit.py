#!/usr/bin/env python3
"""Round-2 visual-representation audit.

Splits source-vs-repository differences into *representation* and *content*, and
audits three systemic questions that round 1 could not settle:

  1. classify-source-repo-diff
     For a given paper, decide per question whether a difference is
     (a) an original-number mapping problem, (b) a text-vs-image rendering
     difference, or (c) genuinely different content. Differences are examined at
     BOTH stem and option level -- round 1 only looked at the stem.

  2. audit-vacuous-stem
     A question whose captured stem is empty and whose repository stem is an
     image matches on options alone. That is a match-gate weakness, not a
     content gap: the repo figure IS the stem.

  3. audit-declared-dimensions
     Split declared-vs-true image dimension errors into "capped-width rounding"
     (declared width == true width, height off by a small constant) and
     "genuine size disagreement". Round 1 reported these as one bucket.

  4. audit-graphic-composites
     Graphic-reasoning questions are delivered as ONE composite raster plus four
     label-only options. Test by XY-cut whether the composite is tile-separable
     (i.e. whether per-option figures could be bound at all).

Emits a no-content ledger: numbers, basenames, sha256, dimensions, counts.
No question text, no option text, no image bytes, no source URLs.

Usage:
  python3 -I visual_representation_audit.py --repo <repo> --handoff <handoff>
                                            [--paper gd|js2025c|js2024a|zj2026c] [--out f.json]
"""
import argparse, collections, hashlib, json, os, re, sys, difflib

from PIL import Image

# reuse round-1 helpers so both rounds agree on parsing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visual_consistency_audit as V  # noqa: E402

IMG_TOKEN = "\x01IMG\x02"
HDR = re.compile(r'^#{2,3}\s*(第\s*(\d+)\s*题|材料\s*(\d+))', re.M)
OPT = re.compile(r'^\s*[-*]\s*\*\*([A-D])\*\*\s*[.．、]?\s*(.*)$', re.M)
PLACEHOLDER_OPTS = {"缺失", "暂缺"}   # sentinel is NOT uniform across captures
PLACEHOLDER_STEM_MARKERS = ("征集", "上传")

PAPERS = {
    "js-2025-xingce-c-4189916": ("JS2025C", "省考/江苏/2025/行测-C类.md", "图片/省考-江苏-2025-行测-C类"),
    "js-2024-xingce-a-4162243": ("JS2024A", "省考/江苏/2024/行测-A类.md", "图片/省考-江苏-2024-行测-A类"),
    "gd-2020-xingce-county-96785": ("GD2020县", "省考/广东/2020/行测-县级卷.md", "图片/省考-广东-2020-行测-县级卷"),
    "zj-2026-xingce-c-8399763": ("ZJ2026C", "省考/浙江/2026/行测-C类.md", "图片/省考-浙江-2026-行测-C类"),
}
SHORT = {"gd": "gd-2020-xingce-county-96785", "js2025c": "js-2025-xingce-c-4189916",
         "js2024a": "js-2024-xingce-a-4162243", "zj2026c": "zj-2026-xingce-c-8399763"}

TAG = re.compile(r"<[^>]+>")
WIDTH_FOLD = str.maketrans({"％": "%", "。": ".", "，": ",", "：": ":", "；": ";",
                            "（": "(", "）": ")", "－": "-", "—": "-", "–": "-", "　": " "})


# --------------------------------------------------------------- text helpers
def norm(s):
    s = V.IMG.sub(IMG_TOKEN, s)
    s = TAG.sub("", s)
    s = s.translate(WIDTH_FOLD)
    return re.sub(r"\s+", "", s)


def split_block(block):
    block = re.sub(r"^#{2,3}[^\n]*\n", "", block)
    opts = [(m.group(1), m.group(2).strip()) for m in OPT.finditer(block)]
    first = OPT.search(block)
    return (block[:first.start()] if first else block), opts


def repo_blocks(path):
    t = open(path, encoding="utf8").read()
    cut = re.search(r"^##\s*答案与解析", t, re.M)
    body = t[:cut.start()] if cut else t
    marks = [(m.start(), m.group(2), m.group(3)) for m in HDR.finditer(body)]
    q, mat = {}, {}
    for i, (off, qn, mn) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        (q if qn else mat)[int(qn or mn)] = body[off:end]
    return q, mat


def diff_kinds(a, b):
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            continue
        x, y = a[i1:i2], b[j1:j2]
        out.append({
            "op": tag,
            "srcImg": IMG_TOKEN in x, "repoImg": IMG_TOKEN in y,
            "srcNum": bool(re.fullmatch(r"[-+×÷/%.,0-9A-Za-z]+", x or "")),
            "repoNum": bool(re.fullmatch(r"[-+×÷/%.,0-9A-Za-z]+", y or "")),
        })
    return out


def is_placeholder_stub(q):
    """A crowdsourcing stub. The sentinel varies between captures (缺失 / 暂缺) and
    the notice wording varies too, so detect on either signal -- a single-string
    check under-detects."""
    texts = [(o.get("text") or "").strip() for o in (q.get("options") or [])]
    if texts and all(t in PLACEHOLDER_OPTS for t in texts):
        return True
    stem = q.get("stemText") or ""
    return all(m in stem for m in PLACEHOLDER_STEM_MARKERS)


def classify_pair(src, rep):
    """Classify one text field pair (stem or a single option)."""
    a, b = norm(src), norm(rep)
    if a == b:
        return "same", []
    kinds = diff_kinds(a, b)
    if kinds and all(k["srcImg"] != k["repoImg"] for k in kinds):
        return "text-vs-image", kinds
    if kinds and all(k["srcImg"] and k["repoImg"] for k in kinds):
        return "image-vs-image", kinds
    if kinds and all(k["srcNum"] or k["repoNum"] for k in kinds):
        return "numeric-token", kinds
    return "content-diff", kinds


def image_facts(repo, mdrel, src, imgdir):
    """Resolve an <img src> to (basename, sha256, w, h, bytes, on_disk)."""
    base = os.path.basename(src)
    p = os.path.normpath(os.path.join(repo, os.path.dirname(mdrel), src))
    if not os.path.isfile(p):
        for sub in ("题目图", "公式图"):
            cand = os.path.join(repo, imgdir, sub, base)
            if os.path.isfile(cand):
                p = cand
                break
    if not os.path.isfile(p):
        return {"basename": base, "onDisk": False}
    with Image.open(p) as im:
        im.load()
        return {"basename": base, "onDisk": True,
                "sha256": V.sha256_file(p), "w": im.width, "h": im.height,
                "bytes": os.path.getsize(p)}


# --------------------------------------------------------------- audit 1
def classify_source_repo_diff(repo, handoff, key):
    label, mdrel, imgdir = PAPERS[key]
    canon = json.load(open(os.path.join(handoff, "papers", key, "canonical.json")))
    unm = list(canon["reconciliation"]["unmatchedSourceNumbers"])
    blocks, _ = repo_blocks(os.path.join(repo, mdrel))
    hq = {q["sourceNumber"]: q for q in canon["questions"]}
    # repository index for the cross-number test
    rep_norm = {}
    for n, blk in blocks.items():
        s, o = split_block(blk)
        rep_norm[n] = (norm(s), [norm(t) for _, t in o])

    rows = []
    for n in unm:
        h = hq[n]
        src_opts = [(o["label"], o["text"]) for o in h["options"]]
        if n not in blocks:
            src_ph = is_placeholder_stub(h)
            rows.append({"number": n, "repoPresent": False,
                         "class": "absent-from-repository",
                         "verdict": "source-placeholder" if src_ph else "absent-from-repository",
                         "sourceIsPlaceholder": src_ph,
                         "detail": "source number has no repository block"})
            continue
        rs, ro = split_block(blocks[n])

        # A crowdsourcing stub is not content: comparing it to real backfilled
        # content says nothing about correctness. Never call that a content diff.
        src_placeholder = is_placeholder_stub(h)
        if src_placeholder:
            ev = []
            for m in V.IMG.finditer(blocks[n]):
                sc = V.SRC.search(m.group(1))
                if sc:
                    ev.append(image_facts(repo, mdrel, sc.group(1), imgdir))
            rows.append({
                "number": n, "repoPresent": True,
                "sourceIsPlaceholder": True,
                "stemClass": "source-placeholder", "optionClass": "source-placeholder",
                "optionDetail": [], "diffLayers": ["source-stub"],
                "verdict": "source-placeholder",
                "vacuousStem": False, "numberingIssue": False,
                "bestRepoNumber": None, "bestRatio": None, "ownRatio": None,
                "images": ev,
                "humanReviewReasons": [
                    "source is a crowdsourcing stub; repository content came from a "
                    "different source and cannot be corroborated or refuted by the capture"],
            })
            continue

        stem_cls, stem_kinds = classify_pair(h["stemText"], rs)

        # option-level: pair by label, classify each
        opt_cls, opt_detail = "same", []
        rep_by_label = {l: t for l, t in ro}
        for lab, txt in src_opts:
            if lab not in rep_by_label:
                opt_detail.append({"label": lab, "class": "missing-in-repo"})
                opt_cls = "content-diff"
                continue
            c, k = classify_pair(txt, rep_by_label[lab])
            opt_detail.append({"label": lab, "class": c, "diffTokenKinds": len(k)})
            if c != "same" and opt_cls == "same":
                opt_cls = c
            elif c == "content-diff":
                opt_cls = "content-diff"

        # vacuous stem: captured stem empty, repository stem is an image
        vacuous = (not (h["stemText"] or "").strip()
                   and IMG_TOKEN in norm(rs))
        # cross-number test
        hs = norm(h["stemText"])
        best, best_r = None, -1.0
        if hs:
            for m, (ms, _) in rep_norm.items():
                r = difflib.SequenceMatcher(None, hs, ms).ratio()
                if r > best_r:
                    best, best_r = m, r
        own = difflib.SequenceMatcher(None, hs, rep_norm[n][0]).ratio() if (hs and n in rep_norm) else 0.0

        # collect image evidence for every image in the repo block
        ev = []
        for m in V.IMG.finditer(blocks[n]):
            s = V.SRC.search(m.group(1))
            if s:
                f = image_facts(repo, mdrel, s.group(1), imgdir)
                f["inBlock"] = "stem" if m.start() < (OPT.search(blocks[n]).start()
                                                     if OPT.search(blocks[n]) else len(blocks[n])) else "option"
                ev.append(f)

        # overall verdict
        layers = []
        if stem_cls != "same":
            layers.append("stem:" + stem_cls)
        if opt_cls != "same":
            layers.append("option:" + opt_cls)
        repr_only = all(c in ("text-vs-image", "image-vs-image", "numeric-token", "same")
                        for c in (stem_cls, opt_cls))
        numbering = bool(best not in (None, n) and best_r - own > 0.15 and best_r > 0.85)
        if vacuous:
            verdict = "repr-diff+human-review"
        elif repr_only and layers:
            verdict = "repr-diff+human-review"
        elif not layers:
            verdict = "same"
        else:
            verdict = "content-diff"

        rows.append({
            "number": n,
            "repoPresent": True,
            "stemClass": stem_cls,
            "optionClass": opt_cls,
            "optionDetail": opt_detail,
            "diffLayers": layers,
            "verdict": verdict,
            "vacuousStem": vacuous,
            "sourceIsPlaceholder": False,
            "numberingIssue": numbering,
            "bestRepoNumber": best,
            "bestRatio": round(best_r, 4) if best_r >= 0 else None,
            "ownRatio": round(own, 4),
            # images whose content is a rendered formula/figure -> opaque offline
            "images": ev,
            "humanReviewReasons": sorted({
                *(["formula/figure image content is not OCR-verifiable offline"]
                  if any(True for f in ev if f.get("onDisk")) else []),
                *(["captured stem empty; repository stem is an image"] if vacuous else {}),
            }),
        })
    return {"paper": label, "unmatchedNumbers": unm, "rows": rows}



# --------------------------------------------------------------- audit 2
def audit_vacuous_stem_matches(repo, handoff, key):
    """Matched questions whose captured stem is empty and whose repository stem is
    an image. The match then rests on identical options alone -- a gate weakness,
    not a content gap: the repository figure IS the stem."""
    label, mdrel, imgdir = PAPERS[key]
    canon = json.load(open(os.path.join(handoff, "papers", key, "canonical.json")))
    unm = set(canon["reconciliation"]["unmatchedSourceNumbers"])
    blocks, _ = repo_blocks(os.path.join(repo, mdrel))
    hq = {q["sourceNumber"]: q for q in canon["questions"]}
    rows = []
    for n, h in sorted(hq.items()):
        if not (h.get("stemText") or "").strip():
            if n not in blocks:
                continue
            blk = blocks[n]
            _, opts = split_block(blk)
            imgs = [V.SRC.search(m.group(1)).group(1) for m in V.IMG.finditer(blk)
                    if V.SRC.search(m.group(1))]
            stem_part = blk.split("- **A**")[0] if "- **A**" in blk else blk
            stem_imgs = [V.SRC.search(m.group(1)).group(1) for m in V.IMG.finditer(stem_part)
                         if V.SRC.search(m.group(1))]
            src_opts = [(o["label"], norm(o["text"])) for o in h["options"]]
            rep_opts = [(l, norm(t)) for l, t in opts]
            rows.append({
                "number": n,
                "availableInHandoff": n in hq,
                "countedMatched": n not in unm,
                "capturedStemEmpty": True,
                "repoStemIsImage": bool(stem_imgs),
                "repoStemImageCount": len(stem_imgs),
                "repoBlockImageCount": len(imgs),
                "optionsIdentical": src_opts == rep_opts,
                "optionCountSrc": len(src_opts), "optionCountRepo": len(rep_opts),
                "imageEvidence": [image_facts(repo, mdrel, s, imgdir) for s in stem_imgs],
                "diagnosis": ("stem-is-image-and-capture-empty; the match is supported by "
                              "identical options and a vacuous stem comparison"
                              if stem_imgs and src_opts == rep_opts else "review"),
            })
    return {"paper": label, "rows": rows,
            "countedMatched": sum(1 for r in rows if r["countedMatched"])}


# --------------------------------------------------------------- audit 3
def audit_declared_dimensions(repo, key):
    label, mdrel, imgdir = PAPERS[key]
    t = open(os.path.join(repo, mdrel), encoding="utf8").read()
    rows, agg = [], collections.Counter()
    for m in V.IMG.finditer(t):
        wm, hm = V.WIDTH.search(m.group(1)), V.HEIGHT.search(m.group(1))
        s = V.SRC.search(m.group(1))
        if not (wm and hm and s):
            continue
        dw, dh = int(wm.group(1)), int(hm.group(1))
        f = image_facts(repo, mdrel, s.group(1), imgdir)
        if not f.get("onDisk"):
            continue
        tw, th = f["w"], f["h"]
        agg["declared"] += 1
        if (dw, dh) == (tw, th):
            agg["exact"] += 1
            continue
        kind = ("capped-width-rounding" if dw == tw and abs(dh - th) <= 2
                else "size-disagreement")
        agg[kind] += 1
        rows.append({"basename": f["basename"], "sha256": f["sha256"],
                     "declared": [dw, dh], "true": [tw, th],
                     "delta": [dw - tw, dh - th], "kind": kind,
                     "cappedWidth": dw == 700})
    return {"paper": label, "counts": dict(agg), "rows": rows}


# --------------------------------------------------------------- audit 4
def xy_cut(ink, x0, y0, x1, y1, gap=4, depth=0):
    if depth > 6 or x1 - x0 < 20 or y1 - y0 < 20:
        return [(x0, y0, x1, y1)]
    for axis in (0, 1):  # 0 = columns, 1 = rows
        lo, hi = (x0, x1) if axis == 0 else (y0, y1)
        prof = []
        for v in range(lo, hi):
            if axis == 0:
                prof.append(sum(1 for y in range(y0, y1) if ink[y][v]))
            else:
                prof.append(sum(1 for x in range(x0, x1) if ink[v][x]))
        runs, s, g = [], None, 0
        for i, val in enumerate(prof):
            if val > 0:
                if s is None:
                    s = i
                g = 0
            else:
                g += 1
                if s is not None and g >= gap:
                    runs.append((s, i - g)); s = None; g = 0
        if s is not None:
            runs.append((s, len(prof) - 1))
        if len(runs) > 1:
            out = []
            for a, b in runs:
                if axis == 0:
                    out += xy_cut(ink, x0 + a, y0, x0 + b + 1, y1, gap, depth + 1)
                else:
                    out += xy_cut(ink, x0, y0 + a, x1, y0 + b + 1, gap, depth + 1)
            return out
    return [(x0, y0, x1, y1)]


def audit_graphic_composites(repo, handoff, key):
    label, mdrel, imgdir = PAPERS[key]
    canon = json.load(open(os.path.join(handoff, "papers", key, "canonical.json")))
    graphic = [q["sourceNumber"] for q in canon["questions"]
               if q["options"] and all((o.get("text") or "").strip() == o.get("label")
                                       for o in q["options"])]
    blocks, _ = repo_blocks(os.path.join(repo, mdrel))
    rows = []
    for n in graphic:
        if n not in blocks:
            rows.append({"number": n, "status": "absent-from-repository"})
            continue
        blk = blocks[n]
        _, opts = split_block(blk)
        imgs = [V.SRC.search(m.group(1)).group(1) for m in V.IMG.finditer(blk)
                if V.SRC.search(m.group(1))]
        rec = {"number": n, "optionTextIsLabelOnly": all(
                   (t.strip() == l) for l, t in opts) if opts else False,
               "optionCount": len(opts), "imageCount": len(imgs), "tiles": []}
        for src in imgs:
            f = image_facts(repo, mdrel, src, imgdir)
            if not f.get("onDisk"):
                rec["tiles"].append({"basename": f["basename"], "onDisk": False})
                continue
            p = os.path.normpath(os.path.join(repo, os.path.dirname(mdrel), src))
            if not os.path.isfile(p):
                for sub in ("题目图", "公式图"):
                    cand = os.path.join(repo, imgdir, sub, f["basename"])
                    if os.path.isfile(cand):
                        p = cand
                        break
            try:
                with Image.open(p) as im:
                    im = im.convert("L")
                    w, h = im.size
                    px = im.load()
                    ink = [[px[x, y] < 235 for x in range(w)] for y in range(h)]
                boxes = xy_cut(ink, 0, 0, w, h)
                rec["tiles"].append({"basename": f["basename"], "sha256": f["sha256"],
                                     "w": w, "h": h, "boxes": len(boxes),
                                     "tileWidths": sorted((b[2] - b[0] for b in boxes),
                                                          reverse=True)[:8]})
            except Exception as e:
                rec["tiles"].append({"basename": f["basename"], "error": type(e).__name__})
        rec["separable"] = any(t.get("boxes", 0) >= 5 for t in rec["tiles"])
        rows.append(rec)
    boxes = collections.Counter(t.get("boxes") for r in rows for t in r.get("tiles", [])
                                if "boxes" in t)
    return {"paper": label, "graphicQuestions": len(graphic),
            "separableQuestions": sum(1 for r in rows if r.get("separable")),
            "boxCountDistribution": dict(sorted(boxes.items())), "rows": rows}


# --------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--paper", default="all", choices=["all", *SHORT])
    ap.add_argument("--out")
    a = ap.parse_args()
    keys = [SHORT[a.paper]] if a.paper != "all" else list(PAPERS)
    doc = {"schemaVersion": 1, "kind": "no-content-visual-representation-ledger",
           "contentPolicy": "numbers, basenames, sha256, dimensions, counts only; "
                            "no question text, no option text, no image bytes, no source URLs",
           "epistemicRules": [
               "text-vs-image is a REPRESENTATION difference; it is not proof that the "
               "rendered value equals the source text",
               "formula/figure raster content is opaque offline (no OCR on this host) -> human review",
               "sha256 equal => identical bytes; sha256 differ => visual difference UNKNOWN",
           ],
           "diffClassification": {}, "vacuousStemMatches": {},
           "declaredDimensions": {}, "graphicComposites": {}}
    for k in keys:
        lab = PAPERS[k][0]
        doc["diffClassification"][lab] = classify_source_repo_diff(a.repo, a.handoff, k)
        doc["vacuousStemMatches"][lab] = audit_vacuous_stem_matches(a.repo, a.handoff, k)
        doc["declaredDimensions"][lab] = audit_declared_dimensions(a.repo, k)
        doc["graphicComposites"][lab] = audit_graphic_composites(a.repo, a.handoff, k)
    out = json.dumps(doc, ensure_ascii=False, indent=1)
    (open(a.out, "w").write(out) if a.out else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
