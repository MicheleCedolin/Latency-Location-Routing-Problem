#!/bin/bash
# LLRP depot-layer pilot launcher (port of the CLRP 6.4.0 pilot). One ARM per job; arms differ ONLY in the depot-impact flags.
#   ARM=off               6.2 heuristics, no depot events (control)
#   ARM=structural        clean.6.3.1 layer with the settings of the 6.3.1 screening pilot
#   ARM=adaptive_explore  clean.6.4.0 time schedule + scaled event cap + untried targets, NO exploitation (factor isolation)
#   ARM=adaptive          clean.6.4.0 full: exploration then set-restricted intensification
# Does not modify any earlier result directory.
set -euo pipefail
cd "${KIT_ROOT:-${SGE_O_WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
ARM="${ARM:-adaptive}"
INSTANCES="${INSTANCES:-coord100-10-1b:coord200-10-1b}"
TIME_LIMIT="${TIME_LIMIT:-120}"
NSEEDS="${NSEEDS:-2}"
WORKERS="${WORKERS:-${NSLOTS:-8}}"
METHODS_FILE="${METHODS_FILE:-hpc/methods_pilot_adaptive.txt}"
ORDER="${ORDER:-seed}"
OUT="${OUT:-analysis/pilot64_${ARM}_$(echo "$INSTANCES" | tr ':,; ' '____')_${TIME_LIMIT}s_${NSEEDS}seeds}"
case "$ARM" in
  off)
    EXTRA_ARGS="--depot-impact off" ;;
  structural)
    EXTRA_ARGS="--depot-impact structural --depot-impact-every ${DEPOT_EVERY:-8} --depot-impact-max-share ${DEPOT_SHARE:-0.15} --depot-impact-event-seconds ${DEPOT_EVENT_SEC:-4.0} --depot-impact-min-interval ${DEPOT_INTERVAL:-2.0}" ;;
  adaptive|adaptive_explore)
    EXTRA_ARGS="--depot-impact adaptive --depot-impact-max-share ${DEPOT_SHARE_ADAPTIVE:-0.30} --depot-impact-event-seconds ${DEPOT_EVENT_SEC:-4.0} --depot-impact-min-interval ${DEPOT_INTERVAL:-2.0}"
    EXTRA_ARGS="$EXTRA_ARGS --depot-impact-first-frac ${FIRST_FRAC:-0.05} --depot-impact-period-frac ${PERIOD_FRAC:-0.06} --depot-impact-exploit-slice ${EXPLOIT_SLICE:-0.04} --depot-impact-cap-exp ${CAP_EXP:-3.0}"
    if [ "$ARM" = adaptive_explore ]; then EXTRA_ARGS="$EXTRA_ARGS --depot-impact-exploit-start 1.0"
    else EXTRA_ARGS="$EXTRA_ARGS --depot-impact-exploit-start ${EXPLOIT_START:-0.30}"; fi ;;
  *) echo 'ERROR: ARM must be off, structural, adaptive_explore or adaptive' >&2; exit 2 ;;
esac
export INSTANCES TIME_LIMIT NSEEDS WORKERS METHODS_FILE ORDER OUT EXTRA_ARGS
mkdir -p "$OUT"
# Record host and CPU: wall-clock budgets buy different amounts of search on different nodes (see the Phase A P50 note).
{ echo "arm=$ARM"; echo "host=$(hostname)"; echo "date_utc=$(date -u +%FT%TZ)"; echo "nproc=$(nproc 2>/dev/null || echo ?)"; \
  echo "job_id=${JOB_ID:-none}"; echo "cpu=$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^ //')"; } > "$OUT/run_host.txt"
exec bash hpc/run.sh
