#!/usr/bin/env bash
# Default-OFF gate for content-only auto-main. Invoked by run-pipeline.sh; also testable alone.
# Only AUTO_MAIN_APPLY=1 adds --apply. Anything else (0, false, unset) is a dry run.
set -u
cd "$(dirname "$0")"

if [ "${AUTO_MAIN_CONTENT:-0}" != 1 ]; then
  echo "auto-main disabled"
  exit 0
fi
for name in AUTO_MAIN_SETTINGS AUTO_MAIN_CREDENTIALS AUTO_MAIN_TRUSTED_ROOT; do
  eval "value=\${$name:-}"
  if [ -z "$value" ]; then
    echo "auto-main skipped: $name missing"
    exit 0
  fi
done
if [ ! -f "$AUTO_MAIN_SETTINGS" ] || [ ! -f "$AUTO_MAIN_CREDENTIALS" ] || [ ! -d "$AUTO_MAIN_TRUSTED_ROOT" ]; then
  echo "auto-main skipped: settings/credentials/trusted-root missing"
  exit 0
fi

apply_flag=""
if [ "${AUTO_MAIN_APPLY:-0}" = 1 ]; then
  apply_flag=--apply
fi

exec node src/auto-main-run.mjs --repo "$REPO" --source-repo "$REPO" \
  --source-ref "${AUTO_MAIN_SOURCE_REF:-integ/2026-10-19}" \
  --settings "$AUTO_MAIN_SETTINGS" --credentials "$AUTO_MAIN_CREDENTIALS" \
  --trusted-root "$AUTO_MAIN_TRUSTED_ROOT" $apply_flag
