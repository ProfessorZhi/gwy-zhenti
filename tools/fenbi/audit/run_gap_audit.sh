#!/usr/bin/env bash
# Offline re-verification for the missing-25 evidence audit.
#
# Runs the two checks that need no network and no credentials:
#   1. library-side gap audit   (front-matter declaration vs headings present)
#   2. 江苏2025C backfill vs its recorded A-class donor blocks
#
# Writes JSON into the output directory (default: a temp dir). Nothing is
# modified in the repository.
#
# Usage:  bash tools/fenbi/audit/run_gap_audit.sh [OUT_DIR]

set -euo pipefail

AUDIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$AUDIT_DIR/../../.." && pwd)"
OUT_DIR="${1:-$(mktemp -d)}"
mkdir -p "$OUT_DIR"

echo "repo root : $REPO_ROOT"
echo "output dir: $OUT_DIR"
echo

echo "### 1. gap audit (declared missing vs headings present)"
python3 "$AUDIT_DIR/gap_audit.py" --repo "$REPO_ROOT" --out "$OUT_DIR/gap-audit.json"
python3 - "$OUT_DIR/gap-audit.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps(doc["summary"], ensure_ascii=False))
for paper in doc["papers"]:
    print(f"  {paper['label']:14} {paper['status']:26} "
          f"headings={paper.get('heading_count')} "
          f"declared_total={paper.get('frontmatter', {}).get('对照题本题量')} "
          f"still_absent={paper.get('still_absent_numbers')}")
PY

echo
echo "### 2. donor comparison for the 江苏2025C backfill"
python3 "$AUDIT_DIR/donor_compare.py" --repo "$REPO_ROOT" --out "$OUT_DIR/donor-compare.json"
python3 - "$OUT_DIR/donor-compare.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps(doc["summary"], ensure_ascii=False))
for item in doc["items"]:
    flag = "CROSS-NUMBER" if item["donor_number_differs_from_recipient"] else "same-number "
    print(f"  C{item['number']:>3} <- A{item['declared_donor_number']:<4} {flag} "
          f"identical={item.get('folded_identical_to_donor')} "
          f"sim={item.get('folded_similarity')} "
          f"scan_clips={item['saved_scan_clip_metadata_count']}")
PY

echo
echo "### network step (optional, no credentials) — verifies the report's pinned sources"
echo "    python3 $AUDIT_DIR/fetch_pinned_sources.py --out /tmp/pinned-25"
echo "    (downloads are third-party documents; do not commit them)"
