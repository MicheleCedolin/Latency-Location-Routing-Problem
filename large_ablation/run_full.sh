#!/bin/bash
# =============================================================================
# run_full.sh - complete staged experiment: Base+SO vs Base+SO+DS on all
# Prins and Tuzun instances, 30 seeds x 50 iterations, resumable.
#
#   Stage 0: small Prins (n=20, 50)          12 instances
#   Stage 1: n=100 (Prins 12 + Tuzun 12)     24 instances
#   Stage 2: Tuzun n=150                     12 instances
#   Stage 3: Prins n=200                      6 instances
#   Stage 4: Tuzun n=200                     12 instances
# A stage is finished before the next one starts; inside a stage every
# instance is completed (30 paired runs per configuration) before the next.
#
# Start (survives logout):
#   setsid nohup bash run_full.sh > run_full.log 2>&1 &
# Watch:
#   tail -f run_full.log          or   bash status.sh
# Interim results at any time (does not disturb the run):
#   python3 run_large_ablation.py aggregate --out results_full
#   python3 run_large_ablation.py analyze   --out results_full
# Stop (finished runs are kept):  pkill -f run_large_ablation.py ; pkill -f run_full.sh
# Resume after a stop / crash / reboot: start the same command again.
#
# Environment variables: WORKERS (30)  OUT (results_full)  PYTHON (python3)
#   MAX_RESTARTS (10)  AGG_EVERY_SEC (3600)  CAL (calibration.csv for ETA)
# =============================================================================
set -u
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python3}"
WORKERS="${WORKERS:-30}"
OUT="${OUT:-results_full}"
SEL="${SEL:-selected_all.csv}"
MAX_RESTARTS="${MAX_RESTARTS:-10}"
AGG_EVERY_SEC="${AGG_EVERY_SEC:-3600}"
CAL="${CAL:-results_hpc_test/calibration.csv}"
EXTRA="${EXTRA:-}"            # extra runner arguments (testing only)

CALARG=""
[ -f "$CAL" ] && CALARG="--calibration $CAL"
mkdir -p "$OUT"
[ -f "$SEL" ] || "$PY" run_large_ablation.py select --all || exit 1

echo "== $(date '+%F %T') start on $(hostname); workers=$WORKERS out=$OUT"
"$PY" run_large_ablation.py plan --selection "$SEL" --workers "$WORKERS" \
      --out "$OUT" $CALARG $EXTRA || exit 1

# hourly interim aggregation (tables in $OUT/aggregated)
( while true; do
    sleep "$AGG_EVERY_SEC"
    "$PY" run_large_ablation.py aggregate --out "$OUT" $EXTRA \
        > "$OUT/aggregate_last.log" 2>&1
  done ) &
AGG_PID=$!
trap 'kill $AGG_PID 2>/dev/null' EXIT

attempt=0
while true; do
  "$PY" run_large_ablation.py run --selection "$SEL" --workers "$WORKERS" \
        --out "$OUT" $CALARG $EXTRA --yes && break
  attempt=$((attempt + 1))
  if [ "$attempt" -gt "$MAX_RESTARTS" ]; then
    echo "== $(date '+%F %T') giving up after $MAX_RESTARTS restarts"
    break
  fi
  echo "== $(date '+%F %T') jobs still pending; restart $attempt/$MAX_RESTARTS in 120 s"
  sleep 120
done

echo "== $(date '+%F %T') final aggregation and analysis"
"$PY" run_large_ablation.py aggregate --out "$OUT" $EXTRA
"$PY" run_large_ablation.py analyze --out "$OUT" $EXTRA
echo "== $(date '+%F %T') finished"
