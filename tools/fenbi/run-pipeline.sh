#!/usr/bin/env bash
# Continuous capture -> ingest -> promote -> commit -> board loop for the Dell A6000.
# Run it from an integration worktree on a non-main branch (batch-promote refuses main).
# Stops when work/fenbi/STOP exists or capture exits with anything other than 0 (done) or 2 (some partial).
#
# Environment:
#   CONCURRENCY=3        browser pages
#   INTERVAL=60          seconds to sleep when the queue is empty
#   RIGHTS_FILE=...      the user's approval file (required to promote; promotion is skipped without it)
#   ALLOW_REPLACE=1      replace existing papers with the Fenbi version (plan section 2, "粉笔优先")
#   PUSH=1               push the integration branch after each commit
#   CAPTURE=0            publisher-only mode: skip capture and read papers written by a separate collector
#   PAPERS_DIR=...       where the collector writes paper caches (default work/fenbi/papers in this worktree)
set -u
cd "$(dirname "$0")"
REPO=$(cd ../.. && pwd)
WORK="$REPO/work/fenbi"
STOP="$WORK/STOP"
INTERVAL=${INTERVAL:-60}
CONCURRENCY=${CONCURRENCY:-3}
RIGHTS_FILE=${RIGHTS_FILE:-}
HEADLESS_FLAG=${HEADLESS:+--headless}
# Strict switch: only the literal 1 enables replacement; "0" must not.
REPLACE_FLAG=""
if [ "${ALLOW_REPLACE:-0}" = 1 ]; then REPLACE_FLAG=--allow-replace; fi
mkdir -p "$WORK"
log() { printf '%s %s\n' "$(date -Iseconds)" "$*" | tee -a "$WORK/pipeline.log"; }

while [ ! -e "$STOP" ]; do
  if [ "${CAPTURE:-1}" = 1 ]; then
    node src/cli.mjs capture --all --concurrency "$CONCURRENCY" $HEADLESS_FLAG
    rc=$?
    log "capture exit=$rc"
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
      log "capture stopped; writing STOP for a human or GPT to inspect"
      echo "capture exit=$rc at $(date -Iseconds)" > "$STOP"
    fi
  fi

  node src/batch-ingest.mjs --repo-root "$REPO" --source-root "${PAPERS_DIR:-$WORK/papers}" --write --limit 1000 > "$WORK/ingest-last.jsonl"
  log "ingest exit=$? $(tail -n 1 "$WORK/ingest-last.jsonl")"

  if [ -n "$RIGHTS_FILE" ]; then
    out=$(node src/promote-all.mjs --candidate-root "$WORK/batch-ingest" --repo-root "$REPO" \
      --rights-file "$RIGHTS_FILE" --apply $REPLACE_FLAG)
    log "promote $out"
    if [ -n "$(git -C "$REPO" status --porcelain -- 国考 省考 图片 catalog/manifest.jsonl)" ]; then
      git -C "$REPO" add -- 国考 省考 图片 catalog/manifest.jsonl
      git -C "$REPO" commit -q -m "integrate(fenbi): pipeline batch $(date -u +%Y-%m-%dT%H:%MZ)"
      log "committed $(git -C "$REPO" rev-parse --short HEAD)"
      [ -n "${PUSH:-}" ] && git -C "$REPO" push -q origin HEAD && log "pushed"
    fi
  fi

  node src/pipeline-board.mjs "$WORK" "$REPO" "${PAPERS_DIR:-$WORK/papers}" | sed 's/^/board /' | tee -a "$WORK/pipeline.log"
  [ -e "$STOP" ] && break
  sleep "$INTERVAL"
done
log "pipeline loop exited"
