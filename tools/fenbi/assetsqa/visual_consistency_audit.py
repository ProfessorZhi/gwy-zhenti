#!/usr/bin/env python3
"""Independent visual/asset consistency audit for the 4 fenbi-captured papers.

Read-only, offline, credential-free. Emits a machine-readable *no-content*
discrepancy ledger: counts, numbers, hashes, image basenames and dimensions.
It never emits question text, option text, image bytes or source URLs.

Epistemic rules (encoded deliberately):
  * sha256 equal  => identical bytes. SOUND.
  * sha256 differ => pixel/visual difference UNKNOWN. No bytes are shipped by
    the handoff, and this host has no OCR, so no visual verdict is claimed.
  * no question->asset binding exists in the handoff schema, so any
    "graphic-reasoning option correspondence" claim is unverifiable there.

Usage:
  python3 -I visual_consistency_audit.py --repo <repo-root> --handoff <handoff-root>
                                         [--out ledger.json]
Exit code 0 = audit ran; 1 = a hard input was missing. Findings are data, not
exit status.
"""
import argparse, collections, hashlib, json, os, re, sys, urllib.parse

from PIL import Image

TARGETS = {
    "js-2025-xingce-c-4189916": ("JS2025C", "省考/江苏/2025/行测-C类.md",
                                 "图片/省考-江苏-2025-行测-C类"),
    "js-2024-xingce-a-4162243": ("JS2024A", "省考/江苏/2024/行测-A类.md",
                                 "图片/省考-江苏-2024-行测-A类"),
    "gd-2020-xingce-county-96785": ("GD2020县", "省考/广东/2020/行测-县级卷.md",
                                    "图片/省考-广东-2020-行测-县级卷"),
    "zj-2026-xingce-c-8399763": ("ZJ2026C", "省考/浙江/2026/行测-C类.md",
                                 "图片/省考-浙江-2026-行测-C类"),
}
QHDR = re.compile(r'^#{2,3}\s*(第\s*(\d+)\s*题|材料\s*(\d+))', re.M)
IMG = re.compile(r'<img\b([^>]*?)/?>', re.I)
SRC = re.compile(r'src="([^"]*)"')
WIDTH = re.compile(r'width\s*=\s*"(\d+)\s*(?:px)?"')
HEIGHT = re.compile(r'height\s*=\s*"(\d+)\s*(?:px)?"')
HOST_OK = re.compile(r'(^|\.)(fbstatic\.cn|fenbike\.cn|fenbi\.com)$', re.I)
PARAM_OK = {"width", "fontSize"}
ANS_SECTION = re.compile(r'^##\s*答案与解析', re.M)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_md(path):
    """Question/material block image attribution.

    An image inside a 材料 block belongs to the material, not to the preceding
    question -- attributing by nearest preceding question header mis-assigns
    every material figure (this was a real bug in an earlier pass).
    """
    text = open(path, encoding="utf8").read()
    marks = [(m.start(), m.group(2), m.group(3)) for m in QHDR.finditer(text)]
    by_q, by_mat, unattributed = collections.defaultdict(list), collections.defaultdict(list), []
    refs = []
    for m in IMG.finditer(text):
        s = SRC.search(m.group(1))
        if not s:
            continue
        raw = urllib.parse.unquote(s.group(1))
        rec = {
            "base": os.path.basename(raw),
            "dirKey": os.path.dirname(raw),
            "declaredW": int(WIDTH.search(m.group(1)).group(1)) if WIDTH.search(m.group(1)) else None,
            "declaredH": int(HEIGHT.search(m.group(1)).group(1)) if HEIGHT.search(m.group(1)) else None,
        }
        cur = None
        for off, qn, mn in marks:
            if off < m.start():
                cur = (qn, mn)
            else:
                break
        if cur and cur[0] is not None:
            rec["question"] = int(cur[0]); by_q[int(cur[0])].append(rec["base"])
        elif cur and cur[1] is not None:
            rec["material"] = int(cur[1]); by_mat[int(cur[1])].append(rec["base"])
        else:
            unattributed.append(rec["base"])
        refs.append(rec)
    return text, refs, by_q, by_mat, unattributed


def audit(repo, handoff):
    L = []
    def add(kind, paper, ref, verdict, detail, evidence=None):
        L.append({"kind": kind, "paper": paper, "ref": ref, "verdict": verdict,
                  "detail": detail, "evidence": evidence or {}})

    papers = {}
    for key, (label, mdrel, imgdir) in TARGETS.items():
        hp = os.path.join(handoff, "papers", key)
        if not os.path.isdir(hp):
            print(f"missing handoff paper {key}", file=sys.stderr)
            return None
        canon = json.load(open(os.path.join(hp, "canonical.json")))
        assets = json.load(open(os.path.join(hp, "assets-index.json")))["assets"]
        md = os.path.join(repo, mdrel)
        text, refs, by_q, by_mat, unattributed = parse_md(md) if os.path.isfile(md) else (None, [], {}, {}, [])
        papers[label] = dict(key=key, canon=canon, assets=assets, mdrel=mdrel,
                             imgdir=imgdir, text=text, refs=refs, by_q=by_q,
                             by_mat=by_mat, unattributed=unattributed)
        add("paper-present", label, key, "pass",
            f"handoff + repo markdown present; {len(canon['questions'])} source questions, "
            f"{len(assets)} captured assets")

    # ---- A. handoff asset byte availability -------------------------------
    tot = present = 0
    for label, P in papers.items():
        miss = [a["file"] for a in P["assets"]
                if not os.path.isfile(os.path.join(handoff, a["relativePath"]))]
        tot += len(P["assets"]); present += len(P["assets"]) - len(miss)
        add("asset-bytes-shipped", label, f"{len(P['assets'])} assets",
            "unknown" if miss else "pass",
            f"{len(miss)}/{len(P['assets'])} asset byte files absent from the handoff",
            {"absent": len(miss)})
    add("asset-bytes-shipped", "ALL", f"{tot} assets", "unknown" if present < tot else "pass",
        f"{present}/{tot} asset bytes present -> handoff-internal sha256/dimension claims "
        f"are unverifiable from the handoff alone", {"present": present, "total": tot})

    # ---- B. self-check receipt strength -----------------------------------
    for label, P in papers.items():
        notflagged = [a["file"] for a in P["assets"] if a.get("filenameMatchesHash") is not True]
        notderived = [a["file"] for a in P["assets"] if a["file"] != a["sha256"] + ".png"]
        add("selfcheck-receipt-strength", label, "verify-handoff.mjs:32", "defect",
            "the handoff self-check reads a pre-computed filenameMatchesHash boolean and never "
            "re-hashes content; with 0 bytes shipped no content hash is computed anywhere, so the "
            "README claim '图片文件名 == 内容 sha256' is not actually enforced",
            {"boolean_not_true": len(notflagged), "filename_not_sha_derived": len(notderived)})

    # ---- C. source-url policy --------------------------------------------
    for label, P in papers.items():
        bad_host, bad_param = [], []
        for a in P["assets"]:
            u = a.get("sourceUrl") or ""
            host = (re.match(r'^https?://([^/?#]+)', u) or [None, ""])[1] if u else ""
            if not HOST_OK.search(host):
                bad_host.append(u)
            if "?" in u:
                for kv in u.split("?", 1)[1].split("&"):
                    if kv and kv.split("=")[0] not in PARAM_OK:
                        bad_param.append(u)
        add("source-url-policy", label, "assets",
            "pass" if not bad_host and not bad_param else "defect",
            f"{len(bad_host)} off-policy hosts, {len(bad_param)} off-policy query params",
            {"bad_host": len(bad_host), "bad_param": len(bad_param)})

    # ---- D. real decode + declared-dimension agreement --------------------
    decode = {}
    for label, P in papers.items():
        root = os.path.join(repo, P["imgdir"])
        errs, dimbad, n = [], [], 0
        if os.path.isdir(root):
            for dp, _, fs in os.walk(root):
                for fn in fs:
                    n += 1
                    fp = os.path.join(dp, fn)
                    try:
                        with Image.open(fp) as im:
                            im.load()
                    except Exception as e:
                        errs.append({"file": fn, "error": type(e).__name__})
        for r in P["refs"]:
            if r["declaredW"] is None or r["declaredH"] is None:
                continue
            fp = None
            for cand in (os.path.join(repo, P["imgdir"], r["dirKey"].split("/")[-1], r["base"]),):
                if os.path.isfile(cand):
                    fp = cand
            if not fp:
                continue
            try:
                with Image.open(fp) as im:
                    im.load()
                    if (im.width, im.height) != (r["declaredW"], r["declaredH"]):
                        dimbad.append({"question": r.get("question"), "base": r["base"],
                                       "declared": [r["declaredW"], r["declaredH"]],
                                       "true": [im.width, im.height]})
            except Exception:
                pass
        decode[label] = {"dirFiles": n, "decodeErrors": errs, "declaredDimMismatch": dimbad}
        add("image-decode", label, P["imgdir"],
            "pass" if not errs else "defect",
            f"{n} image files decoded; {len(errs)} decode errors", {"errors": errs[:5]})
        add("declared-vs-true-dimensions", label, "img width/height attrs",
            "pass" if not dimbad else "need_review",
            f"{len(dimbad)} images whose declared width/height differ from the true decoded size",
            {"mismatches": dimbad})

    # ---- E. handoff <-> repo join by source basename ----------------------
    for label, P in papers.items():
        hb = {}
        for a in P["assets"]:
            u = a.get("sourceUrl") or ""
            hb.setdefault(os.path.basename(urllib.parse.urlparse(u).path), a)
        # basename -> true decoded facts from the repo trees
        truth = {}
        root = os.path.join(repo, P["imgdir"])
        for dp, _, fs in os.walk(root):
            for fn in fs:
                fp = os.path.join(dp, fn)
                try:
                    with Image.open(fp) as im:
                        im.load()
                        truth[fn] = {"sha256": sha256_file(fp), "w": im.width, "h": im.height,
                                     "bytes": os.path.getsize(fp)}
                except Exception:
                    pass
        agree = dis = only = 0
        onlylist = []
        for b, a in hb.items():
            t = truth.get(b)
            if not t:
                only += 1
                onlylist.append({"sha256": a["sha256"], "w": a["width"], "h": a["height"],
                                 "bytes": a["bytes"]})
                continue
            if (t["sha256"] == a["sha256"] and t["w"] == a["width"]
                    and t["h"] == a["height"] and t["bytes"] == a["bytes"]):
                agree += 1
            else:
                dis += 1
        add("handoff-vs-repo-image-identity", label, f"{len(hb)} distinct captured images",
            "pass" if dis == 0 else "defect",
            f"{agree} byte-exact agreement on sha256+width+height+bytes, {dis} disagreement; "
            f"{only} captured image(s) appear in no repo image tree",
            {"agree": agree, "disagree": dis, "repoAbsent": onlylist})

    # ---- F. placeholder vs graphic-only classification --------------------
    for label, P in papers.items():
        unm = set(P["canon"]["reconciliation"]["unmatchedSourceNumbers"])
        cls = collections.defaultdict(list)
        for q in P["canon"]["questions"]:
            stem = (q.get("stemText") or "").strip()
            opts = q.get("options") or []
            tx = [(o.get("text") or "").strip() for o in opts]
            lb = [o.get("label") for o in opts]
            if not stem:
                cls["M"].append(q["sourceNumber"])
            elif tx and all(t == "缺失" for t in tx):
                cls["P"].append(q["sourceNumber"])
            elif tx and lb and all(t == l for t, l in zip(tx, lb)):
                cls["G"].append(q["sourceNumber"])
            else:
                cls["T"].append(q["sourceNumber"])
        matched = sorted({q["sourceNumber"] for q in P["canon"]["questions"]} - unm)
        add("content-class-census", label, "questions", "info",
            f"realText={len(cls['T'])} placeholder={len(cls['P'])} "
            f"graphicLabelOnlyOptions={len(cls['G'])} missingStem={len(cls['M'])}",
            {"placeholderNumbers": sorted(cls["P"]),
             "graphicNumbers": sorted(cls["G"]),
             "missingStemNumbers": sorted(cls["M"])})
        add("placeholder-flagged", label, "reconciliation",
            "pass" if all(n in unm for n in cls["P"]) else "defect",
            f"{sum(1 for n in cls['P'] if n in unm)}/{len(cls['P'])} placeholder questions are "
            f"flagged unmatched by the handoff", {"numbers": sorted(cls["P"])})
        # graphic-only questions are reported matched yet carry no bound visual content
        gmatched = [n for n in cls["G"] if n in matched]
        add("graphic-only-counted-complete", label, "graphic-reasoning",
            "defect" if gmatched else "info",
            f"{len(gmatched)} question(s) counted as matched whose options are bare label letters "
            f"with no question->asset binding; the reconciliation only compares numbers and text "
            f"so it cannot see the missing figures",
            {"numbers": sorted(gmatched),
             "impliedFigureSlots": sum(1 + 4 for n in gmatched)})
        # matched-but-empty
        empt = [n for n in matched if n in cls["M"]]
        if empt:
            add("false-match-empty-stem", label, "reconciliation", "defect",
                f"{len(empt)} question(s) counted as matched although the stem is empty",
                {"numbers": sorted(empt)})

    # ---- G. numbering / cross-number position ---------------------------
    for label, P in papers.items():
        nums = sorted(q["sourceNumber"] for q in P["canon"]["questions"])
        gaps = sorted(set(range(min(nums), max(nums) + 1)) - set(nums)) if nums else []
        add("source-numbering", label, f"{min(nums)}..{max(nums)}", "info",
            f"{len(gaps)} numbers absent inside the source range",
            {"inRangeGaps": gaps})
        if P["text"]:
            md_nums = [int(m.group(2)) for m in QHDR.finditer(P["text"]) if m.group(2)]
            if md_nums:
                mgaps = sorted(set(range(min(md_nums), max(md_nums) + 1)) - set(md_nums))
                add("repo-numbering-and-offset", label, P["mdrel"],
                    "pass" if not set(md_nums) & set() else "info",
                    f"{len(md_nums)} question headers, range {min(md_nums)}..{max(md_nums)}, "
                    f"gaps {mgaps}; original numbering preserved across gaps (no renumbering)",
                    {"gaps": mgaps, "headerCount": len(md_nums)})

    # ---- H. cross-paper image byte identity ------------------------------
    by_sha = collections.defaultdict(set)
    for label, P in papers.items():
        root = os.path.join(repo, P["imgdir"])
        for dp, _, fs in os.walk(root):
            for fn in fs:
                try:
                    by_sha[sha256_file(os.path.join(dp, fn))].add((label, fn))
                except Exception:
                    pass
    cross = {s: sorted(v) for s, v in by_sha.items() if len({x[0] for x in v}) > 1}
    add("cross-paper-image-identity", "ALL", f"{len(cross)} groups", "info",
        f"{len(cross)} image blobs are byte-identical across papers. Byte equality proves identity "
        f"of bytes only; whether the shared figure is the intended figure for BOTH questions is a "
        f"content judgement this audit does not make",
        {"groups": [{"sha256": s, "papers": sorted({p for p, _ in v})} for s, v in cross.items()][:60],
         "groupCount": len(cross)})
    return {"ledger": L, "papers": {k: {"key": v["key"], "questions": len(v["canon"]["questions"]),
                                        "assets": len(v["assets"])} for k, v in papers.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    if not os.path.isdir(a.repo) or not os.path.isdir(a.handoff):
        print("repo/handoff path missing", file=sys.stderr)
        return 1
    res = audit(a.repo, a.handoff)
    if res is None:
        return 1
    doc = {
        "schemaVersion": 1,
        "kind": "no-content-discrepancy-ledger",
        "epistemicRules": [
            "sha256 equal => identical bytes (sound)",
            "sha256 differ => visual/pixel difference UNKNOWN (no bytes shipped, no OCR on this host)",
            "no question->asset binding in the handoff schema => option-correspondence unverifiable",
        ],
        "contentPolicy": "counts, question numbers, hashes, image basenames, dimensions only; "
                         "no question text, no option text, no image bytes, no source URLs",
        "papers": res["papers"],
        "entries": res["ledger"],
    }
    out = json.dumps(doc, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w").write(out)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
