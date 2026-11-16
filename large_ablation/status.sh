#!/bin/bash
# status.sh - progress of the full experiment (safe to run at any time)
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python3}"
WORKERS="${WORKERS:-30}"
OUT="${OUT:-results_full}"
SEL="${SEL:-selected_all.csv}"
CAL="${CAL:-results_hpc_test/calibration.csv}"
CALARG=""
[ -f "$CAL" ] && CALARG="--calibration $CAL"
date '+%F %T'
if pgrep -f run_large_ablation.py > /dev/null; then
  echo "runner: RUNNING ($(pgrep -f 'run_large_ablation.py run' | wc -l) process(es))"
else
  echo "runner: not running"
fi
"$PY" run_large_ablation.py plan --selection "$SEL" --workers "$WORKERS" \
      --out "$OUT" $CALARG
echo "--- last progress lines"
tail -n 5 "$OUT/progress.log" 2>/dev/null
echo "--- errors so far: $(grep -c ' ERROR ' "$OUT/progress.log" 2>/dev/null)"
