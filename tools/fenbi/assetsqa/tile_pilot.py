#!/usr/bin/env python3
"""Graphic-option tile pilot — label-anchored option slot localization.

Offline, no account, no network, no upload.

WHY THIS IS NOT "SPLIT THE ROW IN 5"
------------------------------------
A first pass used raw XY-cut and read a 5-tile result as "1 stem + 4 options".
Geometry showed that is wrong for the common layout:

  * the figures are fused into ONE continuous band (no vertical gutters), and
  * underneath them sit FOUR small, evenly spaced glyphs -- the option labels.

So the raw tile count conflates labels with figures. This tool therefore treats
the **label row** as the anchor: four small similar glyphs define four option
SLOTS, and each option figure is cropped from the figure band above its slot.

WHAT IS DETERMINISTIC
---------------------
  * slot positions (from the label row geometry)
  * crop rectangles and every crop's sha256
  * split/slot stability across gutter thresholds

WHAT IS NOT -- AND IS NEVER CLAIMED
-----------------------------------
  * which glyph is A / B / C / D  -> needs OCR, absent on this host
  * that slot order equals option order -> a left-to-right convention, recorded
    as a hypothesis only
  * that any tile is the correct answer, or matches the source

Therefore `A_D_resolved` stays False and `binding` stays `need_review` for every
question, regardless of how clean the geometry looks.

Crops are written under a directory that MUST live inside the repo's git-ignored
`work/` tree; the tool refuses any other destination.

Usage:
  python3 -I tile_pilot.py --repo . --handoff <handoff> \
      --out-dir work/assetsqa-tiles [--paper js2025c] [--questions 88] [--out f.json]
"""
import argparse
import hashlib
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visual_consistency_audit as V  # noqa: E402
import visual_representation_audit as R  # noqa: E402

PAPERS = R.PAPERS
SHORT = R.SHORT
DEFAULT_GAPS = (3, 4, 5, 6, 8)


# ----------------------------------------------------------------- primitives
def load_ink(path, ink_threshold=235):
    with Image.open(path) as im:
        im = im.convert("L")
        w, h = im.size
        px = im.load()
        return [[px[x, y] < ink_threshold for x in range(w)] for y in range(h)], w, h


def row_bands(ink, w, h, gap=2):
    """Contiguous horizontal bands that contain ink."""
    prof = [sum(1 for x in range(w) if ink[y][x]) for y in range(h)]
    bands, start, run = [], None, 0
    for y, v in enumerate(prof):
        if v > 0:
            if start is None:
                start = y
            run = 0
        else:
            run += 1
            if start is not None and run >= gap:
                bands.append((start, y - run))
                start = None
                run = 0
    if start is not None:
        bands.append((start, h - 1))
    return bands


def col_segments(ink, y0, y1, gap=3):
    """Column ink segments inside a row band. Returns [(x0, x1)] inclusive."""
    w = len(ink[0])
    prof = [sum(1 for y in range(y0, y1 + 1) if ink[y][x]) for x in range(w)]
    segs, start, run = [], None, 0
    for x, v in enumerate(prof):
        if v > 0:
            if start is None:
                start = x
            run = 0
        else:
            run += 1
            if start is not None and run >= gap:
                segs.append((start, x - run))
                start = None
                run = 0
    if start is not None:
        segs.append((start, w - 1))
    return segs


def _cv(vals):
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    if mean == 0:
        return None
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return (var ** 0.5) / mean


def find_label_band(ink, w, h):
    """Find the row of four small glyphs that marks the option slots.

    Criteria (all structural, no glyph recognition):
      * exactly 4 column segments
      * band height between 8 and 40 px
      * segment widths between 4 and 50 px
      * relative width spread <= 0.6
      * every inter-segment gap >= 20 px
    Returns a dict or None.
    """
    best = None
    for (y0, y1) in row_bands(ink, w, h):
        bh = y1 - y0 + 1
        if not (8 <= bh <= 40):
            continue
        segs = col_segments(ink, y0, y1, gap=3)
        if len(segs) != 4:
            continue
        widths = [b - a + 1 for a, b in segs]
        if any(not (4 <= wd <= 50) for wd in widths):
            continue
        cv = _cv(widths)
        if cv is None or cv > 0.6:
            continue
        gaps = [segs[i + 1][0] - segs[i][1] - 1 for i in range(3)]
        if min(gaps) < 20:
            continue
        cand = {"band": [y0, y1], "segments": [[a, b] for a, b in segs],
                "widths": widths, "widthCV": round(cv, 4), "gaps": gaps}
        # prefer the band with the largest total gap (most label-like separation)
        score = sum(gaps)
        if best is None or score > best["_score"]:
            cand["_score"] = score
            best = cand
    if best:
        best.pop("_score", None)
    return best


def option_slots(segs, w):
    """Turn four label glyph x-ranges into four option slot x-ranges.

    Slot width comes from the MEDIAN INTER-GLYPH SPACING, and every slot is
    centred on its glyph. Deriving the first slot by extending to x=0 (the
    obvious alternative) absorbs the stem figure whenever the stem sits to the
    left of the options -- which it usually does.
    """
    centers = [(a + b) / 2 for a, b in segs]
    spacing = sorted(centers[i + 1] - centers[i] for i in range(len(centers) - 1))
    step = spacing[len(spacing) // 2]
    half = step / 2.0
    slots = []
    for c in centers:
        slots.append((max(0, int(round(c - half))), min(w, int(round(c + half)))))
    return slots, step


def bands_above(ink, w, h, label_band):
    """Ink bands strictly above the label band, nearest first."""
    ly0 = label_band["band"][0]
    return sorted([(y0, y1) for (y0, y1) in row_bands(ink, w, h) if y1 < ly0],
                  key=lambda b: -b[1])


def figure_band(ink, w, h, label_band):
    """The band the option figures live in: the NEAREST ink band above the
    labels. Picking by ink area instead would grab the stem row on two-row
    layouts (广东 Q42: stem row 13-152, option row 181-320, labels 334-358)."""
    above = bands_above(ink, w, h, label_band)
    return above[0] if above else None


def crop_and_hash(src_path, rect, out_path):
    """Deterministic crop + hash. Returns sha256, size and the rect used."""
    with Image.open(src_path) as im:
        crop = im.crop(rect)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        crop.save(out_path)
        cw, ch = crop.size
    with open(out_path, "rb") as fh:
        return {"sha256": hashlib.sha256(fh.read()).hexdigest(),
                "w": cw, "h": ch, "rect": list(rect)}


def slot_stability(path, gaps=DEFAULT_GAPS):
    """Is the four-label-slot structure stable across gutter thresholds?"""
    ink, w, h = load_ink(path)
    found = {}
    for g in gaps:
        # recompute segments at this gutter by monkey-free re-scan
        best = None
        for (y0, y1) in row_bands(ink, w, h):
            bh = y1 - y0 + 1
            if not (8 <= bh <= 40):
                continue
            segs = col_segments(ink, y0, y1, gap=g)
            if len(segs) != 4:
                continue
            widths = [b - a + 1 for a, b in segs]
            if any(not (4 <= wd <= 50) for wd in widths):
                continue
            cv = _cv(widths)
            if cv is None or cv > 0.6:
                continue
            gapv = [segs[i + 1][0] - segs[i][1] - 1 for i in range(3)]
            if min(gapv) < 20:
                continue
            score = sum(gapv)
            if best is None or score > best[0]:
                best = (score, y0, y1, segs)
        found[g] = best
    stabilities = {g: (v is not None) for g, v in found.items()}
    counts = [v[3] if v else None for v in found.values()]
    stable = all(stabilities.values()) and len({tuple(map(tuple, c)) for c in counts if c}) == 1
    g0 = next((g for g in gaps if found[g]), None)
    return {
        "perGapFound": {str(g): stabilities[g] for g in gaps},
        "stable": stable,
        "canonicalGap": g0,
        "labelBand": ([found[g0][1], found[g0][2]] if g0 else None),
        "segments": ([[a, b] for a, b in found[g0][3]] if g0 else None),
    }


# ----------------------------------------------------------------- question
def question_images(repo, mdrel, number):
    blocks, _ = R.repo_blocks(os.path.join(repo, mdrel))
    blk = blocks.get(number)
    if blk is None:
        return None, None
    imgs = []
    for m in V.IMG.finditer(blk):
        s = V.SRC.search(m.group(1))
        if s:
            imgs.append(s.group(1))
    cut = R.OPT.search(blk)
    stem_part = blk[:cut.start()] if cut else blk
    stem_imgs = [V.SRC.search(m.group(1)).group(1)
                 for m in V.IMG.finditer(stem_part) if V.SRC.search(m.group(1))]
    return imgs, stem_imgs


def resolve(repo, mdrel, imgdir, src):
    p = os.path.normpath(os.path.join(repo, os.path.dirname(mdrel), src))
    if os.path.isfile(p):
        return p
    base = os.path.basename(src)
    for sub in ("题目图", "公式图"):
        cand = os.path.join(repo, imgdir, sub, base)
        if os.path.isfile(cand):
            return cand
    return None


def analyze_image(src_path, src_name, out_dir, label, number):
    ink, w, h = load_ink(src_path)
    st = slot_stability(src_path)
    with open(src_path, "rb") as fh:
        src_sha = hashlib.sha256(fh.read()).hexdigest()

    rec = {
        "src": src_name,
        "sourceSha256": src_sha,
        "sourceW": w, "sourceH": h,
        "labelBandFound": st["labelBand"] is not None,
        "labelBand": st["labelBand"],
        "labelSegments": st["segments"],
        "slotStability": st["perGapFound"],
        "slotsStable": st["stable"],
        "optionSlots": [],
        "stemRegion": None,
        "A_D_resolved": False,
    }
    if st["labelBand"] is None:
        rec["slotLocalization"] = "ambiguous"
        rec["reason"] = "no four-glyph label row detected; option slots cannot be anchored"
        return rec

    slots, step = option_slots(st["segments"], w)
    fb = figure_band(ink, w, h, {"band": st["labelBand"]})
    if fb is None:
        rec["slotLocalization"] = "ambiguous"
        rec["reason"] = "label row found but no figure band above it"
        return rec

    above = bands_above(ink, w, h, {"band": st["labelBand"]})
    rec["layoutKind"] = "two-row" if len(above) > 1 else "single-row"
    rec["optionSlotWidth"] = round(step, 2)
    rec["slotLocalization"] = "deterministic" if st["stable"] else "unstable-across-thresholds"
    rec["figureBand"] = [fb[0], fb[1]]

    base = src_name.rsplit(".", 1)[0]
    for i, (x0, x1) in enumerate(slots):
        rect = (max(0, x0), fb[0], min(w, x1), fb[1] + 1)
        outp = os.path.join(out_dir, label, str(number), f"{base}-opt{i + 1}.png")
        try:
            rec["optionSlots"].append({
                "slot": i + 1,
                "labelGlyphX": st["segments"][i],
                **crop_and_hash(src_path, rect, outp),
            })
        except Exception as e:  # pragma: no cover - defensive
            rec["optionSlots"].append({"slot": i + 1, "error": type(e).__name__,
                                       "rect": list(rect)})

    # Stem candidate. Two defensible cases; both are labelled as candidates,
    # because "which pixels are the stem" is a semantic question:
    #   two-row  : the band immediately above the option band is the stem row
    #   single-row: the stem is the region left of the first option slot
    stem = None
    if len(above) > 1:
        sy0, sy1 = above[1]
        stem = {"kind": "band-above-option-row", "rect": [0, sy0, w, sy1 + 1]}
    elif slots[0][0] > 5:
        stem = {"kind": "left-of-first-slot", "rect": [0, fb[0], slots[0][0], fb[1] + 1]}
    if stem:
        outp = os.path.join(out_dir, label, str(number), f"{base}-stem.png")
        try:
            rec["stemRegion"] = {"localization": "candidate", **stem,
                                 **crop_and_hash(src_path, tuple(stem["rect"]), outp)}
        except Exception as e:  # pragma: no cover
            rec["stemRegion"] = {"localization": "candidate", **stem,
                                 "error": type(e).__name__}
    else:
        rec["stemRegion"] = {"localization": "not-located",
                             "reason": "no band above the option row and no space left of slot 1"}
    rec["binding"] = "need_review"
    rec["bindingNote"] = ("slots are geometric; the printed letters are not machine-readable, "
                          "so slot order == option order stays a hypothesis")
    return rec


def analyze(repo, handoff, key, number, out_dir):
    label, mdrel, imgdir = PAPERS[key]
    canon = json.load(open(os.path.join(handoff, "papers", key, "canonical.json")))
    hq = {q["sourceNumber"]: q for q in canon["questions"]}
    if number not in hq:
        return {"number": number, "status": "not-in-source-capture"}
    q = hq[number]
    texts = [(o["label"], (o.get("text") or "").strip()) for o in q["options"]]
    label_only = bool(texts) and all(t == l for l, t in texts)
    imgs, _ = question_images(repo, mdrel, number)
    if not imgs:
        return {"number": number, "status": "no-image"}
    rec = {
        "paper": label,
        "sourceId": canon["identity"]["sourceId"],
        "originalNumber": number,
        "optionTextIsLabelOnly": label_only,
        "optionsComplete": not label_only,
        "images": [],
        "A_D_resolved": False,
        "binding": "need_review",
    }
    for src in imgs:
        p = resolve(repo, mdrel, imgdir, src)
        if not p:
            rec["images"].append({"src": os.path.basename(src), "resolved": False})
            continue
        rec["images"].append(analyze_image(p, os.path.basename(src), out_dir, label, number))
    slots_ok = [im for im in rec["images"] if im.get("slotLocalization") == "deterministic"]
    rec["slotsLocalizedDeterministically"] = bool(slots_ok) and len(slots_ok) == len(rec["images"])
    return rec


# ----------------------------------------------------------------- gate
def completeness_gate(repo, handoff, key):
    """Options that are only the label letters are NOT complete: the option
    figures live inside the composite and no per-option object exists. The
    original composite must stay referenced."""
    label, mdrel, imgdir = PAPERS[key]
    canon = json.load(open(os.path.join(handoff, "papers", key, "canonical.json")))
    blocks, _ = R.repo_blocks(os.path.join(repo, mdrel))
    rows = []
    for q in canon["questions"]:
        n = q["sourceNumber"]
        texts = [(o.get("label"), (o.get("text") or "").strip()) for o in q.get("options") or []]
        if not texts:
            continue
        label_only = all(t == l for l, t in texts)
        placeholder = R.is_placeholder_stub(q)
        blk = blocks.get(n, "")
        cut = R.OPT.search(blk)
        stem_part = blk[:cut.start()] if cut else blk
        stem_imgs = [V.SRC.search(m.group(1)).group(1) for m in V.IMG.finditer(stem_part)
                     if V.SRC.search(m.group(1))]
        if placeholder:
            state, reason = False, "source-placeholder"
        elif label_only:
            state, reason = False, "composite-figure-no-option-objects"
        else:
            state, reason = True, None
        rows.append({
            "number": n,
            "optionCount": len(texts),
            "optionTextIsLabelOnly": label_only,
            "optionsComplete": state,
            "reason": reason,
            "compositePreserved": bool(stem_imgs),
            "compositeImageCount": len(stem_imgs),
        })
    return {
        "paper": label,
        "questions": len(rows),
        "complete": sum(1 for r in rows if r["optionsComplete"]),
        "incompleteGraphicLabelOnly": sum(1 for r in rows
                                          if r["reason"] == "composite-figure-no-option-objects"),
        "incompletePlaceholder": sum(1 for r in rows if r["reason"] == "source-placeholder"),
        "compositeMissing": [r["number"] for r in rows
                             if r["optionTextIsLabelOnly"] and not r["compositePreserved"]],
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--out-dir", required=True, help="MUST be inside the repo's work/")
    ap.add_argument("--paper", default="all", choices=["all", *SHORT])
    ap.add_argument("--questions", default="")
    ap.add_argument("--out")
    a = ap.parse_args()

    rel = os.path.relpath(os.path.abspath(a.out_dir), os.path.abspath(a.repo))
    if not (rel == "work" or rel.startswith("work" + os.sep)):
        print("refusing: --out-dir must live under work/ (git-ignored)", file=sys.stderr)
        return 2

    keys = [SHORT[a.paper]] if a.paper != "all" else list(PAPERS)
    wanted = [int(x) for x in a.questions.split(",") if x.strip()]
    ledger = {
        "schemaVersion": 1,
        "kind": "no-content-tile-pilot-ledger",
        "contentPolicy": "numbers, basenames, sha256, rectangles, counts only; "
                         "no image bytes emitted; crops stay under work/ (git-ignored)",
        "claims": {
            "supported": [
                "option slot localization from the four-glyph label row",
                "crop rectangles and per-crop sha256",
                "slot stability across gutter thresholds",
            ],
            "not_supported": [
                "A/B/C/D assignment (printed letters are not machine-readable offline)",
                "slot order == option order (recorded as a hypothesis only)",
                "tile == correct answer",
                "tile == the source figure",
            ],
        },
        "rows": [],
        "completenessGate": {},
    }
    for k in keys:
        canon = json.load(open(os.path.join(a.handoff, "papers", k, "canonical.json")))
        graphic = [q["sourceNumber"] for q in canon["questions"]
                   if q["options"] and all((o.get("text") or "").strip() == o.get("label")
                                           for o in q["options"])]
        for n in [x for x in graphic if not wanted or x in wanted]:
            ledger["rows"].append(analyze(a.repo, a.handoff, k, n, a.out_dir))
        ledger["completenessGate"][PAPERS[k][0]] = completeness_gate(a.repo, a.handoff, k)

    out = json.dumps(ledger, ensure_ascii=False, indent=1)
    (open(a.out, "w").write(out) if a.out else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
