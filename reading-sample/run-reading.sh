#!/usr/bin/env bash
# Reproduce the 92-paper reading sample (read-only inputs).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN=/home/fjd/scratch/gwy-format-final-20261028/structure/repo-main
BASE=/home/fjd/scratch/gwy-format-final-20261028/structure/out/baseline/receipts.jsonl

case "${1:-help}" in
  frame)   python3 -I "$HERE/frame.py" "$MAIN" "$BASE" "$HERE/frame.jsonl" ;;
  select)  python3 -I "$HERE/select.py" "$HERE/frame.jsonl" "$HERE/sample.jsonl" ;;
  plan)    python3 -I "$HERE/plan.py" ;;
  sweep)   python3 -I "$HERE/sweep.py" --depth full > "$HERE/sweep-all.jsonl" ;;
  view)    shift; python3 -I "$HERE/batchview.py" "$*" ;;
  packet)  shift; python3 -I "$HERE/digest.py" --path "$1" --mode "${2:-full}" ;;
  *)
    cat <<'USAGE'
usage: ./run-reading.sh <frame|select|plan|sweep|view RANKS|packet PATH [mode]>

  frame    rebuild frame.jsonl from the read-only main snapshot + baseline receipts
  select   fixed-seed (20261028) stratified selection -> sample.jsonl (92)
  plan     render SAMPLE-PLAN.md
  sweep    rebuild per-paper packets under evidence/ and sweep-all.jsonl
  view     compact view for ranks, e.g. ./run-reading.sh view 1,2,3
  packet   one-paper digest, e.g. ./run-reading.sh packet 省考/江苏/2025/申论-C卷.md full

Prereq: repo-main and repo-pr140 checkouts (see REPORT.md §0).
USAGE
    exit 1 ;;
esac
