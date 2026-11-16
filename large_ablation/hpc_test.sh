#!/bin/bash
# =============================================================================
# hpc_test.sh - time-limited functional test of the large-instance ablation
#
# Purpose: check that everything runs on the HPC (numba, data, both modules,
# parallel workers, resume, output) and get a first CPU-time measurement.
# It does NOT run the real experiment (30 seeds x 50 iterations).
#
# Usage (inside this folder; keep running after logout):
#   nohup bash hpc_test.sh > hpc_test.log 2>&1 &
#   tail -f hpc_test.log
#
# Options (environment variables):
#   WORKERS=24        parallel workers (<= number of PHYSICAL cores; default 24)
#   LIMIT_MIN=40      no new job is started after this many minutes
#   GRACE_MIN=10      running jobs may continue this long, then are killed
#   PYTHON=python3    interpreter of the environment that has numba
#   FULL_PIPELINE=1   also test run -> aggregate -> analyze (3 iterations,
#                     2 seeds, 12 instances, 2 configs = 48 short jobs)
#
# Expected duration: smoke test 1-3 min, calibration about 15-25 min
# (24 jobs x 5 iterations; the n=200 instances are the slowest).
# Hard upper bound: LIMIT_MIN + GRACE_MIN (+ smoke test).
# =============================================================================
set -u
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python3}"
WORKERS="${WORKERS:-24}"
LIMIT_MIN="${LIMIT_MIN:-40}"
GRACE_MIN="${GRACE_MIN:-10}"
OUT="results_hpc_test"

echo "== $(date '+%F %T') environment"
hostname
"$PY" --version
echo "cores (logical): $(nproc)"
"$PY" -c "import numpy, pandas, openpyxl, numba; print('numpy', numpy.__version__, '| pandas', pandas.__version__, '| numba', numba.__version__)" \
  || { echo "A required package is missing. Try: $PY -m pip install --user -r requirements.txt"; exit 1; }
"$PY" -c "import scipy; print('scipy', scipy.__version__)" \
  || echo "(scipy missing: only 'analyze' needs it)"

echo
echo "== $(date '+%F %T') 1/3 smoke test (small instance, 3 iterations)"
"$PY" tests/test_smoke.py || { echo "SMOKE TEST FAILED"; exit 1; }

echo
echo "== $(date '+%F %T') 2/3 calibration: 12 instances x 2 configs, seed 0, 5 iterations"
"$PY" run_large_ablation.py select || exit 1
"$PY" run_large_ablation.py calibrate --workers "$WORKERS" --iters 5 \
      --time-limit-min "$LIMIT_MIN" --grace-min "$GRACE_MIN" --out "$OUT"
echo "(calibration table: $OUT/calibration.csv)"

if [ "${FULL_PIPELINE:-0}" = "1" ]; then
  echo
  echo "== $(date '+%F %T') 3/3 pipeline test: run -> aggregate -> analyze"
  "$PY" run_large_ablation.py run --workers "$WORKERS" --iters 3 --seeds 0-1 \
        --time-limit-min "$LIMIT_MIN" --grace-min "$GRACE_MIN" \
        --out "${OUT}_pipeline" --yes
  "$PY" run_large_ablation.py aggregate --out "${OUT}_pipeline"
  "$PY" run_large_ablation.py analyze --out "${OUT}_pipeline"
else
  echo
  echo "== 3/3 skipped (set FULL_PIPELINE=1 to also test run/aggregate/analyze)"
fi

echo
echo "== $(date '+%F %T') done. Send back: hpc_test.log and $OUT/calibration.csv"
