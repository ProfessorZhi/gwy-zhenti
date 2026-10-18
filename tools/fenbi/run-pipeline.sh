#!/usr/bin/env bash
# Continuous capture -> ingest -> promote loop for the Dell A6000.
# Runs until work/fenbi/STOP exists or capture exits with anything other than 0 (done) or 2 (some papers partial).
# Skeleton: S3 confirms the batch-promote arguments in task T4 before setting RIGHTS_FILE.
set -u
cd "$(dirname "$0")"
REPO=$(cd ../.. && pwd)
WORK="$REPO/work/fenbi"
STOP="$WORK/STOP"
INTERVAL=${INTERVAL:-60}
CONCURRENCY=${CONCURRENCY:-3}
RIGHTS_FILE=${RIGHTS_FILE:-}
HEADLESS_FLAG=${HEADLESS:+--headless}
mkdir -p "$WORK"
log() { printf '%s %s\n' "$(date -Iseconds)" "$*" | tee -a "$WORK/pipeline.log"; }

while [ ! -e "$STOP" ]; do
  node src/cli.mjs capture --all --concurrency "$CONCURRENCY" $HEADLESS_FLAG
  rc=$?
  log "capture exit=$rc"
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
    log "capture stopped; writing STOP for a human or GPT to inspect"
    touch "$STOP"
    break
  fi
  node src/batch-ingest.mjs --repo-root "$REPO" --write --limit 1000
  log "ingest exit=$?"
  if [ -n "$RIGHTS_FILE" ]; then
    node src/batch-promote.mjs --repo-root "$REPO" --candidate-dir "$WORK/batch-ingest" --rights-file "$RIGHTS_FILE" --apply
    log "promote exit=$?"
  fi
  sleep "$INTERVAL"
done
log "pipeline loop exited"
