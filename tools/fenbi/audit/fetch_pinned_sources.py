#!/usr/bin/env python3
"""Fetch the reference documents pinned by the 25-missing source pack and verify them.

The pack records, for each paper, a fixed reference document plus its sha256.
This script downloads each one over plain HTTPS and reports whether the digest
still matches — the check that tells you whether the report's 固定源证据 is
intact or has drifted.

No credentials, no cookies, no authentication of any kind. A missing or
unreachable host is reported as such (DNS failure / HTTP status) and never as
proof that a domain is permanently gone.

Usage:
    python3 tools/fenbi/audit/fetch_pinned_sources.py --out DIR
"""

import argparse
import hashlib
import json
import os
import socket
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import default_repo_root, read_text  # noqa: E402

PACK = "reports/FULL-REPAIR-APTITUDE-25-MISSING-SOURCE-PACK-20261015.json"
USER_AGENT = "gwy-zhenti-missing25-audit/1.0 (read-only source verification)"


def source_name(path):
    """Stable, collision-free label from a paper path.

    '省考/江苏/2024/行测-A类.md' -> '江苏2024-行测-A类'; two papers can share a
    bare filename across provinces/years, so the province and year are kept.
    """
    parts = path.replace("\\", "/").split("/")
    stem = os.path.basename(path).replace(".md", "")
    tail = [p for p in parts[:-1] if p not in ("省考", "国考")]
    return "-".join(tail + [stem])


def pinned_sources(pack):
    """Yield (name, url, expected_sha256) for every pinned document in the pack."""
    for paper in pack.get("papers", []):
        stem = source_name(paper["path"])
        if paper.get("fixed_reference_url"):
            yield (f"{stem}::fixed_reference",
                   paper["fixed_reference_url"],
                   paper.get("fixed_reference_sha256"))
        extra = paper.get("additional_fixed_question_pdf")
        if extra:
            yield (f"{stem}::additional_pdf", extra["url"], extra.get("sha256"))


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=default_repo_root())
    ap.add_argument("--out", required=True,
                    help="directory for downloaded files (do not point this inside the repo)")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    repo_root = os.path.abspath(args.repo)
    if out_dir == repo_root or out_dir.startswith(repo_root + os.sep):
        print("refusing to download third-party documents into the repository tree; "
              "choose an --out directory outside it", file=sys.stderr)
        return 2
    os.makedirs(out_dir, exist_ok=True)

    pack = json.loads(read_text(os.path.join(args.repo, PACK)))
    results = []
    for name, url, expected in pinned_sources(pack):
        record = {"name": name, "url": url, "expected_sha256": expected}
        try:
            data = fetch(url, args.timeout)
            digest = hashlib.sha256(data).hexdigest()
            target = os.path.join(out_dir, name.replace("::", "__"))
            with open(target, "wb") as fh:
                fh.write(data)
            record.update({"bytes": len(data), "sha256": digest,
                           "matches_expected": digest == expected,
                           "saved_to": target})
        except socket.gaierror as exc:
            record.update({"error": "DNS_FAILURE", "detail": str(exc)})
        except urllib.error.HTTPError as exc:
            record.update({"error": f"HTTP_{exc.code}", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - report, never raise
            record.update({"error": type(exc).__name__, "detail": str(exc)})
        results.append(record)
        status = (record.get("error")
                  or ("match" if record.get("matches_expected") else "MISMATCH"))
        print(f"{name:46} {status}")

    doc = {
        "audit": "missing25-pinned-source-fetch",
        "pack": PACK,
        "note": ("Verification only. Downloaded documents are third-party material and must "
                 "not be committed to this repository."),
        "results": results,
        "summary": {
            "total": len(results),
            "matched": sum(1 for r in results if r.get("matches_expected")),
            "mismatched": sum(1 for r in results
                              if r.get("sha256") and not r.get("matches_expected")),
            "unreachable": sum(1 for r in results if r.get("error")),
        },
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out_json}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
