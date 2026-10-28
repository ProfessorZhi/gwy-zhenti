#!/usr/bin/env bash
# Reproduce the 11-case adjudication (read-only inputs, scratch-only outputs).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-all}" in
  collect)  python3 -I "$HERE/collect.py" ;;
  patches)  python3 -I "$HERE/make_patches.py" ;;
  verify)   python3 -I "$HERE/verify_patches.py" ;;
  cases)    python3 -I "$HERE/build_cases.py" ;;
  test)     cd "$HERE" && python3 -I -m unittest discover -s tests -v ;;
  all)
    python3 -I "$HERE/collect.py" >/dev/null
    python3 -I "$HERE/make_patches.py" >/dev/null
    python3 -I "$HERE/verify_patches.py"
    python3 -I "$HERE/build_cases.py"
    ( cd "$HERE" && python3 -I -m unittest discover -s tests )
    ;;
  *) echo "usage: ./run.sh <collect|patches|verify|cases|test|all>"; exit 1 ;;
esac
