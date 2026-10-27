#!/usr/bin/env bash
# 全量排版检查 — 只读、离线、单进程
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3
REPO="${R1F_REPO:-$HERE/repo-main}"
OUT="${R1F_OUT:-$HERE/out/baseline}"

gate() {
  "$PY" -I - <<'PYEOF'
import re,sys
mem=0
for line in open('/proc/meminfo'):
    if line.startswith('MemAvailable:'):
        mem=int(line.split()[1]); break
psi=0.0
try:
    for line in open('/proc/pressure/memory'):
        if line.startswith('some'):
            m=re.search(r'avg10=([\d.]+)',line)
            if m: psi=float(m.group(1))
except OSError:
    pass
print(f"MemAvailable={mem} KiB  PSI some avg10={psi}")
sys.exit(0 if (mem>=12*1024*1024 and psi<1.0) else 2)
PYEOF
}

case "${1:-help}" in
  test)
    cd "$HERE"; exec "$PY" -I -m unittest discover -s tests -v ;;
  baseline)
    cd "$HERE"; gate
    exec "$PY" -I run.py --repo "$REPO" --out "$OUT" ;;
  highrisk)
    cd "$HERE"; gate
    "$PY" -I run.py --repo "$REPO" --out "$OUT"
    sed -n '1,120p' "$OUT/highrisk.md" ;;
  single)
    shift
    [ $# -ge 1 ] || { echo "usage: ./run.sh single <路径子串>"; exit 1; }
    cd "$HERE"; gate
    exec "$PY" -I run.py --repo "$REPO" --out "$HERE/out/single" --only "$1" ;;
  *)
    cat <<'USAGE'
usage: ./run.sh <test|baseline|highrisk|single <子串>>

  test               57 个合成负例/正例
  baseline           全量检查，写 out/baseline/{receipts.jsonl,summary.json,summary.md,highrisk.md}
  highrisk           跑完并打印前 120 行高风险卷证据
  single 江苏/2024   只查匹配子串的卷

env: R1F_REPO（默认 repo-main） R1F_OUT（默认 out/baseline）
USAGE
    exit 1 ;;
esac
