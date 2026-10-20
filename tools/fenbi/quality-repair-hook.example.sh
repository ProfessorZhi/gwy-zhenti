#!/usr/bin/env bash
# EXAMPLE ONLY — not wired into run-pipeline.sh or any service.
# Default OFF. Set QUALITY_REPAIR=1 plus explicit local input files to run a dry-run.
set -u
cd "$(dirname "$0")"
if [ "${QUALITY_REPAIR:-0}" != 1 ]; then
  echo "quality-repair disabled (set QUALITY_REPAIR=1 with local paper/donor JSON)"
  exit 0
fi
for v in QUALITY_REPAIR_PAPERS QUALITY_REPAIR_DONORS QUALITY_REPAIR_OUT; do
  eval "value=\${$v:-}"
  [ -n "$value" ] || { echo "quality-repair skipped: $v missing"; exit 0; }
done
apply_flag=""
if [ "${QUALITY_REPAIR_APPLY:-0}" = 1 ]; then apply_flag=" --apply"; fi
exec node src/quality-repair-run.mjs --papers "$QUALITY_REPAIR_PAPERS" --donors "$QUALITY_REPAIR_DONORS" \
  --out "$QUALITY_REPAIR_OUT" ${QUALITY_REPAIR_TRUSTED_ROOT:+--trusted-root "$QUALITY_REPAIR_TRUSTED_ROOT"}${QUALITY_REPAIR_REVIEWED:+ --reviewed "$QUALITY_REPAIR_REVIEWED"}${apply_flag}
