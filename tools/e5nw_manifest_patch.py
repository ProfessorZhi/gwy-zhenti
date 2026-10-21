#!/usr/bin/env python3
"""Row-level, idempotent manifest updater for the E5NW delivery.

Only lines whose `path` matches an entry in the updates file are rewritten; every
other line is preserved byte-for-byte. Each entry carries the pre-merge file
SHA256 it was built against, so a stale row (changed by another lane) fails
loudly instead of being overwritten. Re-running after the row already carries the
final SHA is a no-op, which makes rebases safe.

Usage:
  python3 tools/e5nw_manifest_patch.py apply  --updates reports/E5NW-MANIFEST-UPDATES-20261022.json
  python3 tools/e5nw_manifest_patch.py check  --updates reports/E5NW-MANIFEST-UPDATES-20261022.json
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "catalog/manifest.jsonl"
ALLOWED = {"bytes", "sha256", "answer_blocks", "missing_answer_numbers", "issues",
           "notes", "source_validation"}

def load_updates(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("updates", [])
    if not isinstance(data, list) or not data:
        raise SystemExit("updates file must contain a non-empty list")
    for u in data:
        if set(u["fields"]) - ALLOWED:
            raise SystemExit("disallowed manifest field in " + u["path"])
    return data

def run(manifest: Path, updates: list[dict], apply: bool):
    raw = manifest.read_bytes()
    lines = raw.splitlines(keepends=True)
    index = {}
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        row = json.loads(line)
        p = row.get("path")
        if p in index:
            raise SystemExit("duplicate manifest path: " + str(p))
        index[p] = (i, row)
    applied = unchanged = 0
    for u in updates:
        if u["path"] not in index:
            raise SystemExit("manifest path missing: " + u["path"])
        i, row = index[u["path"]]
        if row.get("sha256") == u["final_sha256"]:
            unchanged += 1
            continue
        if row.get("sha256") != u["expected_before_sha256"]:
            raise SystemExit("manifest conflict (row changed since build): " + u["path"])
        merged = dict(row); merged.update(u["fields"])
        lines[i] = (json.dumps(merged, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n").encode("utf-8")
        applied += 1
    if apply and applied:
        tmp = manifest.with_suffix(".jsonl.tmp")
        tmp.write_bytes(b"".join(lines))
        os.replace(tmp, manifest)
    return {"status": "ok", "rows_to_update": applied, "already_final": unchanged,
            "total_updates": len(updates), "manifest": str(manifest)}

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["apply", "check"])
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--updates", required=True)
    args = ap.parse_args(argv)
    print(json.dumps(run(Path(args.manifest), load_updates(Path(args.updates)),
                         args.command == "apply"), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
