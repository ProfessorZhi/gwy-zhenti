#!/usr/bin/env bash
# One bounded hourly pass for the offline pipeline. This is NOT a daemon:
# it never loops, never sleeps waiting for new work and never refreshes Fenbi by itself.
#
# Required:
#   GWY_PIPELINE_CONFIG=/abs/path/to/config.json
# Optional:
#   GWY_COLLECTOR_BUDGET=2
#   GWY_COLLECTOR_ADAPTER=/abs/path/to/owner-adapter.mjs  (omit until the real owner is wired)
#   GWY_WORKER_ADAPTER=/abs/path/to/worker-adapter.mjs    (offline consumer, no browser)
set -u

: "${GWY_PIPELINE_CONFIG:?set GWY_PIPELINE_CONFIG to the pipeline config file}"
NODE="${NODE:-node}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
CLI="$HERE/src/cli.mjs"
RUN_ID="hourly-$(date -u +%Y%m%dT%H%M%SZ)-$$"
BUDGET="${GWY_COLLECTOR_BUDGET:-2}"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

run() {
  printf '[%s] %s %s\n' "$(stamp)" "$NODE" "$CLI $*"
  "$NODE" "$CLI" "$@"
  local rc=$?
  printf '[%s] exit=%s\n' "$(stamp)" "$rc"
  return "$rc"
}

FINAL=0

# 1) Recover leases left by a crashed process. Never creates jobs.
run reconcile --config "$GWY_PIPELINE_CONFIG" || FINAL=$?

# 2) Current queue/health snapshot.
run status --config "$GWY_PIPELINE_CONFIG" || FINAL=$?

# 3) One bounded collector pass. Without a real owner adapter this is the expected signal:
#    exit 2, reason=collector_unwired, claimed=0. It must not be mistaken for a capture success.
if [ -n "${GWY_COLLECTOR_ADAPTER:-}" ]; then
  COLLECTOR_OUT="$("$NODE" "$CLI" drain --config "$GWY_PIPELINE_CONFIG" --role collector \
    --budget "$BUDGET" --owner "$RUN_ID" --adapter-module "$GWY_COLLECTOR_ADAPTER" 2>&1)"
  COLLECTOR_RC=$?
else
  COLLECTOR_OUT="$("$NODE" "$CLI" drain --config "$GWY_PIPELINE_CONFIG" --role collector \
    --budget "$BUDGET" --owner "$RUN_ID" 2>&1)"
  COLLECTOR_RC=$?
fi
printf '%s\n' "$COLLECTOR_OUT"
printf '[%s] collector exit=%s\n' "$(stamp)" "$COLLECTOR_RC"
COLLECTOR_REASON="$(printf '%s\n' "$COLLECTOR_OUT" | sed -n 's/.*"reason": "\([^"]*\)".*/\1/p' | head -n 1)"
if [ "$COLLECTOR_RC" -eq 2 ] && [ "$COLLECTOR_REASON" = "collector_unwired" ]; then
  printf '[%s] collector adapter is not wired; no capture was attempted (expected signal, exit 2)\n' "$(stamp)"
  FINAL=2
elif [ "$COLLECTOR_RC" -ne 0 ]; then
  FINAL="$COLLECTOR_RC"
fi

# 4) Optional one bounded offline consumer pass. Omit until an adapter is supplied.
if [ -n "${GWY_WORKER_ADAPTER:-}" ]; then
  run drain --config "$GWY_PIPELINE_CONFIG" --role normalizer --budget "${GWY_WORKER_BUDGET:-4}" \
    --owner "$RUN_ID-worker" --adapter-module "$GWY_WORKER_ADAPTER" || FINAL=$?
fi

# 5) Reviewer/verifier only write advisory manifests; nothing is approved automatically.
run drain --config "$GWY_PIPELINE_CONFIG" --role reviewer --budget 1 || FINAL=$?

# 6) Reconcile again and record the final status.
run reconcile --config "$GWY_PIPELINE_CONFIG" || FINAL=$?
run status --config "$GWY_PIPELINE_CONFIG" || FINAL=$?

exit "$FINAL"
