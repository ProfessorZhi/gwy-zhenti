#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline fingerprint-shard QA.

Input is a metadata-only shard (sourceNumber/repositoryNumber/category/imageSha/
contentHash/optionHash/optionCount/score) plus the repository Markdown.  The
checker never reads a browser profile, cookie, token or practice URL and never
emits question text, options or image bytes.

Key rules:
  * text identity = normalized_equal only (NFKC/fullwidth/punctuation stripping);
  * near/weak are candidates, not exact;
  * ambiguous/weak may be resolved only by a *unique* full SHA-256 image match
    (multiplicity 1 on both sides);
  * image chunking / image conflict stays needs_review or unknown;
  * Q44 of Shanghai keeps its source-explanation dispute.

This is a self-contained stdlib tool so it can run on the QA host without npm.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys
import unicodedata

MATCHED = "matched"
NEEDS_REVIEW = "needs_review"
UNKNOWN = "unknown"


def normalize_text(value):
    s = str(value if value is not None else "")
    s = re.sub(r"<[^>]*>", " ", s)
    s = unicodedata.normalize("NFKC", s)
    s = "".join(
        chr(ord(c) - 0xFEE0) if "！" <= c <= "～" else c for c in s
    )
    s = s.replace("　", " ")
    s = re.sub(r"[（(]\s*[)）]", "", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^一-龥A-Za-z0-9]", "", s)
    return s.strip()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(stem, options):
    """Return the same contentHash/optionHash used by the batch shard."""
    ns = normalize_text(stem)
    no = [normalize_text(x) for x in options]
    return {
        "contentHash": sha256_bytes((ns + "||" + "|".join(no)).encode("utf-8")),
        "optionHash": sha256_bytes("|".join(no).encode("utf-8")),
        "optionCount": len(options),
    }


def parse_repo_markdown(text, image_loader=None):
    """Parse `## 第 N 题` blocks. image_loader(relpath)->bytes|None."""
    parts = re.split(r"^#{2,3}\s*第\s*(\d+)\s*题[^\n]*$", text, flags=re.M)
    out = {}
    for i in range(1, len(parts), 2):
        n = int(parts[i])
        body = parts[i + 1] or ""
        options, stem_lines, image_shas = [], [], []
        for line in body.split("\n"):
            m = re.match(
                r"^\s*[-*]?\s*\*\*([A-Z])\*\*[.、．)）]?\s*(.*)$", line
            ) or re.match(r"^\s*([A-D])[.、．)）]\s*(.*)$", line)
            if m:
                options.append(m.group(2))
            elif line.strip() and not re.match(r"^\s*(---|>|\|)", line):
                stem_lines.append(line)
        for ref in re.findall(r'src="([^"]+)"', body):
            idx = ref.find("图片/")
            if idx < 0:
                continue
            rel = ref[idx:]
            if image_loader is not None:
                data = image_loader(rel)
                if data is not None:
                    image_shas.append(sha256_bytes(data))
        rec = fingerprint(" ".join(stem_lines), options)
        rec["imageShas"] = sorted(set(image_shas))
        rec["imageRefs"] = len(re.findall(r'src="([^"]+)"', body))
        out[n] = rec
    return out


def load_shard(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_pr62_mapping(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    case = doc["cases"][0] if isinstance(doc, dict) and "cases" in doc else doc
    return {m["sourceNumber"]: m for m in case.get("mapping", [])}


def resolve_by_image(slots, repo):
    """Resolve ambiguous/weak slots only when image SHA-256 is unique 1:1.

    Returns {sourceNumber: repositoryNumber}.  A match requires:
      * source category is ambiguous or weak;
      * non-empty source image SHAs;
      * every shared SHA has source multiplicity 1 and repository multiplicity 1;
      * exactly one repository question intersects the source set;
      * the target repository number is not already used by a bound slot.
    """
    src_mult = collections.Counter(
        h for q in slots for h in set(q.get("imageSha") or [])
    )
    repo_index = collections.defaultdict(list)
    for num, rec in repo.items():
        for h in rec["imageShas"]:
            repo_index[h].append(num)
    repo_mult = {h: len(nums) for h, nums in repo_index.items()}
    used = {
        q["repositoryNumber"]
        for q in slots
        if q.get("repositoryNumber")
    }
    resolved = {}
    for q in sorted(slots, key=lambda x: x["sourceNumber"]):
        if q.get("category") not in ("ambiguous", "weak"):
            continue
        src = set(q.get("imageSha") or [])
        if not src:
            continue
        hits = set()
        for h in src:
            if src_mult[h] == 1 and repo_mult.get(h, 0) == 1:
                hits.update(repo_index.get(h, []))
        if len(hits) != 1:
            continue
        target = next(iter(hits))
        if target in used and q.get("repositoryNumber") != target:
            continue
        resolved[q["sourceNumber"]] = target
        used.add(target)
    return resolved


def _image_match(src_imgs, repo_imgs):
    if not src_imgs and not repo_imgs:
        return "not_applicable"
    if src_imgs and repo_imgs and set(src_imgs) == set(repo_imgs):
        return "identical_set"
    if src_imgs and repo_imgs and set(src_imgs) & set(repo_imgs):
        return "partial_overlap"
    if src_imgs and not repo_imgs:
        return "repo_missing"
    if not src_imgs and repo_imgs:
        return "source_missing"
    return "disjoint"


def classify_slot(q, repo_slot, pr_grade=None, resolved=False, pr_mode=False):
    """Return (status, basis, textFingerprint, imageMatch) for one slot."""
    text = "unverified"
    if repo_slot:
        if (
            q.get("contentHash") == repo_slot["contentHash"]
            and q.get("optionHash") == repo_slot["optionHash"]
        ):
            text = "exact"
        elif q.get("contentHash") == repo_slot["contentHash"]:
            text = "option_mismatch"
        else:
            text = "not_equal"
    image = _image_match(
        q.get("imageSha") or [],
        repo_slot["imageShas"] if repo_slot else [],
    )
    cat = q.get("category")
    if pr_mode and q["sourceNumber"] == 44:
        return NEEDS_REVIEW, "q44_source_dispute", text, image
    if cat == "source_stub":
        return UNKNOWN, "source_stub", text, image
    if cat == "repo_missing":
        return UNKNOWN, "repo_missing", text, image
    if cat == "different":
        return UNKNOWN, "different", text, image
    if cat == "image_chunking_not_comparable":
        return NEEDS_REVIEW, "image_chunking_not_comparable", text, image
    if cat == "image_unknown":
        if repo_slot is None:
            return UNKNOWN, "image_unknown_no_repo", text, image
        return (
            NEEDS_REVIEW,
            "image_conflict" if image == "disjoint" else "image_unknown",
            text,
            image,
        )
    if cat == "ambiguous":
        if resolved:
            return MATCHED, "image_sha_unique", text, image
        return NEEDS_REVIEW, "ambiguous", text, image
    if cat == "weak":
        if resolved:
            return MATCHED, "image_sha_unique", text, image
        return NEEDS_REVIEW, "weak_text", text, image
    if cat == "image_sha_identical":
        if text == "exact":
            return MATCHED, "exact_text_image_sha", text, image
        if text == "not_equal" and (q.get("score") or 0) >= 0.85:
            return MATCHED, "near_text_image_sha", text, image
        return MATCHED, "image_sha_unique", text, image
    if cat == "normalized_equal":
        if text == "exact":
            return MATCHED, "exact_text", text, image
        return NEEDS_REVIEW, "fingerprint_mismatch", text, image
    if cat == "near":
        return MATCHED, "near_text", text, image
    return UNKNOWN, "unclassified", text, image


def audit(shard, repo, pr_map=None, label=None, pr_mode=False):
    pr_map = pr_map or {}
    resolved_map = resolve_by_image(shard["questions"], repo)
    rows = []
    for q in sorted(shard["questions"], key=lambda x: x["sourceNumber"]):
        rn = resolved_map.get(q["sourceNumber"], q.get("repositoryNumber"))
        r = repo.get(rn) if rn else None
        grade = pr_map.get(q["sourceNumber"], {}).get("grade") if pr_mode else None
        status, basis, text, image = classify_slot(
            q, r, grade, q["sourceNumber"] in resolved_map, pr_mode
        )
        rows.append(
            {
                "sourceNumber": q["sourceNumber"],
                "repositoryNumber": rn,
                "category": q.get("category"),
                "pr62Grade": grade,
                "textFingerprint": text,
                "imageMatch": image,
                "status": status,
                "basis": basis,
                "resolvedByImage": q["sourceNumber"] in resolved_map,
                "contentHash12": (q.get("contentHash") or "")[:12],
                "optionHash12": (q.get("optionHash") or "")[:12],
                "repoContentHash12": (r["contentHash"][:12] if r else None),
                "imageSha12": (
                    sorted(set(q.get("imageSha") or []))[0][:12]
                    if q.get("imageSha")
                    else None
                ),
                "repoImageSha12": (
                    sorted(set(r["imageShas"]))[0][:12]
                    if r and r["imageShas"]
                    else None
                ),
            }
        )
    counts = collections.Counter(r["status"] for r in rows)
    basis_counts = collections.Counter(r["basis"] for r in rows)
    nums = [r["repositoryNumber"] for r in rows if r["repositoryNumber"]]
    return {
        "sourceId": str(shard.get("sourceId")),
        "label": label or shard.get("label"),
        "repoPaper": shard.get("repoPaper"),
        "slots": len(rows),
        "repoQuestions": len(repo),
        "oneToOne": len(nums) == len(set(nums)),
        "repoNumberRange": [min(nums), max(nums)] if nums else None,
        "counts": dict(sorted(counts.items())),
        "basisCounts": dict(sorted(basis_counts.items())),
        "resolvedByImage": [
            {"sourceNumber": k, "repositoryNumber": v}
            for k, v in sorted(resolved_map.items())
        ],
        "rows": rows,
    }


def _image_loader(root):
    def load(rel):
        try:
            with open(os.path.join(root, rel), "rb") as fh:
                return fh.read()
        except OSError:
            return None

    return load


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shard", required=True)
    ap.add_argument("--paper", required=True, help="repository Markdown for the paper")
    ap.add_argument("--image-root", required=True, help="root containing 图片/...")
    ap.add_argument("--pr62", help="optional PR62 reorder JSON (Shanghai)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label")
    args = ap.parse_args(argv)
    shard = load_shard(args.shard)
    with open(args.paper, encoding="utf-8") as fh:
        repo = parse_repo_markdown(fh.read(), _image_loader(args.image_root))
    pr_map = load_pr62_mapping(args.pr62)
    result = audit(
        shard,
        repo,
        pr_map,
        label=args.label,
        pr_mode=bool(args.pr62),
    )
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(
        "%s slots=%d matched=%d needs_review=%d unknown=%d 1:1=%s -> %s"
        % (
            result["sourceId"],
            result["slots"],
            result["counts"].get(MATCHED, 0),
            result["counts"].get(NEEDS_REVIEW, 0),
            result["counts"].get(UNKNOWN, 0),
            result["oneToOne"],
            args.out,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
